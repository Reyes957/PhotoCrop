"""
UndoManager — 裁剪框操作的撤销/重做管理器

维护两个栈：undo_stack 和 redo_stack。
每个栈帧是一组 CropRect 的深拷贝快照。

用法：
    manager = UndoManager()
    manager.push_state(current_rects)  # 保存当前状态
    rects = manager.undo()             # 撤销，返回上一个状态
    rects = manager.redo()             # 重做，返回下一个状态
"""

from __future__ import annotations

import copy
from typing import List, Optional

from photocrop.utils.crop_rect import CropRect


class UndoManager:
    """裁剪框撤销/重做管理器"""

    def __init__(self, max_history: int = 50):
        self._undo_stack: List[List[CropRect]] = []
        self._redo_stack: List[List[CropRect]] = []
        self._max_history = max_history

    def push_state(self, rects: List[CropRect]) -> None:
        """保存当前状态到撤销栈（清空重做栈）"""
        snapshot = [copy.deepcopy(r) for r in rects]
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> Optional[List[CropRect]]:
        """撤销，返回上一个状态（或 None 如果无法撤销）"""
        if len(self._undo_stack) < 2:
            return None  # 需要至少两帧：当前 + 上一个

        # 当前状态推入 redo 栈
        current = self._undo_stack.pop()
        self._redo_stack.append(current)

        # 返回上一个状态的深拷贝
        previous = self._undo_stack[-1]
        return [copy.deepcopy(r) for r in previous]

    def redo(self) -> Optional[List[CropRect]]:
        """重做，返回下一个状态（或 None 如果无法重做）"""
        if not self._redo_stack:
            return None

        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        return [copy.deepcopy(r) for r in state]

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return len(self._undo_stack) >= 2

    def can_redo(self) -> bool:
        """是否可以重做"""
        return len(self._redo_stack) > 0

    def clear(self) -> None:
        """清空所有历史"""
        self._undo_stack.clear()
        self._redo_stack.clear()

    def serialize(self) -> list:
        """将 undo_stack 最后一帧序列化为可 JSON 的 dict 列表

        用于多图像管理：保存当前图像的裁剪框状态。
        """
        if not self._undo_stack:
            return []
        current = self._undo_stack[-1]
        return [
            {
                "x": r.x, "y": r.y, "width": r.width, "height": r.height,
                "rotation_angle": r.rotation_angle,
                "source_type": r.source_type, "page_num": r.page_num,
            }
            for r in current
        ]

    def deserialize(self, data: list) -> List[CropRect]:
        """从 dict 列表恢复为 CropRect 列表，并推入 undo 栈作为初始状态

        用于多图像管理：切换图像时恢复裁剪框状态。
        """
        rects = [CropRect(**d) for d in data]
        self.clear()
        self.push_state(rects)
        return rects
