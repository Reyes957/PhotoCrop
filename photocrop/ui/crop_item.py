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
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
)

from photocrop.utils.crop_rect import CropRect
from photocrop.utils.rotation import normalize_angle

# ============================================================
# Apple 设计常量
# ============================================================

# 主色调 — 黑白极简（默认 Light）
_ACCENT = QColor("#000000")
_ACCENT_HOVER = QColor("#333333")
_ACCENT_FILL = QColor(0, 0, 0, 10)   # 选中填充 (4% opacity)
_CANVAS_BG = QColor("#E8E8E8")
_WHITE = QColor("#ffffff")
_DASHED = QColor(102, 102, 102)       # 未选中虚线


def set_theme_colors(colors) -> None:
    """更新 CropItem 绘制使用的颜色（主题切换时调用）"""
    global _ACCENT, _ACCENT_HOVER, _ACCENT_FILL, _CANVAS_BG, _WHITE, _DASHED
    _ACCENT = QColor(colors.accent)
    _ACCENT_HOVER = QColor(colors.accent_hover)
    _ACCENT_FILL = QColor(colors.accent)
    _ACCENT_FILL.setAlpha(10)
    _CANVAS_BG = QColor(colors.canvas_bg)
    _WHITE = QColor(colors.surface)
    _DASHED = QColor(102, 102, 102) if colors.accent == "#000000" else QColor(85, 85, 85)

# 手柄尺寸
HANDLE_SIZE = 8
HANDLE_HOVER_SIZE = 10
ROTATION_HANDLE_OFFSET = 28
ROTATION_LINE_WIDTH = 1.0

