"""
旋转估计模块 — 从检测到的照片区域估算旋转角度

两阶段检测：
1. 小角度倾斜检测（±15°）— 基于 Hough 直线检测
2. 横竖方向检测（±90°）— 基于边缘条带亮度分析

规范（project_rules.md §5）：
- 顺时针为正
- 容差 ±10°
"""

from typing import Optional

import numpy as np
from PIL import Image

from photocrop.utils.rotation import normalize_angle, angle_within_tolerance


# ============================================================
# 主入口
# ============================================================

def estimate_rotation_angle(
    crop_img: Image.Image,
    high_confidence_only: bool = True
) -> float:
    """估算照片的正确旋转角度

    两阶段检测：
    1. 先检测小角度倾斜（±15°），基于线条方向
    2. 再检测 ±90° 横竖方向错误，基于边缘条带特征

    Args:
        crop_img: PIL Image，裁剪出的照片区域
        high_confidence_only: 是否仅在高置信度时返回非零角度

    Returns:
        顺时针旋转角度（度），通常为 0, ±90, 或小角度修正
    """
    arr = np.array(crop_img)
    gray = np.mean(arr, axis=2) if arr.ndim == 3 else arr.astype(np.float64)
    h, w = gray.shape

    # 阶段 1：小角度倾斜检测
    small_angle = _detect_small_angle(gray, w, h)
    if small_angle is not None and abs(small_angle) > 0.5:
        return small_angle

    # 阶段 2：±90° 横竖方向检测
    return _detect_90_rotation(gray, w, h)


# ============================================================
# 小角度倾斜检测
# ============================================================

def _detect_small_angle(gray: np.ndarray, w: int, h: int) -> Optional[float]:
    """检测小角度倾斜（±15°）

    使用边缘检测 + 直线分析，找到照片边缘的倾斜角度。

    Args:
        gray: 灰度图像数组
        w: 图像宽度
        h: 图像高度

    Returns:
        倾斜角度（顺时针），如果未检测到返回 None
    """
    # 用简单的梯度检测边缘
    dx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    dy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))

    # 只关注边缘区域（图像四周 15%）
    edge_w = max(int(w * 0.15), 30)
    edge_h = max(int(h * 0.15), 30)

    # 收集边缘区域的梯度方向
    angles = []

    # 上边缘
    top_region = dy[:edge_h, :]
    top_mask = top_region > np.percentile(top_region, 85)
    if np.sum(top_mask) > 10:
        # 找到强边缘的水平位置变化
        angles.extend(_extract_edge_angles(top_mask, 'horizontal'))

    # 下边缘
    bottom_region = dy[-edge_h:, :]
    bottom_mask = bottom_region > np.percentile(bottom_region, 85)
    if np.sum(bottom_mask) > 10:
        angles.extend(_extract_edge_angles(bottom_mask, 'horizontal'))

    # 左边缘
    left_region = dx[:, :edge_w]
    left_mask = left_region > np.percentile(left_region, 85)
    if np.sum(left_mask) > 10:
        angles.extend(_extract_edge_angles(left_mask, 'vertical'))

    # 右边缘
    right_region = dx[:, -edge_w:]
    right_mask = right_region > np.percentile(right_region, 85)
    if np.sum(right_mask) > 10:
        angles.extend(_extract_edge_angles(right_mask, 'vertical'))

    if not angles:
        return None

    # 取中位数角度，过滤异常值
    angles = np.array(angles)
    median_angle = float(np.median(angles))

    # 只返回小角度（±15°）
    if abs(median_angle) <= 15.0 and abs(median_angle) > 0.5:
        return -median_angle  # 负号：倾斜方向与旋转方向相反

    return None


