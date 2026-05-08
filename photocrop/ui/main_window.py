"""
MainWindow — PhotoCrop 主窗口

Apple 设计风格：
- 深色顶栏（frosted glass 效果）
- Apple Blue (#0071e3) 按钮
- 浅灰背景 (#f5f5f7)
- SF Pro 字体
- 精致的间距和排版
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
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
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from photocrop.engine.core import detect_rectangles
from photocrop.export.cropper import export_photo
from photocrop.ui.canvas import CropCanvas
from photocrop.ui.crop_options_panel import CropOptionsPanel
from photocrop.ui.export_dialog import ExportDialog
from photocrop.ui.extracted_images_panel import ExtractedImagesPanel
from photocrop.ui.image_list_panel import ImageListPanel
from photocrop.ui.session import ImageSession
from photocrop.ui.single_view_panel import SingleViewPanel
from photocrop.utils.crop_rect import CropRect

# ============================================================
# Apple 设计常量
# ============================================================

APPLE_BLUE = "#0071e3"
APPLE_BLUE_HOVER = "#2997ff"
APPLE_BLUE_PRESSED = "#005bb5"
DARK_BG = "#1d1d1f"
LIGHT_BG = "#f5f5f7"
WHITE = "#ffffff"
TEXT_PRIMARY = "#f5f5f7"
TEXT_DARK = "#1d1d1f"
TEXT_SECONDARY = "rgba(0,0,0,0.48)"
SEPARATOR = "rgba(0,0,0,0.1)"

FONT_DISPLAY = "SF Pro Display, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"
FONT_BODY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"

# 检测器选项
DETECTOR_OPTIONS = [
    ("CV（默认）", "cv"),
    ("增强 CV", "enhanced-cv"),
    ("组合检测", "combined"),
    ("YOLO-World", "yolo-world"),
]


# ============================================================
# PDF 批量检测后台任务
# ============================================================

class PageDetectionSignals(QObject):
    """批量检测任务信号"""
    page_done = Signal(int, list)  # (page_idx, [CropRect])
    error = Signal(str)


class PageDetectionTask(QRunnable):
    """单页检测任务（在后台线程池中运行）"""

    def __init__(self, page_idx: int, page_img: Image.Image,
                 detector: str, max_count: int):
        super().__init__()
        self.page_idx = page_idx
        self.page_img = page_img.copy()  # 避免线程冲突
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
# 样式表
# ============================================================

STYLE_SHEET = f"""
QMainWindow {{
    background-color: {LIGHT_BG};
}}

/* 工具栏 — 深色 frosted glass */
QToolBar {{
    background-color: rgba(29, 29, 31, 0.95);
    border: none;
    padding: 10px 20px;
    spacing: 10px;
}}

QToolBar::separator {{
    width: 1px;
    background: rgba(255, 255, 255, 0.15);
    margin: 4px 8px;
}}

/* 主按钮 — Apple Blue 胶囊 */
QPushButton {{
    background-color: {APPLE_BLUE};
    color: {WHITE};
    border: none;
    border-radius: 980px;
    padding: 8px 20px;
    font-family: {FONT_BODY};
    font-size: 13px;
    font-weight: 400;
    min-height: 28px;
    letter-spacing: -0.2px;
}}

QPushButton:hover {{
    background-color: {APPLE_BLUE_HOVER};
}}

QPushButton:pressed {{
    background-color: {APPLE_BLUE_PRESSED};
}}

QPushButton:disabled {{
    background-color: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.3);
}}

/* 次要按钮 — 描边风格 */
QPushButton[secondary="true"] {{
    background-color: transparent;
    color: {APPLE_BLUE};
    border: 1px solid {APPLE_BLUE};
}}

QPushButton[secondary="true"]:hover {{
    background-color: rgba(0, 113, 227, 0.1);
}}

/* 工具栏内标签 */
QLabel {{
    font-family: {FONT_BODY};
    font-size: 13px;
    color: rgba(255, 255, 255, 0.85);
    letter-spacing: -0.2px;
}}

QLabel[pageInfo="true"] {{
    color: rgba(255, 255, 255, 0.6);
    font-size: 12px;
}}

/* 状态栏 */
QStatusBar {{
    background-color: rgba(255, 255, 255, 0.9);
    border-top: 1px solid {SEPARATOR};
    font-family: {FONT_BODY};
    font-size: 12px;
    color: {TEXT_SECONDARY};
    padding: 4px 16px;
    letter-spacing: -0.1px;
}}

/* 数值输入 */
QSpinBox {{
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    padding: 4px 8px;
    font-family: {FONT_BODY};
    font-size: 13px;
    background: rgba(255, 255, 255, 0.1);
    color: white;
    min-width: 50px;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    border: none;
    background: transparent;
}}

QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid rgba(255, 255, 255, 0.6);
}}

QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(255, 255, 255, 0.6);
}}

/* 下拉框 */
QComboBox {{
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    padding: 4px 8px;
    font-family: {FONT_BODY};
    font-size: 13px;
    background: rgba(255, 255, 255, 0.1);
    color: white;
    min-width: 90px;
}}

QComboBox:hover {{
    border-color: rgba(255, 255, 255, 0.4);
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {DARK_BG};
    color: white;
    selection-background-color: {APPLE_BLUE};
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
}}
"""


# ============================================================
# MainWindow
# ============================================================

class MainWindow(QMainWindow):
    """PhotoCrop 主窗口

    布局：
    - 顶部工具栏（深色 frosted glass）
    - 中央画布（深色背景）
    - 底部状态栏
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PhotoCrop")
        self.setMinimumSize(900, 600)
        self.resize(1280, 800)

        self.setStyleSheet(STYLE_SHEET)

        # 多图像会话管理
        self._sessions: dict = {}       # key=path_str → ImageSession
        self._current_key: str | None = None

        # 防抖定时器 — 避免 rects_changed 信号风暴导致按钮闪烁
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_button_states)

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._setup_shortcuts()
        self._update_button_states()

    def _setup_ui(self) -> None:
        # 外层容器: 上部内容 + 底部按钮栏
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 上部: 左侧图像列表 + 中间画布/单视图 + 右侧面板
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._image_list_panel = ImageListPanel()
        content_layout.addWidget(self._image_list_panel)

        # 中间: QStackedWidget 切换 Canvas / SingleView
        self._view_stack = QStackedWidget()

        self._canvas = CropCanvas(self)
        self._view_stack.addWidget(self._canvas)  # index 0 = Grid View

        self._single_view = SingleViewPanel()
        self._view_stack.addWidget(self._single_view)  # index 1 = Single View

        content_layout.addWidget(self._view_stack, 1)

        # 右侧面板: CropOptions + ExtractedImages
        right_panel = QWidget()
        right_panel.setFixedWidth(220)
        right_panel.setStyleSheet("background-color: #2c2c2e;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._crop_options_panel = CropOptionsPanel()
        right_layout.addWidget(self._crop_options_panel)

        self._extracted_panel = ExtractedImagesPanel()
        right_layout.addWidget(self._extracted_panel, 1)

        content_layout.addWidget(right_panel)

        outer_layout.addWidget(content, 1)

        # 底部按钮栏
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(44)
        bottom_bar.setStyleSheet("background-color: #2c2c2e;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        bottom_layout.setSpacing(8)

        # Grid/Single 切换按钮组
        self._btn_grid = QPushButton("Grid View")
        self._btn_grid.setCheckable(True)
        self._btn_grid.setChecked(True)
        self._btn_grid.setFixedWidth(80)
        self._btn_grid.setStyleSheet(self._view_toggle_style(True))
        self._btn_grid.clicked.connect(lambda: self._switch_view(0))
        bottom_layout.addWidget(self._btn_grid)

        self._btn_single = QPushButton("Single View")
        self._btn_single.setCheckable(True)
        self._btn_single.setFixedWidth(80)
        self._btn_single.setStyleSheet(self._view_toggle_style(False))
        self._btn_single.clicked.connect(lambda: self._switch_view(1))
        bottom_layout.addWidget(self._btn_single)

        bottom_layout.addStretch()

        # 导出按钮 (也放在底部)
        self._btn_export_page = QPushButton("导出当前页")
        self._btn_export_page.setProperty("secondary", "true")
        self._btn_export_page.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {APPLE_BLUE};
                border: 1px solid {APPLE_BLUE};
                border-radius: 6px;
                padding: 6px 16px;
                font-family: {FONT_BODY};
                font-size: 12px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 113, 227, 0.1);
            }}
            QPushButton:disabled {{
                color: rgba(255,255,255,0.3);
                border-color: rgba(255,255,255,0.15);
            }}
        """)
        self._btn_export_page.clicked.connect(self._on_export)
        bottom_layout.addWidget(self._btn_export_page)

        outer_layout.addWidget(bottom_bar)

        self.setCentralWidget(outer)

        self._view_mode = 0  # 0=Grid, 1=Single

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        # 加载图片 / PDF
        self._btn_load = QPushButton("加载图片")
        self._btn_load.setToolTip("打开图片或 PDF 文件")
        toolbar.addWidget(self._btn_load)

        # PDF 页面导航（初始隐藏）
        self._page_nav_widget = QWidget()
        page_layout = QHBoxLayout(self._page_nav_widget)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)

        self._btn_prev_page = QPushButton("◀")
        self._btn_prev_page.setFixedSize(32, 32)
        self._btn_prev_page.setToolTip("上一页（←）")
        page_layout.addWidget(self._btn_prev_page)

        self._lbl_page_info = QLabel("1 / 1")
        self._lbl_page_info.setProperty("pageInfo", True)
        self._lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_page_info.setFixedWidth(60)
        page_layout.addWidget(self._lbl_page_info)

        self._btn_next_page = QPushButton("▶")
        self._btn_next_page.setFixedSize(32, 32)
        self._btn_next_page.setToolTip("下一页（→）")
        page_layout.addWidget(self._btn_next_page)

        toolbar.addWidget(self._page_nav_widget)
        self._page_nav_widget.setVisible(False)

        toolbar.addSeparator()

        # 检测器选择
        toolbar.addWidget(QLabel("  检测器:"))
        self._combo_detector = QComboBox()
        for label, _ in DETECTOR_OPTIONS:
            self._combo_detector.addItem(label)
        self._combo_detector.setFixedWidth(120)
        self._combo_detector.setToolTip("选择检测算法")
        toolbar.addWidget(self._combo_detector)

        # 检测
        self._btn_detect = QPushButton("检测照片")
        self._btn_detect.setToolTip("自动检测页面中的照片")
        self._btn_detect.setEnabled(False)
        toolbar.addWidget(self._btn_detect)

        # 最大检测数
        toolbar.addWidget(QLabel("  数量:"))
        self._spin_max_count = QSpinBox()
        self._spin_max_count.setRange(1, 10)
        self._spin_max_count.setValue(4)
        self._spin_max_count.setFixedWidth(60)
        toolbar.addWidget(self._spin_max_count)

        toolbar.addSeparator()

        # 清除
        self._btn_clear = QPushButton("清除裁剪框")
        self._btn_clear.setProperty("secondary", "true")
        self._btn_clear.setEnabled(False)
        toolbar.addWidget(self._btn_clear)

        # 弹簧
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # 导出
        self._btn_export = QPushButton("导出全部")
        self._btn_export.setToolTip("导出所有裁剪框为单独图片")
        self._btn_export.setEnabled(False)
        toolbar.addWidget(self._btn_export)

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        # 左侧状态
        self._lbl_status = QLabel("就绪 — 加载图片或 PDF 开始")
        self._statusbar.addWidget(self._lbl_status)

        # 右侧信息
        self._lbl_info = QLabel("")
        self._statusbar.addPermanentWidget(self._lbl_info)

    def _connect_signals(self) -> None:
        self._btn_load.clicked.connect(self._on_load)
        self._btn_detect.clicked.connect(self._on_detect)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_prev_page.clicked.connect(self._on_prev_page)
        self._btn_next_page.clicked.connect(self._on_next_page)

        self._canvas.image_loaded.connect(self._on_image_loaded)
        self._canvas.detection_done.connect(self._on_detection_done)
        self._canvas.rects_changed.connect(self._on_rects_changed)
        self._canvas.page_changed.connect(self._on_page_changed)
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.view_single_requested.connect(self._on_view_single_requested)

        # CropOptionsPanel 信号
        self._crop_options_panel.rect_changed.connect(self._on_crop_options_changed)
        self._crop_options_panel.editing_finished.connect(self._on_crop_options_finished)
        self._crop_options_panel.aspect_ratio_changed.connect(self._on_aspect_ratio_changed)

        # ExtractedImagesPanel 信号
        self._extracted_panel.crop_selected.connect(self._on_extracted_crop_selected)
        self._extracted_panel.crop_delete_requested.connect(self._on_extracted_crop_delete)

        # SingleViewPanel 信号
        self._single_view.exit_requested.connect(lambda: self._switch_view(0))
        self._single_view.selection_changed.connect(self._on_single_view_selection)

        # 图像列表面板信号
        self._image_list_panel.image_selected.connect(self._switch_image)
        self._image_list_panel.re_detect_requested.connect(self._on_re_detect)
        self._image_list_panel.remove_requested.connect(self._on_remove_from_list)

    def _setup_shortcuts(self) -> None:
        """设置键盘快捷键"""
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._on_load)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._on_detect)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._on_export)
        QShortcut(QKeySequence("Left"), self, activated=self._on_prev_page)
        QShortcut(QKeySequence("Right"), self, activated=self._on_next_page)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._on_redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._on_redo)

    @property
    def _selected_detector(self) -> str:
        """获取当前选择的检测器标识"""
        idx = self._combo_detector.currentIndex()
        return DETECTOR_OPTIONS[idx][1]

    # ---- 槽函数 ----

    def _on_load(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片或 PDF",
            "",
            "所有支持格式 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.pdf);;图片 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;PDF (*.pdf);;所有文件 (*)",
        )
        if not paths:
            return

        for path_str in paths:
            self._load_single_file(path_str)

        # 选中最后加载的（PDF 选中第一页）
        if paths:
            last_path = paths[-1]
            if Path(last_path).suffix.lower() == ".pdf":
                self._image_list_panel.select_image(f"{last_path}::page_0")
            else:
                self._image_list_panel.select_image(last_path)

    def _load_single_file(self, path_str: str) -> None:
        """加载单个文件并创建 session"""
        path = Path(path_str)

        try:
            # 先保存当前 session 的状态（必须在 load_image 之前，否则 canvas 已被清除）
            self._save_current_session()

            # 判断是否 PDF
            is_pdf = path.suffix.lower() == ".pdf"

            if is_pdf:
                from photocrop.export.pdf_reader import pdf_to_images
                # 用较低 DPI 生成缩略图（快速），大图按需加载
                thumb_pages = pdf_to_images(path, dpi=72)
                page_count = len(thumb_pages)
                if page_count == 0:
                    raise ValueError("PDF 没有可读取的页面")

                # 生成每页缩略图（44×44）
                page_thumbs: list[Image.Image] = []
                for _, img in thumb_pages:
                    t = img.copy()
                    t.thumbnail((44, 44), Image.Resampling.LANCZOS)
                    page_thumbs.append(t)

                # 高 DPI 页面加载器（按需渲染）
                def page_loader(idx: int) -> Image.Image:
                    from photocrop.export.pdf_reader import pdf_to_images
                    pages = pdf_to_images(path, dpi=200)
                    if 0 <= idx < len(pages):
                        return pages[idx][1]
                    raise IndexError(f"Page {idx} out of range")

                # 第一页作为初始显示
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

                # 预填充预览缓存（使用 72 DPI 缩略图，不再重新渲染）
                for pg_idx, (_, pg_img) in enumerate(thumb_pages):
                    sess.set_page_preview(pg_idx, pg_img)

                self._sessions[path_str] = sess
                self._current_key = path_str

                # 加载第一页到 canvas
                self._canvas.load_pil_image(first_page_img)

                # 启用全局预览模式
                self._extracted_panel.set_global_mode(True)

                # 添加到列表面板（PDF 展开模式）
                first_thumb = page_thumbs[0] if page_thumbs else first_page_img.copy()
                self._image_list_panel.add_image(
                    key=path_str,
                    filename=path.name,
                    thumbnail=first_thumb,
                    page_count=page_count,
                    page_thumbnails=page_thumbs,
                )
            else:
                # 普通图片
                self._canvas.load_image(path_str)

                sess = ImageSession(
                    source_path=path,
                    source_image=self._canvas.source_image,
                    crop_rects=[],
                    undo_snapshot=self._canvas._undo_manager.serialize(),
                )
                self._sessions[path_str] = sess
                self._current_key = path_str

                # 禁用全局预览模式
                self._extracted_panel.set_global_mode(False)

                # 生成缩略图
                thumb = self._canvas.source_image.copy()
                thumb.thumbnail((100, 100), Image.Resampling.LANCZOS)

                # 添加到列表面板
                self._image_list_panel.add_image(
                    key=path_str,
                    filename=path.name,
                    thumbnail=thumb,
                    crop_count=0,
                )

            self._update_image_list_panel()

        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法打开文件:\n{e}")

    def _save_current_session(self) -> None:
        """保存当前 session 的状态"""
        if not self._current_key:
            return

        if "::page_" in self._current_key:
            # PDF 页面：保存到父 session 的 page_crop_rects / page_undo_snapshots
            pdf_key, page_str = self._current_key.rsplit("::page_", 1)
            page_idx = int(page_str)
            sess = self._sessions.get(pdf_key)
            if sess is None:
                return
            sess.page_crop_rects[page_idx] = list(self._canvas.crop_rects)
            sess.page_undo_snapshots[page_idx] = self._canvas._undo_manager.serialize()
        elif self._current_key in self._sessions:
            sess = self._sessions[self._current_key]
            sess.crop_rects = list(self._canvas.crop_rects)
            sess.undo_snapshot = self._canvas._undo_manager.serialize()

    def _switch_image(self, key: str) -> None:
        """切换到另一张图片（支持 PDF 页面 key）"""
        if key == self._current_key:
            return

        # 1. 保存当前
        self._save_current_session()

        if "::page_" in key:
            # PDF 页面切换
            pdf_key, page_str = key.rsplit("::page_", 1)
            page_idx = int(page_str)
            sess = self._sessions.get(pdf_key)
            if sess is None:
                return

            img = sess.get_page_image(page_idx)
            self._canvas.load_pil_image(img)

            # 恢复该页的裁剪框和撤销历史
            page_rects = sess.page_crop_rects.get(page_idx, [])
            self._canvas._restore_rects(page_rects)

            if page_idx in sess.page_undo_snapshots:
                self._canvas._undo_manager.deserialize(sess.page_undo_snapshots[page_idx])
            else:
                self._canvas._undo_manager.clear()
                self._canvas._undo_manager.push_state([])

            sess.current_pdf_page = page_idx
            self._current_key = key

            # 更新预览面板：全局模式显示所有页面
            self._extracted_panel.set_source_image(img)
            self._extracted_panel.set_global_mode(True)
            self._refresh_global_preview(sess, page_idx)
        elif key in self._sessions:
            # 普通图片 / PDF 父项（非 page key）
            sess = self._sessions[key]
            self._canvas.load_pil_image(sess.source_image)
            self._canvas._undo_manager.deserialize(sess.undo_snapshot)
            self._canvas._restore_rects(sess.crop_rects)
            self._current_key = key

            # 更新预览面板：单图用单页模式
            self._extracted_panel.set_source_image(sess.source_image)
            self._extracted_panel.set_global_mode(False)
        else:
            return

        self._update_button_states()
        self._update_image_list_panel()

    def _on_re_detect(self, key: str) -> None:
        """右键菜单：重新检测"""
        if key not in self._sessions:
            return
        # 切换到该图片
        if key != self._current_key:
            self._image_list_panel.select_image(key)
        # 触发检测
        self._on_detect()

    def _on_remove_from_list(self, key: str) -> None:
        """右键菜单：从列表移除（支持 PDF 父项和页面 key）"""
        # 如果 key 是页面 key，提取父 key
        session_key = key
        if "::page_" in key:
            session_key = key.rsplit("::page_", 1)[0]

        if session_key not in self._sessions:
            return

        # 如果移除的是当前图片（或当前图片属于被移除的 PDF），先切换到其他图片
        current_session_key = self._current_key
        if current_session_key and "::page_" in current_session_key:
            current_session_key = current_session_key.rsplit("::page_", 1)[0]

        if session_key == current_session_key:
            keys = list(self._sessions.keys())
            idx = keys.index(session_key)
            if len(keys) > 1:
                next_key = keys[idx - 1] if idx > 0 else keys[1]
                # 如果下一个是 PDF，选中其第一页
                next_sess = self._sessions[next_key]
                if next_sess.is_pdf:
                    self._switch_image(f"{next_key}::page_0")
                else:
                    self._switch_image(next_key)
            else:
                self._current_key = None
                self._canvas.clear_all()
                self._extracted_panel.set_global_mode(False)

        del self._sessions[session_key]
        self._image_list_panel.remove_image(session_key)
        self._update_image_list_panel()

    def _update_image_list_panel(self) -> None:
        """更新图像列表面板的裁剪框数量和统计"""
        total_crops = 0
        for key, sess in self._sessions.items():
            if sess.is_pdf:
                # PDF：更新每页的裁剪计数
                for page_idx in range(sess.page_count):
                    page_key = f"{key}::page_{page_idx}"
                    if page_key == self._current_key:
                        count = len(self._canvas.crop_rects)
                    else:
                        count = len(sess.page_crop_rects.get(page_idx, []))
                    self._image_list_panel.update_crop_count(page_key, count)
                    total_crops += count
            else:
                # 单图
                if key == self._current_key:
                    count = len(self._canvas.crop_rects)
                else:
                    count = len(sess.crop_rects)
                self._image_list_panel.update_crop_count(key, count)
                total_crops += count

        self._image_list_panel.update_total(len(self._sessions), total_crops)

    def _get_current_pdf_session(self) -> ImageSession | None:
        """获取当前 PDF 的 session（如果当前在 PDF 页面上）"""
        if not self._current_key or "::page_" not in self._current_key:
            return None
        pdf_key = self._current_key.rsplit("::page_", 1)[0]
        return self._sessions.get(pdf_key)

    def _refresh_global_preview(self, sess: ImageSession,
                                current_page: int = -1) -> None:
        """刷新全局预览面板（跨页模式）

        使用预览缓存（低 DPI 缩略图）避免重新渲染高 DPI 页面图像。
        仅当前编辑页使用 canvas 实时数据。
        """
        pages_data = []
        for page_idx in range(sess.page_count):
            rects = sess.page_crop_rects.get(page_idx, [])
            # 优先用预览缓存（不触发高 DPI 渲染）
            img = sess.get_page_preview(page_idx)
            if img is None:
                # fallback：用高 DPI（慢，但只在缓存缺失时发生）
                try:
                    img = sess.get_page_image(page_idx)
                    sess.set_page_preview(page_idx, img)
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

        # 解析当前 session，判断是否 PDF 多页
        sess = None
        if self._current_key:
            if "::page_" in self._current_key:
                pdf_key = self._current_key.rsplit("::page_", 1)[0]
                sess = self._sessions.get(pdf_key)
            else:
                sess = self._sessions.get(self._current_key)

        if sess is not None and sess.is_pdf and sess.page_count > 1:
            # 多页 PDF → 批量检测
            self._run_batch_detection(sess, detector, max_count)
            return

        # 单页检测（保留原有逻辑）
        self._lbl_status.setText(f"正在检测（{detector}）...")
        QApplication.processEvents()  # 刷新 UI

        try:
            count = self._canvas.detect(
                detector=detector,
                max_count=max_count,
            )
            self._lbl_status.setText(f"检测到 {count} 个照片")
        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
            self._lbl_status.setText("检测失败")
        except Exception as e:
            QMessageBox.critical(self, "检测失败", str(e))
            self._lbl_status.setText("检测失败")

    def _run_batch_detection(self, sess: ImageSession,
                             detector: str, max_count: int) -> None:
        """PDF 批量检测：后台线程 + 进度条 + 增量预览"""
        total = sess.page_count

        # 清除之前的检测结果
        for page_idx in range(total):
            sess.page_crop_rects[page_idx] = []

        # 切换到 Grid View 以显示预览
        if self._view_mode != 0:
            self._switch_view(0)

        # 清除并准备增量预览面板
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

            # 更新左侧列表裁剪计数
            page_key = f"{pdf_key}::page_{page_idx}"
            self._image_list_panel.update_crop_count(page_key, len(crop_rects))

            # 增量追加到预览面板
            try:
                page_img = sess.get_page_image(page_idx)
                self._extracted_panel.add_page_results(page_idx, page_img, crop_rects)
            except (RuntimeError, IndexError):
                pass

            self._detected_pages.add(page_idx)

        def on_error(msg: str) -> None:
            print(f"[Detection] {msg}")

        # 创建并启动任务
        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(1)  # 串行执行，避免内存压力

        tasks: list[PageDetectionTask] = []
        for page_idx in range(total):
            try:
                img = sess.get_page_image(page_idx)
            except (RuntimeError, IndexError):
                self._detected_pages.add(page_idx)
                continue

            task = PageDetectionTask(page_idx, img, detector, max_count)
            task.signals.page_done.connect(on_page_done)
            task.signals.error.connect(on_error)
            tasks.append(task)
            pool.start(task)

        # 进度轮询
        def check_progress() -> None:
            if self._detect_cancelled:
                return
            done = len(self._detected_pages)
            progress.setValue(done)
            if done < total:
                QTimer.singleShot(100, check_progress)
            else:
                progress.close()
                total_rects = sum(
                    len(sess.page_crop_rects.get(i, []))
                    for i in range(total)
                )
                self._lbl_status.setText(
                    f"检测完成: {total} 页, {total_rects} 个裁剪框"
                )
                self._update_image_list_panel()
                # 刷新全局预览（使用当前页的实时数据）
                current_page = sess.current_pdf_page
                self._refresh_global_preview(sess, current_page)

        QTimer.singleShot(100, check_progress)

        def on_cancel() -> None:
            self._detect_cancelled = True
            for t in tasks:
                t.cancel()
            progress.close()
            self._lbl_status.setText(
                f"批量检测已取消（已完成 {len(self._detected_pages)}/{total} 页）"
            )

        progress.canceled.connect(on_cancel)

    def _on_clear(self) -> None:
        self._canvas.clear_crops()
        self._lbl_status.setText("已清除所有裁剪框")
        self._update_button_states()
        # PDF 全局模式下同步清除预览
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            current_page = -1
            if "::page_" in (self._current_key or ""):
                current_page = int(self._current_key.rsplit("::page_", 1)[1])
                pdf_sess.page_crop_rects[current_page] = []
            self._refresh_global_preview(pdf_sess, current_page)

    def _on_export(self) -> None:
        """打开导出对话框"""
        current_crops = len(self._canvas.crop_rects)
        total_crops = 0
        for key, sess in self._sessions.items():
            if sess.is_pdf:
                # PDF：累加所有页面的裁剪框
                for page_idx in range(sess.page_count):
                    page_key = f"{key}::page_{page_idx}"
                    if page_key == self._current_key:
                        total_crops += len(self._canvas.crop_rects)
                    else:
                        total_crops += len(sess.page_crop_rects.get(page_idx, []))
            else:
                if key == self._current_key:
                    total_crops += len(self._canvas.crop_rects)
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
        template = config.get("template", "{name}_{index:02d}.{ext}")
        scope = config["scope"]

        exported = 0
        errors = []

        if scope == "page":
            # 只导出当前页
            rects = self._canvas.crop_rects
            source_img = self._canvas.source_image
            source_name = "image"
            page_num = 1
            if self._canvas.source_path:
                source_name = self._canvas.source_path.stem
            elif self._current_key and "::page_" in self._current_key:
                # PDF 页面：source_path 为 None，从 session 取文件名和页码
                pdf_key, page_str = self._current_key.rsplit("::page_", 1)
                page_num = int(page_str) + 1
                pdf_sess = self._sessions.get(pdf_key)
                if pdf_sess:
                    source_name = pdf_sess.source_path.stem

            for i, rect in enumerate(rects):
                out_name = template.replace("{name}", source_name) \
                                   .replace("{page}", str(page_num)) \
                                   .replace("{index:02d}", f"{i + 1:02d}") \
                                   .replace("{index}", str(i + 1)) \
                                   .replace("{ext}", suffix.lstrip("."))
                out_path = output_dir / out_name
                try:
                    export_photo(source_img, rect, out_path,
                                 auto_rotate=auto_rotate, trim_white=trim_white,
                                 quality=quality, max_width=max_w, max_height=max_h)
                    exported += 1
                except Exception as e:
                    errors.append(f"#{i + 1}: {e}")
        else:
            # 导出全部 session
            for key, sess in self._sessions.items():
                source_name = sess.source_path.stem

                if sess.is_pdf:
                    # PDF：导出所有页面的裁剪框
                    for page_idx in range(sess.page_count):
                        page_key = f"{key}::page_{page_idx}"
                        if page_key == self._current_key:
                            rects = list(self._canvas.crop_rects)
                            source_img = self._canvas.source_image
                        else:
                            rects = sess.page_crop_rects.get(page_idx, [])
                            source_img = sess.get_page_image(page_idx) if rects else None

                        if not rects or source_img is None:
                            continue

                        for i, rect in enumerate(rects):
                            out_name = template.replace("{name}", source_name) \
                                               .replace("{page}", str(page_idx + 1)) \
                                               .replace("{index:02d}", f"{i + 1:02d}") \
                                               .replace("{index}", str(i + 1)) \
                                               .replace("{ext}", suffix.lstrip("."))
                            out_path = output_dir / out_name
                            try:
                                export_photo(source_img, rect, out_path,
                                             auto_rotate=auto_rotate, trim_white=trim_white,
                                             quality=quality, max_width=max_w, max_height=max_h)
                                exported += 1
                            except Exception as e:
                                errors.append(f"{source_name} p{page_idx + 1} #{i + 1}: {e}")
                else:
                    # 单图
                    if key == self._current_key:
                        rects = self._canvas.crop_rects
                        source_img = self._canvas.source_image
                    else:
                        rects = sess.crop_rects
                        source_img = sess.source_image

                    for i, rect in enumerate(rects):
                        out_name = template.replace("{name}", source_name) \
                                           .replace("{page}", "1") \
                                           .replace("{index:02d}", f"{i + 1:02d}") \
                                           .replace("{index}", str(i + 1)) \
                                           .replace("{ext}", suffix.lstrip("."))
                        out_path = output_dir / out_name
                        try:
                            export_photo(source_img, rect, out_path,
                                         auto_rotate=auto_rotate, trim_white=trim_white,
                                         quality=quality, max_width=max_w, max_height=max_h)
                            exported += 1
                        except Exception as e:
                            errors.append(f"{source_name} #{i + 1}: {e}")

        msg = f"成功导出 {exported} 张照片"
        if errors:
            msg += f"\n\n失败 {len(errors)} 张:\n" + "\n".join(errors)

        QMessageBox.information(self, "导出完成", msg)
        self._lbl_status.setText(f"导出完成: {exported} 张")

    def _on_prev_page(self) -> None:
        self._canvas.prev_page()

    def _on_next_page(self) -> None:
        self._canvas.next_page()

    def _on_undo(self) -> None:
        self._canvas.undo()

    def _on_redo(self) -> None:
        self._canvas.redo()

    def _on_selection_changed(self) -> None:
        """Canvas 选中变化 → 更新 CropOptionsPanel"""
        selected = self._canvas.selected_items
        if not selected:
            return  # 没有选中时不操作，避免 None 覆盖已有选中状态

        rect = selected[-1].crop_rect
        img_size = (0, 0)
        if self._canvas.source_image:
            img_size = self._canvas.source_image.size
        self._crop_options_panel.set_selected_rect(rect, img_size)

    def _on_crop_options_changed(self) -> None:
        """CropOptionsPanel 实时修改 → 刷新画布"""
        # 同步到 CropItem 的视觉
        for item in self._canvas.selected_items:
            item._sync_from_rect()
            item.update()
        self._canvas.rects_changed.emit()

    def _on_crop_options_finished(self) -> None:
        """CropOptionsPanel 编辑完成 → 推入撤销栈"""
        self._canvas._push_undo_state()

    def _on_aspect_ratio_changed(self, ratio: float) -> None:
        """宽高比变化 → 更新选中的 CropItem"""
        for item in self._canvas.selected_items:
            if ratio == 0.0:
                item.aspect_ratio_lock = None
            elif ratio == -1.0:
                # Original: 使用当前宽高比
                if item.crop_rect.height > 0:
                    item.aspect_ratio_lock = item.crop_rect.width / item.crop_rect.height
            else:
                item.aspect_ratio_lock = ratio

    def _on_extracted_crop_selected(self, index: int) -> None:
        """点击预览缩略图 → 选中对应 CropItem"""
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
                self._save_current_session()
                self._image_list_panel.select_image(target_key)
                # 切页后延迟选中，确保 items 已加载
                QTimer.singleShot(0, _do_select)
            else:
                _do_select()
        else:
            items = self._canvas.crop_items
            if 0 <= index < len(items):
                self._canvas._scene.clearSelection()
                items[index].setSelected(True)

    def _on_extracted_crop_delete(self, index: int) -> None:
        """点击预览删除按钮 → 删除对应 CropItem"""
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
                self._save_current_session()
                self._image_list_panel.select_image(target_key)
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
        w, h = self._canvas.source_image.size

        # 更新预览面板源图
        self._extracted_panel.set_source_image(self._canvas.source_image)

        # 显示/隐藏 PDF 导航
        is_pdf = self._canvas.total_pages > 0
        self._page_nav_widget.setVisible(is_pdf)

        if is_pdf:
            self._lbl_status.setText(f"PDF 已加载: {self._canvas.total_pages} 页")
        else:
            self._lbl_status.setText(f"已加载: {w} × {h} 像素")

    def _on_detection_done(self, count: int) -> None:
        self._update_button_states()
        self._update_image_list_panel()

    def _on_rects_changed(self) -> None:
        # 防抖：50ms 内多次信号只触发一次按钮状态刷新
        self._update_timer.start(50)
        count = len(self._canvas.crop_rects)
        if count > 0:
            self._lbl_info.setText(f"{count} 个裁剪框")
        else:
            self._lbl_info.setText("")
        # 更新图像列表面板中的裁剪框计数
        self._update_image_list_panel()

        # 更新提取预览面板
        pdf_sess = self._get_current_pdf_session()
        if pdf_sess is not None and self._extracted_panel._global_mode:
            # PDF 全局模式：更新当前页数据，触发防抖刷新（不重建所有页面图像）
            current_page = -1
            if "::page_" in (self._current_key or ""):
                current_page = int(self._current_key.rsplit("::page_", 1)[1])
                pdf_sess.page_crop_rects[current_page] = list(self._canvas.crop_rects)
            # 直接调 refresh_all_pages 更新数据，复用已有 _all_pages_data 中的图像
            pages_data = list(self._extracted_panel._all_pages_data)
            # 替换当前页的 rects（保留已有图像引用）
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
        self._lbl_page_info.setText(f"{current + 1} / {total}")
        self._update_button_states()

        # 更新页面导航按钮状态
        self._btn_prev_page.setEnabled(current > 0)
        self._btn_next_page.setEnabled(current < total - 1)

    def _update_button_states(self) -> None:
        has_image = self._canvas.source_image is not None
        has_rects = len(self._canvas.crop_rects) > 0

        self._btn_detect.setEnabled(has_image)
        self._btn_clear.setEnabled(has_rects)
        self._btn_export.setEnabled(has_rects)
        self._btn_export_page.setEnabled(has_rects)

    # ---- 视图切换 ----

    def _switch_view(self, mode: int) -> None:
        """切换 Grid / Single 视图"""
        if mode == self._view_mode:
            return

        self._view_mode = mode
        self._view_stack.setCurrentIndex(mode)

        # 更新按钮状态
        self._btn_grid.setChecked(mode == 0)
        self._btn_single.setChecked(mode == 1)
        self._btn_grid.setStyleSheet(self._view_toggle_style(mode == 0))
        self._btn_single.setStyleSheet(self._view_toggle_style(mode == 1))

        # 切换到 Single View 时更新数据
        if mode == 1:
            if self._canvas.source_image:
                self._single_view.set_data(
                    self._canvas.source_image,
                    self._canvas.crop_rects,
                )

    def _on_view_single_requested(self, index: int) -> None:
        """裁剪框工具栏请求切换到 Single View"""
        self._switch_view(1)
        self._single_view.select_crop(index)

    def _on_single_view_selection(self, index: int) -> None:
        """Single View 中选中裁剪框变化"""
        items = self._canvas.crop_items
        if 0 <= index < len(items):
            self._canvas._scene.clearSelection()
            items[index].setSelected(True)

    @staticmethod
    def _view_toggle_style(checked: bool) -> str:
        if checked:
            return f"""
                QPushButton {{
                    background-color: {APPLE_BLUE};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-family: {FONT_BODY};
                    font-size: 11px;
                }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: #86868b;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 4px 12px;
                font-family: {FONT_BODY};
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                border-color: rgba(255,255,255,0.3);
            }}
        """
