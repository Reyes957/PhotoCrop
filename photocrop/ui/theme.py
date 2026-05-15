"""
Theme — 全局主题管理（Light / Dark 双模式）

参考设计规范（photocrop_design_spec.md）：
- Light 模式：#F5F5F5 面板、#E8E8E8 画布、#000000 强调
- Dark 模式：#141414 面板、#1A1A1A 画布、#FFFFFF 强调
- 切换动画：350ms cubic-bezier(0.4, 0, 0.2, 1)
- 字体系统：7 级字号 + 4 级字重
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation, Signal
from PySide6.QtGui import QColor

# ============================================================
# 字体系统（设计规范 §3）
# ============================================================

# 不硬编码 "SF Pro Text"（Qt 字体数据库无法识别，会打印警告）。
# macOS 系统上 "Helvetica Neue" 是 Qt 能正确解析的系统等效字体。
FONT_FAMILY = '"Helvetica Neue", Helvetica, Arial'
FONT_DISPLAY = FONT_FAMILY


class FontSize:
    """字号常量（px）"""
    BRAND = 15        # Toolbar Logo
    BRAND_LARGE = 28  # Empty State Logo
    BODY = 13         # 按钮文字、表单值
    SMALL = 12        # 输入框、列表项文件名
    LABEL = 11        # Header 标签、状态栏、副标题
    TINY = 10         # PDF 页面标记、缩略图标签
    MICRO = 9         # 旋转角度显示


class FontWeight:
    """字重常量"""
    LIGHT = 200       # "Photo" in Empty State
    REGULAR = 400     # 默认
    MEDIUM = 500      # 列表项文件名
    SEMIBOLD = 600    # Header 标签、"Crop" 文字


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
    photo_slot: str      # 照片占位


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
)

# ============================================================
# Dark 模式
# ============================================================

DARK = ThemeColors(
    bg="#141414",
    canvas_bg="#1A1A1A",
    surface="#1E1E1E",
    text="#F0F0F0",
    text_secondary="#909090",
    text_disabled="#606060",
    border="#333333",
    border_strong="#4A4A4A",
    accent="#FFFFFF",
    accent_hover="#E0E0E0",
    danger="#FF5555",
    selected_bg="#2A2A2A",
    hover_bg="rgba(255, 255, 255, 0.05)",
    toolbar_float="rgba(0, 0, 0, 0.75)",
    page_bg="#2A2825",
    photo_slot="#3A3835",
)


# ============================================================
# ThemeTransition — 主题切换过渡动画管理器
# ============================================================

class ThemeTransition:
    """主题切换过渡动画

    350ms cubic-bezier(0.4, 0, 0.2, 1) 过渡所有颜色属性。
    优先级：大面积背景（画布、面板）必须做过渡；文字颜色可瞬间切换。
    """

    DURATION = 350  # ms

    @staticmethod
    def _lerp_color(c1: str, c2: str, t: float) -> str:
        """在两个颜色之间线性插值"""
        color1 = QColor(c1)
        color2 = QColor(c2)
        r = int(color1.red() + (color2.red() - color1.red()) * t)
        g = int(color1.green() + (color2.green() - color1.green()) * t)
        b = int(color1.blue() + (color2.blue() - color1.blue()) * t)
        a = int(color1.alpha() + (color2.alpha() - color1.alpha()) * t)
        return f"rgba({r}, {g}, {b}, {a})" if a < 255 else f"#{r:02x}{g:02x}{b:02x}"

    @classmethod
    def interpolate_colors(cls, start: ThemeColors, end: ThemeColors, t: float) -> ThemeColors:
        """在两个 ThemeColors 之间插值"""
        return ThemeColors(
            bg=cls._lerp_color(start.bg, end.bg, t),
            canvas_bg=cls._lerp_color(start.canvas_bg, end.canvas_bg, t),
            surface=cls._lerp_color(start.surface, end.surface, t),
            text=cls._lerp_color(start.text, end.text, t),
            text_secondary=cls._lerp_color(start.text_secondary, end.text_secondary, t),
            text_disabled=cls._lerp_color(start.text_disabled, end.text_disabled, t),
            border=cls._lerp_color(start.border, end.border, t),
            border_strong=cls._lerp_color(start.border_strong, end.border_strong, t),
            accent=cls._lerp_color(start.accent, end.accent, t),
            accent_hover=cls._lerp_color(start.accent_hover, end.accent_hover, t),
            danger=cls._lerp_color(start.danger, end.danger, t),
            selected_bg=cls._lerp_color(start.selected_bg, end.selected_bg, t),
            hover_bg=cls._lerp_color(start.hover_bg, end.hover_bg, t),
            toolbar_float=cls._lerp_color(start.toolbar_float, end.toolbar_float, t),
            page_bg=cls._lerp_color(start.page_bg, end.page_bg, t),
            photo_slot=cls._lerp_color(start.photo_slot, end.photo_slot, t),
        )


# ============================================================
# ThemeManager 单例
# ============================================================

class ThemeManager(QObject):
    """全局主题管理器

    用法：
        from photocrop.ui.theme import theme
        c = theme.colors  # 当前颜色集
        theme.toggle()    # 切换 Light ↔ Dark（带 350ms 过渡动画）
    """

    theme_changed = Signal(ThemeColors)

    def __init__(self) -> None:
        super().__init__()
        self._mode = "light"  # "light" | "dark"
        self._transition_anim: QVariantAnimation | None = None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def colors(self) -> ThemeColors:
        return LIGHT if self._mode == "light" else DARK

    def toggle(self) -> ThemeColors:
        """切换主题（带 350ms 过渡动画），返回新颜色集"""
        new_mode = "dark" if self._mode == "light" else "light"
        return self.set_mode(new_mode, animate=True)

    def set_mode(self, mode: str, animate: bool = True) -> ThemeColors:
        """设置指定主题模式"""
        if mode not in ("light", "dark"):
            mode = "light"
        if mode == self._mode:
            return self.colors

        start_colors = self.colors
        self._mode = mode
        end_colors = self.colors

        if animate:
            self._animate_transition(start_colors, end_colors)
        else:
            self.theme_changed.emit(end_colors)

        return end_colors

    def _animate_transition(self, start: ThemeColors, end: ThemeColors) -> None:
        """执行 350ms 颜色过渡动画"""
        # 取消正在进行的过渡
        if self._transition_anim is not None:
            self._transition_anim.stop()

        anim = QVariantAnimation()
        anim.setDuration(ThemeTransition.DURATION)
        anim.setEasingCurve(QEasingCurve.Type.BezierSpline)
        # cubic-bezier(0.4, 0, 0.2, 1)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def on_value_changed(value):
            t = value
            interpolated = ThemeTransition.interpolate_colors(start, end, t)
            self.theme_changed.emit(interpolated)

        anim.valueChanged.connect(on_value_changed)
        anim.start()
        self._transition_anim = anim

    def generate_stylesheet(self) -> str:
        """生成全局 QSS 样式表（设计规范 §14）"""
        c = self.colors
        ff = FONT_FAMILY
        return f"""
