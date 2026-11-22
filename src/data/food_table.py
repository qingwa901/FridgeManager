from __future__ import annotations

import sqlite3


class FoodTable:
    """foods 表：冰箱里的食材。数量为"缺货"的条目就是补货清单。
    expiry_date 列不允许 NULL，不设保质期时存空字符串。"""

    SHORTAGE = "缺货"
    COLUMNS = ("name", "quantity", "category", "added_date", "expiry_date", "note")

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS foods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                quantity    TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT '其他',
                added_date  TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                note        TEXT NOT NULL DEFAULT ''
            )
            """
        )

    def list_in_fridge(self) -> list[sqlite3.Row]:
        """冰箱里的食材（不含缺货条目）。"""
        return self.conn.execute("SELECT * FROM foods WHERE quantity != ?", (self.SHORTAGE,)).fetchall()

    def list_shortage(self) -> list[sqlite3.Row]:
        """补货清单，按加入时间排序。"""
        return self.conn.execute("SELECT * FROM foods WHERE quantity = ? ORDER BY added_date, id",
                                 (self.SHORTAGE,)).fetchall()

    def get(self, food_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone()

    def find_shortage(self, name: str, exclude_id: int | None = None) -> sqlite3.Row | None:
        """补货清单里同名的条目。"""
        return self.conn.execute("SELECT * FROM foods WHERE name=? AND quantity=? AND id IS NOT ?",
                                 (name, self.SHORTAGE, exclude_id)).fetchone()

    def insert(self, values: dict) -> int:
        cur = self.conn.execute(
            f"INSERT INTO foods ({', '.join(self.COLUMNS)}) VALUES ({', '.join('?' * len(self.COLUMNS))})",
            tuple(values[c] for c in self.COLUMNS))
        return cur.lastrowid

    def update(self, food_id: int, values: dict) -> bool:
        cur = self.conn.execute(f"UPDATE foods SET {', '.join(f'{c}=?' for c in self.COLUMNS)} WHERE id=?",
                                (*(values[c] for c in self.COLUMNS), food_id))
        return cur.rowcount > 0

    def delete(self, food_id: int) -> bool:
        return self.conn.execute("DELETE FROM foods WHERE id=?", (food_id,)).rowcount > 0
