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


# 手柄尺寸 — 实心圆点
CORNER_DOT_RADIUS = 14      # 四角圆点半径
CORNER_DOT_HOVER = 18       # 四角圆点 hover 半径
CORNER_HIT_RADIUS = 44      # 四角命中判定半径（manhattan 距离）
EDGE_HIT_WIDTH = 22         # 边线命中检测的半宽（鼠标到边线的垂直距离阈值）

# 自由旋转抓取手柄（裁剪框上方的旋转圆点，与四角同尺寸）
GRAB_HANDLE_RADIUS = 14     # 与 CORNER_DOT_RADIUS 一致
GRAB_HANDLE_HOVER = 18      # 与 CORNER_DOT_HOVER 一致
GRAB_HANDLE_OFFSET = 40     # 距裁剪框顶边 40px
GRAB_HIT_EXTRA = 8          # 命中检测额外容差

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

        # Python 端显式缓存 rect，避免 Qt 绑定层返回值不一致导致 sync 失败。
        # 所有修改 rect 的地方（setRect / _sync_from_rect / mouseMoveEvent）同步更新。
        self._py_rect = QRectF()

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
        """动态计算边界，覆盖裁剪框 + 自由旋转抓取手柄（工具栏在框内无需额外扩展）"""
        r = super().boundingRect()
        rect = self.rect()
        if rect.isEmpty():
            return r

        # 抓取手柄区域（在裁剪框上方）
        grab_pos = self._grab_handle_pos(rect)
        gh = max(GRAB_HANDLE_HOVER, GRAB_HANDLE_RADIUS) + GRAB_HIT_EXTRA
        grab_rect = QRectF(
            grab_pos.x() - gh,
            grab_pos.y() - gh,
            gh * 2,
            gh * 2,
        )

        # 合并裁剪框 + 抓取手柄
        top = min(r.top(), grab_rect.top())
        left = min(r.left(), grab_rect.left())
        bottom = max(r.bottom(), grab_rect.bottom())
        right = max(r.right(), grab_rect.right())

        return QRectF(left, top, right - left, bottom - top)

    def shape(self) -> QPainterPath:
        """精确碰撞检测：裁剪框 + 抓取手柄（工具栏在框内已包含）"""
        path = QPainterPath()
        rect = self.rect()
        margin = max(PEN_WIDTH_SELECTED, PEN_WIDTH_INACTIVE) / 2
        # 裁剪框本身（含边框余量）
        path.addRect(rect.adjusted(-margin, -margin, margin, margin))
        # 抓取手柄
        grab_pos = self._grab_handle_pos(rect)
        gh = max(GRAB_HANDLE_HOVER, GRAB_HANDLE_RADIUS) + GRAB_HIT_EXTRA
        path.addEllipse(grab_pos, gh, gh)
        return path

    @property
    def crop_rect(self) -> CropRect:
        return self._crop_rect

    def _setup_transform_origin(self):
        """设置旋转中心为裁剪框中心（必须在 rect 或 rotation 变化后调用）"""
        c = self._py_rect.center()
        self.setTransformOriginPoint(c)

    def _sync_from_rect(self):
        r = self._crop_rect
        new_rect = QRectF(
            r.x - r.width / 2,
            r.y - r.height / 2,
            r.width,
            r.height,
        )
        self.setRect(new_rect)
        self._py_rect = new_rect  # Python 端同步缓存
        self._setup_transform_origin()
        self.setRotation(r.rotation_angle)

    def _sync_to_rect(self):
        """从 Python 端缓存的 rect 更新 CropRect 的 x/y/width/height。

        注意：rotation_angle 不在本方法中同步——旋转角度由鼠标拖拽
        直接写入 self._crop_rect.rotation_angle（mouseMoveEvent 旋转分支）。
        调用 _sync_to_rect 的场景（resize / move / 强制同步）不会改变旋转角度，
        因此不需要覆写 rotation_angle，否则会丢失用户通过旋转手柄设的角度。
        """
        rect = self._py_rect
        self._crop_rect.x = rect.center().x()
        self._crop_rect.y = rect.center().y()
        self._crop_rect.width = rect.width()
        self._crop_rect.height = rect.height()
        self._setup_transform_origin()

    # ---- 绘制 ----

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.rect()
        if rect.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_selected = self.isSelected()

        # 旋转由 QGraphicsItem.setRotation() 处理（item 级旋转变换）
        # paint 内不需要手动旋转 painter

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

        # 自由旋转抓取手柄（始终显示，连接线样式跟随选框状态）
        self._paint_grab_handle(painter, rect, is_selected)

        # 选中时绘制四角手柄 + 工具栏
        if is_selected:
            self._paint_toolbar(painter, rect)
            self._paint_corner_handles(painter, rect)

        # 拖动时显示尺寸信息
        if self._drag_handle not in (HandlePosition.NONE, HandlePosition.BODY,
                                     HandlePosition.ROTATION, HandlePosition.GRAB_ROTATION):
            self._paint_size_label(painter, rect)

    def _paint_corner_handles(self, painter: QPainter, rect: QRectF) -> None:
        """绘制四角圆点手柄（仅选中时显示）"""
        corner_handles = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
        ]
        for pos, handle in corner_handles:
            r = CORNER_DOT_HOVER if self._hovered_handle == handle else CORNER_DOT_RADIUS
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._t_accent))
            painter.drawEllipse(pos, r, r)

    def _paint_grab_handle(self, painter: QPainter, rect: QRectF, is_selected: bool) -> None:
        """绘制自由旋转抓取手柄（始终显示，连接线样式跟随选框状态）"""
        grab_pos = self._grab_handle_pos(rect)
        is_hovered = self._hovered_handle == HandlePosition.GRAB_ROTATION
        grab_r = GRAB_HANDLE_HOVER if is_hovered else GRAB_HANDLE_RADIUS

        # 连接线：样式跟随选框边框
        if is_selected:
            line_pen = QPen(self._t_accent, PEN_WIDTH_SELECTED, Qt.PenStyle.SolidLine)
        else:
            line_pen = QPen(self._t_dashed, PEN_WIDTH_INACTIVE, Qt.PenStyle.CustomDashLine)
            line_pen.setDashPattern(PEN_DASH_PATTERN)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(line_pen)
        painter.drawLine(
            QPointF(rect.center().x(), rect.top()),
            QPointF(grab_pos.x(), grab_pos.y() + grab_r),
        )

        # 实心蓝色圆点
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._t_accent))
        painter.drawEllipse(grab_pos, grab_r, grab_r)

        # hover 时白色 overlay
        if is_hovered:
            painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
            painter.drawEllipse(grab_pos, grab_r, grab_r)

    # ---- 工具栏（内部右上角） ----

    TOOLBAR_BUTTON_SIZE = 84
    TOOLBAR_GAP = 2
    TOOLBAR_ICONS = ["eye", "x", "copy"]  # 查看 / 删除 / 复制（旋转通过抓取手柄）
    TOOLBAR_ICON_COLOR = "#FFFFFF"  # 纯白，最大化对比度

    def _toolbar_bg_rect(self, rect: QRectF) -> QRectF:
        """工具栏背景矩形（裁剪框内部右上角）"""
        n = len(self.TOOLBAR_ICONS)
        total_w = self.TOOLBAR_BUTTON_SIZE * n + self.TOOLBAR_GAP * (n - 1)
        btn_h = self.TOOLBAR_BUTTON_SIZE
        bg_w = total_w + 16  # 8px 内边距两侧
        bg_h = btn_h + 12    # 6px 内边距上下
        return QRectF(
            rect.right() - bg_w - 8,    # 右侧贴边，8px 内边距
            rect.top() + 8,             # 顶部贴边，8px 内边距
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
        """绘制裁剪框内部右上角的工具栏"""
        btn_rects = self._toolbar_rects(rect)

        # 背景
        bg_rect = self._toolbar_bg_rect(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._t_toolbar_bg))
        painter.drawRoundedRect(bg_rect, 6, 6)

        # item 级旋转下 _last_hover_pos 已在本地坐标系
        hover_pos = getattr(self, '_last_hover_pos', QPointF())

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
            icon.paint(painter, btn_rect.toRect(), Qt.AlignmentFlag.AlignCenter)

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
        """返回自由旋转抓取手柄的圆心位置（裁剪框上方）"""
        return QPointF(rect.center().x(), rect.top() - GRAB_HANDLE_OFFSET)

    def _toolbar_button_at(self, pos: QPointF) -> int:
        """检测点击是否在工具栏按钮上，返回按钮索引（-1=无）"""
        rect = self.rect()
        btn_rects = self._toolbar_rects(rect)
        # item 级旋转下 pos 已在本地坐标系，无需 unrotated 变换
        for i, btn_rect in enumerate(btn_rects):
            if btn_rect.contains(pos):
                return i
        return -1

    # ---- 手柄检测 ----

    def _handle_at(self, pos: QPointF) -> str:
        rect = self._py_rect

        # item 级旋转（setRotation）自动将 event.pos() 转换到 item 本地坐标系
        # pos 已经是未旋转坐标，直接使用即可
        p = pos

        # 自由旋转抓取手柄（圆形命中检测）
        grab_pos = self._grab_handle_pos(rect)
        grab_hit_r = max(GRAB_HANDLE_HOVER, GRAB_HANDLE_RADIUS) + GRAB_HIT_EXTRA
        if (p - grab_pos).manhattanLength() < grab_hit_r * 1.4:  # manhattan 近似圆形
            return HandlePosition.GRAB_ROTATION

        # 四角（2× 命中半径）
        corners = [
            (rect.topLeft(), HandlePosition.TOP_LEFT),
            (rect.topRight(), HandlePosition.TOP_RIGHT),
            (rect.bottomLeft(), HandlePosition.BOTTOM_LEFT),
            (rect.bottomRight(), HandlePosition.BOTTOM_RIGHT),
        ]
        for corner_pos, handle in corners:
            if (p - corner_pos).manhattanLength() < CORNER_HIT_RADIUS:
                return handle

        # 四边 — 整条边线均可触发（鼠标到线段的垂直距离 < EDGE_HIT_WIDTH）
        edges = [
            (rect.top(), rect.left(), rect.right(), True, HandlePosition.TOP),       # 水平边
            (rect.bottom(), rect.left(), rect.right(), True, HandlePosition.BOTTOM),  # 水平边
            (rect.left(), rect.top(), rect.bottom(), False, HandlePosition.LEFT),     # 垂直边
            (rect.right(), rect.top(), rect.bottom(), False, HandlePosition.RIGHT),   # 垂直边
        ]
        for line_val, range_min, range_max, is_horizontal, handle in edges:
            if is_horizontal:
                # 水平边：y 方向距离 < 阈值，x 在边范围内
                if abs(p.y() - line_val) < EDGE_HIT_WIDTH and range_min <= p.x() <= range_max:
                    return handle
            else:
                # 垂直边：x 方向距离 < 阈值，y 在边范围内
                if abs(p.x() - line_val) < EDGE_HIT_WIDTH and range_min <= p.y() <= range_max:
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
            self._drag_start_scene = event.scenePos()  # 记录场景坐标起始点（BODY + RESIZE 共用）
            self._drag_rect = QRectF(self._py_rect)  # 使用 Python 端缓存的 rect
            # BODY 拖动：额外记录框中心场景坐标
            if self._drag_handle == HandlePosition.BODY:
                self._drag_rect_center_scene = self.mapToScene(self._drag_rect.center())

            # 整体拖动时暂停呼吸动画，减少重绘开销，提升跟手性
            if self._drag_handle == HandlePosition.BODY:
                self._breathing_active = False

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_handle == HandlePosition.NONE:
            return

        new_rect = QRectF(self._drag_rect)

        if self._drag_handle == HandlePosition.BODY:
            # 全程场景坐标计算，避免旋转导致的坐标系偏差
            new_center_scene = self._drag_rect_center_scene + (event.scenePos() - self._drag_start_scene)
            new_center_local = self.mapFromScene(new_center_scene)
            offset = new_center_local - self._drag_rect.center()
            new_rect.translate(offset)
        elif self._drag_handle in (HandlePosition.ROTATION, HandlePosition.GRAB_ROTATION):
            # 在场景坐标系中计算角度（item 旋转后 event.pos() 在本地坐标系，
            # 需要转到场景坐标才能正确反映鼠标在屏幕上的方位）
            center_scene = self.mapToScene(self._py_rect.center())
            mouse_scene = event.scenePos()
            dx = mouse_scene.x() - center_scene.x()
            dy = mouse_scene.y() - center_scene.y()

            # 旋转方向：鼠标往哪拖，框的顶部就往哪偏（直接操控感）
            # atan2(-dy, -dx) 在标准数学坐标系中，但反转 x 方向：
            #   12 点钟(dx=0,dy=-40): atan2(40, 0) = 90° → rotation = 0° ✓
            #   左拖(dx<0,dy≈-40):    atan2(40, 正值) < 90° → rotation < 0°
            #     → 负角度 = 顺时针 = 框顶部向左偏 ✓
            #   右拖(dx>0,dy≈-40):    atan2(40, 负值) > 90° → rotation > 0°
            #     → 正角度 = 逆时针 = 框顶部向右偏 ✓
            angle_rad = math.atan2(-dy, -dx)
            angle_deg = math.degrees(angle_rad)
            rotation = normalize_angle(angle_deg - 90.0)

            # 吸附到 0°, 90°, -90°, 180°
            snap_angles = [0.0, 90.0, -90.0, 180.0]
            for snap in snap_angles:
                if abs(rotation - snap) < 0.5:
                    rotation = snap
                    break

            self._crop_rect.rotation_angle = rotation
            self._setup_transform_origin()
            self.setRotation(rotation)
            self.update()
            # 轻量实时回调（仅更新属性面板，不触发完整刷新）
            if self._on_rotating:
                self._on_rotating(rotation)
            event.accept()
            return
        else:
            # 缩放手柄：使用场景坐标计算位移，再投影回本地坐标轴，
            # 避免旋转后 item 本地坐标系与屏幕方向不一致导致的"不跟手"问题。
            #
            # 原来直接用 event.pos() - _drag_start（本地坐标差），
            # 旋转后本地 X/Y 轴与屏幕 X/Y 轴不一致，导致边线拖拽有非预期偏移。
            #
            # 现在将场景坐标位移按 item 的旋转角度反旋转到本地坐标系，
            # 保证 场景水平位移 → 本地 X 轴位移，场景垂直位移 → 本地 Y 轴位移。
            sd = event.scenePos() - self._drag_start_scene
            angle_rad = math.radians(self.rotation())
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            local_dx = sd.x() * cos_a + sd.y() * sin_a
            local_dy = -sd.x() * sin_a + sd.y() * cos_a
            if HandlePosition.LEFT in self._drag_handle:
                new_rect.setLeft(self._drag_rect.left() + local_dx)
            if HandlePosition.RIGHT in self._drag_handle:
                new_rect.setRight(self._drag_rect.right() + local_dx)
            if HandlePosition.TOP in self._drag_handle:
                new_rect.setTop(self._drag_rect.top() + local_dy)
            if HandlePosition.BOTTOM in self._drag_handle:
                new_rect.setBottom(self._drag_rect.bottom() + local_dy)

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
        self._py_rect = new_rect  # Python 端同步缓存，确保 sync 使用正确值
        self._setup_transform_origin()  # 立即更新旋转枢轴，防止旋转偏移累积
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
