#!/usr/bin/env bash
# 在已解压发布包中运行。更新会短暂停服务；保留上个发布目录，不删除数据库/工作区。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_DIR="$(realpath "${1:-$SCRIPT_DIR/..}")"
DOMAIN="${2:-_}"
[[ "$(id -u)" == 0 ]] || { echo '请以sudo运行' >&2; exit 1; }
for command in docker mysql python3 java rsync runuser sha256sum flock; do command -v "$command" >/dev/null; done
[[ -f "$RELEASE_DIR/javabackend.jar" && -f "$RELEASE_DIR/web/index.html" && -f "$RELEASE_DIR/db/schema.sql" ]] || {
    echo '发布包缺少jar/前端/SQL' >&2; exit 1;
}
( cd "$RELEASE_DIR"; sha256sum -c SHA256SUMS >/dev/null )
[[ "$(docker info --format '{{.OSType}}')" == linux ]]
exec 9>/run/agent-deploy.lock
flock -n 9 || { echo '另一部署正在进行' >&2; exit 1; }
release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
DEST="/opt/agent/releases/$release_id"
install -d -o root -g root -m 0755 "$DEST"
rsync -a "$RELEASE_DIR/" "$DEST/"
# 压缩包Windows权限不可靠，标准化应用文件权限；运行用户不能修改程序。
chown -R root:root "$DEST"
chmod -R u=rwX,go=rX "$DEST"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --disable-pip-version-check -r "$DEST/python/requirements.txt"
export PYTHONPATH="$DEST/python"
"$DEST/venv/bin/python" "$DEST/deploy/server-settings.py" setup
# 镜像构建会联网；失败时不停止已有服务。国内网络失败会明确报错，不自动换不可信源。
candidate_image="python-agent-sandbox:build-$release_id"
docker build -t "$candidate_image" "$DEST/python/tools/terminal"
docker image inspect "$candidate_image" >/dev/null
# 两次命令共用真实容器，读写Office并验证端口/网络边界；不是只检查镜像存在。
runuser -u agent -- env PYTHONPATH="$DEST/python" "$DEST/venv/bin/python" "$DEST/deploy/verify-sandbox.py" --image "$candidate_image"
old_release=""
# -e要求目标真实存在；首次部署不存在的current不能被当作旧版本。
if [[ -e /opt/agent/current || -L /opt/agent/current ]]; then
    old_release="$(readlink -e /opt/agent/current)" || { echo '当前版本入口损坏，请先修复' >&2; exit 1; }
    [[ "$old_release" == /opt/agent/releases/* && -f "$old_release/javabackend.jar" ]] || {
        echo '当前版本不在受管发布目录，停止以免覆盖' >&2; exit 1;
    }
fi
old_image="$(docker image inspect python-agent-sandbox:1 --format '{{.Id}}' 2>/dev/null || true)"
previous_python="$(mktemp)"
previous_java="$(mktemp)"
previous_nginx="$(mktemp)"
[[ ! -f /etc/systemd/system/agent-python.service ]] || cp -p /etc/systemd/system/agent-python.service "$previous_python"
[[ ! -f /etc/systemd/system/agent-java.service ]] || cp -p /etc/systemd/system/agent-java.service "$previous_java"
[[ ! -f /etc/nginx/conf.d/agent.conf ]] || cp -p /etc/nginx/conf.d/agent.conf "$previous_nginx"
activated=false
rollback() {
    status=$?
    if [[ "$status" != 0 && "$activated" == true ]]; then
        echo '部署失败，尝试恢复旧应用入口；数据库和工作区不做回滚。' >&2
        systemctl stop agent-java.service agent-python.service 2>/dev/null || true
        if [[ -n "$old_release" && -d "$old_release" ]]; then
            ln -sfnT "$old_release" /opt/agent/current
            [[ -z "$old_image" ]] || docker tag "$old_image" python-agent-sandbox:1 || true
            [[ ! -s "$previous_python" ]] || cp -p "$previous_python" /etc/systemd/system/agent-python.service
            [[ ! -s "$previous_java" ]] || cp -p "$previous_java" /etc/systemd/system/agent-java.service
            [[ ! -s "$previous_nginx" ]] || cp -p "$previous_nginx" /etc/nginx/conf.d/agent.conf
            systemctl daemon-reload
            systemctl start agent-python.service agent-java.service || true
            if nginx -t; then systemctl reload nginx || true; fi
        fi
    fi
    rm -f "$previous_python" "$previous_java" "$previous_nginx"
    exit "$status"
}
trap rollback EXIT
activated=true
systemctl stop agent-java.service agent-python.service 2>/dev/null || true
"$DEST/venv/bin/python" "$DEST/deploy/server-settings.py" init-db --schema "$DEST/db/schema.sql"
docker tag "$candidate_image" python-agent-sandbox:1
ln -s "$DEST" /opt/agent/current.next
mv -Tf /opt/agent/current.next /opt/agent/current
cat > /etc/systemd/system/agent-python.service <<'UNIT'
[Unit]
Description=Agent Python (single worker, in-memory SSE)
After=network-online.target mysql.service docker.service
Requires=mysql.service docker.service
Wants=network-online.target
[Service]
Type=simple
User=agent
Group=agent
SupplementaryGroups=docker
WorkingDirectory=/opt/agent/current/python
Environment=AGENT_SERVICE_CONFIG_FILE=/etc/agent/python.toml
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/agent/current/venv/bin/python -m agent_service.run_server
Restart=on-failure
RestartSec=5
TimeoutStopSec=120
PrivateTmp=true
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/agent-java.service <<'UNIT'
[Unit]
Description=Agent Java backend
After=network-online.target mysql.service agent-python.service
Wants=network-online.target
[Service]
Type=simple
User=agent
Group=agent
WorkingDirectory=/opt/agent/current
EnvironmentFile=/etc/agent/java.env
ExecStart=/usr/bin/java -Xms256m -Xmx1536m -XX:+UseG1GC -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Shanghai -jar /opt/agent/current/javabackend.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=120
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
bash "$DEST/deploy/configure-nginx.sh" "$DOMAIN"
systemctl daemon-reload
systemctl enable agent-python agent-java
systemctl restart agent-python agent-java
echo "等待启动；发布目录：$DEST"
ready=false
for attempt in $(seq 1 45); do
    if "$DEST/venv/bin/python" "$DEST/deploy/server-settings.py" health >/dev/null 2>&1; then ready=true; break; fi
    sleep 2
done
if [[ "$ready" != true ]]; then
    echo '服务未就绪，部署失败；未宣称部署成功。请检查journalctl -u agent-python -u agent-java' >&2
    echo "上次发布保留在：${old_release:-无}；数据库与工作区未删除" >&2
    exit 1
fi
bash "$DEST/deploy/check-services.sh" "$DOMAIN"
activated=false
echo "部署检查通过：http://$DOMAIN（_表示可用公网IP测试，正式登录前请配置HTTPS）"
echo '更新前确保没有任务运行；旧发布目录不自动删除，后续按需人工清理。'
