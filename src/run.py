"""开发时的启动入口（PyCharm 里直接运行这个文件即可）：python src/run.py

和 Windows 服务用的 `python -m server` 是同一套启动逻辑，见 server.py。
"""

import sys

from server import main

if __name__ == "__main__":
    sys.exit(main())
