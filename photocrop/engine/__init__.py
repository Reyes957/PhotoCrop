"""
引擎模块 — 照片检测、过滤、旋转估计

检测器抽象层：
    BaseDetector      — 检测器抽象基类
    CVDetector        — 传统 CV 算法检测器
    YOLOWorldDetector — YOLO-World 零样本检测器（需要 ultralytics）
    ModelDetector     — 模型检测器（占位）

主入口：
    detect_rectangles() — 完整 5 步检测流程
    get_detector()      — 检测器工厂函数
"""

try:
    from photocrop.engine.core import detect_rectangles, get_detector
except ImportError:
    detect_rectangles = None
    get_detector = None

try:
    from photocrop.engine.detector_base import BaseDetector
except ImportError:
    BaseDetector = None

try:
    from photocrop.engine.cv_detector import CVDetector
except ImportError:
    CVDetector = None

try:
    from photocrop.engine.yolo_world_detector import YOLOWorldDetector
except ImportError:
    YOLOWorldDetector = None

try:
    from photocrop.engine.model_detector import ModelDetector
except ImportError:
    ModelDetector = None

__all__ = [
    "detect_rectangles",
    "get_detector",
    "BaseDetector",
    "CVDetector",
    "YOLOWorldDetector",
    "ModelDetector",
]
