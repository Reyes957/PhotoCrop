from __future__ import annotations
"""
裁剪导出模块 — 单张照片裁剪 + 旋转 + 去白边

规范（project_rules.md §8）：
    导出顺序（强制）：
    1. 裁剪
    2. rotation
    3. auto_rotate（可选）
    4. 去白边

规范（project_rules.md §9）：
    JPEG → 白色填充
    PNG → 透明

规范（project_rules.md §10）：
    必须逐个处理，禁止批量占用
"""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from photocrop.engine.rotation_estimator import estimate_rotation_angle
from photocrop.utils.crop_rect import CropRect
from photocrop.utils.rotation import to_opencv_angle


# ============================================================
# 主导出函数
# ============================================================

def export_photo(
    source_img: Image.Image,
    rect: CropRect,
    output_path: str | Path,
    *,
    auto_rotate: bool = True,
    trim_white: bool = True,
    quality: int = 95,
    max_width: int = 0,
    max_height: int = 0,
) -> Path:
    """从源图像中裁剪并导出一张照片

    执行 project_rules.md §8 强制流程：
    裁剪 → rotation → auto_rotate（可选） → 去白边

    Args:
        source_img: 原始页面图像（PIL Image）
        rect: CropRect 裁剪区域（中心坐标）
        output_path: 输出文件路径（根据扩展名决定格式）
        auto_rotate: 是否自动旋转（默认 True）
        trim_white: 是否去除白边（默认 True）
        quality: JPEG 压缩质量（1-100）

    Returns:
        实际写入的文件路径（Path 对象）
    """
    output_path = Path(output_path)

    # ---- 步骤 1: 裁剪 ----
    cropped = _crop_image(source_img, rect)

    # ---- 步骤 2: rotation ----
    if rect.rotation_angle != 0.0:
        cropped = _apply_rotation(cropped, rect.rotation_angle)

    # ---- 步骤 3: auto_rotate（可选）----
    if auto_rotate:
        try:
            angle = estimate_rotation_angle(cropped)
            if angle != 0.0:
                cropped = _apply_rotation(cropped, angle)
        except (ValueError, RuntimeError, OSError):
            pass  # 自动旋转失败时跳过（不影响导出）

    # ---- 步骤 4: 去白边 ----
    if trim_white:
        cropped = _trim_white_border(cropped)

    # ---- 步骤 5: 尺寸限制 ----
    if max_width > 0 or max_height > 0:
        cropped = _resize_if_needed(cropped, max_width, max_height)

    # ---- 保存 ----
    _save_image(cropped, output_path, quality=quality)

    return output_path


# ============================================================
# 内部函数
# ============================================================

def _crop_image(source_img: Image.Image, rect: CropRect) -> Image.Image:
    """从源图像裁剪指定区域

    Args:
        source_img: 原始页面图像
        rect: CropRect 裁剪区域

    Returns:
        裁剪后的 PIL Image
    """
    box = rect.to_pixel_tuple()
    # 确保裁剪区域在图像范围内
    img_w, img_h = source_img.size
    x1 = max(0, box[0])
    y1 = max(0, box[1])
    x2 = min(img_w, box[2])
    y2 = min(img_h, box[3])

    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"裁剪区域无效: ({x1}, {y1}, {x2}, {y2})")

    return source_img.crop((x1, y1, x2, y2))


def _apply_rotation(img: Image.Image, angle: float) -> Image.Image:
    """对图像应用旋转

    Args:
        img: 输入图像
        angle: 顺时针旋转角度

    Returns:
        旋转后的图像
    """
    if angle == 0.0:
        return img

    # PIL 的 rotate 是逆时针为正，所以取负
    rotated = img.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    return rotated


def _trim_white_border(
    img: Image.Image,
    threshold: int = 240,
    padding: int = 2,
) -> Image.Image:
    """去除图像周围的白边

    Args:
        img: 输入图像
        threshold: 亮度阈值（0-255），高于此值视为白色
        padding: 保留的边距像素数

    Returns:
        去白边后的图像
    """
    arr = np.array(img.convert("L"))  # 转灰度

    # 找非白色区域
    mask = arr < threshold

    if not mask.any():
        return img  # 全白，返回原图

    # 找边界
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    r_min, r_max = np.where(rows)[0][[0, -1]]
    c_min, c_max = np.where(cols)[0][[0, -1]]

    # 加 padding
    r_min = max(0, r_min - padding)
    r_max = min(arr.shape[0] - 1, r_max + padding)
    c_min = max(0, c_min - padding)
    c_max = min(arr.shape[1] - 1, c_max + padding)

    return img.crop((c_min, r_min, c_max + 1, r_max + 1))


