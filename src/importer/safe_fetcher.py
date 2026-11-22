from __future__ import annotations

import ipaddress
import os
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from common_lib import Base

from importer.recipe_import_error import RecipeImportError


class SafeFetcher(Base):
    """安全抓取网页：只允许 https + allowed_hosts 里的网站，解析出的地址必须是公网（防止借本服务访问局域网/本机），
    跳转后的地址同样检查。HTTPS 证书优先交给操作系统校验（truststore），结果和浏览器一致。"""

    MAX_BYTES = 3 * 1024 * 1024
    TIMEOUT = 10
    USER_AGENT = "Mozilla/5.0 (compatible; FridgeManager-recipe-importer)"

    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = allowed_hosts
        self.ssl_context: ssl.SSLContext | None = None
        self._opener = None

    def check_url(self, url: str) -> None:
        p = urlparse(url)
        allowed = "、".join(sorted(self.allowed_hosts))
        if p.scheme != "https" or not p.hostname:
            raise RecipeImportError(f"只支持 https 链接（允许的网站：{allowed}）")
        if p.username or p.password or p.hostname.lower() not in self.allowed_hosts:
            raise RecipeImportError(f"只能从这些网站导入：{allowed}")
        try:
            infos = socket.getaddrinfo(p.hostname, p.port or 443)
        except socket.gaierror:
            raise RecipeImportError(f"无法解析域名：{p.hostname}")
        for info in infos:
            if not ipaddress.ip_address(info[4][0]).is_global:
                raise RecipeImportError("不允许访问内网或本机地址")

    @classmethod
    def create_ssl_context(cls) -> ssl.SSLContext:
        """优先用 truststore：交给操作系统（Windows 证书库）校验证书，和浏览器结果一致。
        这样在 Norton / 公司代理等会替换 HTTPS 证书的环境下也能正常访问。没装则退回 Python 默认校验。"""
        try:
            import truststore
            cls.get_logger().info("HTTPS 证书校验：使用操作系统证书库（truststore %s）", truststore.__version__)
            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            cls.get_logger().warning("未安装 truststore，使用 Python 默认证书校验（可能与浏览器结果不一致）")
            return ssl.create_default_context()

    def opener(self):
        """首次使用时创建（此时日志已初始化，能记录用的是哪种证书校验）。"""
        if self._opener is None:
            fetcher = self

            class SafeRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    fetcher.check_url(newurl)
                    return super().redirect_request(req, fp, code, msg, headers, newurl)

            self.ssl_context = self.create_ssl_context()
            self._opener = urllib.request.build_opener(SafeRedirect, urllib.request.HTTPSHandler(context=self.ssl_context))
        return self._opener

    def fetch(self, url: str) -> tuple[str, str]:
        """返回 (最终 URL, 文本内容)。"""
        self.check_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "text/html,application/json"})
        try:
            with self.opener().open(req, timeout=self.TIMEOUT) as resp:
                data = resp.read(self.MAX_BYTES + 1)
                charset = resp.headers.get_content_charset() or "utf-8"
                final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            raise RecipeImportError(f"页面返回错误 {e.code}")
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                raise self._cert_error(url, e.reason)
            raise RecipeImportError(f"无法打开页面：{e.reason}")
        except TimeoutError as e:
            raise RecipeImportError(f"无法打开页面：{getattr(e, 'reason', e)}")
        if len(data) > self.MAX_BYTES:
            raise RecipeImportError("页面太大")
        return final_url, data.decode(charset, errors="replace")

    def _cert_error(self, url: str, reason: ssl.SSLCertVerificationError) -> RecipeImportError:
        self.get_logger().warning("HTTPS 证书校验失败 %s：%s（SSL 实现：%s，SSL_CERT_FILE=%s，SSL_CERT_DIR=%s，REQUESTS_CA_BUNDLE=%s）",
                                  url, reason, type(self.ssl_context).__module__, os.environ.get("SSL_CERT_FILE"),
                                  os.environ.get("SSL_CERT_DIR"), os.environ.get("REQUESTS_CA_BUNDLE"))
        msg = str(reason.verify_message or reason)
        if any(w in msg.lower() for w in ("expired", "not yet valid", "过期", "有效期")):
            # 证书"已过期 / 尚未生效"最常见的原因是本机时间不对
            return RecipeImportError(f"网站 HTTPS 证书校验失败（{msg}）。请先检查服务器的系统时间是否正确"
                                     f"（服务器当前时间：{datetime.now():%Y-%m-%d %H:%M}）")
        return RecipeImportError(f"网站 HTTPS 证书校验失败（{msg}）。"
                                 "如果浏览器能正常打开，请确认服务器用的 Python 环境已安装 truststore（pip install -e .），"
                                 "或在服务器上运行 python -m importer <链接> 查看诊断信息")
