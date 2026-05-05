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
from typing import Optional, Callable

from PySide6.QtCore import Qt, QRectF, QPointF
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


# ============================================================
# Apple 设计常量
# ============================================================

# 主色调
APPLE_BLUE = QColor("#0071e3")
APPLE_BLUE_HOVER = QColor("#2997ff")
APPLE_BLUE_LIGHT = QColor(0, 113, 227, 40)  # 半透明蓝

# 中性色
DARK_BG = QColor("#1d1d1f")
LIGHT_BG = QColor("#f5f5f7")
WHITE = QColor("#ffffff")
SEPARATOR = QColor(0, 0, 0, 26)  # 10% 黑

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

    def __init__(self, crop_rect: CropRect, parent: Optional[QGraphicsItem] = None):
        super().__init__(parent)

        self._crop_rect = crop_rect
        self._drag_handle = HandlePosition.NONE
        self._drag_start = QPointF()
        self._drag_rect = QRectF()
        self._hovered_handle = HandlePosition.NONE

        # 回调函数（替代 Signal）
        self._on_changed: Optional[Callable] = None
        self._on_deleted: Optional[Callable] = None

        # 交互设置
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # 从 CropRect 同步位置
        self._sync_from_rect()

    def set_callbacks(self, on_changed: Callable, on_deleted: Callable) -> None:
        """设置回调函数"""
        self._on_changed = on_changed
        self._on_deleted = on_deleted

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

        # 半透明蓝色填充（选中时）
        if is_selected:
            painter.setBrush(QBrush(APPLE_BLUE_LIGHT))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 外框
        if is_selected:
            pen = QPen(APPLE_BLUE, PEN_WIDTH_SELECTED)
        else:
            pen = QPen(QColor(255, 255, 255, 120), PEN_WIDTH_INACTIVE, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(PEN_DASH_PATTERN)
        painter.setPen(pen)
        painter.drawRect(rect)

        # 选中时绘制手柄
        if is_selected:
            self._paint_handles(painter, rect)

    def _paint_handles(self, painter: QPainter, rect: QRectF) -> None:
        hs = HANDLE_SIZE
        hhs = HANDLE_HOVER_SIZE

        # 四角手柄 — 实心圆
        corners = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
        ]
        for pos, handle in corners:
            size = hhs if self._hovered_handle == handle else hs
            painter.setPen(QPen(WHITE, 1.5))
            painter.setBrush(QBrush(APPLE_BLUE))
            painter.drawEllipse(pos, size, size)

        # 四边手柄 — 小方块
        midpoints = [
            (QPointF(rect.center().x(), rect.top()), HandlePosition.TOP),
            (QPointF(rect.center().x(), rect.bottom()), HandlePosition.BOTTOM),
            (QPointF(rect.left(), rect.center().y()), HandlePosition.LEFT),
            (QPointF(rect.right(), rect.center().y()), HandlePosition.RIGHT),
        ]
        for pos, handle in midpoints:
            size = hhs if self._hovered_handle == handle else hs
            half = size / 2
            painter.setPen(QPen(WHITE, 1.5))
            painter.setBrush(QBrush(APPLE_BLUE))
            painter.drawRect(QRectF(pos.x() - half, pos.y() - half, size, size))

        # 旋转手柄 — 带连接线
        rotation_pos = QPointF(
            rect.center().x(),
            rect.top() - ROTATION_HANDLE_OFFSET,
        )

        # 连接线
        painter.setPen(QPen(APPLE_BLUE, ROTATION_LINE_WIDTH, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(rect.center().x(), rect.top()),
            rotation_pos,
        )

        # 旋转手柄圆
        size = hhs if self._hovered_handle == HandlePosition.ROTATION else hs
        painter.setPen(QPen(WHITE, 1.5))
        painter.setBrush(QBrush(APPLE_BLUE_HOVER))
        painter.drawEllipse(rotation_pos, size, size)

        # 显示当前旋转角度
        angle = self._crop_rect.rotation_angle
        if angle != 0.0:
            painter.setPen(QPen(WHITE, 1.0))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            angle_text = f"{angle:.0f}°"
            text_pos = QPointF(rotation_pos.x() + 12, rotation_pos.y() - 4)
            painter.drawText(text_pos, angle_text)

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
        self._update_cursor(handle)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered_handle = HandlePosition.NONE
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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
            rotation = 90.0 - angle_deg

            # 规范化到 [-180, 180]
            while rotation > 180:
                rotation -= 360
            while rotation < -180:
                rotation += 360

            # 吸附到 0°, 90°, -90°, 180°（容差 ±15°）
            snap_angles = [0.0, 90.0, -90.0, 180.0]
            for snap in snap_angles:
                if abs(rotation - snap) < 15:
                    rotation = snap
                    break

            self._crop_rect.rotation_angle = rotation
            if self._on_changed:
                self._on_changed()
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

        self.setRect(new_rect)
        self._sync_to_rect()
        if self._on_changed:
            self._on_changed()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
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
