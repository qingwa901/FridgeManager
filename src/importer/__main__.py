"""诊断导入问题（在 src 目录下）：python -m importer [链接]"""

import sys

from config import settings
from importer.import_diagnostics import ImportDiagnostics
from importer.recipe_importer import RecipeImporter
from main import Server

DEFAULT_URL = "https://pullit.up.railway.app/recipes/C15891F3-18EB-445C-A68C-F2F1588EC745"

if __name__ == "__main__":
    Server.setup_logging(settings)
    ImportDiagnostics(RecipeImporter(settings)).run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL)
