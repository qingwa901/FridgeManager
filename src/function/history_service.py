from __future__ import annotations

from common_lib import Base

from data import Database
from function.service_error import ServiceError


class HistoryService(Base):
    """输入记录：添加 / 修改食材时由 FridgeService 自动记录，这里负责查询和删除（比如删掉打错的名字）。"""

    def __init__(self, db: Database):
        self.db = db

    def list(self) -> list[dict]:
        """[{name, category, use_count, last_used}]，最近用过的在前。"""
        with self.db.session() as s:
            return s.history.list_all()

    def forget(self, name: str) -> None:
        with self.db.session() as s:
            if not s.history.delete(name):
                raise ServiceError(ServiceError.NOT_FOUND, "没有这条输入记录")
        self.get_logger().info("删除输入记录：%s", name)
