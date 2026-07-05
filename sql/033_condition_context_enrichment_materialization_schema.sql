-- N2 context enrichment row-level materialization additive schema draft.
-- Scope: N2-owned context materialization run table plus stock/index/board row tables.
-- Boundary: DDL only; no business row changes; no N3/N4/N5/N6 tables; no event infra tables.

BEGIN;

CREATE TABLE IF NOT EXISTS common_condition_context_enrichment_run (
  run_id TEXT PRIMARY KEY,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_trade_date TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  prev_trade_date TEXT,
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  policy_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  materialization_status TEXT NOT NULL DEFAULT 'planned'
    CHECK (materialization_status IN ('planned', 'running', 'passed', 'failed', 'blocked', 'rolled_back')),
  expected_context_rows INTEGER NOT NULL DEFAULT 0 CHECK (expected_context_rows >= 0),
  stock_rows INTEGER NOT NULL DEFAULT 0 CHECK (stock_rows >= 0),
  index_rows INTEGER NOT NULL DEFAULT 0 CHECK (index_rows >= 0),
  board_rows INTEGER NOT NULL DEFAULT 0 CHECK (board_rows >= 0),
  total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
  p0_count INTEGER NOT NULL DEFAULT 0 CHECK (p0_count >= 0),
  p1_count INTEGER NOT NULL DEFAULT 0 CHECK (p1_count >= 0),
  p2_count INTEGER NOT NULL DEFAULT 0 CHECK (p2_count >= 0),
  payload_artifact_path TEXT,
  payload_artifact_format TEXT NOT NULL DEFAULT 'jsonl' CHECK (payload_artifact_format IN ('jsonl')),
  payload_artifact_hash TEXT,
  rollback_sql_path TEXT,
  report_json_path TEXT,
  report_md_path TEXT,
  operator TEXT,
  confirmation_note TEXT,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (prev_trade_date IS NULL OR prev_trade_date ~ '^[0-9]{8}$'),
  CHECK (jsonb_typeof(policy_json) = 'object'),
  CHECK (jsonb_typeof(raw_json) = 'object'),
  CHECK (total_rows = stock_rows + index_rows + board_rows),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_common_condition_context_enrichment_run_source
ON common_condition_context_enrichment_run(source_condition_run_id, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_common_condition_context_enrichment_run_status
ON common_condition_context_enrichment_run(for_trade_date, materialization_status);

CREATE INDEX IF NOT EXISTS idx_common_condition_context_enrichment_run_policy
ON common_condition_context_enrichment_run(policy_hash, spec_version);

CREATE TABLE IF NOT EXISTS stock_condition_context_enrichment (
  stock_condition_context_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  materialization_run_id TEXT NOT NULL REFERENCES common_condition_context_enrichment_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  condition_key TEXT NOT NULL,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_scope_table TEXT NOT NULL DEFAULT 'stock_minute_target_scope',
  source_minute_target_scope_id BIGINT NOT NULL REFERENCES stock_minute_target_scope(stock_minute_target_scope_id),
  context_materialization_row_key TEXT NOT NULL,
  context_enrichment_version TEXT NOT NULL,
  context_enrichment_hash TEXT NOT NULL,
  period_trigger_baseline_json JSONB NOT NULL,
  trigger_amount_chain_baseline_json JSONB NOT NULL,
  trigger_amount_chain_formula_hash TEXT NOT NULL,
  FULL_prerequisite_trace_json JSONB NOT NULL,
  FULL_prerequisite_quality_status TEXT NOT NULL,
  HINT_prerequisite_trace_json JSONB NOT NULL,
  HINT_prerequisite_quality_status TEXT NOT NULL,
  freshness_status TEXT NOT NULL DEFAULT 'unknown',
  period_baseline_ready_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (context_materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (context_enrichment_hash ~ '^[0-9a-f]{64}$'),
  CHECK (trigger_amount_chain_formula_hash ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(period_trigger_baseline_json) = 'object'),
  CHECK (jsonb_typeof(trigger_amount_chain_baseline_json) = 'object'),
  CHECK (jsonb_typeof(FULL_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(HINT_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(period_baseline_ready_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  UNIQUE(materialization_run_id, context_materialization_row_key),
  UNIQUE(materialization_run_id, source_minute_target_scope_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_run
ON stock_condition_context_enrichment(materialization_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_source_run
ON stock_condition_context_enrichment(source_condition_run_id, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_identity
ON stock_condition_context_enrichment(stock_identity_key, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_condition
ON stock_condition_context_enrichment(condition_key, direction);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_hash
ON stock_condition_context_enrichment(context_enrichment_hash);

CREATE INDEX IF NOT EXISTS idx_stock_condition_context_enrichment_payload
ON stock_condition_context_enrichment USING GIN (payload_json);

CREATE TABLE IF NOT EXISTS index_condition_context_enrichment (
  index_condition_context_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  materialization_run_id TEXT NOT NULL REFERENCES common_condition_context_enrichment_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  condition_key TEXT NOT NULL,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_scope_table TEXT NOT NULL DEFAULT 'index_minute_target_scope',
  source_minute_target_scope_id BIGINT NOT NULL REFERENCES index_minute_target_scope(index_minute_target_scope_id),
  context_materialization_row_key TEXT NOT NULL,
  context_enrichment_version TEXT NOT NULL,
  context_enrichment_hash TEXT NOT NULL,
  period_trigger_baseline_json JSONB NOT NULL,
  trigger_amount_chain_baseline_json JSONB NOT NULL,
  trigger_amount_chain_formula_hash TEXT NOT NULL,
  FULL_prerequisite_trace_json JSONB NOT NULL,
  FULL_prerequisite_quality_status TEXT NOT NULL,
  HINT_prerequisite_trace_json JSONB NOT NULL,
  HINT_prerequisite_quality_status TEXT NOT NULL,
  freshness_status TEXT NOT NULL DEFAULT 'unknown',
  period_baseline_ready_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (context_materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (context_enrichment_hash ~ '^[0-9a-f]{64}$'),
  CHECK (trigger_amount_chain_formula_hash ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(period_trigger_baseline_json) = 'object'),
  CHECK (jsonb_typeof(trigger_amount_chain_baseline_json) = 'object'),
  CHECK (jsonb_typeof(FULL_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(HINT_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(period_baseline_ready_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  UNIQUE(materialization_run_id, context_materialization_row_key),
  UNIQUE(materialization_run_id, source_minute_target_scope_id)
);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_run
ON index_condition_context_enrichment(materialization_run_id);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_source_run
ON index_condition_context_enrichment(source_condition_run_id, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_identity
ON index_condition_context_enrichment(index_identity_key, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_condition
ON index_condition_context_enrichment(condition_key, direction);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_hash
ON index_condition_context_enrichment(context_enrichment_hash);

CREATE INDEX IF NOT EXISTS idx_index_condition_context_enrichment_payload
ON index_condition_context_enrichment USING GIN (payload_json);

CREATE TABLE IF NOT EXISTS board_condition_context_enrichment (
  board_condition_context_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  materialization_run_id TEXT NOT NULL REFERENCES common_condition_context_enrichment_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  condition_key TEXT NOT NULL,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_scope_table TEXT NOT NULL DEFAULT 'board_minute_target_scope',
  source_minute_target_scope_id BIGINT NOT NULL REFERENCES board_minute_target_scope(board_minute_target_scope_id),
  context_materialization_row_key TEXT NOT NULL,
  context_enrichment_version TEXT NOT NULL,
  context_enrichment_hash TEXT NOT NULL,
  period_trigger_baseline_json JSONB NOT NULL,
  trigger_amount_chain_baseline_json JSONB NOT NULL,
  trigger_amount_chain_formula_hash TEXT NOT NULL,
  FULL_prerequisite_trace_json JSONB NOT NULL,
  FULL_prerequisite_quality_status TEXT NOT NULL,
  HINT_prerequisite_trace_json JSONB NOT NULL,
  HINT_prerequisite_quality_status TEXT NOT NULL,
  freshness_status TEXT NOT NULL DEFAULT 'unknown',
  period_baseline_ready_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (context_materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (context_enrichment_hash ~ '^[0-9a-f]{64}$'),
  CHECK (trigger_amount_chain_formula_hash ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(period_trigger_baseline_json) = 'object'),
  CHECK (jsonb_typeof(trigger_amount_chain_baseline_json) = 'object'),
  CHECK (jsonb_typeof(FULL_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(HINT_prerequisite_trace_json) = 'object'),
  CHECK (jsonb_typeof(period_baseline_ready_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  UNIQUE(materialization_run_id, context_materialization_row_key),
  UNIQUE(materialization_run_id, source_minute_target_scope_id)
);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_run
ON board_condition_context_enrichment(materialization_run_id);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_source_run
ON board_condition_context_enrichment(source_condition_run_id, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_identity
ON board_condition_context_enrichment(board_identity_key, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_condition
ON board_condition_context_enrichment(condition_key, direction);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_hash
ON board_condition_context_enrichment(context_enrichment_hash);

CREATE INDEX IF NOT EXISTS idx_board_condition_context_enrichment_payload
ON board_condition_context_enrichment USING GIN (payload_json);

COMMIT;
