from __future__ import annotations

import json
import re

from importer.text_parser import TextParser


class JsonLdParser:
    """来源 1：页面里的 schema.org Recipe（<script type="application/ld+json">）。"""

    SCRIPT_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)

    def parse(self, html: str) -> dict | None:
        for m in self.SCRIPT_RE.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
            r = self._find_recipe(data)
            if not r:
                continue
            ings = []
            for s in r.get("recipeIngredient") or r.get("ingredients") or []:
                name, amount = TextParser.split_amount(str(s))
                ings.append({"name": name, "amount": amount, "section": ""})
            return {
                "name": str(r.get("name", "")).strip(),
                "minutes": TextParser.parse_minutes(r.get("totalTime") or r.get("cookTime")),
                "ingredients": ings,
                "steps": self._steps(r.get("recipeInstructions")),
            }
        return None

    def _find_recipe(self, obj):
        if isinstance(obj, list):
            for x in obj:
                if (r := self._find_recipe(x)) is not None:
                    return r
        elif isinstance(obj, dict):
            t = obj.get("@type")
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return obj
            if "@graph" in obj:
                return self._find_recipe(obj["@graph"])
        return None

    def _steps(self, ins) -> list[str]:
        if isinstance(ins, str):
            return [s.strip() for s in re.split(r"\n+", ins) if s.strip()]
        out = []
        for x in ins or []:
            if isinstance(x, str):
                out.append(x.strip())
            elif isinstance(x, dict):
                if x.get("@type") == "HowToSection":
                    out += self._steps(x.get("itemListElement"))
                elif x.get("text"):
                    out.append(str(x["text"]).strip())
        return [s for s in out if s]
