#!/usr/bin/env bash
# 仅管理Agent自己的站点文件，不覆盖全局nginx.conf。
set -euo pipefail
DOMAIN="${1:-_}"
[[ "$(id -u)" == 0 ]] || { echo '请以sudo运行' >&2; exit 2; }
[[ "$DOMAIN" == _ || "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || {
    echo '域名只填example.com，不填https://、端口或路径' >&2; exit 2;
}
CONF=/etc/nginx/conf.d/agent.conf
# 证书已经启用时不覆盖HTTPS配置，更新代码不应把HTTPS退回HTTP。
if [[ -f "$CONF" ]] && grep -q 'ssl_certificate' "$CONF"; then
    grep -Fq "server_name $DOMAIN;" "$CONF" || { echo '已有HTTPS域名不同，需人工检查' >&2; exit 1; }
    nginx -t
    systemctl reload nginx
    exit 0
fi
candidate="$(mktemp /etc/nginx/agent-candidate.XXXXXX)"
backup="$(mktemp /etc/nginx/agent-backup.XXXXXX)"
had_old=false
[[ ! -f "$CONF" ]] || { cp -p "$CONF" "$backup"; had_old=true; }
trap 'rm -f "$candidate" "$backup"' EXIT
cat > "$candidate" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    root /opt/agent/current/web;
    index index.html;
    server_tokens off;
    client_max_body_size 8m;
    location / { try_files \$uri \$uri/ /index.html; }
    # 不直接在网站域名中执行Agent产出的HTML；下载由Java鉴权接口处理。
    location ~ ^/api/.*/events$ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        gzip off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF
install -m 0644 "$candidate" "$CONF"
if ! nginx -t; then
    if [[ "$had_old" == true ]]; then cp -p "$backup" "$CONF"; else rm -f "$CONF"; fi
    echo 'Nginx校验失败，已恢复原站点文件' >&2
    exit 1
fi
# 新服务器默认欢迎站点会抢占IP访问；移动备份，不删除原始配置。
if [[ -L /etc/nginx/sites-enabled/default ]]; then
    mv /etc/nginx/sites-enabled/default /etc/nginx/agent-default-site.backup
fi
systemctl reload nginx
echo "已配置HTTP站点 $DOMAIN，SSE不缓冲；不暴露Python/MySQL。"
