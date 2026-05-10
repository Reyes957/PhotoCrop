"""
ExtractedImagesPanel — 裁剪结果预览面板

对标 AutoCropper 右侧 EXTRACTED IMAGES。
显示当前页面所有裁剪框的提取结果缩略图。

支持两种模式：
- 单页模式：只显示当前页面的裁剪框（单图或切页时临时显示）
- 全局模式：显示 PDF 所有页面的裁剪框（PDF 加载后的主模式）
"""

from __future__ import annotations

from typing import NamedTuple

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
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
from photocrop.ui.utils import pil_to_pixmap
from photocrop.utils.crop_rect import CropRect


class PageCropRef(NamedTuple):
    """全局索引到页面+本地索引的映射"""
    page_idx: int
    local_idx: int

# ============================================================
# 样式常量
# ============================================================

PANEL_BG = "#F5F5F5"
CARD_BG = "#FFFFFF"
TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#666666"
APPLE_BLUE = "#000000"
DANGER = "#CC0000"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


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
        self.setStyleSheet(f"""
            ExtractedImagesPanel {{
                background-color: {PANEL_BG};
            }}
        """)

        self._source_image: Image.Image | None = None
        self._crop_rects: list[CropRect] = []
        self._cache: dict = {}  # key → QPixmap
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._scroll_area = scroll_area  # 外部传入，用于增量模式自动滚动
        self._global_idx = 0  # 增量模式下的全局索引

        # 全局模式：跨页预览
        self._global_mode = False  # True = 显示所有页面
        self._global_index_map: dict[int, PageCropRef] = {}  # 全局索引 → (page, local)
        self._global_refresh_timer = QTimer(self)
        self._global_refresh_timer.setSingleShot(True)
        self._global_refresh_timer.timeout.connect(self._do_global_refresh)
        self._all_pages_data: list[tuple[int, Image.Image, list[CropRect]]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(6)

        # 折叠头
        self._header = QPushButton("  EXTRACTED IMAGES  ▾")
        self._header.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                text-align: left;
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                padding: 4px 0;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
            }}
        """)
        self._header.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._header)

        # 可滚动区域
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                width: 4px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #CCCCCC;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #999999;
            }
        """)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet(f"background-color: {PANEL_BG};")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(8)
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._collapsed = False

    # ---- 公共 API ----

    def set_source_image(self, img: Image.Image | None) -> None:
        """设置源图像"""
        if img is not self._source_image:
            self._source_image = img
            self._cache.clear()

    def refresh(self, crop_rects: list[CropRect]) -> None:
        """请求刷新（防抖 100ms）"""
        self._crop_rects = list(crop_rects)
        self._refresh_timer.start(100)

    def add_page_results(self, page_idx: int, source_img: Image.Image,
                         rects: list[CropRect]) -> None:
        """增量添加一页的检测结果（用于 PDF 批量检测）

        全局模式下自动跳过——最终由 refresh_all_pages() 统一刷新。

        Args:
            page_idx: 页码（0-based）
            source_img: 该页的源图像
            rects: 该页检测到的裁剪框列表
        """
        if self._global_mode:
            return  # 全局模式下由 refresh_all_pages 统一处理
        # 页面分隔标签
        page_label = QLabel(f"  Page {page_idx + 1}")
        page_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            font-weight: 600;
            padding: 8px 0 4px 4px;
            border-top: 1px solid #E0E0E0;
        """)
        row = self._grid_layout.rowCount()
        self._grid_layout.addWidget(page_label, row, 0, 1, 2)
        row += 1

        if not rects:
            # 无结果时显示提示
            empty_label = QLabel("    No photos detected")
            empty_label.setStyleSheet(f"""
                color: {TEXT_SECONDARY};
                font-family: {FONT_FAMILY};
                font-size: 10px;
                padding: 4px 0;
            """)
            self._grid_layout.addWidget(empty_label, row, 0, 1, 2)
        else:
            for i, rect in enumerate(rects):
                thumb = self._generate_thumbnail(source_img, rect)
                self._add_thumbnail_widget(thumb, self._global_idx, row + i // 2, i % 2)
                self._global_idx += 1

        # 滚动到底部
        if self._scroll_area:
            vbar = self._scroll_area.verticalScrollBar()
            QTimer.singleShot(50, lambda: vbar.setValue(vbar.maximum()))

    def clear_incremental(self) -> None:
        """清除增量模式添加的内容"""
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._global_idx = 0

    # ---- 全局模式（跨页预览） ----

    def set_global_mode(self, enabled: bool) -> None:
        """启用/禁用全局模式（显示 PDF 所有页面的裁剪框）"""
        self._global_mode = enabled
        if not enabled:
            self._all_pages_data.clear()
            self._global_index_map.clear()

    def refresh_all_pages(self, pages_data: list[tuple[int, Image.Image, list[CropRect]]],
                          current_page: int = -1,
                          current_rects: list[CropRect] | None = None) -> None:
        """请求全局刷新（防抖 150ms）

        Args:
            pages_data: [(page_idx, source_img, rects), ...] 所有页面数据
            current_page: 当前编辑的页码（-1 表示无特殊页）
            current_rects: 当前页的实时裁剪框（优先使用，覆盖 pages_data 中的）
        """
        self._all_pages_data = list(pages_data)
        self._current_editing_page = current_page
        self._current_editing_rects = current_rects
        self._global_refresh_timer.start(150)

    def get_page_and_index(self, global_idx: int) -> PageCropRef | None:
        """全局索引 → (page_idx, local_idx)"""
        return self._global_index_map.get(global_idx)

    # ---- 内部方法 ----

    def _do_refresh(self) -> None:
        """实际刷新预览（单页模式）"""
        if self._global_mode:
            return  # 全局模式下忽略单页刷新

        # 清除旧内容
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
        """实际刷新全局预览（跨页模式）"""
        # 清除旧内容
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._global_index_map.clear()
        global_idx = 0

        current_page = getattr(self, '_current_editing_page', -1)
        current_rects = getattr(self, '_current_editing_rects', None)

        for page_idx, source_img, rects in self._all_pages_data:
            # 如果是当前编辑页，用实时数据覆盖
            if page_idx == current_page and current_rects is not None:
                rects = current_rects

            # 页面分隔标签
            page_label = QLabel(f"  Page {page_idx + 1}")
            is_current = page_idx == current_page
            highlight = "color: #000000; font-weight: 700;" if is_current else ""
            page_label.setStyleSheet(f"""
                color: {TEXT_SECONDARY};
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: 600;
                padding: 8px 0 4px 4px;
                border-top: 1px solid #E0E0E0;
                {highlight}
            """)
            row = self._grid_layout.rowCount()
            self._grid_layout.addWidget(page_label, row, 0, 1, 2)
            row += 1

            if not rects:
                empty_label = QLabel("    No photos detected")
                empty_label.setStyleSheet(f"""
                    color: {TEXT_SECONDARY};
                    font-family: {FONT_FAMILY};
                    font-size: 10px;
                    padding: 4px 0;
                """)
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
        """创建单个预览卡片"""
        card = QWidget()
        card.setFixedSize(90, 110)
        card.setStyleSheet(f"""
            QWidget {{
                background-color: {CARD_BG};
                border-radius: 6px;
            }}
            QWidget:hover {{
                background-color: #F0F0F0;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # 缩略图
        thumb_label = QLabel()
        thumb_label.setFixedSize(80, 80)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("border-radius: 4px; background: #E8E8E8;")

        pixmap = self._get_thumbnail(index, rect)
        if pixmap:
            thumb_label.setPixmap(pixmap)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet(f"color: {TEXT_SECONDARY}; border-radius: 4px; background: #E8E8E8;")

        # 点击选中
        thumb_label.mousePressEvent = lambda e, idx=index: self.crop_selected.emit(idx)
        layout.addWidget(thumb_label)

        # 底部: 编号 + 删除按钮
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)

        num_label = QLabel(f"#{index + 1}")
        num_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 10px;
        """)
        bottom.addWidget(num_label)

        bottom.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(16, 16)
        btn_del.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 10px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {DANGER};
            }}
        """)
        btn_del.clicked.connect(lambda _, idx=index: self.crop_delete_requested.emit(idx))
        bottom.addWidget(btn_del)

        layout.addLayout(bottom)

        return card

    def _generate_thumbnail(self, source_img: Image.Image,
                            rect: CropRect) -> QPixmap | None:
        """从源图裁剪并生成缩略图"""
        try:
            cropped = export_photo_to_memory(source_img, rect)
            cropped.thumbnail((80, 80), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            # 限制缓存大小
            if len(self._cache) > 128:
                self._cache.clear()
            return pixmap
        except (ValueError, RuntimeError, OSError):
            return None

    def _add_thumbnail_widget(self, pixmap: QPixmap | None, global_idx: int,
                              row: int, col: int,
                              show_delete: bool = False) -> None:
        """添加一个缩略图 widget 到网格

        Args:
            show_delete: 是否显示删除按钮（全局模式下为 True）
        """
        card = QWidget()
        card.setFixedSize(90, 110)
        card.setStyleSheet(f"""
            QWidget {{
                background-color: {CARD_BG};
                border-radius: 6px;
            }}
            QWidget:hover {{
                background-color: #F0F0F0;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        thumb_label = QLabel()
        thumb_label.setFixedSize(80, 80)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("border-radius: 4px; background: #E8E8E8;")

        if pixmap:
            thumb_label.setPixmap(pixmap)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet(f"color: {TEXT_SECONDARY}; border-radius: 4px; background: #E8E8E8;")

        thumb_label.mousePressEvent = lambda e, idx=global_idx: self.crop_selected.emit(idx)
        layout.addWidget(thumb_label)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)

        num_label = QLabel(f"#{global_idx + 1}")
        num_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 10px;
        """)
        bottom.addWidget(num_label)
        bottom.addStretch()

        if show_delete:
            btn_del = QPushButton("✕")
            btn_del.setFixedSize(16, 16)
            btn_del.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    font-size: 10px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    color: {DANGER};
                }}
            """)
            btn_del.clicked.connect(lambda _, idx=global_idx: self.crop_delete_requested.emit(idx))
            bottom.addWidget(btn_del)

        layout.addLayout(bottom)

        self._grid_layout.addWidget(card, row, col)

    def _get_thumbnail(self, index: int, rect: CropRect) -> QPixmap | None:
        """获取缩略图（带缓存）"""
        if self._source_image is None:
            return None

        cache_key = (id(self._source_image), rect.to_pixel_tuple(), rect.rotation_angle)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            cropped = export_photo_to_memory(self._source_image, rect)
            cropped.thumbnail((80, 80), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            # 限制缓存大小
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
        """更新面板颜色"""
        self.setStyleSheet(f"""
            ExtractedImagesPanel {{
                background-color: {colors.bg};
            }}
        """)
        self._grid_widget.setStyleSheet(f"background-color: {colors.bg};")
