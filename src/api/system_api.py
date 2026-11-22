from __future__ import annotations

from fastapi import APIRouter

from config import Settings


class SystemApi:
    """版本号、食材预设。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.router = APIRouter(prefix="/api")
        self.router.add_api_route("/version", self.version, methods=["GET"])
        self.router.add_api_route("/presets", self.presets, methods=["GET"])

    def version(self):
        """当前版本号（来自根目录 VERSION 文件）。"""
        return {"name": "FridgeManager", "version": self.settings.version}

    def presets(self):
        """食材预设（在 config/config.json 的 food_presets 中配置）。"""
        return self.settings.food_presets
