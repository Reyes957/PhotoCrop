"""
ViewCoordinator — 视图切换协调器

管理 Empty / Grid / Single 三种视图的切换，维护当前视图状态，
通过 AppState 通知其他组件视图变化。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget

from photocrop.ui.state import AppState


class ViewCoordinator(QObject):
    """视图协调器 — 管理 Empty / Grid / Single 三种视图的切换

    职责：
    - 维护当前视图状态
    - 切换视图时同步更新按钮状态
    - 通过 AppState 通知其他组件视图变化
    """

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

    def switch_to(self, mode: int) -> None:
        """切换到指定视图"""
        if mode == self._current:
            return
        self._current = mode
        self._stack.setCurrentIndex(mode)
        self._state.set_view_mode(mode)
        self.view_changed.emit(mode)

        # 同步按钮选中状态
        self._btn_grid.setChecked(mode == self._VIEW_GRID)
        self._btn_single.setChecked(mode == self._VIEW_SINGLE)

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
