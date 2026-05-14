"""
UI 模块 — PySide6 交互画布

v0.4.0 核心组件：
    - canvas.CropCanvas              图像显示 + 裁剪框管理
    - crop_item.CropItem              可交互裁剪框（拖动/缩放/旋转）
    - main_window.MainWindow          主窗口（工具栏 + 画布 + 状态栏）
    - undo_manager.UndoManager        撤销/重做管理器
    - state.SessionState              图像会话状态
    - image_list_panel.ImageListPanel 左侧图像列表
    - crop_options_panel.CropOptionsPanel  裁剪框属性面板
    - extracted_images_panel.ExtractedImagesPanel  提取预览
    - single_view_panel.SingleViewPanel  单视图面板
    - export_dialog.ExportDialog      导出设置对话框
    - template_manager.TemplateManager  模板管理器
"""

from photocrop.ui.canvas import CropCanvas
from photocrop.ui.crop_item import CropItem
from photocrop.ui.main_window import MainWindow

__all__ = ["MainWindow", "CropCanvas", "CropItem"]
