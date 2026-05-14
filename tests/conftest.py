"""pytest 配置 — 在无 GUI 环境下 mock PySide6

当 PySide6 完全未安装时，提供可子类化的 QObject / Signal mock。
当 PySide6 已安装但缺少 native 库时，只 mock GUI 子模块。
"""

import sys
from unittest.mock import MagicMock


class _MockQObject:
    """可子类化的 QObject 替代品 — 让 AppState / ThemeManager 等能正常实例化"""

    def __init__(self, *args, **kwargs):
        pass


class _MockSignal:
    """可调用的 Signal 替代品"""

    def __init__(self, *args, **kwargs):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if slot:
            self._slots.remove(slot)
        else:
            self._slots.clear()

    def emit(self, *args, **kwargs):
        for slot in self._slots:
            slot(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """Signal(...) 作为类变量声明时的协议"""
        return _MockSignal()


def _build_mock_pyside6():
    """构建结构化的 PySide6 mock，保留 QObject / Signal 的可继承性"""
    core = MagicMock()
    core.QObject = _MockQObject
    core.Signal = _MockSignal
    core.Qt = MagicMock()
    core.QTimer = MagicMock()
    core.QEasingCurve = MagicMock()
    core.QVariantAnimation = MagicMock()
    core.QPoint = MagicMock()
    core.QPointF = MagicMock()
    core.QRectF = MagicMock()
    core.QPropertyAnimation = MagicMock()
    core.QByteArray = MagicMock()

    gui = MagicMock()
    widgets = MagicMock()
    svg = MagicMock()

    # 构建包结构
    pyside6 = MagicMock()
    pyside6.QtCore = core
    pyside6.QtGui = gui
    pyside6.QtWidgets = widgets
    pyside6.QtSvg = svg

    return pyside6, core, gui, widgets, svg


def _ensure_pyside6():
    """确保 PySide6 可导入（GUI 部分用结构化 mock 自动兜底）"""
    try:
        import PySide6  # noqa: F401
        from PySide6.QtGui import QPainter  # noqa: F401
        return  # 全部正常，不需要 mock
    except (ImportError, OSError):
        pass

    pyside6, core, gui, widgets, svg = _build_mock_pyside6()
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = core
    sys.modules["PySide6.QtGui"] = gui
    sys.modules["PySide6.QtWidgets"] = widgets
    sys.modules["PySide6.QtSvg"] = svg


_ensure_pyside6()


import pytest


@pytest.fixture(scope="session")
def qapp():
    """创建全局 QApplication（仅在有 GUI 环境时可用）"""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    except (ImportError, RuntimeError):
        pytest.skip("PySide6 GUI 环境不可用")
