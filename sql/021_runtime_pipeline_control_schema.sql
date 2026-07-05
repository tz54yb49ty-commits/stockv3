-- Runtime pipeline control-plane schema draft.
-- Review before execution. This schema only stores orchestration state,
-- command registry entries, rollback registry entries, and timeline rows.
-- It must not modify N1-N6 execute contracts or execute any registered command.

CREATE TABLE IF NOT EXISTS runtime_pipeline_run (
    pipeline_run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    layer_role TEXT NOT NULL DEFAULT 'runtime_control',
    trade_date CHAR(8) NOT NULL,
    status TEXT NOT NULL,
    source_lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    dashboard_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL DEFAULT 'codex_runtime_control',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (layer_role = 'runtime_control'),
    CHECK (
        status IN (
            'PENDING',
            'WAIT_MANUAL_CONFIRM',
            'RUNNING',
            'PASSED',
            'FAILED',
            'BLOCKED',
            'ROLLBACK_READY',
            'ROLLED_BACK'
        )
    )
);

CREATE TABLE IF NOT EXISTS runtime_execute_command_registry (
    command_key TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL,
    target_layer_role TEXT NOT NULL,
    command_argv_json JSONB NOT NULL,
    command_description TEXT NOT NULL,
    requires_manual_confirm BOOLEAN NOT NULL DEFAULT true,
    modifies_execute_contract BOOLEAN NOT NULL DEFAULT false,
    starts_worker BOOLEAN NOT NULL DEFAULT false,
    executes_nightly_run BOOLEAN NOT NULL DEFAULT false,
    registry_only BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (registry_only = true),
    CHECK (modifies_execute_contract = false),
    CHECK (starts_worker = false)
);

CREATE TABLE IF NOT EXISTS runtime_rollback_registry (
    rollback_key TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL,
    target_layer_role TEXT NOT NULL,
    rollback_sql_path TEXT NOT NULL,
    rollback_description TEXT NOT NULL,
    executes_rollback BOOLEAN NOT NULL DEFAULT false,
    registry_only BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (registry_only = true),
    CHECK (executes_rollback = false)
);

CREATE TABLE IF NOT EXISTS runtime_pipeline_stage (
    pipeline_run_id TEXT NOT NULL REFERENCES runtime_pipeline_run(pipeline_run_id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL,
    stage_seq INTEGER NOT NULL,
    stage_title TEXT NOT NULL,
    target_layer_role TEXT NOT NULL,
    status TEXT NOT NULL,
    command_key TEXT NOT NULL REFERENCES runtime_execute_command_registry(command_key),
    rollback_key TEXT NOT NULL REFERENCES runtime_rollback_registry(rollback_key),
    dependencies_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    requires_manual_confirm BOOLEAN NOT NULL DEFAULT true,
    modifies_execute_contract BOOLEAN NOT NULL DEFAULT false,
    starts_worker BOOLEAN NOT NULL DEFAULT false,
    status_reason TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pipeline_run_id, stage_id),
    UNIQUE (pipeline_run_id, stage_seq),
    CHECK (
        status IN (
            'PENDING',
            'WAIT_MANUAL_CONFIRM',
            'RUNNING',
            'PASSED',
            'FAILED',
            'BLOCKED',
            'ROLLBACK_READY',
            'ROLLED_BACK'
        )
    ),
    CHECK (modifies_execute_contract = false),
    CHECK (starts_worker = false)
);

CREATE TABLE IF NOT EXISTS runtime_pipeline_timeline (
    timeline_id BIGSERIAL PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL REFERENCES runtime_pipeline_run(pipeline_run_id) ON DELETE CASCADE,
    stage_id TEXT,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    event_message TEXT NOT NULL,
    event_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        event_type IN (
            'PIPELINE_CREATED',
            'STAGE_REGISTERED',
            'STATUS_CHANGED',
            'MANUAL_CONFIRM_REQUESTED',
            'MANUAL_CONFIRM_GRANTED',
            'ROLLBACK_REGISTERED',
            'DASHBOARD_REFRESHED'
        )
    ),
    CHECK (
        to_status IN (
            'PENDING',
            'WAIT_MANUAL_CONFIRM',
            'RUNNING',
            'PASSED',
            'FAILED',
            'BLOCKED',
            'ROLLBACK_READY',
            'ROLLED_BACK'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_runtime_pipeline_stage_status
    ON runtime_pipeline_stage (pipeline_run_id, status, stage_seq);

CREATE INDEX IF NOT EXISTS idx_runtime_pipeline_timeline_run_created
    ON runtime_pipeline_timeline (pipeline_run_id, created_at, timeline_id);
