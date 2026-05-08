"""
过滤模块 — 小框过滤、IoU 去重、置信度筛选

规范（project_rules.md §6）：
  检测流程中的第 3、4、5 步
"""


from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou  # 统一 IoU 实现

# 向后兼容：允许 from filters import compute_iou
__all__ = ["compute_iou", "iou_deduplicate", "filter_small_rects",
           "filter_extreme_aspect", "limit_count", "validate_photo"]


# ============================================================
# IoU 去重 (NMS 风格)
# ============================================================

def iou_deduplicate(
    rects: list[CropRect],
    iou_threshold: float = 0.7
) -> list[CropRect]:
    """IoU 去重：移除高度重叠的检测框

    按置信度降序排列，保留置信度最高的框，
    移除与其 IoU 超过阈值的其余框。

    Args:
        rects: CropRect 列表
        iou_threshold: IoU 阈值，超过此值视为重复（默认 0.7）

    Returns:
        去重后的 CropRect 列表
    """
    if not rects:
        return []

    # 按置信度降序，无置信度则按面积降序
    sorted_rects = sorted(
        rects,
        key=lambda r: (
            r.confidence if r.confidence is not None else r.area
        ),
        reverse=True
    )

    kept: list[CropRect] = []
    suppressed = set()

    for i, rect_a in enumerate(sorted_rects):
        if i in suppressed:
            continue
        kept.append(rect_a)
        for j, rect_b in enumerate(sorted_rects):
            if j <= i or j in suppressed:
                continue
            iou = compute_iou(rect_a, rect_b)
            if iou > iou_threshold:
                suppressed.add(j)

    return kept


# ============================================================
# 小框过滤
# ============================================================

def filter_small_rects(
    rects: list[CropRect],
    min_width: float = 100,
    min_height: float = 100,
    min_area: float = 10000
) -> list[CropRect]:
    """过滤尺寸过小的检测框（碎片、噪点）

    Args:
        rects: CropRect 列表
        min_width: 最小宽度（像素）
        min_height: 最小高度（像素）
        min_area: 最小面积（像素²）

    Returns:
        过滤后的 CropRect 列表
    """
    return [
        r for r in rects
        if r.width >= min_width
        and r.height >= min_height
        and r.area >= min_area
    ]


# ============================================================
# 过度拉伸过滤
# ============================================================

def filter_extreme_aspect(
    rects: list[CropRect],
    max_aspect_ratio: float = 3.5
) -> list[CropRect]:
    """过滤过度拉伸的框（不太可能是正常照片）

    Args:
        rects: CropRect 列表
        max_aspect_ratio: 最大允许的宽高比 (max(w,h) / min(w,h))

    Returns:
        过滤后的 CropRect 列表
    """
    kept = []
    for r in rects:
        aspect = max(r.width, r.height) / max(min(r.width, r.height), 1)
        if aspect <= max_aspect_ratio:
            kept.append(r)
    return kept


# ============================================================
# 数量限制
# ============================================================

def limit_count(
    rects: list[CropRect],
    max_count: int = 4
) -> list[CropRect]:
    """限制返回的检测框数量

    保留置信度最高（或面积最大）的 N 个框。

    Args:
        rects: CropRect 列表
        max_count: 最大保留数量（默认 4）

    Returns:
        裁剪后的 CropRect 列表
    """
    if len(rects) <= max_count:
        return rects

    sorted_rects = sorted(
        rects,
        key=lambda r: (
            r.confidence if r.confidence is not None else r.area
        ),
        reverse=True
    )
    return sorted_rects[:max_count]


# ============================================================
# 验证过滤器（排除碎片、纯框、过度拉伸）
# ============================================================

def validate_photo(rect: CropRect) -> bool:
    """验证 CropRect 是否对应一张有效照片

    排除碎片、纯框、过度拉伸等。

    Args:
        rect: CropRect 对象

    Returns:
        是否为有效照片
    """
    aspect = max(rect.width, rect.height) / max(min(rect.width, rect.height), 1)

    # 最小尺寸检查
    if rect.width < 100 or rect.height < 100 or rect.area < 10000:
        return False

    # 过度拉伸检查
    if aspect > 3.5:
        return False

    return True
