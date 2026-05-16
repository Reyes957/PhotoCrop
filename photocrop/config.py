"""
用户配置系统

配置文件位置：~/.config/photocrop/config.yaml
所有参数都有默认值，配置文件可选。

用法：
    from photocrop.config import get_config
    cfg = get_config()
    print(cfg.detector)       # "enhanced-cv"
    print(cfg.max_count)      # 4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认配置文件路径
_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "photocrop"
_DEFAULT_CONFIG_FILE = _DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class PhotoCropConfig:
    """PhotoCrop 用户配置（所有字段都有默认值）"""

    # 检测器
    detector: str = "enhanced-cv"
    max_count: int = 4
    min_width: float = 100
    min_height: float = 100
    min_area: float = 10000
    iou_threshold: float = 0.7

    # 导出
    export_format: str = "jpg"  # "jpg" 或 "png"
    jpeg_quality: int = 95
    auto_rotate: bool = True
    trim_white: bool = True

    # YOLO-World
    yolo_model_size: str = "x"
    yolo_confidence: float = 0.1
    yolo_prompts: list = field(default_factory=lambda: ["photograph", "printed photo"])

    # PDF
    pdf_dpi: int = 200

    def to_dict(self) -> dict:
        """转为字典（用于序列化）"""
        return {
            "detector": self.detector,
            "max_count": self.max_count,
            "min_width": self.min_width,
            "min_height": self.min_height,
            "min_area": self.min_area,
            "iou_threshold": self.iou_threshold,
            "export_format": self.export_format,
            "jpeg_quality": self.jpeg_quality,
            "auto_rotate": self.auto_rotate,
            "trim_white": self.trim_white,
            "yolo_model_size": self.yolo_model_size,
            "yolo_confidence": self.yolo_confidence,
            "yolo_prompts": self.yolo_prompts,
            "pdf_dpi": self.pdf_dpi,
        }


def _load_yaml(path: Path) -> dict:
    """加载 YAML 配置文件（依赖可选的 pyyaml）"""
    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml 未安装，跳过配置文件 %s。运行 pip install pyyaml 启用配置。", path)
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, AttributeError) as e:
        logger.warning("配置文件读取失败 (%s): %s", path, e)
        return {}


def load_config(path: Path | None = None) -> PhotoCropConfig:
    """加载用户配置

    Args:
        path: 配置文件路径（默认 ~/.config/photocrop/config.yaml）

    Returns:
        PhotoCropConfig 实例（缺失字段使用默认值）
    """
    config_path = path or _DEFAULT_CONFIG_FILE
    cfg = PhotoCropConfig()

    if not config_path.exists():
        logger.info("配置文件不存在，使用默认值: %s", config_path)
        return cfg

    data = _load_yaml(config_path)
    if not data:
        return cfg

    # 用配置文件的值覆盖默认值
    for key, value in data.items():
        if hasattr(cfg, key):
            current = getattr(cfg, key)
            # 类型检查：只覆盖同类型的值
            if isinstance(value, type(current)):
                setattr(cfg, key, value)
            else:
                logger.warning("配置项 %s 类型不匹配（期望 %s，实际 %s），忽略",
                               key, type(current).__name__, type(value).__name__)

    return cfg


def save_config(cfg: PhotoCropConfig, path: Path | None = None) -> None:
    """保存配置到文件

    Args:
        cfg: PhotoCropConfig 实例
        path: 保存路径（默认 ~/.config/photocrop/config.yaml）
    """
    config_path = path or _DEFAULT_CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg.to_dict(), f, default_flow_style=False, allow_unicode=True)
        logger.info("配置已保存: %s", config_path)
    except ImportError:
        logger.warning("pyyaml 未安装，无法保存配置。运行 pip install pyyaml 启用。")
    except (OSError, ValueError, AttributeError) as e:
        logger.warning("配置保存失败: %s", e)


# 全局配置单例
_global_config: PhotoCropConfig | None = None


def get_config() -> PhotoCropConfig:
    """获取全局配置（单例模式，首次调用时加载）"""
    global _global_config
    if _global_config is None:
        _global_config = load_config()
    return _global_config
