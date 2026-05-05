"""
CombinedDetector — 组合检测器

同时运行 CVDetector 和 EnhancedCVDetector，
合并结果并用 IoU 去重，取两种方法的并集。

优势：
- CVDetector 擅长复杂布局（多照片、混合大小）
- EnhancedCVDetector 擅长精准矩形检测（减少误检）
- 合并后覆盖率最高
"""

from __future__ import annotations

from typing import List

from PIL import Image

from photocrop.engine.detector_base import BaseDetector
from photocrop.engine.cv_detector import CVDetector
from photocrop.engine.enhanced_cv_detector import EnhancedCVDetector
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou


class CombinedDetector(BaseDetector):
    """组合检测器 — CVDetector + EnhancedCVDetector 并集"""

    def __init__(self, iou_threshold: float = 0.5):
        self._cv = CVDetector()
        self._enhanced = EnhancedCVDetector()
        self._iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "combined"

    def detect(self, page_img: Image.Image) -> List[CropRect]:
        """运行两种检测器，合并去重"""
        rects_cv = self._cv.detect(page_img)
        rects_enh = self._enhanced.detect(page_img)

        # 合并，用 IoU 去重
        all_rects = list(rects_cv)
        for r in rects_enh:
            is_dup = False
            for existing in all_rects:
                if compute_iou(r, existing) > self._iou_threshold:
                    is_dup = True
                    break
            if not is_dup:
                all_rects.append(r)

        # 按面积排序
        all_rects.sort(key=lambda r: r.width * r.height, reverse=True)
        for i, r in enumerate(all_rects):
            r.index = i

        return all_rects

    def __repr__(self) -> str:
        return "<CombinedDetector>"
