#!/usr/bin/env python3
"""
引擎测试脚本

测试覆盖：
- CropRect 坐标转换
- 场景分类 + 照片检测
- 小框过滤
- IoU 去重
- 旋转估计
- Fallback 机制

运行方式：从项目根目录执行 python tests/test_engine.py
"""

import sys

from PIL import Image
import numpy as np

from photocrop.engine.core import detect_rectangles, detect_from_pdf_page, summarize
from photocrop.engine.filters import (
    iou_deduplicate,
    filter_small_rects,
    filter_extreme_aspect,
    limit_count,
)
from photocrop.utils.iou import compute_iou
from photocrop.engine.rotation_estimator import estimate_rotation_angle
from photocrop.engine.cv_algorithm import (
    classify_scene,
    detect_photos_in_scene,
    extract_photos_from_page,
)
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.rotation import to_opencv_angle, normalize_angle, angle_within_tolerance

# ============================================================
# 测试工具
# ============================================================

PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  — {detail}")


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


# ============================================================
# 测试 CropRect 坐标系统
# ============================================================

def test_crop_rect():
    section("CropRect 坐标系统")

    # 从像素坐标构造
    rect = CropRect.from_pixel_rect(100, 200, 300, 400, rotation_angle=15.0)
    test("中心 x = 200", abs(rect.x - 200) < 0.01)
    test("中心 y = 300", abs(rect.y - 300) < 0.01)
    test("width = 200", abs(rect.width - 200) < 0.01)
    test("height = 200", abs(rect.height - 200) < 0.01)
    test("rotation_angle = 15.0", abs(rect.rotation_angle - 15.0) < 0.01)

    # 像素坐标转换
    test("x1 = 100", abs(rect.x1 - 100) < 0.01)
    test("y1 = 200", abs(rect.y1 - 200) < 0.01)
    test("x2 = 300", abs(rect.x2 - 300) < 0.01)
    test("y2 = 400", abs(rect.y2 - 400) < 0.01)

    # 往返转换
    test("to_pixel_tuple", rect.to_pixel_tuple() == (100, 200, 300, 400))

    # 面积
    test("area = 40000", abs(rect.area - 40000) < 1)

    # aspect ratio
    test("aspect_ratio = 1.0", abs(rect.aspect_ratio - 1.0) < 0.01)

    # 默认值
    default_rect = CropRect(x=0, y=0, width=100, height=100)
    test("默认 rotation_angle = 0", default_rect.rotation_angle == 0)
    test("默认 source_type = detection", default_rect.source_type == "detection")


# ============================================================
# 测试旋转工具
# ============================================================

def test_rotation_utils():
    section("旋转角度工具")

    test("to_opencv_angle(90) = -90", to_opencv_angle(90) == -90)
    test("to_opencv_angle(-45) = 45", to_opencv_angle(-45) == 45)
    test("to_opencv_angle(0) = 0", to_opencv_angle(0) == 0)

    test("normalize_angle(370) → 10", abs(normalize_angle(370) - 10) < 0.01)
    test("normalize_angle(-190) → 170", abs(normalize_angle(-190) - 170) < 0.01)
    test("normalize_angle(180) → 180 or -180", abs(abs(normalize_angle(180)) - 180) < 0.01)

    test("angle_within_tolerance(95, 90, 10) → True", angle_within_tolerance(95, 90, 10))
    test("angle_within_tolerance(79, 90, 10) → False", not angle_within_tolerance(79, 90, 10))


# ============================================================
# 测试 IoU 计算和过滤
# ============================================================

def test_filters():
    section("IoU 和过滤")

    # 完全重叠
    a = CropRect.from_pixel_rect(0, 0, 100, 100)
    b = CropRect.from_pixel_rect(0, 0, 100, 100)
    test("完全相同 → IoU=1.0", abs(compute_iou(a, b) - 1.0) < 0.01)

    # 无交集
    c = CropRect.from_pixel_rect(200, 200, 300, 300)
    test("无交集 → IoU=0.0", compute_iou(a, c) == 0.0)

    # 部分重叠 (50% 重叠)
    d = CropRect.from_pixel_rect(50, 0, 150, 100)
    iou_val = compute_iou(a, d)
    test("50%重叠 → IoU≈0.33", abs(iou_val - 0.333) < 0.1)

    # IoU 去重
    rects = [
        CropRect.from_pixel_rect(0, 0, 100, 100),       # 置信度低（面积小）
        CropRect.from_pixel_rect(2, 2, 98, 98),          # 与上面高度重叠
        CropRect.from_pixel_rect(200, 200, 300, 300),    # 独立
        CropRect.from_pixel_rect(205, 205, 295, 295),    # 与上面重叠
    ]
    # 设置置信度以便去重
    for i, r in enumerate(rects):
        r.confidence = 1.0 - i * 0.1

    deduped = iou_deduplicate(rects, iou_threshold=0.5)
    test("4个框去重后应剩2个", len(deduped) == 2,
         f"实际 {len(deduped)} 个")

    # 小框过滤
    small = CropRect.from_pixel_rect(0, 0, 50, 50)
    big = CropRect.from_pixel_rect(0, 0, 200, 200)
    filtered = filter_small_rects([small, big], min_width=100, min_height=100)
    test("过滤小框后剩1个", len(filtered) == 1)

    # 过度拉伸过滤
    normal = CropRect(x=0, y=0, width=200, height=300)
    stretched = CropRect(x=0, y=0, width=500, height=50)
    kept = filter_extreme_aspect([normal, stretched])
    test("过度拉伸被过滤", len(kept) == 1)

    # 数量限制
    many = [CropRect.from_pixel_rect(i*10, i*10, i*10+100, i*10+100) for i in range(10)]
    for i, r in enumerate(many):
        r.confidence = float(i)
    limited = limit_count(many, max_count=4)
    test("限制4个框", len(limited) == 4)


