"""
工具模块 — CropRect 数据类、坐标转换、角度工具、IoU 计算
"""

from photocrop.utils.crop_rect import CropRect
from photocrop.utils.iou import compute_iou
from photocrop.utils.rotation import to_opencv_angle

__all__ = ["CropRect", "to_opencv_angle", "compute_iou"]
