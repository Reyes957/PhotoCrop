# PhotoCrop

[English](README.md)

从扫描的 PDF 相册页面中自动检测并裁剪出单张照片的桌面应用。

**场景：** 你有一本老相册，扫描成 PDF 后，想要的是里面每一张独立的照片，而不是整页扫描件。手动裁剪很痛苦。

**PhotoCrop 做的事：** 把扫描页面（图片或 PDF）扔进去，它能找到每一张照片的位置，裁剪出来，还能自动纠正旋转、去除白边，导出干净的独立图片。

---

## 为什么做这个

过年的时候翻出一些老相册，里面的照片都是胶片拍的。照片上有些人已经不在了，有些人的样子只留在记忆里。

这些胶片没有电子版。我想把它们留下来。

PhotoCrop 只做一件事：把照片从扫描页面上干净地裁下来。没有 AI 增强，没有 AI 修复。因为我发现，当你看到一张模糊的老照片，你脑海里浮现的那个人的样子，是任何 AI 都复现不了的。记忆里的面容比像素更真实。

你当然可以拿裁出来的照片去做 AI 修复，GPT 很强，随你。但这个工具的目的就是裁剪——让你看到这张照片的时候，能想起那个人，就够了。

另外，整个检测流程跑的是本地离线模型，你的老照片不会被上传到任何服务器，也不会被拿去训练什么。隐私这块不用担心。

---

## 功能

- **多种检测引擎** — 传统 CV（边缘检测 + 形态学）、增强 CV、组合检测器、YOLO-World 零样本开放词汇检测
- **可插拔检测器架构** — 基于 ABC 抽象基类和工厂模式，可以随时切换检测器或自己写一个
- **三种运行模式** — CLI 命令行（写脚本用）、GUI 图形界面（交互编辑）、PDF 批量模式（一键处理整本）
- **智能导出** — 自动旋转矫正、去白边、支持多种输出格式
- **参数可调** — 最大照片数、最小尺寸阈值、fallback 兜底策略等

---

## 安装

```bash
git clone https://github.com/YOUR_USERNAME/PhotoCrop.git
cd PhotoCrop
pip install -r requirements.txt
```

如果要使用 YOLO-World 检测器（可选的零样本开放词汇检测）：

```bash
pip install ultralytics
pip install git+https://github.com/ultralytics/CLIP.git
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
# 或者直接加载一张图：
python -m photocrop.main --gui page.jpg
```

### PDF — 批量处理

```bash
python -m photocrop.main --pdf album.pdf --output ./photos/
```

### 指定检测器

```bash
python -m photocrop.main page.jpg --detector cv            # 默认：传统 CV 算法
python -m photocrop.main page.jpg --detector enhanced-cv   # 增强 CV 管线
python -m photocrop.main page.jpg --detector combined      # 多检测器并集
python -m photocrop.main page.jpg --detector yolo-world    # YOLO-World（需下载模型）
```

---

## 架构

```
main.py (CLI / --gui / --pdf)
  │
  ├── engine/          检测引擎
  │   ├── detector_base.py   检测器抽象基类
  │   ├── cv_detector.py     传统 CV（边缘检测 + 形态学 + 连通分量）
  │   ├── enhanced_cv_detector.py
  │   ├── combined_detector.py
  │   ├── yolo_world_detector.py   YOLO-World 零样本检测
  │   ├── model_detector.py        预留给视觉大模型 API 的接口
  │   ├── core.py                  流程编排 + 工厂函数
  │   ├── filters.py               小框过滤、IoU 去重、数量限制
  │   └── rotation.py              旋转角度估算
  │
  ├── ui/              PySide6 图形界面
  │   ├── main_window.py   工具栏 + 状态栏
  │   ├── canvas.py        带交互裁剪框的画布
  │   └── crop_item.py     可拖拽编辑的裁剪框
  │
  ├── export/          导出层
  │   ├── cropper.py      裁剪 → 旋转 → 去白边 → 保存
  │   └── pdf_reader.py   PDF → PIL Image 转换
  │
  └── utils/           工具层
      ├── crop_rect.py    CropRect 数据结构
      ├── iou.py          IoU 计算
      └── rotation.py     角度归一化
```

### 检测器抽象

```python
from photocrop.engine.core import detect_rectangles

# 默认 CV 检测
rects = detect_rectangles(img)

# YOLO-World 检测
rects = detect_rectangles(img, detector="yolo-world")

# 自定义检测器
class MyDetector(BaseDetector):
    def detect(self, page_img):
        ...
rects = detect_rectangles(img, detector=MyDetector())
```

---

## 依赖

- Python 3.9+
- PySide6 >= 6.5
- PyMuPDF >= 1.23
- OpenCV >= 4.8
- NumPy、SciPy、Pillow
- （可选）Ultralytics、PyTorch（YOLO-World 需要）

---

## 许可证

MIT
