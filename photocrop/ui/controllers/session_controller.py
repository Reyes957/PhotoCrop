"""
SessionController — Session 生命周期管理

负责文件加载、页面切换、Session 保存/恢复、销毁。

核心原则：
- PDF 文件只打开一次 fitz.Document，缩略图和高清图共用同一句柄
- 所有页面 key 使用 AppState.get_page_key() 生成，统一为 ##PAGE## 分隔符
- MainWindow 不再直接操作 _sessions dict，而是通过 AppState + 本 Controller 操作
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, Signal

from photocrop.ui.state import AppState, SessionState

if TYPE_CHECKING:
    pass


class SessionController(QObject):
    """Session 生命周期管理 — 负责文件加载、页面切换、Session 保存/恢复、销毁

    与 AppState 配合使用：
    - SessionController 负责"怎么做"（加载文件、生成缩略图、管理 PDF 句柄）
    - AppState 负责"存什么"（Session 数据、信号分发）
    """

    load_error = Signal(str, str)      # path, error_msg
    session_loaded = Signal(str)       # key
    page_switched = Signal(str, int)   # key, page_idx

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self._state = app_state
        self._pdf_docs: dict[str, object] = {}  # path_str -> fitz.Document

    # ================================================================
    # 加载
    # ================================================================

    def load_file(self, path_str: str) -> SessionState | None:
        """加载单个文件（图片或 PDF），返回 SessionState

        不自动注册到 AppState —— 由调用方（MainWindow._on_load）决定。
        """
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".pdf":
                return self._load_pdf(path)
            else:
                return self._load_image(path)
        except Exception as e:
            self.load_error.emit(str(path), str(e))
            return None

    def _load_image(self, path: Path) -> SessionState:
        """加载普通图片，返回 SessionState"""
        img = Image.open(path)
        # EXIF 方向校正 — 自动旋转至正确方向
        from PIL import ImageOps
        try:
            img = ImageOps.exif_transpose(img)
        except (AttributeError, KeyError, TypeError):
            pass  # 无 EXIF 数据或格式不支持
        # 统一转换（灰度/RGBA 保留，其他模式转 RGB）
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")

        # 生成缩略图用于左侧列表
        thumb = img.copy()
        thumb.thumbnail((100, 100), Image.Resampling.LANCZOS)

        sess = SessionState(
            key=str(path),
            source_path=path,
            source_image=img,
            crop_rects=[],
            is_pdf=False,
            page_count=1,
        )
        sess.page_thumbnails = [thumb]
        return sess

    def _load_pdf(self, path: Path) -> SessionState:
        """加载 PDF — 只打开一次 fitz.Document，缩略图和高清图共用句柄

        修复：原 MainWindow._load_single_file() 中 pdf_to_images(dpi=72) 和
        fitz.open() 分别打开两次同一文件，导致内存翻倍。现在只打开一次。
        """
        import fitz

        doc = fitz.open(str(path))
        self._pdf_docs[str(path)] = doc

        page_count = len(doc)

        # 生成第一页高清图（200dpi）
        zoom_hd = 200 / 72.0
        pix_hd = doc[0].get_pixmap(matrix=fitz.Matrix(zoom_hd, zoom_hd))
        first_page = Image.frombytes("RGB", (pix_hd.width, pix_hd.height), pix_hd.samples)

        # 生成所有页面缩略图（72dpi）
        page_thumbs: list[Image.Image] = []
        for i in range(page_count):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(1, 1))
            t = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            t.thumbnail((44, 44), Image.Resampling.LANCZOS)
            page_thumbs.append(t)

        # 高清页面加载器 — 复用已打开的 doc
        def page_loader(idx: int) -> Image.Image:
            if str(path) not in self._pdf_docs:
                self._pdf_docs[str(path)] = fitz.open(str(path))
            doc_ref = self._pdf_docs[str(path)]
            z = 200 / 72.0
            p = doc_ref[idx].get_pixmap(matrix=fitz.Matrix(z, z))
            return Image.frombytes("RGB", (p.width, p.height), p.samples)

        sess = SessionState(
            key=str(path),
            source_path=path,
            source_image=first_page,
            crop_rects=[],
            is_pdf=True,
            page_count=page_count,
            pdf_page_loader=page_loader,
        )
        sess.page_thumbnails = page_thumbs
        return sess

    # ================================================================
    # 保存 / 恢复
    # ================================================================

    def save_current_state(self, canvas_crop_rects: list, undo_snapshot: list) -> None:
        """将当前 Canvas 的状态保存到当前 Session 中

        Args:
            canvas_crop_rects: canvas.crop_rects（当前页面的裁剪框列表）
            undo_snapshot: canvas._undo_manager.serialize() 的结果
        """
        sess = self._state.current_session
        if not sess:
            return

        if sess.is_pdf:
            sess.page_crop_rects[sess.current_page] = [copy.deepcopy(r) for r in canvas_crop_rects]
            sess.page_undo_snapshots[sess.current_page] = undo_snapshot
        else:
            sess.crop_rects = [copy.deepcopy(r) for r in canvas_crop_rects]
            sess.undo_snapshot = undo_snapshot

    def restore_session(self, key: str, canvas: object, undo_manager: object) -> bool:
        """恢复指定 Session 到 Canvas 中

        Args:
            key: Session key（图片路径或 PDF 页面 key，如 "file.pdf##PAGE##0"）
            canvas: CropCanvas 实例（需要 load_pil_image / _restore_rects 方法）
            undo_manager: UndoManager 实例（需要 deserialize / clear / push_state 方法）

        Returns:
            是否成功恢复
        """
        # 解析是否是 PDF 页面 key
        parsed = self._state.parse_page_key(key)

        if parsed:
            pdf_key, page_idx = parsed
            sess = self._state.get_session(pdf_key)
            if not sess or not sess.is_pdf:
                return False

            # 切换页面
            sess.current_page = page_idx
            img = sess.pdf_page_loader(page_idx) if sess.pdf_page_loader else sess.source_image
            page_rects = list(sess.page_crop_rects.get(page_idx, []))
            page_undo = sess.page_undo_snapshots.get(page_idx)

            canvas.load_pil_image(img)
            canvas._restore_rects(page_rects)
            if page_undo is not None:
                undo_manager.deserialize(page_undo)
            else:
                undo_manager.clear()
                undo_manager.push_state([])

            self._state.set_current(key)
            self.page_switched.emit(pdf_key, page_idx)
            return True

        # 普通图片 Session
        sess = self._state.get_session(key)
        if not sess:
            return False

        canvas.load_pil_image(sess.source_image)
        undo_manager.deserialize(sess.undo_snapshot)
        canvas._restore_rects(list(sess.crop_rects))

        self._state.set_current(key)
        return True

    # ================================================================
    # 切换页面
    # ================================================================

    def switch_page(self, session_key: str, page_idx: int,
                    canvas: object, undo_manager: object) -> Image.Image | None:
        """在同一 PDF Session 内切换页面

        先保存当前页面状态，再加载目标页面。
        """
        sess = self._state.get_session(session_key)
        if not sess or not sess.is_pdf:
            return None
        if page_idx < 0 or page_idx >= sess.page_count:
            return None

        # 保存当前页面
        current_page = sess.current_page
        sess.page_crop_rects[current_page] = [copy.deepcopy(r) for r in canvas.crop_rects]
        sess.page_undo_snapshots[current_page] = undo_manager.serialize()

        # 加载目标页面
        sess.current_page = page_idx
        img = sess.pdf_page_loader(page_idx) if sess.pdf_page_loader else sess.source_image
        page_rects = list(sess.page_crop_rects.get(page_idx, []))
        page_undo = sess.page_undo_snapshots.get(page_idx)

        canvas.load_pil_image(img)
        canvas._restore_rects(page_rects)
        if page_undo is not None:
            undo_manager.deserialize(page_undo)
        else:
            undo_manager.clear()
            undo_manager.push_state([])

        new_key = self._state.get_page_key(session_key, page_idx)
        self._state.set_current(new_key)
        self.page_switched.emit(session_key, page_idx)
        return img

    # ================================================================
    # 页面导航
    # ================================================================

    def get_sibling_page_key(self, current_key: str, offset: int) -> str | None:
        """获取当前页面的相邻页面 key

        Args:
            current_key: 当前页面 key（可能是 PDF 页面 key 或普通图片 key）
            offset: 偏移量（-1=上一页, +1=下一页）

        Returns:
            相邻页面的 key，超出范围返回 None
        """
        parsed = self._state.parse_page_key(current_key)
        if not parsed:
            return None
        pdf_key, page_idx = parsed
        new_idx = page_idx + offset
        sess = self._state.get_session(pdf_key)
        if not sess or new_idx < 0 or new_idx >= sess.page_count:
            return None
        return self._state.get_page_key(pdf_key, new_idx)

    # ================================================================
    # 删除
    # ================================================================

    def remove_session(self, key: str) -> str | None:
        """删除 Session，返回下一个应选中的 key（或 None 表示回到空状态）

        Args:
            key: 要删除的 key（可能是 PDF 页面 key 或普通图片 key）
        """
        parsed = self._state.parse_page_key(key)
        session_key = parsed[0] if parsed else key

        if not self._state.get_session(session_key):
            return None

        sess = self._state.get_session(session_key)

        # 清理 PDF 句柄
        if sess and sess.is_pdf and str(sess.source_path) in self._pdf_docs:
            self._pdf_docs[str(sess.source_path)].close()
            del self._pdf_docs[str(sess.source_path)]

        # 确定下一个选中的 key
        keys = list(self._state._sessions.keys())
        if session_key in keys:
            idx = keys.index(session_key)
            next_key: str | None = None
            if len(keys) > 1:
                next_idx = idx - 1 if idx > 0 else 1
                next_sess = self._state.get_session(keys[next_idx])
                if next_sess and next_sess.is_pdf:
                    next_key = self._state.get_page_key(keys[next_idx], 0)
                else:
                    next_key = keys[next_idx]

            self._state.remove_session(session_key)
            return next_key

        self._state.remove_session(session_key)
        return None

    # ================================================================
    # 查询
    # ================================================================

    def get_current_pdf_session(self) -> SessionState | None:
        """获取当前 key 所属的 PDF Session（如果是 PDF 页面的话）

        用于判断当前是否在编辑 PDF 页面，以及获取 PDF Session 的元数据。
        """
        current = self._state.current_session
        if current and current.is_pdf:
            return current

        # 当前可能是页面 key，需要查找父 Session
        key = self._state._current_key
        if key:
            parsed = self._state.parse_page_key(key)
            if parsed:
                return self._state.get_session(parsed[0])
        return None

    def get_crop_counts(self) -> tuple[int, int]:
        """返回 (session_count, total_crop_count)"""
        return self._state.session_count, self._state.total_crop_count

    def get_page_crop_count(self, session_key: str, page_idx: int) -> int:
        """获取指定 PDF 页面的裁剪框数量"""
        sess = self._state.get_session(session_key)
        if not sess or not sess.is_pdf:
            return 0
        return len(sess.page_crop_rects.get(page_idx, []))

    def get_session_crop_count(self, key: str) -> int:
        """获取指定 Session 的总裁剪框数量（PDF 累加所有页面）"""
        sess = self._state.get_session(key)
        if not sess:
            return 0
        if sess.is_pdf:
            return sum(len(r) for r in sess.page_crop_rects.values())
        return len(sess.crop_rects)

    # ================================================================
    # 清理
    # ================================================================

    def close_all(self) -> None:
        """关闭所有 PDF 文档句柄，释放资源"""
        for doc in self._pdf_docs.values():
            if hasattr(doc, 'close'):
                doc.close()
        self._pdf_docs.clear()
