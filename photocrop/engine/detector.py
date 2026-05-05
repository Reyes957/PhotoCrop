"""
兼容 shim — detector.py 已重命名为 cv_algorithm.py

本文件仅保留向后兼容的导入，新代码请直接使用 cv_algorithm。
"""

from photocrop.engine.cv_algorithm import (  # noqa: F401
    classify_scene,
    detect_photos_in_scene,
    extract_photos_from_page,
)

__all__ = ["classify_scene", "detect_photos_in_scene", "extract_photos_from_page"]
