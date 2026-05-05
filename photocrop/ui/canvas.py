from __future__ import annotations
"""
CropCanvas — 图像显示 + 裁剪框管理画布

Apple 设计风格：
    - 深色背景 (#1d1d1f)
    - 流畅的缩放和平移
    - PDF 页面导航
"""

from pathlib import Path
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPixmap,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from photocrop.engine.core import detect_rectangles
from photocrop.ui.crop_item import CropItem, HandlePosition
from photocrop.utils.crop_rect import CropRect


class CropCanvas(QGraphicsView):
    """图像显示 + 裁剪框管理画布

    Signals:
        rects_changed: 裁剪框列表发生变化
        image_loaded: 图片加载成功
        detection_done: 检测完成
        page_changed: PDF 页面切换
    """

    rects_changed = Signal()
    image_loaded = Signal()
    detection_done = Signal(int)
    page_changed = Signal(int, int)  # current_page, total_pages

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._source_image: Optional[Image.Image] = None
        self._source_path: Optional[Path] = None
        self._crop_items: List[CropItem] = []

        # PDF 页面管理
        self._pdf_pages: List[Image.Image] = []
        self._current_page: int = 0

        # 框选状态
        self._drawing = False
        self._draw_start = QPointF()
        self._temp_rect = None

        # 画布外观
        self.setBackgroundBrush(QBrush(QColor("#1d1d1f")))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    @property
    def source_image(self) -> Optional[Image.Image]:
        return self._source_image

    @property
    def source_path(self) -> Optional[Path]:
        return self._source_path

    @property
    def crop_items(self) -> List[CropItem]:
        return list(self._crop_items)

    @property
    def crop_rects(self) -> List[CropRect]:
        return [item.crop_rect for item in self._crop_items]

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def total_pages(self) -> int:
        return len(self._pdf_pages)

    # ---- 图片加载 ----

    def load_image(self, path: str | Path) -> None:
        """加载图片"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        # 检查是否是 PDF
        if path.suffix.lower() == '.pdf':
            self._load_pdf(path)
            return

        img = Image.open(path)
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")

        self._source_image = img
        self._source_path = path
        self._pdf_pages = []
        self._current_page = 0

        self._display_image(img)
        self.image_loaded.emit()

    def _load_pdf(self, path: Path) -> None:
        """加载 PDF 文件"""
        try:
            from photocrop.export.pdf_reader import pdf_to_images
            self._pdf_pages = pdf_to_images(path, dpi=200)
        except ImportError:
            raise ImportError("PyMuPDF 未安装，无法加载 PDF")

        if not self._pdf_pages:
            raise ValueError("PDF 没有可读取的页面")

        self._source_path = path
        self._current_page = 0
        self._show_page(0)
        self.image_loaded.emit()

    def load_pil_image(self, img: Image.Image) -> None:
        """直接加载 PIL Image"""
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")

        self._source_image = img
        self._source_path = None
        self._pdf_pages = []
        self._current_page = 0

        self._display_image(img)
        self.image_loaded.emit()

    def _display_image(self, img: Image.Image) -> None:
        """显示图像"""
        # 清除旧裁剪框
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()

        # 清除旧图片
        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)

        # 显示新图片
        qimage = self._pil_to_qimage(img)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item = self._scene.addPixmap(pixmap)

        # 适配视图
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.rects_changed.emit()

    def _show_page(self, page_num: int) -> None:
        """显示指定 PDF 页面"""
        if not self._pdf_pages or page_num < 0 or page_num >= len(self._pdf_pages):
            return

        self._current_page = page_num
        _, img = self._pdf_pages[page_num]
        self._source_image = img

        self._display_image(img)
        self.page_changed.emit(page_num, len(self._pdf_pages))

    def next_page(self) -> None:
        """下一页"""
        if self._pdf_pages and self._current_page < len(self._pdf_pages) - 1:
            self._show_page(self._current_page + 1)

    def prev_page(self) -> None:
        """上一页"""
        if self._pdf_pages and self._current_page > 0:
            self._show_page(self._current_page - 1)

    @staticmethod
    def _pil_to_qimage(img: Image.Image) -> QImage:
        if img.mode == "RGBA":
            data = img.tobytes("raw", "RGBA")
            qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        elif img.mode == "RGB":
            data = img.tobytes("raw", "RGB")
            qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGB888)
        else:
            img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGB888)
        return qimage.copy()

    # ---- 检测 ----

    def detect(self, **kwargs) -> int:
        if self._source_image is None:
            return 0

        # 先清除旧裁剪框，避免重复检测叠加
        self.clear_crops()

        rects = detect_rectangles(self._source_image, **kwargs)

        for rect in rects:
            self._add_crop_item(rect)

        self.detection_done.emit(len(rects))
        return len(rects)

    # ---- 裁剪框管理 ----

    def _add_crop_item(self, rect: CropRect) -> CropItem:
        item = CropItem(rect)
        # 用 lambda 捕获 item 引用，解决 sender() 不可用的问题
        item.set_callbacks(
            on_changed=self._on_crop_changed,
            on_deleted=lambda it=item: self._on_crop_deleted(it),
        )
        self._scene.addItem(item)
        self._crop_items.append(item)
        return item

    def add_crop_rect(self, rect: CropRect) -> CropItem:
        item = self._add_crop_item(rect)
        self.rects_changed.emit()
        return item

    def remove_selected(self) -> None:
        for item in self._crop_items[:]:
            if item.isSelected():
                self._remove_crop_item(item)

    def clear_crops(self) -> None:
        """清除所有裁剪框（保留图片）"""
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()
        self.rects_changed.emit()

    def clear_all(self) -> None:
        """清除所有内容"""
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()
        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)
            self._pixmap_item = None
        self._scene.clear()
        self._crop_items.clear()
        self.rects_changed.emit()

    def _remove_crop_item(self, item: CropItem) -> None:
        if item in self._crop_items:
            self._crop_items.remove(item)
        if item.scene():
            self._scene.removeItem(item)
        self.rects_changed.emit()

    def _on_crop_changed(self) -> None:
        self.rects_changed.emit()

    def _on_crop_deleted(self, item: CropItem) -> None:
        """裁剪框被删除时的回调（由 CropItem 的 keyPressEvent 触发）"""
        if item in self._crop_items:
            self._crop_items.remove(item)
        self.rects_changed.emit()

    # ---- 框选新建 ----

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._item_at(event.position())):
            self._drawing = True
            self._draw_start = self.mapToScene(event.position().toPoint())
            self._temp_rect = self._scene.addRect(
                QRectF(self._draw_start, self._draw_start),
                QPen(QColor("#0071e3"), 1.5, Qt.PenStyle.DashLine),
                QBrush(QColor(0, 113, 227, 30)),
            )
            self._temp_rect.setZValue(1000)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drawing and self._temp_rect:
            end = self.mapToScene(event.position().toPoint())
            self._temp_rect.setRect(QRectF(self._draw_start, end).normalized())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing and self._temp_rect:
            self._drawing = False
            end = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._draw_start, end).normalized()

            if rect.width() > 10 and rect.height() > 10:
                crop_rect = CropRect.from_pixel_rect(
                    rect.left(), rect.top(),
                    rect.right(), rect.bottom(),
                )
                crop_rect.source_type = "manual"
                self._add_crop_item(crop_rect)
                self.rects_changed.emit()

            self._scene.removeItem(self._temp_rect)
            self._temp_rect = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _item_at(self, pos) -> bool:
        scene_pos = self.mapToScene(pos.toPoint())
        item = self._scene.itemAt(scene_pos, self.transform())
        return item is not None and item is not self._pixmap_item

    # ---- 缩放 ----

    def wheelEvent(self, event) -> None:
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 不在这里 fitInView — 保留用户手动缩放/平移的视角
        # 初始适配在 _display_image 中完成
