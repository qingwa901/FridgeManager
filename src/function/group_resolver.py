from __future__ import annotations


class GroupResolver:
    """按食材大类匹配食材。名字必须完全相同，不按字面包含匹配（避免"葱"匹配到"洋葱"）。

    用一份大类快照创建：{大类名: [直接包含的食材或大类]}，嵌套的大类会层层展开。"""

    def __init__(self, groups: dict[str, list[str]]):
        self.groups = groups
        self.expanded = self.expand(groups)

    @staticmethod
    def expand(groups: dict[str, list[str]]) -> dict[str, list[str]]:
        """{大类名: [所有能算作这个大类的名字]}。即使有循环引用也不会死循环。"""
        def walk(name: str, seen: set[str]) -> list[str]:
            out = []
            for m in groups.get(name, ()):
                out.append(m)
                if m in groups and m not in seen:
                    out += walk(m, seen | {m})
            return out
        return {g: list(dict.fromkeys(walk(g, {g}))) for g in groups}

    def in_group(self, group: str, food_name: str) -> bool:
        """food_name 是否属于大类 group（和大类里展开后的某个名字完全相同）。"""
        return food_name in self.expanded.get(group, ())

    def satisfies(self, ingredient: str, food_name: str) -> bool:
        """冰箱里的 food_name 能不能当 ingredient 用：名字相同，或者 ingredient 是大类且 food_name 属于它。"""
        return food_name == ingredient or self.in_group(ingredient, food_name)

    def find_food(self, ingredient: str, foods: list[dict]) -> dict | None:
        """在冰箱食材里找能满足 ingredient 的一样：先找同名的，没有再按大类找。
        食谱写具体食材（如"香菇"）时不会用同类的其他食材代替。foods 已按临期在前排好。"""
        hit = next((f for f in foods if f["name"] == ingredient), None)
        if hit is None and ingredient in self.expanded:
            hit = next((f for f in foods if self.in_group(ingredient, f["name"])), None)
        return hit
