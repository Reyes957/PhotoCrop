# Changelog

## v0.3.1 — 代码质量改进（2026-05-05）

### Bug 修复

- **版本号不一致** — `main.py` 的 GUI 模式硬编码版本号为 `0.2.0`，现在改为从 `photocrop.__version__` 动态读取

### 代码重构

- **消除命名冲突** — `engine/detector.py`（原始 CV 算法）重命名为 `engine/cv_algorithm.py`，避免与 `detector_base.py`（抽象基类）混淆。旧路径保留兼容 shim
- **明确 rotation 模块分工** — `engine/rotation.py`（CV 角度估算）重命名为 `engine/rotation_estimator.py`，与 `utils/rotation.py`（纯数学工具）职责分离。旧路径保留兼容 shim
- **测试目录独立** — `test_engine.py` 从 `photocrop/` 移至项目根目录的 `tests/`，移除 `sys.path` hack
- **完善 model_detector.py 文档** — 明确其作为通用占位检测器的定位，与 YOLOWorldDetector 的关系

### 文档

- **README** — 添加"Why this exists"章节，修正 git clone URL
- **CLAUDE.md** — 同步更新项目结构和 Bug 修复记录

---

## v0.3.0 — 首次公开发布

- Engine：5 步检测流水线（检测 → 旋转估算 → 过滤 → 去重 → 限制数量）
- UI：PySide6 画布 + 可交互裁剪框（拖拽/缩放/旋转）
- Export：裁剪 + 旋转 + 去白边 + JPEG/PNG 双格式
- PDF：批量处理模式
- 检测器：CV / Enhanced CV / Combined / YOLO-World
