"""
MainWindow — PhotoCrop 主窗口

设计规范（v0.6.0 — 1:1 复刻 HTML 参考）：
- Toolbar 44px：Brand + Actions + 居中 Page Nav + 右侧 View/Theme/Export
- 左面板 220px：图像列表
- 中间 Canvas / SingleView
- 右面板 220px：Crop Options + Extracted Images
- 底栏 28px：版本状态 + 缩放控制
- Light/Dark 双主题，350ms 过渡
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from PIL import Image
from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from photocrop import __version__
from photocrop.engine.core import detect_rectangles
from photocrop.export.cropper import export_photo
from photocrop.ui.canvas import CropCanvas
from photocrop.ui.crop_options_panel import CropOptionsPanel
from photocrop.ui.export_dialog import ExportDialog
from photocrop.ui.extracted_images_panel import ExtractedImagesPanel
from photocrop.ui.icons import get_icon
from photocrop.ui.image_list_panel import ImageListPanel
from photocrop.ui.session import ImageSession
from photocrop.ui.single_view_panel import SingleViewPanel
from photocrop.ui.theme import theme
from photocrop.utils.crop_rect import CropRect

# ============================================================
# 常量
# ============================================================

FONT_DISPLAY = (
    "SF Pro Display, Helvetica Neue, Helvetica, Arial, sans-serif"
)
FONT_BODY = (
    "SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif"
)

DETECTOR_OPTIONS = [
    ("CV（默认）", "cv"),
    ("增强 CV", "enhanced-cv"),
    ("组合检测", "combined"),
    ("YOLO-World", "yolo-world"),
]


# ============================================================
# BrandIcon — 左上角双层方框品牌图标
# ============================================================

class BrandIcon(QWidget):
    """双层方框品牌图标"""

    def __init__(self, size: int = 18, opacity: float = 1.0, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._opacity = opacity

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        c = theme.colors.text
        pen = QPen(QColor(c), 2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # 外框
        s = self.width() - 2
        p.drawRect(1, 1, s, s)
        # 内框（偏移 3px，半透明）
        pen.setColor(QColor(c))
        pen.setWidthF(1.5)
        p.setOpacity(self._opacity * 0.5)
        p.setPen(pen)
        inner_offset = self.width() // 6
        inner_size = self.width() - inner_offset * 2
        p.drawRect(inner_offset, inner_offset, inner_size, inner_size)
        p.end()


# ============================================================
# PDF 批量检测后台任务
# ============================================================

class PageDetectionSignals(QObject):
    page_done = Signal(int, list)
    error = Signal(str)


class PageDetectionTask(QRunnable):

    def __init__(self, page_idx: int, page_img: Image.Image,
                 detector: str, max_count: int):
        super().__init__()
        self.page_idx = page_idx
        self.page_img = page_img.copy()
        self.detector = detector
        self.max_count = max_count
        self.signals = PageDetectionSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._cancelled:
            return
        try:
            rects = detect_rectangles(
                self.page_img, detector=self.detector,
                max_count=self.max_count,
            )
            self.signals.page_done.emit(self.page_idx, rects)
        except Exception as e:
            self.signals.error.emit(f"Page {self.page_idx}: {e}")
            self.signals.page_done.emit(self.page_idx, [])


# ============================================================
# MainWindow
# ============================================================

class MainWindow(QMainWindow):
    """PhotoCrop 主窗口

    布局：
    ┌──────────────────────────────────────────────────┐
    │ [Brand] [Actions]      [Page Nav]   [View][☀][Export] │ 44px
    ├───────┬──────────────────────────────┬───────────┤
    │ IMG   │       CANVAS / SINGLE       │ CROP OPT  │
    │ LIST  │         (centered)          │ EXTRACTED │
    │ 220px │                              │ 220px     │
    ├───────┴──────────────────────────────┴───────────┤
    │ Status                     [Zoom | Fit | 1:1]   │ 28px
    └──────────────────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PhotoCrop")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 900)

        # 多图像会话管理
        self._sessions: dict = {}
        self._current_key: str | None = None

        # 防抖定时器
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_button_states)

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._apply_theme()
        self._update_button_states()

    # ================================================================
    # UI 构建
    # ================================================================

    def _setup_ui(self) -> None:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── 工具栏 44px ──
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(44)
        self._toolbar.setObjectName("toolbar")
        self._build_toolbar(self._toolbar)
        outer_layout.addWidget(self._toolbar)

        # ── 主体 ──
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 左面板
        self._image_list_panel = ImageListPanel()
        body_layout.addWidget(self._image_list_panel)

        # 中间: EmptyState / Canvas / SingleView
        self._view_stack = QStackedWidget()

        # 空状态页（index 0）
        self._empty_state = self._build_empty_state()
        self._view_stack.addWidget(self._empty_state)

        # Canvas（index 1）
        self._canvas = CropCanvas(self)
        self._view_stack.addWidget(self._canvas)

        # SingleView（index 2）
        self._single_view = SingleViewPanel()
        self._view_stack.addWidget(self._single_view)

        body_layout.addWidget(self._view_stack, 1)

        # 右面板
        right_panel = QWidget()
        right_panel.setFixedWidth(220)
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._crop_options_panel = CropOptionsPanel()
        right_layout.addWidget(self._crop_options_panel)
        self._extracted_panel = ExtractedImagesPanel()
        right_layout.addWidget(self._extracted_panel, 1)
        body_layout.addWidget(right_panel)

        outer_layout.addWidget(body, 1)

        # ── 底栏 28px ──
        self._bottom_bar = QWidget()
        self._bottom_bar.setFixedHeight(28)
        self._bottom_bar.setObjectName("bottomBar")
        self._build_bottom_bar(self._bottom_bar)
        outer_layout.addWidget(self._bottom_bar)

        self.setCentralWidget(outer)
        self._view_mode = 0

    # ---- 工具栏 ----

    def _build_toolbar(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Brand
        self._brand_icon = BrandIcon(size=20)
        layout.addWidget(self._brand_icon)

        self._brand_text = QLabel()
        self._brand_text.setText(
            '<span style="font-weight:300;letter-spacing:0.06em">Photo</span>'
            '<span style="font-weight:600;letter-spacing:0.01em">Crop</span>'
        )
        self._brand_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brand_text.mousePressEvent = lambda _: self._show_empty_state()
        layout.addWidget(self._brand_text)

        # 分隔线
        sep = QWidget()
        sep.setFixedSize(1, 18)
        sep.setObjectName("toolbarSep")
        layout.addWidget(sep)

        # Action 按钮
        self._btn_load = QPushButton("+ Import")
        self._btn_load.setProperty("toolbar", "true")
        layout.addWidget(self._btn_load)

        # 检测器下拉
        self._combo_detector = QComboBox()
        for label, _ in DETECTOR_OPTIONS:
            self._combo_detector.addItem(label)
        self._combo_detector.setCurrentIndex(0)
        self._combo_detector.setFixedWidth(110)
        self._combo_detector.setFixedHeight(28)
        self._combo_detector.setToolTip("选择检测算法")
        layout.addWidget(self._combo_detector)

        self._btn_detect = QPushButton("Detect")
        self._btn_detect.setProperty("toolbar", "true")
        self._btn_detect.setEnabled(False)
        layout.addWidget(self._btn_detect)

        # 最大检测数
        self._spin_max_count = QSpinBox()
        self._spin_max_count.setRange(1, 10)
        self._spin_max_count.setValue(4)
        self._spin_max_count.setFixedWidth(52)
        self._spin_max_count.setFixedHeight(28)
        self._spin_max_count.setToolTip("最大检测数量")
        layout.addWidget(self._spin_max_count)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setProperty("toolbar", "true")
        self._btn_clear.setEnabled(False)
        layout.addWidget(self._btn_clear)

        self._btn_undo = QPushButton("Undo")
        self._btn_undo.setProperty("toolbar", "true")
        layout.addWidget(self._btn_undo)

        self._btn_redo = QPushButton("Redo")
        self._btn_redo.setProperty("toolbar", "true")
        layout.addWidget(self._btn_redo)

        # 居中 Page Nav（用弹性空间定位）
        layout.addStretch()
        self._page_nav_widget = QWidget()
        pn_layout = QHBoxLayout(self._page_nav_widget)
        pn_layout.setContentsMargins(0, 0, 0, 0)
        pn_layout.setSpacing(8)

        self._btn_prev_page = QPushButton()
        self._btn_prev_page.setProperty("toolbar", "true")
        self._btn_prev_page.setProperty("iconOnly", "true")
        self._btn_prev_page.setFixedSize(28, 28)
        self._btn_prev_page.setIconSize(QSize(14, 14))
        pn_layout.addWidget(self._btn_prev_page)

        self._lbl_page_info = QLabel("Page 1 / 1")
        self._lbl_page_info.setProperty("pageInfo", True)
        self._lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pn_layout.addWidget(self._lbl_page_info)

        self._btn_next_page = QPushButton()
        self._btn_next_page.setProperty("toolbar", "true")
        self._btn_next_page.setProperty("iconOnly", "true")
        self._btn_next_page.setFixedSize(28, 28)
        self._btn_next_page.setIconSize(QSize(14, 14))
        pn_layout.addWidget(self._btn_next_page)

        layout.addWidget(self._page_nav_widget)
        self._page_nav_widget.setVisible(False)
        layout.addStretch()

        # 右侧: View Toggle
        self._btn_grid = QPushButton("Grid")
        self._btn_grid.setCheckable(True)
        self._btn_grid.setChecked(False)
        self._btn_grid.setProperty("toolbar", "true")
        layout.addWidget(self._btn_grid)

        self._btn_single = QPushButton("Single")
        self._btn_single.setCheckable(True)
        self._btn_single.setProperty("toolbar", "true")
        layout.addWidget(self._btn_single)

        # 主题切换
        self._btn_theme = QPushButton()
        self._btn_theme.setFixedSize(28, 28)
        self._btn_theme.setIconSize(QSize(16, 16))
        self._btn_theme.setProperty("toolbar", "true")
        self._btn_theme.setProperty("iconOnly", "true")
        self._btn_theme.setToolTip("切换 Light/Dark 主题")
        layout.addWidget(self._btn_theme)

        # Export
        self._btn_export = QPushButton("Export")
        self._btn_export.setProperty("export_btn", "true")
        self._btn_export.setEnabled(False)
        layout.addWidget(self._btn_export)

    # ---- 空状态页 ----

    def _build_empty_state(self) -> QWidget:
        """构建空状态页面（品牌 Logo + 副标题）"""
        page = QWidget()
        page.setObjectName("emptyState")

        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(20)

        # 品牌大图标（半透明）
        icon = BrandIcon(size=48, opacity=0.15)
        v.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)

        # PhotoCrop 大字
        brand = QLabel(
            '<span style="font-size:28px;font-weight:200;letter-spacing:0.08em">Photo</span>'
            '<span style="font-size:28px;font-weight:500;letter-spacing:0.02em">Crop</span>'
        )
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(brand)

        # 副标题
        self._empty_subtitle = QLabel("SCAN & EXTRACT PHOTOS")
        self._empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; "
            "letter-spacing: 0.25em;"
        )
        v.addWidget(self._empty_subtitle)

        return page

    # ---- 底栏 ----

    @property
    def _version(self) -> str:
        return __version__

    def _build_bottom_bar(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._lbl_bottom_status = QLabel(f"PhotoCrop v{__version__} — Ready")
        self._lbl_bottom_status.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px;"
        )
        layout.addWidget(self._lbl_bottom_status)
        layout.addStretch()

        self._lbl_zoom = QLabel("Zoom: 100%")
        self._lbl_zoom.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px;"
        )
        layout.addWidget(self._lbl_zoom)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(24, 20)
        btn_zoom_in.setProperty("toolbar", "true")
        btn_zoom_in.clicked.connect(self._on_zoom_in)
        layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedSize(24, 20)
        btn_zoom_out.setProperty("toolbar", "true")
        btn_zoom_out.clicked.connect(self._on_zoom_out)
        layout.addWidget(btn_zoom_out)

        self._lbl_pipe = QLabel("|")
        self._lbl_pipe.setStyleSheet(f"color: {theme.colors.border_strong}; font-size: 11px;")
        layout.addWidget(self._lbl_pipe)

        btn_fit = QPushButton("Fit")
        btn_fit.setFixedHeight(20)
        btn_fit.setProperty("toolbar", "true")
        btn_fit.clicked.connect(self._on_zoom_fit)
        layout.addWidget(btn_fit)

        btn_1to1 = QPushButton("1:1")
        btn_1to1.setFixedHeight(20)
        btn_1to1.setProperty("toolbar", "true")
        btn_1to1.clicked.connect(self._on_zoom_1to1)
        layout.addWidget(btn_1to1)

    # ================================================================
    # 信号连接
    # ================================================================

    def _connect_signals(self) -> None:
        self._btn_load.clicked.connect(self._on_load)
        self._btn_detect.clicked.connect(self._on_detect)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_undo.clicked.connect(self._on_undo)
        self._btn_redo.clicked.connect(self._on_redo)
        self._btn_prev_page.clicked.connect(self._on_prev_page)
        self._btn_next_page.clicked.connect(self._on_next_page)
        self._btn_grid.clicked.connect(lambda: self._switch_view(self._VIEW_GRID))
        self._btn_single.clicked.connect(lambda: self._switch_view(self._VIEW_SINGLE))
        self._btn_theme.clicked.connect(self._toggle_theme)

        self._canvas.image_loaded.connect(self._on_image_loaded)
        self._canvas.detection_done.connect(self._on_detection_done)
        self._canvas.rects_changed.connect(self._on_rects_changed)
        self._canvas.page_changed.connect(self._on_page_changed)
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.view_single_requested.connect(self._on_view_single_requested)
        self._canvas.zoom_changed.connect(self._update_zoom_label)

        self._crop_options_panel.rect_changed.connect(self._on_crop_options_changed)
        self._crop_options_panel.editing_finished.connect(
            self._on_crop_options_finished
        )
        self._crop_options_panel.aspect_ratio_changed.connect(
            self._on_aspect_ratio_changed
        )

        self._extracted_panel.crop_selected.connect(self._on_extracted_crop_selected)
        self._extracted_panel.crop_delete_requested.connect(
            self._on_extracted_crop_delete
        )

        self._single_view.exit_requested.connect(lambda: self._switch_view(self._VIEW_GRID))
        self._single_view.selection_changed.connect(self._on_single_view_selection)

        self._image_list_panel.image_selected.connect(self._switch_image)
        self._image_list_panel.re_detect_requested.connect(self._on_re_detect)
        self._image_list_panel.remove_requested.connect(self._on_remove_from_list)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._on_load)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._on_detect)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._on_export)
        QShortcut(QKeySequence("Left"), self, activated=self._on_prev_page)
        QShortcut(QKeySequence("Right"), self, activated=self._on_next_page)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._on_redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._on_redo)

    # ================================================================
    # 主题
    # ================================================================

    def _apply_theme(self) -> None:
        c = theme.colors
        # 全局样式表
        self.setStyleSheet(theme.generate_stylesheet())
        # 组件级颜色更新
        self._toolbar.setStyleSheet(
            f"#toolbar {{ background: {c.bg}; border-bottom: 1px solid {c.border}; }}"
        )
        self._bottom_bar.setStyleSheet(
            f"#bottomBar {{ background: {c.bg}; border-top: 1px solid {c.border}; }}"
        )
        self._image_list_panel.set_theme(c)
        self._crop_options_panel.set_theme(c)
        self._extracted_panel.set_theme(c)
        self._single_view.set_theme(c)
        self._canvas.set_theme(c)
        # 触发 BrandIcon 重绘（它在 paintEvent 中读取 theme.colors.text）
        self._brand_icon.update()
        for icon in self._empty_state.findChildren(BrandIcon):
            icon.update()
        # 更新品牌文字颜色
        self._brand_text.setStyleSheet(f"font-family: {FONT_DISPLAY}; font-size: 15px; color: {c.text};")
        # 更新空状态页
        self._empty_state.setStyleSheet(f"background: {c.canvas_bg};")
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; "
            f"letter-spacing: 0.25em; color: {c.text_secondary};"
        )
        # 底栏标签颜色
        self._lbl_bottom_status.setStyleSheet(f"font-family: {FONT_BODY}; font-size: 11px; color: {c.text_secondary};")
        self._lbl_zoom.setStyleSheet(f"font-family: {FONT_BODY}; font-size: 11px; color: {c.text_secondary};")
        self._lbl_pipe.setStyleSheet(f"color: {c.border_strong}; font-size: 11px;")
        # 工具栏分隔线
        for w in self._toolbar.findChildren(QWidget):
            if w.objectName() == "toolbarSep":
                w.setStyleSheet(f"background: {c.border};")
        # 主题按钮图标
        icon_color = c.accent if theme.mode == "light" else c.text
        if theme.mode == "light":
            self._btn_theme.setIcon(get_icon("sun", icon_color))
        else:
            self._btn_theme.setIcon(get_icon("moon", icon_color))
        # 页面导航图标
        self._btn_prev_page.setIcon(get_icon("chevron-left", icon_color))
        self._btn_next_page.setIcon(get_icon("chevron-right", icon_color))
        # Page info
        self._lbl_page_info.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_BODY}; font-size: 13px;")

    def _toggle_theme(self) -> None:
        """切换 Light / Dark 主题"""
        # 动画：不实际做 QPropertyAnimation（QSS 不支持），直接切换
        theme.toggle()
        self._apply_theme()

    # ================================================================
    # 槽函数
    # ================================================================

    @property
    def _selected_detector(self) -> str:
        idx = self._combo_detector.currentIndex()
        if idx < 0 or idx >= len(DETECTOR_OPTIONS):
            idx = 0
        return DETECTOR_OPTIONS[idx][1]

    def _on_load(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片或 PDF", "",
            "所有支持格式 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.pdf);;"
            "图片 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;"
            "PDF (*.pdf);;所有文件 (*)",
        )
        if not paths:
            return
        for path_str in paths:
            self._load_single_file(path_str)
        if paths:
            last_path = paths[-1]
            if Path(last_path).suffix.lower() == ".pdf":
                self._image_list_panel.select_image(f"{last_path}::page_0")
            else:
                self._image_list_panel.select_image(last_path)

    def _load_single_file(self, path_str: str) -> None:
        path = Path(path_str)
        try:
            self._save_current_session()
            is_pdf = path.suffix.lower() == ".pdf"

            if is_pdf:
                from photocrop.export.pdf_reader import pdf_to_images
                thumb_pages = pdf_to_images(path, dpi=72)
                page_count = len(thumb_pages)
                if page_count == 0:
                    raise ValueError("PDF 没有可读取的页面")

                page_thumbs: list[Image.Image] = []
                for _, img in thumb_pages:
                    t = img.copy()
                    t.thumbnail((44, 44), Image.Resampling.LANCZOS)
                    page_thumbs.append(t)

                def page_loader(idx: int) -> Image.Image:
                    import fitz
                    doc = fitz.open(str(path))
                    try:
                        zoom = 200 / 72.0
                        matrix = fitz.Matrix(zoom, zoom)
                        page = doc[idx]
                        pix = page.get_pixmap(matrix=matrix)
                        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    finally:
                        doc.close()

                first_page_img = page_loader(0)
                sess = ImageSession(
                    source_path=path,
                    source_image=first_page_img,
                    crop_rects=[],
                    undo_snapshot=[],
                    is_pdf=True,
                    pdf_page_count=page_count,
                    pdf_page_loader=page_loader,
                    current_pdf_page=0,
                )
                for pg_idx, (_, pg_img) in enumerate(thumb_pages):
                    sess.set_page_preview(pg_idx, pg_img)

                self._sessions[path_str] = sess
                self._current_key = path_str
                self._canvas.load_pil_image(first_page_img)
                self._extracted_panel.set_global_mode(True)

                first_thumb = page_thumbs[0] if page_thumbs else first_page_img.copy()
                self._image_list_panel.add_image(
                    key=path_str, filename=path.name, thumbnail=first_thumb,
                    page_count=page_count, page_thumbnails=page_thumbs,
                )
            else:
                self._current_key = path_str
                self._canvas.load_image(path_str)
                sess = ImageSession(
                    source_path=path,
                    source_image=self._canvas.source_image,
                    crop_rects=[],
                    undo_snapshot=self._canvas._undo_manager.serialize(),
                )
                self._sessions[path_str] = sess
                self._extracted_panel.set_global_mode(False)
                thumb = self._canvas.source_image.copy()
                thumb.thumbnail((100, 100), Image.Resampling.LANCZOS)
                self._image_list_panel.add_image(
                    key=path_str, filename=path.name,
                    thumbnail=thumb, crop_count=0,
                )

            self._update_image_list_panel()

        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法打开文件:\n{e}")

    def _save_current_session(self) -> None:
        if not self._current_key:
            return
        if "::page_" in self._current_key:
            pdf_key, page_str = self._current_key.rsplit("::page_", 1)
            page_idx = int(page_str)
            sess = self._sessions.get(pdf_key)
            if sess is None:
                return
            sess.page_crop_rects[page_idx] = [copy.deepcopy(r) for r in self._canvas.crop_rects]
            sess.page_undo_snapshots[page_idx] = self._canvas._undo_manager.serialize()
        elif self._current_key in self._sessions:
            sess = self._sessions[self._current_key]
            if sess.is_pdf:
                page_idx = sess.current_pdf_page
                sess.page_crop_rects[page_idx] = [copy.deepcopy(r) for r in self._canvas.crop_rects]
                sess.page_undo_snapshots[page_idx] = self._canvas._undo_manager.serialize()
            else:
                sess.crop_rects = [copy.deepcopy(r) for r in self._canvas.crop_rects]
                sess.undo_snapshot = self._canvas._undo_manager.serialize()

    def _switch_image(self, key: str) -> None:
        if key == self._current_key:
            return
        self._save_current_session()

        if "::page_" in key:
            pdf_key, page_str = key.rsplit("::page_", 1)
            page_idx = int(page_str)
            sess = self._sessions.get(pdf_key)
            if sess is None:
                return
            img = sess.get_page_image(page_idx)
            page_rects = list(sess.page_crop_rects.get(page_idx, []))
            page_undo = sess.page_undo_snapshots.get(page_idx)
            sess.current_pdf_page = page_idx
            self._current_key = key
            self._canvas.load_pil_image(img)
            self._canvas._restore_rects(page_rects)
            if page_undo is not None:
                self._canvas._undo_manager.deserialize(page_undo)
            else:
                self._canvas._undo_manager.clear()
                self._canvas._undo_manager.push_state([])
            self._extracted_panel.set_source_image(img)
            self._extracted_panel.set_global_mode(True)
            self._refresh_global_preview(sess, page_idx)
        elif key in self._sessions:
            sess = self._sessions[key]
            crop_rects = list(sess.crop_rects)
            undo_snapshot = sess.undo_snapshot
            self._current_key = key
            self._canvas.load_pil_image(sess.source_image)
            self._canvas._undo_manager.deserialize(undo_snapshot)
            self._canvas._restore_rects(crop_rects)
            self._extracted_panel.set_source_image(sess.source_image)
            self._extracted_panel.set_global_mode(False)
        else:
            return

        # 切换到 Grid View
        if self._view_mode == self._VIEW_EMPTY:
            self._view_mode = self._VIEW_GRID
            self._view_stack.setCurrentIndex(self._VIEW_GRID)
            self._canvas.fitInView(
                self._canvas._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        self._update_button_states()
        self._update_image_list_panel()

    def _on_re_detect(self, key: str) -> None:
        if key not in self._sessions:
            return
        if key != self._current_key:
            self._image_list_panel.select_image(key)
        self._on_detect()

    def _on_remove_from_list(self, key: str) -> None:
        session_key = key
        if "::page_" in key:
            session_key = key.rsplit("::page_", 1)[0]
        if session_key not in self._sessions:
            return
        current_session_key = self._current_key
        if current_session_key and "::page_" in current_session_key:
            current_session_key = current_session_key.rsplit("::page_", 1)[0]
        if session_key == current_session_key:
            keys = list(self._sessions.keys())
            idx = keys.index(session_key)
            if len(keys) > 1:
                next_key = keys[idx - 1] if idx > 0 else keys[1]
                next_sess = self._sessions[next_key]
                if next_sess.is_pdf:
                    self._switch_image(f"{next_key}::page_0")
                else:
                    self._switch_image(next_key)
            else:
                self._current_key = None
                self._canvas.clear_all()
                self._extracted_panel.set_global_mode(False)
                self._switch_view(self._VIEW_EMPTY)
        del self._sessions[session_key]
        self._image_list_panel.remove_image(session_key)
        self._update_image_list_panel()

    def _update_image_list_panel(self) -> None:
        total_crops = 0
        for key, sess in self._sessions.items():
            if sess.is_pdf:
                for page_idx in range(sess.page_count):
                    is_current_page = False
                    if self._current_key == f"{key}::page_{page_idx}":
                        is_current_page = True
                    elif self._current_key == key and page_idx == sess.current_pdf_page:
                        is_current_page = True
                    if is_current_page:
                        count = len(self._canvas.crop_rects)
                    else:
                        count = len(sess.page_crop_rects.get(page_idx, []))
                    self._image_list_panel.update_crop_count(f"{key}::page_{page_idx}", count)
                    total_crops += count
            else:
                if key == self._current_key:
                    count = len(self._canvas.crop_rects)
                else:
                    count = len(sess.crop_rects)
                self._image_list_panel.update_crop_count(key, count)
                total_crops += count
        self._image_list_panel.update_total(len(self._sessions), total_crops)

    def _get_current_pdf_session(self) -> ImageSession | None:
        if not self._current_key or "::page_" not in self._current_key:
            return None
        pdf_key = self._current_key.rsplit("::page_", 1)[0]
        return self._sessions.get(pdf_key)

    def _refresh_global_preview(self, sess: ImageSession, current_page: int = -1) -> None:
        pages_data = []
        for page_idx in range(sess.page_count):
            rects = sess.page_crop_rects.get(page_idx, [])
            try:
                img = sess.get_page_image(page_idx)
            except (RuntimeError, IndexError):
                img = sess.source_image
            pages_data.append((page_idx, img, rects))
        current_rects = list(self._canvas.crop_rects) if current_page >= 0 else None
        self._extracted_panel.refresh_all_pages(
            pages_data, current_page=current_page, current_rects=current_rects,
        )

    def _on_detect(self) -> None:
        detector = self._selected_detector
        max_count = self._spin_max_count.value()
        sess = None
        if self._current_key:
            if "::page_" in self._current_key:
                pdf_key = self._current_key.rsplit("::page_", 1)[0]
                sess = self._sessions.get(pdf_key)
            else:
                sess = self._sessions.get(self._current_key)
        if sess is not None and sess.is_pdf and sess.page_count > 1:
            self._run_batch_detection(sess, detector, max_count)
            return
        self._lbl_bottom_status.setText(f"正在检测（{detector}）...")
        QApplication.processEvents()
        try:
            count = self._canvas.detect(detector=detector, max_count=max_count)
            self._lbl_bottom_status.setText(f"检测到 {count} 个照片")
        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
        except Exception as e:
            QMessageBox.critical(self, "检测失败", str(e))

    def _run_batch_detection(self, sess: ImageSession, detector: str, max_count: int) -> None:
        total = sess.page_count
        for page_idx in range(total):
            sess.page_crop_rects[page_idx] = []
        if self._view_mode != self._VIEW_GRID:
            self._switch_view(self._VIEW_GRID)
        self._extracted_panel.clear_incremental()
        self._extracted_panel.set_global_mode(True)
        progress = QProgressDialog("正在检测所有 PDF 页面...", "取消", 0, total, self)
        progress.setWindowTitle("批量检测")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        self._detect_cancelled = False
        self._detected_pages: set[int] = set()
        pdf_key = str(sess.source_path)

        def on_page_done(page_idx: int, rects: list) -> None:
            if self._detect_cancelled:
                return
            crop_rects = [r for r in rects if isinstance(r, CropRect)]
            sess.page_crop_rects[page_idx] = crop_rects
            page_key = f"{pdf_key}::page_{page_idx}"
            self._image_list_panel.update_crop_count(page_key, len(crop_rects))
            try:
                page_img = sess.get_page_image(page_idx)
                self._extracted_panel.add_page_results(page_idx, page_img, crop_rects)
            except (RuntimeError, IndexError):
                pass
            self._detected_pages.add(page_idx)

        def on_error(msg: str) -> None:
            print(f"[Detection] {msg}")

        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(1)
        self._batch_tasks: list[PageDetectionTask] = []
        for page_idx in range(total):
            try:
                img = sess.get_page_image(page_idx)
            except (RuntimeError, IndexError):
                self._detected_pages.add(page_idx)
                continue
            task = PageDetectionTask(page_idx, img, detector, max_count)
            task.signals.page_done.connect(on_page_done)
            task.signals.error.connect(on_error)
            self._batch_tasks.append(task)
            pool.start(task)

        def check_progress() -> None:
            if self._detect_cancelled:
                return
            done = len(self._detected_pages)
            progress.setValue(done)
            if done < total:
                QTimer.singleShot(100, check_progress)
            else:
                progress.close()
                total_rects = sum(len(sess.page_crop_rects.get(i, [])) for i in range(total))
                self._lbl_bottom_status.setText(f"检测完成: {total} 页, {total_rects} 个裁剪框")
                self._update_image_list_panel()
                current_page = sess.current_pdf_page
                current_rects = sess.page_crop_rects.get(current_page, [])
                self._canvas._restore_rects(current_rects)
                self._canvas._push_undo_state()
                self._refresh_global_preview(sess, current_page)

        QTimer.singleShot(100, check_progress)

        def on_cancel() -> None:
            self._detect_cancelled = True
            for t in self._batch_tasks:
                t.cancel()
            progress.close()
            self._lbl_bottom_status.setText(
                f"批量检测已取消（已完成 {len(self._detected_pages)}/{total} 页）"
            )

        progress.canceled.connect(on_cancel)

    def _on_clear(self) -> None:
        self._canvas.clear_crops()
        self._lbl_bottom_status.setText("已清除所有裁剪框")
        self._update_button_states()
        self._btn_undo.setEnabled(self._canvas._undo_manager.can_undo())
        self._btn_redo.setEnabled(self._canvas._undo_manager.can_redo())
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            current_page = -1
            if "::page_" in (self._current_key or ""):
                current_page = int(self._current_key.rsplit("::page_", 1)[1])
                pdf_sess.page_crop_rects[current_page] = []
            self._refresh_global_preview(pdf_sess, current_page)

    def _on_export(self) -> None:
        self._save_current_session()
        current_crops = len(self._canvas.crop_rects)
        total_crops = 0
        for _key, sess in self._sessions.items():
            if sess.is_pdf:
                for page_idx in range(sess.page_count):
                    total_crops += len(sess.page_crop_rects.get(page_idx, []))
            else:
                total_crops += len(sess.crop_rects)
        if current_crops == 0 and total_crops == 0:
            QMessageBox.information(self, "导出", "没有裁剪框可以导出")
            return
        dialog = ExportDialog(current_crops, total_crops, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        config = dialog.get_export_config()
        output_dir = config["output_dir"]
        if not output_dir:
            QMessageBox.warning(self, "导出", "请选择输出目录")
            return
        suffix = config["suffix"]
        quality = config["quality"]
        max_w = config["max_width"]
        max_h = config["max_height"]
        auto_rotate = config["auto_rotate"]
        trim_white = config["trim_white"]
        template = config.get("template", "{name}_p{page}_{index:02d}.{ext}")
        scope = config["scope"]
        exported = 0
        errors = []

        if scope == "page":
            rects = self._canvas.crop_rects
            source_img = self._canvas.source_image
            source_name = "image"
            page_num = 1
            if self._canvas.source_path:
                source_name = self._canvas.source_path.stem
            elif self._current_key and "::page_" in self._current_key:
                pdf_key, page_str = self._current_key.rsplit("::page_", 1)
                page_num = int(page_str) + 1
                pdf_sess = self._sessions.get(pdf_key)
                if pdf_sess:
                    source_name = pdf_sess.source_path.stem
            for i, rect in enumerate(rects):
                out_name = self._fill_template(template, source_name, page_num, i + 1, suffix.lstrip("."))
                out_path = output_dir / out_name
                try:
                    export_photo(source_img, rect, out_path, auto_rotate=auto_rotate,
                                 trim_white=trim_white, quality=quality, max_width=max_w, max_height=max_h)
                    exported += 1
                except Exception as e:
                    errors.append(f"#{i + 1}: {e}")
        else:
            for key, sess in self._sessions.items():
                source_name = sess.source_path.stem
                if sess.is_pdf:
                    for page_idx in range(sess.page_count):
                        rects = sess.page_crop_rects.get(page_idx, [])
                        try:
                            source_img = sess.get_page_image(page_idx)
                        except Exception:
                            source_img = None
                        if not rects or source_img is None:
                            continue
                        for i, rect in enumerate(rects):
                            out_name = self._fill_template(template, source_name, page_idx + 1, i + 1, suffix.lstrip("."))
                            out_path = output_dir / out_name
                            try:
                                export_photo(source_img, rect, out_path, auto_rotate=auto_rotate,
                                             trim_white=trim_white, quality=quality, max_width=max_w, max_height=max_h)
                                exported += 1
                            except Exception as e:
                                errors.append(f"{source_name} p{page_idx + 1} #{i + 1}: {e}")
                else:
                    if key == self._current_key:
                        rects = self._canvas.crop_rects
                        source_img = self._canvas.source_image
                    else:
                        rects = sess.crop_rects
                        source_img = sess.source_image
                    for i, rect in enumerate(rects):
                        out_name = self._fill_template(template, source_name, 1, i + 1, suffix.lstrip("."))
                        out_path = output_dir / out_name
                        try:
                            export_photo(source_img, rect, out_path, auto_rotate=auto_rotate,
                                         trim_white=trim_white, quality=quality, max_width=max_w, max_height=max_h)
                            exported += 1
                        except Exception as e:
                            errors.append(f"{source_name} #{i + 1}: {e}")

        msg = f"成功导出 {exported} 张照片\n→ {output_dir}"
        if errors:
            msg += f"\n\n失败 {len(errors)} 张:\n" + "\n".join(errors)
        QMessageBox.information(self, "导出完成", msg)
        self._lbl_bottom_status.setText(f"导出完成: {exported} 张 → {output_dir}")

    def _on_prev_page(self) -> None:
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None:
            prev_page = self._get_sibling_page_key(-1)
            if prev_page:
                self._image_list_panel.select_image(prev_page)
                self._switch_image(prev_page)
            return
        self._canvas.prev_page()

    def _on_next_page(self) -> None:
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None:
            next_page = self._get_sibling_page_key(1)
            if next_page:
                self._image_list_panel.select_image(next_page)
                self._switch_image(next_page)
            return
        self._canvas.next_page()

    def _get_sibling_page_key(self, offset: int) -> str | None:
        if not self._current_key or "::page_" not in self._current_key:
            return None
        pdf_key, page_str = self._current_key.rsplit("::page_", 1)
        page_idx = int(page_str) + offset
        sess = self._sessions.get(pdf_key)
        if sess is None or page_idx < 0 or page_idx >= sess.page_count:
            return None
        return f"{pdf_key}::page_{page_idx}"

    def _on_undo(self) -> None:
        self._canvas.undo()
        self._update_button_states()

    def _on_redo(self) -> None:
        self._canvas.redo()
        self._update_button_states()

    def _on_selection_changed(self) -> None:
        selected = self._canvas.selected_items
        if not selected:
            return
        rect = selected[-1].crop_rect
        img_size = (0, 0)
        if self._canvas.source_image:
            img_size = self._canvas.source_image.size
        self._crop_options_panel.set_selected_rect(rect, img_size)

    def _on_crop_options_changed(self) -> None:
        for item in self._canvas.selected_items:
            item._sync_from_rect()
            item.update()
        self._canvas.rects_changed.emit()

    def _on_crop_options_finished(self) -> None:
        self._canvas._push_undo_state()

    def _on_aspect_ratio_changed(self, ratio: float) -> None:
        for item in self._canvas.selected_items:
            if ratio == 0.0:
                item.aspect_ratio_lock = None
            elif ratio == -1.0:
                if item.crop_rect.height > 0:
                    item.aspect_ratio_lock = item.crop_rect.width / item.crop_rect.height
            else:
                item.aspect_ratio_lock = ratio

    def _on_extracted_crop_selected(self, index: int) -> None:
        if self._extracted_panel._global_mode:
            ref = self._extracted_panel.get_page_and_index(index)
            if ref is None:
                return
            pdf_sess = self._get_current_pdf_session()
            if pdf_sess is None:
                return
            pdf_key = str(pdf_sess.source_path)
            target_key = f"{pdf_key}::page_{ref.page_idx}"
            local_idx = ref.local_idx

            def _do_select() -> None:
                items = self._canvas.crop_items
                if 0 <= local_idx < len(items):
                    self._canvas._scene.clearSelection()
                    items[local_idx].setSelected(True)

            if self._current_key != target_key:
                self._image_list_panel.select_image(target_key)
                self._switch_image(target_key)
                QTimer.singleShot(0, _do_select)
            else:
                _do_select()
        else:
            items = self._canvas.crop_items
            if 0 <= index < len(items):
                self._canvas._scene.clearSelection()
                items[index].setSelected(True)

    def _on_extracted_crop_delete(self, index: int) -> None:
        if self._extracted_panel._global_mode:
            ref = self._extracted_panel.get_page_and_index(index)
            if ref is None:
                return
            pdf_sess = self._get_current_pdf_session()
            if pdf_sess is None:
                return
            pdf_key = str(pdf_sess.source_path)
            target_key = f"{pdf_key}::page_{ref.page_idx}"
            local_idx = ref.local_idx

            def _do_delete() -> None:
                items = self._canvas.crop_items
                if 0 <= local_idx < len(items):
                    item = items[local_idx]
                    if item in self._canvas._crop_items:
                        self._canvas._crop_items.remove(item)
                    if item.scene():
                        self._canvas._scene.removeItem(item)
                    self._canvas._push_undo_state()
                    self._canvas.rects_changed.emit()

            if self._current_key != target_key:
                self._image_list_panel.select_image(target_key)
                self._switch_image(target_key)
                QTimer.singleShot(0, _do_delete)
            else:
                _do_delete()
        else:
            items = self._canvas.crop_items
            if 0 <= index < len(items):
                item = items[index]
                if item in self._canvas._crop_items:
                    self._canvas._crop_items.remove(item)
                if item.scene():
                    self._canvas._scene.removeItem(item)
                self._canvas._push_undo_state()
                self._canvas.rects_changed.emit()

    def _on_image_loaded(self) -> None:
        self._update_button_states()
        # 从空状态切换到 Grid View
        was_empty = self._view_mode == self._VIEW_EMPTY
        if was_empty:
            self._view_mode = self._VIEW_GRID
            self._view_stack.setCurrentIndex(self._VIEW_GRID)
            # 切换到可见视图后必须重新适配，否则图片显示 1-3% 极小
            self._canvas.fitInView(
                self._canvas._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        self._extracted_panel.set_source_image(self._canvas.source_image)

        # PDF 页面导航（从 session 判断，而非 canvas.total_pages）
        pdf_sess = self._get_current_pdf_session()
        is_pdf = pdf_sess is not None and pdf_sess.page_count > 1
        self._page_nav_widget.setVisible(is_pdf)

        img_count = len(self._sessions)
        crop_count = len(self._canvas.crop_rects)
        if is_pdf:
            self._lbl_bottom_status.setText(
                f"PhotoCrop v{__version__} — {img_count} images, PDF {pdf_sess.page_count} pages — Ready"
            )
        elif crop_count > 0:
            self._lbl_bottom_status.setText(
                f"PhotoCrop v{__version__} — {img_count} images, {crop_count} crops — Ready"
            )
        else:
            self._lbl_bottom_status.setText(
                f"PhotoCrop v{__version__} — {img_count} images — Ready"
            )

    def _on_detection_done(self, count: int) -> None:
        self._update_button_states()
        self._update_image_list_panel()
        # 更新撤销按钮（检测完后 undo stack 有变化）
        self._btn_undo.setEnabled(self._canvas._undo_manager.can_undo())
        self._btn_redo.setEnabled(self._canvas._undo_manager.can_redo())

    def _on_rects_changed(self) -> None:
        self._update_timer.start(50)
        count = len(self._canvas.crop_rects)
        img_count = len(self._sessions)
        if count > 0:
            self._lbl_bottom_status.setText(
                f"PhotoCrop v{__version__} — {img_count} images, {count} crops — Ready"
            )
        else:
            self._lbl_bottom_status.setText(
                f"PhotoCrop v{__version__} — {img_count} images — Ready"
            )
        self._update_image_list_panel()
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            current_page = -1
            if "::page_" in (self._current_key or ""):
                current_page = int(self._current_key.rsplit("::page_", 1)[1])
                pdf_sess.page_crop_rects[current_page] = [copy.deepcopy(r) for r in self._canvas.crop_rects]
            pages_data = list(self._extracted_panel._all_pages_data)
            for i, (pg_idx, img, _) in enumerate(pages_data):
                if pg_idx == current_page:
                    pages_data[i] = (pg_idx, img, list(self._canvas.crop_rects))
                    break
            self._extracted_panel.refresh_all_pages(
                pages_data, current_page=current_page,
                current_rects=list(self._canvas.crop_rects),
            )
        else:
            self._extracted_panel.refresh(self._canvas.crop_rects)

    def _on_page_changed(self, current: int, total: int) -> None:
        self._lbl_page_info.setText(f"Page {current + 1} / {total}")
        self._update_button_states()
        self._btn_prev_page.setEnabled(current > 0)
        self._btn_next_page.setEnabled(current < total - 1)

    def _update_button_states(self) -> None:
        has_image = self._canvas.source_image is not None
        has_rects = len(self._canvas.crop_rects) > 0
        self._btn_detect.setEnabled(has_image)
        self._btn_clear.setEnabled(has_rects)
        self._btn_export.setEnabled(has_rects)
        self._btn_undo.setEnabled(self._canvas._undo_manager.can_undo())
        self._btn_redo.setEnabled(self._canvas._undo_manager.can_redo())

    # ---- 视图切换 ----
    # 视图索引：0=Empty  1=Grid(Canvas)  2=Single

    _VIEW_EMPTY = 0
    _VIEW_GRID = 1
    _VIEW_SINGLE = 2

    def _switch_view(self, mode: int) -> None:
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._view_stack.setCurrentIndex(mode)
        self._btn_grid.setChecked(mode == self._VIEW_GRID)
        self._btn_single.setChecked(mode == self._VIEW_SINGLE)
        if mode == self._VIEW_SINGLE and self._canvas.source_image:
            self._single_view.set_data(self._canvas.source_image, self._canvas.crop_rects)

    def _on_view_single_requested(self, index: int) -> None:
        self._switch_view(self._VIEW_SINGLE)
        self._single_view.select_crop(index)

    def _on_single_view_selection(self, index: int) -> None:
        items = self._canvas.crop_items
        if 0 <= index < len(items):
            self._canvas._scene.clearSelection()
            items[index].setSelected(True)

    # ---- 缩放 ----

    def _on_zoom_in(self) -> None:
        self._canvas.scale(1.15, 1.15)
        self._update_zoom_label()

    def _on_zoom_out(self) -> None:
        self._canvas.scale(1 / 1.15, 1 / 1.15)
        self._update_zoom_label()

    def _on_zoom_fit(self) -> None:
        if self._canvas.source_image:
            self._canvas.fitInView(self._canvas._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._update_zoom_label()

    def _on_zoom_1to1(self) -> None:
        self._canvas.resetTransform()
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        m = self._canvas.transform().m11()
        pct = int(m * 100)
        self._lbl_zoom.setText(f"Zoom: {pct}%")

    # ---- 空状态 ----

    def _show_empty_state(self) -> None:
        """点击品牌 Logo 显示空状态"""
        self._switch_view(self._VIEW_EMPTY)

    # ---- 工具方法 ----

    @staticmethod
    def _fill_template(template: str, source_name: str,
                       page_num: int, index: int, ext: str) -> str:
        out = template.replace("{name}", source_name) \
                      .replace("{page}", str(page_num)) \
                      .replace("{ext}", ext)
        out = re.sub(
            r'\{index(?::([^}]+))?\}',
            lambda m: format(index, m.group(1) or "d"),
            out,
        )
        if "{index" not in template:
            if "." in out:
                base, dot_ext = out.rsplit(".", 1)
                out = f"{base}_{index:02d}.{dot_ext}"
            else:
                out = f"{out}_{index:02d}"
        return out
