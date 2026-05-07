# Changelog

## v0.5.0 — 多图像管理 + 属性面板 + 批量导出 + Single View + 模板系统（2026-05-06）

### 阶段一：核心体验

- **UndoManager 序列化** — 新增 `serialize()` / `deserialize()` 方法，支持多图 session 状态保存/恢复
- **多图像管理** — 新增 `session.py`（ImageSession 数据类）+ `image_list_panel.py`（左侧 220px 图像列表面板，缩略图 + 文件名 + 裁剪计数 + 右键菜单）
- **裁剪框属性面板** — 新增 `crop_options_panel.py`（Width/Height/X/Y/Rotation 五个 SpinBox，实时更新裁剪框，editingFinished 推入撤销栈）
- **提取预览面板** — 新增 `extracted_images_panel.py`（2 列网格预览，LRU 缓存，点击选中/删除，折叠头）
- **批量导出对话框** — 新增 `export_dialog.py`（输出目录/格式 JPEG-PNG-TIFF/质量/最大宽高/文件名模板/自动旋转/去白边）；`cropper.py` 新增 `export_photo_to_memory()`、`_resize_if_needed()`、TIFF 支持
- **Single View** — 新增 `single_view_panel.py`（双栏布局：左原图缩略 + 右提取大图，页码导航）；`main_window.py` 使用 QStackedWidget 切换 Grid/Single 视图
- **键盘快捷键扩展** — `canvas.py` 新增 Tab/Shift+Tab 循环选中、Ctrl+A 全选、Ctrl+Click 多选、Esc 取消选中

### 阶段二：交互增强

- **Sync Crop(s)** — `canvas.py` 新增 `sync_selected_crops()`，将最后选中的裁剪框 width/height/rotation 同步到其他选中框
- **Transform 翻转** — `canvas.py` 新增 `flip_horizontal()` / `flip_vertical()`，以原图中心线翻转坐标
- **宽高比锁定** — `crop_item.py` 新增 `aspect_ratio_lock` 属性 + 拖拽手柄时保持比例；`crop_options_panel.py` 新增 Aspect Ratio 下拉框 (Free/Original/1:1/3:2/4:3/16:9)
- **裁剪框浮动工具栏** — `crop_item.py` 选中时显示 ⛶查看 / 📋复制 / ✕删除 三个按钮，hover 高亮

### 阶段三：高级功能

- **模板系统** — 新增 `template_manager.py`，百分比坐标存储，跨图片复用，`~/.config/photocrop/templates.json`
- **TIFF 导出** — `cropper.py` `_save_image()` 增加 TIFF LZW 压缩支持
- **EXIF 写入** — `cropper.py` 新增 `write_exif_metadata()`，支持 Title/Date/Comment/Tags，仅 JPEG/TIFF
- **export_photo_to_memory** — `cropper.py` 新增内存导出函数，用于预览面板和 Single View

### Bug 修复

- **QImage bytesPerLine 缺失** — 4 个文件的 `_pil_to_qimage` / `_pil_to_pixmap` 未显式指定 bytesPerLine，大图显示对角线条纹。修复：显式传入 `width * bytes_per_pixel`
- **CropOptionsPanel removeRow 删 C++ 对象** — `form_layout.removeRow()` 删除已添加的 QLabel 导致 RuntimeError。修复：先构建完整 widget 再 addRow

---

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
