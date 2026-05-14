# Changelog

## v0.7.0 — 架构重构：控制器层 + 全局状态 + 文档同步（2026-05-14）

### 架构变更

- **控制器层** — 5 个控制器将业务逻辑从 MainWindow 中剥离，职责单一、可独立测试
  - `DetectionController` — 检测流程（单图 + 批量 PDF，QThreadPool）
  - `ExportController` — 导出流程（模板填充、进度信号）
  - `SessionController` — Session 生命周期（文件加载、页面切换、保存/恢复）
  - `ThemeController` — 主题切换（订阅者模式，自动分发颜色）
  - `ViewCoordinator` — 视图切换（Empty/Grid/Single，opacity 动画过渡）
- **AppState 全局状态** — Observable 状态容器，所有 UI 组件和 Controller 通过信号订阅数据变化
- **文档全面同步** — 10 个 MD/TOML 文件对齐代码实际状态

### 从 v0.6.4 继承的变更

本版本包含 v0.6.4 的全部变更（6 项 Bug 修复 + 新功能），详见下方 v0.6.4 条目。

---

## v0.6.4 — 第三轮修复：6 项 Bug 修复 + 新功能（2026-05-12）

### 新增文件

- **`ui/state.py`** — AppState 全局状态管理器（Single Source of Truth），SessionState + AppState 双层结构
- **`ui/controllers/`** — UI 控制器层（5 个控制器），负责业务逻辑编排，与 Qt Widget 解耦
  - `detection_controller.py` — 检测流程（单图 + 批量 PDF），QThreadPool 后台线程
  - `export_controller.py` — 导出流程（模板填充、单页/全部导出、进度信号）
  - `session_controller.py` — Session 生命周期（文件加载、页面切换、保存/恢复）
  - `theme_controller.py` — 主题切换控制器（订阅者模式，自动分发颜色）
  - `view_coordinator.py` — 视图切换协调器（Empty/Grid/Single，opacity 动画过渡）
- **`ui/press_button.py`** — PressButton 组件，按下 scale(0.97) 缩放动画（80ms）
- **`ui/toast.py`** — Toast 通知组件（滑入 300ms + 停留 2.5s + 淡出 200ms，最多 3 个堆叠）
- **11 个新 SVG 图标** — brand-logo、brand-logo-large、download、image、layout-grid、moon、redo、refresh-cw、scan-eye、trash、undo、upload

### Bug 修复

| # | 问题 | 文件 |
|---|------|------|
| 73 | Undo 历史在 Session 切换时丢失 — serialize/deserialize 改为保存完整双栈 | `undo_manager.py` + `state.py` |
| 74 | 拖拽导入功能缺失 — 新增 dragEnter/Move/Leave/Drop 事件 + 遮罩反馈 | `canvas.py` + `main_window.py` |
| 75 | Loading 指示器缺失 — canvas 遮罩 + Toast 通知系统 | `canvas.py` + `toast.py` + `main_window.py` |
| 76 | 主题切换颜色过渡缺失 — 350ms cubic-bezier 插值动画 | `theme.py` |
| 77 | 检测算法选择器缺少说明 — 每个检测器 Tooltip | `main_window.py` |
| 78 | 导出对话框表单验证缺失 — 目录验证 + 模板验证 + QSettings 持久化 | `export_dialog.py` |

### 新功能

- **AppState 全局状态** — Observable 状态容器，所有 UI 组件和 Controller 通过信号订阅数据变化
- **控制器架构** — 5 个控制器将业务逻辑从 MainWindow 中剥离，职责单一、可独立测试
- **PressButton 动画** — 按钮按下 scale(0.97) + 80ms 缓动
- **主题切换动画** — 350ms cubic-bezier(0.4, 0, 0.2, 1) 颜色插值过渡
- **Toast 通知** — 非模态滑入通知，最多 3 个堆叠
- **拖拽导入** — 支持 8 种格式拖拽到画布，半透明遮罩 + 虚线框反馈
- **检测器 Tooltip** — 检测器下拉框切换时显示详细说明
- **导出表单验证** — 目录空时按钮置灰 + 红色提示，模板变量实时验证，QSettings 持久化

### UndoManager 序列化变更（向后兼容）

- `serialize()` 返回 JSON 字符串（新格式）而非 dict 列表（旧格式）
- `deserialize()` 接受 `str | list`，自动识别新旧格式

### 测试

