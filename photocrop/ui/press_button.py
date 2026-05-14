"""
PressButton — 支持按下缩放动画的 QPushButton

设计规范 §10 动画 8：按钮按下反馈（80ms）scale 0.97

实现方式：重写 paintEvent，在 QPainter 上应用 scale 变换后
调用 style().drawControl() 绘制标准按钮外观。
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton


class PressButton(QPushButton):
    """按下时有 scale(0.97) 缩放动画的按钮"""

    _PRESS_SCALE = 0.97
    _DURATION = 80  # ms

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scale_val = 1.0
        self._anim: QPropertyAnimation | None = None

    def _get_scale(self) -> float:
        return self._scale_val

    def _set_scale(self, val: float) -> None:
        self._scale_val = val
        self.update()

    scale_value = Property(float, _get_scale, _set_scale)

    def mousePressEvent(self, event) -> None:
        self._animate_to(self._PRESS_SCALE)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._animate_to(1.0)
        super().mouseReleaseEvent(event)

    def _animate_to(self, target: float) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"scale_value")
        anim.setDuration(self._DURATION)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self._scale_val)
        anim.setEndValue(target)
        anim.start()
        self._anim = anim

    def paintEvent(self, event) -> None:
        if abs(self._scale_val - 1.0) < 0.001:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 以控件中心为原点缩放
        center = self.rect().center()
        painter.translate(center)
        painter.scale(self._scale_val, self._scale_val)
        painter.translate(-center)

        # 使用 Qt 样式系统绘制标准按钮外观
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)
        painter.end()
