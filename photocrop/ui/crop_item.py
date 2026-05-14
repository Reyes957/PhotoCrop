"""
CropItem — 可交互裁剪框 QGraphicsItem

规范（project_rules.md §7）：
    支持：拖动、缩放、旋转、删除、新建
    不支持：撤销、多选、自动吸附

Apple 设计风格：
    - Apple Blue (#0071e3) 选中状态
    - 柔和阴影而非硬边框
    - 精致的手柄设计
"""

from __future__ import annotations

import math
import re
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
)

from photocrop.ui.icons import get_icon
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.rotation import normalize_angle

# ============================================================
# 主题颜色（模块级 fallback，CropItem 类属性覆盖）
# ============================================================

def set_theme_colors(colors) -> None:
    """更新 CropItem 类属性颜色（主题切换时调用）"""
    CropItem._t_accent = QColor(colors.accent)
    CropItem._t_accent_hover = QColor(colors.accent_hover)
    fill = QColor(colors.accent)
    fill.setAlpha(10)
    CropItem._t_accent_fill = fill
    CropItem._t_canvas_bg = QColor(colors.canvas_bg)
    CropItem._t_dashed = QColor(102, 102, 102) if colors.accent == "#000000" else QColor(110, 110, 110)
    CropItem._t_toolbar_bg = _parse_rgba(colors.toolbar_float)


def _parse_rgba(rgba_str: str) -> QColor:
    """解析 'rgba(r, g, b, a)' 字符串为 QColor"""
    m = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)', rgba_str)
    if m:
        r, g, b, a = int(m[1]), int(m[2]), int(m[3]), float(m[4])
        return QColor(r, g, b, int(a * 255))
    return QColor(0, 0, 0, 160)

# 手柄尺寸
HANDLE_SIZE = 8
HANDLE_HOVER_SIZE = 10
ROTATION_HANDLE_OFFSET = 32   # 旋转手柄在裁剪框上方 32px（设计规范）
ROTATION_HANDLE_SIZE = 12     # 旋转手柄 12×12px（设计规范）
ROTATION_LINE_WIDTH = 1.0

# 框线样式
PEN_WIDTH_SELECTED = 2.5
PEN_WIDTH_INACTIVE = 2.0
PEN_DASH_PATTERN = [6, 4]


# ============================================================
# 手柄位置
# ============================================================

class HandlePosition:
    NONE = "none"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    ROTATION = "rotation"
    BODY = "body"


# ============================================================
# CropItem
# ============================================================

