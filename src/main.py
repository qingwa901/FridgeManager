"""冰箱管家：记录冰箱食材与保质期，并根据食谱库推荐菜谱。

启动：  .venv\\Scripts\\python.exe src\\run.py
访问：  http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import asynccontextmanager, closing
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

import config
import importer

log = config.setup_logging()

BASE_DIR = config.SRC_DIR
DB_PATH = config.DB_PATH
SEED_RECIPES = BASE_DIR / "data" / "recipes.json"
EXPIRING_DAYS = config.EXPIRING_DAYS  # 剩余天数 <= 该值视为"即将过期"


# ---------------------------------------------------------------- 数据库

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_conn()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS foods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                quantity    TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT '其他',
                added_date  TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                note        TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                ingredients TEXT NOT NULL,          -- JSON 数组：主要食材
                seasonings  TEXT NOT NULL DEFAULT '[]', -- JSON 数组：调料（默认家中常备）
                steps       TEXT NOT NULL DEFAULT '[]', -- JSON 数组：步骤
                minutes     INTEGER NOT NULL DEFAULT 20,
                type        TEXT NOT NULL DEFAULT ''   -- '荤' 或 '素'
            );
            -- 记录导入过的种子食谱名：新增的种子会自动导入，用户删掉的不会再被加回来
            CREATE TABLE IF NOT EXISTS seed_imported (name TEXT PRIMARY KEY);
            """
        )
        # 旧数据库升级：补 type 列
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipes)")}
        for col, ddl in (("type", "TEXT NOT NULL DEFAULT ''"),          # '荤' / '素'
                         ("amounts", "TEXT NOT NULL DEFAULT '{}'"),     # JSON：{食材/调料名: 用量}
                         ("source_url", "TEXT NOT NULL DEFAULT ''")):   # 导入来源链接
            if col not in cols:
                conn.execute(f"ALTER TABLE recipes ADD COLUMN {col} {ddl}")
                log.info("数据库升级：recipes 表新增 %s 列", col)

        seeds = json.loads(SEED_RECIPES.read_text(encoding="utf-8")) if SEED_RECIPES.exists() else []
        seed_type = {r["name"]: r.get("type") or guess_type(r["ingredients"]) for r in seeds}
        imported = {r["name"] for r in conn.execute("SELECT name FROM seed_imported")}
        added = 0
        for r in seeds:
            if r["name"] in imported:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO recipes (name, ingredients, seasonings, steps, minutes, type) VALUES (?,?,?,?,?,?)",
                (
                    r["name"],
                    json.dumps(r["ingredients"], ensure_ascii=False),
                    json.dumps(r.get("seasonings", []), ensure_ascii=False),
                    json.dumps(r.get("steps", []), ensure_ascii=False),
                    r.get("minutes", 20),
                    seed_type[r["name"]],
                ),
            )
            added += cur.rowcount
            conn.execute("INSERT OR IGNORE INTO seed_imported (name) VALUES (?)", (r["name"],))
        if added:
            log.info("从 %s 导入 %d 个新食谱", SEED_RECIPES.name, added)

        # 没有荤素标记的食谱：种子里有就用种子的，否则按食材推断
        for row in conn.execute("SELECT id, name, ingredients FROM recipes WHERE type NOT IN ('荤','素')").fetchall():
            t = seed_type.get(row["name"]) or guess_type(json.loads(row["ingredients"]))
            conn.execute("UPDATE recipes SET type=? WHERE id=?", (t, row["id"]))


def explain_type(ingredients: list[str]) -> tuple[str, str]:
    """按主要食材判断荤素，返回 (类型, 理由)。关键字在 config.json 的 recipe_type 中配置。

    对每个食材：
      1. 名字包含 veg_exceptions 中的词（鸡蛋、牛奶、鸡毛菜…）→ 跳过，不算荤；
      2. 否则名字包含 meat_words 中的词 → 整道菜判为荤；
    所有食材都没命中 → 素。
    """
    for ing in ingredients:
        if any(w in ing for w in config.VEG_EXCEPTIONS):
            continue
        hit = next((w for w in config.MEAT_WORDS if w in ing), None)
        if hit:
            return "荤", f"「{ing}」含「{hit}」"
    return "素", "主要食材中没有肉、禽、水产"


def guess_type(ingredients: list[str]) -> str:
    return explain_type(ingredients)[0]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info("服务启动：数据库=%s 日志=%s", DB_PATH, config.LOG_PATH)
    yield
    log.info("服务停止")


