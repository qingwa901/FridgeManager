from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from common_lib import Base

from api.schemas import RecipeIn
from data import Database
from function.recipe_type_classifier import RecipeTypeClassifier
from function.service_error import ServiceError
from importer import RecipeImporter, RecipeImportError


class RecipeService(Base):
    """食谱库：增删改查、内置食谱导入、从链接识别食谱。"""

    def __init__(self, db: Database, classifier: RecipeTypeClassifier, importer: RecipeImporter, seed_file: Path):
        self.db = db
        self.classifier = classifier
        self.importer = importer
        self.seed_file = seed_file

    def load_seeds(self) -> None:
        """把 seed_file（config/recipes.json）里新增的内置食谱导入数据库；用户删掉的不会再被加回来。
        同时给没有荤素标记的食谱补上标记：内置食谱里有就用内置的，否则按食材判断。"""
        seeds = json.loads(self.seed_file.read_text(encoding="utf-8")) if self.seed_file.exists() else []
        seed_type = {r["name"]: r.get("type") or self.classifier.guess(r["ingredients"]) for r in seeds}
        added = 0
        with self.db.session() as s:
            imported = s.seeds.names()
            for r in seeds:
                if r["name"] in imported:
                    continue
                added += s.recipes.insert_if_absent({
                    "name": r["name"], "ingredients": r["ingredients"], "seasonings": r.get("seasonings", []),
                    "steps": r.get("steps", []), "minutes": r.get("minutes", 20), "type": seed_type[r["name"]],
                })
                s.seeds.add(r["name"])
            for r in s.recipes.list_untyped():
                s.recipes.set_type(r["id"], seed_type.get(r["name"]) or self.classifier.guess(r["ingredients"]))
        if added:
            self.get_logger().info("从 %s 导入 %d 个新食谱", self.seed_file.name, added)

    def list(self) -> list[dict]:
        with self.db.session() as s:
            return s.recipes.list_all()

    def add(self, recipe: RecipeIn) -> dict:
        values, reason = self._values(recipe)
        try:
            with self.db.session() as s:
                row = s.recipes.get(s.recipes.insert(values))
        except sqlite3.IntegrityError:
            self.get_logger().warning("添加食谱失败，已存在同名食谱：%s", recipe.name)
            raise ServiceError(ServiceError.CONFLICT, "已存在同名食谱")
        self.get_logger().info("添加食谱 #%d %s（%s，%s）", row["id"], row["name"], row["type"], reason)
        return {**row, "type_reason": reason}

    def update(self, recipe_id: int, recipe: RecipeIn) -> dict:
        """修改整道食谱（菜名、食材、调料、用量、步骤、用时、荤素、来源链接）。"""
        values, reason = self._values(recipe)
        try:
            with self.db.session() as s:
                old = s.recipes.get(recipe_id)
                if old is None:
                    raise ServiceError(ServiceError.NOT_FOUND, "食谱不存在")
                s.recipes.update(recipe_id, values)
                row = s.recipes.get(recipe_id)
        except sqlite3.IntegrityError:
            self.get_logger().warning("修改食谱 #%d 失败，已存在同名食谱：%s", recipe_id, recipe.name)
            raise ServiceError(ServiceError.CONFLICT, "已存在同名食谱")
        renamed = f"（原名 {old['name']}）" if old["name"] != row["name"] else ""
        self.get_logger().info("修改食谱 #%d %s%s（%s，%s）", recipe_id, row["name"], renamed, row["type"], reason)
        return {**row, "type_reason": reason}

    def set_type(self, recipe_id: int, rtype: str) -> dict:
        with self.db.session() as s:
            if not s.recipes.set_type(recipe_id, rtype):
                raise ServiceError(ServiceError.NOT_FOUND, "食谱不存在")
            row = s.recipes.get(recipe_id)
        self.get_logger().info("食谱 #%d %s 改为%s菜", recipe_id, row["name"], rtype)
        return row

    def delete(self, recipe_id: int) -> None:
        with self.db.session() as s:
            row = s.recipes.get(recipe_id)
            if row is None:
                raise ServiceError(ServiceError.NOT_FOUND, "食谱不存在")
            s.recipes.delete(recipe_id)
        self.get_logger().info("删除食谱 #%d %s", recipe_id, row["name"])

    def import_draft(self, url: str) -> dict:
        """从网页链接识别食谱，返回草稿（不保存）。每个食材带 role：main 主料 / seasoning 调料 / skip 建议删除。"""
        try:
            draft = self.importer.import_recipe(url)
        except RecipeImportError as e:
            self.get_logger().warning("导入食谱失败 %s：%s", url, e)
            raise ServiceError(ServiceError.INVALID, str(e))
        mains = [i["name"] for i in draft["ingredients"] if i["role"] == "main"]
        draft["type"], draft["type_reason"] = self.classifier.explain(mains)
        with self.db.session() as s:
            draft["exists"] = s.recipes.name_exists(draft["name"])
        return draft

    def _values(self, recipe: RecipeIn) -> tuple[dict, str]:
        """整理提交的食谱：去空白、去重、过滤无效用量、确定荤素。返回 (各列的值, 荤素判断理由)。"""
        def clean(xs):
            out = []
            for x in xs:
                if (x := x.strip()) and x not in out:
                    out.append(x)
            return out

        ingredients = clean(recipe.ingredients)
        if not ingredients:
            raise ServiceError(ServiceError.INVALID, "至少需要一个主料")
        seasonings = [x for x in clean(recipe.seasonings) if x not in ingredients]
        # 只保留仍在食材/调料里的用量（编辑时删掉的食材，用量也一并丢弃）
        amounts = {k.strip(): v.strip() for k, v in recipe.amounts.items()
                   if k.strip() in ingredients + seasonings and v.strip()}
        if recipe.type:
            rtype, reason = recipe.type, "手动选择"
        else:
            rtype, reason = self.classifier.explain(ingredients)
            reason = "自动判断：" + reason
        values = {
            "name": recipe.name.strip(), "ingredients": ingredients, "seasonings": seasonings,
            "steps": clean(recipe.steps), "minutes": recipe.minutes, "type": rtype,
            "amounts": amounts, "source_url": recipe.source_url.strip(),
        }
        return values, reason