/* === MainWindow === */
QMainWindow {{
    background-color: {c.bg};
}}

/* === QPushButton — 默认（toolbar 样式） === */
QPushButton {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 0 12px;
    font-family: {ff};
    font-size: {FontSize.BODY}px;
    font-weight: {FontWeight.REGULAR};
    min-height: 28px;
    letter-spacing: -0.2px;
}}
QPushButton:hover {{
    background-color: {c.hover_bg};
    border-color: {c.border_strong};
}}
QPushButton:pressed {{
    background-color: {c.selected_bg};
}}
QPushButton:disabled {{
    background-color: transparent;
    color: {c.text_disabled};
    border-color: {c.border};
    opacity: 0.5;
}}

/* === #bottomBar QPushButton — 底栏缩放按钮（更紧凑） === */
#bottomBar QPushButton {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 0 8px;
    font-size: {FontSize.LABEL}px;
    min-height: 28px;
    font-weight: {FontWeight.REGULAR};
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
    border-radius: 4px;
    padding: 0 12px;
    font-family: {ff};
    font-size: {FontSize.BODY}px;
    font-weight: {FontWeight.REGULAR};
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
    opacity: 0.5;
}}
QPushButton[toolbar="true"]:checked {{
    background-color: {c.selected_bg};
    color: {c.text};
    border-color: {c.border_strong};
    font-weight: {FontWeight.SEMIBOLD};
}}
QPushButton[toolbar="true"][iconOnly="true"] {{
    padding: 0;
}}

