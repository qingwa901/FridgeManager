"""从网页链接导入食谱：抓取页面，识别菜名、食材（含用量/分组）、步骤、用时。

支持两种来源（按顺序尝试）：
  1. schema.org Recipe（页面中的 <script type="application/ld+json">），大多数菜谱网站都有；
  2. SvelteKit 页面的 __data.json（例如 pullit.up.railway.app 的菜谱页）。

只返回草稿，不写数据库；由前端编辑确认后再保存。
排查 HTTPS 问题：在 src 目录下运行 python -m importer <链接>
"""

from importer.recipe_import_error import RecipeImportError
from importer.recipe_importer import RecipeImporter

__all__ = ["RecipeImporter", "RecipeImportError"]
