"""
Toast — 底部浮动通知组件

参考规范：
- 位置: 主窗口底部中央（底部状态栏上方 8px）
- 样式: 背景 rgba(0,0,0,0.8) + backdrop-blur, 圆角 8px
- 动画: 从下方滑入 300ms, 停留 2.5s, 向上淡出 200ms
- 队列: 最多同时显示 3 个
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)


class Toast(QWidget):
    """单条 Toast 通知"""

    _instances: list[Toast] = []  # 类级列表，管理所有活跃 Toast
    MAX_VISIBLE = 3

    def __init__(self, message: str, duration: int = 2500, parent: QWidget | None = None):
        super().__init__(parent)
        self._duration = duration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 样式
        self.setStyleSheet(
            "Toast { background: rgba(0, 0, 0, 0.8); border-radius: 8px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)

        label = QLabel(message)
        label.setStyleSheet(
            "color: white; font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;"
            "font-size: 13px; background: transparent;"
        )
        layout.addWidget(label)

        self.adjustSize()
        self.setFixedHeight(36)

    def show_at_bottom(self, parent: QWidget) -> None:
        """在父窗口底部中央显示"""
        # 管理队列：最多同时显示 3 个
        while len(Toast._instances) >= Toast.MAX_VISIBLE:
            oldest = Toast._instances.pop(0)
            oldest.close()

        Toast._instances.append(self)

        # 计算位置
        pw = parent.width()
        ph = parent.height()
        sw = self.width()
        x = (pw - sw) // 2
        y = ph - 80 - len(Toast._instances) * 44  # 状态栏上方，依次堆叠
        self.move(x, y)
        self.show()

        # 入场动画：从下方滑入
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.pos() + self.rect().center() - self.rect().center() + Qt.QPoint(0, 20))
        anim.setEndValue(self.pos())
        anim.start()
        self._entry_anim = anim

        # 自动消失
        QTimer.singleShot(self._duration, self._fade_out)

    def _fade_out(self) -> None:
        """淡出动画"""
        if self not in Toast._instances:
            return
        Toast._instances.remove(self)

        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(self.pos() - Qt.QPoint(0, 10))
        anim.start()
        anim.finished.connect(self.close)
        self._exit_anim = anim


def show_toast(message: str, parent: QWidget, duration: int = 2500) -> None:
    """便捷函数：显示一条 Toast"""
    toast = Toast(message, duration, parent)
    toast.show_at_bottom(parent)
