# PhotoCrop

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Release](https://img.shields.io/github/v/release/Reyes957/PhotoCrop)
![Platform](https://img.shields.io/badge/Platform-macOS-lightgrey.svg)

[English](README.md)

从扫描的相册页面中自动检测并裁剪出单张照片的桌面应用。macOS 优先。

<p align="center">
  <img src="assets/light-mode.png" alt="PhotoCrop" width="800">
</p>

---

## 为什么做这个

我出生在 90 年代末。那时候家里拍照很少，人人都用胶片机。我仅有的几张童年照片，全是胶片拍的。它们已经不可能再被洗出来了，很多照片只剩纸质的。那些相册散落在家里各个角落，我可能每年过年回去才能翻开一次，看看旧时光。相册上的很多人，已经再也见不到了。

黄粱一梦，二十年过去了。

我想，你大概也是 90 前后出生的，也参加工作了。公司里肯定有带扫描功能的打印机，把那些老相册放进去吧，做出一份过去的 PDF。还有那些拍立得，它们都没有数字版，只有那张纸在。

我想把它们变成数字回忆。这是我做这个工具的原因。

这个工具的第一个用户是我自己。我做它的初衷，就是让那些记忆变成赛博回忆——从此它们可以在聊天里流转，在数据间流动，在硬盘上跟着我们一起走下去。而不是让那些旧相册慢慢遗忘在角落的柜子里，直到有一天相册上的人都已经离开，相册的拥有者已经不认识照片里的人，从而轻易地把那个相册丢掉。

PhotoCrop 只做一件事：把照片从扫描页面上干净地裁下来。没有 AI 增强，没有 AI 修复。当你看到一张模糊的老照片，脑海里浮现的那个人的样子，是任何算法都复现不了的。记忆里的面容比像素更真实。

裁出来的照片你当然可以拿去做 AI 修复，随你。但这个工具的目的就是裁剪——让你看到照片的时候能想起那个人，就够了。

整个检测流程跑的是本地离线模型，照片不会被上传到任何服务器，也不会被拿去训练。

---

## 目录

- [安装](#安装)
- [快速上手](#快速上手)
- [功能](#功能)
- [架构](#架构)
- [依赖](#依赖)

---

## 安装

```bash
git clone https://github.com/Reyes957/PhotoCrop.git
cd PhotoCrop
pip install -e ".[gui]"
```

YOLO-World（可选，零样本检测）：

```bash
pip install -e ".[all]"
```

或用 requirements.txt：

```bash
pip install -r requirements.txt
```

---

## 快速上手

### CLI — 单张图片

```bash
python -m photocrop.main page.jpg --max-count 4
```

### GUI — 图形界面

```bash
python -m photocrop.main --gui
python -m photocrop.main --gui page.jpg
```

### PDF — 批量处理

```bash
python -m photocrop.main --pdf album.pdf --output ./photos/
```

### 指定检测器

```bash
python -m photocrop.main page.jpg --detector enhanced-cv   # 默认
python -m photocrop.main page.jpg --detector cv
python -m photocrop.main page.jpg --detector combined
python -m photocrop.main page.jpg --detector yolo-world
python -m photocrop.main page.jpg --detector model
```

<details>
<summary>GUI 快捷键</summary>

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 加载图片/PDF |
| Ctrl+D | 检测照片 |
| Ctrl+E | 导出全部 |
| Ctrl+Z | 撤销 |
| Ctrl+Shift+Z / Ctrl+Y | 重做 |
| ← → | 上/下一页 |
| Delete / Backspace | 删除选中的裁剪框 |
| Tab / Shift+Tab | 循环选中裁剪框 |
| Ctrl+A | 全选裁剪框 |
| Ctrl+Click | 加选/减选 |
| Esc | 取消选中 |

</details>

---

<details>
<summary><h2 style="display:inline">功能</h2></summary>

- 多种检测引擎 — 增强 CV（默认，低质扫描表现更优）、传统 CV（边缘检测 + 形态学）、组合检测器（IoU 投票融合）、YOLO-World 零样本检测
- 可插拔检测器架构 — ABC 基类 + 工厂模式，可以自己写一个检测器接进去
- 三种运行模式 — CLI 命令行、GUI 图形界面、PDF 批量处理
- 控制器架构 — 5 个控制器（检测、导出、Session、主题、视图），业务逻辑和 Qt 控件解耦
- 全局状态管理 — AppState 容器 + 信号订阅
- 多图像管理 — 左侧面板：缩略图、文件名、裁剪计数，右键菜单
- 裁剪框属性面板 — 实时编辑 Width/Height/X/Y/Rotation，宽高比锁定
- 裁剪结果预览 — 2 列网格，LRU 缓存，点击选中或删除
- PDF 多页展开 — 左侧列表 PDF 展开为父项 + N 个子项
- PDF 全局跨页预览 — 所有页面的裁剪框，按 Page 分组，跨页选中/删除
- 裁剪框旋转 — 浮动工具栏逆时针/顺时针 90°
- Single View — 原图缩略 + 提取大图，页码导航
- 批量导出 — JPEG/PNG/TIFF，质量、最大宽高、文件名模板、自动旋转、去白边
- 模板系统 — 百分比坐标，跨图片复用
- 同步与翻转 — 同步选中框尺寸；水平/垂直翻转
- 智能导出 — 自动旋转矫正、去白边、EXIF 元数据
- Light/Dark 双主题 — 350ms 颜色过渡动画
- Toast 通知 — 非模态滑入，最多 3 个堆叠
- 拖拽导入 — 拖文件到画布，支持 8 种格式
- 撤销/重做 — Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y
- 多选 — Ctrl+Click、Ctrl+A、Tab/Shift+Tab、Esc
- 键盘快捷键 — Ctrl+O 加载、Ctrl+D 检测、Ctrl+E 导出、← → 翻页
- 用户配置 — `~/.config/photocrop/config.yaml` 持久化偏好

</details>

---

<details>
<summary><h2 style="display:inline">架构</h2></summary>

```
photocrop/
  ├── main.py              CLI / --gui / --pdf 入口
  ├── config.py            用户配置系统
  │
  ├── engine/              检测引擎
  │   ├── detector_base.py     检测器抽象基类
  │   ├── cv_detector.py       传统 CV 封装
  │   ├── cv_algorithm.py      核心 CV 算法
  │   ├── enhanced_cv_detector.py
  │   ├── combined_detector.py IoU 投票融合
  │   ├── yolo_world_detector.py  YOLO-World（异步加载）
  │   ├── model_detector.py    视觉大模型 API 占位
  │   ├── core.py              流程编排 + 工厂函数
  │   ├── filters.py           小框过滤、IoU 去重、数量限制
  │   └── rotation_estimator.py  旋转角度估算
  │
  ├── ui/                  PySide6 图形界面
  │   ├── main_window.py       工具栏 + 状态栏 + 快捷键
  │   ├── canvas.py            画布 + 交互裁剪框 + 拖拽导入
  │   ├── crop_item.py         裁剪框（旋转、手柄、浮动工具栏、宽高比锁定）
  │   ├── state.py             AppState 全局状态管理
  │   ├── theme.py             ThemeManager（Light/Dark + 过渡动画）
  │   ├── toast.py             Toast 通知
  │   ├── press_button.py      按下缩放动画按钮
  │   ├── undo_manager.py      撤销/重做（完整双栈）
  │   ├── session.py           单图会话数据类
  │   ├── styled_dropdown.py   自定义下拉组件
  │   ├── image_list_panel.py  左侧图像列表
  │   ├── crop_options_panel.py 右侧属性面板
  │   ├── extracted_images_panel.py 裁剪结果预览
  │   ├── single_view_panel.py Single View 大图预览
  │   ├── export_dialog.py     批量导出对话框
  │   ├── template_manager.py  裁剪模板管理器
  │   ├── icons.py             SVG 图标加载器
  │   ├── utils.py             PIL <-> Qt 图像转换
  │   └── controllers/         业务逻辑控制器
  │       ├── detection_controller.py
  │       ├── export_controller.py
  │       ├── session_controller.py
  │       ├── theme_controller.py
  │       └── view_coordinator.py
  │
  ├── export/              导出层
  │   ├── cropper.py       裁剪 → 旋转 → 去白边 → 保存
  │   └── pdf_reader.py    PDF → PIL Image
  │
  └── utils/               工具层
      ├── crop_rect.py     CropRect 数据结构
      ├── iou.py           IoU 计算
      └── rotation.py      角度归一化
```

### 检测器抽象

```python
from photocrop.engine.core import detect_rectangles

# 默认：增强 CV
rects = detect_rectangles(img)

# 传统 CV
rects = detect_rectangles(img, detector="cv")

# YOLO-World
rects = detect_rectangles(img, detector="yolo-world")

# 自定义检测器
class MyDetector(BaseDetector):
    def detect(self, page_img):
        ...
rects = detect_rectangles(img, detector=MyDetector())
```

</details>

---

## 依赖

- Python 3.9+
- PySide6 >= 6.5（GUI）
- PyMuPDF >= 1.23
- OpenCV >= 4.7
- NumPy、SciPy、Pillow
- platformdirs >= 3.0
- （可选）Ultralytics、PyTorch（YOLO-World）

---

## 许可证

MIT
