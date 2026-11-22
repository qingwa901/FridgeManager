from __future__ import annotations

from fastapi import APIRouter

from api.schemas import ImportIn, RecipeIn, RecipeTypeIn
from function.recipe_service import RecipeService


class RecipeApi:
    """食谱库。"""

    def __init__(self, recipes: RecipeService):
        self.recipes = recipes
        self.router = APIRouter(prefix="/api/recipes")
        r = self.router
        r.add_api_route("", self.list_recipes, methods=["GET"])
        r.add_api_route("", self.add_recipe, methods=["POST"], status_code=201)
        r.add_api_route("/import", self.import_recipe, methods=["POST"])
        r.add_api_route("/{recipe_id}", self.update_recipe, methods=["PUT"])
        r.add_api_route("/{recipe_id}", self.set_recipe_type, methods=["PATCH"])
        r.add_api_route("/{recipe_id}", self.delete_recipe, methods=["DELETE"], status_code=204)

    def list_recipes(self):
        return self.recipes.list()

    def add_recipe(self, recipe: RecipeIn):
        return self.recipes.add(recipe)

    def update_recipe(self, recipe_id: int, recipe: RecipeIn):
        """修改整道食谱（字段同添加；type 为 null 时按主料自动判断）。"""
        return self.recipes.update(recipe_id, recipe)

    def set_recipe_type(self, recipe_id: int, body: RecipeTypeIn):
        """修改食谱的荤/素分类。"""
        return self.recipes.set_type(recipe_id, body.type)

    def delete_recipe(self, recipe_id: int):
        self.recipes.delete(recipe_id)

    def import_recipe(self, body: ImportIn):
        """从网页链接识别食谱，返回草稿（不保存）。每个食材带 role：main 主料 / seasoning 调料 / skip 建议删除。"""
        return self.recipes.import_draft(body.url)
