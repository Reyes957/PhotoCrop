"""ExportController 单元测试"""

from photocrop.ui.controllers.export_controller import ExportController


class TestFillTemplate:
    """测试 ExportController._fill_template 静态方法"""

    def test_basic_template(self):
        result = ExportController._fill_template(
            "{name}_p{page}_{index:02d}.{ext}", "test", 2, 5, "jpg",
        )
        assert result == "test_p2_05.jpg"

    def test_no_index_auto_append(self):
        """不含 {index} 的模板应自动追加序号"""
        result = ExportController._fill_template(
            "{name}.{ext}", "test", 1, 3, "png",
        )
        assert result == "test_03.png"

    def test_no_index_with_page(self):
        result = ExportController._fill_template(
            "{name}_p{page}.{ext}", "doc", 1, 1, "jpg",
        )
        assert result == "doc_p1_01.jpg"

    def test_complex_format(self):
        result = ExportController._fill_template(
            "{name}_page{page}_photo{index:03d}.{ext}", "album", 10, 1, "jpg",
        )
        assert result == "album_page10_photo001.jpg"

    def test_index_no_format(self):
        """{index} 无格式化时应使用默认 d 格式"""
        result = ExportController._fill_template(
            "{name}_{index}.{ext}", "img", 1, 7, "tiff",
        )
        assert result == "img_7.tiff"

    def test_no_extension_in_template(self):
        """模板无 .ext 时应追加 _01"""
        result = ExportController._fill_template(
            "{name}_p{page}", "file", 1, 2, "jpg",
        )
        assert result == "file_p1_02"
