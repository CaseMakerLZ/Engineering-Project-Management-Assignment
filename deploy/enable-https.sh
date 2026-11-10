#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${1:-}"
EMAIL="${2:-}"
[[ "$(id -u)" == 0 ]] || { echo '请以sudo运行' >&2; exit 2; }
[[ "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || {
    echo '用法：sudo bash enable-https.sh example.com your@email.com' >&2; exit 2;
}
[[ "$EMAIL" == *@* && "$EMAIL" != *[[:space:]]* && "$EMAIL" != -* ]] || { echo '请提供证书通知邮箱' >&2; exit 2; }
[[ -f /etc/nginx/conf.d/agent.conf ]] || { echo '先部署HTTP站点' >&2; exit 1; }
grep -Fq "server_name $DOMAIN;" /etc/nginx/conf.d/agent.conf || { echo '域名与现有站点不匹配' >&2; exit 1; }
echo '前提：DNS已指向本服务器、80/443已放行；大陆服务器网站备案已按要求完成。'
getent ahosts "$DOMAIN" >/dev/null || { echo 'DNS尚不可解析' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y certbot python3-certbot-nginx
cp -p /etc/nginx/conf.d/agent.conf "/etc/nginx/agent-before-https-$(date +%s).backup"
certbot --nginx --non-interactive --agree-tos --email "$EMAIL" --domain "$DOMAIN" --redirect
nginx -t
systemctl enable --now certbot.timer
curl --fail --silent --show-error --max-time 15 "https://$DOMAIN/" >/dev/null
echo "HTTPS已启用：https://$DOMAIN；证书续期定时任务已开启。"
