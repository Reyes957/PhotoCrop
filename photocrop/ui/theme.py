"""
Theme — 全局主题管理（Light / Dark 双模式）

参考设计：HTML 参考页面的颜色系统
- Light 模式：#F5F5F5 面板、#E8E8E8 画布、#000000 强调
- Dark 模式：#141414 面板、#1A1A1A 画布、#FFFFFF 强调
- 切换动画：350ms cubic-bezier(0.4, 0, 0.2, 1)
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class ThemeColors:
    """颜色 token 集合"""
    # 背景
    bg: str              # 面板/工具栏/底栏背景
    canvas_bg: str       # 画布背景
    surface: str         # 卡片、输入框背景

    # 文字
    text: str            # 主文字
    text_secondary: str  # 次要文字
    text_disabled: str   # 禁用态

    # 边框
    border: str          # 分割线、输入框边框
    border_strong: str   # 滚动条、hover 边框

    # 强调
    accent: str          # 主按钮、选中态
    accent_hover: str    # 按钮 hover
    danger: str          # 删除

    # 半透明
    selected_bg: str     # 列表选中背景
    hover_bg: str        # 列表 hover 背景
    toolbar_float: str   # 裁剪框工具栏浮层

    # 画布特殊
    page_bg: str         # 扫描页背景
    photo_slot: str      # 照片占位外层
    photo_inner: str     # 照片占位内层


# ============================================================
# Light 模式（默认）
# ============================================================

LIGHT = ThemeColors(
    bg="#F5F5F5",
    canvas_bg="#E8E8E8",
    surface="#FFFFFF",
    text="#1A1A1A",
    text_secondary="#666666",
    text_disabled="#AAAAAA",
    border="#E0E0E0",
    border_strong="#CCCCCC",
    accent="#000000",
    accent_hover="#333333",
    danger="#CC0000",
    selected_bg="rgba(0, 0, 0, 0.08)",
    hover_bg="rgba(0, 0, 0, 0.03)",
    toolbar_float="rgba(0, 0, 0, 0.6)",
    page_bg="#F0EDE8",
    photo_slot="#D8D4CF",
    photo_inner="#C8C4BF",
)

# ============================================================
# Dark 模式
# ============================================================

DARK = ThemeColors(
    bg="#141414",
    canvas_bg="#1A1A1A",
    surface="#1E1E1E",
    text="#F0F0F0",
    text_secondary="#808080",
    text_disabled="#606060",
    border="#2A2A2A",
    border_strong="#404040",
    accent="#FFFFFF",
    accent_hover="#E0E0E0",
    danger="#FF5555",
    selected_bg="#2A2A2A",
    hover_bg="rgba(255, 255, 255, 0.05)",
    toolbar_float="rgba(0, 0, 0, 0.75)",
    page_bg="#2A2825",
    photo_slot="#3A3835",
    photo_inner="#454340",
)


# ============================================================
# ThemeManager 单例
# ============================================================

class ThemeManager(QObject):
    """全局主题管理器

    用法：
        from photocrop.ui.theme import theme
        c = theme.colors  # 当前颜色集
        theme.toggle()    # 切换 Light ↔ Dark
    """

    theme_changed = Signal(ThemeColors)

    def __init__(self) -> None:
        super().__init__()
        self._mode = "light"  # "light" | "dark"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def colors(self) -> ThemeColors:
        return LIGHT if self._mode == "light" else DARK

    def toggle(self) -> ThemeColors:
        """切换主题，返回新颜色集"""
        self._mode = "dark" if self._mode == "light" else "light"
        c = self.colors
        self.theme_changed.emit(c)
        return c

    def set_mode(self, mode: str) -> ThemeColors:
        """设置指定主题模式"""
        if mode not in ("light", "dark"):
            mode = "light"
        if mode == self._mode:
            return self.colors
        self._mode = mode
        c = self.colors
        self.theme_changed.emit(c)
        return c

    def generate_stylesheet(self) -> str:
        """生成全局 QSS 样式表"""
        c = self.colors
        return f"""
/* === MainWindow === */
QMainWindow {{
    background-color: {c.bg};
}}

