#!/usr/bin/env bash
# 首次准备专用Ubuntu服务器；可重复运行，不修改SSH登录规则，不重置数据库。
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo '请以sudo运行' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || { echo '本脚本针对Ubuntu 22.04' >&2; exit 1; }
[[ "$(uname -m)" == x86_64 ]] || { echo '请选择x86_64服务器' >&2; exit 1; }
memory_mb="$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
disk_kb="$(df --output=avail / | tail -1)"
(( memory_mb >= 3800 && disk_kb >= 10485760 )) || { echo '至少4G内存和10G空闲磁盘' >&2; exit 1; }
printf 'Ubuntu %s / %s CPU / %s MiB内存\n' "$VERSION_ID" "$(nproc)" "$memory_mb"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg git rsync unzip openssl nginx mysql-server \
    python3 python3-venv python3-pip openjdk-21-jre-headless ufw
java -version
# 当前Python服务依赖支持Ubuntu22.04自带的Python3.10，不增加第三方Python源。
python3 -c 'import sys; assert sys.version_info >= (3, 10)'
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl --connect-timeout 15 --max-time 120 -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
        "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
fi
systemctl enable --now docker mysql nginx
docker info --format '{{.OSType}}' | grep -qx linux
if ! id agent >/dev/null 2>&1; then useradd --system --create-home --shell /usr/sbin/nologin agent; fi
usermod -aG docker agent
# 应用代码root只读，只有项目工作区由agent写；docker组仍有很高权限，不能对公网暴露Docker。
install -d -o root -g root -m 0755 /opt/agent /opt/agent/releases /var/www/agent
install -d -o agent -g agent -m 0750 /srv/agent/workspaces
install -d -o root -g agent -m 0750 /etc/agent
# MySQL仅回环访问；修改专用配置，不覆盖其他MySQL配置。
printf '[mysqld]\nbind-address=127.0.0.1\nmysqlx-bind-address=127.0.0.1\n' > /etc/mysql/mysql.conf.d/agent-network.cnf
systemctl restart mysql
# 不启用UFW、不改变SSH规则以免断开远程连接；仍需控制台安全组限制端口。
ufw allow 80/tcp
ufw allow 443/tcp
echo '准备完成。请在阿里云安全组仅放行你的SSH端口、80、443；3306/8000/8080不要放行。'
echo '本脚本没有启用UFW或禁用密码登录；确认SSH密钥可用后再单独处理登录加固。'