app = FastAPI(title="冰箱管家", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个 API 请求的方法、路径、状态码和耗时；未捕获异常写入完整堆栈。"""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("请求异常 %s %s", request.method, request.url.path)
        raise
    if not request.url.path.startswith("/api"):
        # 页面和静态文件每次都向服务器确认是否有更新，避免改版后浏览器还用旧的 JS/CSS
        response.headers["Cache-Control"] = "no-cache"
    else:
        log.info("%s %s -> %d (%.1fms)", request.method, request.url.path,
                 response.status_code, (time.perf_counter() - start) * 1000)
    return response


# ---------------------------------------------------------------- 模型

SHORTAGE = "缺货"   # 数量为"缺货"的条目 = 补货清单，不算在冰箱里


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
        if self.quantity == SHORTAGE:
            self.expiry_date = None        # 缺货不需要保质期
        if self.expiry_date and self.expiry_date < self.added_date:
            raise ValueError("保质期不能早于存入日期")
        return self

    def db_values(self) -> tuple:
        """数据库里 expiry_date 列不允许 NULL，不设保质期时存空字符串。"""
        return (self.name.strip(), self.quantity, self.category, self.added_date.isoformat(),
                self.expiry_date.isoformat() if self.expiry_date else "", self.note)


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


def food_row(row: sqlite3.Row) -> dict:
    """status：expired 已过期 / expiring 即将过期 / fresh 新鲜 / none 未设保质期。"""
    d = dict(row)
    d["days_stored"] = (date.today() - date.fromisoformat(d["added_date"])).days
    if not d["expiry_date"]:
        d["expiry_date"] = None
        d["days_left"] = None
        d["status"] = "none"
        return d
    days_left = (date.fromisoformat(d["expiry_date"]) - date.today()).days
    d["days_left"] = days_left
    d["status"] = "expired" if days_left < 0 else "expiring" if days_left <= EXPIRING_DAYS else "fresh"
    return d


def recipe_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("ingredients", "seasonings", "steps", "amounts"):
        d[k] = json.loads(d[k])
    return d


# ---------------------------------------------------------------- 食材 API

@app.get("/api/presets")
def list_presets():
    """食材预设（在 config/config.json 的 food_presets 中配置）。"""
    return config.FOOD_PRESETS


@app.get("/api/foods")
def list_foods():
    """冰箱里的食材（不含"缺货"条目）。
    排序：已过期、即将过期的排在最前（按到期日）；其余按存入日期从早到晚（先放进去的先吃）。"""
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM foods WHERE quantity != ?", (SHORTAGE,)).fetchall()
    foods = [food_row(r) for r in rows]
    urgent = lambda f: f["status"] in ("expired", "expiring")
    foods.sort(key=lambda f: (0, f["expiry_date"], f["name"]) if urgent(f) else (1, f["added_date"], f["name"]))
    return foods


@app.get("/api/shopping")
def list_shopping():
    """补货清单：数量为"缺货"的条目，按加入时间排序。"""
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM foods WHERE quantity = ? ORDER BY added_date, id",
                            (SHORTAGE,)).fetchall()
    return [food_row(r) for r in rows]


def _clear_shortage(conn: sqlite3.Connection, name: str, keep_id: int | None = None) -> int:
    """补货了：删除补货清单里同名的"缺货"条目，返回删除条数。"""
    cur = conn.execute("DELETE FROM foods WHERE name=? AND quantity=? AND id IS NOT ?", (name, SHORTAGE, keep_id))
    if cur.rowcount:
        log.info("补货：已从补货清单移除「%s」", name)
    return cur.rowcount


@app.post("/api/foods", status_code=201)
def add_food(food: FoodIn):
    """添加食材。数量为"缺货" = 加入补货清单（同名已在清单里则不重复添加）；
    其他数量 = 放进冰箱，并自动把补货清单里同名的条目删掉。"""
    with closing(get_conn()) as conn, conn:
        if food.quantity == SHORTAGE:
            dup = conn.execute("SELECT * FROM foods WHERE name=? AND quantity=?", (food.name, SHORTAGE)).fetchone()
            if dup:
                return {**food_row(dup), "duplicate": True}
        cur = conn.execute(
            "INSERT INTO foods (name, quantity, category, added_date, expiry_date, note) VALUES (?,?,?,?,?,?)",
            food.db_values(),
        )
        restocked = 0 if food.quantity == SHORTAGE else _clear_shortage(conn, food.name)
        row = conn.execute("SELECT * FROM foods WHERE id=?", (cur.lastrowid,)).fetchone()
    if food.quantity == SHORTAGE:
        log.info("加入补货清单 #%d %s", row["id"], row["name"])
    else:
        log.info("添加食材 #%d %s 数量=%s 存入=%s 保质期至=%s", row["id"], row["name"], row["quantity"],
                 row["added_date"], row["expiry_date"] or "未设")
    return {**food_row(row), "restocked": restocked}


@app.put("/api/foods/{food_id}")
def update_food(food_id: int, food: FoodIn):
    with closing(get_conn()) as conn, conn:
        if food.quantity == SHORTAGE:
            # 吃完了：补货清单里已有同名条目就合并（删掉这一条），不重复
            dup = conn.execute("SELECT * FROM foods WHERE name=? AND quantity=? AND id!=?",
                               (food.name, SHORTAGE, food_id)).fetchone()
            if dup:
                if conn.execute("DELETE FROM foods WHERE id=?", (food_id,)).rowcount == 0:
                    raise HTTPException(404, "食材不存在")
                log.info("食材 #%d %s 吃完，补货清单里已有，合并", food_id, food.name)
                return {**food_row(dup), "duplicate": True}
        cur = conn.execute(
            "UPDATE foods SET name=?, quantity=?, category=?, added_date=?, expiry_date=?, note=? WHERE id=?",
            (*food.db_values(), food_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "食材不存在")
        restocked = 0 if food.quantity == SHORTAGE else _clear_shortage(conn, food.name, keep_id=food_id)
        row = conn.execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone()
    log.info("更新食材 #%d %s 数量=%s 保质期至=%s", food_id, row["name"], row["quantity"], row["expiry_date"] or "未设")
    return {**food_row(row), "restocked": restocked}


@app.delete("/api/foods/{food_id}", status_code=204)
def delete_food(food_id: int):
    with closing(get_conn()) as conn, conn:
        row = conn.execute("SELECT name FROM foods WHERE id=?", (food_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "食材不存在")
        conn.execute("DELETE FROM foods WHERE id=?", (food_id,))
    log.info("删除食材 #%d %s", food_id, row["name"])


# ---------------------------------------------------------------- 食谱 API

@app.get("/api/recipes")
def list_recipes():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY name").fetchall()
    return [recipe_row(r) for r in rows]


def _recipe_values(recipe: RecipeIn) -> tuple[dict, str]:
    """整理提交的食谱：去空白、去重、过滤无效用量、确定荤素。返回 (各列的值, 荤素判断理由)。"""
    def clean(xs):
        out = []
        for x in xs:
            if (x := x.strip()) and x not in out:
                out.append(x)
        return out

    ingredients = clean(recipe.ingredients)
    if not ingredients:
        raise HTTPException(422, "至少需要一个主料")
    seasonings = [s for s in clean(recipe.seasonings) if s not in ingredients]
    # 只保留仍在食材/调料里的用量（编辑时删掉的食材，用量也一并丢弃）
    amounts = {k.strip(): v.strip() for k, v in recipe.amounts.items()
               if k.strip() in ingredients + seasonings and v.strip()}
    if recipe.type:
        rtype, reason = recipe.type, "手动选择"
    else:
        rtype, reason = explain_type(ingredients)
        reason = "自动判断：" + reason
    values = {
        "name": recipe.name.strip(),
        "ingredients": json.dumps(ingredients, ensure_ascii=False),
        "seasonings": json.dumps(seasonings, ensure_ascii=False),
        "steps": json.dumps(clean(recipe.steps), ensure_ascii=False),
        "minutes": recipe.minutes,
        "type": rtype,
        "amounts": json.dumps(amounts, ensure_ascii=False),
        "source_url": recipe.source_url.strip(),
    }
    return values, reason


@app.post("/api/recipes", status_code=201)
def add_recipe(recipe: RecipeIn):
    values, reason = _recipe_values(recipe)
    cols = ", ".join(values)
    try:
        with closing(get_conn()) as conn, conn:
            cur = conn.execute(f"INSERT INTO recipes ({cols}) VALUES ({', '.join('?' * len(values))})",
                               tuple(values.values()))
            row = conn.execute("SELECT * FROM recipes WHERE id=?", (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        log.warning("添加食谱失败，已存在同名食谱：%s", recipe.name)
        raise HTTPException(409, "已存在同名食谱")
    log.info("添加食谱 #%d %s（%s，%s）", row["id"], row["name"], row["type"], reason)
    return {**recipe_row(row), "type_reason": reason}


@app.put("/api/recipes/{recipe_id}")
def update_recipe(recipe_id: int, recipe: RecipeIn):
    """修改整道食谱（菜名、食材、调料、用量、步骤、用时、荤素、来源链接）。"""
    values, reason = _recipe_values(recipe)
    sets = ", ".join(f"{k}=?" for k in values)
    try:
        with closing(get_conn()) as conn, conn:
            old = conn.execute("SELECT name FROM recipes WHERE id=?", (recipe_id,)).fetchone()
            if old is None:
                raise HTTPException(404, "食谱不存在")
            conn.execute(f"UPDATE recipes SET {sets} WHERE id=?", (*values.values(), recipe_id))
            row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    except sqlite3.IntegrityError:
        log.warning("修改食谱 #%d 失败，已存在同名食谱：%s", recipe_id, recipe.name)
        raise HTTPException(409, "已存在同名食谱")
    renamed = f"（原名 {old['name']}）" if old["name"] != row["name"] else ""
    log.info("修改食谱 #%d %s%s（%s，%s）", recipe_id, row["name"], renamed, row["type"], reason)
    return {**recipe_row(row), "type_reason": reason}


@app.post("/api/recipes/import")
def import_recipe(body: ImportIn):
    """从网页链接识别食谱，返回草稿（不保存）。每个食材带 role：main 主料 / seasoning 调料 / skip 建议删除。"""
    try:
        draft = importer.import_recipe(body.url)
    except importer.ImportError_ as e:
        log.warning("导入食谱失败 %s：%s", body.url, e)
        raise HTTPException(422, str(e))
    mains = [i["name"] for i in draft["ingredients"] if i["role"] == "main"]
    draft["type"], draft["type_reason"] = explain_type(mains)
    with closing(get_conn()) as conn:
        draft["exists"] = conn.execute("SELECT 1 FROM recipes WHERE name=?", (draft["name"],)).fetchone() is not None
    return draft


@app.patch("/api/recipes/{recipe_id}")
def set_recipe_type(recipe_id: int, body: RecipeTypeIn):
    """修改食谱的荤/素分类。"""
    with closing(get_conn()) as conn, conn:
        if conn.execute("UPDATE recipes SET type=? WHERE id=?", (body.type, recipe_id)).rowcount == 0:
            raise HTTPException(404, "食谱不存在")
        row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    log.info("食谱 #%d %s 改为%s菜", recipe_id, row["name"], body.type)
    return recipe_row(row)


@app.delete("/api/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int):
    with closing(get_conn()) as conn, conn:
        row = conn.execute("SELECT name FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "食谱不存在")
        conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
    log.info("删除食谱 #%d %s", recipe_id, row["name"])


# ---------------------------------------------------------------- 推荐

def matches(ingredient: str, food_name: str) -> bool:
    """宽松匹配：'鸡蛋' 能匹配 '土鸡蛋'，'番茄' 能匹配 '番茄'。"""
    return ingredient in food_name or food_name in ingredient


@app.get("/api/recommend")
def recommend(max_missing: int = 2, type: Literal["荤", "素"] | None = None):
    """按"缺少的食材最少 → 用到的临期食材最多 → 匹配率最高"排序。过期食材不参与匹配。
    max_missing 为负数表示不限（包括冰箱里一种食材都没有的食谱）。type 可选，只推荐荤菜或素菜。"""
    foods = [f for f in list_foods() if f["status"] != "expired"]
    results = []
    for r in list_recipes():
        if type and r["type"] != type:
            continue
        have, missing, expiring = [], [], []
        for ing in r["ingredients"]:
            hit = next((f for f in foods if matches(ing, f["name"])), None)
            if hit:
                have.append(ing)
                if hit["status"] == "expiring":
                    expiring.append(hit["name"])
            else:
                missing.append(ing)
        unlimited = max_missing < 0
        # 有数量限制时，至少要有一种食材在冰箱里（否则"缺 2 种"会混进一堆完全不相关的菜）；不限则全部显示
        if not unlimited and (not have or len(missing) > max_missing):
            continue
        results.append({
            **r,
            "have": have,
            "missing": missing,
            "uses_expiring": expiring,
            "match_rate": round(len(have) / len(r["ingredients"]), 2),
        })
    results.sort(key=lambda x: (len(x["missing"]), -len(x["uses_expiring"]), -x["match_rate"]))
    log.info("推荐食谱：可用食材 %d 种，最多缺 %s 种，类型=%s，命中 %d 个食谱",
             len(foods), "不限" if max_missing < 0 else max_missing, type or "全部", len(results))
    return results


@app.get("/api/daily")
def daily(max_missing: int = 2):
    """今日一荤一素：分别返回排好序的荤菜、素菜候选，第一个就是首选，前端可"换一换"。"""
    ranked = recommend(max_missing)
    return {
        "荤": [r for r in ranked if r["type"] == "荤"],
        "素": [r for r in ranked if r["type"] == "素"],
    }


# ---------------------------------------------------------------- 前端

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
