# PhotoCrop 项目上下文

> 供 Claude 在 PhotoCrop 项目工作时自动加载。涵盖项目全貌、架构、经验教训。
> 通用用户偏好和工作流规则在 Claude 记忆系统中（MEMORY.md）。

---

## 一、项目概览

**目标：** 从扫描的 PDF 相册页面中自动检测照片矩形，支持手动微调（放大/缩小/旋转），然后批量裁剪导出。

**版本：** 0.5.1（v0.5.0 + Bug 修复 + 代码去重）

**技术栈：** Python 3.9, PySide6 (Qt GUI), OpenCV 4.13, scipy 1.10+, numpy 2.2, Pillow 9.5+, PyMuPDF 1.23+, platformdirs 3.0+

**运行环境：** macOS（MacBook Air），用户 Python 3.9，pip 21.2.4

**GitHub：** https://github.com/Reyes957/PhotoCrop

### 安装

```bash
# 推荐方式（开发模式 + GUI 依赖）
pip install -e ".[gui]"

# 全量安装（含 YOLO-World）
pip install -e ".[all]"

# 或用 requirements.txt
pip install -r requirements.txt
```

---

## 二、项目结构

```
photocrop/
├── main.py           # CLI/GUI/PDF 三模式入口（logging 配置）
├── config.py         # 用户配置系统（~/.config/photocrop/config.yaml）
├── engine/           # 检测引擎（5步流水线）
│   ├── core.py              — 编排 + 检测器工厂 get_detector()（模块级缓存）
│   ├── cv_algorithm.py      — 原始 CV 算法（22个命名常量，不可修改检测逻辑）
│   ├── detector.py          — 兼容 shim → cv_algorithm.py
│   ├── detector_base.py     — BaseDetector 抽象基类
│   ├── cv_detector.py       — CVDetector 封装
│   ├── enhanced_cv_detector.py — 增强 CV（已标记 DeprecationWarning）
│   ├── combined_detector.py — 组合检测器（IoU 投票融合，非简单并集）
│   ├── yolo_world_detector.py — YOLO-World（异步加载 + platformdirs 缓存）
│   ├── model_detector.py    — 模型检测器（通用占位）
│   ├── rotation_estimator.py — 旋转角度估算（小角度 + ±90°）
│   ├── rotation.py          — 兼容 shim → rotation_estimator.py
│   └── filters.py           — 小框过滤、IoU去重、数量限制
├── ui/               # PySide6 GUI（Apple 极简设计）
│   ├── main_window.py           — 主窗口（工具栏、状态栏、快捷键、防抖、多图 session、全局预览集成）
│   ├── canvas.py                — 画布（图片显示、框选、缩放、撤销/重做、同步/翻转、旋转 90°）
│   ├── crop_item.py             — 可交互裁剪框（旋转渲染、回调模式、5 按钮浮动工具栏、宽高比锁定）
│   ├── undo_manager.py          — 撤销/重做状态管理器（支持序列化/反序列化）
│   ├── session.py               — ImageSession 数据类（单张图像会话状态、PDF 页面预览缓存）
│   ├── image_list_panel.py      — 左侧图像列表面板（缩略图 + 文件名 + 裁剪计数、PDF 多页展开）
│   ├── crop_options_panel.py    — 右侧裁剪框属性面板（Width/Height/X/Y/Rotation/Aspect Ratio）
│   ├── extracted_images_panel.py — 裁剪结果预览面板（2 列网格、LRU 缓存、PDF 全局跨页预览）
│   ├── single_view_panel.py     — Single View 大图预览（左缩略 + 右提取大图）
│   ├── export_dialog.py         — 批量导出设置对话框（格式/质量/尺寸限制/文件名模板）
│   ├── template_manager.py      — 裁剪框模板管理器（百分比坐标，跨图片复用）
│   └── utils.py                 — UI 工具函数（pil_to_qimage / pil_to_pixmap 统一转换）
├── export/           # 导出模块
│   ├── cropper.py      — 裁剪 → 旋转 → 去白边 → 保存（JPEG/PNG/TIFF）+ EXIF 写入 + export_photo_to_memory
│   └── pdf_reader.py   — PDF → PIL Image
└── utils/            # 工具层
    ├── crop_rect.py    — CropRect 数据类（中心坐标系统）
    ├── rotation.py     — 角度规范化与转换（纯数学工具）
    └── iou.py          — 统一 IoU 计算

tests/                # 测试目录（pytest）
├── test_engine.py           — 引擎测试（pytest 类 + fixture）
└── test_global_preview.py   — 全局预览模式测试（预览缓存、索引映射、跨页数据流）

.github/workflows/
└── ci.yml            — CI 流水线（Python 3.9-3.12 + ruff + pytest）

pyproject.toml        — 包配置 + ruff + mypy
CONTRIBUTING.md       — 贡献指南
```

