#!/usr/bin/env python3
from __future__ import annotations

"""
PhotoCrop — 从扫描页面中检测并裁剪照片

用法:
    # CLI 模式
    python -m photocrop.main <image_path>
    python -m photocrop.main page.jpg --max-count 4

    # GUI 模式
    python -m photocrop.main --gui
    python -m photocrop.main --gui page.jpg

    # PDF 批量模式
    python -m photocrop.main --pdf album.pdf --output ./out/
"""

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photocrop",
        description="PhotoCrop — 从扫描页面中检测并裁剪照片",
    )
    parser.add_argument(
        "image",
        type=Path,
        nargs="?",
        help="输入图片路径（JPEG / PNG 等常见格式）",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="启动图形界面",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        help="输入 PDF 文件路径（批量处理模式）",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output"),
        help="输出目录（默认 output/）",
    )
    parser.add_argument(
        "--max-count",
        type=int,
        default=4,
        help="最大检测数量（默认 4）",
    )
    parser.add_argument(
        "--min-width",
        type=float,
        default=100,
        help="最小宽度阈值（默认 100px）",
    )
    parser.add_argument(
        "--min-height",
        type=float,
        default=100,
        help="最小高度阈值（默认 100px）",
    )
    parser.add_argument(
        "--detector",
        type=str,
        default="enhanced-cv",
        choices=["cv", "enhanced-cv", "combined", "yolo-world", "model"],
        help="检测器类型（默认 enhanced-cv）",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="禁用 fallback（无检测结果时返回空列表而非整页）",
    )
    parser.add_argument(
        "--no-auto-rotate",
        action="store_true",
        help="禁用自动旋转",
    )
    parser.add_argument(
        "--no-trim",
        action="store_true",
        help="禁用去白边",
    )
    return parser


# ============================================================
# CLI 模式
# ============================================================

def run_cli(args) -> int:
    """CLI 模式：单张图片检测 + 输出摘要"""
    from photocrop.engine.core import detect_rectangles, summarize

    if not args.image:
        print("错误：CLI 模式需要指定图片路径", file=sys.stderr)
        return 1

    if not args.image.exists():
        print(f"错误：文件不存在 — {args.image}", file=sys.stderr)
        return 1

    try:
        img = Image.open(args.image)
    except (OSError, ValueError) as e:
        print(f"错误：无法打开图片 — {e}", file=sys.stderr)
        return 1

    if img.mode not in ("RGB", "L", "RGBA"):
        img = img.convert("RGB")

    rects = detect_rectangles(
        img,
        detector=args.detector,
        max_count=args.max_count,
        min_width=args.min_width,
        min_height=args.min_height,
        apply_fallback=not args.no_fallback,
    )

    print(summarize(rects))
    return 0


# ============================================================
# GUI 模式
# ============================================================

def run_gui(args) -> int:
    """GUI 模式：启动 PySide6 界面"""
    # 抑制 macOS IMK "mach port" 警告（系统级 stderr 输出，无法从应用层面消除）
    import platform, os
    _stderr_fd = None
    if platform.system() == "Darwin":
        _stderr_fd = os.dup(2)
        os.dup2(os.open(os.devnull, os.O_WRONLY), 2)

    # 抑制 Qt 的 qt.qpa.keymapper Cocoa/Carbon 不匹配警告（macOS PySide6 已知问题）
    _qt_rules = os.environ.get("QT_LOGGING_RULES", "")
    if "qt.qpa.keymapper" not in _qt_rules:
        if _qt_rules and not _qt_rules.endswith(";"):
            _qt_rules += ";"
        os.environ["QT_LOGGING_RULES"] = _qt_rules + "qt.qpa.keymapper=false"

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("错误：PySide6 未安装。请运行: pip install PySide6", file=sys.stderr)
        return 1

    from photocrop.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    # 恢复 stderr
    if _stderr_fd is not None:
        os.dup2(_stderr_fd, 2)
        os.close(_stderr_fd)
    app.setApplicationName("PhotoCrop")
    from photocrop import __version__
    app.setApplicationVersion(__version__)

    window = MainWindow()
    window.show()

    # 如果命令行指定了图片，自动加载（通过 session 创建流程）
    if args.image and args.image.exists():
        window._load_single_file(str(args.image))

    return app.exec()


# ============================================================
# PDF 批量模式
# ============================================================

def run_pdf(args) -> int:
    """PDF 批量模式：读取 PDF，逐页检测并导出"""
    from photocrop.engine.core import detect_rectangles
    from photocrop.export.cropper import export_photo
    from photocrop.export.pdf_reader import pdf_to_images

    if not args.pdf or not args.pdf.exists():
        print(f"错误：PDF 文件不存在 — {args.pdf}", file=sys.stderr)
        return 1

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        pages = pdf_to_images(args.pdf, dpi=200)
    except ImportError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    pdf_stem = args.pdf.stem
    total_pages = len(pages)
    total_exported = 0

    for page_num, page_img in pages:
        print(f"\r处理中: 第 {page_num + 1}/{total_pages} 页...", end="", flush=True)
        rects = detect_rectangles(
            page_img,
            detector=args.detector,
            max_count=args.max_count,
            min_width=args.min_width,
            min_height=args.min_height,
            apply_fallback=not args.no_fallback,
        )

        for i, rect in enumerate(rects):
            out_name = f"{pdf_stem}_p{page_num + 1}_{i + 1:02d}.jpg"
            out_path = output_dir / out_name

            try:
                export_photo(
                    page_img,
                    rect,
                    out_path,
                    auto_rotate=not args.no_auto_rotate,
                    trim_white=not args.no_trim,
                )
                total_exported += 1
            except (OSError, ValueError, RuntimeError) as e:
                print(f"导出失败 {out_name}: {e}", file=sys.stderr)

    print(f"\n完成: 共导出 {total_exported} 张照片到 {output_dir}")
    return 0


# ============================================================
# 主入口
# ============================================================

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )

    if args.gui:
        return run_gui(args)
    elif args.pdf:
        return run_pdf(args)
    else:
        return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
