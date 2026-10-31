"""文件响应自己的清理边界，不依赖网络断开后普通生成器被及时回收。"""

import anyio
from starlette.responses import StreamingResponse


class DownloadResponse(StreamingResponse):
    """正常结束、发送失败或请求取消，都关闭读取器并归还下载名额。"""

    def __init__(self, handle, **kwargs) -> None:
        self.handle = handle
        self.chunks = handle.iter_chunks()
        super().__init__(self.chunks, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # 等正在进行的同步读取退出后再关闭；取消不能跳过资源回收。
            with anyio.CancelScope(shield=True):
                try:
                    await anyio.to_thread.run_sync(self.chunks.close)
                finally:
                    await anyio.to_thread.run_sync(self.handle.close)
