"""从网页链接导入食谱：抓取页面，识别菜名、食材（含用量/分组）、步骤、用时。

支持两种来源（按顺序尝试）：
  1. schema.org Recipe（页面中的 <script type="application/ld+json">），大多数菜谱网站都有；
  2. SvelteKit 页面的 __data.json（例如 pullit.up.railway.app 的菜谱页）。

只返回草稿，不写数据库；由前端编辑确认后再调用 POST /api/recipes 保存。
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse

import config

log = logging.getLogger("fridgeweb.importer")

MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = 10
UA = "Mozilla/5.0 (compatible; fridgeweb-recipe-importer)"


class ImportError_(Exception):
    """导入失败，消息直接展示给用户。"""


# ---------------------------------------------------------------- 安全抓取

def _check_public_host(url: str) -> None:
    """只允许 https + config 中 allowed_hosts 里的网站，且解析出的地址必须是公网（防止借本服务访问局域网/本机）。"""
    p = urlparse(url)
    allowed = "、".join(sorted(config.IMPORT_ALLOWED_HOSTS))
    if p.scheme != "https" or not p.hostname:
        raise ImportError_(f"只支持 https 链接（允许的网站：{allowed}）")
    if p.username or p.password or p.hostname.lower() not in config.IMPORT_ALLOWED_HOSTS:
        raise ImportError_(f"只能从这些网站导入：{allowed}")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443)
    except socket.gaierror:
        raise ImportError_(f"无法解析域名：{p.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ImportError_("不允许访问内网或本机地址")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context() -> ssl.SSLContext:
    """优先用 truststore：交给操作系统（Windows 证书库）校验证书，和浏览器结果一致。
    这样在 Norton / 公司代理等会替换 HTTPS 证书的环境下也能正常访问。没装则退回 Python 默认校验。"""
    try:
        import truststore
        log.info("HTTPS 证书校验：使用操作系统证书库（truststore %s）", truststore.__version__)
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        log.warning("未安装 truststore，使用 Python 默认证书校验（可能与浏览器结果不一致）")
        return ssl.create_default_context()


SSL_CONTEXT: ssl.SSLContext | None = None
_opener = None


def _get_opener():
    """首次使用时创建（此时日志已初始化，能记录用的是哪种证书校验）。"""
    global SSL_CONTEXT, _opener
    if _opener is None:
        SSL_CONTEXT = _ssl_context()
        _opener = urllib.request.build_opener(_SafeRedirect, urllib.request.HTTPSHandler(context=SSL_CONTEXT))
    return _opener


def fetch(url: str) -> tuple[str, str]:
    """返回 (最终 URL, 文本内容)。"""
    _check_public_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    try:
        with _get_opener().open(req, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_BYTES + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
            final_url = resp.geturl()
    except urllib.error.HTTPError as e:
        raise ImportError_(f"页面返回错误 {e.code}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            log.warning("HTTPS 证书校验失败 %s：%s（SSL 实现：%s，SSL_CERT_FILE=%s，SSL_CERT_DIR=%s，REQUESTS_CA_BUNDLE=%s）",
                        url, e.reason, type(SSL_CONTEXT).__module__, os.environ.get("SSL_CERT_FILE"),
                        os.environ.get("SSL_CERT_DIR"), os.environ.get("REQUESTS_CA_BUNDLE"))
            raise ImportError_(f"网站 HTTPS 证书校验失败（{e.reason.verify_message}）。"
                               "如果浏览器能正常打开，请确认服务器用的 Python 环境已安装 truststore（pip install -e .）")
        raise ImportError_(f"无法打开页面：{e.reason}")
    except TimeoutError as e:
        raise ImportError_(f"无法打开页面：{getattr(e, 'reason', e)}")
    if len(data) > MAX_BYTES:
        raise ImportError_("页面太大")
    return final_url, data.decode(charset, errors="replace")


# ---------------------------------------------------------------- 通用工具

def parse_minutes(text) -> int | None:
    """'70分钟' / '1小时30分钟' / 'PT1H10M' / 45 → 分钟数。"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text)
    m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?", s.strip(), re.I)  # ISO 8601
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    h = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h|hour)", s, re.I)
    mi = re.search(r"(\d+)\s*(?:分钟|分|min)", s, re.I)
    if h or mi:
        return round(float(h.group(1)) * 60 if h else 0) + (int(mi.group(1)) if mi else 0)
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


AMOUNT_RE = re.compile(r"^[\d.\/½¼¾一二三四五六七八九十半几]+\s*\S{0,3}$|^(适量|少许|若干|少量|一点|按口味)$")


def split_amount(text: str) -> tuple[str, str]:
    """'老母鸡 1只' / '1只 老母鸡' / '盐 适量' → (名称, 用量)。分不开时用量为空。"""
    parts = text.strip().split()
    if len(parts) >= 2:
        if AMOUNT_RE.match(parts[-1]):
            return " ".join(parts[:-1]), parts[-1]
        if AMOUNT_RE.match(parts[0]):
            return " ".join(parts[1:]), parts[0]
    return text.strip(), ""


