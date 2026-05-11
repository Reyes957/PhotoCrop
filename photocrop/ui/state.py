"""
AppState — 全局状态管理器（Single Source of Truth）

所有 UI 组件和 Controller 通过订阅 AppState 的信号来响应数据变化，
而不是直接访问 MainWindow 的内部 dict。这消除了 MainWindow 作为
"中间人"的必要性，为架构重构提供基础设施。

SessionState: 单个图像/PDF Session 的完整状态快照。
AppState: 全局 Observable 状态容器，管理所有 Session 和 UI 状态。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PIL import Image
from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from photocrop.utils.crop_rect import CropRect


@dataclass
class SessionState:
    """单个图像/PDF Session 的完整状态

    与 ImageSession（session.py）的区别：
    - ImageSession 是 MainWindow 内部使用的会话对象，含 LRU 页面缓存
    - SessionState 是 AppState 管理的全局状态快照，供所有 Controller 共享
    """

    key: str                                    # 唯一标识（文件路径或路径+页码）
    source_path: Path                           # 原始文件路径
    source_image: Image.Image                   # 当前显示的图像（PIL）
    crop_rects: list[CropRect] = field(default_factory=list)  # 当前页面的裁剪框
    undo_snapshot: list = field(default_factory=list)         # UndoManager.serialize() 结果
    is_pdf: bool = False
    page_count: int = 1
    current_page: int = 0
    page_crop_rects: dict[int, list[CropRect]] = field(default_factory=dict)   # page_idx -> list[CropRect]
    page_undo_snapshots: dict[int, list] = field(default_factory=dict)         # page_idx -> bytes/serialized
    page_thumbnails: list[Image.Image] = field(default_factory=list)           # list[Image.Image]
    pdf_page_loader: Callable[[int], Image.Image] | None = None  # 由 SessionController 注入

    # 内部页面缓存（与 ImageSession 兼容）
    _page_cache: dict[int, Image.Image] = field(default_factory=dict, repr=False)
    _cache_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def current_pdf_page(self) -> int:
        """与 ImageSession.current_pdf_page 兼容的别名"""
        return self.current_page

    @current_pdf_page.setter
    def current_pdf_page(self, value: int) -> None:
        self.current_page = value

    def get_page_image(self, page_idx: int) -> Image.Image:
        """按需加载 PDF 页面图像（LRU 缓存，默认保留最近 5 页）

        与 ImageSession.get_page_image() 接口兼容。
        """
        with self._cache_lock:
            if page_idx in self._page_cache:
                return self._page_cache[page_idx]

        if not self.pdf_page_loader:
            raise RuntimeError("PDF page loader not set")
        img = self.pdf_page_loader(page_idx)

        with self._cache_lock:
            # LRU 淘汰：缓存满时删除最早插入的
            if len(self._page_cache) >= 5:
                oldest = next(iter(self._page_cache))
                del self._page_cache[oldest]
            self._page_cache[page_idx] = img
        return img


class AppState(QObject):
    """全局状态管理器 — 唯一真相源（Observable 模式）

    所有 Controller 和 UI 组件通过连接 AppState 的信号来响应变化，
    而不是直接互相调用。这消除了 MainWindow 作为"中间人"的必要性。

    信号分组：
    - Session 生命周期：添加/移除/切换 Session
    - 数据变化：裁剪框、页面切换
    - 流程状态：检测/导出进度
    - UI 状态：主题/视图/缩放/状态栏消息
    """

    # ---- Session 生命周期 ----
    session_added = Signal(str)                # key
    session_removed = Signal(str)              # key
    current_session_changed = Signal(str)      # key（空字符串表示无当前 session）

    # ---- 数据变化 ----
    crop_rects_changed = Signal(str)           # key（哪个 session 的裁剪框变了）
    page_changed = Signal(str, int)            # key, page_idx

    # ---- 流程状态 ----
    detection_progress = Signal(int, int)      # done, total
    detection_finished = Signal(str, int)      # key, total_rects
    export_progress = Signal(int, int)         # done, total
    export_finished = Signal(int, list)        # success_count, errors

    # ---- UI 状态 ----
    theme_changed = Signal()
    view_mode_changed = Signal(int)            # 0=Empty, 1=Grid, 2=Single
    zoom_changed = Signal(float)
    status_message = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, SessionState] = {}
        self._current_key: str | None = None
        self._theme_mode: str = "light"
        self._view_mode: int = 0
        self._zoom: float = 1.0

    # ================================================================
    # Session CRUD
    # ================================================================

    def add_session(self, state: SessionState) -> None:
        """注册新 Session 并通知订阅者"""
        self._sessions[state.key] = state
        self.session_added.emit(state.key)

    def remove_session(self, key: str) -> None:
        """移除 Session；若为当前 Session 则清空选中"""
        if key in self._sessions:
            del self._sessions[key]
            self.session_removed.emit(key)
            if self._current_key == key:
                self._current_key = None
                self.current_session_changed.emit("")

    def set_current(self, key: str) -> None:
        """切换当前活跃 Session"""
        if key != self._current_key:
            self._current_key = key
            self.current_session_changed.emit(key or "")

    def update_crop_rects(self, key: str, rects: list[CropRect]) -> None:
        """更新指定 Session 的裁剪框列表并通知"""
        if key in self._sessions:
            sess = self._sessions[key]
            if sess.is_pdf:
                sess.page_crop_rects[sess.current_page] = rects
            else:
                sess.crop_rects = rects
            self.crop_rects_changed.emit(key)

    def update_page(self, key: str, page_idx: int) -> None:
        """更新 PDF Session 的当前页码并通知"""
        if key in self._sessions:
            sess = self._sessions[key]
            sess.current_page = page_idx
            self.page_changed.emit(key, page_idx)

    # ================================================================
    # 查询
    # ================================================================

    @property
    def current_session(self) -> SessionState | None:
        """获取当前 Session。

        如果当前 key 是 PDF 页面 key（如 test.pdf##PAGE##0），
        自动回退到父 Session（test.pdf）。
        """
        if not self._current_key:
            return None

        # 直接匹配（普通图片或 PDF 父 key）
        sess = self._sessions.get(self._current_key)
        if sess:
            return sess

        # 页面 key 回退到父 Session
        parsed = self.parse_page_key(self._current_key)
        if parsed:
            return self._sessions.get(parsed[0])

        return None

    def get_session(self, key: str) -> SessionState | None:
        """按 key 获取 Session"""
        return self._sessions.get(key)

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def total_crop_count(self) -> int:
        """所有 Session 的裁剪框总数"""
        count = 0
        for sess in self._sessions.values():
            if sess.is_pdf:
                for rects in sess.page_crop_rects.values():
                    count += len(rects)
            else:
                count += len(sess.crop_rects)
        return count

    def get_page_key(self, session_key: str, page_idx: int) -> str:
        """生成页面 key，使用 ##PAGE## 分隔符避免文件路径冲突

        替代原来的 ::page_ 分隔符（修复：文件路径含 ::page_ 时解析错误）。
        """
        return f"{session_key}##PAGE##{page_idx}"

    def parse_page_key(self, key: str) -> tuple[str, int] | None:
        """解析页面 key，返回 (session_key, page_idx) 或 None"""
        if "##PAGE##" not in key:
            return None
        parts = key.rsplit("##PAGE##", 1)
        return parts[0], int(parts[1])

    # ================================================================
    # 主题 / 视图 / 缩放
    # ================================================================

    @property
    def theme_mode(self) -> str:
        return self._theme_mode

    def set_theme_mode(self, mode: str) -> None:
        """设置主题模式（'light' / 'dark'）"""
        if mode != self._theme_mode:
            self._theme_mode = mode
            self.theme_changed.emit()

    @property
    def view_mode(self) -> int:
        return self._view_mode

    def set_view_mode(self, mode: int) -> None:
        """设置视图模式（0=Empty, 1=Grid, 2=Single）"""
        if mode != self._view_mode:
            self._view_mode = mode
            self.view_mode_changed.emit(mode)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        """设置缩放比例"""
        if zoom != self._zoom:
            self._zoom = zoom
            self.zoom_changed.emit(zoom)
