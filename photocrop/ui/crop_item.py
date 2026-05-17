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
    """更新 CropItem 颜色 — 全统一 #5B8DEF 体系（不随主题切换）"""
    ACCENT = QColor("#5B8DEF")
    CropItem._t_accent = ACCENT
    CropItem._t_accent_hover = ACCENT
    fill = QColor(ACCENT)
    fill.setAlpha(25)  # 10%
    CropItem._t_accent_fill = fill
    dashed = QColor(ACCENT)
    dashed.setAlpha(128)  # 50%
    CropItem._t_dashed = dashed
    # 工具栏背景 — 融入 #5B8DEF 色系
    tbg = QColor("#5B8DEF")
    tbg.setAlpha(210)  # ~82%
    CropItem._t_toolbar_bg = tbg


# 手柄尺寸
HANDLE_SIZE = 18          # 角标视觉尺寸
HANDLE_HOVER_SIZE = 22    # 悬停放大尺寸
HANDLE_HIT_RADIUS = 22    # 独立触发判定半径（高于视觉尺寸，便于鼠标靠近即识别）

# 自由旋转抓取手柄（裁剪框上方的旋转图标，hover 激活拖拽旋转）
GRAB_HANDLE_SIZE = 32     # 抓取手柄视觉尺寸（容纳旋转图标）
GRAB_HANDLE_OFFSET = 60   # 距裁剪框顶边 60px（与工具栏按钮中心对齐）
GRAB_HIT_EXTRA = 8        # 命中检测额外容差

# 框线样式
PEN_WIDTH_SELECTED = 10.0     # 选中实线宽度
PEN_WIDTH_INACTIVE = 10.0     # 未选中点状虚线宽度（与选中实线一致）
PEN_DASH_PATTERN = [1, 3]     # 点状虚线（1px 线段 + 3px 间隙，配合 RoundCap 成细密圆点，接近实线）

# Breathing glow animation（选中框光感呼吸脉动）
BREATHING_INTERVAL_MS = 80    # 动画 tick 间隔（比原来 50ms 降低频率，减少重绘开销）
BREATHING_SPEED = 0.15        # 相位增量/tick → ~2.1s 完整周期


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
    GRAB_ROTATION = "grab_rotation"
    BODY = "body"


# ============================================================
# CropItem
# ============================================================

