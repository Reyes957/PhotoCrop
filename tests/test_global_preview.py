"""
测试全局预览模式（跨页预览）

覆盖：
- ImageSession 预览缓存
- ExtractedImagesPanel 全局模式索引映射
- MainWindow 辅助方法逻辑
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

# Mock PySide6 before importing any photocrop.ui modules
# (PySide6 not available in test environment)
_pyside6_mock = MagicMock()
for mod in [
    "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
]:
    sys.modules.setdefault(mod, _pyside6_mock)

from photocrop.ui.extracted_images_panel import PageCropRef  # noqa: E402
from photocrop.ui.session import ImageSession  # noqa: E402
from photocrop.utils.crop_rect import CropRect  # noqa: E402

# ============================================================
# ImageSession 预览缓存
# ============================================================

class TestImageSessionPreviewCache:
    """测试 ImageSession 的预览缓存功能"""

    def _make_session(self, page_count: int = 5) -> ImageSession:
        img = Image.new("RGB", (1000, 1400), "white")
        pages = [(i, Image.new("RGB", (612, 792), "white")) for i in range(page_count)]

        def loader(idx: int) -> Image.Image:
            if 0 <= idx < len(pages):
                return pages[idx][1]
            raise IndexError(f"Page {idx} out of range")

        return ImageSession(
            source_path=Path("/tmp/test.pdf"),
            source_image=img,
            is_pdf=True,
            pdf_page_count=page_count,
            pdf_page_loader=loader,
        )

    def test_preview_cache_initially_empty(self) -> None:
        sess = self._make_session(3)
        assert sess.get_page_preview(0) is None
        assert sess.get_page_preview(1) is None

    def test_set_and_get_preview(self) -> None:
        sess = self._make_session(3)
        img = Image.new("RGB", (612, 792), "red")
        sess.set_page_preview(0, img)

        preview = sess.get_page_preview(0)
        assert preview is not None
        assert preview.width <= 160
        assert preview.height <= 160

    def test_preview_does_not_affect_page_cache(self) -> None:
        sess = self._make_session(3)
        img = Image.new("RGB", (612, 792), "blue")
        sess.set_page_preview(0, img)

        assert 0 not in sess._page_cache
        assert 0 in sess._page_preview_cache

    def test_multiple_pages_preview(self) -> None:
        sess = self._make_session(5)
        for i in range(5):
            sess.set_page_preview(i, Image.new("RGB", (612, 792), (i * 50, 0, 0)))

        for i in range(5):
            assert sess.get_page_preview(i) is not None

    def test_preview_not_evicted_by_page_cache(self) -> None:
        """预览缓存不会被 LRU 淘汰"""
        sess = self._make_session(10)
        for i in range(10):
            sess.set_page_preview(i, Image.new("RGB", (100, 100), "green"))

        for i in range(10):
            sess.get_page_image(i)

        for i in range(10):
            assert sess.get_page_preview(i) is not None

        assert len(sess._page_cache) <= 5

    def test_set_page_preview_copies_image(self) -> None:
        """set_page_preview 不持有原始引用（copy）"""
        sess = self._make_session(1)
        original = Image.new("RGB", (612, 792), "white")
        sess.set_page_preview(0, original)

        # 修改原图不影响缓存
        original.putpixel((0, 0), (255, 0, 0))
        cached = sess.get_page_preview(0)
        assert cached is not None
        assert cached.getpixel((0, 0)) != (255, 0, 0)


# ============================================================
# ExtractedImagesPanel 全局索引映射
# ============================================================

class TestGlobalIndexMapping:
    """测试全局索引到页面+本地索引的映射"""

    def test_page_crop_ref(self) -> None:
        ref = PageCropRef(page_idx=2, local_idx=1)
        assert ref.page_idx == 2
        assert ref.local_idx == 1

    def test_typical_3page_mapping(self) -> None:
        """3 页，分别有 2/3/1 个裁剪框"""
        index_map: dict[int, PageCropRef] = {}
        global_idx = 0
        pages_rects = [(0, 2), (1, 3), (2, 1)]

        for page_idx, rect_count in pages_rects:
            for i in range(rect_count):
                index_map[global_idx] = PageCropRef(page_idx, i)
                global_idx += 1

        assert global_idx == 6
        assert index_map[0] == PageCropRef(0, 0)
        assert index_map[1] == PageCropRef(0, 1)
        assert index_map[2] == PageCropRef(1, 0)
        assert index_map[3] == PageCropRef(1, 1)
        assert index_map[4] == PageCropRef(1, 2)
        assert index_map[5] == PageCropRef(2, 0)

    def test_empty_page_in_middle(self) -> None:
        """中间页无裁剪框时索引连续"""
        index_map: dict[int, PageCropRef] = {}
        global_idx = 0
        pages_rects = [(0, 1), (1, 0), (2, 2)]

        for page_idx, rect_count in pages_rects:
            for i in range(rect_count):
                index_map[global_idx] = PageCropRef(page_idx, i)
                global_idx += 1

        assert global_idx == 3
        assert index_map[0] == PageCropRef(0, 0)
        assert index_map[1] == PageCropRef(2, 0)
        assert index_map[2] == PageCropRef(2, 1)

    def test_nonexistent_index_returns_none(self) -> None:
        index_map: dict[int, PageCropRef] = {}
        assert index_map.get(99) is None


# ============================================================
# MainWindow 辅助逻辑
# ============================================================

class TestMainWindowHelpers:
    """测试与全局预览相关的辅助逻辑"""

    def test_pdf_key_extraction(self) -> None:
        current_key = "/tmp/test.pdf::page_2"
        pdf_key = current_key.rsplit("::page_", 1)[0]
        page_idx = int(current_key.rsplit("::page_", 1)[1])
        assert pdf_key == "/tmp/test.pdf"
        assert page_idx == 2

    def test_single_image_key_no_page(self) -> None:
        current_key = "/tmp/photo.jpg"
        assert "::page_" not in current_key

    def test_on_clear_page_idx_extraction(self) -> None:
        # 正常 PDF 页面
        key = "/tmp/test.pdf::page_3"
        if "::page_" in (key or ""):
            page_idx = int(key.rsplit("::page_", 1)[1])
            assert page_idx == 3

        # None
        key = None
        assert "::page_" not in (key or "")

    def test_pages_data_update_replaces_current_page(self) -> None:
        """替换当前页数据时其他页不变"""
        pages_data = [
            (0, Image.new("RGB", (100, 100), "red"), [CropRect(10, 10, 50, 50)]),
            (1, Image.new("RGB", (100, 100), "green"), [CropRect(20, 20, 60, 60)]),
            (2, Image.new("RGB", (100, 100), "blue"), []),
        ]

        current_page = 1
        new_rects = [
            CropRect(20, 20, 60, 60),
            CropRect(100, 100, 80, 80),
        ]

        updated = list(pages_data)
        for i, (pg_idx, img, _) in enumerate(updated):
            if pg_idx == current_page:
                updated[i] = (pg_idx, img, list(new_rects))
                break

        assert len(updated[0][2]) == 1  # page 0 不变
        assert len(updated[1][2]) == 2  # page 1 更新
        assert updated[1][2][1].x == 100
        assert len(updated[2][2]) == 0  # page 2 不变

    def test_refresh_uses_preview_cache(self) -> None:
        """预览缓存命中时不调用 get_page_image"""
        sess = ImageSession(
            source_path=Path("/tmp/test.pdf"),
            source_image=Image.new("RGB", (1000, 1400), "white"),
            is_pdf=True,
            pdf_page_count=3,
        )
        for i in range(3):
            sess.set_page_preview(i, Image.new("RGB", (612, 792), "white"))

        pages_data = []
        for page_idx in range(sess.page_count):
            img = sess.get_page_preview(page_idx)
            assert img is not None, f"Page {page_idx} cache miss"
            pages_data.append((page_idx, img, []))

        assert len(pages_data) == 3

    def test_refresh_cache_miss_fallback(self) -> None:
        """缓存未命中时 fallback 到 get_page_image"""
        sess = ImageSession(
            source_path=Path("/tmp/test.pdf"),
            source_image=Image.new("RGB", (1000, 1400), "white"),
            is_pdf=True,
            pdf_page_count=2,
            pdf_page_loader=lambda idx: Image.new("RGB", (612, 792), "white"),
        )

        pages_data = []
        for page_idx in range(sess.page_count):
            img = sess.get_page_preview(page_idx)
            if img is None:
                img = sess.get_page_image(page_idx)
                sess.set_page_preview(page_idx, img)
            pages_data.append((page_idx, img, []))

        assert len(pages_data) == 2
        assert sess.get_page_preview(0) is not None
        assert sess.get_page_preview(1) is not None


# ============================================================
# 集成测试
# ============================================================

class TestGlobalPreviewIntegration:
    """端到端数据流"""

    def test_pdf_load_detect_preview_flow(self) -> None:
        """加载 PDF → 批量检测 → 全局预览"""
        page_count = 4
        pages = [(i, Image.new("RGB", (612, 792), "white")) for i in range(page_count)]

        sess = ImageSession(
            source_path=Path("/tmp/album.pdf"),
            source_image=pages[0][1],
            is_pdf=True,
            pdf_page_count=page_count,
            pdf_page_loader=lambda idx: pages[idx][1],
        )

        # 填充预览缓存
        for i, (_, img) in enumerate(pages):
            sess.set_page_preview(i, img)

        # 检测结果
        sess.page_crop_rects[0] = [CropRect(100, 100, 200, 300)]
        sess.page_crop_rects[1] = [
            CropRect(50, 50, 150, 200),
            CropRect(300, 300, 100, 150),
        ]
        sess.page_crop_rects[2] = []
        sess.page_crop_rects[3] = [CropRect(200, 200, 180, 250)]

        # 构建 pages_data
        pages_data = []
        for page_idx in range(sess.page_count):
            rects = sess.page_crop_rects.get(page_idx, [])
            img = sess.get_page_preview(page_idx)
            assert img is not None
            pages_data.append((page_idx, img, rects))

        total_rects = sum(len(r) for _, _, r in pages_data)
        assert total_rects == 4

        # 全局索引映射
        index_map: dict[int, PageCropRef] = {}
        global_idx = 0
        for page_idx, _, rects in pages_data:
            for i, _ in enumerate(rects):
                index_map[global_idx] = PageCropRef(page_idx, i)
                global_idx += 1

        assert global_idx == 4
        assert index_map[0] == PageCropRef(0, 0)
        assert index_map[1] == PageCropRef(1, 0)
        assert index_map[2] == PageCropRef(1, 1)
        assert index_map[3] == PageCropRef(3, 0)

    def test_edit_then_refresh_preserves_other_pages(self) -> None:
        """编辑当前页后刷新，其他页数据不变"""
        sess = ImageSession(
            source_path=Path("/tmp/test.pdf"),
            source_image=Image.new("RGB", (1000, 1400), "white"),
            is_pdf=True,
            pdf_page_count=3,
        )
        for i in range(3):
            sess.set_page_preview(i, Image.new("RGB", (612, 792), "white"))

        sess.page_crop_rects[0] = [CropRect(10, 10, 50, 50)]
        sess.page_crop_rects[1] = [CropRect(20, 20, 60, 60)]
        sess.page_crop_rects[2] = [CropRect(30, 30, 70, 70)]

        current_page = 1
        canvas_rects = [
            CropRect(20, 20, 60, 60),
            CropRect(100, 100, 80, 80),
        ]

        pages_data = []
        for page_idx in range(sess.page_count):
            rects = sess.page_crop_rects.get(page_idx, [])
            img = sess.get_page_preview(page_idx)
            pages_data.append((page_idx, img, rects))

        # 替换当前页
        for i, (pg_idx, img, _) in enumerate(pages_data):
            if pg_idx == current_page:
                pages_data[i] = (pg_idx, img, list(canvas_rects))
                break

        assert len(pages_data[0][2]) == 1
        assert len(pages_data[1][2]) == 2
        assert len(pages_data[2][2]) == 1

    def test_cross_page_delete(self) -> None:
        """跨页删除：索引映射 → 切页 → 删除"""
        sess = ImageSession(
            source_path=Path("/tmp/test.pdf"),
            source_image=Image.new("RGB", (1000, 1400), "white"),
            is_pdf=True,
            pdf_page_count=2,
        )
        sess.page_crop_rects[0] = [
            CropRect(10, 10, 50, 50),
            CropRect(100, 100, 60, 60),
        ]
        sess.page_crop_rects[1] = [CropRect(200, 200, 80, 80)]

        # 全局索引映射
        index_map: dict[int, PageCropRef] = {}
        global_idx = 0
        for page_idx in range(2):
            for i in range(len(sess.page_crop_rects[page_idx])):
                index_map[global_idx] = PageCropRef(page_idx, i)
                global_idx += 1

        # 点击全局索引 2 → page 1, local 0
        ref = index_map[2]
        assert ref == PageCropRef(1, 0)

        # 当前在 page 0，需要切页
        current_page = 0
        assert ref.page_idx != current_page

        # 删除
        del sess.page_crop_rects[ref.page_idx][ref.local_idx]
        assert len(sess.page_crop_rects[1]) == 0
        assert len(sess.page_crop_rects[0]) == 2

    def test_single_image_mode_not_affected(self) -> None:
        """单图模式不触发全局逻辑"""
        sess = ImageSession(
            source_path=Path("/tmp/photo.jpg"),
            source_image=Image.new("RGB", (800, 600), "white"),
        )
        assert not sess.is_pdf
        assert sess.page_count == 1
