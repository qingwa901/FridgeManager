"""服务器入口：前台运行，或用 pywin32 注册为 Windows 服务。

在 src 目录下，用某个虚拟环境的 python 执行：

    python -m server                 前台运行（开发 / 调试），Ctrl+C 停止
    python -m server --port 8080     前台运行，临时换端口
    python -m server install         注册为 Windows 服务（需管理员），开机自动启动、崩溃自动重启；
                                     服务已存在时则更新为当前虚拟环境（升级用）
    python -m server start | stop | restart | status
    python -m server remove          删除服务（需管理员）

服务怎么运行（为什么不用 pywin32 默认的 pythonservice.exe）：
    虚拟环境里的 python.exe 只是个转发器，pythonservice.exe 在虚拟环境里又找不到 Python 的 DLL，
    两者作为服务都容易启动失败（错误 1053）。所以服务直接运行“真正的” python.exe：
        "<Python 安装目录>\\python.exe" -S "<src>\\server.py" --service --venv "<虚拟环境>"
    启动时再手动加载该虚拟环境的 site-packages（包括 pywin32），效果等同于在虚拟环境里运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
SERVER_PY = Path(__file__).resolve()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SERVICE_NAME = "FridgeManager"
SERVICE_DISPLAY = "冰箱管家 FridgeManager"
SERVICE_DESC = "冰箱管家：记录冰箱食材与保质期，推荐食谱，管理补货清单。"


def _load_venv_from_argv() -> None:
    """服务模式下由真正的 python.exe -S 启动：把 --venv 指定的虚拟环境加入模块搜索路径。
    site.addsitedir 会处理其中的 .pth 文件（pywin32 靠 pywin32.pth 加载自己的 DLL 目录）。"""
    if "--venv" in sys.argv:
        venv = Path(sys.argv[sys.argv.index("--venv") + 1])
        import site
        site.addsitedir(str(venv / "Lib" / "site-packages"))


_load_venv_from_argv()


# ---------------------------------------------------------------- uvicorn

def _make_server(app, host: str, port: int):
    """uvicorn.Server 在优雅关闭后会把收到的信号重新触发一次，Windows 上会导致进程以退出码 3 结束。
    这里改为只记录信号、优雅关闭，然后正常返回。非主线程（服务模式）下不安装信号处理，由 SvcStop 控制。"""
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
    """启动服务器并阻塞到退出。返回退出码：0 正常退出，非 0 启动失败或异常。"""
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


# ---------------------------------------------------------------- Windows 服务

def _service_class():
    import servicemanager
    import win32service
    import win32serviceutil

    class StopFlag:
        requested = False
        server = None

    class FridgeService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            super().__init__(args)
            self.stop_flag = StopFlag()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=15000)
            self.stop_flag.requested = True
            if self.stop_flag.server is not None:
                self.stop_flag.server.should_exit = True

        def SvcDoRun(self):
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} 服务启动（{sys.prefix}）")
            code = run_server(stop_flag=self.stop_flag)
            if code:
                servicemanager.LogErrorMsg(f"{SERVICE_NAME} 启动失败，退出码 {code}，详见 logs 目录下的日志")
                # 抛出异常 = 告诉服务管理器"异常停止"，从而触发自动重启（install 时配置的恢复策略）
                raise RuntimeError(f"服务器启动失败，退出码 {code}")
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} 服务已停止")

    return FridgeService


def _host_service() -> int:
    """被服务管理器启动时调用：把当前进程交给服务控制分派器。"""
    import servicemanager
    import pywintypes

    cls = _service_class()
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(cls)
    try:
        servicemanager.StartServiceCtrlDispatcher()
    except pywintypes.error as e:
        if e.winerror == 1063:   # ERROR_FAILED_SERVICE_CONTROLLER_CONNECT：不是被服务管理器启动的
            print("--service 只供 Windows 服务管理器使用。前台运行请用：python -m server", file=sys.stderr)
            return 2
        raise
    return 0


def _service_command_line() -> tuple[str, str]:
    """服务要执行的程序和参数。在虚拟环境中：真正的 python.exe -S + --venv；否则直接用当前 python。"""
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        exe = getattr(sys, "_base_executable", None) or str(Path(sys.base_prefix) / "python.exe")
        args = f'-S "{SERVER_PY}" --service --venv "{sys.prefix}"'
    else:
        exe = sys.executable
        args = f'"{SERVER_PY}" --service'
    return exe, args


def _service_command(cmd: str) -> int:
    try:
        import pywintypes
        import win32service
        import win32serviceutil
    except ImportError:
        print("缺少 pywin32。请在当前虚拟环境中执行：python -m pip install -e ..（或 pip install pywin32）")
        return 1

    def state() -> str | None:
        try:
            s = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
        except pywintypes.error as e:
            if e.winerror == 1060:    # ERROR_SERVICE_DOES_NOT_EXIST
                return None
            raise
        return {win32service.SERVICE_STOPPED: "已停止", win32service.SERVICE_START_PENDING: "正在启动",
                win32service.SERVICE_STOP_PENDING: "正在停止", win32service.SERVICE_RUNNING: "运行中",
                win32service.SERVICE_PAUSED: "已暂停"}.get(s, str(s))

    try:
        current = state()
        if cmd == "status":
            print(f"服务 {SERVICE_NAME}：{current or '未安装'}")
            return 0

        if cmd == "install":
            exe, args = _service_command_line()
            cls = f"{SERVER_PY.with_suffix('')}.FridgeService"
            if current is None:
                win32serviceutil.InstallService(cls, SERVICE_NAME, SERVICE_DISPLAY,
                                                startType=win32service.SERVICE_AUTO_START,
                                                exeName=exe, exeArgs=args, description=SERVICE_DESC)
                print(f"已安装服务 {SERVICE_NAME}（开机自动启动）")
            else:
                win32serviceutil.ChangeServiceConfig(cls, SERVICE_NAME, startType=win32service.SERVICE_AUTO_START,
                                                     exeName=exe, exeArgs=args, displayName=SERVICE_DISPLAY,
                                                     description=SERVICE_DESC)
                print(f"服务 {SERVICE_NAME} 已存在，已更新为当前环境（当前状态：{current}）")
                if current == "运行中":
                    print("  需要重启才会生效：python -m server restart")
            _set_recovery()
            print(f"  程序：{exe}")
            print(f"  参数：{args}")
            print("  启动服务：python -m server start")
            return 0

        if current is None:
            print(f"服务 {SERVICE_NAME} 未安装，先执行：python -m server install")
            return 1
        if cmd == "start":
            win32serviceutil.StartService(SERVICE_NAME)
            win32serviceutil.WaitForServiceStatus(SERVICE_NAME, win32service.SERVICE_RUNNING, 30)
        elif cmd == "stop":
            win32serviceutil.StopServiceWithDeps(SERVICE_NAME, waitSecs=30)
        elif cmd == "restart":
            win32serviceutil.RestartService(SERVICE_NAME, waitSeconds=30)
        elif cmd == "remove":
            if current != "已停止":
                win32serviceutil.StopServiceWithDeps(SERVICE_NAME, waitSecs=30)
            win32serviceutil.RemoveService(SERVICE_NAME)
            print(f"已删除服务 {SERVICE_NAME}")
            return 0
        print(f"服务 {SERVICE_NAME}：{state()}")
        return 0
    except pywintypes.error as e:
        if e.winerror == 5:
            print("权限不足：请用“以管理员身份运行”打开命令行后再执行。")
        else:
            print(f"操作失败：{e.strerror}（{e.funcname}，错误码 {e.winerror}）")
            if cmd in ("start", "restart"):
                print("  启动失败的原因请看 logs 目录下的日志，或 Windows 事件查看器 → Windows 日志 → 应用程序。")
        return 1


def _set_recovery() -> None:
    """崩溃或启动失败时自动重启：5 秒、10 秒、60 秒后重试，一天后重置计数。"""
    import subprocess
    for args in (["failure", SERVICE_NAME, "reset=", "86400", "actions=", "restart/5000/restart/10000/restart/60000"],
                 ["failureflag", SERVICE_NAME, "1"]):
        subprocess.run(["sc.exe", *args], capture_output=True)


# ---------------------------------------------------------------- 入口

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m server", description="冰箱管家 FridgeManager 服务器")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "install", "remove", "start", "stop", "restart", "status"],
                        help="run=前台运行（默认）；其余为 Windows 服务管理")
    parser.add_argument("--host", help="监听地址（默认取 config.json 的 server.host）")
    parser.add_argument("--port", type=int, help="端口（默认取 config.json 的 server.port）")
    parser.add_argument("--service", action="store_true", help=argparse.SUPPRESS)  # 服务管理器启动时使用
    parser.add_argument("--venv", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.service:
        return _host_service()
    if args.command == "run":
        return run_server(args.host, args.port)
    return _service_command(args.command)


if __name__ == "__main__":
    sys.exit(main())
