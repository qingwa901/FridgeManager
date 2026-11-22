from __future__ import annotations

from common_lib import Base

from function.fridge_service import FridgeService
from function.group_service import GroupService
from function.recipe_service import RecipeService


class Recommender(Base):
    """根据冰箱里的食材推荐食谱。"""

    def __init__(self, fridge: FridgeService, recipes: RecipeService, groups: GroupService):
        self.fridge = fridge
        self.recipes = recipes
        self.groups = groups

    def recommend(self, max_missing: int = 2, rtype: str | None = None) -> list[dict]:
        """按"缺少的食材最少 → 用到的临期食材最多 → 匹配率最高"排序。过期食材不参与匹配。
        max_missing 为负数表示不限（包括冰箱里一种食材都没有的食谱）。rtype 可选，只推荐荤菜或素菜。"""
        foods = [f for f in self.fridge.list_foods() if f["status"] != "expired"]
        resolver = self.groups.resolver()
        unlimited = max_missing < 0
        results = []
        for r in self.recipes.list():
            if rtype and r["type"] != rtype:
                continue
            have, missing, expiring, used = [], [], [], {}
            for ing in r["ingredients"]:
                hit = resolver.find_food(ing, foods)
                if hit is None:
                    missing.append(ing)
                    continue
                have.append(ing)
                if hit["name"] != ing:
                    used[ing] = hit["name"]   # 页面显示成"菌菇（干香菇）"
                if hit["status"] == "expiring":
                    expiring.append(hit["name"])
            # 有数量限制时，至少要有一种食材在冰箱里（否则"缺 2 种"会混进一堆完全不相关的菜）；不限则全部显示
            if not unlimited and (not have or len(missing) > max_missing):
                continue
            results.append({**r, "have": have, "missing": missing, "uses_expiring": expiring, "used": used,
                            "match_rate": round(len(have) / len(r["ingredients"]), 2)})
        results.sort(key=lambda x: (len(x["missing"]), -len(x["uses_expiring"]), -x["match_rate"]))
        self.get_logger().info("推荐食谱：可用食材 %d 种，最多缺 %s 种，类型=%s，命中 %d 个食谱",
                               len(foods), "不限" if unlimited else max_missing, rtype or "全部", len(results))
        return results

    def daily(self, max_missing: int = 2) -> dict:
        """今日一荤一素：分别返回排好序的荤菜、素菜候选，第一个就是首选，前端可"换一换"。"""
        ranked = self.recommend(max_missing)
        return {t: [r for r in ranked if r["type"] == t] for t in ("荤", "素")}
