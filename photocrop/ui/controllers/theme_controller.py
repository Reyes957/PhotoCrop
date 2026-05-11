"""
ThemeController — 主题切换控制器

将主题切换逻辑从 MainWindow 中剥离。theme.py 中的 `theme` 单例继续保留
（供全局使用），但 ThemeController 负责管理订阅者列表和批量通知。

订阅者模式让新组件自动获得主题支持，无需 MainWindow 手动遍历更新。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject

from photocrop.ui.theme import ThemeColors, theme


class ThemeController(QObject):
    """主题控制器 — 管理主题切换和组件颜色分发

    允许 UI 组件订阅主题变化，当主题切换时自动收到通知。
    这比 MainWindow 手动遍历所有子组件更新颜色更可靠。

    用法：
        ctrl = ThemeController()
        ctrl.subscribe(lambda c: my_widget.set_theme_colors(c))
        ctrl.toggle()  # 切换主题并通知所有订阅者
    """

    def __init__(self) -> None:
        super().__init__()
        self._listeners: list[Callable[[ThemeColors], None]] = []

    def subscribe(self, callback: Callable[[ThemeColors], None]) -> None:
        """订阅主题变化通知（同一回调不会重复添加）"""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[ThemeColors], None]) -> None:
        """取消订阅"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def toggle(self) -> ThemeColors:
        """切换 Light/Dark 主题，并通知所有订阅者

        Returns:
            切换后的 ThemeColors
        """
        colors = theme.toggle()
        for cb in self._listeners:
            cb(colors)
        return colors

    def apply(self, colors: ThemeColors | None = None) -> ThemeColors:
        """强制应用当前主题（或指定主题），通知所有订阅者

        用于初始化时强制刷新所有已注册组件的颜色。

        Args:
            colors: 指定颜色集，None 则使用当前主题

        Returns:
            实际应用的 ThemeColors
        """
        c = colors or theme.colors
        for cb in self._listeners:
            cb(c)
        return c

    @property
    def colors(self) -> ThemeColors:
        """当前主题颜色集"""
        return theme.colors

    @property
    def mode(self) -> str:
        """当前主题模式 ('light' / 'dark')"""
        return theme.mode
