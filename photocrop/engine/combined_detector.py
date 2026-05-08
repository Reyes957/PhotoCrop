"""
CombinedDetector — 组合检测器（IoU 投票融合）

同时运行 CVDetector 和 EnhancedCVDetector，
使用 IoU 投票策略合并结果（而非简单并集）。

投票规则：
1. 两个检测器都检测到的区域（IoU > 阈值）→ 高置信度，保留
2. 仅一个检测器检测到的区域 → 低置信度，按面积过滤后保留
3. 结果按置信度排序
"""

from __future__ import annotations

from PIL import Image

from photocrop.engine.cv_detector import CVDetector
from photocrop.engine.detector_base import BaseDetector
from photocrop.engine.enhanced_cv_detector import EnhancedCVDetector
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou


class CombinedDetector(BaseDetector):
    """组合检测器 — IoU 投票融合"""

    def __init__(self, iou_threshold: float = 0.3):
        self._cv = CVDetector()
        self._enhanced = EnhancedCVDetector()
        self._iou_threshold = iou_threshold

    @property
    def name(self) -> str:
        return "combined"

    def detect(self, page_img: Image.Image) -> list[CropRect]:
        """运行两种检测器，IoU 投票融合"""
        rects_cv = self._cv.detect(page_img)
        rects_enh = self._enhanced.detect(page_img)

        # 标记来源和初始置信度
        for r in rects_cv:
            r._vote_count = 1
            r._matched = False
        for r in rects_enh:
            r._vote_count = 1
            r._matched = False

        # 投票：找到两个检测器之间的匹配对
        for cv_rect in rects_cv:
            best_iou = 0.0
            best_enh = None
            for enh_rect in rects_enh:
                if enh_rect._matched:
                    continue
                iou = compute_iou(cv_rect, enh_rect)
                if iou > best_iou:
                    best_iou = iou
                    best_enh = enh_rect

            if best_iou > self._iou_threshold and best_enh is not None:
                # 匹配成功：两个检测器都检测到 → 高置信度
                cv_rect._vote_count = 2
                cv_rect._matched = True
                best_enh._matched = True
                # 取两者中面积更合理的那个
                if abs(cv_rect.aspect_ratio - 1.0) < abs(best_enh.aspect_ratio - 1.0):
                    cv_rect.confidence = 2.0
                else:
                    # 用 enhanced 的框，但标记为双投票
                    cv_rect._vote_count = 0  # 标记为不使用 cv 的框

        # 收集结果
        merged = []

        # 1. 双投票的框（两个检测器都检测到）
        for r in rects_cv:
            if r._vote_count >= 2:
                r.confidence = 2.0
                r.source_type = "detection"
                merged.append(r)

        # 2. 仅 CV 检测到且未匹配的
        for r in rects_cv:
            if r._vote_count == 1 and not r._matched:
                r.confidence = 1.0
                r.source_type = "detection"
                merged.append(r)

        # 3. 仅 Enhanced 检测到且未匹配的
        for r in rects_enh:
            if not r._matched:
                r.confidence = 0.5
                r.source_type = "detection"
                merged.append(r)

        # 按置信度降序排序，同置信度按面积降序
        merged.sort(key=lambda r: (r.confidence, r.width * r.height), reverse=True)
        for i, r in enumerate(merged):
            r.index = i

        # 清理临时属性
        for r in merged:
            if hasattr(r, '_vote_count'):
                del r._vote_count
            if hasattr(r, '_matched'):
                del r._matched

        return merged

    def __repr__(self) -> str:
        return "<CombinedDetector (IoU voting)>"
