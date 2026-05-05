"""
YOLOWorldDetector — YOLO-World 零样本检测器

使用 YOLO-World (ultralytics) 进行开放词汇检测，
无需训练即可识别相册页面中的照片。

依赖安装:
    bash install_yolo.sh
    或手动:
        pip install torch torchvision ultralytics
        pip install git+https://github.com/ultralytics/CLIP.git
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from PIL import Image

# 禁用 ultralytics 自动更新
os.environ["ULTRALYTICS_AUTO_UPDATE"] = "0"

from photocrop.engine.detector_base import BaseDetector
from photocrop.utils.crop_rect import CropRect


# 默认文本提示
DEFAULT_PROMPTS = ["photograph", "printed photo"]

# 模型大小
DEFAULT_MODEL_SIZE = "x"


class YOLOWorldDetector(BaseDetector):
    """YOLO-World 零样本开放词汇检测器

    使用文本提示（如 "photograph"）来检测图像中的照片区域，
    无需任何训练数据。首次加载模型可能需要几十秒。

    Example:
        detector = YOLOWorldDetector()
        rects = detector.detect(page_img)

        # 自定义提示
        detector = YOLOWorldDetector(prompts=["photo", "picture"])

        # 使用更小的模型（更快但精度略低）
        detector = YOLOWorldDetector(model_size="s")
    """

    def __init__(
        self,
        prompts: Optional[List[str]] = None,
        model_size: str = DEFAULT_MODEL_SIZE,
        confidence: float = 0.1,
    ):
        self._prompts = prompts or DEFAULT_PROMPTS
        self._model_size = model_size
        self._confidence = confidence
        self._model = None
        self._device = None

    def _detect_device(self) -> str:
        """自动检测最佳推理设备"""
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
            elif torch.cuda.is_available():
                return "cuda"
            else:
                return "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self):
        """延迟加载模型（首次调用时）"""
        if self._model is not None:
            return

        # 检查 ultralytics
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "ultralytics 未安装。请运行:\n"
                "  bash install_yolo.sh\n"
                "或手动:\n"
                "  pip install torch torchvision --user\n"
                "  pip install ultralytics --user"
            )

        # 检查 CLIP（ultralytics 8.2+ 可能已内置）
        try:
            import clip  # noqa: F401
        except ImportError:
            try:
                # 尝试通过 ultralytics.utils.checks 自动安装
                from ultralytics.utils.checks import check_requirements
                check_requirements("git+https://github.com/ultralytics/CLIP.git")
            except Exception:
                raise ImportError(
                    "CLIP 未安装（YOLO-World 依赖）。请运行:\n"
                    "  pip install git+https://github.com/ultralytics/CLIP.git --user"
                )

        os.environ["ULTRALYTICS_AUTO_UPDATE"] = "0"

        # 优先使用项目目录下的本地模型文件（避免重复下载）
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        local_model = os.path.join(
            project_root, f"yolov8{self._model_size}-worldv2.pt"
        )

        if os.path.exists(local_model):
            model_path = local_model
            print(f"[YOLO-World] 使用本地模型: {model_path}")
        else:
            model_path = f"yolov8{self._model_size}-worldv2.pt"
            print(f"[YOLO-World] 本地模型不存在，将自动下载到: {os.getcwd()}")

        # 加载模型
        self._device = self._detect_device()
        print(f"[YOLO-World] 推理设备: {self._device}")

        self._model = YOLO(model_path)
        self._model.set_classes(self._prompts)
        print(f"[YOLO-World] 模型加载完成，提示词: {self._prompts}")

    @property
    def name(self) -> str:
        return "yolo-world"

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model is not None

    def detect(self, page_img: Image.Image) -> List[CropRect]:
        """使用 YOLO-World 检测照片

        Args:
            page_img: PIL Image，完整页面图像（RGB）

        Returns:
            List[CropRect] — 检测到的照片矩形，按面积降序排列
        """
        self._load_model()

        w, h = page_img.size

        # 推理
        results = self._model.predict(
            page_img,
            conf=self._confidence,
            verbose=False,
        )

        rects = []
        for i, box in enumerate(results[0].boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])

            # 边界约束
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            rect = CropRect.from_pixel_rect(x1, y1, x2, y2, rotation_angle=0.0)
            rect.source_type = "detection"
            rect.confidence = conf
            rect.index = i
            rects.append(rect)

        # 按面积从大到小排序
        rects.sort(key=lambda r: r.width * r.height, reverse=True)
        for i, r in enumerate(rects):
            r.index = i

        return rects

    def __repr__(self) -> str:
        return (
            f"<YOLOWorldDetector prompts={self._prompts} "
            f"model={self._model_size} conf={self._confidence}>"
        )
