"""启动入口：python src/run.py （host/port 取自 config/config.json）"""

import uvicorn

import config

if __name__ == "__main__":
    config.setup_logging()
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, app_dir=str(config.SRC_DIR), log_config=None)
