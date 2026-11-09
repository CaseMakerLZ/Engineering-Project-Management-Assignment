#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${1:-_}"
[[ "$(id -u)" == 0 ]] || { echo '请以sudo运行' >&2; exit 1; }
for service in mysql docker agent-python agent-java nginx; do
    systemctl is-active --quiet "$service"
    echo "OK $service"
done
nginx -t
export PYTHONPATH=/opt/agent/current/python
/opt/agent/current/venv/bin/python /opt/agent/current/deploy/server-settings.py health
for port in 8000 8080; do
    addresses="$(ss -lntH | awk -v port="$port" '$4 ~ (":" port "$") {print $4}')"
    # Java可能以IPv4映射IPv6形式显示127.0.0.1；按地址含义而非字符串前缀判断。
    python3 -c '
import ipaddress, sys
port, values = sys.argv[1], sys.argv[2].split()
if not values:
    raise SystemExit(f"端口{port}没有监听，拒绝验收")
for value in values:
    address = ipaddress.ip_address(value.rsplit(":", 1)[0].strip("[]"))
    mapped = getattr(address, "ipv4_mapped", None)
    if not (mapped or address).is_loopback:
        raise SystemExit(f"端口{port}正在非回环地址{address}监听，拒绝验收")
' "$port" "$addresses"
done
# HTTPS启用后会重定向，取回非空静态页并单独检查HTTP返回码。
code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -H "Host: $DOMAIN" http://127.0.0.1/)"
[[ "$code" == 200 || "$code" == 301 || "$code" == 308 ]]
docker image inspect python-agent-sandbox:1 >/dev/null
echo '基础验收通过；浏览器还需验证注册/登录、SSE、DOCX下载和两个账号隔离。'
