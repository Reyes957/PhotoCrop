"""
MainWindow — PhotoCrop 主窗口（Phase 4：纯 UI 布局层）

所有业务逻辑委托给 Controller：
- SessionController：Session 加载/切换/保存/删除
- DetectionController：单图/批量检测
- ExportController：导出
- ThemeController：主题切换
- ViewCoordinator：视图切换
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
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
from photocrop.ui.canvas import CropCanvas
from photocrop.ui.controllers.detection_controller import DetectionController
from photocrop.ui.controllers.export_controller import ExportController
from photocrop.ui.controllers.session_controller import SessionController
from photocrop.ui.controllers.theme_controller import ThemeController
from photocrop.ui.controllers.view_coordinator import ViewCoordinator
from photocrop.ui.crop_options_panel import CropOptionsPanel
from photocrop.ui.export_dialog import ExportDialog
from photocrop.ui.extracted_images_panel import ExtractedImagesPanel
from photocrop.ui.icons import get_colored_svg_path, get_icon
from photocrop.ui.image_list_panel import ImageListPanel
from photocrop.ui.single_view_panel import SingleViewPanel
from photocrop.ui.state import AppState, SessionState
from photocrop.ui.theme import theme
from photocrop.ui.toast import show_toast

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

DETECTOR_TOOLTIPS = {
    "cv": "CV (Default): Fast edge-based detection. Best for well-separated photos on clean backgrounds.",
    "enhanced-cv": "Enhanced CV: Improved edge detection with noise filtering. Better for low-quality scans.",
    "combined": "Combined: Uses both edge detection and contour analysis. Slower but more accurate.",
    "yolo-world": "YOLO-World: AI-powered object detection. Best for complex layouts and mixed content.",
}


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
        s = self.width() - 2
        p.drawRect(1, 1, s, s)
        pen.setColor(QColor(c))
        pen.setWidthF(1.5)
        p.setOpacity(self._opacity * 0.5)
        p.setPen(pen)
        inner_offset = self.width() // 6
        inner_size = self.width() - inner_offset * 2
        p.drawRect(inner_offset, inner_offset, inner_size, inner_size)
        p.end()


# ============================================================
# MainWindow
# ============================================================

class MainWindow(QMainWindow):
    """PhotoCrop 主窗口 — 纯 UI 布局层，所有业务逻辑委托给 Controller"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"PhotoCrop {__version__}")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 900)

        # 1. 状态层
        self._app_state = AppState()

        # 2. 控制器层
        self._session_ctrl = SessionController(self._app_state)
        self._detect_ctrl = DetectionController(self._app_state)
        self._export_ctrl = ExportController(self._app_state)
        self._theme_ctrl = ThemeController()

        # 3. UI 构建
        self._setup_ui()

        # 4. 视图协调器（UI 构建后初始化，需要引用 widget）
        self._view_coord = ViewCoordinator(
            self._app_state, self._view_stack,
            self._btn_grid, self._btn_single,
        )

        # 5. 信号连接
        self._connect_signals()
        self._setup_shortcuts()

        # 6. 主题初始化
        self._theme_ctrl.subscribe(self._on_theme_changed)
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

        # 工具栏 44px
        self._toolbar = QWidget()
        self._toolbar.setFixedHeight(44)
        self._toolbar.setObjectName("toolbar")
        self._build_toolbar(self._toolbar)
        outer_layout.addWidget(self._toolbar)

        # 主体
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._image_list_panel = ImageListPanel()
        body_layout.addWidget(self._image_list_panel)

        self._view_stack = QStackedWidget()
        self._empty_state = self._build_empty_state()
        self._canvas = CropCanvas(self)
        self._single_view = SingleViewPanel()
        self._view_stack.addWidget(self._empty_state)
        self._view_stack.addWidget(self._canvas)
        self._view_stack.addWidget(self._single_view)
        body_layout.addWidget(self._view_stack, 1)

        right_panel = QWidget()
        right_panel.setFixedWidth(220)
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._crop_options_panel = CropOptionsPanel()
        right_layout.addWidget(self._crop_options_panel)

        # 分隔线
        right_sep = QWidget()
        right_sep.setFixedHeight(1)
        right_sep.setObjectName("rightPanelSep")
        right_layout.addWidget(right_sep)

        self._extracted_panel = ExtractedImagesPanel()
        right_layout.addWidget(self._extracted_panel, 1)
        body_layout.addWidget(right_panel)

        outer_layout.addWidget(body, 1)

        # 底栏 36px
        self._bottom_bar = QWidget()
        self._bottom_bar.setFixedHeight(36)
        self._bottom_bar.setObjectName("bottomBar")
        self._build_bottom_bar(self._bottom_bar)
        outer_layout.addWidget(self._bottom_bar)

        self.setCentralWidget(outer)

    def _build_toolbar(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._brand_icon = BrandIcon(size=20)
        layout.addWidget(self._brand_icon)

        self._brand_text = QLabel(
            '<span style="font-weight:300;letter-spacing:0.06em">Photo</span>'
            '<span style="font-weight:600;letter-spacing:0.01em">Crop</span>'
        )
        self._brand_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brand_text.mousePressEvent = lambda _: self._view_coord.show_empty()
        layout.addWidget(self._brand_text)

        sep = QWidget()
        sep.setFixedSize(1, 18)
        sep.setObjectName("toolbarSep")
        layout.addWidget(sep)

        self._btn_load = QPushButton("+ Import")
        self._btn_load.setProperty("toolbar", "true")
        layout.addWidget(self._btn_load)

        self._combo_detector = QComboBox()
        for label, _key in DETECTOR_OPTIONS:
            self._combo_detector.addItem(label)
        self._combo_detector.setCurrentIndex(0)
        self._combo_detector.setFixedWidth(120)
        self._combo_detector.setFixedHeight(28)
        self._combo_detector.currentIndexChanged.connect(self._on_detector_changed)
        layout.addWidget(self._combo_detector)
        # 初始 tooltip
        self._update_detector_tooltip()

        self._btn_detect = QPushButton("Detect")
        self._btn_detect.setProperty("toolbar", "true")
        self._btn_detect.setEnabled(False)
        layout.addWidget(self._btn_detect)

        # Max 数量紧挨 Detect，间距 2px 视觉分组
        self._spin_max_count = QSpinBox()
        self._spin_max_count.setRange(1, 10)
        self._spin_max_count.setValue(4)
        self._spin_max_count.setFixedWidth(76)
        self._spin_max_count.setFixedHeight(28)
        self._spin_max_count.setPrefix("Max ")
        self._spin_max_count.setToolTip("最大检测数量")
        layout.addWidget(self._spin_max_count)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setProperty("toolbar", "true")
        self._btn_clear.setEnabled(False)
        layout.addWidget(self._btn_clear)

        # 操作区 / 编辑区分隔
        sep2 = QWidget()
        sep2.setFixedSize(1, 18)
        sep2.setObjectName("toolbarSep")
        layout.addWidget(sep2)

        self._btn_undo = QPushButton("Undo")
        self._btn_undo.setProperty("toolbar", "true")
        layout.addWidget(self._btn_undo)

        self._btn_redo = QPushButton("Redo")
        self._btn_redo.setProperty("toolbar", "true")
        layout.addWidget(self._btn_redo)

        # 弹性空间 + 居中 Page Nav
        layout.addStretch(1)
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
        layout.addStretch(1)

        # 右侧按钮
        self._btn_grid = QPushButton("Grid")
        self._btn_grid.setCheckable(True)
        self._btn_grid.setChecked(False)
        self._btn_grid.setProperty("toolbar", "true")
        layout.addWidget(self._btn_grid)

        self._btn_single = QPushButton("Single")
        self._btn_single.setCheckable(True)
        self._btn_single.setProperty("toolbar", "true")
        layout.addWidget(self._btn_single)

        self._btn_theme = QPushButton()
        self._btn_theme.setFixedSize(28, 28)
        self._btn_theme.setIconSize(QSize(16, 16))
        self._btn_theme.setProperty("toolbar", "true")
        self._btn_theme.setProperty("iconOnly", "true")
        self._btn_theme.setToolTip("切换 Light/Dark 主题")
        layout.addWidget(self._btn_theme)

        self._btn_export = QPushButton("Export")
        self._btn_export.setProperty("export_btn", "true")
        self._btn_export.setEnabled(False)
        layout.addWidget(self._btn_export)

    def _build_empty_state(self) -> QWidget:
        page = QWidget()
        page.setObjectName("emptyState")
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(16)

        icon = BrandIcon(size=48, opacity=0.25)
        v.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)

        brand = QLabel(
            '<span style="font-size:28px;font-weight:200;letter-spacing:0.08em">Photo</span>'
            '<span style="font-size:28px;font-weight:500;letter-spacing:0.02em">Crop</span>'
        )
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(brand)

        self._empty_subtitle = QLabel("SCAN & EXTRACT PHOTOS")
        self._empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; letter-spacing: 0.25em;"
        )
        v.addWidget(self._empty_subtitle)

        self._empty_hint = QLabel("拖入图片或点击 + Import 开始")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self._empty_hint)

        # 垂直居中偏移补偿：在顶部加弹性空间使内容视觉居中
        v.insertStretch(0, 1)
        v.addStretch(1)
        return page

    def _build_bottom_bar(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(6)

        self._lbl_bottom_status = QLabel("Ready")
        layout.addWidget(self._lbl_bottom_status)
        layout.addStretch()

        # 分隔线：状态信息 | 缩放控件
        self._zoom_sep = QWidget()
        self._zoom_sep.setFixedSize(1, 16)
        self._zoom_sep.setObjectName("toolbarSep")
        layout.addWidget(self._zoom_sep)
        layout.addSpacing(8)

        self._lbl_zoom = QLabel("Zoom: 100%")
        layout.addWidget(self._lbl_zoom)
        layout.addSpacing(4)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(28, 22)
        btn_zoom_in.clicked.connect(self._on_zoom_in)
        layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedSize(28, 22)
        btn_zoom_out.clicked.connect(self._on_zoom_out)
        layout.addWidget(btn_zoom_out)

        layout.addSpacing(4)

        btn_fit = QPushButton("Fit")
        btn_fit.setFixedSize(50, 22)
        btn_fit.clicked.connect(self._on_zoom_fit)
        layout.addWidget(btn_fit)

        btn_1to1 = QPushButton("1:1")
        btn_1to1.setFixedSize(50, 22)
        btn_1to1.clicked.connect(self._on_zoom_1to1)
        layout.addWidget(btn_1to1)

    # ================================================================
    # 信号连接
    # ================================================================

    def _connect_signals(self) -> None:
        # 工具栏按钮
        self._btn_load.clicked.connect(self._on_load)
        self._btn_detect.clicked.connect(self._on_detect)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_undo.clicked.connect(self._on_undo)
        self._btn_redo.clicked.connect(self._on_redo)
        self._btn_prev_page.clicked.connect(self._on_prev_page)
        self._btn_next_page.clicked.connect(self._on_next_page)
        self._btn_grid.clicked.connect(lambda: self._view_coord.show_grid())
        self._btn_single.clicked.connect(self._on_single_clicked)
        self._btn_theme.clicked.connect(self._theme_ctrl.toggle)

        # Canvas 信号
        self._canvas.image_loaded.connect(self._on_image_loaded)
        self._canvas.detection_done.connect(self._on_detection_done)
        self._canvas.rects_changed.connect(self._on_rects_changed)
        self._canvas.page_changed.connect(self._on_page_changed)
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.view_single_requested.connect(self._on_view_single_requested)
        self._canvas.zoom_changed.connect(self._update_zoom_label)
        self._canvas.crop_rotating.connect(self._on_crop_rotating)
        self._canvas.files_dropped.connect(self._on_files_dropped)

        # 右面板信号
        self._crop_options_panel.rect_changed.connect(self._on_crop_options_changed)
        self._crop_options_panel.editing_finished.connect(self._on_crop_options_finished)
        self._crop_options_panel.aspect_ratio_changed.connect(self._on_aspect_ratio_changed)
        self._extracted_panel.crop_selected.connect(self._on_extracted_crop_selected)
        self._extracted_panel.crop_delete_requested.connect(self._on_extracted_crop_delete)

        # SingleView
        self._single_view.exit_requested.connect(lambda: self._view_coord.show_grid())
        self._single_view.selection_changed.connect(self._on_single_view_selection)

        # 左面板
        self._image_list_panel.image_selected.connect(self._on_image_selected)
        self._image_list_panel.re_detect_requested.connect(self._on_re_detect)
        self._image_list_panel.remove_requested.connect(self._on_remove_from_list)

        # Controller 信号
        self._session_ctrl.load_error.connect(self._on_load_error)
        self._detect_ctrl.batch_page_done.connect(self._on_batch_page_done)
        self._detect_ctrl.batch_progress.connect(self._on_batch_progress)
        self._detect_ctrl.batch_finished.connect(self._on_batch_finished)
        self._app_state.status_message.connect(self._lbl_bottom_status.setText)

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
        self.setStyleSheet(theme.generate_stylesheet())

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

        self._brand_icon.update()
        for bi in self._empty_state.findChildren(BrandIcon):
            bi.update()

        self._brand_text.setStyleSheet(
            f"font-family: {FONT_DISPLAY}; font-size: 15px; color: {c.text};"
        )
        self._empty_state.setStyleSheet(f"background: {c.canvas_bg};")
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; "
            f"letter-spacing: 0.25em; color: {c.text_secondary};"
        )
        self._empty_hint.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; color: {c.text_secondary};"
        )
        self._lbl_bottom_status.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; color: {c.text_secondary};"
        )
        self._lbl_zoom.setStyleSheet(
            f"font-family: {FONT_BODY}; font-size: 11px; color: {c.text_secondary};"
        )

        for w in self._toolbar.findChildren(QWidget):
            if w.objectName() == "toolbarSep":
                w.setStyleSheet(f"background: {c.border};")

        # 右侧面板分隔线
        for w in self.findChildren(QWidget):
            if w.objectName() == "rightPanelSep":
                w.setStyleSheet(f"background: {c.border};")

        icon_color = c.accent if theme.mode == "light" else c.text
        self._btn_theme.setIcon(
            get_icon("sun" if theme.mode == "light" else "moon", icon_color)
        )
        self._btn_prev_page.setIcon(get_icon("chevron-left", icon_color))
        self._btn_next_page.setIcon(get_icon("chevron-right", icon_color))
        self._lbl_page_info.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_BODY}; font-size: 13px;"
        )

        # ComboBox 下拉箭头 SVG 图标
        arrow_color = c.text_secondary if theme.mode == "light" else c.text
        arrow_path = get_colored_svg_path("chevron-down", arrow_color)
        if arrow_path:
            self._combo_detector.setStyleSheet(
                f"QComboBox::down-arrow {{ image: url('{arrow_path}'); "
                f"width: 14px; height: 14px; }}"
            )

        # SpinBox / ComboBox 与工具栏按钮底部对齐
        self._spin_max_count.setStyleSheet(
            "QSpinBox { padding: 4px 6px; min-height: 22px; }"
        )

    def _on_theme_changed(self, _colors: object) -> None:
        self._apply_theme()

    # ================================================================
    # 槽函数 — 只调用 Controller，不直接操作数据
    # ================================================================

    @property
    def _selected_detector(self) -> str:
        idx = self._combo_detector.currentIndex()
        if idx < 0 or idx >= len(DETECTOR_OPTIONS):
            idx = 0
        return DETECTOR_OPTIONS[idx][1]

    def _on_detector_changed(self, index: int) -> None:
        """检测器下拉框变化时更新 tooltip"""
        self._update_detector_tooltip()

    def _update_detector_tooltip(self) -> None:
        """更新检测器下拉框的 tooltip"""
        idx = self._combo_detector.currentIndex()
        if 0 <= idx < len(DETECTOR_OPTIONS):
            key = DETECTOR_OPTIONS[idx][1]
            tooltip = DETECTOR_TOOLTIPS.get(key, "")
            self._combo_detector.setToolTip(tooltip)

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
            last_sess = self._app_state.get_session(last_path)
            if last_sess and last_sess.is_pdf:
                page_key = self._app_state.get_page_key(last_path, 0)
                self._image_list_panel.select_image(page_key)
                self._on_image_selected(page_key)
            else:
                self._image_list_panel.select_image(last_path)
                self._on_image_selected(last_path)

    def _load_single_file(self, path_str: str) -> None:
        """加载单个文件 — 委托 SessionController"""
        if self._app_state.current_session:
            self._session_ctrl.save_current_state(
                self._canvas.crop_rects,
                self._canvas._undo_manager.serialize(),
            )
        sess = self._session_ctrl.load_file(path_str)
        if not sess:
            return
        self._app_state.add_session(sess)

        path = Path(path_str)
        if sess.is_pdf:
            first_thumb = (sess.page_thumbnails[0]
                           if sess.page_thumbnails else sess.source_image.copy())
            self._image_list_panel.add_image(
                key=path_str, filename=path.name, thumbnail=first_thumb,
                page_count=sess.page_count, page_thumbnails=sess.page_thumbnails,
            )
        else:
            thumb = (sess.page_thumbnails[0]
                     if sess.page_thumbnails else sess.source_image.copy())
            self._image_list_panel.add_image(
                key=path_str, filename=path.name, thumbnail=thumb, crop_count=0,
            )

    def _on_image_selected(self, key: str) -> None:
        """用户选择了新的图像/PDF页面 — 委托 SessionController"""
        if key == self._app_state._current_key:
            return
        self._session_ctrl.save_current_state(
            self._canvas.crop_rects,
            self._canvas._undo_manager.serialize(),
        )
        success = self._session_ctrl.restore_session(
            key, self._canvas, self._canvas._undo_manager,
        )
        if not success:
            return

        sess = self._app_state.current_session
        if sess:
            self._extracted_panel.set_source_image(sess.source_image)
            self._extracted_panel.set_global_mode(sess.is_pdf)
            if sess.is_pdf:
                self._refresh_global_preview(sess, sess.current_page)

        if self._view_coord.is_empty:
            self._view_coord.show_grid()
            self._canvas.fitInView(
                self._canvas._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        self._update_button_states()
        self._update_image_list_panel()

    def _on_detect(self) -> None:
        detector = self._selected_detector
        max_count = self._spin_max_count.value()

        sess = self._app_state.current_session
        if sess is not None and sess.is_pdf and sess.page_count > 1:
            if not self._view_coord.is_grid:
                self._view_coord.show_grid()
            self._extracted_panel.clear_incremental()
            self._extracted_panel.set_global_mode(True)
            self._batch_progress = QProgressDialog(
                "正在检测所有 PDF 页面...", "取消", 0, sess.page_count, self,
            )
            self._batch_progress.setWindowTitle("批量检测")
            self._batch_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._batch_progress.setMinimumDuration(0)
            self._batch_progress.setValue(0)
            self._batch_progress.canceled.connect(self._detect_ctrl.cancel)
            self._detect_ctrl.detect_all_pages(sess.key, detector, max_count)
            return

        self._app_state.status_message.emit(f"正在检测（{detector}）...")
        self._canvas.show_loading("Detecting photos...")
        QApplication.processEvents()
        try:
            count = self._detect_ctrl.detect_current(
                detector, max_count, self._canvas,
            )
            self._canvas.hide_loading()
            self._app_state.status_message.emit(f"检测到 {count} 个照片")
            show_toast(f"Detected {count} photos", self)
            self._update_button_states()
            self._update_image_list_panel()
        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
        except Exception as e:
            QMessageBox.critical(self, "检测失败", str(e))

    def _on_batch_page_done(self, session_key: str, page_idx: int, crop_rects: list) -> None:
        sess = self._app_state.get_session(session_key)
        if not sess:
            return
        page_key = self._app_state.get_page_key(session_key, page_idx)
        self._image_list_panel.update_crop_count(page_key, len(crop_rects))
        try:
            page_img = sess.get_page_image(page_idx)
            self._extracted_panel.add_page_results(page_idx, page_img, crop_rects)
        except (RuntimeError, IndexError):
            pass

    def _on_batch_progress(self, done: int, _total: int) -> None:
        if hasattr(self, '_batch_progress') and self._batch_progress:
            self._batch_progress.setValue(done)

    def _on_batch_finished(self, session_key: str, total_rects: int) -> None:
        if hasattr(self, '_batch_progress') and self._batch_progress:
            self._batch_progress.close()
        sess = self._app_state.get_session(session_key)
        if sess:
            self._app_state.status_message.emit(
                f"检测完成: {sess.page_count} 页, {total_rects} 个裁剪框"
            )
            self._update_image_list_panel()
            self._update_button_states()
            current_page = sess.current_page
            current_rects = sess.page_crop_rects.get(current_page, [])
            self._canvas._restore_rects(current_rects)
            self._canvas._push_undo_state()
            self._refresh_global_preview(sess, current_page)

    def _on_export(self) -> None:
        self._session_ctrl.save_current_state(
            self._canvas.crop_rects,
            self._canvas._undo_manager.serialize(),
        )
        current_crops = len(self._canvas.crop_rects)
        total_crops = self._app_state.total_crop_count
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

        try:
            exported, errors = self._export_ctrl.export(config, self._canvas)
            msg = f"成功导出 {exported} 张照片\n→ {output_dir}"
            if errors:
                msg += f"\n\n失败 {len(errors)} 张:\n" + "\n".join(errors)
            QMessageBox.information(self, "导出完成", msg)
            show_toast(f"Export complete: {exported} images to {output_dir}", self)
            self._app_state.status_message.emit(
                f"导出完成: {exported} 张 → {output_dir}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_clear(self) -> None:
        self._canvas.clear_crops()
        self._app_state.status_message.emit("已清除所有裁剪框")
        self._update_button_states()

        pdf_sess = self._session_ctrl.get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            current_page = pdf_sess.current_page
            pdf_sess.page_crop_rects[current_page] = []
            self._refresh_global_preview(pdf_sess, current_page)

    def _on_prev_page(self) -> None:
        pdf_sess = self._session_ctrl.get_current_pdf_session()
        if pdf_sess is not None:
            prev_key = self._session_ctrl.get_sibling_page_key(
                self._app_state._current_key, -1,
            )
            if prev_key:
                self._image_list_panel.select_image(prev_key)
                self._on_image_selected(prev_key)
            return
        self._canvas.prev_page()

    def _on_next_page(self) -> None:
        pdf_sess = self._session_ctrl.get_current_pdf_session()
        if pdf_sess is not None:
            next_key = self._session_ctrl.get_sibling_page_key(
                self._app_state._current_key, 1,
            )
            if next_key:
                self._image_list_panel.select_image(next_key)
                self._on_image_selected(next_key)
            return
        self._canvas.next_page()

    def _on_re_detect(self, key: str) -> None:
        parsed = self._app_state.parse_page_key(key)
        session_key = parsed[0] if parsed else key
        if not self._app_state.get_session(session_key):
            return
        if key != self._app_state._current_key:
            self._image_list_panel.select_image(key)
            self._on_image_selected(key)
        self._on_detect()

    def _on_remove_from_list(self, key: str) -> None:
        parsed = self._app_state.parse_page_key(key)
        parent_key = parsed[0] if parsed else key

        next_key = self._session_ctrl.remove_session(key)
        if next_key:
            self._image_list_panel.remove_image(parent_key)
            self._image_list_panel.select_image(next_key)
            self._on_image_selected(next_key)
        else:
            self._app_state.set_current("")
            self._canvas.clear_all()
            self._extracted_panel.set_global_mode(False)
            self._view_coord.show_empty()
            self._image_list_panel.remove_image(parent_key)
        self._update_image_list_panel()

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
        img_size = (self._canvas.source_image.size
                    if self._canvas.source_image else (0, 0))
        self._crop_options_panel.set_selected_rect(rect, img_size)

    def _on_crop_rotating(self, angle: float) -> None:
        """旋转中实时更新右面板角度值"""
        self._crop_options_panel.update_rotation(angle)

    def _on_crop_options_changed(self) -> None:
        for item in self._canvas.selected_items:
            item._sync_from_rect()
            item.update()
        self._canvas.rects_changed.emit()

    def _on_crop_options_finished(self) -> None:
        self._canvas._push_undo_state()
        self._update_button_states()

    def _on_aspect_ratio_changed(self, ratio: float) -> None:
        for item in self._canvas.selected_items:
            if ratio == 0.0:
                item.aspect_ratio_lock = None
            elif ratio == -1.0:
                h = item.crop_rect.height
                if h > 0:
                    item.aspect_ratio_lock = item.crop_rect.width / h
            else:
                item.aspect_ratio_lock = ratio

    def _on_extracted_crop_selected(self, index: int) -> None:
        if self._extracted_panel._global_mode:
            ref = self._extracted_panel.get_page_and_index(index)
            if ref is None:
                return
            pdf_sess = self._session_ctrl.get_current_pdf_session()
            if pdf_sess is None:
                return
            pdf_key = str(pdf_sess.source_path)
            target_key = self._app_state.get_page_key(pdf_key, ref.page_idx)
            local_idx = ref.local_idx

            def _do_select() -> None:
                items = self._canvas.crop_items
                if 0 <= local_idx < len(items):
                    self._canvas._scene.clearSelection()
                    items[local_idx].setSelected(True)

            if self._app_state._current_key != target_key:
                self._image_list_panel.select_image(target_key)
                self._on_image_selected(target_key)
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
            pdf_sess = self._session_ctrl.get_current_pdf_session()
            if pdf_sess is None:
                return
            pdf_key = str(pdf_sess.source_path)
            target_key = self._app_state.get_page_key(pdf_key, ref.page_idx)
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

            if self._app_state._current_key != target_key:
                self._image_list_panel.select_image(target_key)
                self._on_image_selected(target_key)
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

    def _on_single_clicked(self) -> None:
        """用户点击底部 Single 按钮 — 切换到单张预览视图"""
        items = self._canvas.crop_items
        if not items or self._canvas.source_image is None:
            # 没有裁剪框或没有图片：只切换视图（会显示空白状态）
            self._view_coord.show_single()
            return
        # 找到当前选中的裁剪框索引，没有则默认第一个
        selected = self._canvas.selected_items
        index = items.index(selected[-1]) if selected else 0
        self._on_view_single_requested(index)

    def _on_view_single_requested(self, index: int) -> None:
        self._view_coord.show_single()
        self._single_view.set_data(
            self._canvas.source_image, self._canvas.crop_rects,
        )
        self._single_view.select_crop(index)

    def _on_single_view_selection(self, index: int) -> None:
        items = self._canvas.crop_items
        if 0 <= index < len(items):
            self._canvas._scene.clearSelection()
            items[index].setSelected(True)

    def _on_image_loaded(self) -> None:
        self._update_button_states()

        if self._view_coord.is_empty:
            self._view_coord.show_grid()
            self._canvas.fitInView(
                self._canvas._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

        self._extracted_panel.set_source_image(self._canvas.source_image)

        sess = self._app_state.current_session
        is_pdf = sess is not None and sess.is_pdf and sess.page_count > 1
        self._page_nav_widget.setVisible(is_pdf)

        img_count = self._app_state.session_count
        crop_count = len(self._canvas.crop_rects)
        if is_pdf:
            self._app_state.status_message.emit(
                f"{img_count} images · PDF {sess.page_count} pages"
            )
        elif crop_count > 0:
            self._app_state.status_message.emit(
                f"{img_count} images · {crop_count} crops"
            )
        else:
            self._app_state.status_message.emit(
                f"{img_count} images"
            )

    def _on_detection_done(self, _count: int) -> None:
        self._update_button_states()
        self._update_image_list_panel()

    def _on_rects_changed(self) -> None:
        count = len(self._canvas.crop_rects)
        self._app_state.status_message.emit(
            f"{self._app_state.session_count} images · {count} crops"
        )
        self._update_button_states()
        self._update_image_list_panel()

        pdf_sess = self._session_ctrl.get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            current_page = pdf_sess.current_page
            pdf_sess.page_crop_rects[current_page] = [
                copy.deepcopy(r) for r in self._canvas.crop_rects
            ]
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

    def _on_load_error(self, _path: str, error: str) -> None:
        QMessageBox.critical(self, "加载失败", f"无法打开文件:\n{error}")

    def _on_files_dropped(self, paths: list[str]) -> None:
        """拖拽导入文件"""
        for path_str in paths:
            self._load_single_file(path_str)
        if paths:
            last_path = paths[-1]
            last_sess = self._app_state.get_session(last_path)
            if last_sess and last_sess.is_pdf:
                page_key = self._app_state.get_page_key(last_path, 0)
                self._image_list_panel.select_image(page_key)
                self._on_image_selected(page_key)
            else:
                self._image_list_panel.select_image(last_path)
                self._on_image_selected(last_path)

    # ================================================================
    # UI 更新（被动响应）
    # ================================================================

    def _update_button_states(self) -> None:
        has_image = self._canvas.source_image is not None
        has_rects = len(self._canvas.crop_rects) > 0
        self._btn_detect.setEnabled(has_image)
        self._btn_clear.setEnabled(has_rects)
        self._btn_export.setEnabled(has_rects)
        self._btn_undo.setEnabled(self._canvas._undo_manager.can_undo())
        self._btn_redo.setEnabled(self._canvas._undo_manager.can_redo())

    def _update_image_list_panel(self) -> None:
        total_crops = 0
        for key, sess in self._app_state._sessions.items():
            if sess.is_pdf:
                for page_idx in range(sess.page_count):
                    page_key = self._app_state.get_page_key(key, page_idx)
                    is_current = (self._app_state._current_key == page_key)
                    count = (len(self._canvas.crop_rects) if is_current
                             else len(sess.page_crop_rects.get(page_idx, [])))
                    self._image_list_panel.update_crop_count(page_key, count)
                    total_crops += count
            else:
                is_current = (self._app_state._current_key == key)
                count = (len(self._canvas.crop_rects) if is_current
                         else len(sess.crop_rects))
                self._image_list_panel.update_crop_count(key, count)
                total_crops += count
        self._image_list_panel.update_total(
            self._app_state.session_count, total_crops,
        )

    def _refresh_global_preview(self, sess: SessionState,
                                current_page: int = -1) -> None:
        pages_data = []
        for page_idx in range(sess.page_count):
            rects = sess.page_crop_rects.get(page_idx, [])
            try:
                img = sess.get_page_image(page_idx)
            except (RuntimeError, IndexError):
                img = sess.source_image
            pages_data.append((page_idx, img, rects))
        current_rects = (list(self._canvas.crop_rects)
                         if current_page >= 0 else None)
        self._extracted_panel.refresh_all_pages(
            pages_data, current_page=current_page,
            current_rects=current_rects,
        )

    def _update_zoom_label(self) -> None:
        m = self._canvas.transform().m11()
        self._lbl_zoom.setText(f"Zoom: {int(m * 100)}%")

    # ================================================================
    # 缩放
    # ================================================================

    def _on_zoom_in(self) -> None:
        self._canvas.scale(1.15, 1.15)
        self._update_zoom_label()

    def _on_zoom_out(self) -> None:
        self._canvas.scale(1 / 1.15, 1 / 1.15)
        self._update_zoom_label()

    def _on_zoom_fit(self) -> None:
        if self._canvas.source_image:
            self._canvas.fitInView(
                self._canvas._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            self._update_zoom_label()

    def _on_zoom_1to1(self) -> None:
        self._canvas.resetTransform()
        self._update_zoom_label()

    # ================================================================
    # 窗口关闭
    # ================================================================

    def closeEvent(self, event) -> None:
        self._detect_ctrl.cancel()
        self._session_ctrl.close_all()
        event.accept()
