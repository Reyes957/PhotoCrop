"""
CVDetector — 传统 CV 算法检测器

封装现有 detector.py 的算法，实现 BaseDetector 接口。
原始算法不做任何修改（project_rules.md §3）。
"""

from __future__ import annotations

from typing import List

from PIL import Image

from photocrop.engine.detector_base import BaseDetector
from photocrop.engine.detector import extract_photos_from_page
from photocrop.utils.crop_rect import CropRect


class CVDetector(BaseDetector):
    """传统 CV 算法检测器

    使用边缘检测 + 形态学合并 + 连通分量 + 高斯评分，
    来自 extract_photos_v3_final.py 的原始算法。
    """

    @property
    def name(self) -> str:
        return "cv"

    def detect(self, page_img: Image.Image) -> List[CropRect]:
        """使用传统 CV 算法检测照片

        Args:
            page_img: PIL Image，完整页面图像

        Returns:
            List[CropRect] — 检测到的照片矩形
        """
        # 确保 RGB
        if page_img.mode not in ("RGB", "L", "RGBA"):
            page_img = page_img.convert("RGB")

        w, h = page_img.size

        # 调用原始算法
        raw_boxes = extract_photos_from_page(page_img)
        if not raw_boxes:
            return []

        # 转换为 CropRect
        rects = []
        for i, (x1, y1, x2, y2) in enumerate(raw_boxes):
            # 边界约束
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            rect = CropRect.from_pixel_rect(x1, y1, x2, y2, rotation_angle=0.0)
            rect.source_type = "detection"
            rect.index = i
            rects.append(rect)

        return rects
