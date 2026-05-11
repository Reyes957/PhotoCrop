"""pytest 配置 — 在无 GUI 环境下 mock PySide6 GUI 依赖

PySide6.QtCore 可正常使用（不需要 native 库）。
只 mock QtGui / QtWidgets / QtSvg（需要 libEGL）。
"""

import sys
from unittest.mock import MagicMock


def _ensure_pyside6():
    """确保 PySide6 可导入（GUI 部分用 MagicMock 自动兜底）"""
    try:
        from PySide6.QtGui import QPainter  # noqa: F401
        return  # 全部正常，不需要 mock
    except (ImportError, OSError):
        pass

    # 只 mock 需要 native 库的子模块，保留 QtCore 真实实现
    for mod_name in ['PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg']:
        if mod_name not in sys.modules or not isinstance(sys.modules.get(mod_name), MagicMock):
            sys.modules[mod_name] = MagicMock()


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
