"""
CropOptionsPanel — 裁剪框属性编辑面板

对标 AutoCropper 右侧 CROP OPTIONS。
显示选中裁剪框的 Width/Height/X/Y/Rotation，支持实时编辑。
"""

from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QFormLayout,
    QSizePolicy,
)

from photocrop.utils.crop_rect import CropRect

# ============================================================
# 样式常量
# ============================================================

PANEL_BG = "#2c2c2e"
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#86868b"
APPLE_BLUE = "#0071e3"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


class CropOptionsPanel(QWidget):
    """裁剪框属性编辑面板

    Signals:
        rect_changed: 裁剪框属性被修改时发出（实时，用于预览更新）
        editing_finished: 编辑完成时发出（用于推入撤销栈）
    """

    rect_changed = Signal()
    editing_finished = Signal()
    aspect_ratio_changed = Signal(float)  # 发出 ratio 值（None → -1, Free → 0, 具体值 → ratio）

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(f"""
            CropOptionsPanel {{
                background-color: {PANEL_BG};
            }}
        """)

        self._block_signals = False
        self._current_rect: Optional[CropRect] = None
        self._current_image_size: tuple = (0, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题
        header = QLabel("CROP OPTIONS")
        header.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(header)

        # 未选中占位
        self._placeholder = QLabel("选择一个裁剪框")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 12px;
            padding: 30px 0;
        """)
        layout.addWidget(self._placeholder)

        # 属性表单容器
        self._form_widget = QWidget()
        form_layout = QFormLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        label_style = f"""
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 12px;
        """
        spin_style = f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: rgba(255, 255, 255, 0.08);
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                padding: 3px 6px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-height: 22px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {APPLE_BLUE};
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 14px;
                border: none;
                background: transparent;
            }}
        """

        # Width
        lbl_w = QLabel("Width (px)")
        lbl_w.setStyleSheet(label_style)
        self._spin_width = QSpinBox()
        self._spin_width.setRange(10, 10000)
        self._spin_width.setStyleSheet(spin_style)
        self._spin_width.valueChanged.connect(self._on_value_changed)
        self._spin_width.editingFinished.connect(self._on_editing_finished)
        form_layout.addRow(lbl_w, self._spin_width)

        # Height
        lbl_h = QLabel("Height (px)")
        lbl_h.setStyleSheet(label_style)
        self._spin_height = QSpinBox()
        self._spin_height.setRange(10, 10000)
        self._spin_height.setStyleSheet(spin_style)
        self._spin_height.valueChanged.connect(self._on_value_changed)
        self._spin_height.editingFinished.connect(self._on_editing_finished)
        form_layout.addRow(lbl_h, self._spin_height)

        # X Position
        lbl_x = QLabel("X (px)")
        lbl_x.setStyleSheet(label_style)
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 10000)
        self._spin_x.setStyleSheet(spin_style)
        self._spin_x.valueChanged.connect(self._on_value_changed)
        self._spin_x.editingFinished.connect(self._on_editing_finished)
        form_layout.addRow(lbl_x, self._spin_x)

        # Y Position
        lbl_y = QLabel("Y (px)")
        lbl_y.setStyleSheet(label_style)
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 10000)
        self._spin_y.setStyleSheet(spin_style)
        self._spin_y.valueChanged.connect(self._on_value_changed)
        self._spin_y.editingFinished.connect(self._on_editing_finished)
        form_layout.addRow(lbl_y, self._spin_y)

        # Rotation
        lbl_rot = QLabel("Rotation (deg)")
        lbl_rot.setStyleSheet(label_style)
        self._spin_rotation = QDoubleSpinBox()
        self._spin_rotation.setRange(-180.0, 180.0)
        self._spin_rotation.setSingleStep(0.5)
        self._spin_rotation.setDecimals(1)
        self._spin_rotation.setStyleSheet(spin_style)
        self._spin_rotation.valueChanged.connect(self._on_value_changed)
        self._spin_rotation.editingFinished.connect(self._on_editing_finished)

        # 重置旋转按钮
        self._btn_reset_rotation = QPushButton("Reset")
        self._btn_reset_rotation.setFixedSize(50, 22)
        self._btn_reset_rotation.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {APPLE_BLUE};
                border: 1px solid {APPLE_BLUE};
                border-radius: 4px;
                font-family: {FONT_FAMILY};
                font-size: 10px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 113, 227, 0.1);
            }}
        """)
        self._btn_reset_rotation.clicked.connect(self._on_reset_rotation)

        # Rotation 行：Spin + Reset 按钮
        rot_widget = QWidget()
        rot_layout = QHBoxLayout(rot_widget)
        rot_layout.setContentsMargins(0, 0, 0, 0)
        rot_layout.setSpacing(4)
        rot_layout.addWidget(self._spin_rotation)
        rot_layout.addWidget(self._btn_reset_rotation)
        form_layout.addRow(lbl_rot, rot_widget)

        # Aspect Ratio
        lbl_ar = QLabel("Aspect Ratio")
        lbl_ar.setStyleSheet(label_style)
        self._combo_aspect = QComboBox()
        self._combo_aspect.addItems(["Free", "Original", "1:1", "3:2", "4:3", "16:9"])
        self._combo_aspect.setStyleSheet(f"""
            QComboBox {{
                background-color: rgba(255,255,255,0.08);
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 4px;
                padding: 3px 6px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-height: 22px;
            }}
        """)
        self._combo_aspect.currentIndexChanged.connect(self._on_aspect_changed)
        form_layout.addRow(lbl_ar, self._combo_aspect)

        layout.addWidget(self._form_widget)
        self._form_widget.setVisible(False)

        layout.addStretch()

    def set_selected_rect(self, rect: Optional[CropRect],
                          image_size: tuple = (0, 0)) -> None:
        """设置当前选中的裁剪框

        Args:
            rect: 选中的 CropRect，或 None（取消选中）
            image_size: 源图尺寸 (width, height)，用于限制 SpinBox 范围
        """
        # 防御：如果传入 None 但当前已有数据，不覆盖（避免信号重复触发导致面板空白）
        if rect is None and self._current_rect is not None:
            return

        self._current_rect = rect
        self._current_image_size = image_size

        if rect is None:
            self._placeholder.setVisible(True)
            self._form_widget.setVisible(False)
            return

        self._placeholder.setVisible(False)
        self._form_widget.setVisible(True)

        # 更新范围
        img_w, img_h = image_size
        if img_w > 0:
            self._spin_x.setRange(0, img_w)
        if img_h > 0:
            self._spin_y.setRange(0, img_h)

        # 填充值（不触发信号）
        self._block_signals = True
        self._spin_width.setValue(int(rect.width))
        self._spin_height.setValue(int(rect.height))
        self._spin_x.setValue(int(rect.x1))
        self._spin_y.setValue(int(rect.y1))
        self._spin_rotation.setValue(rect.rotation_angle)
        self._block_signals = False

    def _on_value_changed(self) -> None:
        """实时更新裁剪框（不推入撤销栈）"""
        if self._block_signals or self._current_rect is None:
            return

        rect = self._current_rect
        x1 = self._spin_x.value()
        y1 = self._spin_y.value()
        w = self._spin_width.value()
        h = self._spin_height.value()
        rotation = self._spin_rotation.value()

        # 从像素坐标重建 CropRect
        new_rect = CropRect.from_pixel_rect(x1, y1, x1 + w, y1 + h, rotation)
        rect.x = new_rect.x
        rect.y = new_rect.y
        rect.width = new_rect.width
        rect.height = new_rect.height
        rect.rotation_angle = rotation

        self.rect_changed.emit()

    def _on_editing_finished(self) -> None:
        """编辑完成，推入撤销栈"""
        if self._block_signals or self._current_rect is None:
            return
        self.editing_finished.emit()

    def _on_reset_rotation(self) -> None:
        """重置旋转角度为 0"""
        if self._current_rect is None:
            return
        self._block_signals = True
        self._spin_rotation.setValue(0.0)
        self._block_signals = False
        self._current_rect.rotation_angle = 0.0
        self.rect_changed.emit()
        self.editing_finished.emit()

    def _on_aspect_changed(self, index: int) -> None:
        """宽高比下拉框变化"""
        # 0=Free, 1=Original, 2=1:1, 3=3:2, 4=4:3, 5=16:9
        ratio_map = {
            0: 0.0,       # Free
            1: -1.0,      # Original (特殊标记)
            2: 1.0,       # 1:1
            3: 3 / 2,     # 3:2
            4: 4 / 3,     # 4:3
            5: 16 / 9,    # 16:9
        }
        ratio = ratio_map.get(index, 0.0)
        self.aspect_ratio_changed.emit(ratio)
