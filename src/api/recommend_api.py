from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from function.recommender import Recommender


class RecommendApi:
    """推荐食谱。"""

    def __init__(self, recommender: Recommender):
        self.recommender = recommender
        self.router = APIRouter(prefix="/api")
        self.router.add_api_route("/recommend", self.recommend, methods=["GET"])
        self.router.add_api_route("/daily", self.daily, methods=["GET"])

    def recommend(self, max_missing: int = 2, type: Literal["荤", "素"] | None = None):
        """max_missing 为负数表示不限；type 可选，只推荐荤菜或素菜。"""
        return self.recommender.recommend(max_missing, type)

    def daily(self, max_missing: int = 2):
        """今日一荤一素：{"荤": [...], "素": [...]}，各自按推荐顺序排列。"""
        return self.recommender.daily(max_missing)
