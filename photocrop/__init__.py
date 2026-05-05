"""
PhotoCrop - 从扫描 PDF 相册中提取照片

v0.1.0: 引擎封装 — 检测照片矩形 + 旋转角度估计
v0.2.0: UI 交互 — PySide6 画布 + 可交互裁剪框
v0.3.0: 导出功能 — 裁剪 + 旋转 + 去白边 + PDF 读取
"""

__version__ = "0.4.0"

from photocrop.utils.crop_rect import CropRect

# 引擎依赖 scipy，可能未安装
try:
    from photocrop.engine.core import detect_rectangles
except ImportError:
    detect_rectangles = None

__all__ = ["detect_rectangles", "CropRect"]
