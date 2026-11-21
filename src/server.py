"""服务器入口：启动 FastAPI 应用。监听地址、端口等都在 config/config.json 中配置。

    python -m server                 前台运行（在 src 目录下执行），Ctrl+C 停止
    python -m server --port 8080     临时换端口

作为 Windows 服务运行见 service.py（它在子进程里调用这里的 run_server()）。
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _make_server(app, host: str, port: int):
    """uvicorn.Server 在优雅关闭后会把收到的信号重新触发一次，Windows 上会导致进程以退出码 3 结束。
    这里改为只记录信号、优雅关闭，然后正常返回。非主线程下不安装信号处理（由调用方用 should_exit 控制）。"""
    import contextlib
    import signal
    import threading

    import uvicorn

    class QuietExitServer(uvicorn.Server):
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

    return QuietExitServer(uvicorn.Config(app, host=host, port=port, log_config=None))


def run_server(host: str | None = None, port: int | None = None, stop_flag=None) -> int:
    """启动服务器并阻塞到退出。返回退出码：0 正常退出，非 0 启动失败或异常。

    stop_flag：可选，带 requested / server 两个属性的对象。服务器创建后会写入 stop_flag.server，
    调用方设置 stop_flag.server.should_exit = True 即可让服务器优雅关闭（service.py 用）。"""
    import config

    log = config.setup_logging()
    host, port = host or config.HOST, port or config.PORT
    log.info("启动 FridgeManager %s：http://%s:%s（Python %s，%s）",
             config.VERSION, host, port, sys.version.split()[0], sys.prefix)
    try:
        from main import app
        server = _make_server(app, host, port)
        if stop_flag is not None:
            stop_flag.server = server
            if stop_flag.requested:          # 还没启动就收到了停止请求
                server.should_exit = True
        server.run()
    except SystemExit as e:                  # uvicorn 启动失败（如端口被占用）时会 sys.exit(3)
        code = e.code if isinstance(e.code, int) else 1
        if code:
            log.error("服务器启动失败，退出码 %s（端口 %s 是否被占用？）", code, port)
        return code
    except Exception:
        log.exception("服务器异常退出")
        return 1
    if not server.started and not (stop_flag and stop_flag.requested):
        log.error("服务器没有成功启动")
        return 1
    log.info("服务器已退出")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m server", description="冰箱管家 FridgeManager 服务器")
    parser.add_argument("--host", help="监听地址（默认取 config.json 的 server.host）")
    parser.add_argument("--port", type=int, help="端口（默认取 config.json 的 server.port）")
    args = parser.parse_args(argv)
    return run_server(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
