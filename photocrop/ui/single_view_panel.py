"""
SingleViewPanel — 单个裁剪框大图预览

双栏布局：
- 左侧：原图缩略 + 所有裁剪框轮廓（不可编辑）
- 右侧：选中裁剪框的提取大图
- 底部：页码 + 左右箭头切换
"""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt, Signal
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
from photocrop.ui.utils import pil_to_pixmap, pil_to_qimage
from photocrop.utils.crop_rect import CropRect

# ============================================================
# 样式常量
# ============================================================

BG_COLOR = "#E8E8E8"
PANEL_BG = "#F5F5F5"
TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#666666"
APPLE_BLUE = "#000000"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


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
        self.setStyleSheet(f"background-color: {BG_COLOR};")

        self._source_image: Image.Image | None = None
        self._crop_rects: list[CropRect] = []
        self._current_index: int = 0
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._rect_items: list[QGraphicsRectItem] = []

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 左侧: 原图缩略 + 裁剪框轮廓 ----
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_panel.setStyleSheet(f"background-color: {BG_COLOR};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        lbl_left = QLabel("OVERVIEW")
        lbl_left.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        left_layout.addWidget(lbl_left)

        self._overview_scene = QGraphicsScene()
        self._overview_view = QGraphicsView(self._overview_scene)
        self._overview_view.setBackgroundBrush(QBrush(QColor(BG_COLOR)))
        self._overview_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._overview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overview_view.setStyleSheet("border: none;")
        left_layout.addWidget(self._overview_view, 1)

        # 退出按钮
        btn_exit = QPushButton("返回 Grid View")
        btn_exit.setProperty("secondary", "true")
        btn_exit.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {APPLE_BLUE};
                border: 1px solid {APPLE_BLUE};
                border-radius: 6px;
                padding: 6px 12px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.05);
            }}
        """)
        btn_exit.clicked.connect(self.exit_requested.emit)
        left_layout.addWidget(btn_exit)

        main_layout.addWidget(left_panel)

        # ---- 右侧: 提取大图 ----
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background-color: {BG_COLOR};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(f"""
            background-color: #F5F5F5;
            border-radius: 8px;
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 14px;
        """)
        self._preview_label.setText("选择一个裁剪框")
        right_layout.addWidget(self._preview_label, 1)

        # 底部: 页码导航
        nav_bar = QWidget()
        nav_bar.setStyleSheet(f"background-color: {PANEL_BG}; border-radius: 6px;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedSize(28, 28)
        self._btn_prev.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_PRIMARY};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ color: {APPLE_BLUE}; }}
        """)
        self._btn_prev.clicked.connect(self._go_prev)
        nav_layout.addWidget(self._btn_prev)

        self._lbl_page = QLabel("0 / 0")
        self._lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_page.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        """)
        nav_layout.addWidget(self._lbl_page, 1)

        self._btn_next = QPushButton("▶")
        self._btn_next.setFixedSize(28, 28)
        self._btn_next.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_PRIMARY};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{ color: {APPLE_BLUE}; }}
        """)
        self._btn_next.clicked.connect(self._go_next)
        nav_layout.addWidget(self._btn_next)

        right_layout.addWidget(nav_bar)

        main_layout.addWidget(right_panel, 1)

    def set_data(self, source_image: Image.Image, crop_rects: list[CropRect]) -> None:
        """设置源图和裁剪框数据"""
        self._source_image = source_image
        self._crop_rects = list(crop_rects)
        self._current_index = 0

        self._update_overview()
        self._update_preview()
        self._update_nav()

    def select_crop(self, index: int) -> None:
        """选中指定裁剪框"""
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
        """更新左侧原图缩略 + 裁剪框轮廓"""
        self._overview_scene.clear()
        self._rect_items.clear()

        if self._source_image is None:
            return

        # 显示原图
        qimage = pil_to_qimage(self._source_image)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item = self._overview_scene.addPixmap(pixmap)

        # 绘制裁剪框轮廓
        for i, rect in enumerate(self._crop_rects):
            x1, y1, x2, y2 = rect.to_pixel_tuple()
            is_current = (i == self._current_index)
            pen = QPen(
                QColor(APPLE_BLUE) if is_current else QColor(0, 0, 0, 40),
                2.0 if is_current else 1.0,
            )
            rect_item = self._overview_scene.addRect(x1, y1, x2 - x1, y2 - y1, pen)
            if is_current:
                rect_item.setBrush(QBrush(QColor(0, 0, 0, 20)))
            self._rect_items.append(rect_item)

        self._overview_view.fitInView(
            self._overview_scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _update_overview_highlight(self) -> None:
        """更新高亮状态"""
        for i, rect_item in enumerate(self._rect_items):
            is_current = (i == self._current_index)
            pen = QPen(
                QColor(APPLE_BLUE) if is_current else QColor(0, 0, 0, 40),
                2.0 if is_current else 1.0,
            )
            rect_item.setPen(pen)
            if is_current:
                rect_item.setBrush(QBrush(QColor(0, 0, 0, 20)))
            else:
                rect_item.setBrush(Qt.BrushStyle.NoBrush)

    def _update_preview(self) -> None:
        """更新右侧提取大图"""
        if not self._crop_rects or self._source_image is None:
            self._preview_label.setText("选择一个裁剪框")
            self._preview_label.setPixmap(QPixmap())
            return

        rect = self._crop_rects[self._current_index]
        try:
            cropped = export_photo_to_memory(self._source_image, rect)
            # 缩放到预览区域大小
            max_w, max_h = 600, 600
            cropped.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            pixmap = pil_to_pixmap(cropped)
            self._preview_label.setText("")
            self._preview_label.setPixmap(pixmap)
        except (ValueError, RuntimeError, OSError):
            self._preview_label.setText("无法生成预览")
            self._preview_label.setPixmap(QPixmap())

    def _update_nav(self) -> None:
        """更新页码导航"""
        total = len(self._crop_rects)
        self._lbl_page.setText(f"{self._current_index + 1} / {total}")
        self._btn_prev.setEnabled(self._current_index > 0)
        self._btn_next.setEnabled(self._current_index < total - 1)

