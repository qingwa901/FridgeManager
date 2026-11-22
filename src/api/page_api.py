from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


class PageApi:
    """网页首页。引用的 JS / CSS 地址带内容指纹（/static/app.js?v=<md5 前 10 位>），文件一改地址就变，
    浏览器必须重新下载。有些手机浏览器会无视 Cache-Control: no-cache，刷新时直接用缓存里的旧文件，只靠响应头不可靠。"""

    VERSIONED_ASSETS = ("style.css", "app.js")

    def __init__(self, static_dir: Path):
        self.static_dir = static_dir
        self.router = APIRouter()
        self.router.add_api_route("/", self.index, methods=["GET"], include_in_schema=False)

    def asset_url(self, name: str) -> str:
        digest = hashlib.md5((self.static_dir / name).read_bytes()).hexdigest()[:10]
        return f"/static/{name}?v={digest}"

    def index(self):
        html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        for name in self.VERSIONED_ASSETS:
            html = html.replace(f'"/static/{name}"', f'"{self.asset_url(name)}"')
        return HTMLResponse(html)
