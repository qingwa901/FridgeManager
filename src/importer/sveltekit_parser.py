from __future__ import annotations

import json
from urllib.parse import urlparse, urlunparse

from importer.recipe_import_error import RecipeImportError
from importer.safe_fetcher import SafeFetcher
from importer.text_parser import TextParser


class SvelteKitParser:
    """来源 2：SvelteKit 页面的 __data.json（例如 pullit.up.railway.app 的菜谱页）。"""

    def __init__(self, fetcher: SafeFetcher):
        self.fetcher = fetcher

    def parse(self, url: str) -> dict | None:
        p = urlparse(url)
        data_url = urlunparse(p._replace(path=p.path.rstrip("/") + "/__data.json", query="", fragment=""))
        try:
            _, text = self.fetcher.fetch(data_url)
            payload = json.loads(text)
        except (RecipeImportError, json.JSONDecodeError):
            return None
        for node in payload.get("nodes") or []:
            if not isinstance(node, dict) or node.get("type") != "data":
                continue
            arr = node.get("data")
            if not isinstance(arr, list) or not arr:
                continue
            r = self._find_with_ingredients(self._unflatten(arr, 0))
            if r:
                return self._to_draft(r)
        return None

    @staticmethod
    def _to_draft(r: dict) -> dict:
        ings = []
        for x in r["ingredients"]:
            if isinstance(x, dict) and x.get("name"):
                ings.append({"name": str(x["name"]).strip(), "amount": str(x.get("amount") or "").strip(),
                             "section": str(x.get("section") or "").strip()})
            elif isinstance(x, str):
                name, amount = TextParser.split_amount(x)
                ings.append({"name": name, "amount": amount, "section": ""})
        steps_raw = r.get("steps") or r.get("instructions") or []
        steps_raw = sorted((s for s in steps_raw if isinstance(s, (dict, str))),
                           key=lambda s: s.get("order", 0) if isinstance(s, dict) else 0)
        steps = [(s.get("instruction") or s.get("text") or "") if isinstance(s, dict) else s for s in steps_raw]
        return {
            "name": str(r.get("title") or r.get("name") or "").strip(),
            "minutes": TextParser.parse_minutes(r.get("cookTime") or r.get("totalTime")),
            "ingredients": ings,
            "steps": [s.strip() for s in steps if s and s.strip()],
        }

    def _unflatten(self, arr: list, i: int, depth: int = 0):
        """解码 SvelteKit (devalue) 的扁平化数据：对象/数组里的值是指向 arr 的下标。"""
        if not isinstance(i, int) or i < 0 or i >= len(arr) or depth > 50:
            return None
        v = arr[i]
        if isinstance(v, dict):
            return {k: self._unflatten(arr, j, depth + 1) for k, j in v.items()}
        if isinstance(v, list):
            if v and isinstance(v[0], str):  # 特殊类型，如 ["Date", "2026-..."]
                return v[1] if len(v) > 1 else None
            return [self._unflatten(arr, j, depth + 1) for j in v]
        return v

    def _find_with_ingredients(self, obj, depth: int = 0):
        if depth > 8:
            return None
        if isinstance(obj, dict):
            if isinstance(obj.get("ingredients"), list):
                return obj
            children = obj.values()
        elif isinstance(obj, list):
            children = obj
        else:
            return None
        for v in children:
            if (r := self._find_with_ingredients(v, depth + 1)) is not None:
                return r
        return None
