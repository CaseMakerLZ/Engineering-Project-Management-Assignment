PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    local_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES project(id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_project
    ON conversation(project_id, created_at);

CREATE TABLE IF NOT EXISTS agent_run (
    run_id TEXT PRIMARY KEY,
    project_id TEXT,
    conversation_id TEXT,
    prompt TEXT NOT NULL,
    context_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_task (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    python_run_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversation(id),
    FOREIGN KEY (python_run_id) REFERENCES agent_run(run_id)
);

CREATE INDEX IF NOT EXISTS idx_task_conversation
    ON agent_task(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS agent_run_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    content_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence_no),
    FOREIGN KEY(run_id) REFERENCES agent_run(run_id)
);
