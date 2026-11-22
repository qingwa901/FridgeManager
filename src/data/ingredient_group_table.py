from __future__ import annotations

import json
import sqlite3

from common_lib import Base


class IngredientGroupTable(Base):
    """ingredient_groups 表：食材大类。members 是 JSON 数组，成员可以是具体食材，也可以是另一个大类名。"""

    # 第一次建表时放进去的示例大类，之后在网页上的"食材大类"（右上角齿轮）里增删改
    DEFAULT_GROUPS = {
        "菌菇": ["香菇", "干香菇", "鲜香菇", "羊角菇", "平菇", "金针菇", "杏鲍菇", "蘑菇", "口蘑", "茶树菇",
                 "鸡腿菇", "牛肝菌", "松茸", "木耳", "银耳"],
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self) -> None:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingredient_groups'").fetchone()
        if exists:
            return
        self.conn.execute(
            """
            CREATE TABLE ingredient_groups (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL UNIQUE,
                members TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        for name, members in self.DEFAULT_GROUPS.items():
            self.insert(name, members)
        self.get_logger().info("数据库升级：新增食材大类表，预置 %s", "、".join(self.DEFAULT_GROUPS))

    @staticmethod
    def to_dict(row: sqlite3.Row) -> dict:
        return {"id": row["id"], "name": row["name"], "members": json.loads(row["members"])}

    def list_all(self) -> list[dict]:
        return [self.to_dict(r) for r in self.conn.execute("SELECT * FROM ingredient_groups ORDER BY name")]

    def as_map(self) -> dict[str, list[str]]:
        """{大类名: [直接包含的食材或大类]}"""
        return {g["name"]: g["members"] for g in self.list_all()}

    def get(self, group_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM ingredient_groups WHERE id=?", (group_id,)).fetchone()
        return self.to_dict(row) if row else None

    def name_taken(self, name: str, exclude_id: int | None = None) -> bool:
        return self.conn.execute("SELECT 1 FROM ingredient_groups WHERE name=? AND id IS NOT ?",
                                 (name, exclude_id)).fetchone() is not None

    def insert(self, name: str, members: list[str]) -> int:
        cur = self.conn.execute("INSERT INTO ingredient_groups (name, members) VALUES (?, ?)",
                                (name, json.dumps(members, ensure_ascii=False)))
        return cur.lastrowid

    def update(self, group_id: int, name: str, members: list[str]) -> bool:
        cur = self.conn.execute("UPDATE ingredient_groups SET name=?, members=? WHERE id=?",
                                (name, json.dumps(members, ensure_ascii=False), group_id))
        return cur.rowcount > 0

    def rename_member(self, old: str, new: str, exclude_id: int | None = None) -> None:
        """其他大类里引用 old 的地方改成 new（大类改名时用）。"""
        for g in self.list_all():
            if g["id"] != exclude_id and old in g["members"]:
                members = list(dict.fromkeys(new if m == old else m for m in g["members"]))
                self.update(g["id"], g["name"], members)

    def delete(self, group_id: int) -> bool:
        return self.conn.execute("DELETE FROM ingredient_groups WHERE id=?", (group_id,)).rowcount > 0
