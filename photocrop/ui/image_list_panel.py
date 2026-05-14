"""
ImageListPanel — 左侧图像列表面板

对标 AutoCropper 左侧 IMAGES 面板。
深色背景，缩略图 + 文件名 + 裁剪框数量。

支持 PDF 多页展开：父项 + N 个带缩略图的子项。
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

# ============================================================
# 默认样式常量（初始化时使用，set_theme 后会被覆盖）
# ============================================================
from photocrop.ui.theme import FONT_FAMILY, FontSize, FontWeight
from photocrop.ui.utils import pil_to_pixmap


@dataclass
class _PanelColors:
    """面板内部颜色（从 ThemeColors 提取，方便各方法使用）"""
    bg: str = "#F5F5F5"
    text: str = "#1A1A1A"
    text_secondary: str = "#666666"
    accent: str = "#000000"
    border: str = "#E0E0E0"
    selected_bg: str = "rgba(0, 0, 0, 0.08)"
    hover_bg: str = "rgba(0, 0, 0, 0.03)"
    thumb_bg: str = "#E0E0E0"
    danger: str = "#CC0000"


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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self._colors = _PanelColors()

        self._build_ui()
        self._apply_styles()

        # 存储 path key 到 row 的映射
        self._path_keys: list[str] = []
        self._block_signal = False

    def _build_ui(self) -> None:
        """构建 UI 结构（不设置颜色样式）"""
        self.setStyleSheet(f"ImageListPanel {{ background-color: {self._colors.bg}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        self._header = QLabel("IMAGES")
        self._header.setStyleSheet("padding-left: 10px;")
        self._header.setFixedHeight(32)
        layout.addWidget(self._header)

        # 列表
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, 1)

        # 底部统计
        self._lbl_total = QLabel("0 images, 0 crops")
        self._lbl_total.setFixedHeight(28)
        layout.addWidget(self._lbl_total)

    def _apply_styles(self) -> None:
        """根据当前 _colors 应用所有样式（初始化和主题切换时调用）"""
        c = self._colors
        self.setStyleSheet(f"ImageListPanel {{ background-color: {c.bg}; }}")
        self._header.setStyleSheet(f"""
            background-color: {c.bg};
            color: {c.text_secondary};
            font-family: {FONT_FAMILY};
            font-size: {FontSize.LABEL}px;
            font-weight: {FontWeight.SEMIBOLD};
            letter-spacing: 0.15em;
            padding-left: 12px;
            border-bottom: 1px solid {c.border};
        """)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {c.bg};
                border: none;
                outline: none;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                color: {c.text};
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-left: 3px solid transparent;
                min-height: 44px;
            }}
            QListWidget::item:selected {{
                background-color: {c.selected_bg};
                border-left: 3px solid {c.accent};
                color: {c.text};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {c.hover_bg};
            }}
        """)
        self._lbl_total.setStyleSheet(f"""
            background-color: {c.bg};
            color: {c.text_secondary};
            font-family: {FONT_FAMILY};
            font-size: 11px;
            padding-left: 10px;
            border-top: 1px solid {c.border};
        """)
        # 更新所有已有列表项的子控件颜色
        self._refresh_item_colors()

    # ---- 公共 API ----

    def add_image(self, key: str, filename: str, thumbnail: Image.Image,
                  crop_count: int = 0, page_count: int = 1,
                  page_thumbnails: list[Image.Image] | None = None) -> None:
        """添加一张图片到列表

        Args:
            key: 图片路径字符串（用作 dict key）
            filename: 显示的文件名
            thumbnail: 缩略图 PIL Image
            crop_count: 当前裁剪框数量（单图用）
            page_count: PDF 页数（>1 时展开为父项+子项）
            page_thumbnails: 每页的缩略图列表（PDF 用）
        """
        if page_count > 1:
            self._add_pdf_parent(key, filename, page_count, thumbnail, page_thumbnails)
        else:
            self._add_single_item(key, filename, thumbnail, crop_count)

    def update_crop_count(self, key: str, count: int) -> None:
        """更新指定图像的裁剪框数量（支持单图和 PDF 页面 key）"""
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
        self._lbl_total.setText(f"{image_count} images, {crop_count} crops")

    def remove_image(self, key: str) -> None:
        """从列表移除一张图片（单图或 PDF 父项+子项）"""
        try:
            idx = self._path_keys.index(key)
        except ValueError:
            return

        # 检查是否是 PDF 父项，如果是则同时移除所有子项
        item = self._list.item(idx)
        if item is not None:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "pdf_parent":
                pdf_key = data["key"]
                # 收集要移除的子项 key
                child_keys = [k for k in self._path_keys
                              if k.startswith(f"{pdf_key}##PAGE##")]
                # 先移除子项（从后往前）
                for ck in reversed(child_keys):
                    ci = self._path_keys.index(ck)
                    self._path_keys.pop(ci)
                    self._list.takeItem(ci)
                # 再移除父项
                idx = self._path_keys.index(key)

        self._path_keys.pop(idx)
        self._list.takeItem(idx)

    def select_image(self, key: str) -> None:
        """程序化选中一张图片（支持 page key）"""
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

    def set_theme(self, colors) -> None:
        """更新面板颜色（主题切换时调用）"""
        self._colors = _PanelColors(
            bg=colors.bg,
            text=colors.text,
            text_secondary=colors.text_secondary,
            accent=colors.accent,
            border=colors.border,
            selected_bg=colors.selected_bg,
            hover_bg=colors.hover_bg,
            thumb_bg=colors.border if colors.accent == "#000000" else "#3A3A3A",
            danger=colors.danger,
        )
        self._apply_styles()

    def _refresh_item_colors(self) -> None:
        """更新所有列表项内部控件的颜色（主题切换 + 新项创建后调用）"""
        c = self._colors
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            widget = self._list.itemWidget(item)
            if widget is None:
                continue
            for lbl in widget.findChildren(QLabel):
                obj_name = lbl.objectName()
                if obj_name == "count_label":
                    lbl.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 10px;")
                elif obj_name == "thumb_label":
                    lbl.setStyleSheet(f"border-radius: 4px; background: {c.thumb_bg};")
                else:
                    lbl.setStyleSheet(f"color: {c.text}; font-family: {FONT_FAMILY}; font-size: 12px;")
            # 刷新 PDF 页面子项的左边框指示线颜色
            if widget.objectName() == "pdf_page_widget":
                widget.setStyleSheet(f"#pdf_page_widget {{ border-left: 2px solid {c.border}; }}")

    # ---- 单图项 ----

    def _add_single_item(self, key: str, filename: str,
                         thumbnail: Image.Image, crop_count: int) -> None:
        """添加单图项"""
        c = self._colors
        self._path_keys.append(key)

        item_widget = QWidget()
        item_widget.setFixedHeight(48)
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 4, 4, 4)
        item_layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        thumb_label = QLabel()
        thumb_label.setFixedSize(44, 44)
        thumb_label.setObjectName("thumb_label")
        thumb_label.setStyleSheet(f"border-radius: 4px; background: {c.thumb_bg};")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = pil_to_pixmap(thumbnail).scaled(
            44, 44, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        thumb_label.setPixmap(pixmap)
        top_row.addWidget(thumb_label)

        name_label = QLabel(filename)
        name_label.setStyleSheet(f"color: {c.text}; font-family: {FONT_FAMILY}; font-size: 12px; font-weight: 500;")
        name_label.setWordWrap(True)
        top_row.addWidget(name_label, 1)

        item_layout.addLayout(top_row)

        count_label = QLabel(f"{crop_count} crops")
        count_label.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 10px; padding-left: 52px;")
        count_label.setObjectName("count_label")
        item_layout.addWidget(count_label)

        item = QListWidgetItem()
        item.setSizeHint(QSize(200, 48))
        self._list.addItem(item)
        self._list.setItemWidget(item, item_widget)

    # ---- PDF 父项 + 子项 ----

    def _add_pdf_parent(self, pdf_key: str, filename: str, page_count: int,
                        first_thumb: Image.Image,
                        page_thumbs: list[Image.Image] | None) -> None:
        """添加 PDF 父项 + N 个页面子项"""
        # 父项
        self._path_keys.append(pdf_key)
        parent_widget = self._create_pdf_parent_widget(filename, page_count, first_thumb)
        parent_item = QListWidgetItem()
        parent_item.setSizeHint(QSize(200, 40))
        parent_item.setData(Qt.ItemDataRole.UserRole, {"type": "pdf_parent", "key": pdf_key})
        self._list.addItem(parent_item)
        self._list.setItemWidget(parent_item, parent_widget)

        # 子项
        for idx in range(page_count):
            page_key = f"{pdf_key}##PAGE##{idx}"
            self._path_keys.append(page_key)
            thumb = page_thumbs[idx] if page_thumbs and idx < len(page_thumbs) else None
            page_widget = self._create_page_widget(idx, 0, thumb)
            page_item = QListWidgetItem()
            page_item.setSizeHint(QSize(200, 50))
            page_item.setData(Qt.ItemDataRole.UserRole, {
                "type": "pdf_page", "key": page_key,
                "pdf_key": pdf_key, "page_idx": idx,
            })
            self._list.addItem(page_item)
            self._list.setItemWidget(page_item, page_widget)

    def _create_pdf_parent_widget(self, filename: str, page_count: int,
                                  first_thumb: Image.Image) -> QWidget:
        """创建 PDF 父项 widget：文件名 + 页数"""
        c = self._colors
        widget = QWidget()
        widget.setFixedHeight(36)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 8, 4)
        layout.setSpacing(8)

        thumb_label = QLabel()
        thumb_label.setFixedSize(28, 28)
        thumb_label.setObjectName("thumb_label")
        thumb_label.setStyleSheet(f"border-radius: 3px; background: {c.thumb_bg};")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = pil_to_pixmap(first_thumb).scaled(
            28, 28, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        thumb_label.setPixmap(pixmap)
        layout.addWidget(thumb_label)

        name_label = QLabel(f"{filename}  ({page_count} pages)")
        name_label.setStyleSheet(f"color: {c.text}; font-family: {FONT_FAMILY}; font-size: 11px; font-weight: 600;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label, 1)

        return widget

    def _create_page_widget(self, page_idx: int, crop_count: int,
                            thumbnail: Image.Image | None = None) -> QWidget:
        """创建 PDF 页面子项 widget：缩略图 + Page N - X crops"""
        c = self._colors
        widget = QWidget()
        widget.setObjectName("pdf_page_widget")
        widget.setFixedHeight(46)
        widget.setStyleSheet(f"#pdf_page_widget {{ border-left: 2px solid {c.border}; }}")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(16, 4, 8, 4)
        layout.setSpacing(8)

        thumb_label = QLabel()
        thumb_label.setFixedSize(36, 36)
        thumb_label.setObjectName("thumb_label")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if thumbnail is not None:
            thumb_label.setStyleSheet(f"border-radius: 3px; background: {c.thumb_bg};")
            pixmap = pil_to_pixmap(thumbnail).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_label.setPixmap(pixmap)
        else:
            thumb_label.setText(f"P{page_idx + 1}")
            thumb_label.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 10px; border-radius: 3px; background: {c.thumb_bg};")
        layout.addWidget(thumb_label)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        page_label = QLabel(f"Page {page_idx + 1}")
        page_label.setStyleSheet(f"color: {c.text}; font-family: {FONT_FAMILY}; font-size: 11px; font-weight: 500;")
        text_col.addWidget(page_label)

        count_label = QLabel(f"{crop_count} crops")
        count_label.setStyleSheet(f"color: {c.text_secondary}; font-family: {FONT_FAMILY}; font-size: 10px;")
        count_label.setObjectName("count_label")
        text_col.addWidget(count_label)

        layout.addLayout(text_col, 1)

        return widget

    # ---- 事件处理 ----

    def _on_row_changed(self, row: int) -> None:
        if self._block_signal or row < 0 or row >= len(self._path_keys):
            return

        item = self._list.item(row)
        if item is None:
            return

        data = item.data(Qt.ItemDataRole.UserRole)

        # PDF 父项点击 → 自动选中第一个子页
        if isinstance(data, dict) and data.get("type") == "pdf_parent":
            pdf_key = data["key"]
            for i in range(row + 1, len(self._path_keys)):
                d_item = self._list.item(i)
                if d_item is None:
                    continue
                d = d_item.data(Qt.ItemDataRole.UserRole)
                if (isinstance(d, dict) and d.get("type") == "pdf_page"
                        and d.get("pdf_key") == pdf_key):
                    self._block_signal = True
                    self._list.setCurrentRow(i)
                    self._block_signal = False
                    # 仍然发射信号让主窗口加载第一页
                    self.image_selected.emit(self._path_keys[i])
                    return
            return

        self.image_selected.emit(self._path_keys[row])

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        row = self._list.row(item)
        if row < 0 or row >= len(self._path_keys):
            return
        key = self._path_keys[row]

        # 获取实际的 session key（PDF 页面 key 需要提取父 key）
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if isinstance(data, dict) and data.get("type") == "pdf_page":
            session_key = data.get("pdf_key", key)
        elif isinstance(data, dict) and data.get("type") == "pdf_parent":
            session_key = data.get("key", key)
        else:
            session_key = key

        c = self._colors
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {c.bg};
                color: {c.text};
                border: 1px solid {c.border};
                border-radius: 8px;
                padding: 4px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
                min-height: 28px;
            }}
            QMenu::item:selected {{
                background-color: {c.hover_bg};
            }}
        """)
        from photocrop.ui.icons import get_icon
        action_detect = menu.addAction(get_icon("refresh-cw", c.text_secondary), "Re-detect")
        action_remove = menu.addAction(get_icon("trash", c.danger), "Remove")

        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == action_detect:
            self.re_detect_requested.emit(session_key)
        elif chosen == action_remove:
            self.remove_requested.emit(session_key)
