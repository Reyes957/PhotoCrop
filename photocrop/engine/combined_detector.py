"""
CombinedDetector — 组合检测器（IoU 投票融合）

同时运行 CVDetector 和 EnhancedCVDetector，
使用 IoU 投票策略合并结果（而非简单并集）。

投票规则：
1. 两个检测器都检测到的区域（IoU > 阈值）→ 高置信度，保留
2. 仅一个检测器检测到的区域 → 低置信度，按面积过滤后保留
3. 结果按置信度排序

.. deprecated::
    CombinedDetector 依赖已废弃的 EnhancedCVDetector，建议使用 CVDetector（默认）
    或 YOLO-World 代替。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from PIL import Image

from photocrop.engine.cv_detector import CVDetector
from photocrop.engine.detector_base import BaseDetector
from photocrop.engine.enhanced_cv_detector import EnhancedCVDetector
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou


@dataclass
class _VoteEntry:
    """投票记录 — 替代在 CropRect 上动态添加 _vote_count / _matched"""
    rect: CropRect
    vote_count: int = 1
    matched: bool = False


class CombinedDetector(BaseDetector):
    """组合检测器 — IoU 投票融合"""

    def __init__(self, iou_threshold: float = 0.3):
        # BUG-011 fix: 同步标记为废弃
        warnings.warn(
            "CombinedDetector 已废弃，建议使用 EnhancedCVDetector（默认）或 YOLO-World 代替",
            DeprecationWarning,
            stacklevel=2,
        )
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

        # 用独立的 _VoteEntry 跟踪投票状态（不污染 CropRect）
        cv_entries = [_VoteEntry(rect=r) for r in rects_cv]
        enh_entries = [_VoteEntry(rect=r) for r in rects_enh]

        # 投票：找到两个检测器之间的匹配对
        for cv_entry in cv_entries:
            best_iou = 0.0
            best_enh: _VoteEntry | None = None
            for enh_entry in enh_entries:
                if enh_entry.matched:
                    continue
                iou = compute_iou(cv_entry.rect, enh_entry.rect)
                if iou > best_iou:
                    best_iou = iou
                    best_enh = enh_entry

            if best_iou > self._iou_threshold and best_enh is not None:
                # 匹配成功：两个检测器都检测到 → 高置信度
                cv_entry.vote_count = 2
                cv_entry.matched = True
                best_enh.matched = True
                # 取两者中面积更合理的那个
                if abs(cv_entry.rect.aspect_ratio - 1.0) < abs(best_enh.rect.aspect_ratio - 1.0):
                    cv_entry.rect.confidence = 2.0
                else:
                    # 用 enhanced 的框，但标记为不使用 cv 的框
                    cv_entry.vote_count = 0

        # 收集结果
        merged: list[CropRect] = []

        # 1. 双投票的框（两个检测器都检测到）
        for entry in cv_entries:
            if entry.vote_count >= 2:
                entry.rect.confidence = 2.0
                entry.rect.source_type = "detection"
                merged.append(entry.rect)

        # 2. 仅 CV 检测到且未匹配的
        for entry in cv_entries:
            if entry.vote_count == 1 and not entry.matched:
                entry.rect.confidence = 1.0
                entry.rect.source_type = "detection"
                merged.append(entry.rect)

        # 3. 仅 Enhanced 检测到且未匹配的
        for entry in enh_entries:
            if not entry.matched:
                entry.rect.confidence = 0.5
                entry.rect.source_type = "detection"
                merged.append(entry.rect)

        # 按置信度降序排序，同置信度按面积降序
        merged.sort(key=lambda r: (r.confidence, r.width * r.height), reverse=True)
        for i, r in enumerate(merged):
            r.index = i

        return merged

    def __repr__(self) -> str:
        return "<CombinedDetector (IoU voting)>"
