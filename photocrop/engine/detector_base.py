"""
BaseDetector — 检测器抽象接口

所有检测器（传统 CV、本地模型、大模型 API）都实现此接口。
engine/core.py 通过此接口调度不同检测器，实现可替换。

规范：
    - 输入：PIL Image（单页）
    - 输出：List[CropRect]（中心坐标）
    - 检测器不负责过滤和去重（由 core.py 统一处理）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from PIL import Image

from photocrop.utils.crop_rect import CropRect


class BaseDetector(ABC):
    """检测器抽象基类

    所有检测器必须实现 detect() 方法。
    detect() 只负责"找到照片在哪"，不做过滤、去重、旋转估算。

    Example:
        class MyDetector(BaseDetector):
            def detect(self, page_img):
                # 你的检测逻辑
                return [CropRect(...)]

        detector = MyDetector()
        rects = detector.detect(img)
    """

    @property
    def name(self) -> str:
        """检测器名称，用于日志和选择"""
        return self.__class__.__name__

    @abstractmethod
    def detect(self, page_img: Image.Image) -> List[CropRect]:
        """检测页面中的照片矩形

        Args:
            page_img: PIL Image，完整页面图像（RGB）

        Returns:
            List[CropRect] — 检测到的照片矩形（中心坐标，rotation_angle 可为 0）

        Note:
            - 不需要做小框过滤、IoU 去重、数量限制（由 core.py 统一处理）
            - 不需要做旋转估算（由 core.py 统一处理）
            - 只需要返回"照片在哪里"
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
