"""
DetectionController — 检测流程控制器

将检测逻辑从 MainWindow 中剥离。管理单图检测和批量 PDF 检测，
包括后台线程（QThreadPool）和取消机制。

职责：
- 单图检测：委托 canvas.detect()（它已处理 clear + add + undo）
- 批量 PDF 检测：管理后台线程，通过信号通知 UI 进度
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from photocrop.engine.core import detect_rectangles
from photocrop.ui.state import AppState
from photocrop.utils.crop_rect import CropRect

if TYPE_CHECKING:
    from photocrop.ui.canvas import CropCanvas


# ============================================================
# 批量检测后台任务
# ============================================================

class PageDetectionSignals(QObject):
    """检测任务信号 — 跨线程通信"""
    page_done = Signal(int, list)    # page_idx, rects
    error = Signal(str)              # error_msg


class PageDetectionTask(QRunnable):
    """单页检测后台任务"""

    def __init__(self, page_idx: int, page_img: Image.Image,
                 detector: str, max_count: int):
        super().__init__()
        self.page_idx = page_idx
        self.page_img = page_img.copy()
        self.detector = detector
        self.max_count = max_count
        self.signals = PageDetectionSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._cancelled:
            return
        try:
            rects = detect_rectangles(
                self.page_img, detector=self.detector,
                max_count=self.max_count,
            )
            self.signals.page_done.emit(self.page_idx, rects)
        except Exception as e:
            self.signals.error.emit(f"Page {self.page_idx}: {e}")
            self.signals.page_done.emit(self.page_idx, [])


# ============================================================
# DetectionController
# ============================================================

class DetectionController(QObject):
    """检测流程控制器 — 管理单图检测和批量 PDF 检测

    单图检测委托 canvas.detect()（它已处理 clear + add_rect + push_undo）。
    批量检测管理后台线程，通过 page_done 信号逐步通知 UI 更新。
    """

    # 批量检测信号
    batch_page_done = Signal(str, int, list)  # session_key, page_idx, rects
    batch_progress = Signal(int, int)         # done, total
    batch_finished = Signal(str, int)         # session_key, total_rects
    batch_error = Signal(str)                 # error_msg

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self._state = app_state
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(1)  # 串行检测，避免资源竞争
        self._tasks: list[PageDetectionTask] = []
        self._cancelled = False
        self._detected_pages: set[int] = set()

    # ---- 单图检测 ----

    def detect_current(self, detector: str, max_count: int,
                       canvas: CropCanvas) -> int:
        """检测当前 Session 的当前页面

        委托 canvas.detect() 执行（它已处理 clear_crops + add_crop_rect + push_undo）。

        Returns:
            检测到的裁剪框数量
        """
        return canvas.detect(detector=detector, max_count=max_count)

    # ---- 批量 PDF 检测 ----

    def detect_all_pages(self, session_key: str, detector: str,
                         max_count: int) -> None:
        """批量检测 PDF 所有页面（后台线程）

        通过 batch_page_done / batch_progress / batch_finished 信号通知 UI。
        MainWindow 负责连接这些信号来更新 extracted_panel 和 image_list。

        Args:
            session_key: PDF Session 的 key（文件路径）
            detector: 检测器名称
            max_count: 最大检测数量
        """
        sess = self._state.get_session(session_key)
        if not sess or not sess.is_pdf:
            return

        total = sess.page_count
        self._cancelled = False
        self._detected_pages.clear()
        self._tasks.clear()

        # 清空旧结果
        for i in range(total):
            sess.page_crop_rects[i] = []

        def on_page_done(page_idx: int, rects: list) -> None:
            """单页检测完成 — 存储结果并通知 UI"""
            if self._cancelled:
                return
            crop_rects = [r for r in rects if isinstance(r, CropRect)]
            sess.page_crop_rects[page_idx] = crop_rects
            self._detected_pages.add(page_idx)
            # 通知 MainWindow 更新 extracted_panel 和 image_list
            self.batch_page_done.emit(session_key, page_idx, crop_rects)
            self.batch_progress.emit(len(self._detected_pages), total)

        def on_error(msg: str) -> None:
            self.batch_error.emit(msg)

        # 创建并启动所有任务
        for page_idx in range(total):
            try:
                img = sess.get_page_image(page_idx)
            except (RuntimeError, IndexError):
                self._detected_pages.add(page_idx)
                continue

            task = PageDetectionTask(page_idx, img, detector, max_count)
            task.signals.page_done.connect(on_page_done)
            task.signals.error.connect(on_error)
            self._tasks.append(task)
            self._pool.start(task)

        # 进度检查定时器 — 等待所有任务完成
        def check_progress() -> None:
            if self._cancelled:
                return
            done = len(self._detected_pages)
            if done < total:
                QTimer.singleShot(100, check_progress)
            else:
                total_rects = sum(
                    len(sess.page_crop_rects.get(i, []))
                    for i in range(total)
                )
                self.batch_finished.emit(session_key, total_rects)

        QTimer.singleShot(100, check_progress)

    def cancel(self) -> None:
        """取消正在进行的批量检测"""
        self._cancelled = True
        for task in self._tasks:
            task.cancel()

    @property
    def is_running(self) -> bool:
        """是否有批量检测任务在运行"""
        return len(self._detected_pages) < len(self._tasks) and not self._cancelled