- **6 个新测试文件** — `test_comprehensive_features.py`（106 个测试）、`test_state.py`、`test_export_controller.py`、`test_session_controller.py`、`test_global_preview.py`、`conftest.py`（共享 fixture）
- **总计 123 个测试通过**

---

## v0.6.3 — 第二轮设计审查 + Signal/State 一致性修复（2026-05-12）

### UI 美学/实用性改进（18 项）

**第一轮（8 项）：**
- **工具栏分组** — Import → Detect → Clear 操作区和 Undo/Redo 编辑区之间加分隔线
- **空状态引导** — 新增提示文字"拖入图片或点击 + Import 开始"
- **底栏降噪** — 版本号移入窗口标题，状态栏只显示 `N images · M crops`
- **Dark 模式虚线对比度** — 裁剪框未选中虚线 `#555` → `#6E6E`
- **属性面板标签重排** — 标签左对齐 12px，单位移入 SpinBox suffix
- **列表选中态** — Dark 模式从 `rgba(255,255,255,0.12)` 改为不透明 `#2A2A2A`
- **禁用文字对比度** — Dark 模式 `text_disabled` `#505050` → `#606060`
- **Zoom 按钮对齐** — Fit/1:1 按钮固定宽度 36px

**第二轮（9 项）：**
- **提取面板卡片 hover** — Dark 模式从透明色改 `selected_bg`
- **Single View 返回按钮 hover** — 从 `#80808020` 改 `hover_bg`
- **右侧面板分隔线** — Crop Options 和 Extracted Images 之间加分隔线
- **Single View 预览背景** — 统一为画布背景色
- **空状态图标** — 透明度 15% → 25%
- **Reset 按钮字号** — 10px → 11px
- **ComboBox 下拉选中** — 深色模式从纯白改 `accent_hover`
- **Header 缩进** — 字面空格 → CSS `padding-left`
- **PDF 子项缩进** — 2px 左边框指示线

### Bug 修复

- **Single 按钮点击后空白** — 底部 Single 按钮只切换视图不填充数据。修复：`_on_single_clicked()` 自动获取选中裁剪框并填充 SingleView
- **_on_rects_changed 不刷新按钮** — 裁剪框操作后 Undo/Redo/Clear 按钮状态不更新。修复：添加 `_update_button_states()` 调用
- **_on_crop_options_finished 不刷新按钮** — push undo state 后按钮未更新
- **pyproject.toml 版本号不一致** — 0.5.2 → 0.6.3
- **ExportDialog 硬编码亮色主题** — 重构为 `_apply_theme_stylesheet()`，从 ThemeManager 动态取色

### 测试

- **106 个新测试** — `tests/test_comprehensive_features.py`：CropRect 边缘情况、UndoManager 完整生命周期、手柄位置检测、工具栏按钮、模板填充、AppState/SessionController/Engine/Export/Theme 全覆盖
- **全部 184 个测试通过**（78 原有 + 106 新增）

---

## v0.6.2 — SVG 图标系统（2026-05-11）

### SVG 图标系统

- **11 个 SVG 图标** — sun/moon/chevron-left/right/down/up/eye/x/rotate-ccw/rotate-cw/copy
- **`get_icon(name, color)` 加载器** — QSvgRenderer 渲染，运行时注入颜色，内置缓存
- **修复主题切换按钮空白** — 从 Unicode emoji 迁移到 SVG
- **修复 QComboBox/QSpinBox 黑方块箭头** — 删除不生效的 CSS border 三角技巧
- **修复裁剪框工具栏 tofu** — SF Pro Icons 从 font-family 链中移除（9 处）

### 工具栏交互修复

- **5 按钮工具栏** — 新增 `rotate-cw.svg`，mousePressEvent 映射 5 个按钮索引
- **CropItem boundingRect 扩展** — 向上扩展 36px 包含工具栏区域，修复按钮不可交互
- **工具栏选中即显示** — 不再仅 hover 显示

---

## v0.6.1 — UI 主题修复（2026-05-10）

### 主题系统重构

- **4 个面板 Dark 主题适配** — image_list / crop_options / extracted_images / single_view
- **_PanelColors dataclass** — 各面板独立颜色数据类，`_build_ui()` / `_apply_styles()` 分离
- **CropItem 主题支持** — `set_theme_colors()` + `_TOOLBAR_BG` / `_SURFACE` 全局变量
- **Undo/Redo 按钮动态启用** — 根据 `can_undo()` / `can_redo()` 实时更新
- **Canvas zoom_changed 信号** — 底栏 Zoom 百分比响应滚轮
- **批量检测后撤销** — `_restore_rects` 后 `_push_undo_state()`
- **DeviceCoordinateCache → ItemCoordinateCache** — 消除变换伪影
- **提取面板缓存键** — `id()` → 确定性 `image.size`
- **theme.py 清理** — 删除 QToolBar 死代码、修复无效 opacity、新增 QMenu/QComboBox 样式