---

## 三、检测器架构

**工厂函数（core.py，带模块级缓存）：**
- `detector=None` 或 `"cv"` → CVDetector（默认）
- `"enhanced-cv"` → EnhancedCVDetector（已废弃，会触发 DeprecationWarning）
- `"combined"` → CombinedDetector（IoU 投票融合）
- `"yolo-world"` → YOLOWorldDetector（支持 `load_async()` 异步预加载）
- `"model"` → ModelDetector（占位）
- `<BaseDetector 实例>` → 直接使用

**设计模式：** ABC + 工厂。BaseDetector 抽象基类 + get_detector() 工厂让后续接入任何检测器都很简单，只需实现 detect() 方法。类似的可替换组件（如导出器、过滤器）也用同样的模式。

### 检测器对比

| 检测器 | 标识 | 速度 | 质量 | 依赖 |
|--------|------|------|------|------|
| CV（默认）| `cv` | 快 | 中（3.6/页）| 无 |
| 增强 CV（废弃）| `enhanced-cv` | 快 | 低（漏检多）| 无 |
| 组合（投票融合）| `combined` | 中 | 中 | 无 |
| YOLO-World | `yolo-world` | 慢* | 待验证 | torch+ultralytics+CLIP |

### YOLO-World 状态（2026-05-05）

- 代码已实现：`yolo_world_detector.py`，实现 BaseDetector 接口
- 模型文件：`yolov8x-worldv2.pt`（140MB）已在项目目录
- 依赖：`pip install -e ".[yolo]"`
- **异步加载：** `load_async()` 在后台线程加载模型，不阻塞 UI；`detect()` 自动等待加载完成
- **缓存管理：** 使用 `platformdirs.user_cache_dir("photocrop")` 管理模型缓存
- **未验证：** VM 网络太慢装不了 PyTorch，在用户 Mac 上依赖已装好但测试脚本未跑完

### 模型推荐

- **首选：YOLO-World** — 零样本、速度快（~30-50ms/页）、ultralytics 生态成熟
- **备选：Grounding DINO** — 框选精度更高但更慢（~200-500ms/页）
- **第三：Florence-2** — 轻量（0.23B/0.77B）、多功能，但对矩形检测不是最优
- **不推荐：SAM** — 像素分割过重，后处理复杂

---

## 四、测试样本分析

7 个 PDF，共 28 页，涵盖 5 种页面类型：

1. **规整网格**（021080、021081、021083 p0）— 2列2-4张，CV 处理好
2. **上下双图**（021082、021083 p1-p2）— CV 处理好
3. **单图整页**（021083 p3、021092 p1）— 最简单
4. **复杂混合**（021110 大部分页面）— 大小不一、位置不规则，CV 容易漏检
5. **照片贴边**（021110 p5）— 边缘检测被干扰

CV 算法在复杂混合布局（021110 系列）上表现最差，这是 YOLO-World 的主要提升目标。

---

## 五、核心 Bug 修复记录

