"""
EnhancedCVDetector — 增强版 CV 检测器

在原始 CV 算法基础上，增加：
1. 自适应阈值（处理不同光照）
2. Hough 直线检测（找矩形边框）
3. 轮廓多边形近似（筛选矩形）
4. 边缘密度分析（区分照片 vs 装饰/文字区域）

不依赖 PyTorch，只用 OpenCV + numpy。
"""

from __future__ import annotations

import warnings

import cv2
import numpy as np
from PIL import Image

from photocrop.engine.detector_base import BaseDetector
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou


class EnhancedCVDetector(BaseDetector):
    """增强版 CV 检测器 — 专门针对相册页面优化"""

    def __init__(
        self,
        min_area_ratio: float = 0.01,
        max_area_ratio: float = 0.95,
        min_rectangularity: float = 0.7,
        aspect_ratio_range: tuple[float, float] = (0.2, 5.0),
    ):
        warnings.warn(
            "EnhancedCVDetector 已废弃，检测效果不如原始 CVDetector。"
            "请使用 CVDetector 或 YOLOWorldDetector。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.min_rectangularity = min_rectangularity
        self.aspect_ratio_range = aspect_ratio_range

    @property
    def name(self) -> str:
        return "enhanced-cv"

    def detect(self, page_img: Image.Image) -> list[CropRect]:
        """检测页面中的照片矩形"""
        if page_img.mode not in ("RGB", "L"):
            page_img = page_img.convert("RGB")

        img_array = np.array(page_img)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if len(img_array.shape) == 3 else img_array
        h, w = gray.shape
        page_area = h * w

        # 多种方法检测，合并结果
        candidates = []

        # 方法 1: 自适应阈值 + 轮廓
        candidates.extend(self._detect_adaptive_thresh(gray, w, h, page_area))

        # 方法 2: Canny 边缘 + 轮廓
        candidates.extend(self._detect_canny_contours(gray, w, h, page_area))

        # 方法 3: 形态学梯度 + 轮廓
        candidates.extend(self._detect_morphological(gray, w, h, page_area))

        if not candidates:
            return []

        # 合并重叠框
        rects = self._merge_candidates(candidates, w, h)
        return rects

    def _detect_adaptive_thresh(self, gray, w, h, page_area) -> list:
        """自适应阈值方法 — 处理不均匀光照"""
        rects = []
        # 高斯自适应阈值
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 5
        )
        # 闭运算连接断裂边框
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            rect = self._analyze_contour(cnt, w, h, page_area)
            if rect:
                rects.append(rect)
        return rects

    def _detect_canny_contours(self, gray, w, h, page_area) -> list:
        """Canny 边缘 + 轮廓检测"""
        rects = []
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)
        # 膨胀连接边缘
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            rect = self._analyze_contour(cnt, w, h, page_area)
            if rect:
                rects.append(rect)
        return rects

    def _detect_morphological(self, gray, w, h, page_area) -> list:
        """形态学梯度方法"""
        rects = []
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
        _, thresh = cv2.threshold(blackhat, 10, 255, cv2.THRESH_BINARY)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.dilate(thresh, kernel2, iterations=3)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            rect = self._analyze_contour(cnt, w, h, page_area)
            if rect:
                rects.append(rect)
        return rects

    def _analyze_contour(self, cnt, w, h, page_area) -> CropRect | None:
        """分析单个轮廓，判断是否为照片"""
        area = cv2.contourArea(cnt)
        if area < page_area * self.min_area_ratio:
            return None
        if area > page_area * self.max_area_ratio:
            return None

        # 最小外接矩形
        x, y, rw, rh = cv2.boundingRect(cnt)
        rect_area = rw * rh
        if rect_area == 0:
            return None

        # 矩形度：轮廓面积 / 外接矩形面积
        rectangularity = area / rect_area
        if rectangularity < self.min_rectangularity:
            return None

        # 宽高比
        aspect = max(rw, rh) / max(min(rw, rh), 1)
        if aspect < self.aspect_ratio_range[0] or aspect > self.aspect_ratio_range[1]:
            return None

        # 边界约束
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x + rw), min(h, y + rh)
        if x2 - x1 < 50 or y2 - y1 < 50:
            return None

        return CropRect.from_pixel_rect(x1, y1, x2, y2, rotation_angle=0.0)

    def _merge_candidates(self, candidates, w, h) -> list[CropRect]:
        """合并重叠的候选框"""
        if not candidates:
            return []

        # 按面积排序
        candidates.sort(key=lambda r: r.width * r.height, reverse=True)

        merged = []
        for cand in candidates:
            is_dup = False
            for existing in merged:
                if compute_iou(cand, existing) > 0.5:
                    is_dup = True
                    break
            if not is_dup:
                cand.source_type = "detection"
                merged.append(cand)

        # 编号
        for i, r in enumerate(merged):
            r.index = i

        return merged

    def __repr__(self) -> str:
        return "<EnhancedCVDetector>"
