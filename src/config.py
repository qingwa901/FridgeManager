"""读取 config/config.json。

配置中的相对路径一律相对于项目根目录解析。
可通过环境变量 FRIDGEMANAGER_CONFIG 指定其他配置文件。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class Settings:
    """全部配置项。用模块底部的 settings 实例，不要自己再创建。"""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    SRC_DIR = PROJECT_ROOT / "src"
    VERSION_FILE = PROJECT_ROOT / "VERSION"
    CONFIG_DIR = PROJECT_ROOT / "config"
    SEED_RECIPES_FILE = CONFIG_DIR / "recipes.json"   # 内置食谱，启动时导入数据库

    def __init__(self, config_path: Path):
        self.config_path = config_path
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        # 版本号规则 1.{年后两位}.{月}.{当月第几个版本，从 0 开始}，例如 1.26.11.0
        self.version: str = (self.VERSION_FILE.read_text(encoding="utf-8").strip()
                             if self.VERSION_FILE.exists() else "0.0.0.0")

        self.host: str = cfg["server"]["host"]
        self.port: int = cfg["server"]["port"]
        self.db_path: Path = self._resolve(cfg["database"]["path"])

        log = cfg["log"]
        # 日志目录。文件名由公共库生成：fridgemanager_{启动时间}.log，每天午夜轮转。
        # 兼容旧配置 "path": "logs/fridgemanager.log"（取它所在的目录）
        self.log_dir: Path = self._resolve(log["dir"]) if "dir" in log else self._resolve(log["path"]).parent
        self.log_level: str = log.get("level", "INFO")
        self.log_retention_days: int = log.get("retention_days", 14)

        self.expiring_days: int = cfg["fridge"].get("expiring_days", 3)   # 剩余天数 <= 该值视为"即将过期"
        # 食材预设：[{name, category, shelf_days, quantity}]，用于添加食材时一键填写
        self.food_presets: list[dict] = cfg.get("food_presets", [])

        # 自动判断荤素用的关键字
        rtype = cfg.get("recipe_type", {})
        self.meat_words: list[str] = rtype.get("meat_words", ["肉", "鸡", "鸭", "鱼", "虾", "牛", "猪", "羊"])
        self.veg_exceptions: list[str] = rtype.get("veg_exceptions", ["鸡蛋", "鸭蛋"])

        # 从链接导入食谱：名称完全等于这些词的食材默认归为"调料" / 默认删除；允许导入的网站（域名完全一致，且必须 https）
        imp = cfg.get("recipe_import", {})
        self.import_seasoning_words: set[str] = set(imp.get("seasoning_words", ["盐", "糖", "油", "生抽", "老抽"]))
        self.import_skip_words: set[str] = set(imp.get("skip_words", ["水", "清水"]))
        self.import_allowed_hosts: set[str] = {h.lower() for h in imp.get("allowed_hosts", ["pullit.up.railway.app"])}

    @classmethod
    def load(cls) -> "Settings":
        default = cls.CONFIG_DIR / "config.json"
        return cls(Path(os.environ.get("FRIDGEMANAGER_CONFIG", default)))

    def _resolve(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else self.PROJECT_ROOT / path


settings = Settings.load()
