"""短时仓库代理：仅允许带随机口令的HTTPS CONNECT，不接受模型指定目标。"""
import base64
import hmac
import ipaddress
import os
import select
import socket
import socketserver
import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I仅信任随镜像发布的脚本目录。
from dependency_policy import REGISTRY_HOSTS


def resolve_public(host, resolver=socket.getaddrinfo):
    """先解析再固定实际连接IP；任何非公网地址都拒绝，避免DNS变更绕过。"""
    if host not in REGISTRY_HOSTS:
        raise ValueError('repository denied')
    values = resolver(host, 443, type=socket.SOCK_STREAM)
    if not values or any(not ipaddress.ip_address(v[4][0]).is_global for v in values):
        raise ValueError('nonpublic repository address')
    return values[0]


class RegistryProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, token):
        super().__init__(address, Tunnel)
        self.authorization = 'Basic ' + base64.b64encode(('agent:' + token).encode()).decode()
        self.deadline = time.monotonic() + 165
        self.lock = threading.Lock()
        self.remaining = 48 * 1024 * 1024  # 包体、元数据及TLS总流量；全连接合计。
        self.slots = threading.BoundedSemaphore(8)

    def charge(self, size):
        with self.lock:
            self.remaining -= size
            return self.remaining >= 0 and time.monotonic() < self.deadline

    def verify_request(self, request, client_address):
        return self.charge(0)


class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            self.relay()
        except (OSError, ValueError):
            pass  # 不把域名解析细节或随机口令写入日志。
        finally:
            self.server.slots.release()

    def relay(self):
        self.request.settimeout(10)
        header = bytearray()
        while b'\r\n\r\n' not in header:
            block = self.request.recv(2048)
            if not block:
                return
            header.extend(block)
            if len(header) > 8192 or not self.server.charge(len(block)):
                return
        raw, extra = bytes(header).split(b'\r\n\r\n', 1)
        lines = raw.decode('ascii').split('\r\n')
        parts = lines[0].split()
        fields = {}
        for line in lines[1:]:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            if key in fields:
                return
            fields[key] = value.strip()
        # Python 3.10/urllib3代理握手可使用HTTP/1.0，Node通常是HTTP/1.1。
        if len(parts) != 3 or parts[0] != 'CONNECT' or parts[2] not in {'HTTP/1.0', 'HTTP/1.1'}:
            return
        if not hmac.compare_digest(fields.get('proxy-authorization', ''), self.server.authorization):
            self.request.sendall(b'HTTP/1.1 407 Proxy Authentication Required\r\n\r\n')
            return
        host, sep, port = parts[1].partition(':')
        if not sep or port != '443':
            return
        family, kind, protocol, _, address = resolve_public(host)
        with socket.socket(family, kind, protocol) as remote:
            remote.settimeout(10)
            remote.connect(address)
            self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            if extra:
                remote.sendall(extra)
            while self.server.charge(0):
                readable, _, _ = select.select([self.request, remote], [], [], 1)
                for source in readable:
                    data = source.recv(32768)
                    if not data or not self.server.charge(len(data)):
                        return
                    (remote if source is self.request else self.request).sendall(data)


if __name__ == '__main__':
    token = os.environ.pop('AGENT_DOWNLOAD_TOKEN')
    with RegistryProxy(('0.0.0.0', 18081), token) as server:
        server.serve_forever(poll_interval=.5)
