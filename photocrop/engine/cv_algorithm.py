"""
CV 算法实现 — 场景分类 + 单场景内照片检测

原始算法来自 extract_photos_v3_final.py，仅做封装，不修改检测逻辑。
CVDetector（detector_base.py 的实现）调用本模块的 extract_photos_from_page()。

检测流程：
1. classify_scene() → 将页面划分为场景区域
2. detect_photos_in_scene() → 在每个场景内检测照片
3. extract_photos_from_page() → 综合以上两步
"""

from typing import List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage


# ============================================================
# 命名常量（原 magic numbers）
# ============================================================

# classify_scene
DOWNscale_FACTOR = 4          # 缩小倍数加速处理
MIN_REGION_COORDS = 20        # 忽略极小连通区域的坐标数
MERGE_DISTANCE_PX = 50        # 两个区域距离 < 此值则合并
EDGE_PERCENTILE = 85          # 取边缘强度前 15% 作为显著边缘
DILATION_KERNEL_SIZE = 7      # 形态学膨胀核大小
DILATION_ITERATIONS = 2       # 形态学膨胀迭代次数

# detect_photos_in_scene
MIN_SCENE_SIZE = 80           # 场景区域最小宽/高
MIN_SPLIT_SIZE = 100          # 分割检测最小尺寸
SPLIT_STD_WINDOW = 50         # 分割点两侧 std 计算窗口
SPLIT_STD_THRESHOLD = 10      # 分割点两侧 std 最小阈值
MIN_BOX_SIZE = 50             # 候选框最小宽/高
BLANK_THRESHOLD = 240         # 灰度值 > 此值视为空白
MAX_TEXTURE_SCORE = 50        # 纹理分上限
EDGE_STRIP_WIDTH = 5          # 边缘检测条带宽度
LOW_TEXTURE_THRESHOLD = 15    # 低纹理边缘判定阈值
EDGE_SCORE_BONUS = 20         # 有低纹理边缘时加分
AREA_RATIO_MIN = 0.3          # 多框面积比最小值
OVERLAP_PENALTY_FACTOR = 0.001  # 重叠惩罚系数
COVERAGE_THRESHOLD = 0.85     # 双框覆盖场景面积比阈值
MIN_MERGED_BOX_SIZE = 200     # 合并框最小尺寸


# ============================================================
# 场景分类
# ============================================================

