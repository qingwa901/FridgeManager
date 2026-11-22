from __future__ import annotations

import sqlite3
from datetime import date

from common_lib import Base

from api.schemas import FoodIn
from data import Database, Session
from function.group_resolver import GroupResolver
from function.service_error import ServiceError


class FridgeService(Base):
    """冰箱食材和补货清单（数量为"缺货"的条目）。"""

    def __init__(self, db: Database, expiring_days: int):
        self.db = db
        self.expiring_days = expiring_days   # 剩余天数 <= 该值视为"即将过期"

    def to_view(self, row: sqlite3.Row) -> dict:
        """加上 days_stored（已存天数）、days_left、status：expired / expiring / fresh / none（未设保质期）。"""
        d = dict(row)
        today = date.today()
        d["days_stored"] = (today - date.fromisoformat(d["added_date"])).days
        if not d["expiry_date"]:
            d.update(expiry_date=None, days_left=None, status="none")
            return d
        days_left = (date.fromisoformat(d["expiry_date"]) - today).days
        d["days_left"] = days_left
        d["status"] = "expired" if days_left < 0 else "expiring" if days_left <= self.expiring_days else "fresh"
        return d

    def list_foods(self) -> list[dict]:
        """冰箱里的食材（不含缺货条目）。
        排序：已过期、即将过期的排在最前（按到期日）；其余按存入日期从早到晚（先放进去的先吃）。"""
        with self.db.session() as s:
            foods = [self.to_view(r) for r in s.foods.list_in_fridge()]
        urgent = lambda f: f["status"] in ("expired", "expiring")
        foods.sort(key=lambda f: (0, f["expiry_date"], f["name"]) if urgent(f) else (1, f["added_date"], f["name"]))
        return foods

    def list_shopping(self) -> list[dict]:
        with self.db.session() as s:
            return [self.to_view(r) for r in s.foods.list_shortage()]

    def add(self, food: FoodIn) -> dict:
        """数量为"缺货" = 加入补货清单（同名已在清单里则不重复添加，返回 duplicate）；
        其他数量 = 放进冰箱，并自动删掉补货清单里对应的条目（返回 restocked 条数）。"""
        with self.db.session() as s:
            if food.is_shortage and (dup := s.foods.find_shortage(food.name)):
                return {**self.to_view(dup), "duplicate": True}
            food_id = s.foods.insert(food.db_values())
            restocked = 0 if food.is_shortage else self._clear_shortage(s, food.name)
            row = s.foods.get(food_id)
        if food.is_shortage:
            self.get_logger().info("加入补货清单 #%d %s", row["id"], row["name"])
        else:
            self.get_logger().info("添加食材 #%d %s 数量=%s 存入=%s 保质期至=%s", row["id"], row["name"], row["quantity"],
                                   row["added_date"], row["expiry_date"] or "未设")
        return {**self.to_view(row), "restocked": restocked}

    def update(self, food_id: int, food: FoodIn) -> dict:
        with self.db.session() as s:
            if food.is_shortage and (dup := s.foods.find_shortage(food.name, exclude_id=food_id)):
                # 吃完了：补货清单里已有同名条目就合并（删掉这一条），不重复
                if not s.foods.delete(food_id):
                    raise ServiceError(ServiceError.NOT_FOUND, "食材不存在")
                self.get_logger().info("食材 #%d %s 吃完，补货清单里已有，合并", food_id, food.name)
                return {**self.to_view(dup), "duplicate": True}
            if not s.foods.update(food_id, food.db_values()):
                raise ServiceError(ServiceError.NOT_FOUND, "食材不存在")
            restocked = 0 if food.is_shortage else self._clear_shortage(s, food.name, keep_id=food_id)
            row = s.foods.get(food_id)
        self.get_logger().info("更新食材 #%d %s 数量=%s 保质期至=%s", food_id, row["name"], row["quantity"], row["expiry_date"] or "未设")
        return {**self.to_view(row), "restocked": restocked}

    def delete(self, food_id: int) -> None:
        with self.db.session() as s:
            row = s.foods.get(food_id)
            if row is None:
                raise ServiceError(ServiceError.NOT_FOUND, "食材不存在")
            s.foods.delete(food_id)
        self.get_logger().info("删除食材 #%d %s", food_id, row["name"])

    @classmethod
    def _clear_shortage(cls, s: Session, name: str, keep_id: int | None = None) -> int:
        """补货了：删除补货清单里同名的条目；清单里是大类（如"菌菇"）、买回的是其中一样（如"羊角菇"）也删。"""
        resolver = GroupResolver(s.groups.as_map())
        hits = [r for r in s.foods.list_shortage() if r["id"] != keep_id and resolver.satisfies(r["name"], name)]
        for r in hits:
            s.foods.delete(r["id"])
            cls.get_logger().info("补货：已从补货清单移除「%s」（添加了「%s」）", r["name"], name)
        return len(hits)
