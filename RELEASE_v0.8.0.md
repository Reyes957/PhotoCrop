# PhotoCrop v0.8.0

First formal release since v0.3.1. A complete rewrite happened in between: new architecture, new UI, 121+ bug fixes. From a prototype to a desktop app you can actually use every day.

> 自 v0.3.1 以来的首个正式 Release。这期间经历了一次完整的重写：新架构、新 UI、121+ bug 修复。从原型变成了一个能日常使用的桌面应用。

## Install

```bash
pip install -e ".[gui]"     # GUI dependencies
pip install -e ".[all]"     # includes YOLO-World
```

---

## Highlights

### Architecture

- **Controller layer** -- 5 controllers (Detection, Export, Session, Theme, View) pull business logic out of the main window
- **AppState** -- Observable state container, signal-driven data flow
- **Detector ABC + factory** -- Swap between CV, Enhanced CV, Combined, YOLO-World, or write your own
- **IoU voting fusion** -- Two detectors cross-validate, high-confidence regions merge

### UI

- **Light / Dark themes** -- 18 color tokens, 350ms transition animation
- **SVG icon system** -- 11 SVG icons with runtime color injection
- **StyledDropdown** -- Custom dropdown built from scratch in pure QWidget
- **CropItem redesign** -- Toolbar inside the box, dot handles, edge-line hit detection, glow breathing pulse
- **Rotation crop pipeline** -- Four-corner mapping, scene-coordinate dragging, intuitive rotation direction

### Features

- Multi-image management with PDF cross-page preview
- Batch export (JPEG/PNG/TIFF) with filename templates
- Single View real-time preview
- Crop property panel (Width/Height/X/Y/Rotation/Aspect Ratio)
- Template system, undo/redo, drag-and-drop import, toast notifications

### Quality

- 121+ bugs fixed, 184+ tests passing
- CI/CD (Python 3.9-3.12 + ruff + pytest)
- mypy type checking

---

## What's new in this release (v0.7.4 to v0.8.0)

### v0.7.4 -- Crop box UI overhaul

- Toolbar moved inside the crop box (8px padding)
- Solid blue dot handles (r=14, hover=18)
- Full-edge hit detection (perpendicular distance < 22)
- Rotation grab handle as a dot, connection line follows selection state

### v0.7.5 -- Rotation crop fix, end to end

- Rewrote `_rotate_and_crop`: four corners -> bounding box -> reverse rotate -> final crop
- Preview no longer runs `auto_rotate`, which was undoing user rotation
- Dragging uses scene coordinates throughout, no more coordinate drift after rotation
- Snap tolerance tightened from +/-15 degrees to +/-0.5 degrees

### v0.8.0 -- Polish

- Test expectations adjusted for `_CROP_PEN_HALF` offset
- Full-project ruff lint cleanup
- README rewrite

---

## What's new (Chinese)

### v0.7.4 -- 裁剪框 UI 重构

- 工具栏移入框内（8px 内边距）
- 实心蓝色圆点手柄（r=14, hover=18）
- 四边整线触发（垂直距离 < 22）
- 旋转圆点手柄 + 连接线跟随选框状态

### v0.7.5 -- 旋转裁剪全链路修复

- `_rotate_and_crop` 重写：四角映射 → 包围盒 → 反向旋转 → 最终裁剪
- 预览禁用 `auto_rotate`，不再抵消用户旋转
- 拖动全程场景坐标，消除旋转后坐标系偏差
- 吸附容差 ±15° → ±0.5°

### v0.8.0 -- 质量打磨

- 测试期望值适配 `_CROP_PEN_HALF` 偏移
- 全项目 ruff lint 清理
- README 重构

---

Full changelog: [CHANGELOG.md](CHANGELOG.md)

**Full Changelog**: https://github.com/Reyes957/PhotoCrop/compare/v0.3.1...v0.8.0