def classify_scene(page_img: Image.Image) -> List[Tuple[int, int, int, int]]:
    """
    将页面划分为互不重叠的场景区域（照片所在的矩形区域）。

    优化：多尺度检测 + 形态学合并，适配不同排列密度。

    Args:
        page_img: PIL Image，完整页面图像

    Returns:
        List[(x1, y1, x2, y2)] — 场景区域的像素边界坐标列表
    """
    # 缩小图像加速处理
    small = page_img.resize(
        (page_img.width // DOWNscale_FACTOR, page_img.height // DOWNscale_FACTOR),
        Image.Resampling.NEAREST,
    )
    arr = np.array(small)
    gray = np.mean(arr, axis=2) if arr.ndim == 3 else arr

    # 多尺度边缘检测：在不同尺度下检测边缘，合并结果
    edge_map = np.zeros_like(gray, dtype=np.float32)

    # 尺度1：原始尺度（检测小照片）
    dx1 = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    dy1 = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
    edge_map += (dx1 + dy1) * 1.0

    # 尺度2：2x 下采样（检测中等照片）
    gray2 = gray[::2, ::2]
    dx2 = np.abs(np.diff(gray2, axis=1, append=gray2[:, -1:]))
    dy2 = np.abs(np.diff(gray2, axis=0, append=gray2[-1:, :]))
    # 上采样回原始尺寸
    from scipy.ndimage import zoom
    dx2_up = zoom(dx2, 2, order=1)
    dy2_up = zoom(dy2, 2, order=1)
    if dx2_up.shape != edge_map.shape:
        dx2_up = np.resize(dx2_up, edge_map.shape)
        dy2_up = np.resize(dy2_up, edge_map.shape)
    edge_map += (dx2_up + dy2_up) * 1.5

    # 阈值：取边缘强度前 15% 作为显著边缘
    threshold = np.percentile(edge_map, EDGE_PERCENTILE)
    edge_mask = edge_map > threshold

    # 形态学膨胀：合并照片内部的断裂边缘
    structure = np.ones((DILATION_KERNEL_SIZE, DILATION_KERNEL_SIZE), dtype=bool)
    edge_mask = ndimage.binary_dilation(edge_mask, structure=structure, iterations=DILATION_ITERATIONS)

    # 标记连通区域
    labeled, num_features = ndimage.label(edge_mask)

    # 构建场景区域：过滤小区域，合并邻近区域
    regions = []
    for i in range(1, num_features + 1):
        coords = np.argwhere(labeled == i)
        if len(coords) < MIN_REGION_COORDS:
            continue

        y1, x1 = coords.min(axis=0)
        y2, x2 = coords.max(axis=0)

        # 缩放回原始尺寸
        regions.append((x1 * DOWNscale_FACTOR, y1 * DOWNscale_FACTOR,
                         x2 * DOWNscale_FACTOR, y2 * DOWNscale_FACTOR))

    # 合并重叠/邻近区域
    merged = []
    for r in sorted(regions, key=lambda r: (r[1], r[0])):
        x1, y1, x2, y2 = r
        merged_flag = False
        for i, (mx1, my1, mx2, my2) in enumerate(merged):
            if not (x2 < mx1 - MERGE_DISTANCE_PX or x1 > mx2 + MERGE_DISTANCE_PX or
                    y2 < my1 - MERGE_DISTANCE_PX or y1 > my2 + MERGE_DISTANCE_PX):
                merged[i] = (min(x1, mx1), min(y1, my1),
                             max(x2, mx2), max(y2, my2))
                merged_flag = True
                break
        if not merged_flag:
            merged.append(r)

    return merged


# ============================================================
# 单场景内照片检测
# ============================================================

def detect_photos_in_scene(
    page_img: Image.Image,
    scene_box: Tuple[int, int, int, int]
) -> List[Tuple[int, int, int, int]]:
    """
    在单个场景区域内检测照片（支持 1~4 张不同排列方式）。

    策略：逐行/列扫描，找最佳分割 + 高斯模型后处理。

    Args:
        page_img: PIL Image，完整页面图像
        scene_box: (x1, y1, x2, y2) 场景区域像素坐标

    Returns:
        List[(x1, y1, x2, y2)] — 检测到的照片边界列表
    """
    x1, y1, x2, y2 = scene_box
    w, h = x2 - x1, y2 - y1

    if w < MIN_SCENE_SIZE or h < MIN_SCENE_SIZE:
        return []

    region = page_img.crop((x1, y1, x2, y2))
    arr = np.array(region)
    gray = np.mean(arr, axis=2) if arr.ndim == 3 else arr

    # 策略选择：先尝试按最亮分割点切分，再用高斯模型验证
    proj_h = np.mean(gray, axis=1)
    proj_w = np.mean(gray, axis=0)

    # 找水平和垂直分割点（亮度局部极小值，且两侧差异大）
    def find_splits(proj, min_size=MIN_SPLIT_SIZE):
        """找分割点：亮度局部极小值，且两侧都有足够的内容"""
        splits = []
        for i in range(min_size, len(proj) - min_size):
            # 局部极小值
            if proj[i] < proj[i - 1] and proj[i] < proj[i + 1]:
                # 两侧都有足够的内容
                left_std = np.std(proj[max(0, i - SPLIT_STD_WINDOW):i])
                right_std = np.std(proj[i:min(len(proj), i + SPLIT_STD_WINDOW)])
                if left_std > SPLIT_STD_THRESHOLD and right_std > SPLIT_STD_THRESHOLD:
                    # 两侧都有足够大小
                    if i > min_size and len(proj) - i > min_size:
                        splits.append(i)
        return splits

    h_splits = find_splits(proj_h)
    w_splits = find_splits(proj_w)

    candidates = []

    # 候选方案1：不分割（单张照片）
    candidates.append([scene_box])

    # 候选方案2：水平分割（上下排列）
    for split in h_splits:
        candidates.append([
            (x1, y1, x2, y1 + split),
            (x1, y1 + split, x2, y2)
        ])

    # 候选方案3：垂直分割（左右排列）
    for split in w_splits:
        candidates.append([
            (x1, y1, x1 + split, y2),
            (x1 + split, y1, x2, y2)
        ])

    # 候选方案4：2x2 网格
    if len(h_splits) >= 1 and len(w_splits) >= 1:
        candidates.append([
            (x1, y1, x1 + w_splits[0], y1 + h_splits[0]),
            (x1 + w_splits[0], y1, x2, y1 + h_splits[0]),
            (x1, y1 + h_splits[0], x1 + w_splits[0], y2),
            (x1 + w_splits[0], y1 + h_splits[0], x2, y2)
        ])

    # 候选方案5：三张照片（水平三等分或垂直三等分）
    if len(h_splits) >= 2:
        candidates.append([
            (x1, y1, x2, y1 + h_splits[0]),
            (x1, y1 + h_splits[0], x2, y1 + h_splits[1]),
            (x1, y1 + h_splits[1], x2, y2)
        ])
    if len(w_splits) >= 2:
        candidates.append([
            (x1, y1, x1 + w_splits[0], y2),
            (x1 + w_splits[0], y1, x1 + w_splits[1], y2),
            (x1 + w_splits[1], y1, x2, y2)
        ])

    # 高斯模型评分：选最符合"多个矩形照片"的方案
    best_score = -float('inf')
    best_boxes = []

    for boxes in candidates:
        score = 0
        valid_boxes = []
        for bx1, by1, bx2, by2 in boxes:
            bw, bh = bx2 - bx1, by2 - by1
            if bw < MIN_BOX_SIZE or bh < MIN_BOX_SIZE:
                score -= 1000
                continue

            box_img = page_img.crop((bx1, by1, bx2, by2))
            box_arr = np.array(box_img)
            box_gray = np.mean(box_arr, axis=2) if box_arr.ndim == 3 else box_arr

            # 照片评分：内容多、纹理丰富、不过度空白
            mean_val = np.mean(box_gray)
            std_val = np.std(box_gray)

            # 内容分：非空白区域比例
            content_ratio = np.sum(box_gray < BLANK_THRESHOLD) / box_gray.size

            # 纹理分
            texture_score = min(std_val, MAX_TEXTURE_SCORE)

            # 照片应该有明显的边框（边缘亮度突变）
            edge_score = 0
            if bh > EDGE_STRIP_WIDTH * 4 and bw > EDGE_STRIP_WIDTH * 4:
                top_edge = box_gray[:EDGE_STRIP_WIDTH, :]
                bottom_edge = box_gray[-EDGE_STRIP_WIDTH:, :]
                left_edge = box_gray[:, :EDGE_STRIP_WIDTH]
                right_edge = box_gray[:, -EDGE_STRIP_WIDTH:]
                edges = [top_edge, bottom_edge, left_edge, right_edge]
                edge_stds = [np.std(e) for e in edges]
                has_low_texture_edge = any(s < LOW_TEXTURE_THRESHOLD for s in edge_stds)
                if has_low_texture_edge:
                    edge_score = EDGE_SCORE_BONUS

            box_score = content_ratio * 100 + texture_score * 2 + edge_score
            score += box_score
            valid_boxes.append((bx1, by1, bx2, by2))

        # 额外加分：多个照片有合理的相对大小
        if len(valid_boxes) >= 2:
            areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in valid_boxes]
            if max(areas) > 0:
                area_ratios = [a / max(areas) for a in areas]
                # 照片大小应该相对均匀（避免一个极大一个极小）
                if all(r > AREA_RATIO_MIN for r in area_ratios):
                    score += 50  # 大小合理加分

        # 惩罚：过度重叠的框
        overlap_penalty = 0
        for i in range(len(valid_boxes)):
            for j in range(i + 1, len(valid_boxes)):
                b1 = valid_boxes[i]
                b2 = valid_boxes[j]
                # 计算重叠
                ix1 = max(b1[0], b2[0])
                iy1 = max(b1[1], b2[1])
                ix2 = min(b1[2], b2[2])
                iy2 = min(b1[3], b2[3])
                if ix2 > ix1 and iy2 > iy1:
                    overlap = (ix2 - ix1) * (iy2 - iy1)
                    overlap_penalty += overlap * OVERLAP_PENALTY_FACTOR
        score -= overlap_penalty

        if score > best_score and valid_boxes:
            best_score = score
            best_boxes = valid_boxes

    # 后处理：检查 coverage
    if len(best_boxes) == 2:
        # 2张照片：检查是否覆盖了场景的主要部分
        total_box_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in best_boxes)
        scene_area = w * h
        if total_box_area / scene_area > COVERAGE_THRESHOLD:
            return best_boxes
        # coverage 不够，可能中间有碎片，尝试合并
        merged_box = (
            min(b[0] for b in best_boxes),
            min(b[1] for b in best_boxes),
            max(b[2] for b in best_boxes),
            max(b[3] for b in best_boxes)
        )
        # 检查合并后的框是否合理
        mw, mh = merged_box[2] - merged_box[0], merged_box[3] - merged_box[1]
        if mw > MIN_MERGED_BOX_SIZE and mh > MIN_MERGED_BOX_SIZE:
            best_boxes = [merged_box]

    return best_boxes


# ============================================================
# 页面级照片提取
# ============================================================

def extract_photos_from_page(page_img: Image.Image) -> List[Tuple[int, int, int, int]]:
    """从单页提取所有照片的边界框，按位置排序

    Args:
        page_img: PIL Image，完整页面图像

    Returns:
        List[(x1, y1, x2, y2)] — 所有检测到的照片边界框
    """
    all_boxes = []

    scenes = classify_scene(page_img)
    for scene in scenes:
        boxes = detect_photos_in_scene(page_img, scene)
        for box in boxes:
            x1, y1, x2, y2 = [int(v) for v in box]
            all_boxes.append((x1, y1, x2, y2))

    # 按 y 坐标排序（从上到下），同 y 按 x 排序
    all_boxes.sort(key=lambda b: (b[1], b[0]))

    return all_boxes
