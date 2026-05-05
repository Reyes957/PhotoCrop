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

- **Multiple detection engines** — Traditional CV (edge detection + morphology), Enhanced CV, Combined detector, and YOLO-World zero-shot open-vocabulary detection
- **Pluggable detector architecture** — ABC base class + factory pattern; swap detectors or add your own
- **Three modes** — CLI for scripting, GUI (PySide6) for interactive editing, PDF batch for bulk processing
- **Smart export** — Auto-rotation correction, white-border trimming, multi-format output
- **Configurable** — Max photo count, minimum size thresholds, fallback behavior, and more

---

## Installation

```bash
git clone https://github.com/Reyes957/PhotoCrop.git
cd PhotoCrop
pip install -r requirements.txt
```

For the optional YOLO-World detector (zero-shot open-vocabulary detection):

```bash
pip install ultralytics
pip install git+https://github.com/ultralytics/CLIP.git
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
python -m photocrop.main page.jpg --detector combined     # Union of multiple detectors
python -m photocrop.main page.jpg --detector yolo-world   # YOLO-World (requires model file)
```

---

## Architecture

```
main.py (CLI / --gui / --pdf)
  │
  ├── engine/          Detection pipeline
  │   ├── detector_base.py   ABC for pluggable detectors
  │   ├── cv_detector.py     Traditional CV (edge + morphology + connected components)
  │   ├── enhanced_cv_detector.py
  │   ├── combined_detector.py
  │   ├── yolo_world_detector.py  YOLO-World zero-shot
  │   ├── model_detector.py       Placeholder for vision API detectors
  │   ├── core.py                 Orchestration + factory
  │   ├── filters.py              Small-box filtering, IoU dedup, count limiting
  │   └── rotation.py             Rotation angle estimation
  │
  ├── ui/              PySide6 GUI
  │   ├── main_window.py   Toolbar + status bar
  │   ├── canvas.py        Canvas with interactive crop boxes
  │   └── crop_item.py     Editable crop region widget
  │
  ├── export/          Output layer
  │   ├── cropper.py      Crop → rotate → trim → save
  │   └── pdf_reader.py   PDF → PIL Image conversion
  │
  └── utils/           Shared utilities
      ├── crop_rect.py    CropRect data class
      ├── iou.py          Intersection-over-Union
      └── rotation.py     Angle normalization
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
- PySide6 >= 6.5
- PyMuPDF >= 1.23
- OpenCV >= 4.8
- NumPy, SciPy, Pillow
- (Optional) Ultralytics, PyTorch for YOLO-World

---

## License

MIT
