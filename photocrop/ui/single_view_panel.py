"""
SingleViewPanel — 单个裁剪框大图预览

双栏布局：
- 左侧：原图缩略 + 所有裁剪框轮廓（不可编辑）
- 右侧：选中裁剪框的提取大图
- 底部：页码 + 左右箭头切换
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photocrop.export.cropper import export_photo_to_memory
from photocrop.ui.icons import get_icon
from photocrop.ui.theme import FONT_FAMILY
from photocrop.ui.utils import pil_to_pixmap, pil_to_qimage
from photocrop.utils.crop_rect import CropRect


@dataclass
class _PanelColors:
    """面板内部颜色"""
    bg: str = "#E8E8E8"
    panel_bg: str = "#F5F5F5"
    text: str = "#1A1A1A"
    text_secondary: str = "#666666"
    accent: str = "#000000"
    hover_bg: str = "rgba(0, 0, 0, 0.03)"


class SingleViewPanel(QWidget):
    """单个裁剪框大图预览面板

    Signals:
        selection_changed(int): 选中的裁剪框索引变化
        exit_requested: 用户要求退出 Single View
    """

    selection_changed = Signal(int)
    exit_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._colors = _PanelColors()

        self._source_image: Image.Image | None = None
        self._crop_rects: list[CropRect] = []
        self._current_index: int = 0
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._rect_items: list[QGraphicsRectItem] = []

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧 Overview
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        self._lbl_overview = QLabel("OVERVIEW")
        left_layout.addWidget(self._lbl_overview)

        self._overview_scene = QGraphicsScene()
        self._overview_view = QGraphicsView(self._overview_scene)
        self._overview_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._overview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overview_view.setStyleSheet("border: none;")
        left_layout.addWidget(self._overview_view, 1)

        self._btn_exit = QPushButton("Return to Grid View")
        self._btn_exit.setProperty("secondary", "true")
        self._btn_exit.setToolTip("Return to Grid View")
        self._btn_exit.clicked.connect(self.exit_requested.emit)
        left_layout.addWidget(self._btn_exit)

        main_layout.addWidget(left_panel)

        # 右侧 Preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setText("Select a crop to view")
        right_layout.addWidget(self._preview_label, 1)

        # 底部导航
        nav_bar = QWidget()
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        self._btn_prev = QPushButton()
        self._btn_prev.setFixedSize(28, 28)
        self._btn_prev.setIconSize(QSize(14, 14))
        self._btn_prev.setToolTip("Previous crop")
        self._btn_prev.clicked.connect(self._go_prev)
        nav_layout.addWidget(self._btn_prev)

        self._lbl_page = QLabel("0 / 0")
        self._lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self._lbl_page, 1)

        self._btn_next = QPushButton()
        self._btn_next.setFixedSize(28, 28)
        self._btn_next.setIconSize(QSize(14, 14))
        self._btn_next.setToolTip("Next crop")
        self._btn_next.clicked.connect(self._go_next)
        nav_layout.addWidget(self._btn_next)

        right_layout.addWidget(nav_bar)
        main_layout.addWidget(right_panel, 1)

    def _apply_styles(self) -> None:
        """根据当前 _colors 应用所有样式"""
        c = self._colors
        self.setStyleSheet(f"background-color: {c.bg};")
        self._lbl_overview.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: 11px; font-weight: 600; letter-spacing: 0.5px;"
        )
        self._overview_view.setBackgroundBrush(QBrush(QColor(c.bg)))
        self._btn_exit.setStyleSheet(
            f"QPushButton {{"
            f"background-color: transparent; color: {c.accent}; "
            f"border: 1px solid {c.accent}; border-radius: 6px; "
            f"padding: 6px 12px; font-family: {FONT_FAMILY}; font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {c.hover_bg}; }}"
        )
        self._preview_label.setStyleSheet(
            f"background-color: {c.bg}; border-radius: 8px; "
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 14px;"
        )
        nav_bar_style = f"background-color: {c.panel_bg}; border-radius: 6px;"
        self._btn_prev.setIcon(get_icon("chevron-left", c.text))
        self._btn_prev.setStyleSheet(
            f"QPushButton {{ background-color: transparent; border: none; }}"
            f"QPushButton:hover {{ background-color: {c.hover_bg}; }}"
        )
        self._btn_next.setIcon(get_icon("chevron-right", c.text))
        self._btn_next.setStyleSheet(
            f"QPushButton {{ background-color: transparent; border: none; }}"
            f"QPushButton:hover {{ background-color: {c.hover_bg}; }}"
        )
        self._lbl_page.setStyleSheet(f"color: {c.text}; font-family: {FONT_FAMILY}; font-size: 13px;")
        # 导航条背景
        nav = self._lbl_page.parent()
        if nav:
            nav.setStyleSheet(nav_bar_style)

    def set_data(self, source_image: Image.Image, crop_rects: list[CropRect]) -> None:
        self._source_image = source_image
        self._crop_rects = list(crop_rects)
        self._current_index = 0
        self._update_overview()
        self._update_preview()
        self._update_nav()

    def select_crop(self, index: int) -> None:
        if 0 <= index < len(self._crop_rects):
            self._current_index = index
            self._update_preview()
            self._update_nav()
            self._update_overview_highlight()

    def _go_prev(self) -> None:
        if self._crop_rects and self._current_index > 0:
            self._current_index -= 1
            self._update_preview()
            self._update_nav()
            self._update_overview_highlight()
            self.selection_changed.emit(self._current_index)

    def _go_next(self) -> None:
        if self._crop_rects and self._current_index < len(self._crop_rects) - 1:
            self._current_index += 1
            self._update_preview()
            self._update_nav()
            self._update_overview_highlight()
            self.selection_changed.emit(self._current_index)

    def _update_overview(self) -> None:
        self._overview_scene.clear()
        self._rect_items.clear()

        if self._source_image is None:
            return

        qimage = pil_to_qimage(self._source_image)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item = self._overview_scene.addPixmap(pixmap)

        c = self._colors
        for i, rect in enumerate(self._crop_rects):
            is_current = (i == self._current_index)
            pen = QPen(
                QColor(c.accent) if is_current else QColor(c.text_secondary),
                2.0 if is_current else 1.0,
            )
            # 使用 QGraphicsRectItem + setRotation 显示旋转矩形
            from PySide6.QtWidgets import QGraphicsRectItem as QRI
            rect_item = QRI(
                rect.x - rect.width / 2,
                rect.y - rect.height / 2,
                rect.width,
                rect.height,
            )
            rect_item.setPen(pen)
            rect_item.setTransformOriginPoint(rect.width / 2, rect.height / 2)
            rect_item.setRotation(rect.rotation_angle)
            if is_current:
                c_accent = QColor(c.accent)
                c_accent.setAlpha(20)
                rect_item.setBrush(QBrush(c_accent))
            self._overview_scene.addItem(rect_item)
            self._rect_items.append(rect_item)

        self._overview_view.fitInView(
            self._overview_scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _update_overview_highlight(self) -> None:
        c = self._colors
        for i, rect_item in enumerate(self._rect_items):
            is_current = (i == self._current_index)
            pen = QPen(
                QColor(c.accent) if is_current else QColor(c.text_secondary),
                2.0 if is_current else 1.0,
            )
            rect_item.setPen(pen)
            if is_current:
                c_accent = QColor(c.accent)
                c_accent.setAlpha(20)
                rect_item.setBrush(QBrush(c_accent))
            else:
                rect_item.setBrush(Qt.BrushStyle.NoBrush)

    def _update_preview(self) -> None:
        if not self._crop_rects or self._source_image is None:
            self._preview_label.setText("Select a crop to view")
            self._preview_label.setPixmap(QPixmap())
            return

        rect = self._crop_rects[self._current_index]
        try:
            cropped = export_photo_to_memory(self._source_image, rect, auto_rotate=False, trim_white=False)
            # 动态适配可用空间
            available = self._preview_label.size()
            max_w = max(available.width() - 20, 200)
            max_h = max(available.height() - 20, 200)
            cropped.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            self._preview_label.setText("")
            self._preview_label.setPixmap(pixmap)
            self._preview_label.repaint()  # 强制立即视觉刷新
        except (ValueError, RuntimeError, OSError):
            self._preview_label.setText("无法生成预览")
            self._preview_label.setPixmap(QPixmap())

    def _update_nav(self) -> None:
        total = len(self._crop_rects)
        self._lbl_page.setText(f"{self._current_index + 1} / {total}")
        self._btn_prev.setEnabled(self._current_index > 0)
        self._btn_next.setEnabled(self._current_index < total - 1)

    def set_theme(self, colors) -> None:
        """更新面板颜色（主题切换时调用）"""
        self._colors = _PanelColors(
            bg=colors.canvas_bg, panel_bg=colors.bg,
            text=colors.text, text_secondary=colors.text_secondary,
            accent=colors.accent, hover_bg=colors.hover_bg,
        )
        self._apply_styles()
