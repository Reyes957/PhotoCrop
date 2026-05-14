"""
Toast — 底部浮动通知组件（设计规范 §9）

规范：
- 位置: 主窗口底部中央（底部状态栏上方 8px）
- 样式: 背景 rgba(0,0,0,0.8) + backdrop-blur, 圆角 8px
- 动画: 从下方滑入 300ms, 停留 2.5s, 向上淡出 200ms
- 队列: 最多同时显示 3 个
- 类型: info/success(黑色), warning(amber), error(red)
- 关闭: X 按钮
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from photocrop.ui.icons import get_icon
from photocrop.ui.theme import FONT_FAMILY, FontSize

# 类型颜色映射（设计规范 §9）
_TYPE_COLORS = {
    "info": "rgba(0, 0, 0, 0.8)",
    "success": "rgba(0, 0, 0, 0.8)",
    "warning": "rgba(180, 120, 0, 0.9)",
    "error": "rgba(180, 30, 30, 0.9)",
}

# 类型图标映射
_TYPE_ICONS = {
    "info": "eye",
    "success": "eye",
    "warning": "scan-eye",
    "error": "x",
}


# 每个父窗口独立的 Toast 实例列表（避免跨窗口共享）
_TOAST_LISTS: dict[int, list[Toast]] = {}


def _get_toast_list(parent: QWidget) -> list[Toast]:
    """获取指定父窗口的 Toast 列表（按 parent id 隔离）"""
    pid = id(parent)
    if pid not in _TOAST_LISTS:
        _TOAST_LISTS[pid] = []
    return _TOAST_LISTS[pid]


class Toast(QWidget):
    """单条 Toast 通知"""

    MAX_VISIBLE = 3

    def __init__(self, message: str, duration: int = 2500,
                 toast_type: str = "info",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._duration = duration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        bg = _TYPE_COLORS.get(toast_type, _TYPE_COLORS["info"])
        self.setStyleSheet(
            f"Toast {{ background: {bg}; border-radius: 8px; }}"
        )

        layout = QHBoxLayout(self)
        # 设计规范：padding 8px 16px（上下8 左右16）
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # 图标（16px, 白色, opacity 0.8）
        icon_name = _TYPE_ICONS.get(toast_type, "eye")
        icon_label = QLabel()
        icon_label.setFixedSize(16, 16)
        icon_pixmap = get_icon(icon_name, "#FFFFFF").pixmap(16, 16)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setStyleSheet("background: transparent; opacity: 0.8;")
        layout.addWidget(icon_label)

        label = QLabel(message)
        label.setStyleSheet(
            f"color: white; font-family: {FONT_FAMILY}; "
            f"font-size: {FontSize.BODY}px; background: transparent;"
        )
        layout.addWidget(label)

        # 关闭 X 按钮（12px, opacity 0.6）
        btn_close = QPushButton("×")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.6); background: transparent; "
            "border: none; font-size: 12px; }"
            "QPushButton:hover { color: white; }"
        )
        btn_close.clicked.connect(self._close_immediate)
        layout.addWidget(btn_close)

        self.adjustSize()
        self.setFixedHeight(36)
        self.setMaximumWidth(400)

    def _close_immediate(self) -> None:
        """用户点击关闭"""
        parent = self.parentWidget()
        if parent:
            toasts = _get_toast_list(parent)
            if self in toasts:
                toasts.remove(self)
        self.close()

    def show_at_bottom(self, parent: QWidget) -> None:
        """在父窗口底部中央显示（设计规范：Bottom Bar 上方 8px）"""
        toasts = _get_toast_list(parent)
        while len(toasts) >= Toast.MAX_VISIBLE:
            oldest = toasts.pop(0)
            oldest.close()

        toasts.append(self)

        pw = parent.width()
        ph = parent.height()
        sw = self.width()
        x = (pw - sw) // 2
        # Bottom Bar 36px + 8px 间距 + 堆叠偏移
        y = ph - 44 - 8 - len(toasts) * 44
        self.move(x, y)
        self.show()

        # 入场动画：translateY(20px)→0 + opacity 0→1, 300ms
        start_pos = self.pos() + QPoint(0, 20)
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start_pos)
        anim.setEndValue(self.pos())
        anim.start()
        self._entry_anim = anim

        QTimer.singleShot(self._duration, self._fade_out)

    def _fade_out(self) -> None:
        """淡出动画（200ms: translateY 0→-10, opacity 1→0）"""
        parent = self.parentWidget()
        if parent:
            toasts = _get_toast_list(parent)
            if self not in toasts:
                return
            toasts.remove(self)
        else:
            return

        end_pos = self.pos() + QPoint(0, -10)
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(end_pos)
        anim.start()
        anim.finished.connect(self.close)
        self._exit_anim = anim


def show_toast(message: str, parent: QWidget,
               duration: int = 2500, toast_type: str = "info") -> None:
    """便捷函数：显示一条 Toast"""
    toast = Toast(message, duration, toast_type, parent)
    toast.show_at_bottom(parent)