class CropItem(QGraphicsRectItem):
    """可交互裁剪框 — Apple 设计风格"""

    # 主题颜色（类属性，由 set_theme_colors() 更新）
    _t_accent = QColor("#000000")
    _t_accent_hover = QColor("#333333")
    _t_accent_fill = QColor(0, 0, 0, 10)
    _t_canvas_bg = QColor("#E8E8E8")
    _t_dashed = QColor(102, 102, 102)
    _t_toolbar_bg = QColor(0, 0, 0, 200)

    def __init__(self, crop_rect: CropRect, parent: QGraphicsItem | None = None):
        super().__init__(parent)

        self._crop_rect = crop_rect
        self._drag_handle = HandlePosition.NONE
        self._drag_start = QPointF()
        self._drag_rect = QRectF()
        self._hovered_handle = HandlePosition.NONE
        self._is_toolbar_hovered = False
        self._is_item_hovered = False  # 整体 hover 状态（用于工具栏显示）
        self._glow_alpha = 0  # 选中发光动画 alpha（0-80）

        # 宽高比锁定（None = Free，-1 = Original，>0 = 固定比值）
        self.aspect_ratio_lock: float | None = None

        # 回调函数（替代 Signal）
        self._on_changed: Callable | None = None
        self._on_deleted: Callable | None = None
        self._on_view_single: Callable | None = None  # 切换到 Single View
        self._on_copy: Callable | None = None          # 复制此框
        self._on_rotate_left: Callable | None = None   # 逆时针 90°
        self._on_rotate_right: Callable | None = None  # 顺时针 90°
        self._on_rotating: Callable | None = None      # 旋转中实时回调（轻量）

        # 交互设置
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # 从 CropRect 同步位置
        self._sync_from_rect()

    def set_callbacks(self, on_changed: Callable, on_deleted: Callable,
                      on_view_single: Callable | None = None,
                      on_copy: Callable | None = None,
                      on_rotate_left: Callable | None = None,
                      on_rotate_right: Callable | None = None,
                      on_rotating: Callable | None = None) -> None:
        """设置回调函数"""
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self._on_view_single = on_view_single
        self._on_copy = on_copy
        self._on_rotate_left = on_rotate_left
        self._on_rotate_right = on_rotate_right
        self._on_rotating = on_rotating

    def boundingRect(self) -> QRectF:
        """扩展边界以包含旋转手柄（上方）和工具栏（右上方），确保鼠标事件可达"""
        r = super().boundingRect()
        # 上方：旋转手柄(-28) + 手柄半径(4) + 间距(6) = -38
        # 右方：工具栏 (5×30 + 4×4 + 10 padding) ≈ 186px
        return r.adjusted(-6, -48, 190, 6)

    def shape(self) -> QPainterPath:
        """精确碰撞检测：裁剪框 + 旋转手柄 + 工具栏"""
        path = QPainterPath()
        # 裁剪框本体
        path.addRect(self.rect())
        # 旋转手柄区域
        rot_pos = QPointF(
            self.rect().center().x(),
            self.rect().top() - ROTATION_HANDLE_OFFSET,
        )
        path.addEllipse(rot_pos, 12, 12)
        # 工具栏区域
        path.addRect(self._toolbar_bg_rect(self.rect()))
        return path

    @property
    def crop_rect(self) -> CropRect:
        return self._crop_rect

    def _sync_from_rect(self):
        r = self._crop_rect
        self.setRect(QRectF(
            r.x - r.width / 2,
            r.y - r.height / 2,
            r.width,
            r.height,
        ))

    def _sync_to_rect(self):
        rect = self.rect()
        self._crop_rect.x = rect.center().x()
        self._crop_rect.y = rect.center().y()
        self._crop_rect.width = rect.width()
        self._crop_rect.height = rect.height()

    # ---- 绘制 ----

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.rect()
        if rect.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_selected = self.isSelected()

        # 应用旋转变换（围绕裁剪框中心）
        painter.save()
        angle = self._crop_rect.rotation_angle
        if angle != 0:
            center = rect.center()
            painter.translate(center)
            painter.rotate(-angle)
            painter.translate(-center)

        # 选中发光效果（设计规范：box-shadow 0→3px→0px, 300ms）
        if is_selected and self._glow_alpha > 0:
            glow_color = QColor(self._t_accent)
            glow_color.setAlpha(self._glow_alpha)
            pen = QPen(glow_color, 6.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # 半透明填充（选中时）
        if is_selected:
            painter.setBrush(QBrush(self._t_accent_fill))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 外框
        if is_selected:
            pen = QPen(self._t_accent, PEN_WIDTH_SELECTED)
        else:
            pen = QPen(self._t_dashed, PEN_WIDTH_INACTIVE, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(PEN_DASH_PATTERN)
        painter.setPen(pen)
        painter.drawRect(rect)

        # 选中时绘制手柄
        if is_selected:
            self._paint_handles(painter, rect)
            # 工具栏：仅在 hover 选中框时显示（设计规范）
            if self._is_item_hovered or self._is_toolbar_hovered:
                self._paint_toolbar(painter, rect)

        # 拖动时显示尺寸信息
        if self._drag_handle not in (HandlePosition.NONE, HandlePosition.BODY,
                                     HandlePosition.ROTATION):
            self._paint_size_label(painter, rect)

        painter.restore()

    def _paint_handles(self, painter: QPainter, rect: QRectF) -> None:
        hs = HANDLE_SIZE
        hhs = HANDLE_HOVER_SIZE

        # 统一使用 8×8 方块（参考设计规范）
        all_handles = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
            (QPointF(rect.center().x(), rect.top()), HandlePosition.TOP),
            (QPointF(rect.center().x(), rect.bottom()), HandlePosition.BOTTOM),
            (QPointF(rect.left(), rect.center().y()), HandlePosition.LEFT),
            (QPointF(rect.right(), rect.center().y()), HandlePosition.RIGHT),
        ]
        for pos, handle in all_handles:
            size = hhs if self._hovered_handle == handle else hs
            half = size / 2
            painter.setPen(QPen(self._t_accent, 1.0))
            painter.setBrush(QBrush(self._t_canvas_bg))
            painter.drawRect(QRectF(pos.x() - half, pos.y() - half, size, size))

        # 旋转手柄 — 带连接线（设计规范：12×12px，虚线连接）
        rotation_pos = QPointF(
            rect.center().x(),
            rect.top() - ROTATION_HANDLE_OFFSET,
        )

        # 连接线：3px 实线 + 3px 间隙的虚线
        dash_pen = QPen(self._t_accent, ROTATION_LINE_WIDTH)
        dash_pen.setDashPattern([3, 3])
        painter.setPen(dash_pen)
        painter.drawLine(
            QPointF(rect.center().x(), rect.top()),
            rotation_pos,
        )

        # 旋转手柄方块（12×12px）
        rhs = ROTATION_HANDLE_SIZE
        rhh = rhs + 2 if self._hovered_handle == HandlePosition.ROTATION else rhs
        rh_half = rhh / 2
        painter.setPen(QPen(self._t_accent, 1.0))
        painter.setBrush(QBrush(self._t_canvas_bg))
        painter.drawRect(QRectF(rotation_pos.x() - rh_half, rotation_pos.y() - rh_half, rhh, rhh))

        # 显示当前旋转角度
        angle = self._crop_rect.rotation_angle
        if angle != 0.0:
            painter.setPen(QPen(self._t_accent, 1.0))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            angle_text = f"{angle:.0f}°"
            text_pos = QPointF(rotation_pos.x() + 12, rotation_pos.y() - 4)
            painter.drawText(text_pos, angle_text)

    # ---- 工具栏（右上角） ----

    TOOLBAR_BUTTON_SIZE = 28
    TOOLBAR_GAP = 4
    TOOLBAR_ICONS = ["eye", "x", "rotate-ccw", "rotate-cw", "copy"]  # view, delete, rotate CCW, rotate CW, copy
    TOOLBAR_ICON_COLOR = "#FFFFFF"  # 纯白，最大化对比度

    def _toolbar_bg_rect(self, rect: QRectF) -> QRectF:
        """工具栏背景矩形（裁剪框右上角外侧）"""
        n = len(self.TOOLBAR_ICONS)
        total_w = self.TOOLBAR_BUTTON_SIZE * n + self.TOOLBAR_GAP * (n - 1)
        btn_h = self.TOOLBAR_BUTTON_SIZE
        return QRectF(
            rect.right() + 8,                    # 裁剪框右侧 8px
            rect.top() - btn_h // 2 - 5,         # 垂直居中对齐顶边
            total_w + 10,                         # 宽度 + 内边距
            btn_h + 10,                           # 高度 + 内边距
        )

    def _toolbar_rects(self, rect: QRectF) -> list:
        """返回工具栏按钮的 QRectF（裁剪框右上角外侧）"""
        btn_w = self.TOOLBAR_BUTTON_SIZE
        n = len(self.TOOLBAR_ICONS)
        x_start = rect.right() + 13             # 背景左边距 5px + 8px 间距
        y = rect.top() - btn_w // 2             # 垂直居中对齐顶边

        rects = []
        for i in range(n):
            rx = x_start + i * (btn_w + self.TOOLBAR_GAP)
            rects.append(QRectF(rx, y, btn_w, btn_w))
        return rects

    def _paint_toolbar(self, painter: QPainter, rect: QRectF) -> None:
        """绘制裁剪框右上角的工具栏"""
        btn_rects = self._toolbar_rects(rect)

        # 背景
        bg_rect = self._toolbar_bg_rect(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._t_toolbar_bg))
        painter.drawRoundedRect(bg_rect, 6, 6)

        # 按钮
        for _i, (btn_rect, icon_name) in enumerate(zip(btn_rects, self.TOOLBAR_ICONS)):
            # 按钮 hover 高亮
            if btn_rect.contains(getattr(self, '_last_hover_pos', QPointF())):
                painter.setBrush(QBrush(QColor(255, 255, 255, 35)))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(btn_rect, 4, 4)

            # SVG 图标（5px padding → 20×20 可见区域）
            icon = get_icon(icon_name, self.TOOLBAR_ICON_COLOR)
            icon_rect = btn_rect.adjusted(5, 5, -5, -5)
            icon.paint(painter, icon_rect.toRect(), Qt.AlignmentFlag.AlignCenter)

    def _paint_size_label(self, painter: QPainter, rect: QRectF) -> None:
        """拖动缩放手柄时显示尺寸浮层"""
        w = int(rect.width())
        h = int(rect.height())
        text = f"{w} × {h}"

        font = painter.font()
        font.setPointSize(10)
        font.setWeight(font.Weight.Medium)
        painter.setFont(font)

        # 计算文本尺寸
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(text)
        tw = text_rect.width() + 12
        th = text_rect.height() + 6

        # 位置：裁剪框底部中央下方
        label_x = rect.center().x() - tw / 2
        label_y = rect.bottom() + 6
        label_rect = QRectF(label_x, label_y, tw, th)

        # 背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._t_toolbar_bg))
        painter.drawRoundedRect(label_rect, 4, 4)

        # 文字
        painter.setPen(QPen(QColor("#F0F0F0")))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _toolbar_button_at(self, pos: QPointF) -> int:
        """检测点击是否在工具栏按钮上，返回按钮索引（-1=无）"""
        if not self.isSelected():
            return -1
        rect = self.rect()
        btn_rects = self._toolbar_rects(rect)
        for i, btn_rect in enumerate(btn_rects):
            if btn_rect.contains(pos):
                return i
        return -1

    # ---- 手柄检测 ----

    def _handle_at(self, pos: QPointF) -> str:
        rect = self.rect()
        hs = HANDLE_SIZE * 1.5  # 检测区域略大

        # 旋转手柄（检测区域更大，方便点击）
        rotation_pos = QPointF(rect.center().x(), rect.top() - ROTATION_HANDLE_OFFSET)
        if (pos - rotation_pos).manhattanLength() < hs * 2:
            return HandlePosition.ROTATION

        # 四角
        corners = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
        ]
        for corner_pos, handle in corners:
            if (pos - corner_pos).manhattanLength() < hs:
                return handle

        # 四边
        edges = [
            (QPointF(rect.center().x(), rect.top()), HandlePosition.TOP),
            (QPointF(rect.center().x(), rect.bottom()), HandlePosition.BOTTOM),
            (QPointF(rect.left(), rect.center().y()), HandlePosition.LEFT),
            (QPointF(rect.right(), rect.center().y()), HandlePosition.RIGHT),
        ]
        for edge_pos, handle in edges:
            if (pos - edge_pos).manhattanLength() < hs:
                return handle

        if rect.contains(pos):
            return HandlePosition.BODY

        return HandlePosition.NONE

    # ---- 光标 ----

    def _update_cursor(self, handle: str) -> None:
        cursor_map = {
            HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.TOP: Qt.CursorShape.SizeVerCursor,
            HandlePosition.BOTTOM: Qt.CursorShape.SizeVerCursor,
            HandlePosition.LEFT: Qt.CursorShape.SizeHorCursor,
            HandlePosition.RIGHT: Qt.CursorShape.SizeHorCursor,
            HandlePosition.ROTATION: Qt.CursorShape.CrossCursor,
            HandlePosition.BODY: Qt.CursorShape.SizeAllCursor,
            HandlePosition.NONE: Qt.CursorShape.ArrowCursor,
        }
        self.setCursor(cursor_map.get(handle, Qt.CursorShape.ArrowCursor))

    # ---- 鼠标事件 ----

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        handle = self._handle_at(event.pos())
        if handle != self._hovered_handle:
            self._hovered_handle = handle
            self.update()
        self._last_hover_pos = event.pos()

        # 整体 hover 状态（用于工具栏显示）
        if not self._is_item_hovered:
            self._is_item_hovered = True
            if self.isSelected():
                self.update()

        # 检测工具栏 hover
        toolbar_idx = self._toolbar_button_at(event.pos())
        was_hovered = self._is_toolbar_hovered
        self._is_toolbar_hovered = toolbar_idx >= 0
        if was_hovered != self._is_toolbar_hovered:
            self.update()
        self._update_cursor(handle)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered_handle = HandlePosition.NONE
        self._is_toolbar_hovered = False
        self._is_item_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 先检查工具栏按钮（5 个：eye view / x delete / rotate-ccw / rotate-cw / copy）
            toolbar_idx = self._toolbar_button_at(event.pos())
            if toolbar_idx == 0 and self._on_view_single:
                self._on_view_single()
                event.accept()
                return
            elif toolbar_idx == 1 and self._on_deleted:
                self._on_deleted()
                if self.scene():
                    self.scene().removeItem(self)
                event.accept()
                return
            elif toolbar_idx == 2 and self._on_rotate_left:
                self._on_rotate_left()
                event.accept()
                return
            elif toolbar_idx == 3 and self._on_rotate_right:
                self._on_rotate_right()
                event.accept()
                return
            elif toolbar_idx == 4 and self._on_copy:
                self._on_copy()
                event.accept()
                return

            self._drag_handle = self._handle_at(event.pos())
            self._drag_start = event.pos()
            self._drag_rect = self.rect()
            self.setSelected(True)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_handle == HandlePosition.NONE:
            return

        delta = event.pos() - self._drag_start
        new_rect = QRectF(self._drag_rect)

        if self._drag_handle == HandlePosition.BODY:
            new_rect.translate(delta)
        elif self._drag_handle == HandlePosition.ROTATION:
            # 计算从矩形中心到鼠标位置的角度
            center = self.rect().center()
            mouse = event.pos()
            dx = mouse.x() - center.x()
            dy = mouse.y() - center.y()

            # atan2 返回弧度，转换为角度
            # Qt 坐标系 y 轴向下，atan2(-dy,dx) 得到标准数学角度
            angle_rad = math.atan2(-dy, dx)
            angle_deg = math.degrees(angle_rad)

            # 从 12 点钟方向顺时针：鼠标在正上方=0°，左侧=正值（逆时针）
            rotation = normalize_angle(angle_deg - 90.0)

            # 吸附到 0°, 90°, -90°, 180°（容差 ±15°）
            snap_angles = [0.0, 90.0, -90.0, 180.0]
            for snap in snap_angles:
                if abs(rotation - snap) < 15:
                    rotation = snap
                    break

            self._crop_rect.rotation_angle = rotation
            self.update()
            # 轻量实时回调（仅更新属性面板，不触发完整刷新）
            if self._on_rotating:
                self._on_rotating(rotation)
            event.accept()
            return
        else:
            if HandlePosition.LEFT in self._drag_handle:
                new_rect.setLeft(self._drag_rect.left() + delta.x())
            if HandlePosition.RIGHT in self._drag_handle:
                new_rect.setRight(self._drag_rect.right() + delta.x())
            if HandlePosition.TOP in self._drag_handle:
                new_rect.setTop(self._drag_rect.top() + delta.y())
            if HandlePosition.BOTTOM in self._drag_handle:
                new_rect.setBottom(self._drag_rect.bottom() + delta.y())

            # 最小尺寸
            min_size = 20
            if new_rect.width() < min_size:
                new_rect.setWidth(min_size)
            if new_rect.height() < min_size:
                new_rect.setHeight(min_size)

            # 宽高比锁定
            if self.aspect_ratio_lock is not None and self.aspect_ratio_lock > 0:
                ratio = self.aspect_ratio_lock
                # 根据拖动手柄类型决定以哪个维度为主
                if self._drag_handle in (
                    HandlePosition.LEFT, HandlePosition.RIGHT,
                    HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT,
                    HandlePosition.BOTTOM_LEFT, HandlePosition.BOTTOM_RIGHT,
                ):
                    # 以宽度为主，计算高度
                    new_h = new_rect.width() / ratio
                    if new_h >= min_size:
                        new_rect.setHeight(new_h)
                else:
                    # 以高度为主，计算宽度
                    new_w = new_rect.height() * ratio
                    if new_w >= min_size:
                        new_rect.setWidth(new_w)

        self.setRect(new_rect)
        self._sync_to_rect()
        self.update()  # 视觉重绘，_on_changed 延迟到 release 时触发
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # 拖动结束，一次性触发变更回调（避免拖动期间信号风暴）
        if self._drag_handle != HandlePosition.NONE and self._on_changed:
            self._on_changed()
        self._drag_handle = HandlePosition.NONE
        self.update()  # 确保最终状态重绘（工具栏、手柄等）
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._on_deleted:
                self._on_deleted()
            if self.scene():
                self.scene().removeItem(self)
            event.accept()
        else:
            super().keyPressEvent(event)

    def itemChange(self, change, value):
        """选中状态变化时触发发光动画"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self._start_glow()
        return super().itemChange(change, value)

    def _start_glow(self) -> None:
        """启动选中发光动画（300ms: 0→80→0）"""
        self._glow_alpha = 80
        self.update()
        # 150ms 后淡出
        QTimer.singleShot(150, self._fade_glow)

    def _fade_glow(self) -> None:
        """发光淡出"""
        if self._glow_alpha > 0:
            self._glow_alpha = max(0, self._glow_alpha - 40)
            self.update()
            if self._glow_alpha > 0:
                QTimer.singleShot(30, self._fade_glow)
