"""
ExportDialog — 批量导出设置对话框

对标 AutoCropper 底部导出按钮弹出的对话框。
支持格式选择、质量设置、尺寸限制、文件名模板。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# ============================================================
# 样式常量
# ============================================================

PANEL_BG = "#F5F5F5"
TEXT_PRIMARY = "#1A1A1A"
TEXT_SECONDARY = "#666666"
APPLE_BLUE = "#000000"
DARK_BG = "#F5F5F5"
FONT_FAMILY = "SF Pro Text, Helvetica Neue, Helvetica, Arial, sans-serif"


class ExportDialog(QDialog):
    """批量导出设置对话框

    返回用户选择的导出参数。
    """

    def __init__(self, current_page_crops: int = 0, total_crops: int = 0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("导出设置")
        self.setMinimumWidth(420)
        # BUG-044 fix: 初始化 _export_scope，默认为 "page"
        self._export_scope = "page"
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {PANEL_BG};
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
                font-size: 12px;
            }}
            QGroupBox {{
                color: {TEXT_PRIMARY};
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 16px;
                font-size: 11px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {TEXT_SECONDARY};
            }}
            QComboBox, QSpinBox, QLineEdit {{
                background-color: #FFFFFF;
                color: {TEXT_PRIMARY};
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                min-height: 22px;
            }}
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{
                border-color: #999999;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
                font-size: 12px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid #999999;
                background: #FFFFFF;
            }}
            QCheckBox::indicator:checked {{
                background: {APPLE_BLUE};
                border-color: {APPLE_BLUE};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: #CCCCCC;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: {APPLE_BLUE};
                border-radius: 7px;
            }}
            QPushButton {{
                background-color: {APPLE_BLUE};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: #333333;
            }}
            QPushButton[secondary="true"] {{
                background-color: transparent;
                color: {APPLE_BLUE};
                border: 1px solid {APPLE_BLUE};
            }}
        """)

        self._current_page_crops = current_page_crops
        self._total_crops = total_crops
        self._settings = QSettings("PhotoCrop", "PhotoCrop")

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 输出目录
        dir_group = QWidget()
        dir_layout = QHBoxLayout(dir_group)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(8)

        lbl_dir = QLabel("输出目录")
        lbl_dir.setFixedWidth(60)
        dir_layout.addWidget(lbl_dir)

        self._edit_dir = QLineEdit()
        last_dir = self._settings.value("export/last_dir", "")
        self._edit_dir.setText(last_dir)
        self._edit_dir.setPlaceholderText("选择导出目录...")
        dir_layout.addWidget(self._edit_dir, 1)

        btn_browse = QPushButton("浏览")
        btn_browse.setProperty("secondary", "true")
        btn_browse.setFixedWidth(60)
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(btn_browse)

        layout.addWidget(dir_group)

        # 格式 + 质量
        fmt_group = QWidget()
        fmt_layout = QFormLayout(fmt_group)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        fmt_layout.setSpacing(8)

        lbl_fmt = QLabel("格式")
        self._combo_format = QComboBox()
        self._combo_format.addItems(["JPEG", "PNG", "TIFF"])
        self._combo_format.setCurrentIndex(0)
        self._combo_format.currentIndexChanged.connect(self._on_format_changed)
        fmt_layout.addRow(lbl_fmt, self._combo_format)

        # JPEG 质量
        self._quality_widget = QWidget()
        quality_layout = QHBoxLayout(self._quality_widget)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)

        self._slider_quality = QSlider(Qt.Orientation.Horizontal)
        self._slider_quality.setRange(1, 100)
        self._slider_quality.setValue(95)
        self._slider_quality.valueChanged.connect(self._on_quality_changed)
        quality_layout.addWidget(self._slider_quality, 1)

        self._lbl_quality = QLabel("95")
        self._lbl_quality.setFixedWidth(28)
        self._lbl_quality.setAlignment(Qt.AlignmentFlag.AlignRight)
        quality_layout.addWidget(self._lbl_quality)

        lbl_quality = QLabel("质量")
        fmt_layout.addRow(lbl_quality, self._quality_widget)
        # JPEG 默认选中，质量 slider 初始可见
        self._quality_widget.setVisible(True)

        layout.addWidget(fmt_group)

        # 尺寸限制
        size_group = QGroupBox("尺寸限制 (0 = 不限制)")
        size_layout = QFormLayout(size_group)
        size_layout.setSpacing(6)

        self._spin_max_w = QSpinBox()
        self._spin_max_w.setRange(0, 10000)
        self._spin_max_w.setSuffix(" px")
        size_layout.addRow("最大宽度", self._spin_max_w)

        self._spin_max_h = QSpinBox()
        self._spin_max_h.setRange(0, 10000)
        self._spin_max_h.setSuffix(" px")
        size_layout.addRow("最大高度", self._spin_max_h)

        layout.addWidget(size_group)

        # 处理选项
        opt_group = QWidget()
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(0, 0, 0, 0)
        opt_layout.setSpacing(6)

        self._chk_auto_rotate = QCheckBox("自动旋转")
        self._chk_auto_rotate.setChecked(True)
        opt_layout.addWidget(self._chk_auto_rotate)

        self._chk_trim_white = QCheckBox("去白边")
        self._chk_trim_white.setChecked(True)
        opt_layout.addWidget(self._chk_trim_white)

        layout.addWidget(opt_group)

        # 文件名模板
        tpl_group = QWidget()
        tpl_layout = QHBoxLayout(tpl_group)
        tpl_layout.setContentsMargins(0, 0, 0, 0)
        tpl_layout.setSpacing(8)

        lbl_tpl = QLabel("文件名")
        lbl_tpl.setFixedWidth(60)
        tpl_layout.addWidget(lbl_tpl)

        self._edit_template = QLineEdit("{name}_p{page}_{index:02d}.{ext}")
        self._edit_template.setToolTip("可用变量: {name} {page} {index:02d} {ext}")
        tpl_layout.addWidget(self._edit_template, 1)

        layout.addWidget(tpl_group)

        # 分隔
        layout.addSpacing(8)

        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # 当前页导出按钮（次要描边样式）
        self._btn_export_page = QPushButton(f"导出当前页 ({self._current_page_crops})")
        self._btn_export_page.setProperty("secondary", "true")
        self._btn_export_page.clicked.connect(lambda: self._on_export("page"))
        btn_layout.addWidget(self._btn_export_page)

        # 全部导出按钮（主按钮黑底样式，继承全局 QPushButton）
        self._btn_export_all = QPushButton(f"导出全部 ({self._total_crops})")
        self._btn_export_all.clicked.connect(lambda: self._on_export("all"))
        btn_layout.addWidget(self._btn_export_all)

        layout.addLayout(btn_layout)

    def _browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if directory:
            self._edit_dir.setText(directory)
            self._settings.setValue("export/last_dir", directory)

    def _on_format_changed(self, index: int) -> None:
        # JPEG 才显示质量滑块
        self._quality_widget.setVisible(index == 0)

    def _on_quality_changed(self, value: int) -> None:
        self._lbl_quality.setText(str(value))

    def _on_export(self, scope: str) -> None:
        """导出按钮点击"""
        self._export_scope = scope
        self.accept()

    def get_export_config(self) -> dict:
        """返回用户选择的导出配置"""
        format_map = {0: ".jpg", 1: ".png", 2: ".tif"}
        fmt_index = self._combo_format.currentIndex()

        return {
            "output_dir": Path(self._edit_dir.text()) if self._edit_dir.text() else None,
            "suffix": format_map.get(fmt_index, ".jpg"),
            "quality": self._slider_quality.value(),
            "max_width": self._spin_max_w.value(),
            "max_height": self._spin_max_h.value(),
            "auto_rotate": self._chk_auto_rotate.isChecked(),
            "trim_white": self._chk_trim_white.isChecked(),
            "template": self._edit_template.text(),
            "scope": self._export_scope,
        }
