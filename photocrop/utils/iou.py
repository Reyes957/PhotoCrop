"""
IoU 计算 — 统一实现

所有检测器和过滤器共用此模块，避免重复代码。
"""

from __future__ import annotations

from photocrop.utils.crop_rect import CropRect


def compute_iou(rect_a: CropRect, rect_b: CropRect) -> float:
    """计算两个 CropRect 的 IoU（交并比）

    Args:
        rect_a: CropRect A
        rect_b: CropRect B

    Returns:
        IoU 值 (0.0 ~ 1.0)，两者无交集时返回 0.0
    """
    ax1, ay1, ax2, ay2 = rect_a.x1, rect_a.y1, rect_a.x2, rect_a.y2
    bx1, by1, bx2, by2 = rect_b.x1, rect_b.y1, rect_b.x2, rect_b.y2

    # 交集
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter_area = (ix2 - ix1) * (iy2 - iy1)

    # 并集
    area_a = rect_a.area
    area_b = rect_b.area
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area
