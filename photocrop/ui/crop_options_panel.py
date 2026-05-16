"""
CropOptionsPanel — 裁剪框属性编辑面板

对标 AutoCropper 右侧 CROP OPTIONS。
显示选中裁剪框的 Width/Height/X/Y/Rotation，支持实时编辑。

v0.5.3: 自定义 56px 标签列布局，标签与单位分行显示。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from photocrop.ui.styled_dropdown import LightDropdown
from photocrop.ui.theme import FONT_FAMILY
from photocrop.utils.crop_rect import CropRect


@dataclass
class _PanelColors:
    """面板内部颜色（从 ThemeColors 提取）"""
    bg: str = "#F5F5F5"
    text: str = "#1A1A1A"
    text_secondary: str = "#666666"
    surface: str = "#FFFFFF"
    border: str = "#E0E0E0"
    border_strong: str = "#CCCCCC"
    accent: str = "#000000"


class CropOptionsPanel(QWidget):
    """裁剪框属性编辑面板 — 黑白极简风格（优雅表单排布）"""

    rect_changed = Signal()
    editing_finished = Signal()
    aspect_ratio_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self._colors = _PanelColors()

        self._block_signals = False
        self._current_rect: CropRect | None = None
        self._current_image_size: tuple = (0, 0)

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        """构建 UI 结构（不设置颜色）"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._header = QLabel("CROP OPTIONS")
        layout.addWidget(self._header)

        self._placeholder = QLabel("Select a crop to edit")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder)

        self._form_widget = QWidget()
        form_layout = QVBoxLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        # --- Size group ---
        # Width
        row_w = self._create_form_row("Width")
        self._spin_width = QSpinBox()
        self._spin_width.setRange(10, 10000)
        self._spin_width.valueChanged.connect(self._on_value_changed)
        self._spin_width.editingFinished.connect(self._on_editing_finished)
        row_w.layout().addWidget(self._spin_width, 1)
        unit_w = QLabel("px")
        unit_w.setObjectName("unitLabel")
        row_w.layout().addWidget(unit_w)
        form_layout.addWidget(row_w)

        # Height
        row_h = self._create_form_row("Height")
        self._spin_height = QSpinBox()
        self._spin_height.setRange(10, 10000)
        self._spin_height.valueChanged.connect(self._on_value_changed)
        self._spin_height.editingFinished.connect(self._on_editing_finished)
        row_h.layout().addWidget(self._spin_height, 1)
        unit_h = QLabel("px")
        unit_h.setObjectName("unitLabel")
        row_h.layout().addWidget(unit_h)
        form_layout.addWidget(row_h)

        # --- Separator: Size → Position ---
        form_layout.addWidget(self._create_separator())

        # --- Position group ---
        # X
        row_x = self._create_form_row("X")
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 10000)
        self._spin_x.valueChanged.connect(self._on_value_changed)
        self._spin_x.editingFinished.connect(self._on_editing_finished)
        row_x.layout().addWidget(self._spin_x, 1)
        unit_x = QLabel("px")
        unit_x.setObjectName("unitLabel")
        row_x.layout().addWidget(unit_x)
        form_layout.addWidget(row_x)

        # Y
        row_y = self._create_form_row("Y")
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 10000)
        self._spin_y.valueChanged.connect(self._on_value_changed)
        self._spin_y.editingFinished.connect(self._on_editing_finished)
        row_y.layout().addWidget(self._spin_y, 1)
        unit_y = QLabel("px")
        unit_y.setObjectName("unitLabel")
        row_y.layout().addWidget(unit_y)
        form_layout.addWidget(row_y)

        # --- Separator: Position → Rotation ---
        form_layout.addWidget(self._create_separator())

        # --- Rotation (input on first row, Reset link below) ---
        row_rot = self._create_form_row("Rotation")
        self._spin_rotation = QDoubleSpinBox()
        self._spin_rotation.setRange(-180.0, 180.0)
        self._spin_rotation.setSingleStep(0.5)
        self._spin_rotation.setDecimals(1)
        self._spin_rotation.valueChanged.connect(self._on_value_changed)
        self._spin_rotation.editingFinished.connect(self._on_editing_finished)
        row_rot.layout().addWidget(self._spin_rotation, 1)
        unit_rot = QLabel("deg")
        unit_rot.setObjectName("unitLabel")
        row_rot.layout().addWidget(unit_rot)
        form_layout.addWidget(row_rot)

        self._btn_reset_rotation = QPushButton("Reset to 0")
        self._btn_reset_rotation.setObjectName("resetLink")
        self._btn_reset_rotation.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset_rotation.clicked.connect(self._on_reset_rotation)
        reset_row = QWidget()
        reset_layout = QHBoxLayout(reset_row)
        reset_layout.setContentsMargins(64, 0, 0, 0)  # 56px label + 8px spacing
        reset_layout.addWidget(self._btn_reset_rotation)
        reset_layout.addStretch()
        form_layout.addWidget(reset_row)

        # --- Separator: Rotation → Aspect ---
        form_layout.addWidget(self._create_separator())

        # --- Aspect Ratio ---
        row_ar = self._create_form_row("Aspect")
        self._combo_aspect = LightDropdown(parent=self)
        self._combo_aspect.add_option("free", "Free")
        self._combo_aspect.add_option("original", "Original")
        self._combo_aspect.add_option("1:1", "1:1", "□")
        self._combo_aspect.add_option("3:2", "3:2", "▭")
        self._combo_aspect.add_option("4:3", "4:3", "▭")
        self._combo_aspect.add_option("16:9", "16:9", "▬")
        self._combo_aspect.current_changed.connect(self._on_aspect_changed)
        row_ar.layout().addWidget(self._combo_aspect, 1)
        form_layout.addWidget(row_ar)

        layout.addWidget(self._form_widget)
        self._form_widget.setVisible(False)
        layout.addStretch()

    def _create_separator(self) -> QWidget:
        """创建细线分隔符（占位，颜色在 _apply_styles 中设置）"""
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setObjectName("formSep")
        return sep

    def _apply_styles(self) -> None:
        """根据当前 _colors 应用所有样式"""
        c = self._colors
        self.setStyleSheet(f"CropOptionsPanel {{ background-color: {c.bg}; }}")
        self._header.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: 11px; font-weight: 600; letter-spacing: 0.5px;"
        )
        self._placeholder.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: 12px; padding: 40px 0;"
        )
        # 输入框
        input_style = (
            f"QSpinBox, QDoubleSpinBox {{"
            f"background-color: {c.surface}; color: {c.text}; "
            f"border: 1px solid {c.border}; border-radius: 4px; "
            f"padding: 3px 6px; font-family: {FONT_FAMILY}; "
            f"font-size: 12px; min-height: 24px;"
            f"}}"
            f"QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c.border_strong}; }}"
            f"QSpinBox::up-button, QSpinBox::down-button,"
            f"QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{"
            f"width: 14px; border: none; background: transparent; }}"
        )
        for spin in [self._spin_width, self._spin_height, self._spin_x, self._spin_y, self._spin_rotation]:
            spin.setStyleSheet(input_style)
        # LightDropdown — 统一主题
        self._combo_aspect.apply_theme(c)
        # Reset 链接按钮
        self._btn_reset_rotation.setStyleSheet(
            f"QPushButton {{"
            f"background-color: transparent; color: {c.text_secondary}; "
            f"border: none; font-family: {FONT_FAMILY}; font-size: 11px; "
            f"padding: 2px 0; text-decoration: underline;"
            f"}}"
            f"QPushButton:hover {{ color: {c.accent}; }}"
        )
        # 单位标签 + 分隔线 + 表单行标签
        for lbl in self.findChildren(QLabel):
            if lbl in (self._header, self._placeholder):
                continue
            if lbl.objectName() == "unitLabel":
                lbl.setStyleSheet(
                    f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
                    f"font-size: 11px; font-weight: 500; min-width: 20px;"
                )
                continue
            ss = lbl.styleSheet() or ""
            if "color:" in ss:
                continue  # already explicitly styled
            lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 12px;"
            )
        for sep in self._form_widget.findChildren(QWidget):
            if sep.objectName() == "formSep":
                sep.setStyleSheet(f"background-color: {c.border};")

    # ===== 辅助：创建表单行 =====

    def _create_form_row(self, label: str) -> QWidget:
        c = self._colors
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedWidth(56)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: 12px;"
        )
        row_layout.addWidget(lbl)
        return row

    def _create_label_col(self, label: str, unit: str) -> QWidget:
        """Deprecated: kept for backward compatibility. Use _create_form_row instead."""
        return self._create_form_row(label)

    # ===== 业务方法 =====

    def set_selected_rect(self, rect: CropRect | None,
                          image_size: tuple = (0, 0)) -> None:
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

        img_w, img_h = image_size
        if img_w > 0:
            self._spin_x.setRange(0, img_w)
        if img_h > 0:
            self._spin_y.setRange(0, img_h)

        self._block_signals = True
        self._spin_width.setValue(int(rect.width))
        self._spin_height.setValue(int(rect.height))
        self._spin_x.setValue(int(rect.x1))
        self._spin_y.setValue(int(rect.y1))
        self._spin_rotation.setValue(rect.rotation_angle)
        self._block_signals = False

    def update_rotation(self, angle: float) -> None:
        """旋转中轻量更新角度值（不触发 valueChanged 信号）"""
        if self._current_rect is None:
            return
        self._block_signals = True
        self._spin_rotation.setValue(angle)
        self._block_signals = False

    def _on_value_changed(self) -> None:
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
        if self._block_signals or self._current_rect is None:
            return
        self.editing_finished.emit()

    def _on_reset_rotation(self) -> None:
        if self._current_rect is None:
            return
        self._block_signals = True
        self._spin_rotation.setValue(0.0)
        self._block_signals = False
        self._current_rect.rotation_angle = 0.0
        self.rect_changed.emit()
        self.editing_finished.emit()

    def _on_aspect_changed(self, value: str) -> None:
        ratio_map = {
            "free": 0.0, "original": -1.0, "1:1": 1.0,
            "3:2": 3 / 2, "4:3": 4 / 3, "16:9": 16 / 9,
        }
        ratio = ratio_map.get(value, 0.0)
        self.aspect_ratio_changed.emit(ratio)

    def set_theme(self, colors) -> None:
        """更新面板颜色（主题切换时调用）"""
        self._colors = _PanelColors(
            bg=colors.bg, text=colors.text, text_secondary=colors.text_secondary,
            surface=colors.surface, border=colors.border,
            border_strong=colors.border_strong, accent=colors.accent,
        )
        self._apply_styles()
        self._combo_aspect.apply_theme(colors)