# 框线样式
PEN_WIDTH_SELECTED = 2.0
PEN_WIDTH_INACTIVE = 1.5
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

    def __init__(self, crop_rect: CropRect, parent: QGraphicsItem | None = None):
        super().__init__(parent)

        self._crop_rect = crop_rect
        self._drag_handle = HandlePosition.NONE
        self._drag_start = QPointF()
        self._drag_rect = QRectF()
        self._hovered_handle = HandlePosition.NONE
        self._is_toolbar_hovered = False

        # 宽高比锁定（None = Free，-1 = Original，>0 = 固定比值）
        self.aspect_ratio_lock: float | None = None

        # 回调函数（替代 Signal）
        self._on_changed: Callable | None = None
        self._on_deleted: Callable | None = None
        self._on_view_single: Callable | None = None  # 切换到 Single View
        self._on_copy: Callable | None = None          # 复制此框
        self._on_rotate_left: Callable | None = None   # 逆时针 90°
        self._on_rotate_right: Callable | None = None  # 顺时针 90°

        # 交互设置
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # 从 CropRect 同步位置
        self._sync_from_rect()

    def set_callbacks(self, on_changed: Callable, on_deleted: Callable,
                      on_view_single: Callable | None = None,
                      on_copy: Callable | None = None,
                      on_rotate_left: Callable | None = None,
                      on_rotate_right: Callable | None = None) -> None:
        """设置回调函数"""
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self._on_view_single = on_view_single
        self._on_copy = on_copy
        self._on_rotate_left = on_rotate_left
        self._on_rotate_right = on_rotate_right

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

        # 半透明填充（选中时）
        if is_selected:
            painter.setBrush(QBrush(_ACCENT_FILL))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 外框
        if is_selected:
            pen = QPen(_ACCENT, PEN_WIDTH_SELECTED)
        else:
            pen = QPen(_DASHED, PEN_WIDTH_INACTIVE, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(PEN_DASH_PATTERN)
        painter.setPen(pen)
        painter.drawRect(rect)

        # 选中时绘制手柄和工具栏（在旋转坐标系内）
        if is_selected:
            self._paint_handles(painter, rect)
            if self._hovered_handle != HandlePosition.NONE or self._is_toolbar_hovered:
                self._paint_toolbar(painter, rect)

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
            painter.setPen(QPen(_ACCENT, 1.0))
            painter.setBrush(QBrush(_CANVAS_BG))
            painter.drawRect(QRectF(pos.x() - half, pos.y() - half, size, size))

        # 旋转手柄 — 带连接线
        rotation_pos = QPointF(
            rect.center().x(),
            rect.top() - ROTATION_HANDLE_OFFSET,
        )

        # 连接线
        painter.setPen(QPen(_ACCENT, ROTATION_LINE_WIDTH, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(rect.center().x(), rect.top()),
            rotation_pos,
        )

        # 旋转手柄方块
        size = hhs if self._hovered_handle == HandlePosition.ROTATION else hs
        half = size / 2
        painter.setPen(QPen(_ACCENT, 1.0))
        painter.setBrush(QBrush(_CANVAS_BG))
        painter.drawRect(QRectF(rotation_pos.x() - half, rotation_pos.y() - half, size, size))

        # 显示当前旋转角度
        angle = self._crop_rect.rotation_angle
        if angle != 0.0:
            painter.setPen(QPen(_ACCENT, 1.0))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            angle_text = f"{angle:.0f}°"
            text_pos = QPointF(rotation_pos.x() + 12, rotation_pos.y() - 4)
            painter.drawText(text_pos, angle_text)

    # ---- 工具栏 ----

    TOOLBAR_BUTTON_SIZE = 20
    TOOLBAR_GAP = 4
    TOOLBAR_LABELS = ["👁", "✕", "↺", "⧉"]  # view, delete, rotate, copy (参考设计)

    def _toolbar_rects(self, rect: QRectF) -> list:
        """返回工具栏按钮的 QRectF（在裁剪框坐标系内）"""
        btn_w = self.TOOLBAR_BUTTON_SIZE
        n = len(self.TOOLBAR_LABELS)
        total_w = btn_w * n + self.TOOLBAR_GAP * (n - 1)
        x_start = rect.center().x() - total_w / 2
        y = rect.top() - 28  # 框上方 28px

        rects = []
        for i in range(n):
            rx = x_start + i * (btn_w + self.TOOLBAR_GAP)
            rects.append(QRectF(rx, y, btn_w, btn_w))
        return rects

    def _paint_toolbar(self, painter: QPainter, rect: QRectF) -> None:
        """绘制裁剪框上方的工具栏"""
        btn_rects = self._toolbar_rects(rect)

        # 背景
        n = len(self.TOOLBAR_LABELS)
        total_w = self.TOOLBAR_BUTTON_SIZE * n + self.TOOLBAR_GAP * (n - 1)
        bg_rect = QRectF(
            rect.center().x() - total_w / 2 - 4,
            rect.top() - 32,
            total_w + 8,
            self.TOOLBAR_BUTTON_SIZE + 8,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 160)))  # 深色浮层，保持可见性
        painter.drawRoundedRect(bg_rect, 4, 4)

        # 按钮
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)

        for _i, (btn_rect, label) in enumerate(zip(btn_rects, self.TOOLBAR_LABELS)):
            # 按钮背景
            if btn_rect.contains(self._toolbar_hover_pos):
                painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(btn_rect, 3, 3)

            # 图标文字
            painter.setPen(QPen(_WHITE))
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, label)

    @property
    def _toolbar_hover_pos(self) -> QPointF:
        """返回鼠标在裁剪框坐标系中的位置（用于工具栏高亮）"""
        return getattr(self, '_last_hover_pos', QPointF())

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

        # 旋转手柄
        rotation_pos = QPointF(rect.center().x(), rect.top() - ROTATION_HANDLE_OFFSET)
        if (pos - rotation_pos).manhattanLength() < hs:
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
            self.update()  # 触发重绘
        self._last_hover_pos = event.pos()
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
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 先检查工具栏按钮（4 个：👁view ✕delete ↺rotate ⧉copy）
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
            elif toolbar_idx == 3 and self._on_copy:
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
            # 注意：Qt 坐标系 y 轴向下，所以角度方向与数学坐标系相反
            angle_rad = math.atan2(-dy, dx)  # 负 dy 因为 y 轴向下
            angle_deg = math.degrees(angle_rad)

            # 转换为"从 12 点钟方向顺时针"的角度
            # atan2 的 0° 在 3 点钟方向，顺时针为正
            # 我们要的是从 12 点钟方向顺时针
            rotation = normalize_angle(90.0 - angle_deg)

            # 吸附到 0°, 90°, -90°, 180°（容差 ±15°）
            snap_angles = [0.0, 90.0, -90.0, 180.0]
            for snap in snap_angles:
                if abs(rotation - snap) < 15:
                    rotation = snap
                    break

            self._crop_rect.rotation_angle = rotation
            self.update()  # 触发重绘，但不触发 _on_changed 信号风暴
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
