import uvicorn
import sys
from pathlib import Path

# 支持在 PyCharm 中直接运行本文件，也支持以包模块方式启动。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.api import app


if __name__ == "__main__":
    # 开发阶段使用 Uvicorn；生产部署时可由进程管理器启动 ASGI 应用。
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
