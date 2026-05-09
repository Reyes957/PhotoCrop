"""UI 工具函数 — PIL <-> Qt 图像转换"""

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def pil_to_qimage(img: Image.Image) -> QImage:
    """PIL Image -> QImage（深拷贝，避免内存问题）

    BUG-010 fix: 正确处理 LA/PA/P 等带 alpha 的模式。
    """
    if img.mode in ("RGBA", "LA", "PA"):
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        bpl = img.width * 4
        qimage = QImage(data, img.width, img.height, bpl,
                        QImage.Format.Format_RGBA8888)
    else:
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        bpl = img.width * 3
        qimage = QImage(data, img.width, img.height, bpl,
                        QImage.Format.Format_RGB888)
    return qimage.copy()


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    """PIL Image -> QPixmap"""
    return QPixmap.fromImage(pil_to_qimage(img))
