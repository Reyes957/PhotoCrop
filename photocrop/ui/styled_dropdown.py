"""
StyledDropdown / LightDropdown — 自定义下拉组件家族

StyledDropdown: 重模型下拉（检测器选择），56px 选项行 + 描述副标题
LightDropdown:  轻量下拉（Aspect Ratio 等），36px 选项行 + 可选 Badge

共性：
- 反色选中态（Light 黑底白字 / Dark 白底黑字）
- 淡入淡出动画 + 面板阴影
- SVG 箭头切换
- 键盘导航（Esc / ↑↓ / Enter）
- 点击外部关闭（全局事件过滤器）
- 高度自适应内容
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBitmap, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
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
        layout.setContentsMargins(10, 6, 12, 6)
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
# LightOptionRow — 轻量选项行（36px，无描述，可选 Badge）
# ============================================================

class LightOptionRow(QWidget):
    """轻量下拉菜单中的单个选项行（36px 统一高度）"""

    clicked = Signal(str)

    def __init__(self, value: str, label: str, badge: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._value = value
        self._selected = False

        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(8)

        # 选中标记
        self._check = QLabel("✓")
        self._check.setFixedWidth(16)
        self._check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check.setVisible(False)
        layout.addWidget(self._check)

        # 标签
        self._lbl = QLabel(label)
        self._lbl.setWordWrap(False)
        layout.addWidget(self._lbl, 1)

        # Badge（比例图示等）
        self._badge = QLabel(badge) if badge else None
        if self._badge:
            self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._badge.setFixedWidth(24)
            layout.addWidget(self._badge)

        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._check.setVisible(selected)

        from photocrop.ui.theme import theme
        c = theme.colors

        if selected:
            bg = c.accent
            fg = "#FFFFFF" if theme.mode == "light" else "#1A1A1A"
            self.setStyleSheet(
                f"background-color: {bg}; border: none; border-radius: 4px;"
            )
            self._lbl.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.SEMIBOLD}; color: {fg}; "
                f"background: transparent; border: none;"
            )
            if self._badge:
                self._badge.setStyleSheet(
                    f"color: {fg}; font-size: {FontSize.BODY}px; "
                    f"background: transparent; border: none;"
                )
            self._check.setStyleSheet(
                f"color: {fg}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.SEMIBOLD}; "
                f"background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(
                "background-color: transparent; border: none; border-radius: 4px;"
            )
            self._lbl.setStyleSheet(
                f"font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px; "
                f"font-weight: {FontWeight.REGULAR}; color: {c.text}; "
                f"background: transparent; border: none;"
            )
            if self._badge:
                self._badge.setStyleSheet(
                    f"color: {c.text_secondary}; font-size: {FontSize.BODY}px; "
                    f"background: transparent; border: none;"
                )

    def enterEvent(self, event) -> None:
        if not self._selected:
            from photocrop.ui.theme import theme
            self.setStyleSheet(
                f"background-color: {theme.colors.hover_bg}; "
                f"border: none; border-radius: 4px;"
            )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._selected:
            self.setStyleSheet(
                "background-color: transparent; border: none; border-radius: 4px;"
            )
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._value)
        super().mousePressEvent(event)


# ============================================================
# _DropdownPanelBase — 共用面板逻辑（动画、键盘、外部点击）
# ============================================================

class _DropdownPanelBase(QWidget):
    """下拉组件公共基类

    架构：layout 直接挂在 _panel（QFrame Popup 窗体）上。
    背景/边框/圆角由 QFrame 的 stylesheet 实现。
    """

    current_changed = Signal(str)

    # 子类可覆盖的参数
    _OPEN_DURATION = 180
    _CLOSE_DURATION = 130
    _ROW_HEIGHT = 56  # 子类覆盖
    _PANEL_RADIUS = 8
    _CONTENT_MARGINS = (4, 4, 4, 4)
    _CONTENT_SPACING = 2

    def __init__(self, panel_width: int = 280, parent: QWidget | None = None):
        super().__init__(parent)
        self._panel_width = panel_width
        self._options: list[QWidget] = []
        self._current_value: str = ""
        self._is_open = False
        self._keyboard_index: int = -1

        self._open_anim: QPropertyAnimation | None = None
        self._close_anim: QPropertyAnimation | None = None
        self._trigger_global_rect: QRect = QRect()

        # 触发器
        self._trigger = QPushButton()
        self._trigger.setFixedHeight(32)
        self._trigger.setMinimumWidth(140)
        self._trigger.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trigger.clicked.connect(self._on_trigger_clicked)

        # 箭头
        self._arrow = QLabel(self._trigger)
        self._arrow.setFixedSize(14, 14)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._trigger)

        # 弹出面板（QFrame + stylesheet 圆角）
        self._panel = QFrame()
        self._panel.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._panel.setFixedWidth(panel_width)
        # 监听面板自身的 Close/Hide，处理 macOS 外部关闭面板的场景
        self._panel.installEventFilter(self)

        # 面板布局
        cm = self._CONTENT_MARGINS
        self._panel_layout = QVBoxLayout(self._panel)
        self._panel_layout.setContentsMargins(*cm)
        self._panel_layout.setSpacing(self._CONTENT_SPACING)

        self._apply_style()

    # ---- 子类必须实现 ----

    def _apply_style(self) -> None:
        raise NotImplementedError

    def _row_value(self, row: QWidget) -> str:
        raise NotImplementedError

    def _set_row_selected(self, row: QWidget, selected: bool) -> None:
        raise NotImplementedError

    def _row_label_text(self, row: QWidget) -> str:
        raise NotImplementedError

    # ---- 公共 API ----

    def set_current(self, value: str) -> None:
        self._current_value = value
        self._update_trigger_text()
        self._update_selection()

    def current_value(self) -> str:
        return self._current_value

    def apply_theme(self, colors) -> None:
        self._apply_style()
        self._update_selection()

    # ---- 内部方法 ----

    def _register_option(self, row: QWidget) -> None:
        row.clicked.connect(self._on_option_clicked)
        self._panel_layout.addWidget(row)
        self._options.append(row)
        if not self._current_value and self._options:
            self._current_value = self._row_value(row)
            self._update_trigger_text()
            self._update_selection()

    def _update_trigger_text(self) -> None:
        for row in self._options:
            if self._row_value(row) == self._current_value:
                self._trigger.setText(self._row_label_text(row))
                return
        self._trigger.setText("")

    def _update_selection(self) -> None:
        for row in self._options:
            self._set_row_selected(row, self._row_value(row) == self._current_value)

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

    def _update_arrow_icon(self) -> None:
        from photocrop.ui.theme import theme
        c = theme.colors
        color = c.text_secondary
        icon_name = "chevron-up" if self._is_open else "chevron-down"
        icon = get_icon(icon_name, color)
        self._arrow.setPixmap(icon.pixmap(14, 14))

    # ---- 面板动画 ----

    def _compute_panel_height(self) -> int:
        """根据选项行的实际尺寸计算面板高度"""
        total = 0
        for row in self._options:
            hint = row.sizeHint()
            total += hint.height() if hint.height() > 0 else self._ROW_HEIGHT
        cm = self._CONTENT_MARGINS
        sp = self._CONTENT_SPACING
        total += cm[1] + cm[3]  # top + bottom margins
        if len(self._options) > 1:
            total += (len(self._options) - 1) * sp
        return total

    def _open_panel(self) -> None:
        if self._is_open:
            return
        self._keyboard_index = -1

        # 先停止可能残留的关闭动画，避免其 finished→hide 干扰
        if self._close_anim is not None:
            self._close_anim.stop()
            self._close_anim = None

        self._update_arrow_icon()

        # 动态计算面板高度
        panel_h = self._compute_panel_height()
        self._panel.setFixedHeight(panel_h)

        # 圆角遮罩（替代 WA_TranslucentBackground，避免 macOS 文字模糊）
        r = self._PANEL_RADIUS
        w = self._panel.width()
        bitmap = QBitmap(w, panel_h)
        bitmap.clear()
        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.color1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, panel_h, r, r)
        painter.end()
        self._panel.setMask(bitmap)

        # 先以 0 透明度显示面板，让 macOS 完成初始窗口定位，
        # 然后再移动到正确位置 — 避免 macOS 在 show() 时覆盖 move() 的坐标。
        self._panel.setWindowOpacity(0.0)
        self._panel.show()
        self._panel.raise_()

        # macOS 已接受该窗口，move() 不会被覆盖
        trigger_geo = self._trigger.rect()
        trigger_geo.moveTopLeft(self._trigger.mapToGlobal(QPoint(0, 0)))
        self._trigger_global_rect = trigger_geo
        self._panel.move(trigger_geo.bottomLeft() + QPoint(0, 6))

        self._is_open = True
        self._update_selection()

        # 淡入动画 — 面板已在正确位置，仅需透明度过渡
        anim = QPropertyAnimation(self._panel, b"windowOpacity")
        anim.setDuration(self._OPEN_DURATION)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._open_anim = anim

        # 安装全局事件过滤器
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _close_panel(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        self._keyboard_index = -1

        # 立即移除事件过滤器
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

        self._update_arrow_icon()

        # 停止可能残留的旧动画（断开 finished 避免 stop() 误触发 hide）
        if self._close_anim is not None:
            try:
                self._close_anim.finished.disconnect()
            except RuntimeError:
                pass
            self._close_anim.stop()
            self._close_anim = None

        # 淡出动画（不连接 finished 信号）
        anim = QPropertyAnimation(self._panel, b"windowOpacity")
        anim.setDuration(self._CLOSE_DURATION)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.start()
        self._close_anim = anim

        # 动画时长结束后隐藏（用 QTimer，不依赖 finished 信号）
        QTimer.singleShot(
            self._CLOSE_DURATION + 20, self._hide_panel_if_closed,
        )

    def _hide_panel_if_closed(self) -> None:
        """仅在面板确实已关闭时隐藏（防止重开后被误隐藏）"""
        if not self._is_open:
            self._panel.hide()

    # ---- 全局事件过滤器（点击外部关闭）----

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # 拦截面板自身的 Close/Hide — 当 macOS 因用户点击外部而关闭 Popup 时，
        # Qt 会直接关掉窗口而不经过 _close_panel()。这里同步内部状态。
        if obj is self._panel and event.type() in (
            QEvent.Type.Close, QEvent.Type.Hide,
        ):
            if self._is_open:
                self._is_open = False
                self._keyboard_index = -1
                app = QApplication.instance()
                if app:
                    app.removeEventFilter(self)
                self._update_arrow_icon()
            return False

        if (self._is_open and event.type() == QEvent.Type.MouseButtonPress):
            pos = event.globalPosition().toPoint()
            panel_geo = self._panel.geometry()
            # 点击面板内部 → 放行
            if panel_geo.contains(pos):
                return super().eventFilter(obj, event)
            # 点击触发器区域 → 放行（由 clicked 信号 → _on_trigger_clicked 统一处理）
            if self._trigger_global_rect.contains(pos):
                return super().eventFilter(obj, event)
            # 点击外部 → 关闭
            self._close_panel()
            # 不消费事件，让点击在目标位置正常生效
            return False
        return super().eventFilter(obj, event)

    # ---- 键盘导航 ----

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._is_open:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._close_panel()
        elif key == Qt.Key.Key_Down:
            self._navigate_keyboard(1)
        elif key == Qt.Key.Key_Up:
            self._navigate_keyboard(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm_keyboard_selection()
        else:
            super().keyPressEvent(event)

    def _navigate_keyboard(self, delta: int) -> None:
        count = len(self._options)
        if count == 0:
            return
        self._keyboard_index = max(0, min(count - 1,
                                          self._keyboard_index + delta))
        for i, row in enumerate(self._options):
            if i == self._keyboard_index and self._row_value(row) != self._current_value:
                from photocrop.ui.theme import theme
                row.setStyleSheet(
                    f"background-color: {theme.colors.hover_bg}; "
                    f"border: none; border-radius: 6px;"
                )
            elif self._row_value(row) != self._current_value:
                row.setStyleSheet(
                    "background-color: transparent; border: none; "
                    "border-radius: 6px;"
                )

    def _confirm_keyboard_selection(self) -> None:
        if 0 <= self._keyboard_index < len(self._options):
            value = self._row_value(self._options[self._keyboard_index])
            self._on_option_clicked(value)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._arrow.move(self._trigger.width() - 22, 9)


# ============================================================
# StyledDropdown — 重模型下拉（检测器选择）
# ============================================================

class StyledDropdown(_DropdownPanelBase):
    """自定义下拉组件（替代 QComboBox），56px 选项行 + 描述"""

    _ROW_HEIGHT = 56
    _PANEL_RADIUS = 8
    _CONTENT_MARGINS = (4, 0, 4, 0)  # 左右 4px / 上下 0px，选项贴边

    def __init__(self, panel_width: int = 280, parent: QWidget | None = None):
        super().__init__(panel_width, parent)

    def add_option(self, value: str, label: str, desc: str = "") -> None:
        row = OptionRow(value, label, desc, self._panel)
        self._register_option(row)

    def _apply_style(self) -> None:
        from photocrop.ui.theme import theme
        c = theme.colors

        self._trigger.setStyleSheet(
            f"QPushButton {{"
            f" background: {c.surface}; color: {c.text};"
            f" border: 1px solid {c.border}; border-radius: 4px;"
            f" padding: 0 28px 0 10px;"
            f" font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px;"
            f" font-weight: {FontWeight.REGULAR};"
            f" text-align: left;"
            f"}}"
            f"QPushButton:hover {{ border-color: {c.border_strong}; }}"
            f"QPushButton:pressed {{ border-color: {c.accent}; }}"
        )

        r = self._PANEL_RADIUS
        self._panel.setStyleSheet(
            f"QFrame {{"
            f" background: {c.surface};"
            f" border: 1px solid {c.border_strong};"
            f" border-radius: {r}px;"
            f"}}"
        )

        self._update_arrow_icon()

    def _row_value(self, row: QWidget) -> str:
        return row._value  # type: ignore[attr-defined]

    def _set_row_selected(self, row: QWidget, selected: bool) -> None:
        row.set_selected(selected)  # type: ignore[attr-defined]

    def _row_label_text(self, row: QWidget) -> str:
        return row._lbl.text()  # type: ignore[attr-defined]


# ============================================================
# LightDropdown — 轻量下拉（Aspect Ratio 等）
# ============================================================

class LightDropdown(_DropdownPanelBase):
    """轻量下拉组件，36px 选项行 + 可选 Badge，无描述"""

    _ROW_HEIGHT = 36
    _PANEL_RADIUS = 6
    _OPEN_DURATION = 160
    _CLOSE_DURATION = 110

    def __init__(self, panel_width: int = 160, parent: QWidget | None = None):
        super().__init__(panel_width, parent)
        self._trigger.setFixedHeight(28)

    def add_option(self, value: str, label: str, badge: str = "") -> None:
        row = LightOptionRow(value, label, badge, self._panel)
        self._register_option(row)

    def _apply_style(self) -> None:
        from photocrop.ui.theme import theme
        c = theme.colors

        self._trigger.setStyleSheet(
            f"QPushButton {{"
            f" background: {c.surface}; color: {c.text};"
            f" border: 1px solid {c.border}; border-radius: 4px;"
            f" padding: 0 24px 0 8px;"
            f" font-family: {FONT_FAMILY}; font-size: {FontSize.BODY}px;"
            f" font-weight: {FontWeight.REGULAR};"
            f" text-align: left;"
            f"}}"
            f"QPushButton:hover {{ border-color: {c.border_strong}; }}"
            f"QPushButton:pressed {{ border-color: {c.accent}; }}"
        )

        r = self._PANEL_RADIUS
        self._panel.setStyleSheet(
            f"QFrame {{"
            f" background: {c.surface};"
            f" border: 1px solid {c.border_strong};"
            f" border-radius: {r}px;"
            f"}}"
        )

        self._update_arrow_icon()

    def _row_value(self, row: QWidget) -> str:
        return row._value  # type: ignore[attr-defined]

    def _set_row_selected(self, row: QWidget, selected: bool) -> None:
        row.set_selected(selected)  # type: ignore[attr-defined]

    def _row_label_text(self, row: QWidget) -> str:
        return row._lbl.text()  # type: ignore[attr-defined]
