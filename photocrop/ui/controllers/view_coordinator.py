"""
ViewCoordinator — 视图切换协调器

管理 Empty / Grid / Single 三种视图的切换，维护当前视图状态，
通过 AppState 通知其他组件视图变化。

动画策略：截图覆盖法
- 切换前截取旧页面快照 → 创建覆盖层
- 立即切换 QStackedWidget 页面（新页面正常渲染）
- 覆盖层 opacity 1→0 淡出，露出下方新页面
- 避免在 QGraphicsView 上使用 QGraphicsOpacityEffect（会导致缓存残影）
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedWidget

from photocrop.ui.state import AppState


class ViewCoordinator(QObject):
    """视图协调器 — 管理 Empty / Grid / Single 三种视图的切换"""

    view_changed = Signal(int)  # 0=Empty, 1=Grid, 2=Single

    _VIEW_EMPTY = 0
    _VIEW_GRID = 1
    _VIEW_SINGLE = 2

    # 动画时长（ms）
    _FADE_DURATION = 220

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
        self._overlay: QLabel | None = None

    def switch_to(self, mode: int) -> None:
        """切换到指定视图（带 fade 动画）"""
        if mode == self._current or self._switching:
            return

        # 清理上一次可能残留的覆盖层
        if self._overlay is not None:
            self._overlay.hide()
            self._overlay.setGraphicsEffect(None)
            self._overlay.deleteLater()
            self._overlay = None

        self._switching = True
        old_mode = self._current
        self._current = mode
        self._anims.clear()

        # 1) 截取旧页面快照
        old_page = self._stack.widget(old_mode)
        snapshot = old_page.grab()

        # 2) 创建覆盖层（叠在 stacked widget 上方）
        overlay = QLabel(self._stack.parent())
        overlay.setPixmap(snapshot)
        overlay.setGeometry(self._stack.geometry())
        overlay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.show()
        overlay.raise_()
        self._overlay = overlay

        # 3) 立即切换页面（新页面在覆盖层下方正常渲染）
        self._stack.setCurrentIndex(mode)
        self._state.set_view_mode(mode)
        self.view_changed.emit(mode)
        self._btn_grid.setChecked(mode == self._VIEW_GRID)
        self._btn_single.setChecked(mode == self._VIEW_SINGLE)

        # 4) 覆盖层淡出动画 → 露出新页面
        eff = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(eff)

        fade = QPropertyAnimation(eff, b"opacity")
        fade.setDuration(self._FADE_DURATION)
        fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        self._anims.append(fade)

        def on_done():
            overlay.hide()
            overlay.setGraphicsEffect(None)
            overlay.deleteLater()
            self._overlay = None
            self._switching = False

        fade.finished.connect(on_done)
        fade.start()

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