def _save_image(img: Image.Image, path: Path, quality: int = 95) -> None:
    """保存图像

    规范（project_rules.md §9）：
        JPEG → 白色填充
        PNG → 透明
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    suffix = path.suffix.lower()

    if suffix in (".jpg", ".jpeg"):
        # JPEG: 白色填充（不支持透明）
        if img.mode in ("RGBA", "LA", "PA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        exif_data = img.info.get("exif")
        if exif_data:
            img.save(str(path), "JPEG", quality=quality, exif=exif_data)
        else:
            img.save(str(path), "JPEG", quality=quality)

    elif suffix == ".png":
        # PNG: 保留透明通道
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.save(str(path), "PNG")

    elif suffix in (".tif", ".tiff"):
        # TIFF: LZW 压缩
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")
        exif_data = img.info.get("exif")
        if exif_data:
            img.save(str(path), "TIFF", compression="tiff_lzw", exif=exif_data)
        else:
            img.save(str(path), "TIFF", compression="tiff_lzw")

    else:
        # 默认按原格式保存
        img.save(str(path))


def _resize_if_needed(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """按最大宽高限制缩放图像（保持比例）"""
    if max_w <= 0 and max_h <= 0:
        return img
    w, h = img.size
    ratio = 1.0
    if max_w > 0 and w > max_w:
        ratio = min(ratio, max_w / w)
    if max_h > 0 and h > max_h:
        ratio = min(ratio, max_h / h)
    if ratio < 1.0:
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return img


def export_photo_to_memory(
    source_img: Image.Image,
    rect: CropRect,
    *,
    auto_rotate: bool = True,
    trim_white: bool = True,
) -> Image.Image:
    """导出到内存，返回 PIL Image，不保存文件

    用于预览面板和 Single View 显示。
    """
    cropped = _crop_image(source_img, rect)
    if rect.rotation_angle != 0.0:
        cropped = _apply_rotation(cropped, rect.rotation_angle)
    if auto_rotate:
        try:
            angle = estimate_rotation_angle(cropped)
            if angle != 0.0:
                cropped = _apply_rotation(cropped, angle)
        except (ValueError, RuntimeError, OSError):
            pass
    if trim_white:
        cropped = _trim_white_border(cropped)
    return cropped


def write_exif_metadata(
    img: Image.Image,
    *,
    title: str = "",
    description: str = "",
    tags: str = "",
    date: str = "",
) -> Image.Image:
    """写入 EXIF 元数据（仅 JPEG/TIFF 有效）

    使用 Pillow 原生 EXIF 支持，不引入额外依赖。
    EXIF 数据存储在 img.info["exif"] 中，_save_image 会自动传递给 save()。

    Args:
        img: 输入图像
        title: 图片标题 (ImageDescription)
        description: 描述 (UserComment)
        tags: 标签 (XPKeywords)
        date: 日期 (DateTimeOriginal)

    Returns:
        带 EXIF 数据的图像副本
    """
    img = img.copy()

    # 使用 IFD 字典直接构建 EXIF 字节
    # 避免 Exif() 对象在空图像上初始化不完整的问题
    from PIL.Image import Exif

    exif = Exif()
    exif[0x010F] = "PhotoCrop"  # Make — 标识来源

    if title:
        exif[0x010E] = title  # ImageDescription

    if date:
        exif[0x9003] = date  # DateTimeOriginal

    if description:
        comment_bytes = b"ASCII\x00\x00\x00" + description.encode("ascii", errors="replace")[:500]
        exif[0x9286] = comment_bytes  # UserComment

    if tags:
        exif[0x9C9E] = tags.encode("utf-16-le") + b"\x00\x00"  # XPKeywords

    img.info["exif"] = exif.tobytes()
    return img
