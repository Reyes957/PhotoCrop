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
from PySide6.QtCore import (
    QPointF,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
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
    files_dropped = Signal(list)      # 拖拽导入的文件路径列表

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
        self._min_drag_size = 20  # 设计规范：仅在宽高都 > 20px 时显示

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

        # 拖拽导入支持
        self.setAcceptDrops(True)
        self._drag_overlay: QWidget | None = None

        # Loading 状态指示器
        self._loading_overlay: QWidget | None = None
        self._spinner_angle: float = 0
        self._spinner_timer: QTimer | None = None

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
        self.reset_undo()
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
        """显示图像（不清空撤销历史 — 由调用方管理）"""
        # 清除旧裁剪框
        for item in self._crop_items[:]:
            self._scene.removeItem(item)
        self._crop_items.clear()

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
        self.reset_undo()
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

    def push_undo_state(self) -> None:
        """将当前裁剪框状态推入撤销栈（公共接口）"""
        self._push_undo_state()

    # ---- 公共 Undo API（供 MainWindow / Controller 调用） ----

    def get_undo_snapshot(self) -> str:
        """获取撤销管理器的完整序列化快照（JSON 字符串）"""
        return self._undo_manager.serialize()

    def restore_undo_snapshot(self, snapshot: str | list) -> None:
        """从序列化快照恢复撤销/重做栈"""
        self._undo_manager.deserialize(snapshot)

    def reset_undo(self) -> None:
        """清空撤销历史并推入空初始帧"""
        self._undo_manager.clear()
        self._undo_manager.push_state([])

    def restore_rects_from_list(self, rects: list[CropRect]) -> None:
        """用给定的 CropRect 列表替换当前所有裁剪框（公共接口）"""
        self._restore_rects(rects)

    def scene_rect(self) -> QRectF:
        """返回场景矩形（公共接口）"""
        return self._scene.sceneRect()

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return self._undo_manager.can_undo()

    def can_redo(self) -> bool:
        """是否可以重做"""
        return self._undo_manager.can_redo()

    def clear_scene_selection(self) -> None:
        """清除场景中所有选中项"""
        self._scene.clearSelection()

    def remove_crop_item(self, item: CropItem) -> None:
        """移除指定裁剪框（公共接口，含 undo 推入和信号通知）"""
        if item in self._crop_items:
            self._crop_items.remove(item)
        if item.scene():
            self._scene.removeItem(item)
        self._push_undo_state()
        self.rects_changed.emit()

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
                # 设计规范：1.5px dashed accent, background selected_bg, 圆角 2px
                from photocrop.ui.theme import theme as _t
                self._temp_rect = self._scene.addRect(
                    QRectF(self._draw_start, end).normalized(),
                    QPen(QColor(_t.colors.accent), 1.5, Qt.PenStyle.DashLine),
                    QBrush(QColor(_t.colors.selected_bg)),
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

    # ---- 拖拽导入 ----

    SUPPORTED_FORMATS = {
        ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".pdf",
    }

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """拖拽进入画布时显示半透明遮罩"""
        mime = event.mimeData()
        if mime.hasUrls():
            # 检查是否有支持的文件格式
            urls = mime.urls()
            has_supported = any(
                Path(u.toLocalFile()).suffix.lower() in self.SUPPORTED_FORMATS
                for u in urls if u.isLocalFile()
            )
            if has_supported:
                event.acceptProposedAction()
                self._show_drag_overlay(valid=True)
                return
            else:
                event.acceptProposedAction()
                self._show_drag_overlay(valid=False)
                return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """持续接受拖拽"""
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        """拖拽离开时移除遮罩"""
        self._hide_drag_overlay()

    def dropEvent(self, event: QDropEvent) -> None:
        """拖拽放下时提取文件路径并导入"""
        self._hide_drag_overlay()
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        paths = []
        for url in mime.urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in self.SUPPORTED_FORMATS:
                    paths.append(str(p))

        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()

    def _show_drag_overlay(self, valid: bool = True) -> None:
        """显示拖拽遮罩（设计规范：半透明 + 虚线框 + 图标 + 文字）"""
        if self._drag_overlay is not None:
            self._hide_drag_overlay()

        from photocrop.ui.icons import get_icon
        from photocrop.ui.theme import FONT_FAMILY, FontSize

        overlay = QWidget(self.viewport())
        overlay.setGeometry(self.viewport().rect())
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 虚线框容器
        box = QWidget()
        box.setFixedSize(340, 140)
        accent = "#000000" if valid else "#CC0000"
        box.setStyleSheet(
            f"border: 2px dashed {accent};"
            f"border-radius: 8px;"
            f"background: rgba({'0,0,0' if valid else '204,0,0'}, 0.05);"
            f"padding: 32px 48px;"
        )
        box_layout = QVBoxLayout(box)
        box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.setSpacing(8)

        # 图标（使用 SVG）
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_name = "upload" if valid else "x"
        icon_pixmap = get_icon(icon_name, accent).pixmap(20, 20)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setStyleSheet("border: none; background: transparent;")
        box_layout.addWidget(icon_label)

        text = "Drop images here to import" if valid else "Unsupported file format"
        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(
            f"font-size: {FontSize.BODY}px; color: {accent}; "
            f"border: none; background: transparent; font-family: {FONT_FAMILY};"
        )
        box_layout.addWidget(text_label)

        layout.addWidget(box)

        # 设计规范：遮罩背景 theme["accent"] opacity 0.1
        from photocrop.ui.theme import theme as _t
        accent_color = _t.colors.accent
        overlay.setStyleSheet(f"background: {accent_color}; opacity: 0.1;")
        overlay.show()
        self._drag_overlay = overlay

        # 脉冲动画（opacity 0.7↔0.9, 1.5s infinite）
        if valid:
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            eff = QGraphicsOpacityEffect(overlay)
            eff.setOpacity(0.7)
            overlay.setGraphicsEffect(eff)
            self._drag_pulse_effect = eff
            self._drag_pulse_timer = QTimer()
            self._drag_pulse_alpha = 0.7
            self._drag_pulse_dir = 1
            def pulse_drag():
                self._drag_pulse_alpha += self._drag_pulse_dir * 0.005
                if self._drag_pulse_alpha >= 0.9:
                    self._drag_pulse_dir = -1
                elif self._drag_pulse_alpha <= 0.7:
                    self._drag_pulse_dir = 1
                eff.setOpacity(self._drag_pulse_alpha)
            self._drag_pulse_timer.timeout.connect(pulse_drag)
            self._drag_pulse_timer.start(50)

    def _hide_drag_overlay(self) -> None:
        """隐藏拖拽遮罩"""
        if hasattr(self, '_drag_pulse_timer') and self._drag_pulse_timer is not None:
            self._drag_pulse_timer.stop()
            self._drag_pulse_timer = None
        if self._drag_overlay is not None:
            self._drag_overlay.hide()
            self._drag_overlay.deleteLater()
            self._drag_overlay = None

    # ---- Loading 状态指示器 ----

    def show_loading(self, message: str = "Loading image...") -> None:
        """显示 loading 遮罩（设计规范：半透明背景 + spinner + 文字脉冲）"""
        self.hide_loading()

        from photocrop.ui.theme import FONT_FAMILY, FontSize

        overlay = QWidget(self.viewport())
        overlay.setGeometry(self.viewport().rect())
        # 设计规范：theme["bg"] 50% opacity
        from photocrop.ui.theme import theme as _theme
        bg_color = _theme.colors.bg
        overlay.setStyleSheet(
            f"background: {bg_color}; opacity: 0.5;"
        )

        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        # Spinner（自绘旋转圆弧）
        self._spinner_label = QLabel()
        self._spinner_label.setFixedSize(24, 24)
        self._spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spinner_label, 0, Qt.AlignmentFlag.AlignCenter)

        # 提示文字（脉冲动画）
        text_label = QLabel(message)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(
            f"font-size: {FontSize.BODY}px; color: #666666; background: transparent; "
            f"font-family: {FONT_FAMILY};"
        )
        layout.addWidget(text_label)

        overlay.show()
        self._loading_overlay = overlay

        # 启动 spinner 旋转动画（1s per rotation, linear）
        self._spinner_angle = 0
        self._spinner_timer = QTimer()
        self._spinner_timer.timeout.connect(self._rotate_spinner)
        self._spinner_timer.start(33)  # ~30fps

        # 文字脉冲动画（2s: opacity 1→0.5→1）
        self._text_pulse_timer = QTimer()
        self._text_pulse_alpha = 1.0
        self._text_pulse_dir = -1
        def pulse_text():
            self._text_pulse_alpha += self._text_pulse_dir * 0.025
            if self._text_pulse_alpha <= 0.5:
                self._text_pulse_dir = 1
            elif self._text_pulse_alpha >= 1.0:
                self._text_pulse_dir = -1
            text_label.setStyleSheet(
                f"font-size: {FontSize.BODY}px; color: #666666; background: transparent; "
                f"font-family: {FONT_FAMILY}; opacity: {self._text_pulse_alpha:.2f};"
            )
        self._text_pulse_timer.timeout.connect(pulse_text)
        self._text_pulse_timer.start(50)  # 2s cycle = 40 steps × 50ms

    def _rotate_spinner(self) -> None:
        """旋转 spinner（自绘弧线）"""
        self._spinner_angle = (self._spinner_angle + 6) % 360
        if hasattr(self, '_spinner_label') and self._spinner_label:
            from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#000000"), 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.translate(12, 12)
            painter.rotate(self._spinner_angle)
            painter.drawArc(-9, -9, 18, 18, 0, 270 * 16)
            painter.end()
            self._spinner_label.setPixmap(pixmap)

    def hide_loading(self) -> None:
        """隐藏 loading 遮罩"""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if hasattr(self, '_text_pulse_timer') and self._text_pulse_timer is not None:
            self._text_pulse_timer.stop()
            self._text_pulse_timer = None
        if self._loading_overlay is not None:
            self._loading_overlay.hide()
            self._loading_overlay.deleteLater()
            self._loading_overlay = None

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
