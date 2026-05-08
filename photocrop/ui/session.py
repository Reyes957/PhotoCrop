"""
ImageSession — 单张图像的会话状态

用于多图像管理：保存/恢复每张图像的裁剪框、撤销历史、PDF 状态。
支持 PDF 多页按需加载（LRU 缓存，默认保留最近 5 页）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from photocrop.utils.crop_rect import CropRect


@dataclass
class ImageSession:
    """单张图像的完整会话状态"""

    source_path: Path
    source_image: Image.Image
    crop_rects: list[CropRect] = field(default_factory=list)
    undo_snapshot: list = field(default_factory=list)  # UndoManager.serialize() 的结果

    # PDF 多页支持
    is_pdf: bool = False
    pdf_page_count: int = 0
    pdf_page_loader: Callable[[int], Image.Image] | None = None
    page_crop_rects: dict[int, list[CropRect]] = field(default_factory=dict)
    page_undo_snapshots: dict[int, list] = field(default_factory=dict)
    current_pdf_page: int = 0
    _page_cache: dict[int, Image.Image] = field(default_factory=dict, repr=False)
    _page_preview_cache: dict[int, Image.Image] = field(default_factory=dict, repr=False)

    def get_page_image(self, page_idx: int) -> Image.Image:
        """按需加载 PDF 页面图像（LRU 缓存，默认保留最近 5 页）"""
        if page_idx in self._page_cache:
            return self._page_cache[page_idx]
        if not self.pdf_page_loader:
            raise RuntimeError("PDF page loader not set")
        img = self.pdf_page_loader(page_idx)
        # LRU 淘汰：缓存满时删除最早插入的
        if len(self._page_cache) >= 5:
            oldest = next(iter(self._page_cache))
            del self._page_cache[oldest]
        self._page_cache[page_idx] = img
        return img

    def clear_page_cache(self) -> None:
        """清除所有页面缓存"""
        self._page_cache.clear()

    def get_page_preview(self, page_idx: int) -> Image.Image | None:
        """获取页面预览图（小尺寸，用于全局预览面板，不淘汰）

        Returns None if not cached.
        """
        return self._page_preview_cache.get(page_idx)

    def set_page_preview(self, page_idx: int, img: Image.Image,
                         size: tuple[int, int] = (160, 160)) -> None:
        """缓存页面预览图"""
        preview = img.copy()
        preview.thumbnail(size, Image.Resampling.LANCZOS)
        self._page_preview_cache[page_idx] = preview

    @property
    def page_count(self) -> int:
        """总页数（PDF 为实际页数，单图为 1）"""
        return self.pdf_page_count if self.is_pdf else 1

    @property
    def all_crop_rects(self) -> list[CropRect]:
        """获取所有页面的裁剪框（带 page_num 标记）"""
        all_rects: list[CropRect] = []
        for page_idx in sorted(self.page_crop_rects.keys()):
            for rect in self.page_crop_rects[page_idx]:
                rc = CropRect(
                    x=rect.x, y=rect.y, width=rect.width,
                    height=rect.height, rotation_angle=rect.rotation_angle,
                    source_type=rect.source_type, page_num=page_idx,
                )
                all_rects.append(rc)
        return all_rects
