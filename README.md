# PhotoCrop

[中文文档](README_CN.md)

A Python desktop application that automatically detects and crops individual photos from scanned PDF album pages.

**Problem:** You have a photo album. You scan its pages to PDF. Now you want the individual photos — not the whole page. Doing this by hand is tedious.

**What PhotoCrop does:** Feed it a scanned page (image or PDF), and it finds each photo, crops them out, optionally corrects rotation, trims white borders, and exports clean individual image files.

---

## Why this exists

I found some old family albums over the Chinese New Year. The photos were all shot on film. Some of the people in them are gone. Some exist only in memory.

There were no digital copies. I wanted to keep them.

PhotoCrop does one thing: crop photos cleanly from scanned pages. No AI enhancement, no AI restoration. When you look at a blurry old photo and a face comes to mind, no AI can reproduce that. The face you remember is more real than any pixel.

You can take the cropped photos and run them through AI restoration if you want — GPT is good at that. But this tool is just about cropping. If looking at the photo brings someone back to you, that's enough.

The whole detection pipeline runs locally with offline models. Your photos never leave your machine, and nothing gets sent off for training. Your memories stay yours.

---

## Features

- **Multiple detection engines** — Traditional CV (edge detection + morphology), Enhanced CV (deprecated), Combined detector (IoU voting fusion), and YOLO-World zero-shot open-vocabulary detection
- **Pluggable detector architecture** — ABC base class + factory pattern; swap detectors or add your own
- **Three modes** — CLI for scripting, GUI (PySide6) for interactive editing, PDF batch for bulk processing
- **Multi-image management** — Left panel with thumbnails, file names, and crop counts; right-click context menu
- **Crop property panel** — Real-time editing of Width/Height/X/Y/Rotation with aspect ratio lock
- **Crop result preview** — 2-column grid with LRU cache; click to select or delete
- **Single View** — Side-by-side layout: original thumbnail + extracted full-size image with page navigation
- **Batch export dialog** — Format (JPEG/PNG/TIFF), quality, max dimensions, filename template, auto-rotation, white-border trimming
- **Template system** — Percentage-based crop templates that work across different images
- **Sync & Transform** — Sync crop dimensions across selections; flip horizontal/vertical
- **Smart export** — Auto-rotation correction, white-border trimming, EXIF metadata, multi-format output
- **Undo/Redo** — Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y for all crop operations
- **Multi-select** — Ctrl+Click, Ctrl+A (select all), Tab/Shift+Tab (cycle), Esc (deselect)
- **Keyboard shortcuts** — Ctrl+O (load), Ctrl+D (detect), Ctrl+E (export), arrow keys (page navigation)
- **User config** — Optional `~/.config/photocrop/config.yaml` for persistent preferences
- **Configurable** — Max photo count, minimum size thresholds, fallback behavior, and more

---

## Installation

```bash
git clone https://github.com/Reyes957/PhotoCrop.git
cd PhotoCrop
pip install -e ".[gui]"
```

For YOLO-World (zero-shot open-vocabulary detection):

```bash
pip install -e ".[all]"
```

Or install everything from `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Quick Start

### CLI — single image

```bash
python -m photocrop.main page.jpg --max-count 4
```

### GUI — interactive editor

```bash
python -m photocrop.main --gui
# or load an image directly:
python -m photocrop.main --gui page.jpg
```

### PDF — batch process

```bash
python -m photocrop.main --pdf album.pdf --output ./photos/
```

### Choose a detector

```bash
python -m photocrop.main page.jpg --detector cv          # Default: traditional CV
python -m photocrop.main page.jpg --detector enhanced-cv  # Enhanced CV pipeline
python -m photocrop.main page.jpg --detector combined     # IoU voting fusion
python -m photocrop.main page.jpg --detector yolo-world   # YOLO-World (requires model)
```

### GUI keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Load image/PDF |
| Ctrl+D | Detect photos |
| Ctrl+E | Export all |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z / Ctrl+Y | Redo |
| ← → | Previous/next page |
| Delete / Backspace | Remove selected crop box |
| Tab / Shift+Tab | Cycle through crop boxes |
| Ctrl+A | Select all crop boxes |
| Ctrl+Click | Add/remove from selection |
| Esc | Deselect all |

---

## Architecture

```
photocrop/
  ├── main.py              CLI / --gui / --pdf entry point
  ├── config.py            User config system (~/.config/photocrop/config.yaml)
  │
  ├── engine/              Detection pipeline
  │   ├── detector_base.py     ABC for pluggable detectors
  │   ├── cv_detector.py       Traditional CV wrapper
  │   ├── cv_algorithm.py      Core CV algorithm (scene classification + photo detection)
  │   ├── enhanced_cv_detector.py
  │   ├── combined_detector.py IoU voting fusion
  │   ├── yolo_world_detector.py  YOLO-World zero-shot (async loading)
  │   ├── model_detector.py    Placeholder for vision API detectors
  │   ├── core.py              Orchestration + factory (cached)
  │   ├── filters.py           Small-box filtering, IoU dedup, count limiting
  │   └── rotation_estimator.py  Rotation angle estimation
  │
  ├── ui/                  PySide6 GUI (Apple design)
  │   ├── main_window.py       Toolbar + status bar + shortcuts + multi-image session
  │   ├── canvas.py            Canvas with interactive crop boxes + undo/redo + sync/flip
  │   ├── crop_item.py         Editable crop region widget (rotation, handles, floating toolbar, aspect lock)
  │   ├── undo_manager.py      Undo/redo state management (serializable)
  │   ├── session.py           ImageSession data class for per-image state
  │   ├── image_list_panel.py  Left panel: thumbnails + filenames + crop counts
  │   ├── crop_options_panel.py Right panel: Width/Height/X/Y/Rotation/Aspect Ratio
  │   ├── extracted_images_panel.py Crop result preview (2-column grid + LRU cache)
  │   ├── single_view_panel.py Single View: thumbnail + full-size preview
  │   ├── export_dialog.py     Batch export settings dialog
  │   └── template_manager.py  Crop template manager (percentage coordinates)
  │
  ├── export/              Output layer
  │   ├── cropper.py       Crop -> rotate -> trim -> save
  │   └── pdf_reader.py    PDF -> PIL Image conversion
  │
  └── utils/               Shared utilities
      ├── crop_rect.py     CropRect data class (center coordinate system)
      ├── iou.py           Intersection-over-Union
      └── rotation.py      Angle normalization
```

### Detector abstraction

```python
from photocrop.engine.core import detect_rectangles

# Default CV
rects = detect_rectangles(img)

# YOLO-World
rects = detect_rectangles(img, detector="yolo-world")

# Your own detector
class MyDetector(BaseDetector):
    def detect(self, page_img):
        ...
rects = detect_rectangles(img, detector=MyDetector())
```

---

## Requirements

- Python 3.9+
- PySide6 >= 6.5 (GUI)
- PyMuPDF >= 1.23
- OpenCV >= 4.7
- NumPy, SciPy, Pillow
- platformdirs >= 3.0
- (Optional) Ultralytics, PyTorch for YOLO-World

---

## License

MIT
