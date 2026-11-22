from __future__ import annotations


class RecipeTypeClassifier:
    """按主要食材判断荤素。关键字在 config.json 的 recipe_type 中配置。

    对每个食材：
      1. 名字包含 veg_exceptions 中的词（鸡蛋、牛奶、鸡毛菜…）→ 跳过，不算荤；
      2. 否则名字包含 meat_words 中的词 → 整道菜判为荤；
    所有食材都没命中 → 素。
    """

    def __init__(self, meat_words: list[str], veg_exceptions: list[str]):
        self.meat_words = meat_words
        self.veg_exceptions = veg_exceptions

    def explain(self, ingredients: list[str]) -> tuple[str, str]:
        """返回 (类型, 理由)。"""
        for ing in ingredients:
            if any(w in ing for w in self.veg_exceptions):
                continue
            hit = next((w for w in self.meat_words if w in ing), None)
            if hit:
                return "荤", f"「{ing}」含「{hit}」"
        return "素", "主要食材中没有肉、禽、水产"

    def guess(self, ingredients: list[str]) -> str:
        return self.explain(ingredients)[0]
