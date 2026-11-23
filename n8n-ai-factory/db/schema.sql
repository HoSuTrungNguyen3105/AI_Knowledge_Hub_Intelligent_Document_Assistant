-- AI Agent Factory — PostgreSQL schema
-- Applied automatically by docker-compose (mounted into
-- /docker-entrypoint-initdb.d) on first database initialisation.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS projects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT,
    mode         TEXT NOT NULL DEFAULT 'full'
                 CHECK (mode IN ('full', 'module', 'existing')),
    module_name  TEXT,
    requirement  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'PENDING'
                 CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_ISSUES', 'FAILED')),
    models       JSONB NOT NULL DEFAULT '{}'::jsonb,
    zip_url      TEXT,
    summary      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_key    TEXT,
    agent_id    TEXT NOT NULL,
    title       TEXT,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'RETRYING')),
    depends_on  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_id          TEXT,
    agent_id         TEXT NOT NULL,
    agent_name       TEXT,
    model            TEXT,
    status           TEXT NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'RETRYING')),
    input_context    JSONB,
    output           JSONB,
    error            TEXT,
    prompt_tokens    INTEGER,
    completion_tokens INTEGER,
    total_tokens     INTEGER,
    cost_usd         NUMERIC(12, 6),
    duration_ms      INTEGER,
    attempt          INTEGER NOT NULL DEFAULT 1,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'source_file',
    path        TEXT NOT NULL,
    size_bytes  BIGINT,
    sha256      TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qa_reviews (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    attempt          INTEGER NOT NULL DEFAULT 0,
    build_ok         BOOLEAN,
    qa_verdict       TEXT,
    reviewer_verdict TEXT,
    passed           BOOLEAN,
    issues           JSONB NOT NULL DEFAULT '[]'::jsonb,
    logs             JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_project ON agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(project_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_qa_reviews_project ON qa_reviews(project_id);
