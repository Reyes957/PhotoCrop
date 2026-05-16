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
from PySide6.QtGui import QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
from photocrop.ui.styled_dropdown import StyledDropdown
from photocrop.ui.extracted_images_panel import ExtractedImagesPanel
from photocrop.ui.icons import get_icon
from photocrop.ui.image_list_panel import ImageListPanel
from photocrop.ui.press_button import PressButton
from photocrop.ui.single_view_panel import SingleViewPanel
from photocrop.ui.state import AppState, SessionState
from photocrop.ui.theme import FONT_DISPLAY, FONT_FAMILY, FontSize, FontWeight, theme
from photocrop.ui.toast import show_toast

# ============================================================
# 常量
# ============================================================

DETECTOR_OPTIONS = [
    ("Enhanced CV (Default)", "enhanced-cv"),
    ("CV", "cv"),
    ("Combined", "combined"),
    ("YOLO-World", "yolo-world"),
]

DETECTOR_TOOLTIPS = {
    "enhanced-cv": "Enhanced CV (Default): Improved edge detection with noise filtering. Better for low-quality scans.",
    "cv": "CV: Fast edge-based detection. Best for well-separated photos on clean backgrounds.",
    "combined": "Combined: Uses both edge detection and contour analysis. Slower but more accurate.",
    "yolo-world": "YOLO-World: AI-powered object detection. Best for complex layouts and mixed content.",
}


# ============================================================
# BrandIcon — SVG 品牌图标（设计规范 §4 元素 1）
# ============================================================

