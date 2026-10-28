import sys
from pathlib import Path

# 支持在 PyCharm 中直接运行本文件，也支持以包模块方式启动。
if __package__ in (None, ""):
    service_directory = Path(__file__).resolve().parent
    # 直接运行本文件时，这个目录会排在模块查找路径中。
    # 必须移除它，否则 http/ 会遮住 Python 自带的 http，导致 FastAPI 导入失败。
    sys.path[:] = [
        entry for entry in sys.path
        if Path(entry).resolve() != service_directory
    ]
    sys.path.insert(0, str(service_directory.parent))

import uvicorn

from agent_service.app import app


if __name__ == "__main__":
    # 开发阶段使用 Uvicorn；生产部署时可由进程管理器启动 ASGI 应用。
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