def classify(name: str, section: str) -> str:
    """导入时给食材的默认归类：main（主料）/ seasoning（调料）/ skip（默认删除）。"""
    if name in config.IMPORT_SKIP_WORDS:
        return "skip"
    if any(w in section for w in ("调味", "调料", "佐料", "酱汁", "腌料")):
        return "seasoning"
    if name in config.IMPORT_SEASONING_WORDS:
        return "seasoning"
    return "main"


# ---------------------------------------------------------------- 来源 1：schema.org JSON-LD

def _find_ld_recipe(obj):
    if isinstance(obj, list):
        for x in obj:
            if (r := _find_ld_recipe(x)) is not None:
                return r
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
            return obj
        if "@graph" in obj:
            return _find_ld_recipe(obj["@graph"])
    return None


def _ld_steps(ins) -> list[str]:
    if isinstance(ins, str):
        return [s.strip() for s in re.split(r"\n+", ins) if s.strip()]
    out = []
    for x in ins or []:
        if isinstance(x, str):
            out.append(x.strip())
        elif isinstance(x, dict):
            if x.get("@type") == "HowToSection":
                out += _ld_steps(x.get("itemListElement"))
            elif x.get("text"):
                out.append(str(x["text"]).strip())
    return [s for s in out if s]


def from_json_ld(html: str) -> dict | None:
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        r = _find_ld_recipe(data)
        if not r:
            continue
        ings = []
        for s in r.get("recipeIngredient") or r.get("ingredients") or []:
            name, amount = split_amount(str(s))
            ings.append({"name": name, "amount": amount, "section": ""})
        return {
            "name": str(r.get("name", "")).strip(),
            "minutes": parse_minutes(r.get("totalTime") or r.get("cookTime")),
            "ingredients": ings,
            "steps": _ld_steps(r.get("recipeInstructions")),
        }
    return None


# ---------------------------------------------------------------- 来源 2：SvelteKit __data.json

def _unflatten(arr: list, i: int, depth: int = 0):
    """解码 SvelteKit (devalue) 的扁平化数据：对象/数组里的值是指向 arr 的下标。"""
    if not isinstance(i, int) or i < 0 or i >= len(arr) or depth > 50:
        return None
    v = arr[i]
    if isinstance(v, dict):
        return {k: _unflatten(arr, j, depth + 1) for k, j in v.items()}
    if isinstance(v, list):
        if v and isinstance(v[0], str):  # 特殊类型，如 ["Date", "2026-..."]
            return v[1] if len(v) > 1 else None
        return [_unflatten(arr, j, depth + 1) for j in v]
    return v


def _find_with_ingredients(obj, depth=0):
    if depth > 8:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("ingredients"), list):
            return obj
        for v in obj.values():
            if (r := _find_with_ingredients(v, depth + 1)) is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            if (r := _find_with_ingredients(v, depth + 1)) is not None:
                return r
    return None


def from_sveltekit(url: str) -> dict | None:
    p = urlparse(url)
    data_url = urlunparse(p._replace(path=p.path.rstrip("/") + "/__data.json", query="", fragment=""))
    try:
        _, text = fetch(data_url)
        payload = json.loads(text)
    except (ImportError_, json.JSONDecodeError):
        return None
    for node in payload.get("nodes") or []:
        if not isinstance(node, dict) or node.get("type") != "data":
            continue
        arr = node.get("data")
        if not isinstance(arr, list) or not arr:
            continue
        r = _find_with_ingredients(_unflatten(arr, 0))
        if not r:
            continue
        ings = []
        for x in r["ingredients"]:
            if isinstance(x, dict) and x.get("name"):
                ings.append({"name": str(x["name"]).strip(), "amount": str(x.get("amount") or "").strip(),
                             "section": str(x.get("section") or "").strip()})
            elif isinstance(x, str):
                name, amount = split_amount(x)
                ings.append({"name": name, "amount": amount, "section": ""})
        steps_raw = r.get("steps") or r.get("instructions") or []
        steps_raw = sorted((s for s in steps_raw if isinstance(s, (dict, str))),
                           key=lambda s: s.get("order", 0) if isinstance(s, dict) else 0)
        steps = [(s.get("instruction") or s.get("text") or "") if isinstance(s, dict) else s for s in steps_raw]
        return {
            "name": str(r.get("title") or r.get("name") or "").strip(),
            "minutes": parse_minutes(r.get("cookTime") or r.get("totalTime")),
            "ingredients": ings,
            "steps": [s.strip() for s in steps if s and s.strip()],
        }
    return None


# ---------------------------------------------------------------- 入口

def import_recipe(url: str) -> dict:
    url = url.strip()
    final_url, html = fetch(url)
    draft = from_json_ld(html) or from_sveltekit(final_url)
    if not draft or not draft["ingredients"]:
        raise ImportError_("没能从这个页面识别出食谱（页面中没有找到食材列表）")
    if not draft["name"]:
        m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        draft["name"] = re.split(r"\s*[·|\-–—_]\s*", m.group(1).strip())[0] if m else "未命名食谱"
    for ing in draft["ingredients"]:
        ing["role"] = classify(ing["name"], ing["section"])
    draft["minutes"] = draft["minutes"] or 20
    draft["source_url"] = url
    log.info("从 %s 识别食谱「%s」：%d 种食材、%d 个步骤", urlparse(url).hostname, draft["name"],
             len(draft["ingredients"]), len(draft["steps"]))
    return draft
