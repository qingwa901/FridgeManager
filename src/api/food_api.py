from __future__ import annotations

from fastapi import APIRouter

from api.schemas import FoodIn
from function.fridge_service import FridgeService


class FoodApi:
    """冰箱食材和补货清单。"""

    def __init__(self, fridge: FridgeService):
        self.fridge = fridge
        self.router = APIRouter(prefix="/api")
        r = self.router
        r.add_api_route("/foods", self.list_foods, methods=["GET"])
        r.add_api_route("/foods", self.add_food, methods=["POST"], status_code=201)
        r.add_api_route("/foods/{food_id}", self.update_food, methods=["PUT"])
        r.add_api_route("/foods/{food_id}", self.delete_food, methods=["DELETE"], status_code=204)
        r.add_api_route("/shopping", self.list_shopping, methods=["GET"])

    def list_foods(self):
        """冰箱里的食材（不含"缺货"条目），临期的排前面。"""
        return self.fridge.list_foods()

    def list_shopping(self):
        """补货清单：数量为"缺货"的条目，按加入时间排序。"""
        return self.fridge.list_shopping()

    def add_food(self, food: FoodIn):
        """添加食材。数量为"缺货" = 加入补货清单；其他数量 = 放进冰箱，并自动删掉补货清单里对应的条目。"""
        return self.fridge.add(food)

    def update_food(self, food_id: int, food: FoodIn):
        return self.fridge.update(food_id, food)

    def delete_food(self, food_id: int):
        self.fridge.delete(food_id)
