"""
旋转角度工具

规范（project_rules.md §5）：
- 顺时针为正
- OpenCV 角度转换必须使用 to_opencv_angle()
"""



def to_opencv_angle(clockwise_degrees: float) -> float:
    """将顺时针角度转换为 OpenCV 角度

    OpenCV 使用逆时针为正的角度系统。
    本函数将本项目的顺时针角度转换为 OpenCV 格式。

    Args:
        clockwise_degrees: 顺时针旋转角度（度）

    Returns:
        OpenCV 兼容的旋转角度（逆时针为正）
    """
    return -clockwise_degrees


def normalize_angle(angle_degrees: float) -> float:
    """将角度规范化到 [-180, 180] 范围内

    Args:
        angle_degrees: 任意角度（度）

    Returns:
        规范化后的角度，范围 [-180, 180]
    """
    angle = angle_degrees % 360
    if angle > 180:
        angle -= 360
    return angle


def angle_within_tolerance(angle: float, expected: float, tolerance: float = 10.0) -> bool:
    """检查角度是否在容差范围内（±10° 默认）

    Args:
        angle: 待检查角度
        expected: 期望角度
        tolerance: 容差度数（默认 10°）

    Returns:
        是否在容差内
    """
    diff = abs(normalize_angle(angle - expected))
    return diff <= tolerance or abs(diff - 360) <= tolerance
