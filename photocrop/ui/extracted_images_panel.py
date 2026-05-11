"""
ExtractedImagesPanel — 裁剪结果预览面板

对标 AutoCropper 右侧 EXTRACTED IMAGES。
显示当前页面所有裁剪框的提取结果缩略图。

支持两种模式：
- 单页模式：只显示当前页面的裁剪框（单图或切页时临时显示）
- 全局模式：显示 PDF 所有页面的裁剪框（PDF 加载后的主模式）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from photocrop.export.cropper import export_photo_to_memory
from photocrop.ui.icons import get_icon
from photocrop.ui.utils import pil_to_pixmap
from photocrop.utils.crop_rect import CropRect


class PageCropRef(NamedTuple):
    """全局索引到页面+本地索引的映射"""
    page_idx: int
    local_idx: int


FONT_FAMILY = "SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif"


@dataclass
class _PanelColors:
    """面板内部颜色（从 ThemeColors 提取）"""
    bg: str = "#F5F5F5"
    surface: str = "#FFFFFF"
    card_bg: str = "#FFFFFF"
    card_hover: str = "#F0F0F0"
    hover_bg: str = "rgba(0, 0, 0, 0.03)"
    text: str = "#1A1A1A"
    text_secondary: str = "#666666"
    border: str = "#E0E0E0"
    accent: str = "#000000"
    danger: str = "#CC0000"
    canvas_bg: str = "#E8E8E8"


class ExtractedImagesPanel(QWidget):
    """裁剪结果预览面板

    Signals:
        crop_selected: 点击缩略图时发出，参数为裁剪框在列表中的索引
        crop_delete_requested: 点击删除按钮时发出，参数为索引
    """

    crop_selected = Signal(int)
    crop_delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None,
                 scroll_area: QScrollArea | None = None):
        super().__init__(parent)
        self._colors = _PanelColors()

        self._source_image: Image.Image | None = None
        self._crop_rects: list[CropRect] = []
        self._cache: dict = {}  # key → QPixmap
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._scroll_area = scroll_area
        self._global_idx = 0

        # 全局模式
        self._global_mode = False
        self._global_index_map: dict[int, PageCropRef] = {}
        self._global_refresh_timer = QTimer(self)
        self._global_refresh_timer.setSingleShot(True)
        self._global_refresh_timer.timeout.connect(self._do_global_refresh)
        self._all_pages_data: list[tuple[int, Image.Image, list[CropRect]]] = []
        # 动态属性现在在 __init__ 中初始化
        self._current_editing_page: int = -1
        self._current_editing_rects: list[CropRect] | None = None

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        """构建 UI 结构"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(6)

        self._header = QPushButton("  EXTRACTED IMAGES  ▾")
        self._header.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(8)
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._collapsed = False

    def _apply_styles(self) -> None:
        """根据当前 _colors 应用所有样式"""
        c = self._colors
        self.setStyleSheet(f"ExtractedImagesPanel {{ background-color: {c.bg}; }}")
        self._header.setStyleSheet(
            f"QPushButton {{"
            f"background-color: transparent; color: {c.text_secondary}; "
            f"border: none; text-align: left; font-family: {FONT_FAMILY}; "
            f"font-size: 11px; font-weight: 600; letter-spacing: 0.5px; padding: 4px 0;"
            f"}}"
            f"QPushButton:hover {{ color: {c.text}; }}"
        )
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: transparent; border: none; }}"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{"
            f"background: {c.border}; border-radius: 2px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background: {c.text_secondary}; }}"
        )
        self._grid_widget.setStyleSheet(f"background-color: {c.bg};")

    # ---- 公共 API ----

    def set_source_image(self, img: Image.Image | None) -> None:
        if img is not self._source_image:
            self._source_image = img
            self._cache.clear()

    def refresh(self, crop_rects: list[CropRect]) -> None:
        self._crop_rects = list(crop_rects)
        self._refresh_timer.start(100)

    def add_page_results(self, page_idx: int, source_img: Image.Image,
                         rects: list[CropRect]) -> None:
        if self._global_mode:
            return
        c = self._colors
        page_label = QLabel(f"  Page {page_idx + 1}")
        page_label.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: 11px; font-weight: 600; padding: 8px 0 4px 4px; "
            f"border-top: 1px solid {c.border};"
        )
        row = self._grid_layout.rowCount()
        self._grid_layout.addWidget(page_label, row, 0, 1, 2)
        row += 1

        if not rects:
            empty_label = QLabel("    No photos detected")
            empty_label.setStyleSheet(
                f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
                f"font-size: 10px; padding: 4px 0;"
            )
            self._grid_layout.addWidget(empty_label, row, 0, 1, 2)
        else:
            for i, rect in enumerate(rects):
                thumb = self._generate_thumbnail(source_img, rect)
                self._add_thumbnail_widget(thumb, self._global_idx, row + i // 2, i % 2)
                self._global_idx += 1

        if self._scroll_area:
            vbar = self._scroll_area.verticalScrollBar()
            QTimer.singleShot(50, lambda: vbar.setValue(vbar.maximum()))

    def clear_incremental(self) -> None:
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._global_idx = 0

    # ---- 全局模式 ----

    def set_global_mode(self, enabled: bool) -> None:
        self._global_mode = enabled
        if not enabled:
            self._all_pages_data.clear()
            self._global_index_map.clear()

    def refresh_all_pages(self, pages_data: list[tuple[int, Image.Image, list[CropRect]]],
                          current_page: int = -1,
                          current_rects: list[CropRect] | None = None) -> None:
        self._all_pages_data = list(pages_data)
        self._current_editing_page = current_page
        self._current_editing_rects = current_rects
        self._global_refresh_timer.start(150)

    def get_page_and_index(self, global_idx: int) -> PageCropRef | None:
        return self._global_index_map.get(global_idx)

    # ---- 内部方法 ----

    def _do_refresh(self) -> None:
        if self._global_mode:
            return
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._global_idx = 0

        if self._source_image is None or not self._crop_rects:
            return

        for i, rect in enumerate(self._crop_rects):
            card = self._create_preview_card(i, rect)
            col = i % 2
            row = i // 2
            self._grid_layout.addWidget(card, row, col)

    def _do_global_refresh(self) -> None:
        c = self._colors
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._global_index_map.clear()
        global_idx = 0

        current_page = self._current_editing_page
        current_rects = self._current_editing_rects

        for page_idx, source_img, rects in self._all_pages_data:
            if page_idx == current_page and current_rects is not None:
                rects = current_rects

            page_label = QLabel(f"  Page {page_idx + 1}")
            is_current = page_idx == current_page
            highlight = f"color: {c.accent}; font-weight: 700;" if is_current else ""
            page_label.setStyleSheet(
                f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
                f"font-size: 11px; font-weight: 600; padding: 8px 0 4px 4px; "
                f"border-top: 1px solid {c.border}; {highlight}"
            )
            row = self._grid_layout.rowCount()
            self._grid_layout.addWidget(page_label, row, 0, 1, 2)
            row += 1

            if not rects:
                empty_label = QLabel("    No photos detected")
                empty_label.setStyleSheet(
                    f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
                    f"font-size: 10px; padding: 4px 0;"
                )
                self._grid_layout.addWidget(empty_label, row, 0, 1, 2)
            else:
                for i, rect in enumerate(rects):
                    self._global_index_map[global_idx] = PageCropRef(page_idx, i)
                    thumb = self._generate_thumbnail(source_img, rect)
                    self._add_thumbnail_widget(thumb, global_idx, row + i // 2, i % 2,
                                               show_delete=True)
                    global_idx += 1

        self._global_idx = global_idx

    def _create_preview_card(self, index: int, rect: CropRect) -> QWidget:
        """创建单个预览卡片（单页模式）"""
        return self._build_card(index, rect, show_delete=False)

    def _add_thumbnail_widget(self, pixmap: QPixmap | None, global_idx: int,
                              row: int, col: int,
                              show_delete: bool = False) -> None:
        """添加缩略图 widget 到网格"""
        card = self._build_card(global_idx, None, show_delete=show_delete, pixmap=pixmap)
        self._grid_layout.addWidget(card, row, col)

    def _build_card(self, index: int, rect: CropRect | None,
                    show_delete: bool = False,
                    pixmap: QPixmap | None = None) -> QWidget:
        """统一创建预览卡片（单页和全局模式共享）"""
        c = self._colors
        card = QWidget()
        card.setFixedSize(90, 110)
        card.setStyleSheet(
            f"QWidget {{ background-color: {c.card_bg}; border-radius: 6px; }}"
            f"QWidget:hover {{ background-color: {c.card_hover}; }}"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        thumb_label = QLabel()
        thumb_label.setFixedSize(80, 80)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet(f"border-radius: 4px; background: {c.canvas_bg};")

        if pixmap is None and rect is not None and self._source_image is not None:
            pixmap = self._get_thumbnail(index, rect)
        if pixmap:
            thumb_label.setPixmap(pixmap)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet(f"color: {c.text_secondary}; border-radius: 4px; background: {c.canvas_bg};")

        thumb_label.mousePressEvent = lambda e, idx=index: self.crop_selected.emit(idx)
        layout.addWidget(thumb_label)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)

        num_label = QLabel(f"#{index + 1}")
        num_label.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 10px;")
        bottom.addWidget(num_label)
        bottom.addStretch()

        if show_delete:
            btn_del = QPushButton()
            btn_del.setFixedSize(16, 16)
            btn_del.setIcon(get_icon("x", c.text_secondary))
            btn_del.setIconSize(QSize(10, 10))
            btn_del.setStyleSheet(
                f"QPushButton {{ background-color: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ background-color: {c.hover_bg}; }}"
            )
            btn_del.clicked.connect(lambda _, idx=index: self.crop_delete_requested.emit(idx))
            bottom.addWidget(btn_del)

        layout.addLayout(bottom)
        return card

    def _generate_thumbnail(self, source_img: Image.Image,
                            rect: CropRect) -> QPixmap | None:
        try:
            cropped = export_photo_to_memory(source_img, rect)
            cropped.thumbnail((80, 80), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            if len(self._cache) > 128:
                self._cache.clear()
            return pixmap
        except (ValueError, RuntimeError, OSError):
            return None

    def _get_thumbnail(self, index: int, rect: CropRect) -> QPixmap | None:
        if self._source_image is None:
            return None

        # 用确定性 key 替代 id()
        cache_key = (self._source_image.size, rect.to_pixel_tuple(), rect.rotation_angle)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            cropped = export_photo_to_memory(self._source_image, rect)
            cropped.thumbnail((80, 80), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            if len(self._cache) > 128:
                self._cache.clear()
            self._cache[cache_key] = pixmap
            return pixmap
        except (ValueError, RuntimeError, OSError):
            return None

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self._scroll.setVisible(not self._collapsed)
        self._header.setText(
            "  EXTRACTED IMAGES  ▸" if self._collapsed
            else "  EXTRACTED IMAGES  ▾"
        )

    def set_theme(self, colors) -> None:
        """更新面板颜色（主题切换时调用）"""
        self._colors = _PanelColors(
            bg=colors.bg, surface=colors.surface,
            card_bg=colors.surface, card_hover=colors.hover_bg,
            hover_bg=colors.hover_bg,
            text=colors.text, text_secondary=colors.text_secondary,
            border=colors.border, accent=colors.accent,
            danger=colors.danger, canvas_bg=colors.canvas_bg,
        )
        self._apply_styles()
        # 触发全局刷新以重建卡片（使用新颜色）
        if self._global_mode and self._all_pages_data:
            self._do_global_refresh()
        elif self._crop_rects:
            self._do_refresh()
