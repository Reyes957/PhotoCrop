"""
CustomDropdown — 沿触发器向下延展的下拉菜单

替代 Qt 默认的浮窗式 QComboBox 弹出，实现 Windows 字体选择器风格：
- 从触发器底部向下延伸展开（不是悬浮弹窗）
- 打开/关闭带最大高度动画（200ms ease-out）
- 选中项显示左侧竖线指示器 + 加粗文字
- 无边框、背景与面板一致

用法：
    combo = QComboBox()
    combo.addItems(["A", "B", "C"])
    dropdown = CustomDropdown(combo, parent=main_window)
    # 主题切换时调 dropdown.set_theme(colors)
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from photocrop.ui.theme import FONT_FAMILY, FontSize


class CustomDropdown(QWidget):
    """沿触发器向下延展的下拉菜单，带动画"""

    # 动画参数
    _ANIM_DURATION = 200   # ms
    _MAX_VISIBLE = 8       # 最大可见行数（超出则滚动）

    def __init__(self, combo, parent: QWidget | None = None):
        super().__init__(parent)
        self._combo = combo
        self._is_open = False

        # 隐藏 Qt 默认弹出
        combo.view().setWindowFlags(Qt.WindowType.FramelessWindowHint)
        combo.view().hide()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        layout.addWidget(self._list)

        for i in range(combo.count()):
            self._list.addItem(combo.itemText(i))

        self._list.itemClicked.connect(self._on_item_clicked)

        # 动画
        self._open_anim: QPropertyAnimation | None = None

        self.hide()
        self._apply_style()

    def _apply_style(self) -> None:
        """应用 QSS 样式"""
        from photocrop.ui.theme import theme
        c = theme.colors
        self.setStyleSheet(
            f"CustomDropdown {{ background: {c.bg}; border: none; }}"
        )
        self._list.setStyleSheet(
            f"QListWidget {{ background: {c.bg}; color: {c.text};"
            f" border: none; outline: none; padding: 4px;"
            f" font-family: {FONT_FAMILY}; font-size: {FontSize.SMALL}px; }}"
            f"QListWidget::item {{ padding: 8px 12px; min-height: 28px;"
            f" border: none; border-left: 3px solid transparent;"
            f" border-radius: 2px; }}"
            f"QListWidget::item:selected {{ background: {c.selected_bg};"
            f" border-left: 3px solid {c.accent}; font-weight: 600;"
            f" padding-left: 9px; }}"
            f"QListWidget::item:hover {{ background: {c.hover_bg}; }}"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {c.border_strong};"
            f" border-radius: 2px; min-height: 20px; }}"
        )

    def set_theme(self, colors) -> None:
        """主题切换时更新样式"""
        self._apply_style()

    def _on_item_clicked(self, item) -> None:
        idx = self._list.row(item)
        self._combo.setCurrentIndex(idx)
        self.close_dropdown()
        self._combo.currentIndexChanged.emit(idx)

    def eventFilter(self, obj, event) -> bool:
        """点击下拉菜单外部时关闭"""
        if event.type() == QEvent.Type.MouseButtonPress:
            if self.isVisible():
                click_pos = event.globalPosition().toPoint()
                if not self.geometry().contains(click_pos):
                    self.close_dropdown()
        return False

    def _position_below_trigger(self) -> None:
        """将下拉菜单定位到触发器正下方"""
        parent = self.parentWidget()
        if not parent:
            return
        global_pos = self._combo.mapToGlobal(QPoint(0, self._combo.height()))
        local_pos = parent.mapFromGlobal(global_pos)
        self.move(local_pos)
        self.setFixedWidth(self._combo.width())

    def _calc_target_height(self) -> int:
        """计算展开后的目标高度"""
        row_h = 36  # 与 min-height: 28px + padding 匹配
        n = min(self._list.count(), self._MAX_VISIBLE)
        return n * row_h + 8  # +8 for padding

    def toggle(self) -> None:
        """切换下拉菜单的打开/关闭状态"""
        if self._is_open:
            self.close_dropdown()
        else:
            self.open_dropdown()

    def open_dropdown(self) -> None:
        """打开下拉菜单（带动画）"""
        if self._is_open:
            return
        self._is_open = True

        self._position_below_trigger()
        self._list.setCurrentRow(self._combo.currentIndex())

        target_h = self._calc_target_height()

        # 安装全局事件过滤器（点击外部关闭）
        QApplication.instance().installEventFilter(self)

        # 先显示（高度为 0），再启动展开动画
        self.setFixedHeight(0)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"maximumHeight")
        anim.setDuration(self._ANIM_DURATION)
        anim.setStartValue(0)
        anim.setEndValue(target_h)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        anim.finished.connect(lambda: self.setFixedHeight(target_h))
        self._open_anim = anim

    def close_dropdown(self) -> None:
        """关闭下拉菜单（带动画）"""
        if not self._is_open:
            return
        self._is_open = False

        QApplication.instance().removeEventFilter(self)

        current_h = self.height()

        anim = QPropertyAnimation(self, b"maximumHeight")
        anim.setDuration(self._ANIM_DURATION)
        anim.setStartValue(current_h)
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.start()
        anim.finished.connect(self.hide)
        self._open_anim = anim
