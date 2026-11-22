from __future__ import annotations

import datetime
import getpass
import os
import socket
import ssl
import sys
import tempfile
from urllib.parse import urlparse

from importer.recipe_import_error import RecipeImportError
from importer.recipe_importer import RecipeImporter


class ImportDiagnostics:
    """排查"HTTPS 证书校验失败"：打印环境、两种校验方式的结果、网站实际返回的证书，最后做一次导入测试。"""

    ANTIVIRUS = ("Norton", "Avast", "Kaspersky", "ESET")

    def __init__(self, importer: RecipeImporter):
        self.importer = importer

    def run(self, url: str) -> None:
        host = urlparse(url).hostname
        self._print_environment()
        try:
            import truststore
            self._try_connect(host, "系统证书库（truststore，本程序实际使用的方式）",
                              truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        except ImportError:
            pass
        self._try_connect(host, "Python 默认证书（OpenSSL）", ssl.create_default_context())
        self._print_served_cert(host)
        print("-" * 60)
        try:
            d = self.importer.import_recipe(url)
            print(f"导入测试：成功，识别到「{d['name']}」，{len(d['ingredients'])} 种食材")
        except RecipeImportError as e:
            print(f"导入测试：失败 —— {e}")

    @staticmethod
    def _print_environment() -> None:
        print("=" * 60)
        print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
        print(f"环境        : {sys.prefix}")
        print(f"运行账户    : {getpass.getuser()}")
        now = datetime.datetime.now()
        print(f"本机时间    : {now:%Y-%m-%d %H:%M:%S}  (UTC {datetime.datetime.now(datetime.UTC):%Y-%m-%d %H:%M})"
              "  ← 时间不对也会导致“证书已过期”")
        print(f"OpenSSL     : {ssl.OPENSSL_VERSION}")
        try:
            import truststore
            print(f"truststore  : {truststore.__version__}")
        except ImportError:
            print("truststore  : 未安装！请在这个环境里执行 pip install -e .（项目根目录）")
        for k in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY"):
            if os.environ.get(k):
                print(f"环境变量    : {k}={os.environ[k]}")
        print("=" * 60)

    @staticmethod
    def _try_connect(host: str, name: str, ctx: ssl.SSLContext) -> bool:
        try:
            with socket.create_connection((host, 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname=host):
                print(f"[通过] {name}")
                return True
        except ssl.SSLCertVerificationError as e:
            print(f"[失败] {name}：{e.verify_message}")
        except Exception as e:
            print(f"[失败] {name}：{e}")
        return False

    def _print_served_cert(self, host: str) -> None:
        """不校验，只看网站实际返回的证书（被杀毒软件 / 代理替换时，签发者会是它们）。"""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            with socket.create_connection((host, 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname=host) as t:
                pem = ssl.DER_cert_to_PEM_cert(t.getpeercert(binary_form=True))
            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
                f.write(pem)
            info = ssl._ssl._test_decode_cert(f.name)
            os.unlink(f.name)
            issuer = ", ".join(f"{k}={v}" for rdn in info.get("issuer", ()) for k, v in rdn)
            print(f"网站返回的证书：签发者 {issuer}")
            print(f"                有效期 {info.get('notBefore')}  →  {info.get('notAfter')}")
            if any(a in issuer for a in self.ANTIVIRUS):
                print("                ↑ 证书被杀毒软件的 HTTPS 扫描替换了。若本程序作为 Windows 服务运行，"
                      "要确认这个杀毒软件的根证书装在“本地计算机”证书库（不只是当前用户）。")
        except Exception as e:
            print(f"读取网站证书失败：{e}")
