"""
CropRect — 统一坐标数据类

规范（project_rules.md §4）：
- x, y → 矩形中心坐标
- width, height → 矩形尺寸
- rotation_angle → 顺时针为正，单位：度

转换公式：
  像素左上角 x = x - width/2
  像素左上角 y = y - height/2
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CropRect:
    """检测到的照片矩形区域（中心坐标系统）"""

    x: float  # 中心 x
    y: float  # 中心 y
    width: float
    height: float
    rotation_angle: float = 0.0  # 顺时针度数

    confidence: Optional[float] = None  # 检测置信度 (0.0 ~ 1.0)

    # —— 内部元数据（不参与相等比较）——
    source_type: str = field(default="detection", repr=False)  # "detection" | "manual"
    page_num: int = field(default=0, repr=False)
    index: int = field(default=0, repr=False)

    # —— 像素坐标转换 ——

    @property
    def x1(self) -> float:
        """左上角 x（像素坐标）"""
        return self.x - self.width / 2

    @property
    def y1(self) -> float:
        """左上角 y（像素坐标）"""
        return self.y - self.height / 2

    @property
    def x2(self) -> float:
        """右下角 x（像素坐标）"""
        return self.x + self.width / 2

    @property
    def y2(self) -> float:
        """右下角 y（像素坐标）"""
        return self.y + self.height / 2

    @property
    def area(self) -> float:
        """矩形面积"""
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        """宽高比 (width/height)"""
        if self.height == 0:
            return float("inf")
        return self.width / self.height

    # —— 工厂方法 ——

    @classmethod
    def from_pixel_rect(cls, x1: float, y1: float, x2: float, y2: float,
                        rotation_angle: float = 0.0,
                        confidence: Optional[float] = None) -> "CropRect":
        """从像素边角坐标构造 CropRect

        Args:
            x1: 左上角 x
            y1: 左上角 y
            x2: 右下角 x
            y2: 右下角 y
            rotation_angle: 旋转角度
            confidence: 置信度
        """
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        w = x2 - x1
        h = y2 - y1
        return cls(x=cx, y=cy, width=w, height=h,
                   rotation_angle=rotation_angle,
                   confidence=confidence)

    def to_pixel_tuple(self) -> tuple:
        """返回 (x1, y1, x2, y2) 像素坐标"""
        return (int(self.x1), int(self.y1), int(self.x2), int(self.y2))

    def __str__(self) -> str:
        return (f"CropRect(cx={self.x:.1f}, cy={self.y:.1f}, "
                f"w={self.width:.1f}, h={self.height:.1f}, "
                f"angle={self.rotation_angle:.1f}°)")
