"""AppState + SessionState 单元测试"""

from pathlib import Path

import pytest
from PIL import Image

from photocrop.ui.state import AppState, SessionState
from photocrop.utils.crop_rect import CropRect


def _make_sess(key: str, **kwargs) -> SessionState:
    """创建测试用 SessionState"""
    defaults = dict(
        key=key,
        source_path=Path(key),
        source_image=Image.new("RGB", (100, 100)),
    )
    defaults.update(kwargs)
    return SessionState(**defaults)


class TestAppState:
    def test_add_and_get_session(self):
        app = AppState()
        sess = _make_sess("test.jpg")
        app.add_session(sess)
        assert app.session_count == 1
        assert app.get_session("test.jpg") is sess

    def test_remove_session(self):
        app = AppState()
        sess = _make_sess("a.jpg")
        app.add_session(sess)
        app.set_current("a.jpg")
        app.remove_session("a.jpg")
        assert app.session_count == 0
        assert app.current_session is None

    def test_remove_session_clears_current(self):
        """删除当前 session 后 current 应清空"""
        app = AppState()
        app.add_session(_make_sess("a.jpg"))
        app.add_session(_make_sess("b.jpg"))
        app.set_current("a.jpg")
        app.remove_session("a.jpg")
        assert app.current_session is None

    def test_set_current(self):
        app = AppState()
        sess = _make_sess("x.jpg")
        app.add_session(sess)
        app.set_current("x.jpg")
        assert app.current_session is sess

    def test_page_key_format(self):
        app = AppState()
        assert app.get_page_key("test.pdf", 0) == "test.pdf##PAGE##0"
        assert app.get_page_key("test.pdf", 5) == "test.pdf##PAGE##5"

    def test_parse_page_key(self):
        app = AppState()
        assert app.parse_page_key("test.pdf##PAGE##3") == ("test.pdf", 3)
        assert app.parse_page_key("test.pdf##PAGE##0") == ("test.pdf", 0)
        assert app.parse_page_key("test.jpg") is None
        assert app.parse_page_key("") is None

    def test_total_crop_count_single(self):
        app = AppState()
        sess = _make_sess("a.jpg")
        sess.crop_rects = [CropRect(10, 10, 20, 20)]
        app.add_session(sess)
        assert app.total_crop_count == 1

    def test_total_crop_count_pdf(self):
        app = AppState()
        sess = _make_sess("doc.pdf", is_pdf=True, page_count=3)
        sess.page_crop_rects[0] = [CropRect(0, 0, 10, 10)]
        sess.page_crop_rects[1] = [CropRect(0, 0, 10, 10), CropRect(10, 10, 20, 20)]
        sess.page_crop_rects[2] = []
        app.add_session(sess)
        assert app.total_crop_count == 3

    def test_update_crop_rects(self):
        app = AppState()
        sess = _make_sess("a.jpg")
        app.add_session(sess)
        app.set_current("a.jpg")
        rects = [CropRect(5, 5, 10, 10)]
        app.update_crop_rects("a.jpg", rects)
        assert len(sess.crop_rects) == 1

    def test_update_crop_rects_pdf(self):
        app = AppState()
        sess = _make_sess("doc.pdf", is_pdf=True, page_count=2)
        sess.current_page = 1
        app.add_session(sess)
        app.set_current("doc.pdf")
        rects = [CropRect(1, 1, 2, 2)]
        app.update_crop_rects("doc.pdf", rects)
        assert len(sess.page_crop_rects[1]) == 1


class TestSessionState:
    def test_current_pdf_page_alias(self):
        sess = _make_sess("t.pdf", is_pdf=True, page_count=5)
        assert sess.current_pdf_page == 0
        sess.current_pdf_page = 3
        assert sess.current_page == 3

    def test_get_page_image_cache(self):
        sess = _make_sess("t.pdf", is_pdf=True, page_count=8)
        loads = [0]

        def loader(idx):
            loads[0] += 1
            return Image.new("RGB", (50, 50))

        sess.pdf_page_loader = loader

        # 加载 8 页
        for i in range(8):
            sess.get_page_image(i)
        assert loads[0] == 8
        # 缓存应保留最后 5 页
        assert len(sess._page_cache) == 5

        # 再次访问被淘汰的页应重新加载
        sess.get_page_image(0)
        assert loads[0] == 9

        # 缓存中的页不应重新加载
        sess.get_page_image(7)
        assert loads[0] == 9

    def test_get_page_image_no_loader(self):
        sess = _make_sess("t.pdf", is_pdf=True, page_count=1)
        with pytest.raises(RuntimeError, match="PDF page loader not set"):
            sess.get_page_image(0)