---

## v0.6.0 — 1:1 复刻 HTML 参考 UI（2026-05-09）

### 架构变更

- **三页 QStackedWidget** — Empty State / Canvas / SingleView
- **ThemeManager 单例** — Light/Dark 双模式 18 个颜色 token + `generate_stylesheet()`
- **BrandIcon 绘制组件** — QPainter 双层方框
- **全局主题系统** — `theme.toggle()` → `_apply_theme()` 统一刷新
- **工具栏 44px 重排** — BrandIcon + BrandText + 所有按钮统一 28px 高 + AlignVCenter
- **检测器下拉 QComboBox** — 110px 宽
- **裁剪框工具栏 5 按钮** — 深色浮层 + SVG/Unicode 图标
- **手柄 8×8 方块** — 9 个手柄 + 旋转手柄虚线连接线

### 19 个 Bug 修复（BUG-047 至 BUG-065）

- 导出 is_current 逻辑、CropRect 浅拷贝、_current_key 时序、跨页预览导航、键盘快捷键、复制框类型、导出文件名覆盖、PDF page_loader 性能、模板自定义格式等

---

## v0.5.3 — 黑白极简 UI 迁移 + 表单布局重构（2026-05-10）

### UI 设计系统迁移

- **Apple Blue → 黑白极简** — 全部 8 个 UI 文件从 `#0071e3` 蓝色系迁移到 `#000000` 纯黑白配色
- **颜色常量统一** — `PANEL_BG`、`TEXT_PRIMARY`、`TEXT_SECONDARY`、`APPLE_BLUE` 等常量全部更新
- **样式表重写** — `main_window.py` 的 `STYLE_SHEET` 完整重写（工具栏、按钮、输入框、下拉框、状态栏）
- **工具栏保持深色浮层** — `crop_item.py` 的裁剪框浮动工具栏保持 `QColor(0,0,0,160)` + 白色文字，确保在任何图片上可见
- **选中项极浅灰背景** — `image_list_panel.py` 选中项用 `rgba(0,0,0,0.08)` + 黑左边框 3px，不用纯黑底

### 布局与交互重构

- **crop_options_panel.py 完整重构** — 从 QFormLayout 改为自定义 56px 标签列布局，标签与单位分行显示（如 "Width" + "px"），行间距 6→10px，面板内边距 10→16,12，输入框高度 22→24px
- **底部栏紧凑化** — 高度从 44px 减至 28px，左侧显示版本+状态，右侧 View Toggle（纯文字 bold/gray）+ Export（实心黑底）
- **工具栏按钮描边风格** — 新增 `[toolbar="true"]` 属性，工具栏按钮改为透明底 + #D0D0D0 描边，区别于全局黑底主按钮
- **Export 按钮实心化** — 底部 Export 按钮从描边 secondary 改为实心黑底白字
- **View Toggle 纯文字** — Grid/Single 切换从黑底/描边改为纯文字 bold(黑)/gray

### 涉及文件

- `photocrop/ui/main_window.py` — 颜色常量、STYLE_SHEET、底部栏、工具栏按钮、Export、View Toggle
- `photocrop/ui/canvas.py` — 画布背景 `#E8E8E8`、框选矩形黑色
- `photocrop/ui/crop_item.py` — 颜色常量、虚线边框 `#666`、工具栏深色浮层
- `photocrop/ui/crop_options_panel.py` — 完整重构（56px 标签列 + 分行标签）
- `photocrop/ui/export_dialog.py` — 颜色常量、样式表、导出全部按钮
- `photocrop/ui/extracted_images_panel.py` — 颜色常量、滚动条 4px、hover、缩略图占位
- `photocrop/ui/image_list_panel.py` — 颜色常量、选中项、右键菜单、缩略图占位
- `photocrop/ui/single_view_panel.py` — 颜色常量、预览面板、高亮框

---

## v0.5.2 — Bug 修复 + PDF 功能增强（2026-05-09）

### PDF 功能增强

