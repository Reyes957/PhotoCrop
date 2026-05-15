"""
StyledDropdown — 1:1 复刻设计规范的自定义下拉组件

替代原生 QComboBox，实现：
- 反色选中态（Light 黑底白字，Dark 白底黑字）
- 200ms 淡入动画
- SVG 箭头切换
- 选项带主标签 + 描述副标题（无独立卡片背景）
- 面板左对齐触发器，顶部偏移 6px
"""

from __future__ import annotations

from PySide6.QtCore import (
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photocrop.ui.icons import get_icon
from photocrop.ui.theme import FONT_FAMILY, FontSize, FontWeight


# ============================================================
# OptionRow — 单个选项行（56px 统一高度，无独立背景）
# ============================================================

class OptionRow(QWidget):
    """下拉菜单中的单个选项行（56px 统一高度）"""

    clicked = Signal(str)

    def __init__(self, value: str, label: str, desc: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._value = value
        self._selected = False

        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(8)

        # 选中标记（默认隐藏）
        self._check = QLabel("✓")
        self._check.setFixedWidth(16)
        self._check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check.setVisible(False)
        layout.addWidget(self._check)

        # 文字区（始终创建 _desc，避免高度塌陷）
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self._lbl = QLabel(label)
        self._lbl.setWordWrap(False)
        text_layout.addWidget(self._lbl)

        self._desc = QLabel(desc if desc else "")
        self._desc.setWordWrap(True)
        text_layout.addWidget(self._desc)

        layout.addLayout(text_layout, 1)

        # 初始状态
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._check.setVisible(selected)

        from photocrop.ui.theme import theme
        c = theme.colors

        if selected:
            bg = c.accent
            fg = "#FFFFFF" if theme.mode == "light" else "#1A1A1A"
            desc_fg = ("rgba(255,255,255,0.7)" if theme.mode == "light"
                       else "rgba(26,26,26,0.6)")

            self.setStyleSheet(
                f"background-color: {bg}; border: none; border-radius: 6px;"
            )
            self._lbl.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.MEDIUM}; color: {fg}; "
                f"background: transparent; border: none;"
            )
            self._desc.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.TINY}px; "
                f"font-weight: {FontWeight.REGULAR}; color: {desc_fg}; "
                f"background: transparent; border: none;"
            )
            self._check.setStyleSheet(
                f"color: {fg}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.SEMIBOLD}; "
                f"background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(
                "background-color: transparent; border: none; border-radius: 6px;"
            )
            self._lbl.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.MEDIUM}; color: {c.text}; "
                f"background: transparent; border: none;"
            )
            self._desc.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.TINY}px; "
                f"font-weight: {FontWeight.REGULAR}; color: {c.text_secondary}; "
                f"background: transparent; border: none;"
            )

    def enterEvent(self, event) -> None:
        if not self._selected:
            from photocrop.ui.theme import theme
            self.setStyleSheet(
                f"background-color: {theme.colors.hover_bg}; "
                f"border: none; border-radius: 6px;"
            )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._selected:
            self.setStyleSheet(
                "background-color: transparent; border: none; border-radius: 6px;"
            )
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._value)
        super().mousePressEvent(event)


# ============================================================
# StyledDropdown — 自定义下拉组件
# ============================================================

