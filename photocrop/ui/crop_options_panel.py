"""
CropOptionsPanel — 裁剪框属性编辑面板

对标 AutoCropper 右侧 CROP OPTIONS。
显示选中裁剪框的 Width/Height/X/Y/Rotation，支持实时编辑。

v0.5.3: 自定义 56px 标签列布局，标签与单位分行显示。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from photocrop.utils.crop_rect import CropRect

# ============================================================
# 样式常量 — 黑白极简
# ============================================================

PANEL_BG = "#F5F5F5"
TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#666666"
APPLE_BLUE = "#000000"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


class CropOptionsPanel(QWidget):
    """裁剪框属性编辑面板 — 黑白极简风格（优雅表单排布）"""

    rect_changed = Signal()
    editing_finished = Signal()
    aspect_ratio_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(f"""
            CropOptionsPanel {{
                background-color: {PANEL_BG};
            }}
        """)

        self._block_signals = False
        self._current_rect: CropRect | None = None
        self._current_image_size: tuple = (0, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
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
            padding: 40px 0;
        """)
        layout.addWidget(self._placeholder)

        # ===== 属性表单容器 — 优雅排布 =====
        self._form_widget = QWidget()
        form_layout = QVBoxLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)  # 行间距 10px

        # 通用输入框样式
        input_style = f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: #FFFFFF;
                color: {TEXT_PRIMARY};
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 3px 6px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-height: 24px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: #999999;
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 14px;
                border: none;
                background: transparent;
            }}
        """

        # --- Width 行 ---
        row_w = self._create_form_row("Width", "px")
        self._spin_width = QSpinBox()
        self._spin_width.setRange(10, 10000)
        self._spin_width.setStyleSheet(input_style)
        self._spin_width.valueChanged.connect(self._on_value_changed)
        self._spin_width.editingFinished.connect(self._on_editing_finished)
        row_w.layout().addWidget(self._spin_width)
        form_layout.addWidget(row_w)

        # --- Height 行 ---
        row_h = self._create_form_row("Height", "px")
        self._spin_height = QSpinBox()
        self._spin_height.setRange(10, 10000)
        self._spin_height.setStyleSheet(input_style)
        self._spin_height.valueChanged.connect(self._on_value_changed)
        self._spin_height.editingFinished.connect(self._on_editing_finished)
        row_h.layout().addWidget(self._spin_height)
        form_layout.addWidget(row_h)

        # --- X 行 ---
        row_x = self._create_form_row("X", "px")
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 10000)
        self._spin_x.setStyleSheet(input_style)
        self._spin_x.valueChanged.connect(self._on_value_changed)
        self._spin_x.editingFinished.connect(self._on_editing_finished)
        row_x.layout().addWidget(self._spin_x)
        form_layout.addWidget(row_x)

        # --- Y 行 ---
        row_y = self._create_form_row("Y", "px")
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 10000)
        self._spin_y.setStyleSheet(input_style)
        self._spin_y.valueChanged.connect(self._on_value_changed)
        self._spin_y.editingFinished.connect(self._on_editing_finished)
        row_y.layout().addWidget(self._spin_y)
        form_layout.addWidget(row_y)

        # --- Rotation 行（带 Reset 按钮）---
        row_rot = QWidget()
        rot_layout = QHBoxLayout(row_rot)
        rot_layout.setContentsMargins(0, 0, 0, 0)
        rot_layout.setSpacing(8)

        # 标签列（固定 56px）
        lbl_rot = self._create_label_col("Rotation", "")
        rot_layout.addWidget(lbl_rot)

        # 输入框 + Reset
        self._spin_rotation = QDoubleSpinBox()
        self._spin_rotation.setRange(-180.0, 180.0)
        self._spin_rotation.setSingleStep(0.5)
        self._spin_rotation.setDecimals(1)
        self._spin_rotation.setStyleSheet(input_style)
        self._spin_rotation.valueChanged.connect(self._on_value_changed)
        self._spin_rotation.editingFinished.connect(self._on_editing_finished)
        rot_layout.addWidget(self._spin_rotation, 1)

        self._btn_reset_rotation = QPushButton("Reset")
        self._btn_reset_rotation.setFixedSize(44, 24)
        self._btn_reset_rotation.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                font-family: {FONT_FAMILY};
                font-size: 10px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: #F0F0F0;
                border-color: #BBBBBB;
            }}
        """)
        self._btn_reset_rotation.clicked.connect(self._on_reset_rotation)
        rot_layout.addWidget(self._btn_reset_rotation)
        form_layout.addWidget(row_rot)

        # --- Aspect Ratio 行 ---
        row_ar = QWidget()
        ar_layout = QHBoxLayout(row_ar)
        ar_layout.setContentsMargins(0, 0, 0, 0)
        ar_layout.setSpacing(8)

        lbl_ar = self._create_label_col("Aspect", "")
        ar_layout.addWidget(lbl_ar)

        self._combo_aspect = QComboBox()
        self._combo_aspect.addItems(["Free", "Original", "1:1", "3:2", "4:3", "16:9"])
        self._combo_aspect.setStyleSheet(f"""
            QComboBox {{
                background-color: #FFFFFF;
                color: {TEXT_PRIMARY};
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 3px 6px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-height: 24px;
            }}
            QComboBox:focus {{
                border-color: #999999;
            }}
        """)
        self._combo_aspect.currentIndexChanged.connect(self._on_aspect_changed)
        ar_layout.addWidget(self._combo_aspect, 1)
        form_layout.addWidget(row_ar)

        layout.addWidget(self._form_widget)
        self._form_widget.setVisible(False)
        layout.addStretch()

    # ===== 辅助：创建表单行 =====

    def _create_form_row(self, label: str, unit: str) -> QWidget:
        """创建一行：固定56px标签列 + 输入框槽位"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        lbl_widget = self._create_label_col(label, unit)
        row_layout.addWidget(lbl_widget)
        return row

    def _create_label_col(self, label: str, unit: str) -> QWidget:
        """创建标签列：主标签 + 单位（换行），固定 56px，右对齐"""
        col = QWidget()
        col.setFixedWidth(56)
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)
        col_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lbl_main = QLabel(label)
        lbl_main.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
        """)
        lbl_main.setAlignment(Qt.AlignmentFlag.AlignRight)
        col_layout.addWidget(lbl_main)

        if unit:
            lbl_unit = QLabel(unit)
            lbl_unit.setStyleSheet(f"""
                color: {TEXT_SECONDARY};
                font-family: {FONT_FAMILY};
                font-size: 9px;
            """)
            lbl_unit.setAlignment(Qt.AlignmentFlag.AlignRight)
            col_layout.addWidget(lbl_unit)

        return col

    # ===== 业务方法（完全不变）=====

    def set_selected_rect(self, rect: CropRect | None,
                          image_size: tuple = (0, 0)) -> None:
        """设置当前选中的裁剪框"""
        # 防御：如果传入 None 但当前已有数据，不覆盖
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
        ratio_map = {
            0: 0.0,       # Free
            1: -1.0,      # Original
            2: 1.0,       # 1:1
            3: 3 / 2,     # 3:2
            4: 4 / 3,     # 4:3
            5: 16 / 9,    # 16:9
        }
        ratio = ratio_map.get(index, 0.0)
        self.aspect_ratio_changed.emit(ratio)

    def set_theme(self, colors) -> None:
        """更新面板颜色"""
        self.setStyleSheet(f"""
            CropOptionsPanel {{
                background-color: {colors.bg};
            }}
        """)
