from __future__ import annotations

import sqlite3
from datetime import datetime

from common_lib import Base


class ItemHistoryTable(Base):
    """item_history 表：输入过的每样东西和它的种类。删除食材时不删这里，下次添加时用来建议名称、自动选种类。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self) -> None:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_history'").fetchone()
        if exists:
            return
        self.conn.execute(
            """
            CREATE TABLE item_history (
                name      TEXT PRIMARY KEY,
                category  TEXT NOT NULL,             -- 最近一次用的种类
                use_count INTEGER NOT NULL DEFAULT 1,
                last_used TEXT NOT NULL              -- 最近一次添加 / 修改的时间
            )
            """
        )
        # 第一次建表：把现在冰箱和补货清单里的东西先记进去（种类取最近存入的那一条）
        cur = self.conn.execute(
            """
            INSERT INTO item_history (name, category, use_count, last_used)
            SELECT name, category, COUNT(*), MAX(added_date) FROM foods GROUP BY name
            """
        )
        self.get_logger().info("数据库升级：新增输入记录表，已从现有食材导入 %d 条", cur.rowcount)

    def record(self, name: str, category: str) -> None:
        """记一次：新名字就新增；已有的更新种类、次数加一。"""
        self.conn.execute(
            """
            INSERT INTO item_history (name, category, use_count, last_used) VALUES (?, ?, 1, ?)
            ON CONFLICT(name) DO UPDATE SET category=excluded.category, use_count=use_count + 1,
                                            last_used=excluded.last_used
            """,
            (name, category, datetime.now().isoformat(timespec="seconds")))

    def list_all(self) -> list[dict]:
        """最近用过的在前。"""
        rows = self.conn.execute("SELECT * FROM item_history ORDER BY last_used DESC, use_count DESC").fetchall()
        return [dict(r) for r in rows]

    def delete(self, name: str) -> bool:
        return self.conn.execute("DELETE FROM item_history WHERE name=?", (name,)).rowcount > 0
