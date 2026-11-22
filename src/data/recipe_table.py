from __future__ import annotations

import json
import sqlite3

from common_lib import Base


class RecipeTable(Base):
    """recipes 表：食谱库。ingredients / seasonings / steps / amounts 以 JSON 存储，读出时自动解码。"""

    JSON_COLUMNS = ("ingredients", "seasonings", "steps", "amounts")
    # 旧数据库升级时补的列
    MIGRATIONS = (("type", "TEXT NOT NULL DEFAULT ''"),          # '荤' / '素'
                  ("amounts", "TEXT NOT NULL DEFAULT '{}'"),     # JSON：{食材/调料名: 用量}
                  ("source_url", "TEXT NOT NULL DEFAULT ''"))    # 导入来源链接

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                ingredients TEXT NOT NULL,              -- JSON 数组：主要食材
                seasonings  TEXT NOT NULL DEFAULT '[]', -- JSON 数组：调料（默认家中常备）
                steps       TEXT NOT NULL DEFAULT '[]', -- JSON 数组：步骤
                minutes     INTEGER NOT NULL DEFAULT 20,
                type        TEXT NOT NULL DEFAULT ''    -- '荤' 或 '素'
            )
            """
        )
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(recipes)")}
        for col, ddl in self.MIGRATIONS:
            if col not in cols:
                self.conn.execute(f"ALTER TABLE recipes ADD COLUMN {col} {ddl}")
                self.get_logger().info("数据库升级：recipes 表新增 %s 列", col)

    @classmethod
    def to_dict(cls, row: sqlite3.Row) -> dict:
        d = dict(row)
        for k in cls.JSON_COLUMNS:
            d[k] = json.loads(d[k])
        return d

    @classmethod
    def encode(cls, values: dict) -> dict:
        """列表 / 字典类型的列转成 JSON 文本。"""
        return {k: json.dumps(v, ensure_ascii=False) if k in cls.JSON_COLUMNS else v for k, v in values.items()}

    def list_all(self) -> list[dict]:
        return [self.to_dict(r) for r in self.conn.execute("SELECT * FROM recipes ORDER BY name")]

    def get(self, recipe_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        return self.to_dict(row) if row else None

    def name_exists(self, name: str) -> bool:
        return self.conn.execute("SELECT 1 FROM recipes WHERE name=?", (name,)).fetchone() is not None

    def insert(self, values: dict) -> int:
        """同名食谱已存在时抛 sqlite3.IntegrityError。"""
        v = self.encode(values)
        cur = self.conn.execute(f"INSERT INTO recipes ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                                tuple(v.values()))
        return cur.lastrowid

    def insert_if_absent(self, values: dict) -> bool:
        """同名已存在则跳过，返回是否插入了。"""
        v = self.encode(values)
        cur = self.conn.execute(f"INSERT OR IGNORE INTO recipes ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})",
                                tuple(v.values()))
        return cur.rowcount > 0

    def update(self, recipe_id: int, values: dict) -> bool:
        """改名成已有的名字时抛 sqlite3.IntegrityError。"""
        v = self.encode(values)
        cur = self.conn.execute(f"UPDATE recipes SET {', '.join(f'{k}=?' for k in v)} WHERE id=?",
                                (*v.values(), recipe_id))
        return cur.rowcount > 0

    def set_type(self, recipe_id: int, rtype: str) -> bool:
        return self.conn.execute("UPDATE recipes SET type=? WHERE id=?", (rtype, recipe_id)).rowcount > 0

    def list_untyped(self) -> list[dict]:
        """没有荤素标记的食谱。"""
        return [self.to_dict(r) for r in self.conn.execute("SELECT * FROM recipes WHERE type NOT IN ('荤','素')")]

    def delete(self, recipe_id: int) -> bool:
        return self.conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,)).rowcount > 0
