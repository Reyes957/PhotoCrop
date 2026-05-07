"""
ImageSession — 单张图像的会话状态

用于多图像管理：保存/恢复每张图像的裁剪框、撤销历史、PDF 状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image

from photocrop.utils.crop_rect import CropRect


@dataclass
class ImageSession:
    """单张图像的完整会话状态"""

    source_path: Path
    source_image: Image.Image
    crop_rects: List[CropRect] = field(default_factory=list)
    undo_snapshot: list = field(default_factory=list)  # UndoManager.serialize() 的结果
    pdf_pages: list = field(default_factory=list)       # 如果是 PDF，存储所有页面
    current_pdf_page: int = 0
    is_pdf: bool = False
