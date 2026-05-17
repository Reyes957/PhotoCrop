"""
ExportController — 导出流程控制器

将导出逻辑从 MainWindow 中剥离。负责模板填充、单页导出、全部导出、
错误收集和进度反馈。

职责：
- 模板填充和文件名生成（_fill_template）
- 单页导出和全部导出
- 进度信号通知 UI
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from photocrop.export.cropper import export_photo
from photocrop.ui.state import AppState

if TYPE_CHECKING:
    from photocrop.ui.canvas import CropCanvas


class ExportController(QObject):
    """导出流程控制器 — 管理单页导出和全部导出

    MainWindow 只负责弹出 ExportDialog 和显示结果，
    实际导出逻辑全部在本 Controller 中。
    """

    export_progress = Signal(int, int)      # done, total
    export_finished = Signal(int, list)     # success_count, errors

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self._state = app_state

    def export(self, config: dict, canvas: CropCanvas) -> tuple[int, list[str]]:
        """执行导出

        Args:
            config: ExportDialog.get_export_config() 返回的配置字典
            canvas: CropCanvas 实例（获取当前页面的裁剪框和图像）

        Returns:
            (成功导出数量, 错误列表)
        """
        output_dir = Path(config["output_dir"])
        suffix = config["suffix"]
        quality = config["quality"]
        max_w = config.get("max_width")
        max_h = config.get("max_height")
        auto_rotate = config["auto_rotate"]
        trim_white = config["trim_white"]
        template = config.get("template", "{name}_p{page}_{index:02d}.{ext}")
        scope = config["scope"]

        exported = 0
        errors: list[str] = []
        total = self.count_total_rects(scope, canvas)
        current = 0

        if scope == "page":
            exported, errors, current = self._export_page(
                canvas, output_dir, suffix, quality, max_w, max_h,
                auto_rotate, trim_white, template, current, total,
            )
        else:
            exported, errors, current = self._export_all_sessions(
                canvas, output_dir, suffix, quality, max_w, max_h,
                auto_rotate, trim_white, template, current, total,
            )

        self.export_finished.emit(exported, errors)
        return exported, errors

    def _export_page(self, canvas: CropCanvas, output_dir: Path,
                     suffix: str, quality: int, max_w: int | None,
                     max_h: int | None, auto_rotate: bool, trim_white: bool,
                     template: str, current: int, total: int,
                     ) -> tuple[int, list[str], int]:
        """导出当前页面"""
        exported = 0
        errors: list[str] = []

        rects = canvas.crop_rects
        source_img = canvas.source_image
        for i, r in enumerate(rects):
            print(f"[DIAG EXPORT] rect[{i}] angle={r.rotation_angle:.2f} w={r.width:.0f} h={r.height:.0f}")

        if not rects or source_img is None:
            return 0, [], current

        sess = self._state.current_session
        source_name = "image"
        page_num = 1

        if sess:
            source_name = sess.source_path.stem
            if sess.is_pdf:
                page_num = sess.current_page + 1

        for i, rect in enumerate(rects):
            current += 1
            out_name = self._fill_template(
                template, source_name, page_num,
                i + 1, suffix.lstrip("."),
            )
            out_path = output_dir / out_name
            try:
                export_photo(
                    source_img, rect, out_path,
                    auto_rotate=auto_rotate, trim_white=trim_white,
                    quality=quality, max_width=max_w, max_height=max_h,
                )
                exported += 1
            except (ValueError, RuntimeError, OSError) as e:
                errors.append(f"#{i + 1}: {e}")
            self.export_progress.emit(current, total)

        return exported, errors, current

    def _export_all_sessions(
        self, canvas: CropCanvas, output_dir: Path,
        suffix: str, quality: int, max_w: int | None,
        max_h: int | None, auto_rotate: bool, trim_white: bool,
        template: str, current: int, total: int,
    ) -> tuple[int, list[str], int]:
        """导出所有 Session"""
        exported = 0
        errors: list[str] = []
        export_kw = dict(
            auto_rotate=auto_rotate, trim_white=trim_white,
            quality=quality, max_width=max_w, max_height=max_h,
        )

        for key, sess in self._state._sessions.items():
            source_name = sess.source_path.stem

            if sess.is_pdf:
                for page_idx in range(sess.page_count):
                    rects = sess.page_crop_rects.get(page_idx, [])
                    if not rects:
                        continue
                    try:
                        source_img = sess.get_page_image(page_idx)
                    except (RuntimeError, IndexError, OSError):
                        continue

                    for i, rect in enumerate(rects):
                        current += 1
                        out_name = self._fill_template(
                            template, source_name, page_idx + 1,
                            i + 1, suffix.lstrip("."),
                        )
                        out_path = output_dir / out_name
                        try:
                            export_photo(source_img, rect, out_path, **export_kw)
                            exported += 1
                        except (ValueError, RuntimeError, OSError) as e:
                            errors.append(f"{source_name} p{page_idx + 1} #{i + 1}: {e}")
                        self.export_progress.emit(current, total)
            else:
                if key == self._state._current_key:
                    rects = canvas.crop_rects
                    source_img = canvas.source_image
                else:
                    rects = sess.crop_rects
                    source_img = sess.source_image

                if not rects:
                    continue

                for i, rect in enumerate(rects):
                    current += 1
                    out_name = self._fill_template(
                        template, source_name, 1, i + 1, suffix.lstrip("."),
                    )
                    out_path = output_dir / out_name
                    try:
                        export_photo(source_img, rect, out_path, **export_kw)
                        exported += 1
                    except (ValueError, RuntimeError, OSError) as e:
                        errors.append(f"{source_name} #{i + 1}: {e}")
                    self.export_progress.emit(current, total)

        return exported, errors, current

    def count_total_rects(self, scope: str, canvas: CropCanvas) -> int:
        """计算总裁剪框数量（用于进度条）"""
        if scope == "page":
            return len(canvas.crop_rects)
        return self._state.total_crop_count

    @staticmethod
    def _fill_template(template: str, source_name: str,
                       page_num: int, index: int, ext: str) -> str:
        """填充导出模板

        支持的占位符：
        - {name}: 源文件名（不含扩展名）
        - {page}: 页码（从1开始）
        - {ext}: 扩展名
        - {index}: 裁剪框序号（从1开始）
        - {index:02d}: 带格式化的序号
        """
        _vars = {"name": source_name, "page": str(page_num), "ext": ext}

        def _replace(m: re.Match) -> str:
            key = m.group(1)
            fmt = m.group(2)
            if key == "index":
                return format(index, fmt or "d") if fmt else str(index)
            return _vars.get(key, m.group(0))

        out = re.sub(r'\{(\w+)(?::([^}]+))?\}', _replace, template)

        # 如果模板中没有 {index}，自动追加序号
        if "{index" not in template:
            if "." in out:
                base, dot_ext = out.rsplit(".", 1)
                out = f"{base}_{index:02d}.{dot_ext}"
            else:
                out = f"{out}_{index:02d}"

        return out
