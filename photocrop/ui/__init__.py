"""
UI 模块 — PySide6 交互画布

v0.2.0 核心组件：
    - canvas.CropCanvas      图像显示 + 裁剪框管理
    - crop_item.CropItem      可交互裁剪框（拖动/缩放/旋转）
    - main_window.MainWindow   主窗口（工具栏 + 画布 + 状态栏）
"""

from photocrop.ui.main_window import MainWindow
from photocrop.ui.canvas import CropCanvas
from photocrop.ui.crop_item import CropItem

__all__ = ["MainWindow", "CropCanvas", "CropItem"]
