from __future__ import annotations

import sqlite3

from data.food_table import FoodTable
from data.ingredient_group_table import IngredientGroupTable
from data.recipe_table import RecipeTable
from data.seed_imported_table import SeedImportedTable


class Session:
    """一个数据库连接上的所有表。由 Database.session() 创建，同一个 Session 里的操作在同一个事务中。"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.foods = FoodTable(conn)
        self.recipes = RecipeTable(conn)
        self.seeds = SeedImportedTable(conn)
        self.groups = IngredientGroupTable(conn)