class CropItem(QGraphicsRectItem):
    """可交互裁剪框 — Apple 设计风格"""

    # 统一蓝灰色 #5B8DEF（不随主题切换）
    _t_accent = QColor("#5B8DEF")
    _t_accent_hover = QColor("#5B8DEF")
    _t_accent_fill = QColor(91, 141, 239, 25)   # 10%
    _t_dashed = QColor(91, 141, 239, 128)        # 50%
    _t_toolbar_bg = QColor(91, 141, 239, 210)    # #5B8DEF ~82%

    def __init__(self, crop_rect: CropRect, parent: QGraphicsItem | None = None):
        super().__init__(parent)

        self._crop_rect = crop_rect
        self._drag_handle = HandlePosition.NONE
        self._drag_start = QPointF()
        self._drag_rect = QRectF()
        self._hovered_handle = HandlePosition.NONE
        self._is_toolbar_hovered = False
        self._is_item_hovered = False  # 整体 hover 状态（用于工具栏显示）
        self._breathing_phase = 0.0  # 呼吸光晕动画相位
        self._breathing_active = False  # 呼吸动画是否运行中

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

        # 交互设置（不使用 ItemCoordinateCache — macOS CoreAnimation 下大范围透明区域合成出白色伪影）
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
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
        """动态计算边界，覆盖裁剪框 + 自由旋转抓取手柄 + 工具栏"""
        r = super().boundingRect()
        rect = self.rect()
        if rect.isEmpty():
            return r

        # 抓取手柄区域
        grab_pos = self._grab_handle_pos(rect)
        gh_half = GRAB_HANDLE_SIZE / 2 + GRAB_HIT_EXTRA
        grab_rect = QRectF(
            grab_pos.x() - gh_half,
            grab_pos.y() - gh_half,
            gh_half * 2,
            gh_half * 2,
        )

        # 工具栏背景区域
        tb_rect = self._toolbar_bg_rect(rect)

        # 合并所有区域
        all_rects = [r, tb_rect, grab_rect]
        top = min(rr.top() for rr in all_rects)
        left = min(rr.left() for rr in all_rects)
        bottom = max(rr.bottom() for rr in all_rects)
        right = max(rr.right() for rr in all_rects)

        return QRectF(left, top, right - left, bottom - top)

    def shape(self) -> QPainterPath:
        """精确碰撞检测：裁剪框 + 抓取手柄 + 工具栏"""
        path = QPainterPath()
        rect = self.rect()
        margin = max(PEN_WIDTH_SELECTED, PEN_WIDTH_INACTIVE) / 2
        # 裁剪框本身（含边框余量）
        path.addRect(rect.adjusted(-margin, -margin, margin, margin))
        # 抓取手柄
        grab_pos = self._grab_handle_pos(rect)
        gh = GRAB_HANDLE_SIZE + GRAB_HIT_EXTRA
        gh_half = gh / 2
        path.addRect(QRectF(grab_pos.x() - gh_half, grab_pos.y() - gh_half, gh, gh))
        # 工具栏背景
        path.addRect(self._toolbar_bg_rect(rect))
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

        # 选中呼吸光晕（宽笔触柔光，脉冲透明度 — 连续脉动）
        if is_selected:
            glow_alpha_val = int(25 + 25 * (math.sin(self._breathing_phase) * 0.5 + 0.5))
            glow_color = QColor(self._t_accent)
            glow_color.setAlpha(glow_alpha_val)
            glow_pen = QPen(glow_color, 18.0)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # 半透明填充（选中时）
        if is_selected:
            painter.setBrush(QBrush(self._t_accent_fill))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 外框 — 选中实线（光晕之上） / 未选中的点状虚线
        if is_selected:
            pen = QPen(self._t_accent, PEN_WIDTH_SELECTED)
        else:
            pen = QPen(self._t_dashed, PEN_WIDTH_INACTIVE, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(PEN_DASH_PATTERN)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawRect(rect)

        # 选中时绘制手柄 + 工具栏（选中即一直显示，不依赖 hover）
        # 注意：工具栏先画，手柄/连接线后画，确保连接线不被工具栏背景遮挡
        if is_selected:
            self._paint_toolbar(painter, rect)
            self._paint_handles(painter, rect)

        # 拖动时显示尺寸信息
        if self._drag_handle not in (HandlePosition.NONE, HandlePosition.BODY,
                                     HandlePosition.ROTATION, HandlePosition.GRAB_ROTATION):
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
            painter.setPen(QPen(self._t_accent, 1.5))
            painter.setBrush(QBrush(self._t_accent))
            painter.drawRect(QRectF(pos.x() - half, pos.y() - half, size, size))

        # 自由旋转抓取手柄（裁剪框上方旋转图标 + 连接线）
        grab_pos = self._grab_handle_pos(rect)
        is_hovered = self._hovered_handle == HandlePosition.GRAB_ROTATION
        grab_size = GRAB_HANDLE_SIZE + 6 if is_hovered else GRAB_HANDLE_SIZE
        grab_half = grab_size / 2

        # 连接线：裁剪框顶边 → 抓取手柄下边缘
        line_pen = QPen(self._t_accent, 2.0)
        line_pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(line_pen)
        painter.drawLine(
            QPointF(rect.center().x(), rect.top()),
            QPointF(grab_pos.x(), grab_pos.y() + GRAB_HANDLE_SIZE / 2),
        )

        # 实心圆形背景
        grab_rect = QRectF(grab_pos.x() - grab_half, grab_pos.y() - grab_half, grab_size, grab_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._t_accent))
        painter.drawEllipse(grab_rect)

        # hover 时白色 overlay
        if is_hovered:
            painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
            painter.drawEllipse(grab_rect)

        # 旋转图标（白色，居中）
        icon = get_icon("rotate-ccw", "#FFFFFF")
        icon_size = int(grab_size * 0.7)
        icon_x = int(grab_pos.x() - icon_size / 2)
        icon_y = int(grab_pos.y() - icon_size / 2)
        icon.paint(painter, QRectF(icon_x, icon_y, icon_size, icon_size).toRect(),
                   Qt.AlignmentFlag.AlignCenter)

    # ---- 工具栏（右上角） ----

    TOOLBAR_BUTTON_SIZE = 84
    TOOLBAR_GAP = 2
    TOOLBAR_ICONS = ["eye", "x", "copy"]  # 查看 / 删除 / 复制（旋转通过抓取手柄）
    TOOLBAR_ICON_COLOR = "#FFFFFF"  # 纯白，最大化对比度

    def _toolbar_bg_rect(self, rect: QRectF) -> QRectF:
        """工具栏背景矩形（裁剪框上方偏右）"""
        n = len(self.TOOLBAR_ICONS)
        total_w = self.TOOLBAR_BUTTON_SIZE * n + self.TOOLBAR_GAP * (n - 1)
        btn_h = self.TOOLBAR_BUTTON_SIZE
        bg_w = total_w + 16  # 8px 内边距两侧
        bg_h = btn_h + 12    # 6px 内边距上下（面板总高96不变）
        return QRectF(
            rect.right() - bg_w - 16,   # 右侧对齐，16px 外边距
            rect.top() - bg_h - 12,     # 裁剪框上方，12px 间距
            bg_w,
            bg_h,
        )

    def _toolbar_rects(self, rect: QRectF) -> list:
        """返回工具栏按钮的 QRectF（基于 bg_rect 内边距）"""
        btn_w = self.TOOLBAR_BUTTON_SIZE
        n = len(self.TOOLBAR_ICONS)
        bg_rect = self._toolbar_bg_rect(rect)
        x_start = bg_rect.x() + 8
        y = bg_rect.y() + 6
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

        # hover 判定需变换到未旋转坐标系（与 _toolbar_button_at 一致）
        hover_pos = self._unrotated_pos(getattr(self, '_last_hover_pos', QPointF()))

        # 按钮
        for _i, (btn_rect, icon_name) in enumerate(zip(btn_rects, self.TOOLBAR_ICONS)):
            # 按钮 hover 高亮
            if btn_rect.contains(hover_pos):
                painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(btn_rect, 4, 4)

            # SVG 图标（0px padding → 84×84 填满按钮，最大化可见面积）
            icon = get_icon(icon_name, self.TOOLBAR_ICON_COLOR)
            icon_rect = btn_rect
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

        # 文字（统一使用 #5B8DEF）
        painter.setPen(QPen(self._t_accent))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _grab_handle_pos(self, rect: QRectF) -> QPointF:
        """返回自由旋转抓取手柄的中心位置（裁剪框上方）"""
        return QPointF(rect.center().x(), rect.top() - GRAB_HANDLE_OFFSET)

    def _toolbar_button_at(self, pos: QPointF) -> int:
        """检测点击是否在工具栏按钮上，返回按钮索引（-1=无）"""
        rect = self.rect()
        btn_rects = self._toolbar_rects(rect)
        p = self._unrotated_pos(pos)
        for i, btn_rect in enumerate(btn_rects):
            if btn_rect.contains(p):
                return i
        return -1

    # ---- 坐标变换 ----

    def _unrotated_pos(self, pos: QPointF) -> QPointF:
        """将鼠标位置旋转回 item 的未旋转坐标系（用于手柄命中检测）。
        paint() 中对裁剪框施加了 painter.rotate(-angle) 旋转，所以逆变换是旋转 +angle。
        """
        angle = self._crop_rect.rotation_angle
        if angle == 0:
            return pos
        rad = math.radians(-angle)
        center = self.rect().center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        return QPointF(
            center.x() + dx * cos_a + dy * sin_a,
            center.y() - dx * sin_a + dy * cos_a,
        )

    # ---- 手柄检测 ----

    def _handle_at(self, pos: QPointF) -> str:
        rect = self.rect()
        hs = HANDLE_HIT_RADIUS  # 独立触发半径，远大于视觉尺寸

        # 裁剪框旋转时，鼠标 pos 在旋转后的坐标系中，需要变换回未旋转坐标系
        # 才能和未旋转的手柄矩形正确匹配
        p = self._unrotated_pos(pos)

        # 自由旋转抓取手柄
        grab_pos = self._grab_handle_pos(rect)
        grab_hit = GRAB_HANDLE_SIZE + GRAB_HIT_EXTRA
        grab_half = grab_hit / 2
        grab_rect = QRectF(grab_pos.x() - grab_half, grab_pos.y() - grab_half, grab_hit, grab_hit)
        if grab_rect.contains(p):
            return HandlePosition.GRAB_ROTATION

        # 四角
        corners = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
        ]
        for corner_pos, handle in corners:
            if (p - corner_pos).manhattanLength() < hs:
                return handle

        # 四边
        edges = [
            (QPointF(rect.center().x(), rect.top()), HandlePosition.TOP),
            (QPointF(rect.center().x(), rect.bottom()), HandlePosition.BOTTOM),
            (QPointF(rect.left(), rect.center().y()), HandlePosition.LEFT),
            (QPointF(rect.right(), rect.center().y()), HandlePosition.RIGHT),
        ]
        for edge_pos, handle in edges:
            if (p - edge_pos).manhattanLength() < hs:
                return handle

        if rect.contains(p):
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
            HandlePosition.GRAB_ROTATION: Qt.CursorShape.CrossCursor,
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
            # 点击工具栏/手柄前确保选中此框（选中后才显示工具栏视觉反馈）
            self.setSelected(True)

            # 先检查工具栏按钮（3 个：eye / x / copy）
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
            elif toolbar_idx == 2 and self._on_copy:
                self._on_copy()
                event.accept()
                return

            self._drag_handle = self._handle_at(event.pos())
            self._drag_start = event.pos()
            self._drag_rect = self.rect()

            # 整体拖动时暂停呼吸动画，减少重绘开销，提升跟手性
            if self._drag_handle == HandlePosition.BODY:
                self._breathing_active = False

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
        elif self._drag_handle in (HandlePosition.ROTATION, HandlePosition.GRAB_ROTATION):
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
        # _on_changed 延迟到 release 时触发，避免拖动期间信号风暴
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # 拖动结束，一次性触发变更回调（避免拖动期间信号风暴）
        if self._drag_handle != HandlePosition.NONE and self._on_changed:
            self._on_changed()
        # 恢复呼吸动画
        if self._drag_handle == HandlePosition.BODY and self.isSelected():
            self._start_breathing()
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
        """选中状态变化时触发光晕呼吸动画"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self._start_breathing()
            else:
                self._stop_breathing()
        return super().itemChange(change, value)

    # ---- 呼吸光晕动画 ----

    def _start_breathing(self) -> None:
        """启动选中框呼吸光晕动画（连续脉冲透明度）"""
        self._breathing_phase = 0.0
        self._breathing_active = True
        self._schedule_breathing_tick()

    def _stop_breathing(self) -> None:
        """停止呼吸光晕动画"""
        self._breathing_active = False
        self._breathing_phase = 0.0
        self.update()

    def _schedule_breathing_tick(self) -> None:
        """呼吸动画 tick：推进相位并安排下一次"""
        if not self._breathing_active:
            return
        self._breathing_phase = (self._breathing_phase + BREATHING_SPEED) % (2 * math.pi)
        self.update()
        QTimer.singleShot(BREATHING_INTERVAL_MS, self._schedule_breathing_tick)