- **PDF 全局跨页预览** — `extracted_images_panel.py` 全局模式显示 PDF 所有页面的裁剪框，按 Page 分组，当前页高亮，支持跨页点击选中/删除
- **PDF 多页展开** — `image_list_panel.py` 左侧列表 PDF 展开为父项 + N 个带缩略图的子项
- **PDF 页面预览缓存** — `session.py` 新增 `_page_preview_cache`（160×160 小图），独立于 LRU 页面缓存，PDF 加载时一次性填充
- **裁剪框旋转 90°** — `crop_item.py` 浮动工具栏新增 ↺/↻ 按钮，逆时针/顺时针 90° 旋转并推入撤销栈

### Bug 修复（17 项）

- **detect() 未 emit rects_changed** — 检测完成后预览面板为空。修复：`detect()` 改为直接清除 items，添加完后 `_push_undo_state()` + `rects_changed.emit()`
- **PageDetectionTask 被 GC 回收** — PDF 批量检测信号丢失。修复：`tasks` 改为实例属性 `self._batch_tasks`
- **_save_current_session PDF 初始状态保存错字段** — `_current_key` 不含 `::page_` 时走 elif 分支，保存到 `sess.crop_rects` 而非 `page_crop_rects`。修复：elif 分支增加 `sess.is_pdf` 判断
- **_on_export 导出前未保存当前页** — canvas 上的最新修改未同步到 session。修复：`_on_export` 开头调用 `_save_current_session()`
- **导出时 page_key 与 _current_key 永不匹配** — `page_key` 永远不等于 `_current_key`。修复：增加 `is_current` 匹配条件（3 处）
- **PDF page_loader 重新渲染整个 PDF** — `pdf_to_images(path, dpi=200)` 每次渲染所有页只为取 1 页。修复：改用 `fitz.open()` 只渲染目标页
- **导出文件名模板不支持自定义格式** — 硬编码 `.replace("{index:02d}", ...)` 只支持 02d。修复：新增 `_fill_template()` 静态方法，正则匹配支持 `{index:N}` 任意格式
- **极小图片导致引擎崩溃** — `classify_scene` 无最小尺寸检查。修复：`w < DOWNscale_FACTOR * 2` 时跳过检测
- **CropRect.from_pixel_rect 不验证参数** — 反序坐标产生负 width/height。修复：自动交换坐标 + 抛 ValueError
- **pil_to_qimage 丢失 LA/P alpha** — 只处理 RGBA 和 RGB。修复：LA/PA 模式先 convert("RGBA")
- **CombinedDetector 依赖已废弃 EnhancedCVDetector** — 每次初始化触发 DeprecationWarning。修复：同步标记为废弃
- **CLI --detector 缺少 model** — choices 与 get_detector() 不一致。修复：添加 "model"
- **Canvas.clear_all() 未释放 source_image** — 大图像内存无法回收。修复：添加 `self._source_image = None`
- **ImageSession._page_cache 无锁** — 多线程竞态条件。修复：添加 threading.Lock
- **ExportDialog 必选参数** — 无法独立构造。修复：参数改为可选（默认 0）
- **TemplateManager API 不一致** — apply_template 需要 CropTemplate 对象。修复：新增 `apply_template_by_name()` 便捷方法
- **预览面板裁剪缩略图显示问号** — `_refresh_global_preview` 传给 ExtractedImagesPanel 的 pages_data 是 160×160 缩略图，crop_rect 坐标基于全尺寸图，裁剪框超出图片范围。修复：改用 `get_page_image()`（全尺寸，LRU 缓存）

### CI 修复

- **ruff lint 199 处报错** — v0.5.1 提交后 CI 失败。修复：`ruff --fix` + `ruff --fix --unsafe-fixes`（类型注解现代化：List→list、Optional→X|None、Union→X|Y）+ 手动修复 4 处 B904 + pyproject.toml 添加 E402 到 ignore。31 个文件已提交。

### 第二轮 Bug 修复（2026-05-09）

