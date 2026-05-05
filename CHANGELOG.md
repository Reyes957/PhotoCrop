# Changelog

## v0.4.0 — UI 体验 + 工程化基础设施 + 新功能（2026-05-05）

### P0 — 严重体验问题修复

- **框太容易新建** — `canvas.py` 引入 30px 最小拖动阈值，单击空白处不再误创建裁剪框，临时矩形延迟到超过阈值后才创建
- **拖动裁剪框残影** — `canvas.py` 设置 `FullViewportUpdate` 模式；`crop_item.py` 添加 `ItemSendsGeometryChanges` + `DeviceCoordinateCache`，`_on_changed()` 延迟到 `mouseReleaseEvent` 触发，消除信号风暴
- **按钮样式异常** — `main_window.py` 修复 `setProperty("secondary", True)` → `"true"`（QSS 匹配字符串）；导航按钮 28→32px；新增快捷键 Ctrl+O/D/E、←/→

### P1 — 重要问题修复

- **版本号不一致** — `__init__.py` 从 `0.3.0` 更新为 `0.3.1`
- **裸 except Exception** — `main.py`、`cropper.py`、`rotation_estimator.py`、`core.py` 共 5 处改为具体异常类型 `(ValueError, RuntimeError, OSError)` 等
- **旋转 paint 未应用变换** — `crop_item.py` 的 `paint()` 添加 `painter.save()/rotate()/restore()` 坐标变换
- **rects_changed 信号风暴** — `main_window.py` 添加 50ms QTimer 防抖
- **添加 pyproject.toml** — 完整包配置，`pip install -e .` 可用，可选 extras（gui/yolo）

### P2 — 工程化改进

- **CI/CD** — 添加 `.github/workflows/ci.yml`（Python 3.9-3.12 矩阵测试 + ruff lint）
- **pytest 迁移** — `tests/test_engine.py` 从自定义框架重写为 pytest（类 + fixture + assert）
- **logging** — `main.py` 配置 `logging.basicConfig()`；`yolo_world_detector.py` 改用 `logging` 模块
- **检测器缓存** — `core.py` 的 `get_detector()` 添加模块级缓存，避免重复导入
- **角度规范化** — `crop_item.py` 复用 `utils/rotation.py` 的 `normalize_angle()`
- **命名常量** — `cv_algorithm.py` 提取 22 个命名常量替代 magic numbers
- **EnhancedCV 废弃标记** — 添加 `DeprecationWarning`
- **YOLO-World 异步加载** — 新增 `load_async()` 方法，后台线程加载模型不阻塞 UI
- **platformdirs** — `yolo_world_detector.py` 使用 `platformdirs.user_cache_dir` 管理模型缓存
- **ruff 配置** — `pyproject.toml` 添加 `[tool.ruff]`（E/F/W/I/UP/B 规则）
- **mypy 配置** — `pyproject.toml` 添加 `[tool.mypy]`

### P3 — 长期优化

- **CombinedDetector 投票融合** — 从简单并集改为 IoU 投票策略（双检测器匹配 → 高置信度，单检测器 → 低置信度）
- **CONTRIBUTING.md** — 添加贡献指南
- **用户配置系统** — 新增 `photocrop/config.py`，支持 `~/.config/photocrop/config.yaml`
- **PDF 进度条** — 批量模式添加 `\r处理中: 第 X/Y 页...` 进度显示
- **撤销/重做** — 新增 `photocrop/ui/undo_manager.py`，集成到 Canvas/MainWindow，支持 Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y

---

## v0.3.0 — 首次公开发布

- Engine：5 步检测流水线（检测 → 旋转估算 → 过滤 → 去重 → 限制数量）
- UI：PySide6 画布 + 可交互裁剪框（拖拽/缩放/旋转）
- Export：裁剪 + 旋转 + 去白边 + JPEG/PNG 双格式
- PDF：批量处理模式
- 检测器：CV / Enhanced CV / Combined / YOLO-World
