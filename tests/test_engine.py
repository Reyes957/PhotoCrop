"""
引擎测试 — pytest 版本

覆盖：
- CropRect 坐标转换
- 旋转工具
- IoU 计算和过滤
- 旋转估计
- 引擎完整流程
- 场景分类
- 摘要输出

运行：pytest tests/ -v
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

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
# Fixtures
# ============================================================

@pytest.fixture
def synthetic_page():
    """合成测试图像：白底上放三个暗色矩形模拟照片"""
    img = Image.new("RGB", (1200, 800), color=(248, 248, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 550, 750], fill=(180, 170, 160))
    draw.rectangle([600, 50, 1150, 380], fill=(170, 160, 150))
    draw.rectangle([600, 400, 1150, 750], fill=(190, 180, 170))
    return img


@pytest.fixture
def synthetic_with_frame():
    """合成带白边的横版图像（模拟旋转 90° 的竖版照片）"""
    arr = np.full((400, 600, 3), (200, 180, 160), dtype=np.uint8)
    arr[:, -30:, :] = (250, 250, 245)  # 右边白边
    arr[:, :30, :] = (180, 160, 140)    # 左边内容
    arr[:20, :, :] = (240, 240, 235)    # 顶部白边
    arr[-20:, :, :] = (240, 240, 235)   # 底部白边
    return Image.fromarray(arr)


# ============================================================
# CropRect 坐标系统
# ============================================================

class TestCropRect:
    def test_from_pixel_rect_center(self):
        rect = CropRect.from_pixel_rect(100, 200, 300, 400, rotation_angle=15.0)
        assert abs(rect.x - 200) < 0.01
        assert abs(rect.y - 300) < 0.01
        assert abs(rect.width - 200) < 0.01
        assert abs(rect.height - 200) < 0.01
        assert abs(rect.rotation_angle - 15.0) < 0.01

    def test_pixel_corners(self):
        rect = CropRect.from_pixel_rect(100, 200, 300, 400)
        assert abs(rect.x1 - 100) < 0.01
        assert abs(rect.y1 - 200) < 0.01
        assert abs(rect.x2 - 300) < 0.01
        assert abs(rect.y2 - 400) < 0.01

    def test_to_pixel_tuple(self):
        rect = CropRect.from_pixel_rect(100, 200, 300, 400)
        assert rect.to_pixel_tuple() == (100, 200, 300, 400)

    def test_area(self):
        rect = CropRect.from_pixel_rect(0, 0, 200, 200)
        assert abs(rect.area - 40000) < 1

    def test_aspect_ratio(self):
        rect = CropRect.from_pixel_rect(0, 0, 200, 200)
        assert abs(rect.aspect_ratio - 1.0) < 0.01

    def test_defaults(self):
        rect = CropRect(x=0, y=0, width=100, height=100)
        assert rect.rotation_angle == 0
        assert rect.source_type == "detection"


# ============================================================
# 旋转工具
# ============================================================

class TestRotationUtils:
    def test_to_opencv_angle(self):
        assert to_opencv_angle(90) == -90
        assert to_opencv_angle(-45) == 45
        assert to_opencv_angle(0) == 0

    def test_normalize_angle(self):
        assert abs(normalize_angle(370) - 10) < 0.01
        assert abs(normalize_angle(-190) - 170) < 0.01
        assert abs(abs(normalize_angle(180)) - 180) < 0.01

    def test_angle_within_tolerance(self):
        assert angle_within_tolerance(95, 90, 10)
        assert not angle_within_tolerance(79, 90, 10)


# ============================================================
# IoU 计算和过滤
# ============================================================

class TestFilters:
    def test_iou_identical(self):
        a = CropRect.from_pixel_rect(0, 0, 100, 100)
        b = CropRect.from_pixel_rect(0, 0, 100, 100)
        assert abs(compute_iou(a, b) - 1.0) < 0.01

    def test_iou_no_overlap(self):
        a = CropRect.from_pixel_rect(0, 0, 100, 100)
        c = CropRect.from_pixel_rect(200, 200, 300, 300)
        assert compute_iou(a, c) == 0.0

    def test_iou_partial(self):
        a = CropRect.from_pixel_rect(0, 0, 100, 100)
        d = CropRect.from_pixel_rect(50, 0, 150, 100)
        iou_val = compute_iou(a, d)
        assert abs(iou_val - 0.333) < 0.1

    def test_iou_dedup(self):
        rects = [
            CropRect.from_pixel_rect(0, 0, 100, 100),
            CropRect.from_pixel_rect(2, 2, 98, 98),
            CropRect.from_pixel_rect(200, 200, 300, 300),
            CropRect.from_pixel_rect(205, 205, 295, 295),
        ]
        for i, r in enumerate(rects):
            r.confidence = 1.0 - i * 0.1
        deduped = iou_deduplicate(rects, iou_threshold=0.5)
        assert len(deduped) == 2

    def test_filter_small_rects(self):
        small = CropRect.from_pixel_rect(0, 0, 50, 50)
        big = CropRect.from_pixel_rect(0, 0, 200, 200)
        filtered = filter_small_rects([small, big], min_width=100, min_height=100)
        assert len(filtered) == 1

    def test_filter_extreme_aspect(self):
        normal = CropRect(x=0, y=0, width=200, height=300)
        stretched = CropRect(x=0, y=0, width=500, height=50)
        kept = filter_extreme_aspect([normal, stretched])
        assert len(kept) == 1

    def test_limit_count(self):
        many = [CropRect.from_pixel_rect(i*10, i*10, i*10+100, i*10+100) for i in range(10)]
        for i, r in enumerate(many):
            r.confidence = float(i)
        limited = limit_count(many, max_count=4)
        assert len(limited) == 4


# ============================================================
# 旋转估计
# ============================================================

class TestRotationEstimation:
    def test_white_image(self):
        white_img = Image.new("RGB", (400, 300), color=(255, 255, 255))
        angle = estimate_rotation_angle(white_img)
        assert angle == 0.0

    def test_synthetic_image(self, synthetic_with_frame):
        angle = estimate_rotation_angle(synthetic_with_frame)
        assert angle in (-90.0, 0.0, 90.0)


# ============================================================
# 引擎完整流程
# ============================================================

class TestEnginePipeline:
    def test_synthetic_detection(self, synthetic_page):
        rects = detect_rectangles(synthetic_page)
        assert len(rects) >= 1
        assert all(
            0 <= r.x1 and r.y1 >= 0 and r.x2 <= synthetic_page.width and r.y2 <= synthetic_page.height
            for r in rects
        )
        assert all(r.width > 0 and r.height > 0 for r in rects)

    def test_blank_fallback(self):
        blank = Image.new("RGB", (800, 600), color=(255, 255, 255))
        fallback_rects = detect_rectangles(blank)
        assert len(fallback_rects) >= 1
        assert fallback_rects[0].source_type == "fallback"


# ============================================================
# 场景分类
# ============================================================

class TestSceneClassification:
    def test_multi_scene(self, synthetic_page):
        scenes = classify_scene(synthetic_page)
        assert len(scenes) >= 1

    def test_detect_in_scene(self, synthetic_page):
        scenes = classify_scene(synthetic_page)
        if scenes:
            boxes = detect_photos_in_scene(synthetic_page, scenes[0])
            assert isinstance(boxes, list)


# ============================================================
# 摘要输出
# ============================================================

class TestSummarize:
    def test_summary_content(self):
        rects = [
            CropRect(x=200, y=300, width=400, height=300, rotation_angle=0.0),
            CropRect(x=600, y=200, width=350, height=250, rotation_angle=-90.0),
        ]
        rects[0].source_type = "detection"
        rects[1].source_type = "fallback"
        summary = summarize(rects)
        assert "检测到" in summary
        assert "fallback" in summary

    def test_summary_empty(self):
        empty_summary = summarize([])
        assert "未检测到" in empty_summary