- **BUG-047 导出 is_current 判断逻辑错误** — 当 `_current_key` 是 PDF 父键时，`is_current` 判断逻辑可能导致当前页的裁剪框使用了 session 中保存的旧数据。修复：统一 `is_current` 判断逻辑（`_on_export`、`total_crops` 计算、`_update_image_list_panel` 三处）
- **BUG-048 CropRect 浅拷贝导致切页后检测框变化** — `_save_current_session` 和 `_on_rects_changed` 用 `list()` 保存裁剪框，CropRect 对象是 CropItem 内部持有的同一引用。修复：所有保存到 session 的位置改为 `[copy.deepcopy(r) for r in self._canvas.crop_rects]`
- **BUG-049 _current_key 时序错误导致切页数据串页** — `_switch_image` 中 `_current_key` 的赋值放在 `load_pil_image` 和 `_restore_rects` 之后，这些方法发射的 `rects_changed` 信号用旧 `_current_key` 保存数据，导致旧页面 session 槽被新页面数据污染。修复：在操作 canvas 之前先快照目标页数据、更新 `_current_key`、再用快照恢复 canvas（`_switch_image` PDF+非PDF 两分支，`_load_single_file` 非PDF 分支）
- **BUG-050 跨页预览面板点击无法切换页面** — `_on_extracted_crop_selected` 中 `select_image` 内部 `_block_signal = True` 阻止了 `_switch_image` 的触发。修复：`select_image` 之后显式调用 `_switch_image`（选中+删除两处）
- **BUG-051 ← → 键盘快捷键 session 模式 PDF 失效** — `_on_prev_page` / `_on_next_page` 调用 `canvas.prev_page()` / `canvas.next_page()`，走的是 `_pdf_pages` 列表（session 模式下永远为空）。修复：新增 `_get_sibling_page_key()` 方法，优先使用 image_list_panel 导航，非 PDF 回退到 canvas 原有逻辑
- **BUG-052 复制裁剪框 source_type 错误** — `_on_crop_copy` 创建新 `CropRect` 时拷贝了原框的 `source_type`。修复：复制框 `source_type` 强制设为 `"manual"`
- **导出文件名模板缺少 {page}** — 默认模板 `{name}_{index:02d}.{ext}` 无 `{page}` 变量，多页 PDF 导出时不同页产生相同文件名互相覆盖。修复：默认模板改为 `{name}_p{page}_{index:02d}.{ext}`
- **导出成功消息不显示输出路径** — 用户不知道文件写到哪里。修复：对话框和状态栏均显示完整输出路径
- **config.py 裸 except Exception** — `_load_yaml()` 和 `save_config()` 中两处裸 except。修复：改为 `(OSError, ValueError, AttributeError)`
- **ruff B007 + 测试清理** — 未使用的循环变量 `key` 改为 `_key`；删除重复的中文命名测试文件 `test_export尺寸匹配.py`，合并到 `test_export_bug.py`（新增 3 个测试用例，共 6 个）；修复测试文件 `return` → `assert` 警告

---

## v0.5.1 — Bug 修复 + 代码质量（2026-05-07）

### Bug 修复

- **clear_crops() 后无法撤销** — `canvas.py` 清除操作前未保存状态到撤销栈。修复：在清除前调用 `_push_undo_state()`
- **拖拽新建裁剪框后无法撤销** — `canvas.py` mouseReleaseEvent 中新建框后未推入撤销栈。修复：新建后调用 `_push_undo_state()`
- **属性面板选中后不显示** — `main_window.py` 的 `_on_selection_changed` 在无选中时传入 None 覆盖已有数据；`crop_options_panel.py` 的 `set_selected_rect` 缺少防御。修复：无选中时直接 return + 防御 None 覆盖
- **pyproject.toml build-backend 错误** — `setuptools.backends._legacy:_Backend` 不存在导致 `pip install -e .` 失败。修复：改为 `setuptools.build_meta`
- **TemplateManager str 路径崩溃** — 传入 str 时 `config_dir / "templates.json"` 报 TypeError。修复：`Path(config_dir)` 确保类型
- **GUI 启动跳过 session 创建** — `main.py` 中 `load_image()` 不经过 `_load_single_file()`，左侧图片列表空白。修复：改为调用 `_load_single_file()`
- **导出文件名模板未使用** — ExportDialog 有模板输入框但 `_on_export()` 硬编码格式。修复：从 config 读取模板并解析 `{name}`/`{page}`/`{index}`/`{ext}` 变量

### 代码质量

- **_pil_to_qimage 去重** — 4 个文件中的重复 `_pil_to_qimage` / `_pil_to_pixmap` 实现抽取到新建的 `ui/utils.py`，统一调用

---

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
- **裁剪框浮动工具栏** — `crop_item.py` 选中时显示 ⛶查看 / 📋复制 / ↺逆时针 / ↻顺时针 / ✕删除 五个按钮，hover 高亮

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