class BrandIcon(QWidget):
    """SVG 双层方框品牌图标"""

    def __init__(self, size: int = 20, opacity: float = 1.0, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._opacity = opacity
        self._icon_name = "brand-logo-large" if size > 30 else "brand-logo"

    def paintEvent(self, _event):
        icon = get_icon(self._icon_name, theme.colors.text)
        p = QPainter(self)
        p.setOpacity(self._opacity)
        icon.paint(p, self.rect())
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

        # 3b. 延迟 fitInView 定时器（避免快速切页时累积多次调用）
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self._do_fit_in_view)

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

    def showEvent(self, event):
        """窗口首次显示时清除焦点，避免 QSpinBox 自动获取焦点导致光标闪烁。"""
        super().showEvent(event)
        self._spin_max_count.clearFocus()
        self.setFocus()

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
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._brand_icon = BrandIcon(size=20)
        layout.addWidget(self._brand_icon)

        self._brand_text = QLabel(
            f'<span style="font-family:{FONT_DISPLAY};font-size:{FontSize.BRAND}px;'
            f'font-weight:300;letter-spacing:0.06em">Photo</span>'
            f'<span style="font-family:{FONT_DISPLAY};font-size:{FontSize.BRAND}px;'
            f'font-weight:{FontWeight.SEMIBOLD};letter-spacing:0.01em">Crop</span>'
        )
        self._brand_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brand_text.mousePressEvent = lambda _: self._view_coord.show_empty()
        layout.addWidget(self._brand_text)

        sep = QWidget()
        sep.setFixedSize(1, 18)
        sep.setObjectName("toolbarSep")
        layout.addWidget(sep)

        self._btn_load = PressButton("Import")
        self._btn_load.setProperty("toolbar", "true")
        self._btn_load.setIconSize(QSize(14, 14))
        layout.addWidget(self._btn_load)

        self._dropdown_detector = StyledDropdown(panel_width=280, parent=self)
        self._dropdown_detector.add_option("enhanced-cv", "Enhanced CV (Default)",
            "Improved edge detection with noise filtering. Better for low-quality scans.")
        self._dropdown_detector.add_option("cv", "CV",
            "Fast edge-based detection. Best for well-separated photos on clean backgrounds.")
        self._dropdown_detector.add_option("combined", "Combined",
            "IoU voting fusion. Slower but more accurate.")
        self._dropdown_detector.add_option("yolo-world", "YOLO-World",
            "AI-powered zero-shot detection. Best for mixed content.")
        self._dropdown_detector.current_changed.connect(self._on_detector_changed)
        layout.addWidget(self._dropdown_detector)

        self._btn_detect = PressButton("Detect")
        self._btn_detect.setProperty("toolbar", "true")
        self._btn_detect.setIconSize(QSize(14, 14))
        self._btn_detect.setEnabled(False)
        layout.addWidget(self._btn_detect)

        self._spin_max_count = QSpinBox()
        self._spin_max_count.setRange(1, 10)
        self._spin_max_count.setValue(5)
        self._spin_max_count.setFixedWidth(58)
        self._spin_max_count.setFixedHeight(28)
        self._spin_max_count.setPrefix("Max ")
        self._spin_max_count.setToolTip("Maximum detection count")
        layout.addWidget(self._spin_max_count)

        self._btn_clear = PressButton("Clear")
        self._btn_clear.setProperty("toolbar", "true")
        self._btn_clear.setIconSize(QSize(14, 14))
        self._btn_clear.setEnabled(False)
        layout.addWidget(self._btn_clear)

        sep2 = QWidget()
        sep2.setFixedSize(1, 18)
        sep2.setObjectName("toolbarSep")
        layout.addWidget(sep2)

        self._btn_undo = QPushButton("Undo")
        self._btn_undo.setProperty("toolbar", "true")
        self._btn_undo.setIconSize(QSize(14, 14))
        self._btn_undo.setToolTip("Undo (Ctrl+Z)")
        layout.addWidget(self._btn_undo)

        self._btn_redo = QPushButton("Redo")
        self._btn_redo.setProperty("toolbar", "true")
        self._btn_redo.setIconSize(QSize(14, 14))
        self._btn_redo.setToolTip("Redo (Ctrl+Y)")
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
        self._btn_prev_page.setFixedSize(32, 32)
        self._btn_prev_page.setIconSize(QSize(16, 16))
        pn_layout.addWidget(self._btn_prev_page)

        self._lbl_page_info = QLabel("Page 1 / 1")
        self._lbl_page_info.setProperty("pageInfo", True)
        self._lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pn_layout.addWidget(self._lbl_page_info)

        self._btn_next_page = QPushButton()
        self._btn_next_page.setProperty("toolbar", "true")
        self._btn_next_page.setProperty("iconOnly", "true")
        self._btn_next_page.setFixedSize(32, 32)
        self._btn_next_page.setIconSize(QSize(16, 16))
        pn_layout.addWidget(self._btn_next_page)

        layout.addWidget(self._page_nav_widget)
        self._page_nav_widget.setVisible(False)
        layout.addStretch(1)

        # 右侧按钮
        self._btn_grid = QPushButton("Grid")
        self._btn_grid.setCheckable(True)
        self._btn_grid.setChecked(False)
        self._btn_grid.setProperty("toolbar", "true")
        self._btn_grid.setIconSize(QSize(14, 14))
        layout.addWidget(self._btn_grid)

        self._btn_single = QPushButton("Single")
        self._btn_single.setCheckable(True)
        self._btn_single.setProperty("toolbar", "true")
        self._btn_single.setIconSize(QSize(14, 14))
        layout.addWidget(self._btn_single)

        sep3 = QWidget()
        sep3.setFixedSize(1, 18)
        sep3.setObjectName("toolbarSep")
        layout.addWidget(sep3)

        self._btn_theme = QPushButton()
        self._btn_theme.setFixedSize(28, 28)
        self._btn_theme.setIconSize(QSize(16, 16))
        self._btn_theme.setProperty("toolbar", "true")
        self._btn_theme.setProperty("iconOnly", "true")
        self._btn_theme.setToolTip("Toggle Light/Dark theme")
        layout.addWidget(self._btn_theme)

        self._btn_export = PressButton("Export")
        self._btn_export.setProperty("export_btn", "true")
        self._btn_export.setFixedHeight(28)
        self._btn_export.setIconSize(QSize(14, 14))
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
            f'<span style="font-size:{FontSize.BRAND_LARGE}px;font-weight:{FontWeight.LIGHT};'
            f'letter-spacing:0.08em">Photo</span>'
            f'<span style="font-size:{FontSize.BRAND_LARGE}px;font-weight:{FontWeight.SEMIBOLD};'
            f'letter-spacing:0.02em">Crop</span>'
        )
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(brand)

        self._empty_subtitle = QLabel("SCAN & EXTRACT PHOTOS")
        self._empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px; "
            f"font-weight: {FontWeight.SEMIBOLD}; letter-spacing: 0.25em;"
        )
        v.addWidget(self._empty_subtitle)

        self._empty_hint = QLabel("Drag images here or click Import to start")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px;"
        )
        v.addWidget(self._empty_hint)

        # 设计规范 §6：同 Toolbar Import 按钮但更大 padding（16px 24px）
        self._empty_import_btn = PressButton("Import")
        self._empty_import_btn.setIconSize(QSize(14, 14))
        self._empty_import_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {theme.colors.border};"
            f" border-radius: 4px; padding: 16px 24px; font-family: {FONT_FAMILY};"
            f" font-size: {FontSize.BODY}px; color: {theme.colors.text}; }}"
            f"QPushButton:hover {{ background: {theme.colors.hover_bg};"
            f" border-color: {theme.colors.border_strong}; }}"
        )
        self._empty_import_btn.clicked.connect(self._on_load)
        v.addWidget(self._empty_import_btn, 0, Qt.AlignmentFlag.AlignCenter)

        v.insertStretch(0, 1)
        v.addStretch(1)
        return page

    def _build_bottom_bar(self, parent: QWidget) -> None:
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        self._lbl_bottom_status = QLabel("Ready · Drag images or press Ctrl+O")
        layout.addWidget(self._lbl_bottom_status)
        layout.addStretch()

        self._zoom_sep = QWidget()
        self._zoom_sep.setFixedSize(1, 16)
        self._zoom_sep.setObjectName("toolbarSep")
        layout.addWidget(self._zoom_sep)
        layout.addSpacing(8)

        self._lbl_zoom = QLabel("Zoom: 100%")
        layout.addWidget(self._lbl_zoom)
        layout.addSpacing(4)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(28, 28)
        btn_zoom_in.clicked.connect(self._on_zoom_in)
        layout.addWidget(btn_zoom_in)

        layout.addSpacing(4)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedSize(28, 28)
        btn_zoom_out.clicked.connect(self._on_zoom_out)
        layout.addWidget(btn_zoom_out)

        layout.addSpacing(4)

        btn_fit = QPushButton("Fit")
        btn_fit.setFixedSize(50, 28)
        btn_fit.clicked.connect(self._on_zoom_fit)
        layout.addWidget(btn_fit)

        layout.addSpacing(4)

        btn_1to1 = QPushButton("1:1")
        btn_1to1.setFixedSize(50, 28)
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
        QShortcut(QKeySequence("Delete"), self, activated=self._on_delete_selected)
        QShortcut(QKeySequence("Tab"), self, activated=self._toggle_view)
        QShortcut(QKeySequence("Plus"), self, activated=self._on_zoom_in)
        QShortcut(QKeySequence("Equal"), self, activated=self._on_zoom_in)
        QShortcut(QKeySequence("Minus"), self, activated=self._on_zoom_out)

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

        self._empty_state.setStyleSheet(f"background: {c.canvas_bg};")
        self._empty_subtitle.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px; "
            f"font-weight: {FontWeight.SEMIBOLD}; letter-spacing: 0.25em; color: {c.text_secondary};"
        )
        self._empty_hint.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px; color: {c.text_secondary};"
        )
        self._lbl_bottom_status.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px; color: {c.text_secondary};"
        )
        self._lbl_zoom.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FontSize.LABEL}px; "
            f"color: {c.text_secondary};"
        )

        for w in self._toolbar.findChildren(QWidget):
            if w.objectName() == "toolbarSep":
                w.setStyleSheet(f"background: {c.border};")

        for w in self.findChildren(QWidget):
            if w.objectName() == "rightPanelSep":
                w.setStyleSheet(f"background: {c.border};")

        # 图标颜色：Light 模式用 accent（黑色），Dark 模式用 text（白色）
        ic = c.accent if theme.mode == "light" else c.text

        # 工具栏按钮图标
        self._btn_load.setIcon(get_icon("upload", ic))
        self._btn_detect.setIcon(get_icon("scan-eye", ic))
        self._btn_clear.setIcon(get_icon("trash", ic))
        self._btn_undo.setIcon(get_icon("undo", ic))
        self._btn_redo.setIcon(get_icon("redo", ic))
        self._btn_grid.setIcon(get_icon("layout-grid", ic))
        self._btn_single.setIcon(get_icon("image", ic))
        self._btn_theme.setIcon(
            get_icon("sun" if theme.mode == "light" else "moon", ic)
        )
        # Export 按钮图标跟随按钮文字颜色（不是通用图标颜色）
        export_text_color = "#FFFFFF" if theme.mode == "light" else "#1A1A1A"
        self._btn_export.setIcon(get_icon("download", export_text_color))

        # 空状态 Import 按钮（16px 24px padding）
        self._empty_import_btn.setIcon(get_icon("upload", ic))
        self._empty_import_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {c.border};"
            f" border-radius: 4px; padding: 16px 24px; font-family: {FONT_FAMILY};"
            f" font-size: {FontSize.BODY}px; color: {c.text}; }}"
            f"QPushButton:hover {{ background: {c.hover_bg};"
            f" border-color: {c.border_strong}; }}"
        )

        # Page 导航图标
        self._btn_prev_page.setIcon(get_icon("chevron-left", ic))
        self._btn_next_page.setIcon(get_icon("chevron-right", ic))
        self._lbl_page_info.setStyleSheet(
            f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; "
            f"font-size: {FontSize.BODY}px;"
        )

        # 检测器下拉菜单主题
        self._dropdown_detector.apply_theme(c)

    def _on_theme_changed(self, _colors: object) -> None:
        self._apply_theme()

    # ================================================================
    # 槽函数 — 只调用 Controller，不直接操作数据
    # ================================================================

    @property
    def _selected_detector(self) -> str:
        return self._dropdown_detector.current_value()

    def _on_detector_changed(self, value: str) -> None:
        """检测器下拉框变化"""
        tooltip = DETECTOR_TOOLTIPS.get(value, "")
        self._dropdown_detector.setToolTip(tooltip)

    def _on_load(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images or PDF", "",
            "All Supported (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.pdf);;"
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;"
            "PDF (*.pdf);;All Files (*)",
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
                self._canvas.get_undo_snapshot(),
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
            self._canvas.get_undo_snapshot(),
        )
        success = self._session_ctrl.restore_session(
            key, self._canvas,
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
                self._canvas.scene_rect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        self._update_button_states()
        self._update_image_list_panel()

    def _on_detect(self) -> None:
        detector = self._selected_detector
        max_count = self._spin_max_count.value()

        # 检测中状态：图标变为 Spinner，文字变为 "Detecting..."（设计规范 §4 元素 5）
        self._btn_detect.setText("Detecting...")
        self._btn_detect.setEnabled(False)
        self._start_detect_spinner()

        sess = self._app_state.current_session
        if sess is not None and sess.is_pdf and sess.page_count > 1:
            if not self._view_coord.is_grid:
                self._view_coord.show_grid()
            self._extracted_panel.clear_incremental()
            self._extracted_panel.set_global_mode(True)
            self._batch_progress = QProgressDialog(
                "Detecting all PDF pages...", "Cancel", 0, sess.page_count, self,
            )
            self._batch_progress.setWindowTitle("Batch Detection")
            self._batch_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._batch_progress.setMinimumDuration(0)
            self._batch_progress.setValue(0)
            self._batch_progress.canceled.connect(self._detect_ctrl.cancel)
            self._detect_ctrl.detect_all_pages(sess.key, detector, max_count)
            return

        self._app_state.status_message.emit(f"Detecting ({detector})...")
        self._canvas.show_loading("Detecting photos...")
        QApplication.processEvents()
        try:
            count = self._detect_ctrl.detect_current(
                detector, max_count, self._canvas,
            )
            self._canvas.hide_loading()
            self._app_state.status_message.emit(f"Detected {count} photos")
            show_toast(f"Detected {count} photos", self)
            self._stop_detect_spinner()
            self._update_button_states()
            self._update_image_list_panel()
        except ImportError as e:
            self._stop_detect_spinner()
            QMessageBox.critical(self, "Missing Dependency", str(e))
        except (ValueError, RuntimeError, OSError) as e:
            self._stop_detect_spinner()
            QMessageBox.critical(self, "Detection Failed", str(e))

    def _start_detect_spinner(self) -> None:
        """检测中：旋转 Detect 按钮图标"""
        self._detect_spinner_angle = 0
        self._detect_spinner_timer = QTimer()
        ic = theme.colors.accent if theme.mode == "light" else theme.colors.text
        def rotate():
            self._detect_spinner_angle = (self._detect_spinner_angle + 30) % 360
            icon = get_icon("scan-eye", ic)
            self._btn_detect.setIcon(icon)
        self._detect_spinner_timer.timeout.connect(rotate)
        self._detect_spinner_timer.start(100)

    def _stop_detect_spinner(self) -> None:
        """检测结束：恢复 Detect 按钮"""
        if hasattr(self, '_detect_spinner_timer') and self._detect_spinner_timer:
            self._detect_spinner_timer.stop()
            self._detect_spinner_timer = None
        self._btn_detect.setText("Detect")
        ic = theme.colors.accent if theme.mode == "light" else theme.colors.text
        self._btn_detect.setIcon(get_icon("scan-eye", ic))

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
        self._stop_detect_spinner()
        sess = self._app_state.get_session(session_key)
        if sess:
            self._app_state.status_message.emit(
                f"Detection complete: {sess.page_count} pages, {total_rects} crops"
            )
            self._update_image_list_panel()
            self._update_button_states()
            current_page = sess.current_page
            current_rects = sess.page_crop_rects.get(current_page, [])
            self._canvas.restore_rects_from_list(current_rects)
            self._canvas.push_undo_state()
            self._refresh_global_preview(sess, current_page)

    def _on_export(self) -> None:
        self._session_ctrl.save_current_state(
            self._canvas.crop_rects,
            self._canvas.get_undo_snapshot(),
        )
        current_crops = len(self._canvas.crop_rects)
        total_crops = self._app_state.total_crop_count
        if current_crops == 0 and total_crops == 0:
            QMessageBox.information(self, "Export", "No crops to export")
            return

        dialog = ExportDialog(current_crops, total_crops, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        config = dialog.get_export_config()
        output_dir = config["output_dir"]
        if not output_dir:
            QMessageBox.warning(self, "Export", "Please select an output directory")
            return

        try:
            exported, errors = self._export_ctrl.export(config, self._canvas)
            msg = f"Successfully exported {exported} photos\n→ {output_dir}"
            if errors:
                msg += f"\n\nFailed {len(errors)}:\n" + "\n".join(errors)
            QMessageBox.information(self, "Export Complete", msg)
            show_toast(f"Export complete: {exported} images to {output_dir}", self)
            self._app_state.status_message.emit(
                f"Export complete: {exported} images → {output_dir}"
            )
        except (ValueError, RuntimeError, OSError) as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _on_clear(self) -> None:
        self._canvas.clear_crops()
        self._app_state.status_message.emit("All crops cleared")
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

    def _on_delete_selected(self) -> None:
        """Delete 键删除选中裁剪框"""
        self._canvas.remove_selected()
        self._update_button_states()

    def _toggle_view(self) -> None:
        """Tab 键在 Grid/Single 之间切换"""
        if self._view_coord.is_single:
            self._view_coord.show_grid()
        elif self._view_coord.is_grid:
            self._on_single_clicked()

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
        self._canvas.push_undo_state()
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
                    self._canvas.clear_scene_selection()
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
                self._canvas.clear_scene_selection()
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
                    self._canvas.remove_crop_item(items[local_idx])

            if self._app_state._current_key != target_key:
                self._image_list_panel.select_image(target_key)
                self._on_image_selected(target_key)
                QTimer.singleShot(0, _do_delete)
            else:
                _do_delete()
        else:
            items = self._canvas.crop_items
            if 0 <= index < len(items):
                self._canvas.remove_crop_item(items[index])

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
            self._canvas.clear_scene_selection()
            items[index].setSelected(True)

    def _on_image_loaded(self) -> None:
        self._update_button_states()

        if self._view_coord.is_empty:
            self._view_coord.show_grid()

        # 延迟 fitInView：先取消上一次未执行的调用，再重启定时器。
        # _display_image 内部的 fitInView 可能在 viewport 尺寸为 0 时执行（Empty 页面），
        # 用 singleShot(0) 保证 viewport 就绪后再适配。
        self._fit_timer.start()

    def _do_fit_in_view(self) -> None:
        """延迟执行的 fitInView（由 _fit_timer 触发，确保 viewport 已就绪）"""
        self._canvas.fitInView(
            self._canvas.scene_rect(),
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
                f"{img_count} active · PDF {sess.page_count} pages"
            )
        elif crop_count > 0:
            self._app_state.status_message.emit(
                f"{img_count} active · {crop_count} crops"
            )
        else:
            self._app_state.status_message.emit(
                f"{img_count} active"
            )

    def _on_detection_done(self, _count: int) -> None:
        self._update_button_states()
        self._update_image_list_panel()

    def _on_rects_changed(self) -> None:
        count = len(self._canvas.crop_rects)
        self._app_state.status_message.emit(
            f"{self._app_state.session_count} active · {count} crops"
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
        QMessageBox.critical(self, "Load Failed", f"Cannot open file:\n{error}")

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
        self._btn_undo.setEnabled(self._canvas.can_undo())
        self._btn_redo.setEnabled(self._canvas.can_redo())

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
                self._canvas.scene_rect(),
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
