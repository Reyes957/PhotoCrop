"""
引擎主入口 — 编排完整的检测流程

规范（project_rules.md §6）检测流程：
1. 原始检测 → detector（可替换：CVDetector / ModelDetector）
2. 估算旋转 → rotation.estimate_rotation_angle()
3. 过滤小框 → filters.filter_small_rects()
4. IoU 去重 → filters.iou_deduplicate()
5. 限制数量 + fallback → filters.limit_count() + _apply_fallback()

输出：List[CropRect]（中心坐标系统）
"""

from __future__ import annotations

from typing import List, Optional, Union

from PIL import Image

from photocrop.engine.detector_base import BaseDetector
from photocrop.engine.filters import (
    filter_small_rects,
    iou_deduplicate,
    limit_count,
    filter_extreme_aspect,
)
from photocrop.engine.rotation_estimator import estimate_rotation_angle
from photocrop.utils.crop_rect import CropRect


# ============================================================
# 默认参数
# ============================================================

DEFAULT_MIN_WIDTH = 100
DEFAULT_MIN_HEIGHT = 100
DEFAULT_MIN_AREA = 10000
DEFAULT_IOU_THRESHOLD = 0.7
DEFAULT_MAX_COUNT = 4


# ============================================================
# 检测器工厂（带模块级缓存）
# ============================================================

_detector_cache: dict[str, BaseDetector] = {}


def get_detector(detector: Union[str, BaseDetector, None] = None) -> BaseDetector:
    """获取检测器实例（字符串标识命中缓存，避免重复导入）

    Args:
        detector: 检测器标识
            - None 或 "cv": 传统 CV 算法（默认）
            - "yolo-world": YOLO-World 零样本检测器
            - "model": 模型检测器（占位）
            - BaseDetector 实例: 直接使用

    Returns:
        BaseDetector 实例
    """
    if isinstance(detector, BaseDetector):
        return detector

    key = detector or "cv"

    if key in _detector_cache:
        return _detector_cache[key]

    if key == "cv":
        from photocrop.engine.cv_detector import CVDetector
        instance = CVDetector()
    elif key == "enhanced-cv":
        from photocrop.engine.enhanced_cv_detector import EnhancedCVDetector
        instance = EnhancedCVDetector()
    elif key == "combined":
        from photocrop.engine.combined_detector import CombinedDetector
        instance = CombinedDetector()
    elif key == "yolo-world":
        from photocrop.engine.yolo_world_detector import YOLOWorldDetector
        instance = YOLOWorldDetector()
    elif key == "model":
        from photocrop.engine.model_detector import ModelDetector
        instance = ModelDetector()
    else:
        raise ValueError(f"未知的检测器: {detector}")

    _detector_cache[key] = instance
    return instance


# ============================================================
# 主检测函数
# ============================================================

def detect_rectangles(
    page_img: Image.Image,
    *,
    detector: Union[str, BaseDetector, None] = None,
    min_width: float = DEFAULT_MIN_WIDTH,
    min_height: float = DEFAULT_MIN_HEIGHT,
    min_area: float = DEFAULT_MIN_AREA,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    max_count: int = DEFAULT_MAX_COUNT,
    estimate_rotation_flag: bool = True,
    apply_fallback: bool = True,
) -> List[CropRect]:
    """检测页面中的所有照片矩形

    这是引擎的对外主入口，执行完整的 5 步检测流程。

    Args:
        page_img: PIL Image，完整页面图像（RGB 或灰度）
        detector: 检测器（"cv" / "model" / BaseDetector 实例 / None=默认cv）
        min_width: 最小宽度（像素），用于小框过滤
        min_height: 最小高度（像素）
        min_area: 最小面积（像素²）
        iou_threshold: IoU 去重阈值（0.0 ~ 1.0）
        max_count: 最大返回数量
        estimate_rotation_flag: 是否估算旋转角度
        apply_fallback: 无检测结果时是否返回整页作为 fallback

    Returns:
        List[CropRect] — 检测到的照片矩形列表（中心坐标）

    Example:
        >>> from PIL import Image
        >>> from photocrop.engine import detect_rectangles
        >>> img = Image.open("page.jpg")
        >>> rects = detect_rectangles(img)
        >>> rects = detect_rectangles(img, detector="model")  # 使用模型
    """
    if page_img.mode not in ("RGB", "L", "RGBA"):
        page_img = page_img.convert("RGB")

    # 获取检测器
    det = get_detector(detector)

    # ---- 步骤 1: 原始检测 ----
    rects = det.detect(page_img)

    if not rects:
        if apply_fallback:
            return _apply_page_fallback(page_img)
        return []

    # ---- 步骤 2: 估算旋转 ----
    if estimate_rotation_flag:
        for rect in rects:
            try:
                crop_img = page_img.crop(rect.to_pixel_tuple())
                angle = estimate_rotation_angle(crop_img)
                rect.rotation_angle = angle
            except (ValueError, RuntimeError, OSError):
                rect.rotation_angle = 0.0

    # ---- 步骤 3: 过滤小框 ----
    rects = filter_small_rects(rects,
                               min_width=min_width,
                               min_height=min_height,
                               min_area=min_area)

    if not rects:
        if apply_fallback:
            return _apply_page_fallback(page_img)
        return []

    # ---- 步骤 4: IoU 去重 ----
    rects = iou_deduplicate(rects, iou_threshold=iou_threshold)

    if not rects:
        if apply_fallback:
            return _apply_page_fallback(page_img)
        return []

    # ---- 步骤 5: 过滤过度拉伸 + 限制数量 ----
    rects = filter_extreme_aspect(rects)
    rects = limit_count(rects, max_count=max_count)

    if not rects:
        if apply_fallback:
            return _apply_page_fallback(page_img)
        return []

    # 重新编号
    for i, rect in enumerate(rects):
        rect.index = i

    return rects


# ============================================================
# Fallback
# ============================================================

def _apply_page_fallback(page_img: Image.Image) -> List[CropRect]:
    """Fallback：将整页作为一个 CropRect 返回"""
    w, h = page_img.size
    rect = CropRect.from_pixel_rect(0, 0, w, h, rotation_angle=0.0)
    rect.source_type = "fallback"
    rect.index = 0
    return [rect]


# ============================================================
# 从 PDF 检测
# ============================================================

def detect_from_pdf_page(
    page_img: Image.Image,
    page_num: int = 0,
    **kwargs
) -> List[CropRect]:
    """从 PDF 的某一页检测照片（便捷封装）"""
    rects = detect_rectangles(page_img, **kwargs)
    for r in rects:
        r.page_num = page_num
    return rects


# ============================================================
# 检测结果摘要
# ============================================================

def summarize(rects: List[CropRect]) -> str:
    """生成检测结果的可读摘要"""
    if not rects:
        return "未检测到任何照片矩形"

    lines = [f"检测到 {len(rects)} 个照片矩形:"]
    for i, r in enumerate(rects):
        fallback_mark = " [fallback]" if r.source_type == "fallback" else ""
        lines.append(
            f"  #{i+1}: 中心({r.x:.0f}, {r.y:.0f}) "
            f"尺寸{r.width:.0f}x{r.height:.0f} "
            f"旋转{r.rotation_angle:.1f}°{fallback_mark}"
        )
    return "\n".join(lines)
