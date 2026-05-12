from __future__ import annotations

"""
CropCanvas — 图像显示 + 裁剪框管理画布

Apple 设计风格：
    - 深色背景 (#1d1d1f)
    - 流畅的缩放和平移
    - PDF 页面导航
"""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from photocrop.engine.core import detect_rectangles
from photocrop.ui.crop_item import CropItem
from photocrop.ui.undo_manager import UndoManager
from photocrop.ui.utils import pil_to_qimage
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
    selection_changed = Signal()      # 选中的裁剪框变化
    view_single_requested = Signal(int)  # 请求切换到 Single View，参数为裁剪框索引
    zoom_changed = Signal()           # 缩放比例变化（滚轮/按钮）
    crop_rotating = Signal(float)     # 旋转中实时角度（轻量，仅更新属性面板）

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._source_image: Image.Image | None = None
        self._source_path: Path | None = None
        self._crop_items: list[CropItem] = []

        # 撤销/重做
        self._undo_manager = UndoManager()

        # PDF 页面管理
        self._pdf_pages: list[Image.Image] = []
        self._current_page: int = 0

        # 框选状态
        self._drawing = False
        self._draw_start = QPointF()
        self._temp_rect = None
        self._min_drag_size = 30  # 最小拖动距离（像素），防止手抖误触

        # 画布外观
        self._canvas_bg = QColor("#E8E8E8")
        self.setBackgroundBrush(QBrush(self._canvas_bg))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # 解决拖动裁剪框残影：全视口更新模式
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )

        # 监听 scene 选中变化
        self._scene.selectionChanged.connect(self._on_selection_changed)

    def set_theme(self, colors) -> None:
        """更新画布背景色和裁剪框颜色"""
        self._canvas_bg = QColor(colors.canvas_bg)
        self.setBackgroundBrush(QBrush(self._canvas_bg))
        # 更新 CropItem 颜色
        from photocrop.ui.crop_item import set_theme_colors
        set_theme_colors(colors)
        # 触发所有裁剪框重绘
        for item in self._crop_items:
            item.update()

    @property
    def source_image(self) -> Image.Image | None:
        return self._source_image

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def crop_items(self) -> list[CropItem]:
        return list(self._crop_items)

    @property
    def crop_rects(self) -> list[CropRect]:
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
        """加载 PDF 文件

        Deprecated: MainWindow 使用 session-based 按需加载（_load_single_file），
        不经过此路径。此方法仅供直接的 canvas API 调用使用，会一次性渲染所有页面。
        """
        try:
            from photocrop.export.pdf_reader import pdf_to_images
            self._pdf_pages = pdf_to_images(path, dpi=200)
        except ImportError as err:
            raise ImportError("PyMuPDF 未安装，无法加载 PDF") from err

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

        # 重置撤销历史，推入空状态作为初始帧
        self._undo_manager.clear()
        self._undo_manager.push_state([])

        # 清除旧图片
        if self._pixmap_item:
            self._scene.removeItem(self._pixmap_item)

        # 显示新图片
        qimage = pil_to_qimage(img)
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

    # ---- 撤销/重做 ----

    def undo(self) -> None:
        """撤销上一个操作"""
        rects = self._undo_manager.undo()
        if rects is not None:
            self._restore_rects(rects)

    def redo(self) -> None:
        """重做上一个撤销的操作"""
        rects = self._undo_manager.redo()
        if rects is not None:
            self._restore_rects(rects)

    def _restore_rects(self, rects: list[CropRect]) -> None:
        """用给定的 CropRect 列表替换当前所有裁剪框"""
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()
        for rect in rects:
            self._add_crop_item(rect)
        self.rects_changed.emit()

    # ---- 检测 ----

    def detect(self, **kwargs) -> int:
        if self._source_image is None:
            return 0

        # 直接清除旧裁剪框（不通过 clear_crops，避免多余的 undo 帧）
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()

        rects = detect_rectangles(self._source_image, **kwargs)

        for rect in rects:
            self._add_crop_item(rect)

        # BUG-001 fix: 推入撤销状态并通知 UI（预览面板依赖此信号刷新）
        self._push_undo_state()
        self.rects_changed.emit()

        self.detection_done.emit(len(rects))
        return len(rects)

    # ---- 裁剪框管理 ----

    def _add_crop_item(self, rect: CropRect) -> CropItem:
        item = CropItem(rect)
        # 用 lambda 捕获 item 引用，解决 sender() 不可用的问题
        item.set_callbacks(
            on_changed=self._on_crop_changed,
            on_deleted=lambda it=item: self._on_crop_deleted(it),
            on_view_single=lambda it=item: self._on_crop_view_single(it),
            on_copy=lambda it=item: self._on_crop_copy(it),
            on_rotate_left=lambda it=item: self._on_crop_rotate_left(it),
            on_rotate_right=lambda it=item: self._on_crop_rotate_right(it),
            on_rotating=self._on_crop_rotating,
        )
        self._scene.addItem(item)
        self._crop_items.append(item)
        return item

    def add_crop_rect(self, rect: CropRect) -> CropItem:
        item = self._add_crop_item(rect)
        self._push_undo_state()
        self.rects_changed.emit()
        return item

    def remove_selected(self) -> None:
        for item in self._crop_items[:]:
            if item.isSelected():
                self._remove_crop_item(item)

    def clear_crops(self) -> None:
        """清除所有裁剪框（保留图片）"""
        self._push_undo_state()  # 保存清除前的状态，支持撤销
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
        # BUG-013 fix: 释放 source_image 引用，允许 GC 回收大图像
        self._source_image = None
        self._source_path = None
        self.rects_changed.emit()

    def _remove_crop_item(self, item: CropItem) -> None:
        if item in self._crop_items:
            self._crop_items.remove(item)
        if item.scene():
            self._scene.removeItem(item)
        self.rects_changed.emit()

    def _on_crop_changed(self) -> None:
        self._push_undo_state()
        self.rects_changed.emit()
        # 旋转/缩放后确保裁剪框在视野内
        self.centerOn(self._scene.sceneRect().center())

    def _on_crop_rotating(self, angle: float) -> None:
        """旋转中轻量回调 — 仅更新属性面板角度，不触发完整刷新"""
        self.crop_rotating.emit(angle)

    def _on_crop_deleted(self, item: CropItem) -> None:
        """裁剪框被删除时的回调（由 CropItem 的 keyPressEvent 触发）"""
        if item in self._crop_items:
            self._crop_items.remove(item)
        self._push_undo_state()
        self.rects_changed.emit()

    def _on_crop_view_single(self, item: CropItem) -> None:
        """裁剪框工具栏：切换到 Single View（由 MainWindow 连接）"""
        # 发出信号让 MainWindow 处理
        if hasattr(self, 'view_single_requested'):
            idx = self._crop_items.index(item) if item in self._crop_items else 0
            self.view_single_requested.emit(idx)

    def _on_crop_copy(self, item: CropItem) -> None:
        """裁剪框工具栏：复制此框（偏移 20px）"""
        new_rect = CropRect(
            x=item.crop_rect.x + 20,
            y=item.crop_rect.y + 20,
            width=item.crop_rect.width,
            height=item.crop_rect.height,
            rotation_angle=item.crop_rect.rotation_angle,
            source_type="manual",
            page_num=item.crop_rect.page_num,
        )
        self._add_crop_item(new_rect)
        self._push_undo_state()
        self.rects_changed.emit()

    def _on_crop_rotate_left(self, item: CropItem) -> None:
        """裁剪框工具栏：逆时针旋转 90°"""
        item.crop_rect.rotation_angle = (item.crop_rect.rotation_angle - 90) % 360
        item._sync_from_rect()
        item.update()
        self._push_undo_state()
        self.rects_changed.emit()

    def _on_crop_rotate_right(self, item: CropItem) -> None:
        """裁剪框工具栏：顺时针旋转 90°"""
        item.crop_rect.rotation_angle = (item.crop_rect.rotation_angle + 90) % 360
        item._sync_from_rect()
        item.update()
        self._push_undo_state()
        self.rects_changed.emit()

    def _push_undo_state(self) -> None:
        """将当前裁剪框状态推入撤销栈"""
        self._undo_manager.push_state(self.crop_rects)

    def _on_selection_changed(self) -> None:
        """scene 选中变化时发出信号"""
        self.selection_changed.emit()

    @property
    def selected_items(self) -> list[CropItem]:
        """返回当前选中的 CropItem 列表"""
        return [it for it in self._crop_items if it.isSelected()]

    @property
    def selected_crop_rects(self) -> list[CropRect]:
        """返回当前选中的 CropRect 列表"""
        return [it.crop_rect for it in self._crop_items if it.isSelected()]

    # ---- 同步 / 翻转 ----

    def sync_selected_crops(self) -> int:
        """将最后选中的裁剪框参数同步到其他选中的框。返回同步数量。"""
        selected = [it for it in self._crop_items if it.isSelected()]
        if len(selected) < 2:
            return 0
        source = selected[-1]  # 最后选中的为源
        src_rect = source.crop_rect
        count = 0
        for item in selected[:-1]:
            item.crop_rect.width = src_rect.width
            item.crop_rect.height = src_rect.height
            item.crop_rect.rotation_angle = src_rect.rotation_angle
            item._sync_from_rect()
            count += 1
        self._push_undo_state()
        self.rects_changed.emit()
        return count

    def flip_horizontal(self) -> None:
        """水平翻转：选中的裁剪框以原图中心垂直线为轴翻转 x 坐标"""
        selected = [it for it in self._crop_items if it.isSelected()]
        if selected and self._source_image:
            center_x = self._source_image.width / 2
            for item in selected:
                item.crop_rect.x = 2 * center_x - item.crop_rect.x
                item._sync_from_rect()
            self._push_undo_state()
            self.rects_changed.emit()

    def flip_vertical(self) -> None:
        """垂直翻转：选中的裁剪框以原图中心水平线为轴翻转 y 坐标"""
        selected = [it for it in self._crop_items if it.isSelected()]
        if selected and self._source_image:
            center_y = self._source_image.height / 2
            for item in selected:
                item.crop_rect.y = 2 * center_y - item.crop_rect.y
                item._sync_from_rect()
            self._push_undo_state()
            self.rects_changed.emit()

    # ---- 框选新建 ----

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._item_at(event.position())):
            # Ctrl+Click: 不启动框选，让 scene 处理多选
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                super().mousePressEvent(event)
                return
            self._drawing = True
            self._draw_start = self.mapToScene(event.position().toPoint())
            # 延迟创建临时矩形 — 只有真正拖动才显示
            self._temp_rect = None
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()

        # Tab: 循环选中下一个 CropItem
        if key == Qt.Key.Key_Tab and not (modifiers & Qt.KeyboardModifier.ControlModifier):
            self._cycle_selection(forward=True)
            event.accept()
            return

        # Shift+Tab: 选中上一个
        if key == Qt.Key.Key_Tab and (modifiers & Qt.KeyboardModifier.ShiftModifier):
            self._cycle_selection(forward=False)
            event.accept()
            return

        # Ctrl+A: 全选
        if key == Qt.Key.Key_A and (modifiers & Qt.KeyboardModifier.ControlModifier):
            for item in self._crop_items:
                item.setSelected(True)
            event.accept()
            return

        # Esc: 取消所有选中
        if key == Qt.Key.Key_Escape:
            self._scene.clearSelection()
            event.accept()
            return

        super().keyPressEvent(event)

    def _cycle_selection(self, forward: bool = True) -> None:
        """循环选中下一个/上一个 CropItem"""
        if not self._crop_items:
            return

        # 找到当前选中项的索引
        current_idx = -1
        for i, item in enumerate(self._crop_items):
            if item.isSelected():
                current_idx = i
                break

        # 计算下一个索引
        if forward:
            next_idx = (current_idx + 1) % len(self._crop_items)
        else:
            next_idx = (current_idx - 1) % len(self._crop_items)

        # 取消所有选中，选中目标
        self._scene.clearSelection()
        self._crop_items[next_idx].setSelected(True)

    def mouseMoveEvent(self, event) -> None:
        if self._drawing:
            end = self.mapToScene(event.position().toPoint())
            # 检查是否超过最小拖动距离
            if self._temp_rect is None:
                dx = abs(end.x() - self._draw_start.x())
                dy = abs(end.y() - self._draw_start.y())
                if dx < self._min_drag_size and dy < self._min_drag_size:
                    return  # 移动太小，忽略
                # 超过阈值，创建临时矩形
                self._temp_rect = self._scene.addRect(
                    QRectF(self._draw_start, end).normalized(),
                    QPen(QColor("#000000"), 1.5, Qt.PenStyle.DashLine),
                    QBrush(QColor(0, 0, 0, 20)),
                )
                self._temp_rect.setZValue(1000)
            else:
                self._temp_rect.setRect(QRectF(self._draw_start, end).normalized())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing:
            self._drawing = False

            if self._temp_rect is not None:
                # 用户确实拖动了足够距离
                end = self.mapToScene(event.position().toPoint())
                rect = QRectF(self._draw_start, end).normalized()

                if rect.width() > self._min_drag_size and rect.height() > self._min_drag_size:
                    crop_rect = CropRect.from_pixel_rect(
                        rect.left(), rect.top(),
                        rect.right(), rect.bottom(),
                    )
                    crop_rect.source_type = "manual"
                    self._add_crop_item(crop_rect)
                    self._push_undo_state()  # 保存新建后的状态，支持撤销
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
        self.zoom_changed.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 不在这里 fitInView — 保留用户手动缩放/平移的视角
        # 初始适配在 _display_image 中完成
