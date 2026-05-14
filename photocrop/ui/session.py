"""
.. deprecated::
    ImageSession 已合并到 SessionState（photocrop.ui.state）。
    本文件保留向后兼容的别名，将在未来版本中移除。
"""

import warnings

from photocrop.ui.state import SessionState

warnings.warn(
    "ImageSession 已废弃，改用 photocrop.ui.state.SessionState",
    DeprecationWarning,
    stacklevel=2,
)

# 向后兼容别名
ImageSession = SessionState

__all__ = ["ImageSession"]
