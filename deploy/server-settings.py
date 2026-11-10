"""服务器侧部署辅助：只写专用配置目录；密码不放命令参数，不导入用户项目代码。

由deploy-release.sh使用服务器venv调用。setup创建配置，init-db按现有Java/Python
建表定义初始化，health只做只读验收。不是业务接口或数据库迁移系统。
"""
import argparse
import getpass
import grp
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.request

CONFIG = Path("/etc/agent/python.toml")
JAVA_ENV = Path("/etc/agent/java.env")
TABLES = {
    "user": {"user_id", "username", "password_hash", "status", "created_at", "updated_at", "last_login_at"},
    "auth_session": {"session_id", "user_id", "token_hash", "expires_at", "revoked_at", "created_at"},
    "project": {"id", "name", "description", "owner_id", "created_at", "updated_at"},
    "conversation": {"id", "project_id", "title", "status", "created_at", "updated_at"},
    "agent_task": {"id", "conversation_id", "python_run_id", "created_at"},
    "agent_run": {"run_id", "project_id", "conversation_id", "prompt", "context_json", "status",
                  "result", "error", "created_at", "started_at", "finished_at"},
    "agent_run_message": {"id", "run_id", "sequence_no", "message_type", "content_json", "created_at"},
    "agent_memory": {"memory_id", "project_id", "content", "source_run_id", "updated_at"},
}


def load_settings():
    from agent_service.config import Settings
    return Settings.from_environment(CONFIG)


def setup():
    """首次交互填写模型凭据，重复部署沿用；不执行或source用户配置内容。"""
    if CONFIG.exists() != JAVA_ENV.exists():
        raise RuntimeError("python.toml/java.env只有一个存在，请人工检查，不覆盖已有配置")
    if CONFIG.exists():
        settings = load_settings()
        if settings.execution_mode != "cloud" or not settings.sandbox_enabled:
            raise RuntimeError("正式部署必须为cloud且sandbox.enabled=true")
        if settings.terminal_mode != "disabled" or settings.terminal_allow_cloud_host_test:
            raise RuntimeError("正式部署禁止宿主终端测试开关")
        if not settings.llm_api_key or not settings.llm_model_id or not settings.internal_token:
            raise RuntimeError("服务器配置缺少模型凭据、模型名或内部令牌")
        print("沿用 /etc/agent/python.toml 和 java.env，不输出凭据")
        return
    if not sys.stdin.isatty():
        raise RuntimeError("首次部署需要交互终端填写模型参数，请通过SSH登录后运行")
    model = input("模型名称（按模型服务商控制台填写）：").strip()
    base = input("模型API地址（例如 https://api.deepseek.com）：").strip()
    key = getpass.getpass("模型API密钥（输入不显示）：").strip()
    web_key = getpass.getpass("Tavily搜索密钥（可留空，输入不显示）：").strip()
    if not model or not key or not base.startswith("https://"):
        raise ValueError("必须填写模型名称、API密钥和HTTPS API地址")
    token, password = secrets.token_hex(32), secrets.token_hex(24)
    # JSON字符串与这里使用的TOML基础字符串兼容，避免引号/换行破坏配置。
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    source = f"""
[service]
name = "python-agent-service"
internal_token = {quote(token)}
[llm]
model_id = {quote(model)}
api_key = {quote(key)}
base_url = {quote(base)}
timeout_seconds = 200.0
[web]
api_key = {quote(web_key)}
[mysql]
host = "127.0.0.1"
port = 3306
user = "agent_app"
password = {quote(password)}
database = "agent_javabackend"
pool_size = 5
[storage]
backend = "mysql"
[runtime]
mode = "cloud"
max_agent_steps = 50
max_concurrent_runs = 2
[cloud]
workspace_root = "/srv/agent/workspaces"
[sandbox]
enabled = true
image = "python-agent-sandbox:1"
timeout_seconds = 60
memory_mb = 512
cpus = 1.0
pids = 64
disk_mb = 256
max_output_bytes = 65536
max_concurrent = 1
[terminal]
mode = "disabled"
allow_cloud_host_test = false
"""
    java = f"""SPRING_PROFILES_ACTIVE=cloud
SERVER_ADDRESS=127.0.0.1
SERVER_PORT=8080
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USERNAME=agent_app
MYSQL_PASSWORD={password}
MYSQL_DATABASE=agent_javabackend
AGENT_SERVICE_BASE_URL=http://127.0.0.1:8000
AGENT_SERVICE_INTERNAL_TOKEN={token}
DB_MAX_POOL_SIZE=10
DB_MIN_IDLE=2
SPRING_SQL_INIT_MODE=never
"""
    CONFIG.parent.mkdir(mode=0o750, exist_ok=True)
    os.chown(CONFIG.parent, 0, grp.getgrnam("agent").gr_gid)
    for path, text, mode in ((CONFIG, source, 0o640), (JAVA_ENV, java, 0o600)):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.chown(path, 0, grp.getgrnam("agent").gr_gid)
    print("已生成服务器独立配置；未使用本机密钥。上下文预算默认要求模型至少256k。")


