from __future__ import annotations

import sqlite3


class SeedImportedTable:
    """seed_imported 表：记录导入过的内置食谱名。新增的内置食谱会自动导入，用户删掉的不会再被加回来。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS seed_imported (name TEXT PRIMARY KEY)")

    def names(self) -> set[str]:
        return {r["name"] for r in self.conn.execute("SELECT name FROM seed_imported")}

    def add(self, name: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO seed_imported (name) VALUES (?)", (name,))
