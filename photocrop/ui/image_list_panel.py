"""
ImageListPanel — 左侧图像列表面板

对标 AutoCropper 左侧 IMAGES 面板。
深色背景，缩略图 + 文件名 + 裁剪框数量。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
    QMenu,
)

# ============================================================
# 样式常量
# ============================================================

PANEL_BG = "#2c2c2e"
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#86868b"
SELECTED_BORDER = "#0071e3"
FONT_FAMILY = "SF Pro Text, SF Pro Icons, Helvetica Neue, Helvetica, Arial, sans-serif"


class ImageListPanel(QWidget):
    """左侧图像列表面板

    Signals:
        image_selected: 选中图像时发出，参数为图像路径字符串（dict key）
        re_detect_requested: 右键菜单请求重新检测
        remove_requested: 右键菜单请求从列表移除
    """

    image_selected = Signal(str)
    re_detect_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedWidth(220)

        # 独立样式表，不与全局 STYLE_SHEET 冲突
        self.setStyleSheet(f"""
            ImageListPanel {{
                background-color: {PANEL_BG};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        header = QLabel("  IMAGES")
        header.setFixedHeight(32)
        header.setStyleSheet(f"""
            background-color: {PANEL_BG};
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            padding-left: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        """)
        layout.addWidget(header)

        # 列表
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {PANEL_BG};
                border: none;
                outline: none;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                color: {TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-left: 3px solid transparent;
                min-height: 50px;
            }}
            QListWidget::item:selected {{
                background-color: rgba(0, 113, 227, 0.15);
                border-left: 3px solid {SELECTED_BORDER};
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, 1)

        # 底部统计
        self._lbl_total = QLabel("  0 images, 0 crops")
        self._lbl_total.setFixedHeight(28)
        self._lbl_total.setStyleSheet(f"""
            background-color: {PANEL_BG};
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            padding-left: 10px;
            border-top: 1px solid rgba(255,255,255,0.08);
        """)
        layout.addWidget(self._lbl_total)

        # 存储 path key 到 row 的映射
        self._path_keys: list[str] = []
        self._block_signal = False

    def add_image(self, key: str, filename: str, thumbnail: Image.Image,
                  crop_count: int = 0) -> None:
        """添加一张图片到列表

        Args:
            key: 图片路径字符串（用作 dict key）
            filename: 显示的文件名
            thumbnail: 缩略图 PIL Image
            crop_count: 当前裁剪框数量
        """
        self._path_keys.append(key)

        # 创建自定义 widget
        item_widget = QWidget()
        item_widget.setFixedHeight(56)
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 4, 4, 4)
        item_layout.setSpacing(2)

        # 上行: 缩略图 + 文件名
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # 缩略图
        thumb_label = QLabel()
        thumb_label.setFixedSize(44, 44)
        thumb_label.setStyleSheet("border-radius: 4px; background: #3a3a3c;")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._pil_to_pixmap(thumbnail).scaled(
            44, 44, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        thumb_label.setPixmap(pixmap)
        top_row.addWidget(thumb_label)

        # 文件名
        name_label = QLabel(filename)
        name_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 12px;
            font-weight: 500;
        """)
        name_label.setWordWrap(True)
        top_row.addWidget(name_label, 1)

        item_layout.addLayout(top_row)

        # 下行: 裁剪框数量
        count_label = QLabel(f"{crop_count} crops")
        count_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-family: {FONT_FAMILY};
            font-size: 10px;
            padding-left: 52px;
        """)
        count_label.setObjectName("count_label")
        item_layout.addWidget(count_label)

        item = QListWidgetItem()
        item.setSizeHint(QSize(200, 56))
        self._list.addItem(item)
        self._list.setItemWidget(item, item_widget)

    def update_crop_count(self, key: str, count: int) -> None:
        """更新指定图像的裁剪框数量"""
        try:
            idx = self._path_keys.index(key)
        except ValueError:
            return
        item = self._list.item(idx)
        if item is None:
            return
        widget = self._list.itemWidget(item)
        if widget is None:
            return
        count_label = widget.findChild(QLabel, "count_label")
        if count_label:
            count_label.setText(f"{count} crops")

    def update_total(self, image_count: int, crop_count: int) -> None:
        """更新底部统计"""
        self._lbl_total.setText(f"  {image_count} images, {crop_count} crops")

    def remove_image(self, key: str) -> None:
        """从列表移除一张图片"""
        try:
            idx = self._path_keys.index(key)
        except ValueError:
            return
        self._path_keys.pop(idx)
        self._list.takeItem(idx)

    def select_image(self, key: str) -> None:
        """程序化选中一张图片"""
        try:
            idx = self._path_keys.index(key)
        except ValueError:
            return
        self._block_signal = True
        self._list.setCurrentRow(idx)
        self._block_signal = False

    def clear(self) -> None:
        """清空列表"""
        self._path_keys.clear()
        self._list.clear()

    def _on_row_changed(self, row: int) -> None:
        if self._block_signal:
            return
        if 0 <= row < len(self._path_keys):
            self.image_selected.emit(self._path_keys[row])

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        row = self._list.row(item)
        if row < 0 or row >= len(self._path_keys):
            return
        key = self._path_keys[row]

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {PANEL_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 4px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: rgba(0, 113, 227, 0.3);
            }}
        """)
        action_detect = menu.addAction("重新检测")
        action_remove = menu.addAction("从列表移除")

        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == action_detect:
            self.re_detect_requested.emit(key)
        elif chosen == action_remove:
            self.remove_requested.emit(key)

    @staticmethod
    def _pil_to_pixmap(img: Image.Image) -> QPixmap:
        """PIL Image → QPixmap"""
        if img.mode == "RGBA":
            img = img.convert("RGBA")
            data = img.tobytes("raw", "RGBA")
            bpl = img.width * 4
            qimage = QImage(data, img.width, img.height, bpl, QImage.Format.Format_RGBA8888)
        else:
            img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            bpl = img.width * 3
            qimage = QImage(data, img.width, img.height, bpl, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimage.copy())
