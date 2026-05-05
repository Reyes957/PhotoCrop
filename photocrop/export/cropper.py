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
        except Exception:
            pass  # 自动旋转失败时跳过

    # ---- 步骤 4: 去白边 ----
    if trim_white:
        cropped = _trim_white_border(cropped)

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
        img.save(str(path), "JPEG", quality=quality)

    elif suffix == ".png":
        # PNG: 保留透明通道
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.save(str(path), "PNG")

    else:
        # 默认按原格式保存
        img.save(str(path))
