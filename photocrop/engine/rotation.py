"""
兼容 shim — 旋转估算已重命名为 rotation_estimator.py

本文件仅保留向后兼容的导入，新代码请直接使用 rotation_estimator。
纯数学工具（normalize_angle、to_opencv_angle）在 utils/rotation.py。
"""

from photocrop.engine.rotation_estimator import (  # noqa: F401
    estimate_rotation_angle,
    estimate_from_array,
    estimate_batch,
)

__all__ = ["estimate_rotation_angle", "estimate_from_array", "estimate_batch"]