class StyledDropdown(QWidget):
    """自定义下拉组件（替代 QComboBox）"""

    current_changed = Signal(str)

    def __init__(self, panel_width: int = 280, parent: QWidget | None = None):
        super().__init__(parent)
        self._panel_width = panel_width
        self._options: list[OptionRow] = []
        self._current_value: str = ""
        self._is_open = False
        self._open_anim: QPropertyAnimation | None = None
        self._close_anim: QPropertyAnimation | None = None

        # 触发器
        self._trigger = QPushButton()
        self._trigger.setFixedHeight(32)
        self._trigger.setMinimumWidth(140)
        self._trigger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trigger.clicked.connect(self._on_trigger_clicked)

        # 箭头（SVG 图标）
        self._arrow = QLabel(self._trigger)
        self._arrow.setFixedSize(14, 14)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._trigger)

        # 弹出面板
        self._panel = QFrame()
        self._panel.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._panel.setFixedWidth(panel_width)

        self._panel_layout = QVBoxLayout(self._panel)
        self._panel_layout.setContentsMargins(4, 4, 4, 4)
        self._panel_layout.setSpacing(2)

        # 透明度效果（动画用）
        self._opacity_effect = QGraphicsOpacityEffect(self._panel)
        self._opacity_effect.setOpacity(1.0)
        self._panel.setGraphicsEffect(self._opacity_effect)

        self._apply_style()

    def add_option(self, value: str, label: str, desc: str = "") -> None:
        row = OptionRow(value, label, desc, self._panel)
        row.clicked.connect(self._on_option_clicked)
        row.set_selected(False)
        self._panel_layout.addWidget(row)
        self._options.append(row)
        if not self._current_value and self._options:
            self._current_value = value
            self._update_trigger_text()
            self._update_selection()

    def set_current(self, value: str) -> None:
        self._current_value = value
        self._update_trigger_text()
        self._update_selection()

    def current_value(self) -> str:
        return self._current_value

    def apply_theme(self, colors) -> None:
        self._apply_style()
        self._update_selection()

    def _apply_style(self) -> None:
        from photocrop.ui.theme import theme
        c = theme.colors

        self._trigger.setStyleSheet(
            f"QPushButton {{"
            f" background: {c.surface}; color: {c.text};"
            f" border: 1px solid {c.border}; border-radius: 6px;"
            f" padding: 0 28px 0 10px;"
            f" font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px;"
            f" font-weight: {FontWeight.REGULAR};"
            f" text-align: left;"
            f"}}"
            f"QPushButton:hover {{ border-color: {c.border_strong}; }}"
        )

        self._panel.setStyleSheet(
            f"QFrame {{"
            f" background: {c.surface};"
            f" border: 1px solid {c.border_strong};"
            f" border-radius: 8px;"
            f"}}"
        )

        self._update_arrow_icon()

    def _update_arrow_icon(self) -> None:
        from photocrop.ui.theme import theme
        c = theme.colors
        color = c.text_secondary
        icon_name = "chevron-up" if self._is_open else "chevron-down"
        icon = get_icon(icon_name, color)
        self._arrow.setPixmap(icon.pixmap(14, 14))

    def _update_trigger_text(self) -> None:
        for row in self._options:
            if row._value == self._current_value:
                self._trigger.setText(row._lbl.text())
                return
        self._trigger.setText("")

    def _update_selection(self) -> None:
        for row in self._options:
            row.set_selected(row._value == self._current_value)

    def _on_trigger_clicked(self) -> None:
        if self._is_open:
            self._close_panel()
        else:
            self._open_panel()

    def _on_option_clicked(self, value: str) -> None:
        self._current_value = value
        self._update_trigger_text()
        self._update_selection()
        self._close_panel()
        self.current_changed.emit(value)

    # ---- 面板动画 ----

    def _open_panel(self) -> None:
        if self._is_open:
            return
        self._is_open = True

        self._update_arrow_icon()

        # 定位面板
        trigger_global = self._trigger.mapToGlobal(
            QPoint(0, self._trigger.height()),
        )
        self._panel.move(trigger_global + QPoint(0, 6))
        self._panel.setFixedWidth(self._panel_width)

        self._update_selection()

        # 淡入动画
        self._opacity_effect.setOpacity(0.0)
        self._panel.show()
        self._panel.raise_()

        anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._open_anim = anim

    def _close_panel(self) -> None:
        if not self._is_open:
            return
        self._is_open = False

        self._update_arrow_icon()

        anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        anim.setDuration(200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.start()
        anim.finished.connect(self._panel.hide)
        self._close_anim = anim

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._arrow.move(self._trigger.width() - 22, 9)
