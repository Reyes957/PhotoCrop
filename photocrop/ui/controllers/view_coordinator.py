"""
ViewCoordinator — 视图切换协调器

管理 Empty / Grid / Single 三种视图的切换，维护当前视图状态，
通过 AppState 通知其他组件视图变化。

设计规范 §10 动画 2：视图切换
- 退出：opacity 1→0，200ms
- 进入：opacity 0→1，250ms
- 缓动：cubic-bezier(0.4, 0, 0.2, 1)
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget

from photocrop.ui.state import AppState


class ViewCoordinator(QObject):
    """视图协调器 — 管理 Empty / Grid / Single 三种视图的切换"""

    view_changed = Signal(int)  # 0=Empty, 1=Grid, 2=Single

    _VIEW_EMPTY = 0
    _VIEW_GRID = 1
    _VIEW_SINGLE = 2

    def __init__(self, app_state: AppState, stack: QStackedWidget,
                 btn_grid: object, btn_single: object) -> None:
        super().__init__()
        self._state = app_state
        self._stack = stack
        self._btn_grid = btn_grid
        self._btn_single = btn_single
        self._current = self._VIEW_EMPTY
        self._anims: list = []  # 防止 GC 回收
        self._switching = False  # 防止动画期间重复触发

        # 为每个页面添加 opacity 效果
        self._effects: list[QGraphicsOpacityEffect] = []
        for i in range(stack.count()):
            page = stack.widget(i)
            eff = QGraphicsOpacityEffect(page)
            eff.setOpacity(1.0)
            page.setGraphicsEffect(eff)
            self._effects.append(eff)

    def switch_to(self, mode: int) -> None:
        """切换到指定视图（带 fade 动画）"""
        if mode == self._current or self._switching:
            return

        self._switching = True
        old_mode = self._current
        self._current = mode
        self._anims.clear()

        # 退出动画：opacity 1→0, 200ms
        old_eff = self._effects[old_mode]
        fade_out = QPropertyAnimation(old_eff, b"opacity")
        fade_out.setDuration(200)
        fade_out.setEasingCurve(QEasingCurve.Type.BezierSpline)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        self._anims.append(fade_out)

        def on_fade_out_done():
            # 清除旧页面的 opacity 效果（避免缓存残留）
            old_eff.setOpacity(1.0)
            page_old = self._stack.widget(old_mode)
            page_old.setGraphicsEffect(None)

            # 切换页面
            self._stack.setCurrentIndex(mode)
            self._state.set_view_mode(mode)
            self.view_changed.emit(mode)
            self._btn_grid.setChecked(mode == self._VIEW_GRID)
            self._btn_single.setChecked(mode == self._VIEW_SINGLE)

            # 为新页面创建 fresh opacity effect
            page_new = self._stack.widget(mode)
            new_eff = QGraphicsOpacityEffect(page_new)
            new_eff.setOpacity(0.0)
            page_new.setGraphicsEffect(new_eff)
            self._effects[mode] = new_eff

            # 进入动画：opacity 0→1, 250ms
            fade_in = QPropertyAnimation(new_eff, b"opacity")
            fade_in.setDuration(250)
            fade_in.setEasingCurve(QEasingCurve.Type.BezierSpline)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)

            def on_fade_in_done():
                # 动画结束后清除效果，让页面直接渲染（避免主题切换时缓存问题）
                new_eff.setOpacity(1.0)
                page_new.setGraphicsEffect(None)
                # 重新创建 effect 供下次使用
                fresh_eff = QGraphicsOpacityEffect(page_new)
                fresh_eff.setOpacity(1.0)
                page_new.setGraphicsEffect(fresh_eff)
                self._effects[mode] = fresh_eff
                self._switching = False

            fade_in.finished.connect(on_fade_in_done)
            fade_in.start()
            self._anims.append(fade_in)

        fade_out.finished.connect(on_fade_out_done)
        fade_out.start()

    def show_empty(self) -> None:
        self.switch_to(self._VIEW_EMPTY)

    def show_grid(self) -> None:
        self.switch_to(self._VIEW_GRID)

    def show_single(self) -> None:
        self.switch_to(self._VIEW_SINGLE)

    @property
    def current(self) -> int:
        return self._current

    @property
    def is_empty(self) -> bool:
        return self._current == self._VIEW_EMPTY

    @property
    def is_grid(self) -> bool:
        return self._current == self._VIEW_GRID

    @property
    def is_single(self) -> bool:
        return self._current == self._VIEW_SINGLE
