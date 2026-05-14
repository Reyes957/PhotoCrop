# Contributing to PhotoCrop

感谢你对 PhotoCrop 的兴趣！以下是参与贡献的指南。

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/Reyes957/PhotoCrop.git
cd PhotoCrop

# 安装依赖（开发模式）
pip install -e ".[all]"

# 安装开发工具
pip install pytest ruff mypy
```

## 代码规范

- **Python 3.9+**：不使用 3.10+ 语法（如 `match/case`）
- **格式化**：使用 `ruff format` 统一格式
- **Lint**：使用 `ruff check` 检查代码质量
- **类型注解**：公共 API 需要类型注解，内部方法建议添加

```bash
# 格式化
ruff format photocrop/ tests/

# 检查
ruff check photocrop/ tests/

# 类型检查（可选）
mypy photocrop/
```

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_engine.py::TestCropRect -v

# 运行特定模块
pytest tests/test_state.py -v
pytest tests/test_export_controller.py -v
pytest tests/test_session_controller.py -v
```

## 提交规范

使用清晰的提交信息：

```
feat: 添加 YOLO-World 异步加载
fix: 修复裁剪框拖动残影
refactor: 提取 cv_algorithm.py 中的 magic numbers
docs: 更新 README 安装说明
test: 添加 CombinedDetector 投票融合测试
```

## 架构概述

```
photocrop/
├── engine/     # 检测引擎（ABC + 工厂模式）
├── ui/         # PySide6 GUI（黑白极简设计）
│   ├── controllers/  # 业务逻辑控制器层（与 Qt 控件解耦）
│   ├── state.py      # AppState 全局状态管理器
│   ├── theme.py      # ThemeManager 单例（Light/Dark + 过渡动画）
│   └── ...           # 各 UI 面板和组件
├── export/     # 裁剪 + 导出
└── utils/      # 工具函数
```

新增检测器只需继承 `BaseDetector` 并实现 `detect()` 方法，然后在 `engine/core.py` 的 `get_detector()` 工厂中注册。

新增控制器只需继承 `QObject`，通过 `AppState` 订阅状态变化，在 `main_window.py` 中实例化并连接信号。

## 报告问题

请使用 [GitHub Issues](https://github.com/Reyes957/PhotoCrop/issues) 报告 bug 或提出功能建议。包含以下信息：

- 操作系统和 Python 版本
- 复现步骤
- 预期行为 vs 实际行为
- 相关截图（如有）
