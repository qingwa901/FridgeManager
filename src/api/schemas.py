"""接口的请求体（pydantic 模型）。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from data.food_table import FoodTable


class FoodIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    quantity: str = Field(default="", max_length=30)
    category: str = Field(default="其他", max_length=20)
    added_date: date = Field(default_factory=date.today)
    expiry_date: date | None = None   # 不填 = 不设保质期
    note: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _check_dates(self):
        self.name = self.name.strip()
        if self.quantity == FoodTable.SHORTAGE:
            self.expiry_date = None        # 缺货不需要保质期
        if self.expiry_date and self.expiry_date < self.added_date:
            raise ValueError("保质期不能早于存入日期")
        return self

    @property
    def is_shortage(self) -> bool:
        return self.quantity == FoodTable.SHORTAGE

    def db_values(self) -> dict:
        """数据库里 expiry_date 列不允许 NULL，不设保质期时存空字符串。"""
        return {"name": self.name, "quantity": self.quantity, "category": self.category,
                "added_date": self.added_date.isoformat(),
                "expiry_date": self.expiry_date.isoformat() if self.expiry_date else "", "note": self.note}


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    ingredients: list[str] = Field(min_length=1)
    seasonings: list[str] = []
    steps: list[str] = []
    minutes: int = Field(default=20, ge=1, le=600)
    type: Literal["荤", "素"] | None = None  # 不填则按食材自动判断
    amounts: dict[str, str] = {}             # 用量，如 {"老母鸡": "1只"}
    source_url: str = Field(default="", max_length=2000, pattern=r"^(https?://\S+)?$")


class ImportIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class RecipeTypeIn(BaseModel):
    type: Literal["荤", "素"]


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    members: list[str] = Field(min_length=1, max_length=200)