def _extract_edge_angles(mask: np.ndarray, direction: str) -> list:
    """从边缘掩码中提取倾斜角度

    通过找到边缘点的质心位置变化来估算倾斜。

    Args:
        mask: 边缘掩码（bool 数组）
        direction: 'horizontal' 或 'vertical'

    Returns:
        角度列表
    """
    angles = []

    if direction == 'horizontal':
        # 水平边缘：看每列的边缘位置变化
        for col_start in range(0, mask.shape[1], max(mask.shape[1] // 4, 1)):
            col_end = min(col_start + mask.shape[1] // 4, mask.shape[1])
            segment = mask[:, col_start:col_end]
            if segment.size == 0:
                continue
            # 找每列的边缘位置
            positions = []
            for c in range(segment.shape[1]):
                col_data = segment[:, c]
                if np.any(col_data):
                    positions.append(np.argmax(col_data))
            if len(positions) >= 2:
                # 用线性回归估算角度
                x = np.arange(len(positions))
                slope = np.polyfit(x, positions, 1)[0]
                angle = np.degrees(np.arctan(slope))
                if abs(angle) < 15:
                    angles.append(angle)

    elif direction == 'vertical':
        # 垂直边缘：看每行的边缘位置变化
        for row_start in range(0, mask.shape[0], max(mask.shape[0] // 4, 1)):
            row_end = min(row_start + mask.shape[0] // 4, mask.shape[0])
            segment = mask[row_start:row_end, :]
            if segment.size == 0:
                continue
            # 找每行的边缘位置
            positions = []
            for r in range(segment.shape[0]):
                row_data = segment[r, :]
                if np.any(row_data):
                    positions.append(np.argmax(row_data))
            if len(positions) >= 2:
                x = np.arange(len(positions))
                slope = np.polyfit(x, positions, 1)[0]
                angle = np.degrees(np.arctan(slope))
                if abs(angle) < 15:
                    angles.append(angle)

    return angles


# ============================================================
# ±90° 横竖方向检测
# ============================================================

def _detect_90_rotation(gray: np.ndarray, w: int, h: int) -> float:
    """检测 ±90° 的横竖方向错误

    使用四边 10% 边缘条带分析亮度/纹理特征，
    判断照片是否存在 ±90° 的横竖方向错误。

    Args:
        gray: 灰度图像数组
        w: 图像宽度
        h: 图像高度

    Returns:
        旋转角度（0.0 或 -90.0）
    """
    aspect = w / h

    # 分析四边边缘（10% 宽度条带）
    edge_w = max(w // 10, 20)
    edge_h = max(h // 10, 20)

    left_edge = gray[:, :edge_w]
    right_edge = gray[:, -edge_w:]
    top_edge = gray[:edge_h, :]
    bottom_edge = gray[-edge_h:, :]

    lm = float(np.mean(left_edge))
    ls = float(np.std(left_edge))
    rm = float(np.mean(right_edge))
    rs = float(np.std(right_edge))
    tm = float(np.mean(top_edge))
    ts = float(np.std(top_edge))
    bm = float(np.mean(bottom_edge))
    bs = float(np.std(bottom_edge))

    if aspect > 1.0:
        # 横版图像：检查是否需要旋转 90°

        # A 级：强单侧特征
        right_is_frame = rm > 218 and rs < 25
        left_is_frame = lm > 218 and ls < 25
        left_is_content = lm < 190 or ls > 55
        right_is_content = rm < 190 or rs > 55

        if right_is_frame and left_is_content:
            return -90.0
        if left_is_frame and right_is_content:
            return -90.0

        # B 级：三边相框纸
        top_is_frame = tm > 210 and ts < 35
        bottom_is_frame = bm > 210 and bs < 35

        if rm > 210 and rs < 30 and top_is_frame and bottom_is_frame \
                and (ls > 28 or lm < 210):
            return -90.0
        if lm > 210 and ls < 30 and top_is_frame and bottom_is_frame \
                and (rs > 28 or rm < 210):
            return -90.0

    elif aspect < 1.0:
        # 纵向照片：检查头朝左/右的情况
        left_is_frame = lm > 218 and ls < 25
        right_is_frame = rm > 218 and rs < 25
        if left_is_frame or right_is_frame:
            return -90.0

    return 0.0


# ============================================================
# 从图像数组估算
# ============================================================

def estimate_from_array(arr: np.ndarray) -> float:
    """从 numpy 数组估算旋转角度

    Args:
        arr: numpy 数组 (H, W) 或 (H, W, C)

    Returns:
        顺时针旋转角度
    """
    if arr.ndim == 2:
        img = Image.fromarray(arr.astype(np.uint8))
    else:
        img = Image.fromarray(arr)
    return estimate_rotation_angle(img)


# ============================================================
# 批量估算
# ============================================================

def estimate_batch(
    crop_images: list,
    default_angle: float = 0.0
) -> list:
    """对多个裁剪图像批量估算旋转角度

    Args:
        crop_images: PIL Image 或 numpy 数组列表
        default_angle: 无法估算时使用的默认角度

    Returns:
        角度列表（与输入一一对应）
    """
    angles = []
    for img in crop_images:
        try:
            if isinstance(img, np.ndarray):
                angle = estimate_from_array(img)
            else:
                angle = estimate_rotation_angle(img)
            angles.append(angle)
        except Exception:
            angles.append(default_angle)
    return angles
