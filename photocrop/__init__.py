"""
PhotoCrop - 从扫描 PDF 相册中提取照片

v0.1.0: 引擎封装 — 检测照片矩形 + 旋转角度估计
v0.2.0: UI 交互 — PySide6 画布 + 可交互裁剪框
v0.3.0: 导出功能 — 裁剪 + 旋转 + 去白边 + PDF 读取
v0.4.0: UI 体验 + 工程化基础设施 — 撤销/重做、配置系统、投票融合、CI/CD
v0.5.0: 多图像管理 + 属性面板 + 批量导出 + Single View + 模板系统 + PDF 全局预览
v0.5.1: Bug 修复 — 撤销支持、属性面板、build-backend、导出模板、代码去重
v0.5.2: 17 个 Bug 修复 + PDF 全局跨页预览 + 裁剪框旋转 90° + PDF 多页展开 + CI 修复
v0.6.0: 1:1 复刻 HTML 参考 UI + Light/Dark 双主题 + 工具栏重构 + 空状态页
v0.6.1: UI 主题重构 — 4 面板 Dark 模式完整支持 + 版本号动态化 + Undo/Redo 禁用逻辑 + Zoom 实时同步 + 9 bug fixes
v0.6.2: SVG 图标系统 — 22 个 SVG 图标 + get_icon() 运行时颜色注入 + 主题切换/工具栏修复
v0.6.3: 第二轮设计审查 — 18 项 UI 美学改进 + Signal/State 一致性 + 106 新测试
v0.6.4: 控制器架构 — AppState 全局状态 + 5 个控制器 + PressButton + Toast + 拖拽导入 + 6 bug fixes
v0.7.0: 架构重构 — 业务逻辑与 Qt 解耦 + 全局状态管理 + 123 测试 + 文档全面同步
v0.7.1: StyledDropdown/LightDropdown 自定义下拉组件 + 默认检测器 enhanced-cv + 提取面板精调
v0.7.2: CropItem 裁剪框边框修复 — ItemClipsToShape 裁剪框线修复 + 加粗虚线 + 选中框呼吸脉动
v0.7.3: 旋转手柄重构 — 84px toolbar 风格 + SVG 图标放大（工具栏/旋转手柄 UI 统一）
"""

__version__ = "0.7.4"

from photocrop.utils.crop_rect import CropRect

# 引擎依赖 scipy，可能未安装
try:
    from photocrop.engine.core import detect_rectangles
except ImportError:
    detect_rectangles = None

__all__ = ["detect_rectangles", "CropRect"]
