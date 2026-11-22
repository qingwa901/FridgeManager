"""冰箱管家 FridgeManager：唯一的程序入口。监听地址、端口等都在 config/config.json 中配置。

    python -m main                 前台运行（在 src 目录下执行），Ctrl+C 停止
    python -m main --port 8080     临时换端口
    python src/main.py             同上（PyCharm 里直接运行这个文件即可）

作为 Windows 服务运行见 service.py（它在子进程里运行这里的 Server）。

代码结构：
    main.py      组装应用（FridgeManagerApp）、启动服务器（Server）
    api/         HTTP 接口，每个类一组路由
    function/    业务功能（冰箱、食谱、大类、推荐、荤素判断、版本号）
    data/        数据读写，一张表一个类
    importer/    从链接导入食谱
日志、FastAPI 应用的公共部分（请求计时、参数校验错误、接口文档）来自公共库 ZQCommonLib（libs/CommonLib）。
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import argparse
import contextlib
import signal
import threading
from contextlib import asynccontextmanager
from http import HTTPStatus

import uvicorn
from common_lib import Base
from common_lib.api import BaseResponse, ErrorResponse, create_app, setup_api_logging
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.food_api import FoodApi
from api.group_api import GroupApi
from api.page_api import PageApi
from api.recipe_api import RecipeApi
from api.recommend_api import RecommendApi
from api.system_api import SystemApi
from config import Settings, settings
from data import Database
from function.fridge_service import FridgeService
from function.group_service import GroupService
from function.recipe_service import RecipeService
from function.recipe_type_classifier import RecipeTypeClassifier
from function.recommender import Recommender
from function.service_error import ServiceError
from importer import RecipeImporter


class FridgeManagerApp(Base):
    """把数据库、业务功能和接口组装成 FastAPI 应用（self.app）。

    应用由公共库的 create_app 创建：接口文档在 /api/docs，每个请求记录耗时（日志带请求 ID）。
    出错时都返回公共库的错误格式 {"Error": {"Title", "Method", "ErrorMsg"}}，HTTP 状态码为 404 / 409 / 422。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.static_dir = settings.SRC_DIR / "static"

        self.db = Database(settings.db_path)
        classifier = RecipeTypeClassifier(settings.meat_words, settings.veg_exceptions)
        self.fridge = FridgeService(self.db, settings.expiring_days)
        self.recipes = RecipeService(self.db, classifier, RecipeImporter(settings), settings.SEED_RECIPES_FILE)
        self.groups = GroupService(self.db)
        self.recommender = Recommender(self.fridge, self.recipes, self.groups)

        self.app = create_app(title="冰箱管家 FridgeManager", version=settings.version, prefix="/api",
                              host=settings.host, port=settings.port, lifespan=self._lifespan)
        self.app.middleware("http")(self._no_cache)
        self.app.add_exception_handler(ServiceError, self._service_error)
        self.app.add_exception_handler(RequestValidationError, self._validation_error)
        for api in (SystemApi(settings), FoodApi(self.fridge), RecipeApi(self.recipes), GroupApi(self.groups),
                    RecommendApi(self.recommender), PageApi(self.static_dir)):
            self.app.include_router(api.router)
        self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")

    @asynccontextmanager
    async def _lifespan(self, _: FastAPI):
        self.db.initialize()
        self.recipes.load_seeds()
        self.get_logger().info("服务启动：版本=%s 数据库=%s 日志目录=%s", self.settings.version,
                               self.settings.db_path, self.settings.log_dir)
        yield
        self.get_logger().info("服务停止")

    @staticmethod
    async def _no_cache(request: Request, call_next):
        """页面和静态文件每次都向服务器确认是否有更新，避免改版后浏览器还用旧的 JS/CSS。"""
        response = await call_next(request)
        if not request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @classmethod
    def _error(cls, request: Request, status_code: int, message: str) -> JSONResponse:
        """用公共库的错误格式 {"Error": {"Title", "Method", "ErrorMsg"}} 返回。"""
        cls.get_logger().warning("%s %s -> %d %s", request.method, request.url.path, status_code, message)
        body = BaseResponse(Error=ErrorResponse(Title=HTTPStatus(status_code).phrase, Method=request.url.path,
                                                ErrorMsg=message))
        return JSONResponse(jsonable_encoder(body), status_code=status_code)

    @classmethod
    async def _service_error(cls, request: Request, e: ServiceError):
        """业务错误，HTTP 状态码保持 404 / 409 / 422。"""
        return cls._error(request, e.status_code, e.message)

    @classmethod
    async def _validation_error(cls, request: Request, e: RequestValidationError):
        """参数校验失败（422）。替换公共库的 ExceptionHandler.standard_validation_exception_handler：
        它会把错误消息也写进响应头，而响应头只能放 latin-1 字符，中文消息（如"保质期不能早于存入日期"）会出错。"""
        msgs = [str(err["msg"]).removeprefix("Value error, ") for err in e.errors()]
        return cls._error(request, HTTPStatus.UNPROCESSABLE_ENTITY, "；".join(msgs))


