"""Windows 服务包装：把 server.py 的服务器包装成 Windows 服务。

只负责服务的启动 / 停止，不负责注册；监听地址、端口等都在 config/config.json 中配置。

    python -m service          由 Windows 服务管理器启动（注册服务时用这个命令）
    python -m service debug    在控制台按服务的方式运行，Ctrl+C 停止（不用注册即可测试）

结构：
    父进程（本文件）：只做服务控制，导入很轻，能尽快连上服务管理器；
    子进程：运行 server.run_server()（uvicorn），停止时先优雅关闭，超时再结束整个进程树。
"""

import logging
import multiprocessing
import subprocess
import sys
import threading
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    import servicemanager
    import win32service
    import win32serviceutil
except Exception as error:   # 缺少 pywin32 时也让模块能被导入，方便给出提示
    logging.getLogger("WinService").error("Failed to import pywin32", exc_info=error)
    raise

GRACEFUL_STOP_SECONDS = 10   # 优雅关闭的等待时间，超时后强制结束进程树


def _run_server_process(stop_event) -> None:
    """子进程入口。延迟导入 server（以及 FastAPI、数据库等），
    这样父进程自身的导入很轻，StartServiceCtrlDispatcher() 能尽快连上服务管理器。"""
    import server

    class StopFlag:
        requested = False
        server = None

    flag = StopFlag()

    def wait_for_stop():
        stop_event.wait()
        flag.requested = True
        if flag.server is not None:
            flag.server.should_exit = True   # 让 uvicorn 优雅关闭

    threading.Thread(target=wait_for_stop, name="stop-watcher", daemon=True).start()
    sys.exit(server.run_server(stop_flag=flag))


class FridgeManagerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "FridgeManager"
    _svc_display_name_ = "冰箱管家 FridgeManager"
    _svc_description_ = "冰箱管家：记录冰箱食材与保质期，推荐食谱，管理补货清单。"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_requested = False
        self._stop_lock = threading.Lock()
        self._stopped = False
        self._stop_done = threading.Event()
        self.stop_event = multiprocessing.Event()
        self.process = multiprocessing.Process(target=_run_server_process, args=(self.stop_event,),
                                               name="FridgeManagerServer")

    def GetAcceptedControls(self):
        result = win32serviceutil.ServiceFramework.GetAcceptedControls(self)
        result |= win32service.SERVICE_ACCEPT_PRESHUTDOWN
        return result

    def SvcOtherEx(self, control, event_type, data):
        # pywin32 只把 SERVICE_CONTROL_STOP 交给 SvcStop()；关机 / 重启时发送的 PRESHUTDOWN 会到这里，
        # 默认被忽略，服务管理器就会报告"收到预关闭控制后没有正确关闭"。
        if control == win32service.SERVICE_CONTROL_PRESHUTDOWN:
            servicemanager.LogInfoMsg("FridgeManager: 收到系统关机（preshutdown）通知")
            self.SvcStop()
        else:
            win32serviceutil.ServiceFramework.SvcOtherEx(self, control, event_type, data)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(f"FridgeManager: 服务启动（Python {sys.version.split()[0]}，{sys.prefix}）")
        self.process.start()
        servicemanager.LogInfoMsg(f"FridgeManager: 服务器进程已启动（pid={self.process.pid}）")

        while not self.stop_requested:
            self.process.join(5)
            if not self.process.is_alive() and not self.stop_requested:
                # 服务器自己退出了（如端口被占用、配置错误）：报告失败，让服务管理器按恢复策略处理，
                # 而不是让服务一直显示"正在运行"却什么也不做。
                code = self.process.exitcode
                servicemanager.LogErrorMsg(f"FridgeManager: 服务器进程意外退出（退出码 {code}），详见 logs 目录下的日志")
                raise RuntimeError(f"服务器进程意外退出，退出码 {code}")

        # 等 SvcStop 把子进程清理完再返回；返回后服务管理器会认为服务已停止，进程随时可能被回收。
        self._stop_done.wait(GRACEFUL_STOP_SECONDS + 15)

    def SvcStop(self):
        # 防止重复进入：PRESHUTDOWN 和 STOP 可能先后到达
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True

        try:
            servicemanager.LogInfoMsg("FridgeManager: 正在停止服务")
            # waitHint 告诉服务管理器下一次进度报告前要等多久，避免较慢的关闭被当成卡死
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=(GRACEFUL_STOP_SECONDS + 10) * 1000)
            self.stop_requested = True

            if self.process.is_alive():
                # 1) 优雅关闭：通知子进程让 uvicorn 正常退出（日志里会有"服务停止"）
                self.stop_event.set()
                self.process.join(GRACEFUL_STOP_SECONDS)

            if self.process.is_alive():
                # 2) 超时：结束子进程及其所有子孙进程。Process.terminate() 在 Windows 上只结束直接子进程，
                #    taskkill /T 会结束整个进程树。
                pid = self.process.pid
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=10000)
                servicemanager.LogInfoMsg(f"FridgeManager: 优雅关闭超时，结束进程树（pid={pid}）")
                try:
                    result = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                            capture_output=True, text=True, check=False)
                    servicemanager.LogInfoMsg(f"FridgeManager: taskkill: {result.stdout.strip() or result.stderr.strip()}")
                except Exception as kill_error:
                    servicemanager.LogErrorMsg(f"FridgeManager: taskkill 失败：{kill_error}")
                self.process.join(timeout=5)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=3)

            servicemanager.LogInfoMsg(f"FridgeManager: 服务已停止（服务器进程退出码 {self.process.exitcode}）")
        except Exception as e:
            servicemanager.LogErrorMsg(f"FridgeManager: 停止服务时出错：{e}")
        finally:
            self._stop_done.set()


def main() -> None:
    try:
        if len(sys.argv) == 1:
            # 由 Windows 服务管理器启动
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(FridgeManagerService)
            servicemanager.StartServiceCtrlDispatcher()
        elif sys.argv[1:] == ["debug"]:
            # 在控制台按服务的方式运行（不需要注册服务），Ctrl+C 停止
            win32serviceutil.DebugService(FridgeManagerService, [FridgeManagerService._svc_name_])
        else:
            print("用法：python -m service          （由 Windows 服务管理器启动）\n"
                  "      python -m service debug    （在控制台按服务方式运行，Ctrl+C 停止）")
            sys.exit(2)
    except Exception as error:
        if getattr(error, "winerror", None) == 1063:   # 不是由服务管理器启动的
            print("python -m service 需要由 Windows 服务管理器启动。\n"
                  "在控制台测试请用：python -m service debug；直接运行服务器请用：python -m server")
            sys.exit(1)
        logging.getLogger("WinService").error("Failed to start", exc_info=error)
        raise


if __name__ == "__main__":
    main()