def check_tables(connection):
    """确认八张表的必需列都存在；旧表不自动迁移或清空。"""
    cursor = connection.cursor()
    try:
        for table, expected in TABLES.items():
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s", (table,)
            )
            actual = {row[0] for row in cursor.fetchall()}
            if not expected <= actual:
                raise RuntimeError(f"表{table}缺少字段{sorted(expected - actual)}；停止，不自动迁移")
    finally:
        cursor.close()


def initialize(schema):
    import mysql.connector
    from agent_service.storage.repository import MySQLRunRepository
    settings = load_settings()
    if settings.mysql_database != "agent_javabackend" or settings.mysql_user != "agent_app":
        raise RuntimeError("脚本仅管理专用数据库agent_javabackend和agent_app账号")
    connection = mysql.connector.connect(user="root", unix_socket="/var/run/mysqld/mysqld.sock")
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS agent_javabackend "
                       "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        # 密码由驱动参数化处理，不拼接SQL，不出现在进程参数或日志。
        cursor.execute("CREATE USER IF NOT EXISTS 'agent_app'@'127.0.0.1' IDENTIFIED BY %s",
                       (settings.mysql_password,))
        cursor.execute("ALTER USER 'agent_app'@'127.0.0.1' IDENTIFIED BY %s",
                       (settings.mysql_password,))
        cursor.execute("GRANT ALL PRIVILEGES ON agent_javabackend.* TO 'agent_app'@'127.0.0.1'")
        cursor.execute("USE agent_javabackend")
        for statement in schema.read_text(encoding="utf-8-sig").split(";"):
            if statement.strip():
                cursor.execute(statement)
        connection.commit()
        cursor.close()
    finally:
        connection.close()
    repository = MySQLRunRepository(settings)
    try:
        repository.initialize()
    finally:
        repository.close()
    connection = mysql.connector.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password, database=settings.mysql_database)
    try:
        check_tables(connection)
    finally:
        connection.close()
    print("MySQL八张表初始化及字段检查通过；未删除已有数据")


def health():
    """带令牌验证Python；Java用已存在的受保护接口，401才表示鉴权正常。"""
    import mysql.connector
    settings = load_settings()
    request = urllib.request.Request("http://127.0.0.1:8000/api/internal/health",
        headers={"X-Service-Token": settings.internal_token})
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("Python health失败")
    try:
        urllib.request.urlopen("http://127.0.0.1:8080/api/projects", timeout=5)
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise RuntimeError(f"Java鉴权检查返回{error.code}，应为401") from error
    else:
        raise RuntimeError("Java未拒绝无凭据项目请求，检查cloud配置")
    connection = mysql.connector.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password, database=settings.mysql_database)
    try:
        check_tables(connection)
    finally:
        connection.close()
    print("Python令牌、Java鉴权和MySQL八张表检查通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "init-db", "health"])
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise RuntimeError("请以sudo运行服务器部署辅助")
        if args.action == "setup":
            setup()
        elif args.action == "init-db":
            if not args.schema:
                raise RuntimeError("缺少--schema")
            initialize(args.schema)
        else:
            health()
    except Exception as error:
        # 驱动和网络错误可能含凭据或内部响应，避免直接回显原始异常。
        if isinstance(error, RuntimeError):
            print(f"部署检查失败：{error}", file=sys.stderr)
        else:
            print(f"部署检查失败：{type(error).__name__}；请核对配置、服务状态和数据库结构", file=sys.stderr)
        raise SystemExit(1)
