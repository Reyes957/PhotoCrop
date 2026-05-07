"""
ExtractedImagesPanel — 裁剪结果预览面板

对标 AutoCropper 右侧 EXTRACTED IMAGES。
显示当前页面所有裁剪框的提取结果缩略图。
"""

from __future__ import annotations

import functools
from typing import Optional, List

from PIL import Image
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QGridLayout,
    QPushButton,
)

from photocrop.export.cropper import export_photo_to_memory
from photocrop.utils.crop_rect import CropRect

# ============================================================
# 样式常量
# ============================================================

PANEL_BG = "#2c2c2e"
CARD_BG = "#3a3a3c"
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#86868b"
APPLE_BLUE = "#0071e3"
DANGER = "#ff3b30"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


class ExtractedImagesPanel(QWidget):
    """裁剪结果预览面板

    Signals:
        crop_selected: 点击缩略图时发出，参数为裁剪框在列表中的索引
        crop_delete_requested: 点击删除按钮时发出，参数为索引
    """

    crop_selected = Signal(int)
    crop_delete_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            ExtractedImagesPanel {{
                background-color: {PANEL_BG};
            }}
        """)

        self._source_image: Optional[Image.Image] = None
        self._crop_rects: List[CropRect] = []
        self._cache: dict = {}  # key → QPixmap
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

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
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.2);
                border-radius: 3px;
            }}
        """)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet(f"background-color: {PANEL_BG};")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(8)
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._collapsed = False

    def set_source_image(self, img: Optional[Image.Image]) -> None:
        """设置源图像"""
        if img is not self._source_image:
            self._source_image = img
            self._cache.clear()

    def refresh(self, crop_rects: List[CropRect]) -> None:
        """请求刷新（防抖 100ms）"""
        self._crop_rects = list(crop_rects)
        self._refresh_timer.start(100)

    def _do_refresh(self) -> None:
        """实际刷新预览"""
        # 清除旧内容
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if self._source_image is None or not self._crop_rects:
            return

        for i, rect in enumerate(self._crop_rects):
            card = self._create_preview_card(i, rect)
            col = i % 2
            row = i // 2
            self._grid_layout.addWidget(card, row, col)

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
                background-color: #48484a;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # 缩略图
        thumb_label = QLabel()
        thumb_label.setFixedSize(80, 80)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("border-radius: 4px; background: #2c2c2e;")

        pixmap = self._get_thumbnail(index, rect)
        if pixmap:
            thumb_label.setPixmap(pixmap)
        else:
            thumb_label.setText("?")
            thumb_label.setStyleSheet(f"color: {TEXT_SECONDARY}; border-radius: 4px; background: #2c2c2e;")

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

    def _get_thumbnail(self, index: int, rect: CropRect) -> Optional[QPixmap]:
        """获取缩略图（带缓存）"""
        if self._source_image is None:
            return None

        cache_key = (id(self._source_image), rect.to_pixel_tuple(), rect.rotation_angle)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            cropped = export_photo_to_memory(self._source_image, rect)
            cropped.thumbnail((80, 80), Image.Resampling.LANCZOS)
            pixmap = self._pil_to_pixmap(cropped)
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

    @staticmethod
    def _pil_to_pixmap(img: Image.Image) -> QPixmap:
        if img.mode == "RGBA":
            img = img.convert("RGBA")
            data = img.tobytes("raw", "RGBA")
            bpl = img.width * 4
            qimage = QImage(data, img.width, img.height, bpl, QImage.Format.Format_RGBA8888)
        else:
            img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            bpl = img.width * 3
            qimage = QImage(data, img.width, img.height, bpl, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimage.copy())
