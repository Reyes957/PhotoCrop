"""SessionController 单元测试"""

from pathlib import Path

from PIL import Image

from photocrop.ui.controllers.session_controller import SessionController
from photocrop.ui.state import AppState
from photocrop.utils.crop_rect import CropRect


class TestSessionController:
    def test_load_image(self, tmp_path):
        app = AppState()
        ctrl = SessionController(app)

        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (200, 200), color="red").save(img_path)

        sess = ctrl.load_file(str(img_path))
        assert sess is not None
        assert sess.key == str(img_path)
        assert not sess.is_pdf
        assert sess.source_image.size == (200, 200)
        assert len(sess.page_thumbnails) == 1

    def test_load_image_rgba(self, tmp_path):
        """RGBA 图片应保留 alpha 通道"""
        app = AppState()
        ctrl = SessionController(app)

        img_path = tmp_path / "rgba.png"
        Image.new("RGBA", (100, 100)).save(img_path)

        sess = ctrl.load_file(str(img_path))
        assert sess is not None
        assert sess.source_image.mode == "RGBA"

    def test_load_nonexistent(self):
        """加载不存在的文件应返回 None 并发射 load_error"""
        app = AppState()
        ctrl = SessionController(app)

        errors = []
        ctrl.load_error.connect(lambda p, e: errors.append((p, e)))

        result = ctrl.load_file("/tmp/nonexistent_file_12345.jpg")
        assert result is None
        assert len(errors) == 1

    def test_save_and_restore(self, tmp_path):
        """保存裁剪框到 session，然后恢复"""
        app = AppState()
        ctrl = SessionController(app)

        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100)).save(img_path)

        sess = ctrl.load_file(str(img_path))
        app.add_session(sess)
        app.set_current(str(img_path))

        # 保存裁剪框
        rects = [CropRect(10, 10, 20, 20), CropRect(50, 50, 30, 30)]
        ctrl.save_current_state(rects, [])
        assert len(sess.crop_rects) == 2

    def test_remove_session(self, tmp_path):
        app = AppState()
        ctrl = SessionController(app)

        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100)).save(img_path)
        sess = ctrl.load_file(str(img_path))
        app.add_session(sess)

        next_key = ctrl.remove_session(str(img_path))
        assert next_key is None
        assert app.session_count == 0

    def test_remove_session_next_key(self, tmp_path):
        """删除一个 session 后应返回另一个 session 的 key"""
        app = AppState()
        ctrl = SessionController(app)

        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        Image.new("RGB", (100, 100)).save(a)
        Image.new("RGB", (100, 100)).save(b)

        sa = ctrl.load_file(str(a))
        sb = ctrl.load_file(str(b))
        app.add_session(sa)
        app.add_session(sb)

        next_key = ctrl.remove_session(str(a))
        assert next_key is not None
        assert app.session_count == 1

    def test_get_sibling_page_key(self):
        app = AppState()
        ctrl = SessionController(app)

        from photocrop.ui.state import SessionState
        sess = SessionState(
            key="doc.pdf", source_path=Path("doc.pdf"),
            source_image=Image.new("RGB", (100, 100)),
            is_pdf=True, page_count=5,
        )
        app.add_session(sess)

        pk0 = app.get_page_key("doc.pdf", 0)
        pk4 = app.get_page_key("doc.pdf", 4)

        assert ctrl.get_sibling_page_key(pk0, -1) is None
        assert ctrl.get_sibling_page_key(pk0, 1) == "doc.pdf##PAGE##1"
        assert ctrl.get_sibling_page_key(pk4, 1) is None
        assert ctrl.get_sibling_page_key(pk4, -1) == "doc.pdf##PAGE##3"

    def test_get_current_pdf_session_none(self):
        """非 PDF 时应返回 None"""
        app = AppState()
        ctrl = SessionController(app)
        assert ctrl.get_current_pdf_session() is None

    def test_close_all(self, tmp_path):
        """close_all 不应抛异常"""
        app = AppState()
        ctrl = SessionController(app)
        ctrl.close_all()  # 无 PDF 句柄时也不报错
