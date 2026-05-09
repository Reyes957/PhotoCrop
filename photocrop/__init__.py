"""
PhotoCrop - 从扫描 PDF 相册中提取照片

v0.1.0: 引擎封装 — 检测照片矩形 + 旋转角度估计
v0.2.0: UI 交互 — PySide6 画布 + 可交互裁剪框
v0.3.0: 导出功能 — 裁剪 + 旋转 + 去白边 + PDF 读取
v0.4.0: UI 体验 + 工程化基础设施 — 撤销/重做、配置系统、投票融合、CI/CD
v0.5.0: 多图像管理 + 属性面板 + 批量导出 + Single View + 模板系统 + PDF 全局预览
v0.5.1: Bug 修复 — 撤销支持、属性面板、build-backend、导出模板、代码去重
v0.5.2: 17 个 Bug 修复 + PDF 全局跨页预览 + 裁剪框旋转 90° + PDF 多页展开 + CI 修复
"""

__version__ = "0.5.2"

from photocrop.utils.crop_rect import CropRect

# 引擎依赖 scipy，可能未安装
try:
    from photocrop.engine.core import detect_rectangles
except ImportError:
    detect_rectangles = None

__all__ = ["detect_rectangles", "CropRect"]
