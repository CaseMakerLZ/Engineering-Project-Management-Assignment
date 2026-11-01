"""有上限的 MySQL 连接复用；一次借用只包住一次仓储操作，不包住 Agent 运行。"""

import logging
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from typing import Any, Callable, Iterator


logger = logging.getLogger(__name__)


class MySQLPoolError(RuntimeError):
    """连接池满载或已关闭；只含可对外展示的文案，不含驱动原始错误。"""

    code = "STORAGE_UNAVAILABLE"


class MySQLConnectionPool:
    """按需建立连接；每条连接同一时刻只交给一个调用方，满载立即失败。"""

    def __init__(self, connect: Callable[[], Any], size: int = 5) -> None:
        """只准备内存管理对象，不连接真实数据库。"""
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise ValueError("MySQL 连接池大小必须是正整数")
        self._connect = connect
        self._slots = BoundedSemaphore(size)
        #Lock()是互斥锁，即进行PV操作时信号量为1（Lock()底层实现不是用信号量，但是理解代码时可以默认有一个信号量为1）
        self._lock = Lock()
        self._idle: list[Any] = []
        self._closed = False

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """借出独占连接；成功后清理事务/会话再归还，异常连接直接丢弃。

        acquire 许可（非阻塞，拿不到就报错）
              → 加锁，池关了？报错
              → 空闲池有连接？pop 一个
              → ping 检查，断了就销毁
              → 还没有？新建
              → 再加锁，池关了？报错
              → yield 交给调用方
              → 调用方用完 / 抛异常
              → reset_session 清理，成功标记可复用
              → finally：
                  可复用且池没关 → 放回空闲池
                  否则 → 销毁
                  释放许可（一定执行）
        """
        if not self._slots.acquire(blocking=False):
            raise MySQLPoolError("MySQL 连接正在使用中，请稍后重试")
        connection = None
        reusable = False
        try:
            with self._lock:
                if self._closed:
                    raise MySQLPoolError("MySQL 连接池已关闭")
                if self._idle:
                    connection = self._idle.pop()
            if connection is not None:
                try:
                    # 只在执行 SQL 之前检查断线；不自动重试 SQL，避免重复写入。
                    connection.ping(reconnect=False)
                except Exception:
                    self._dispose(connection)
                    connection = None
            if connection is None:
                connection = self._connect()
            with self._lock:
                if self._closed:
                    raise MySQLPoolError("MySQL 连接池已关闭")
            yield connection
            # 清掉只读查询留下的事务、会话变量等，不能让下个任务继承。
            try:
                connection.reset_session()
                reusable = True
            except Exception:
                # SQL 可能已经提交成功；清理失败只丢弃连接，不伪装成写入失败。
                logger.warning("MySQL 连接归还前清理失败；该连接将被关闭")
        finally:
            if connection is not None:
                with self._lock:
                    if reusable and not self._closed:
                        self._idle.append(connection)
                        connection = None
                if connection is not None:
                    self._dispose(connection)
            self._slots.release()

    def close(self) -> None:
        """停止借出并关闭空闲连接；仍在使用的连接等本次操作退出后关闭。"""
        with self._lock:
            self._closed = True
            idle, self._idle = self._idle, []
        for connection in idle:
            self._dispose(connection)

    @staticmethod
    def _dispose(connection: Any) -> None:
        """尽力关闭坏连接，不用清理异常覆盖原来的数据库错误。"""
        try:
            connection.close()
        except Exception:
            logger.warning("关闭 MySQL 连接失败；该连接已移出连接池")
