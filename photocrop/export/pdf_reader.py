from __future__ import annotations

"""
PDF 读取模块 — 将 PDF 页面渲染为 PIL Image

依赖 PyMuPDF（fitz），在 project_rules.md §1 中列为 v0.3 依赖。
"""

from pathlib import Path

from PIL import Image


def pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 200,
) -> list[tuple[int, Image.Image]]:
    """将 PDF 的每一页渲染为 PIL Image

    Args:
        pdf_path: PDF 文件路径
        dpi: 渲染分辨率（默认 200）

    Returns:
        [(page_num, Image), ...] — 页码从 0 开始
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as err:
        raise ImportError(
            "PyMuPDF 未安装。请运行: pip install PyMuPDF"
        ) from err

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    images: list[tuple[int, Image.Image]] = []

    doc = fitz.open(str(pdf_path))
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append((page_num, img))
    finally:
        doc.close()

    return images
