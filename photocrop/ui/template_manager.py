"""
TemplateManager — 裁剪框模板管理

保存/加载裁剪框布局模板（百分比坐标），可跨图片复用。
存储位置: ~/.config/photocrop/templates.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

from photocrop.utils.crop_rect import CropRect


@dataclass
class CropTemplate:
    """裁剪框模板"""
    name: str
    rects: List[dict] = field(default_factory=list)  # 百分比坐标: {x, y, w, h, rotation}
    aspect_ratio: Optional[float] = None


class TemplateManager:
    """模板管理器"""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "photocrop"
        self._config_dir = Path(config_dir)
        self._templates_file = self._config_dir / "templates.json"
        self._templates: List[CropTemplate] = []
        self._load()

    @property
    def templates(self) -> List[CropTemplate]:
        return list(self._templates)

    def _load(self) -> None:
        """从磁盘加载模板"""
        if not self._templates_file.exists():
            return
        try:
            data = json.loads(self._templates_file.read_text(encoding="utf-8"))
            self._templates = []
            for item in data:
                self._templates.append(CropTemplate(
                    name=item.get("name", "Unnamed"),
                    rects=item.get("rects", []),
                    aspect_ratio=item.get("aspect_ratio"),
                ))
        except (json.JSONDecodeError, OSError):
            self._templates = []

    def _save(self) -> None:
        """保存模板到磁盘"""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = [
            {"name": t.name, "rects": t.rects, "aspect_ratio": t.aspect_ratio}
            for t in self._templates
        ]
        self._templates_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_template(self, name: str, crop_rects: List[CropRect],
                      image_size: tuple) -> CropTemplate:
        """将当前裁剪框保存为模板（转换为百分比坐标）

        Args:
            name: 模板名称
            crop_rects: 当前裁剪框列表
            image_size: 源图尺寸 (width, height)
        """
        img_w, img_h = image_size
        rects = []
        for r in crop_rects:
            rects.append({
                "x_pct": r.x / img_w if img_w > 0 else 0,
                "y_pct": r.y / img_h if img_h > 0 else 0,
                "w_pct": r.width / img_w if img_w > 0 else 0,
                "h_pct": r.height / img_h if img_h > 0 else 0,
                "rotation": r.rotation_angle,
            })

        template = CropTemplate(name=name, rects=rects)
        self._templates.append(template)
        self._save()
        return template

    def apply_template(self, template: CropTemplate,
                       image_size: tuple) -> List[CropRect]:
        """将模板应用到指定尺寸的图片

        Args:
            template: 模板
            image_size: 目标图片尺寸 (width, height)

        Returns:
            转换后的 CropRect 列表
        """
        img_w, img_h = image_size
        result = []
        for r in template.rects:
            x = r.get("x_pct", 0) * img_w
            y = r.get("y_pct", 0) * img_h
            w = r.get("w_pct", 0) * img_w
            h = r.get("h_pct", 0) * img_h
            rotation = r.get("rotation", 0)
            result.append(CropRect.from_pixel_rect(
                x - w / 2, y - h / 2, x + w / 2, y + h / 2, rotation,
            ))
        return result

    def delete_template(self, name: str) -> bool:
        """删除指定名称的模板"""
        for i, t in enumerate(self._templates):
            if t.name == name:
                self._templates.pop(i)
                self._save()
                return True
        return False
