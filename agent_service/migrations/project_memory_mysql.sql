-- 已有 MySQL agent_memory 的一次性迁移；新数据库不需要运行。
-- 先停止所有 Python 写入进程，并完成数据库备份。
-- 请逐段执行并核对结果，任意语句失败都必须停止，不要使用忽略错误继续执行的选项。
-- MySQL DDL 会隐式提交，不能用一个 BEGIN/ROLLBACK 包住全部步骤。

-- 1. 确认来源表为旧版十列结构，状态只有 ACTIVE、SUPERSEDED。
SHOW COLUMNS FROM agent_memory;
SELECT status, COUNT(*) FROM agent_memory GROUP BY status;
-- 若出现其他状态或结构不符，请停止；不要猜测哪些记录应当丢弃。

-- 2. 建立精简的新表；故意不加 IF NOT EXISTS，防止覆盖上次遗留的迁移结果。
CREATE TABLE agent_memory_project_new (
    memory_id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    source_run_id VARCHAR(36) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    KEY idx_agent_memory_project_updated (project_id, updated_at, memory_id),
    CONSTRAINT fk_agent_memory_project_source_run FOREIGN KEY (source_run_id)
        REFERENCES agent_run(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 一条 INSERT 原子复制全部有效记忆；旧的被替代记录留在原表，不重新生效。
INSERT INTO agent_memory_project_new
    (memory_id, project_id, content, source_run_id, updated_at)
SELECT memory_id, project_id, content, source_run_id, updated_at
FROM agent_memory WHERE status = 'ACTIVE';
COMMIT;

-- 4. 两个数量必须相等，字段差异必须为 0，再执行下一段。
SELECT
    (SELECT COUNT(*) FROM agent_memory WHERE status = 'ACTIVE') AS expected_count,
    (SELECT COUNT(*) FROM agent_memory_project_new) AS copied_count;
SELECT COUNT(*) AS different_rows
FROM agent_memory AS old
LEFT JOIN agent_memory_project_new AS new ON old.memory_id = new.memory_id
WHERE old.status = 'ACTIVE' AND (
    new.memory_id IS NULL OR
    NOT (BINARY old.project_id <=> BINARY new.project_id) OR
    NOT (BINARY old.content <=> BINARY new.content) OR
    NOT (BINARY old.source_run_id <=> BINARY new.source_run_id) OR
    NOT (old.updated_at <=> new.updated_at)
);

-- 5. 同一条 RENAME 完成切换；备份名已被占用时失败，不覆盖已有备份。
RENAME TABLE agent_memory TO agent_memory_legacy_backup,
             agent_memory_project_new TO agent_memory;

-- 原表全部数据仍在 agent_memory_legacy_backup；运行时不读取该表。
-- 核对迁移和新版本读写成功后，由维护者决定何时删除备份，不在此脚本自动删除。
