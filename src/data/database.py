from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from common_lib import Base

from data.session import Session


class Database(Base):
    """SQLite 数据库。每次 session() 打开一个连接、一个事务：正常结束提交，出异常回滚。"""

    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def session(self) -> Iterator[Session]:
        conn = self.connect()
        try:
            with conn:
                yield Session(conn)
        finally:
            conn.close()

    def initialize(self) -> None:
        """建表，并把旧数据库升级到当前结构。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as s:
            s.foods.create()
            s.recipes.create()
            s.seeds.create()
            s.groups.create()
            s.history.create()   # 放在 foods 之后：第一次建表时要从 foods 导入
        self.get_logger().info("数据库已就绪：%s", self.path)
