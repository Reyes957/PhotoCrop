"""
icons.py — SVG 图标辅助模块

提供 get_icon() 函数，用 QSvgRenderer 加载 SVG 并注入颜色，
返回主题感知的 QIcon。内置缓存避免重复渲染。

用法：
    from photocrop.ui.icons import get_icon
    btn.setIcon(get_icon("sun", "#000000"))
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICON_DIR = Path(__file__).parent / "icons"
_cache: dict[tuple[str, str], QIcon] = {}


def get_icon(name: str, color: str) -> QIcon:
    """加载 SVG 图标，注入颜色，返回 QIcon。

    Args:
        name: 图标名（不含扩展名），如 "sun", "chevron-left"
        color: CSS 颜色字符串，如 "#000000", "#F0F0F0"

    Returns:
        渲染好的 QIcon，或空 QIcon（文件不存在时）
    """
    cache_key = (name, color)
    if cache_key in _cache:
        return _cache[cache_key]

    svg_path = _ICON_DIR / f"{name}.svg"
    if not svg_path.exists():
        return QIcon()

    svg_data = svg_path.read_text()
    svg_data = svg_data.replace("currentColor", color)

    svg_bytes = QByteArray(svg_data.encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)
    if not renderer.isValid():
        return QIcon()

    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    icon = QIcon(pixmap)
    _cache[cache_key] = icon
    return icon


def clear_cache() -> None:
    """清空图标缓存（主题切换时调用）。"""
    _cache.clear()
