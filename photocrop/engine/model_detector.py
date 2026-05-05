"""
ModelDetector — 模型检测器（占位）

预留接口，用于接入：
- 本地模型（YOLO、SAM 等）
- 大模型视觉 API（GPT-4V、Claude Vision 等）

当前为占位实现，返回空列表。
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image

from photocrop.engine.detector_base import BaseDetector
from photocrop.utils.crop_rect import CropRect


class ModelDetector(BaseDetector):
    """模型检测器 — 占位

    接入模型时，只需实现 detect() 方法。

    Example (接入 YOLO):
        class YOLODetector(BaseDetector):
            def __init__(self, model_path):
                from ultralytics import YOLO
                self.model = YOLO(model_path)

            def detect(self, page_img):
                results = self.model(page_img)
                rects = []
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    rects.append(CropRect.from_pixel_rect(x1, y1, x2, y2))
                return rects

    Example (接入 GPT-4V):
        class GPT4VDetector(BaseDetector):
            def __init__(self, api_key):
                self.client = OpenAI(api_key=api_key)

            def detect(self, page_img):
                # 调用 API 获取照片坐标
                # 解析返回的坐标
                return rects
    """

    def __init__(self, model_path: Optional[str] = None, **kwargs):
        self._model_path = model_path
        self._config = kwargs

    @property
    def name(self) -> str:
        return "model"

    def detect(self, page_img: Image.Image) -> List[CropRect]:
        """使用模型检测照片 — 当前为占位实现

        Args:
            page_img: PIL Image，完整页面图像

        Returns:
            List[CropRect] — 当前返回空列表
        """
        # TODO: 接入模型推理
        # 1. 预处理 image
        # 2. 调用模型
        # 3. 解析输出为 CropRect
        return []
