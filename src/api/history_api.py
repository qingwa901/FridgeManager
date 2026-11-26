from __future__ import annotations

from fastapi import APIRouter

from function.history_service import HistoryService


class HistoryApi:
    """输入记录：输入过的每样东西和它的种类（删除食材后也保留），用于名称下拉建议和自动选种类。"""

    def __init__(self, history: HistoryService):
        self.history = history
        self.router = APIRouter(prefix="/api/history")
        self.router.add_api_route("", self.list_history, methods=["GET"])
        self.router.add_api_route("/{name}", self.forget, methods=["DELETE"], status_code=204)

    def list_history(self):
        """[{name, category, use_count, last_used}]，最近用过的在前。"""
        return self.history.list()

    def forget(self, name: str):
        """删除一条输入记录（比如打错的名字），不影响冰箱里的食材。"""
        self.history.forget(name)
