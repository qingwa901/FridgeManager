from __future__ import annotations

import re
from urllib.parse import urlparse

from common_lib import Base

from config import Settings
from importer.json_ld_parser import JsonLdParser
from importer.recipe_import_error import RecipeImportError
from importer.safe_fetcher import SafeFetcher
from importer.sveltekit_parser import SvelteKitParser


class RecipeImporter(Base):
    """抓取链接 → 识别食谱 → 给每个食材默认归类。只返回草稿，不写数据库。"""

    SEASONING_SECTIONS = ("调味", "调料", "佐料", "酱汁", "腌料")

    def __init__(self, settings: Settings):
        self.seasoning_words = settings.import_seasoning_words
        self.skip_words = settings.import_skip_words
        self.fetcher = SafeFetcher(settings.import_allowed_hosts)
        self.json_ld = JsonLdParser()
        self.sveltekit = SvelteKitParser(self.fetcher)

    def classify(self, name: str, section: str) -> str:
        """食材的默认归类：main（主料）/ seasoning（调料）/ skip（默认删除）。"""
        if name in self.skip_words:
            return "skip"
        if any(w in section for w in self.SEASONING_SECTIONS) or name in self.seasoning_words:
            return "seasoning"
        return "main"

    def import_recipe(self, url: str) -> dict:
        url = url.strip()
        final_url, html = self.fetcher.fetch(url)
        draft = self.json_ld.parse(html) or self.sveltekit.parse(final_url)
        if not draft or not draft["ingredients"]:
            raise RecipeImportError("没能从这个页面识别出食谱（页面中没有找到食材列表）")
        if not draft["name"]:
            m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
            draft["name"] = re.split(r"\s*[·|\-–—_]\s*", m.group(1).strip())[0] if m else "未命名食谱"
        for ing in draft["ingredients"]:
            ing["role"] = self.classify(ing["name"], ing["section"])
        draft["minutes"] = draft["minutes"] or 20
        draft["source_url"] = url
        self.get_logger().info("从 %s 识别食谱「%s」：%d 种食材、%d 个步骤", urlparse(url).hostname, draft["name"],
                               len(draft["ingredients"]), len(draft["steps"]))
        return draft