1. **裁剪框删除引用泄漏** — `_on_crop_deleted` 原来用 `self.sender()`（Qt Signal），但 CropItem 用普通回调，`sender()` 永远返回 None。修复：lambda 捕获 item 引用
2. **旋转手柄是摆设** — `mouseMoveEvent` 里空执行。修复：atan2 角度计算，吸附 0°/90°/-90°/180°（±15°），手柄旁显示角度值
3. **重复检测叠加** — 每次点"检测照片"新框叠加到旧框上。修复：`detect()` 开头先 `clear_crops()`
4. **窗口缩放重置视角** — `resizeEvent` 的 `fitInView` 重置手动缩放。修复：只在加载图片时适配一次
5. **导出固定 JPEG** — `_on_export` 硬编码 `.jpg`。修复：弹窗选择 JPEG（白色填充）或 PNG（透明）
6. **IoU 计算统一** — 原来 filters.py、combined_detector.py、enhanced_cv_detector.py 各有一份。统一到 `utils/iou.py`
7. **版本号硬编码** — main.py 的 `setApplicationVersion("0.2.0")` 写死版本号。修复：改为从 `photocrop.__version__` 动态读取
8. **命名冲突** — `detector.py`（CV 算法）与 `detector_base.py`（抽象基类）名称混淆。修复：重命名为 `cv_algorithm.py`，旧路径保留兼容 shim
9. **rotation 模块重叠** — `engine/rotation.py`（CV 估算）与 `utils/rotation.py`（纯数学工具）分工不清。修复：重命名为 `rotation_estimator.py`，旧路径保留兼容 shim
10. **测试文件位置** — `test_engine.py` 放在源码目录内。修复：移至 `tests/` 独立目录
11. **框太容易新建** — 单击空白处即创建裁剪框。修复：30px 最小拖动阈值，延迟创建临时矩形
12. **拖动裁剪框残影** — Minimal ViewportUpdateMode + 信号风暴。修复：FullViewportUpdate + ItemSendsGeometryChanges + _on_changed 延迟到 release
13. **按钮样式异常** — `setProperty("secondary", True)` 传 Python bool，QSS 匹配字符串 `"true"`。修复：改为字符串
14. **旋转 paint 未应用变换** — 设置旋转角度后视觉上不旋转。修复：paint() 添加 painter.save/rotate/restore
15. **裸 except Exception** — 5 处过于宽泛的异常捕获。修复：改为具体异常类型
16. **rects_changed 信号风暴** — 拖动框时按钮频繁刷新。修复：50ms QTimer 防抖
17. **QImage bytesPerLine 缺失** — PIL `tobytes("raw","RGB")` 返回紧凑数据，QImage 未显式指定 bytesPerLine 导致大图对角线条纹。修复：4 个文件的 `_pil_to_qimage` / `_pil_to_pixmap` 显式传入 `width * bytes_per_pixel`
18. **CropOptionsPanel removeRow 删 C++ 对象** — `form_layout.removeRow()` 会删除已添加的 QLabel，导致 RuntimeError。修复：先构建含 SpinBox+Reset 的 widget 再一次性 addRow
19. **clear_crops() 后无法撤销** — 清除操作前未保存状态到撤销栈。修复：在清除前调用 `_push_undo_state()`
20. **拖拽新建裁剪框后无法撤销** — mouseReleaseEvent 中新建框后未推入撤销栈。修复：新建后调用 `_push_undo_state()`
21. **属性面板选中后不显示** — `_on_selection_changed` 在无选中时传入 None 覆盖已有数据。修复：无选中时直接 return + `set_selected_rect` 防御 None 覆盖
22. **pyproject.toml build-backend 错误** — `setuptools.backends._legacy:_Backend` 不存在，`pip install -e .` 失败。修复：改为 `setuptools.build_meta`
23. **TemplateManager str 路径崩溃** — 传入 str 时 `config_dir / "templates.json"` 报 TypeError。修复：`Path(config_dir)` 确保类型
24. **GUI 启动跳过 session 创建** — `load_image()` 不经过 `_load_single_file()`，左侧列表空白。修复：改为调用 `_load_single_file()`
25. **导出文件名模板未使用** — ExportDialog 有模板输入框但 `_on_export()` 硬编码格式。修复：从 config 读取模板并解析变量
26. **_pil_to_qimage 重复定义** — 4 个文件各有一份相同实现。修复：抽取到 `ui/utils.py`，四处统一调用

---

## 六、已知限制

- 旋转估计对小角度（2-5°）精度取决于图像质量
- ModelDetector 仍为占位
- 不支持自动吸附（按设计）
- 用户配置系统依赖可选的 pyyaml（无 pyyaml 时使用默认值）

