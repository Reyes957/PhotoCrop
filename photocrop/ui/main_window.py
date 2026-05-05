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
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QColor, QFont, QPalette, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QFrame,
)

from photocrop.export.cropper import export_photo
from photocrop.ui.canvas import CropCanvas
from photocrop.ui.crop_item import CropItem


# ============================================================
# Apple 设计常量
# ============================================================

APPLE_BLUE = "#0071e3"
APPLE_BLUE_HOVER = "#2997ff"
APPLE_BLUE_PRESSED = "#005bb5"
DARK_BG = "#1d1d1f"
LIGHT_BG = "#f5f5f7"
WHITE = "#ffffff"
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

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._update_button_states()

    def _setup_ui(self) -> None:
        self._canvas = CropCanvas(self)
        self.setCentralWidget(self._canvas)

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
        self._btn_prev_page.setFixedSize(28, 28)
        self._btn_prev_page.setToolTip("上一页")
        page_layout.addWidget(self._btn_prev_page)

        self._lbl_page_info = QLabel("1 / 1")
        self._lbl_page_info.setProperty("pageInfo", True)
        self._lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_page_info.setFixedWidth(60)
        page_layout.addWidget(self._lbl_page_info)

        self._btn_next_page = QPushButton("▶")
        self._btn_next_page.setFixedSize(28, 28)
        self._btn_next_page.setToolTip("下一页")
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
        self._btn_clear.setProperty("secondary", True)
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

    @property
    def _selected_detector(self) -> str:
        """获取当前选择的检测器标识"""
        idx = self._combo_detector.currentIndex()
        return DETECTOR_OPTIONS[idx][1]

    # ---- 槽函数 ----

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片或 PDF",
            "",
            "所有支持格式 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.pdf);;图片 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;PDF (*.pdf);;所有文件 (*)",
        )
        if not path:
            return

        try:
            self._canvas.load_image(path)
        except ImportError as e:
            QMessageBox.critical(self, "缺少依赖", str(e))
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法打开文件:\n{e}")

    def _on_detect(self) -> None:
        detector = self._selected_detector
        max_count = self._spin_max_count.value()

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

    def _on_clear(self) -> None:
        self._canvas.clear_crops()
        self._lbl_status.setText("已清除所有裁剪框")
        self._update_button_states()

    def _on_export(self) -> None:
        rects = self._canvas.crop_rects
        if not rects:
            QMessageBox.information(self, "导出", "没有裁剪框可以导出")
            return

        source_img = self._canvas.source_image
        if source_img is None:
            return

        # 选择导出目录和格式
        output_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not output_dir:
            return

        output_dir = Path(output_dir)
        source_name = "image"
        if self._canvas.source_path:
            source_name = self._canvas.source_path.stem

        # 询问导出格式
        format_choice = QMessageBox.question(
            self,
            "导出格式",
            "选择导出格式：\n\n是 = JPEG（白色填充，文件更小）\n否 = PNG（支持透明通道）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )

        if format_choice == QMessageBox.StandardButton.Cancel:
            return

        suffix = ".jpg" if format_choice == QMessageBox.StandardButton.Yes else ".png"

        exported = 0
        errors = []

        for i, rect in enumerate(rects):
            out_name = f"{source_name}_{i + 1:02d}{suffix}"
            out_path = output_dir / out_name

            try:
                export_photo(source_img, rect, out_path)
                exported += 1
            except Exception as e:
                errors.append(f"#{i + 1}: {e}")

        msg = f"成功导出 {exported} 张照片"
        if errors:
            msg += f"\n\n失败 {len(errors)} 张:\n" + "\n".join(errors)

        QMessageBox.information(self, "导出完成", msg)
        self._lbl_status.setText(f"导出完成: {exported} 张")

    def _on_prev_page(self) -> None:
        self._canvas.prev_page()

    def _on_next_page(self) -> None:
        self._canvas.next_page()

    def _on_image_loaded(self) -> None:
        self._update_button_states()
        w, h = self._canvas.source_image.size

        # 显示/隐藏 PDF 导航
        is_pdf = self._canvas.total_pages > 0
        self._page_nav_widget.setVisible(is_pdf)

        if is_pdf:
            self._lbl_status.setText(f"PDF 已加载: {self._canvas.total_pages} 页")
        else:
            self._lbl_status.setText(f"已加载: {w} × {h} 像素")

    def _on_detection_done(self, count: int) -> None:
        self._update_button_states()

    def _on_rects_changed(self) -> None:
        self._update_button_states()
        count = len(self._canvas.crop_rects)
        if count > 0:
            self._lbl_info.setText(f"{count} 个裁剪框")
        else:
            self._lbl_info.setText("")

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
