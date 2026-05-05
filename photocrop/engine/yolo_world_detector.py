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

import logging
import os
import threading
from typing import List, Optional

from PIL import Image

# 禁用 ultralytics 自动更新
os.environ["ULTRALYTICS_AUTO_UPDATE"] = "0"

from photocrop.engine.detector_base import BaseDetector
from photocrop.utils.crop_rect import CropRect

logger = logging.getLogger(__name__)

# 默认文本提示
DEFAULT_PROMPTS = ["photograph", "printed photo"]

# 模型大小
DEFAULT_MODEL_SIZE = "x"


def _get_cache_dir() -> str:
    """获取模型缓存目录（使用 platformdirs 或 fallback）"""
    try:
        from platformdirs import user_cache_dir
        cache = user_cache_dir("photocrop")
    except ImportError:
        cache = os.path.join(os.path.expanduser("~"), ".cache", "photocrop")
    os.makedirs(cache, exist_ok=True)
    return cache


class YOLOWorldDetector(BaseDetector):
    """YOLO-World 零样本开放词汇检测器

    使用文本提示（如 "photograph"）来检测图像中的照片区域，
    需要任何训练数据。首次加载模型可能需要几十秒。

    支持异步预加载：调用 `load_async()` 在后台线程加载模型，
    避免阻塞 UI。`detect()` 会等待加载完成。

    Example:
        detector = YOLOWorldDetector()
        rects = detector.detect(page_img)

        # 自定义提示
        detector = YOLOWorldDetector(prompts=["photo", "picture"])

        # 使用更小的模型（更快但精度略低）
        detector = YOLOWorldDetector(model_size="s")

        # 异步预加载（不阻塞）
        detector = YOLOWorldDetector()
        detector.load_async()
        # ... 用户做其他操作 ...
        rects = detector.detect(page_img)  # 如果加载完成则立即使用
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
        self._loading = False
        self._load_event = threading.Event()

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

    def _load_model_sync(self):
        """同步加载模型（内部方法）"""
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
                from ultralytics.utils.checks import check_requirements
                check_requirements("git+https://github.com/ultralytics/CLIP.git")
            except (ImportError, Exception):
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
            logger.info("使用本地模型: %s", model_path)
        else:
            # 使用 platformdirs 缓存目录
            cache_dir = _get_cache_dir()
            cached_model = os.path.join(
                cache_dir, f"yolov8{self._model_size}-worldv2.pt"
            )
            if os.path.exists(cached_model):
                model_path = cached_model
                logger.info("使用缓存模型: %s", model_path)
            else:
                model_path = f"yolov8{self._model_size}-worldv2.pt"
                logger.info("本地模型不存在，将自动下载: %s", model_path)

        # 加载模型
        self._device = self._detect_device()
        logger.info("推理设备: %s", self._device)

        self._model = YOLO(model_path)
        self._model.set_classes(self._prompts)
        logger.info("模型加载完成，提示词: %s", self._prompts)
        self._load_event.set()

    def _load_model(self):
        """加载模型（如果异步加载中则等待完成）"""
        if self._model is not None:
            return
        if self._loading:
            # 异步加载进行中，等待完成
            self._load_event.wait()
            if self._model is not None:
                return
        self._load_model_sync()

    def load_async(self) -> None:
        """在后台线程中预加载模型（不阻塞调用者）

        调用后 `detect()` 会自动等待加载完成。
        重复调用是安全的（已加载则跳过）。
        """
        if self._model is not None or self._loading:
            return
        self._loading = True
        thread = threading.Thread(target=self._load_model_sync, daemon=True)
        thread.start()

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