---

## 七、v0.3.1 新增功能

- **撤销/重做** — `undo_manager.py` + Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y
- **键盘快捷键** — Ctrl+O/D/E、← →、Delete/Backspace
- **用户配置** — `config.py` + `~/.config/photocrop/config.yaml`
- **YOLO 异步加载** — `load_async()` 后台线程预加载
- **CombinedDetector 投票融合** — IoU 匹配 → 双检测器高置信度
- **CI/CD** — GitHub Actions（Python 3.9-3.12 + ruff + pytest）
- **工程化** — pyproject.toml、ruff、mypy、pytest、logging、platformdirs

## 七(2)、v0.5.0 新增功能

- **多图像管理** — `session.py` + `image_list_panel.py`，左侧 220px 面板，缩略图 + 文件名 + 裁剪计数，右键菜单（重新检测/移除）
- **裁剪框属性面板** — `crop_options_panel.py`，Width/Height/X/Y/Rotation 实时编辑，editingFinished 推入撤销栈
- **宽高比锁定** — CropOptionsPanel 下拉框 (Free/Original/1:1/3:2/4:3/16:9)，CropItem 拖拽手柄时保持比例
- **裁剪结果预览** — `extracted_images_panel.py`，2 列网格，LRU 缓存，点击选中/删除
- **Single View** — `single_view_panel.py`，双栏布局（左原图缩略 + 右提取大图），页码导航
- **Grid/Single 视图切换** — 底部按钮栏，QStackedWidget 切换
- **批量导出对话框** — `export_dialog.py`，格式 (JPEG/PNG/TIFF)、质量、最大宽高、文件名模板、自动旋转/去白边
- **键盘快捷键扩展** — Tab/Shift+Tab 循环选中、Ctrl+A 全选、Ctrl+Click 多选、Esc 取消选中
- **Sync Crop(s)** — 将最后选中的裁剪框 width/height/rotation 同步到其他选中框
- **Transform 翻转** — 水平/垂直翻转选中裁剪框坐标
- **裁剪框浮动工具栏** — 选中时显示 ⛶查看 / 📋复制 / ↺逆时针 / ↻顺时针 / ✕删除 五个按钮
- **模板系统** — `template_manager.py`，百分比坐标存储，跨图片复用
- **TIFF 导出** — LZW 压缩
- **EXIF 写入** — Title/Date/Comment/Tags，仅 JPEG/TIFF
- **export_photo_to_memory** — 导出到内存不保存文件，用于预览
- **UndoManager 序列化** — `serialize()` / `deserialize()` 支持多图 session 状态保存/恢复
- **裁剪框旋转 90°** — 浮动工具栏 ↺/↻ 按钮，顺时针/逆时针 90° 旋转并推入撤销栈
- **PDF 多页展开** — `image_list_panel.py` 左侧列表 PDF 展开为父项 + N 个带缩略图的子项
- **PDF 全局跨页预览** — `extracted_images_panel.py` 全局模式显示 PDF 所有页面的裁剪框，按 Page 分组，当前页高亮，支持跨页点击选中/删除
- **PDF 页面预览缓存** — `session.py` 的 `_page_preview_cache` 独立于 LRU 页面缓存，不被淘汰，避免全局刷新时重新渲染高 DPI 图像

---

## 八、PhotoCrop 工作流

- 用户想要本地模型先选候选框，然后手动微调（放大/缩小/旋转）→ 导出
- 不需要云端 API 的方案（倾向于本地离线模型）
- 优先考虑实际可行的方案，而非追求理论最优

### Agent 收尾：/neat 文档同步

每次在 Agent 会话中完成一轮实质性工作后，运行 `/neat`（或说"整理一下"/"同步一下"/"sync up"）。它会把本次会话的代码变更与三层文档对齐：

1. **CLAUDE.md / AGENTS.md**（给当前 AI 看的项目上下文）
2. **docs/ 和 README**（给同事和其他人看的文档）
3. **Agent 记忆系统**（给跨会话的自己看的记忆文件）