class QuietExitServer(uvicorn.Server):
    """uvicorn.Server 在优雅关闭后会把收到的信号重新触发一次，Windows 上会导致进程以退出码 3 结束。
    这里改为只记录信号、优雅关闭，然后正常返回。非主线程下不安装信号处理（由调用方用 should_exit 控制）。"""

    @contextlib.contextmanager
    def capture_signals(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        sigs = [getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGBREAK") if hasattr(signal, n)]
        original = {s: signal.signal(s, self.handle_exit) for s in sigs}
        try:
            yield
        finally:
            for s, h in original.items():
                signal.signal(s, h)


class Server(Base):
    """启动服务器并阻塞到退出。

    没有用公共库的 run_api：Windows 服务需要能从另一个线程让服务器优雅关闭（stop_flag），
    并且要拿到退出码判断服务器是否启动成功，run_api（uvicorn.run）做不到。"""

    LOG_NAME = "fridgemanager"   # 日志文件名前缀：fridgemanager_{启动时间}.log（也会清理旧的 fridgemanager.log.*）

    def __init__(self, settings: Settings, host: str | None = None, port: int | None = None):
        self.settings = settings
        self.host = host or settings.host
        self.port = port or settings.port

    @classmethod
    def setup_logging(cls, settings: Settings) -> str:
        """公共库的日志：控制台 + 每天午夜轮转的日志文件，带请求 ID；清理 retention_days 天前的日志。返回日志文件路径。"""
        return setup_api_logging(cls.LOG_NAME, str(settings.log_dir), level=settings.log_level,
                                 retention_days=settings.log_retention_days)

    def run(self, stop_flag=None) -> int:
        """返回退出码：0 正常退出，非 0 启动失败或异常。

        stop_flag：可选，带 requested / server 两个属性的对象。服务器创建后会写入 stop_flag.server，
        调用方设置 stop_flag.server.should_exit = True 即可让服务器优雅关闭（service.py 用）。"""
        log_file = self.setup_logging(self.settings)
        log = self.get_logger()
        log.info("启动 FridgeManager %s：http://%s:%s（Python %s，%s），日志：%s",
                 self.settings.version, self.host, self.port, sys.version.split()[0], sys.prefix, log_file)
        try:
            app = FridgeManagerApp(self.settings).app
            server = QuietExitServer(uvicorn.Config(app, host=self.host, port=self.port, log_config=None))
            if stop_flag is not None:
                stop_flag.server = server
                if stop_flag.requested:          # 还没启动就收到了停止请求
                    server.should_exit = True
            server.run()
        except SystemExit as e:                  # uvicorn 启动失败（如端口被占用）时会 sys.exit(3)
            code = e.code if isinstance(e.code, int) else 1
            if code:
                log.error("服务器启动失败，退出码 %s（端口 %s 是否被占用？）", code, self.port)
            return code
        except Exception:
            log.exception("服务器异常退出")
            return 1
        if not server.started and not (stop_flag and stop_flag.requested):
            log.error("服务器没有成功启动")
            return 1
        log.info("服务器已退出")
        return 0

    @classmethod
    def from_args(cls, argv: list[str] | None = None) -> "Server":
        parser = argparse.ArgumentParser(prog="python -m main", description="冰箱管家 FridgeManager 服务器")
        parser.add_argument("--host", help="监听地址（默认取 config.json 的 server.host）")
        parser.add_argument("--port", type=int, help="端口（默认取 config.json 的 server.port）")
        args = parser.parse_args(argv)
        return cls(settings, args.host, args.port)


if __name__ == "__main__":
    sys.exit(Server.from_args().run())