/* === QPushButton[secondary] — 次要描边按钮 === */
QPushButton[secondary="true"] {{
    background-color: transparent;
    color: {c.text};
    border: 1px solid {c.accent};
}}
QPushButton[secondary="true"]:hover {{
    background-color: {c.hover_bg};
}}

/* === QPushButton:checked — Toggle 选中态 === */
QPushButton:checked {{
    background-color: {c.selected_bg};
    color: {c.text};
    border-color: {c.border_strong};
    font-weight: {FontWeight.SEMIBOLD};
}}

/* === QPushButton[export_btn] — Export 按钮 === */
QPushButton[export_btn="true"] {{
    background-color: {c.accent};
    color: {"#FFFFFF" if self._mode == "light" else "#1A1A1A"};
    border: none;
    border-radius: 4px;
    padding: 1px 12px;
    font-weight: {FontWeight.MEDIUM};
    min-height: 28px;
    max-height: 28px;
    font-size: {FontSize.BODY}px;
}}
QPushButton[export_btn="true"]:hover {{
    background-color: {c.accent_hover};
}}
QPushButton[export_btn="true"]:disabled {{
    background-color: {c.accent};
    color: {"#FFFFFF" if self._mode == "light" else "#1A1A1A"};
    opacity: 0.5;
}}

/* === QLabel === */
QLabel {{
    font-family: {ff};
    font-size: {FontSize.BODY}px;
    color: {c.text};
    letter-spacing: -0.2px;
}}
QLabel[pageInfo="true"] {{
    color: {c.text_secondary};
    font-size: {FontSize.BODY}px;
}}

/* === QStatusBar === */
QStatusBar {{
    background-color: {c.bg};
    border-top: 1px solid {c.border};
    font-family: {ff};
    font-size: {FontSize.SMALL}px;
    color: {c.text_secondary};
    padding: 4px 16px;
}}

/* === QToolTip === */
QToolTip {{
    background-color: {c.surface};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 6px;
    padding: 6px 10px;
    font-family: {ff};
    font-size: {FontSize.LABEL}px;
}}

/* === QMenu === */
QMenu {{
    background-color: {c.bg};
    color: {c.text};
    border: 1px solid {c.border_strong};
    border-radius: 8px;
    padding: 4px;
    font-family: {ff};
    font-size: {FontSize.SMALL}px;
}}
QMenu::item {{
    padding: 6px 16px;
    border-radius: 4px;
    min-height: 32px;
}}
QMenu::item:selected {{
    background-color: {c.hover_bg};
}}

/* === QSpinBox / QDoubleSpinBox === */
QSpinBox, QDoubleSpinBox {{
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 0 8px;
    font-family: {ff};
    font-size: {FontSize.SMALL}px;
    background: {c.surface};
    color: {c.text};
    min-height: 28px;
    max-height: 28px;
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
    border-radius: 4px;
    padding: 0px 28px 0px 8px;
    font-family: {ff};
    font-size: {FontSize.SMALL}px;
    background: {c.surface};
    color: {c.text};
    min-height: 28px;
    max-height: 28px;
}}
QComboBox:hover {{
    border-color: {c.border_strong};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.bg};
    color: {c.text};
    border: none;
    padding: 4px;
    outline: none;
    font-family: {ff};
    font-size: {FontSize.SMALL}px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    min-height: 28px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 2px;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {c.selected_bg};
    border-left: 3px solid {c.accent};
    font-weight: 600;
    padding-left: 9px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {c.hover_bg};
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
    min-height: 20px;
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