为什么需要：代码迭代多轮后文档容易过时——接口变了但 CLAUDE.md 里的列表没更新，记忆里写着旧方案但实际已换新方案。过期文档让 AI 越用越笨。`/neat` 就是清理这个"文档脑腐"的。

触发方式：`/neat`、`整理一下`、`同步一下`、`sync up` 均可。

---

## 九、项目专属经验教训

**DO：检测器架构抽象** — ABC + 工厂模式正确。BaseDetector + get_detector() 让后续接入任何检测器都很简单。类似的可替换组件也用同样的模式。

**DO：IoU 投票融合** — CombinedDetector 从简单并集改为投票策略后效果更好。两个检测器都检测到的区域置信度高，单个检测器独检的置信度低。多检测器融合应用"投票"或"交叉验证"策略。

**DON'T：组合检测器直接并集** — ~~CombinedDetector 将 CV + Enhanced 结果简单并集导致大量误检（135 vs 102）。~~ 已在 v0.3.1 修复为投票融合。

**DON'T：过度优化纯 CV** — 原始 extract_photos_from_page 算法效果最好（3.6/页平均）。增强版 CV（自适应阈值/Hough/形态学）反而更差。YOLO-World 等模型方案才是主要提升方向。

**DO：延迟创建 UI 元素** — 框选时不在 mousePressEvent 创建临时矩形，而是等到 mouseMoveEvent 超过阈值后才创建。避免单击闪现。

**DO：信号防抖** — 拖动等高频操作触发的信号用 QTimer 防抖（50ms），避免 UI 频繁刷新。

**DO：具体异常类型** — 不要用裸 `except Exception:`。根据上下文选择 `(ValueError, RuntimeError, OSError)` 等具体类型。

**DO：QImage 显式 bytesPerLine** — PIL `tobytes("raw","RGB")` 返回紧凑像素数据。`QImage(data, w, h, format)` 不传 bytesPerLine 时 Qt 自行推算，大图或非标准尺寸可能不匹配导致对角线条纹。必须显式传入 `width * bytes_per_pixel`。

**DON'T：formLayout.removeRow() 删除已有 widget** — Qt 的 `removeRow()` 会同时删除 label 和 field widget 的 C++ 对象。如果后续还要引用这些 widget 会触发 RuntimeError。应先构建完整 widget 再一次性 `addRow()`。

**DO：破坏性操作前保存撤销状态** — `clear_crops()`、拖拽新建等改变裁剪框列表的操作，必须在执行前调用 `_push_undo_state()`。否则用户无法撤销，数据丢失不可恢复。

**DO：防御性 None 处理** — Qt 信号可能被多次触发，`selection_changed` 之类的变化信号在某些时序下会先传入正确值再传入 None。对于"选中 → 更新面板"的流程，应在 handler 中对 None 做防御性判断，避免覆盖已有数据。

**DO：消除重复代码** — 同一个工具函数（如 `_pil_to_qimage`）出现在 3+ 个文件中时，应立即抽取到共享模块。重复代码是维护炸弹——改一处忘改其他处就是 bug。

**DO：提交前运行 ruff check** — CI 会跑 ruff，本地不过的代码推上去一定失败。代码写完 → `ruff check .` → 有错就 `ruff --fix --unsafe-fixes` → 手动修剩余 → 确认 0 错误 → 再提交。v0.5.1 因未预检导致 CI 失败，事后修了 31 个文件。

**DO：预览图用独立缓存** — 全局预览面板需要所有页面的缩略图。如果每次刷新都调 `get_page_image()`（LRU 缓存 5 页），28 页 PDF 每次拖动裁剪框会触发 23 次高 DPI 渲染。解决：`_page_preview_cache` 独立缓存，PDF 加载时一次性填充，不参与 LRU 淘汰。

**DO：跨页操作前保存状态** — 用户在全局预览中点击/删除其他页的裁剪框时，必须先 `_save_current_session()` 再切页。否则当前页的未保存编辑丢失。选中操作用 `QTimer.singleShot(0, ...)` 延迟执行，确保页面已加载。

> 通用工作流规则（文件安全、下载策略等）见 Claude 记忆系统中的 feedback_workflow.md。

---

*最后更新：2026-05-08*