/* === QPushButton — 默认（primary 黑底） === */
QPushButton {{
    background-color: {c.accent};
    color: {c.bg};
    border: none;
    border-radius: 6px;
    padding: 0 14px;
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 13px;
    font-weight: 400;
    min-height: 28px;
    letter-spacing: -0.2px;
}}
QPushButton:hover {{
    background-color: {c.accent_hover};
}}
QPushButton:pressed {{
    background-color: {c.accent};
}}
QPushButton:disabled {{
    background-color: {c.border};
    color: {c.text_disabled};
}}

/* === #bottomBar QPushButton — 底栏缩放按钮（更紧凑） === */
#bottomBar QPushButton {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 0 8px;
    font-size: 11px;
    min-height: 20px;
    font-weight: 400;
}}
#bottomBar QPushButton:hover {{
    background-color: {c.hover_bg};
    border-color: {c.border_strong};
}}
#bottomBar QPushButton:pressed {{
    background-color: {c.selected_bg};
}}

/* === QPushButton[toolbar] — 工具栏操作按钮 === */
QPushButton[toolbar="true"] {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 0 14px;
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 13px;
    font-weight: 400;
    min-height: 28px;
}}
QPushButton[toolbar="true"]:hover {{
    background-color: {c.hover_bg};
    border-color: {c.border_strong};
}}
QPushButton[toolbar="true"]:pressed {{
    background-color: {c.selected_bg};
}}
QPushButton[toolbar="true"]:disabled {{
    background-color: transparent;
    color: {c.text_disabled};
    border-color: {c.border};
    opacity: 0.35;
}}
QPushButton[toolbar="true"]:checked {{
    background-color: {c.selected_bg};
    color: {c.text};
    border-color: {c.border_strong};
    font-weight: 600;
}}
QPushButton[toolbar="true"][iconOnly="true"] {{
    padding: 0;
}}

/* === QPushButton[secondary] — 次要描边按钮 === */
QPushButton[secondary="true"] {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.text};
}}
QPushButton[secondary="true"]:hover {{
    background-color: {c.hover_bg};
}}

/* === QPushButton:checked — Toggle 选中态 === */
QPushButton:checked {{
    background-color: {c.accent};
    color: {c.surface};
    border-color: transparent;
}}

/* === QPushButton[export_btn] — Export 按钮 === */
QPushButton[export_btn="true"] {{
    background-color: {c.accent};
    color: {c.surface};
    border: none;
    border-radius: 6px;
    padding: 0 20px;
    font-weight: 500;
    min-height: 28px;
}}
QPushButton[export_btn="true"]:hover {{
    background-color: {c.accent_hover};
}}

/* === QLabel === */
QLabel {{
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: {c.text};
    letter-spacing: -0.2px;
}}
QLabel[pageInfo="true"] {{
    color: {c.text_secondary};
    font-size: 13px;
}}

/* === QStatusBar === */
QStatusBar {{
    background-color: {c.bg};
    border-top: 1px solid {c.border};
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 12px;
    color: {c.text_secondary};
    padding: 4px 16px;
}}

/* === QMenu === */
QMenu {{
    background-color: {c.bg};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 6px;
    padding: 4px;
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 12px;
}}
QMenu::item {{
    padding: 6px 16px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {c.hover_bg};
}}

/* === QSpinBox / QDoubleSpinBox === */
QSpinBox, QDoubleSpinBox {{
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 4px 6px;
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 12px;
    background: {c.surface};
    color: {c.text};
    min-height: 28px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c.border_strong};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
    background: transparent;
}}

/* === QComboBox === */
QComboBox {{
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 3px 28px 3px 10px;
    font-family: SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif;
    font-size: 12px;
    background: {c.surface};
    color: {c.text};
    min-height: 28px;
}}
QComboBox:hover {{
    border-color: {c.border_strong};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid {c.border};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.surface};
    color: {c.text};
    selection-background-color: {c.selected_bg};
    selection-color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px;
    border-radius: 4px;
    min-height: 28px;
    border: none;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {c.selected_bg};
    color: {c.text};
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {c.hover_bg};
    color: {c.text};
}}

/* === QScrollArea / QScrollBar === */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical {{
    width: 4px;
    background: transparent;
}}
QScrollBar::handle:vertical {{
    background: {c.border_strong};
    border-radius: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.text_disabled};
}}

/* === QProgressDialog === */
QProgressDialog {{
    background-color: {c.surface};
    color: {c.text};
}}
"""


# 模块级单例
theme = ThemeManager()
