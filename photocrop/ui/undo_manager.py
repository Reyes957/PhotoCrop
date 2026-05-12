"""
UndoManager — 裁剪框操作的撤销/重做管理器

维护两个栈：undo_stack 和 redo_stack。
每个栈帧是一组 CropRect 的深拷贝快照。

v0.6.4: serialize/deserialize 保存完整双栈（而非单帧），
Session 切换后撤销历史不丢失。

用法：
    manager = UndoManager()
    manager.push_state(current_rects)  # 保存当前状态
    rects = manager.undo()             # 撤销，返回上一个状态
    rects = manager.redo()             # 重做，返回下一个状态
"""

from __future__ import annotations

import copy
import json

from photocrop.utils.crop_rect import CropRect


def _rect_to_dict(r: CropRect) -> dict:
    return {
        "x": r.x, "y": r.y, "width": r.width, "height": r.height,
        "rotation_angle": r.rotation_angle,
        "source_type": r.source_type, "page_num": r.page_num,
    }


def _rect_from_dict(d: dict) -> CropRect:
    return CropRect(**d)


class UndoManager:
    """裁剪框撤销/重做管理器"""

    def __init__(self, max_history: int = 50):
        self._undo_stack: list[list[CropRect]] = []
        self._redo_stack: list[list[CropRect]] = []
        self._max_history = max_history

    def push_state(self, rects: list[CropRect]) -> None:
        """保存当前状态到撤销栈（清空重做栈）"""
        snapshot = [copy.deepcopy(r) for r in rects]
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> list[CropRect] | None:
        """撤销，返回上一个状态（或 None 如果无法撤销）"""
        if len(self._undo_stack) < 2:
            return None  # 需要至少两帧：当前 + 上一个

        # 当前状态推入 redo 栈
        current = self._undo_stack.pop()
        self._redo_stack.append(current)

        # 返回上一个状态的深拷贝
        previous = self._undo_stack[-1]
        return [copy.deepcopy(r) for r in previous]

    def redo(self) -> list[CropRect] | None:
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

    # ================================================================
    # 序列化 — 保存完整双栈（v0.6.4 修复）
    # ================================================================

    def serialize(self) -> str:
        """将完整的 undo_stack + redo_stack 序列化为 JSON 字符串

        v0.6.4: 保存完整双栈结构（而非仅最后一帧），
        Session 切换后撤销/重做历史完整保留。
        """
        data = {
            "undo": [[_rect_to_dict(r) for r in frame]
                     for frame in self._undo_stack],
            "redo": [[_rect_to_dict(r) for r in frame]
                     for frame in self._redo_stack],
        }
        return json.dumps(data)

    def deserialize(self, snapshot: str | list) -> None:
        """从序列化数据恢复完整的 undo/redo 栈

        v0.6.4: 恢复完整双栈结构。兼容旧版 list 格式（单帧回退）。

        Args:
            snapshot: JSON 字符串（新格式）或 dict 列表（旧格式兼容）
        """
        # 兼容旧版：list 格式只有一帧
        if isinstance(snapshot, list):
            self.clear()
            if snapshot:
                self.push_state([_rect_from_dict(d) for d in snapshot])
            return

        try:
            data = json.loads(snapshot)
        except (json.JSONDecodeError, TypeError):
            self.clear()
            return

        self._undo_stack = [
            [_rect_from_dict(r) for r in frame]
            for frame in data.get("undo", [])
        ]
        self._redo_stack = [
            [_rect_from_dict(r) for r in frame]
            for frame in data.get("redo", [])
        ]

    # ================================================================
    # 旧版兼容接口（保留给非关键路径）
    # ================================================================

    def serialize_legacy(self) -> list:
        """旧版序列化：仅保存最后一帧（向后兼容）"""
        if not self._undo_stack:
            return []
        current = self._undo_stack[-1]
        return [_rect_to_dict(r) for r in current]

    def deserialize_legacy(self, data: list) -> list[CropRect]:
        """旧版反序列化：从 dict 列表恢复为 CropRect 列表"""
        rects = [_rect_from_dict(d) for d in data]
        self.clear()
        self.push_state(rects)
        return rects