# ============================================================
# 测试旋转估计
# ============================================================

def test_rotation_estimation():
    section("旋转估计")

    # 纯白图像（无边框特征）→ 应返回 0
    white_img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    angle = estimate_rotation_angle(white_img)
    test("纯白图像 → 旋转 0°", angle == 0.0, f"实际 {angle}")

    # 合成一张带白边的横版图像（模拟旋转 90°的竖版照片）
    # 左边白边，右边内容 → 应该检测到旋转
    arr = np.full((400, 600, 3), (200, 180, 160), dtype=np.uint8)  # 米色背景
    arr[:, -30:, :] = (250, 250, 245)  # 右边白边
    arr[:, :30, :] = (180, 160, 140)    # 左边内容
    # 顶部白边
    arr[:20, :, :] = (240, 240, 235)
    arr[-20:, :, :] = (240, 240, 235)
    synthetic = Image.fromarray(arr)
    angle = estimate_rotation_angle(synthetic)
    print(f"  合成图像旋转估计: {angle}°")
    test("合成图像旋转估计正常完成", angle in (-90.0, 0.0, 90.0),
         f"实际 {angle}")


# ============================================================
# 测试引擎完整流程
# ============================================================

def test_engine_pipeline():
    section("引擎完整流程")

    # 创建合成测试图像（白底上放几个暗色矩形模拟照片）
    img = Image.new("RGB", (1200, 800), color=(248, 248, 245))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    # 模拟两张照片的位置
    draw.rectangle([50, 50, 550, 750], fill=(180, 170, 160))
    draw.rectangle([600, 50, 1150, 380], fill=(170, 160, 150))
    draw.rectangle([600, 400, 1150, 750], fill=(190, 180, 170))

    rects = detect_rectangles(img)

    print(f"  检测到 {len(rects)} 个矩形:")
    for r in rects:
        print(f"    {r}")

    test("合成图像检测到至少1个矩形", len(rects) >= 1,
         f"实际 {len(rects)} 个")
    test("所有矩形坐标在图像范围内", all(
        0 <= r.x1 and r.y1 >= 0 and r.x2 <= img.width and r.y2 <= img.height
        for r in rects
    ))
    test("所有矩形有有效尺寸", all(r.width > 0 and r.height > 0 for r in rects))

    # 测试 fallback（空白图像）
    blank = Image.new("RGB", (800, 600), color=(255, 255, 255))
    fallback_rects = detect_rectangles(blank)
    test("空白图像触发 fallback", len(fallback_rects) >= 1)
    if fallback_rects:
        test("Fallback 标记为 fallback 类型",
             fallback_rects[0].source_type == "fallback")


# ============================================================
# 测试场景分类（纯算法测试）
# ============================================================

def test_scene_classification():
    section("场景分类")

    # 合成多场景图像
    img = Image.new("RGB", (1200, 800), color=(248, 248, 245))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    draw.rectangle([40, 40, 560, 760], fill=(180, 170, 160))
    draw.rectangle([600, 40, 1160, 760], fill=(170, 165, 155))

    scenes = classify_scene(img)
    print(f"  分类到 {len(scenes)} 个场景")
    for s in scenes:
        print(f"    场景: {s}")

    test("多场景图像至少1个场景", len(scenes) >= 1)

    # 空场景内检测
    if scenes:
        boxes = detect_photos_in_scene(img, scenes[0])
        print(f"    场景内检测到 {len(boxes)} 个照片")
        test("场景内检测正常返回", isinstance(boxes, list))


# ============================================================
# 测试摘要输出
# ============================================================

def test_summarize():
    section("摘要输出")

    rects = [
        CropRect(x=200, y=300, width=400, height=300, rotation_angle=0.0),
        CropRect(x=600, y=200, width=350, height=250, rotation_angle=-90.0),
    ]
    rects[0].source_type = "detection"
    rects[1].source_type = "fallback"

    summary = summarize(rects)
    print(f"  摘要:\n{summary}")
    test("摘要包含'检测到'", "检测到" in summary)
    test("摘要包含'fallback'", "fallback" in summary)

    empty_summary = summarize([])
    test("空列表摘要", "未检测到" in empty_summary)


# ============================================================
# 主测试入口
# ============================================================

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("\n" + "="*60)
    print("  PhotoCrop — 引擎测试")
    print("="*60)

    test_crop_rect()
    test_rotation_utils()
    test_filters()
    test_rotation_estimation()
    test_engine_pipeline()
    test_scene_classification()
    test_summarize()

    print(f"\n{'='*60}")
    print(f"  结果: {PASS} 通过 / {FAIL} 失败")
    print(f"{'='*60}")

    return FAIL == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
