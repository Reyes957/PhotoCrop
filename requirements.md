# PhotoCrop 依赖清单

> 版本：0.7.1 | Python：>=3.9 | 最后更新：2026-05-15

---

## 一、核心依赖（必需）

| 包名 | 最低版本 | 用途 |
|------|----------|------|
| `Pillow` | >=9.5 | 图像读写（JPEG/PNG/TIFF/BMP/WebP） |
| `numpy` | >=1.23 | 数组运算、图像矩阵处理 |
| `scipy` | >=1.10 | 形态学操作（检测流水线） |
| `PyMuPDF` | >=1.23 | PDF 页面渲染（fitz） |
| `opencv-python` | >=4.8 | 图像处理（边缘检测、轮廓分析、形态学） |
| `platformdirs` | >=3.0 | 跨平台缓存目录（YOLO 模型缓存、SVG 缓存） |

---

## 二、GUI 依赖（可选）

| 包名 | 最低版本 | 用途 |
|------|----------|------|
| `PySide6` | >=6.5 | Qt6 GUI 框架（主窗口、画布、对话框、SVG 渲染） |

安装方式：

```bash
pip install -e ".[gui]"
```

---

## 三、YOLO-World 依赖（可选）

| 包名 | 最低版本 | 用途 |
|------|----------|------|
| `ultralytics` | >=8.1 | YOLO-World 零样本检测器 |
| `torch` | >=2.0 | PyTorch 深度学习框架 |
| `torchvision` | >=0.15 | 视觉模型工具 |

安装方式：

```bash
pip install -e ".[yolo]"
```

---

## 四、全量安装

```bash
pip install -e ".[all]"     # 核心 + GUI + YOLO
pip install -r requirements.txt  # 等效方式
```

---

## 五、开发依赖

| 工具 | 用途 |
|------|------|
| `ruff` | 代码格式化 + lint（E/F/W/I/UP/B） |
| `mypy` | 静态类型检查 |
| `pytest` | 单元测试 |

配置见 `pyproject.toml` 的 `[tool.ruff]`、`[tool.mypy]` 节。

---

## 六、requirements.txt

```
# 核心依赖
PySide6>=6.5
PyMuPDF>=1.23
scipy>=1.10
numpy>=1.23
opencv-python>=4.8
Pillow>=9.5
platformdirs>=3.0

# YOLO-World 零样本检测器（可选）
# 安装方法：pip install -e ".[yolo]"
# ultralytics>=8.1
# torch>=2.0
# torchvision>=0.15
```

---

## 七、版本兼容性

| Python | 状态 |
|--------|------|
| 3.9 | ✅ 主要开发版本 |
| 3.10 | ✅ CI 测试通过 |
| 3.11 | ✅ CI 测试通过 |
| 3.12 | ✅ CI 测试通过 |

| 平台 | 状态 |
|------|------|
| macOS (Apple Silicon) | ✅ 主要开发平台 |
| macOS (Intel) | ✅ 兼容 |
| Linux | ✅ 兼容（需安装 Qt 依赖） |
| Windows | ⚠️ 未测试 |
