"""读取 config/config.json，并初始化日志。

配置中的相对路径一律相对于项目根目录解析。
可通过环境变量 FRIDGEMANAGER_CONFIG 指定其他配置文件。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
CONFIG_PATH = Path(os.environ.get("FRIDGEMANAGER_CONFIG", PROJECT_ROOT / "config" / "config.json"))
VERSION_FILE = PROJECT_ROOT / "VERSION"
# 版本号规则 1.{年后两位}.{月}.{当月第几个版本，从 0 开始}，例如 1.26.11.0
VERSION: str = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0.0.0"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PROJECT_ROOT / path


_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

HOST: str = _cfg["server"]["host"]
PORT: int = _cfg["server"]["port"]
DB_PATH: Path = _resolve(_cfg["database"]["path"])
LOG_PATH: Path = _resolve(_cfg["log"]["path"])
LOG_LEVEL: str = _cfg["log"].get("level", "INFO")
LOG_RETENTION_DAYS: int = _cfg["log"].get("retention_days", 14)
EXPIRING_DAYS: int = _cfg["fridge"].get("expiring_days", 3)
# 食材预设：[{name, category, shelf_days, quantity}]，用于添加食材时一键填写
FOOD_PRESETS: list[dict] = _cfg.get("food_presets", [])
# 自动判断荤素用的关键字
MEAT_WORDS: list[str] = _cfg.get("recipe_type", {}).get("meat_words", ["肉", "鸡", "鸭", "鱼", "虾", "牛", "猪", "羊"])
VEG_EXCEPTIONS: list[str] = _cfg.get("recipe_type", {}).get("veg_exceptions", ["鸡蛋", "鸭蛋"])
# 从链接导入食谱时：名称完全等于这些词的食材默认归为"调料" / 默认删除
IMPORT_SEASONING_WORDS: set[str] = set(_cfg.get("recipe_import", {}).get("seasoning_words", ["盐", "糖", "油", "生抽", "老抽"]))
IMPORT_SKIP_WORDS: set[str] = set(_cfg.get("recipe_import", {}).get("skip_words", ["水", "清水"]))
# 允许导入的网站（域名需完全一致，且必须 https）
IMPORT_ALLOWED_HOSTS: set[str] = {h.lower() for h in _cfg.get("recipe_import", {}).get("allowed_hosts", ["pullit.up.railway.app"])}


def cleanup_old_logs() -> list[Path]:
    """删除日志目录中修改时间早于 retention_days 的历史日志（fridgemanager.log.YYYY-MM-DD 等）。

    TimedRotatingFileHandler 只在午夜轮转时清理；如果程序那时没在运行，
    启动时这里会再兜底清理一次。
    """
    cutoff = time.time() - LOG_RETENTION_DAYS * 86400
    removed = []
    for f in LOG_PATH.parent.glob(LOG_PATH.name + ".*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed.append(f)
    return removed


def setup_logging() -> logging.Logger:
    """配置根日志：控制台 + 每天午夜轮转的日志文件，只保留最近 retention_days 天。可重复调用。"""
    root = logging.getLogger()
    if getattr(root, "_fridgemanager_configured", False):
        return logging.getLogger("fridgemanager")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    removed = cleanup_old_logs()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = TimedRotatingFileHandler(LOG_PATH, when="midnight", backupCount=LOG_RETENTION_DAYS,
                                            encoding="utf-8")
    file_handler.setFormatter(fmt)

    root.setLevel(LOG_LEVEL)
    root.addHandler(file_handler)
    # 作为 Windows 服务或用 pythonw 运行时没有控制台（sys.stderr 为 None），此时只写文件
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    # uvicorn 的访问日志与错误日志也写入同一文件
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    root._fridgemanager_configured = True
    log = logging.getLogger("fridgemanager")
    for f in removed:
        log.info("已清理过期日志：%s", f.name)
    return log
