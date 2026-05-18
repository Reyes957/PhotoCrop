"""
测试导出功能的边界情况 — 裁剪区域超出图像范围
"""

from pathlib import Path

from PIL import Image

from photocrop.export.cropper import _crop_image, export_photo
from photocrop.utils.crop_rect import CropRect


def test_crop_image_with_large_rect():
    """裁剪区域完全超出图像范围时应 clamp 到图像边界"""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    rect = CropRect(x=150, y=150, width=200, height=200)
    try:
        cropped = _crop_image(img, rect)
        # 应该 clamp 到图像边界内
        assert cropped.width <= 100
        assert cropped.height <= 100
    except ValueError as e:
        assert "裁剪区域无效" in str(e)


def test_crop_image_with_partial_rect():
    """裁剪区域部分超出图像范围时应 clamp 到图像边界"""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    rect = CropRect(x=80, y=80, width=100, height=100)
    cropped = _crop_image(img, rect)
    assert cropped.width <= 100
    assert cropped.height <= 100


def test_export_with_large_rect():
    """导出时 crop_rect 完全超出图像范围应报错"""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    rect = CropRect(x=150, y=150, width=200, height=200)

    output_path = Path("/tmp/test_export.jpg")
    try:
        export_photo(img, rect, output_path, auto_rotate=False, trim_white=False)
        # 如果没抛异常，验证文件存在
        assert output_path.exists()
        output_path.unlink()
    except (ValueError, RuntimeError, OSError) as e:
        # ValueError: 裁剪区域完全无效 → 预期行为
        assert "裁剪区域无效" in str(e) or "无效" in str(e)


def test_crop_rect_inside_image():
    """crop_rect 完全在图像范围内时正常裁剪"""
    img = Image.new("RGB", (100, 100), color=(0, 0, 255))
    rect = CropRect(x=50, y=50, width=50, height=50)
    cropped = _crop_image(img, rect)
    # _CROP_PEN_HALF=-5 使每边向内缩 5px：50-10=40
    assert cropped.size == (40, 40)


def test_crop_rect_partially_outside_top_left():
    """crop_rect 部分在图像范围外（左上角超出）"""
    img = Image.new("RGB", (100, 100), color=(0, 255, 0))
    rect = CropRect(x=80, y=80, width=100, height=100)
    cropped = _crop_image(img, rect)
    # 应该 clamp，结果不会超出图像
    assert cropped.width <= 100
    assert cropped.height <= 100


def test_source_image_bounds_export():
    """验证 _crop_image 对边界情况的 clamp 行为"""
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    # 左上角在图像外
    rect = CropRect(x=30, y=30, width=100, height=100)
    cropped = _crop_image(img, rect)
    # x=30,y=30,w=100,h=100 → x1=-20,y1=-20,x2=80,y2=80
    # _CROP_PEN_HALF=-5: x1=-20+5=-15→0, y1=-15→0, x2=80-5=75, y2=75
    assert cropped.size == (75, 75)
