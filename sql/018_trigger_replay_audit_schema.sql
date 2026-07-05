-- A-share monitor v3 N4 C3 replay audit schema draft.
-- Stage: N4-C3 replay audit schema / execute contract design.
--
-- Boundary:
--   - Strictly additive schema only.
--   - Creates replay audit fact tables for N4 closed confirmation replay.
--   - Does not alter existing trigger tables.
--   - Does not write common_event_outbox, common_event_inbox, checkpoints,
--     common_trigger_match, or common_trigger_state.
--   - Does not emit TriggerMatched / TriggerPendingMarketData.

BEGIN;

CREATE TABLE IF NOT EXISTS stock_trigger_replay_audit (
  replay_audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  replay_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id) ON DELETE CASCADE,
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_projection_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_context_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_n5_action_run_id TEXT,
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  condition_key TEXT NOT NULL,
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY_30M_VOL', 'S_SELL_30M_SHRINK', 'BUY_HINT', 'SELL_HINT')),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  trigger_period TEXT NOT NULL CHECK (trigger_period = '30m'),
  trigger_bucket TEXT NOT NULL,
  replay_classification TEXT NOT NULL CHECK (replay_classification IN ('would_match', 'would_clear', 'would_change', 'unchanged', 'missing', 'not_ready')),
  replay_diff_type TEXT NOT NULL CHECK (replay_diff_type IN ('projection_not_matched_but_closed_matched', 'projection_matched_but_closed_not_matched', 'both_matched_but_quality_changed', 'unchanged', 'replay_blocked')),
  original_trigger_status TEXT NOT NULL CHECK (original_trigger_status IN ('matched', 'pending_market_data', 'cleared', 'inactive', 'missing', 'unknown')),
  closed_signal_status TEXT NOT NULL CHECK (closed_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  closed_signal_quality_status TEXT NOT NULL CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'unknown')),
  projection_signal_status TEXT CHECK (projection_signal_status IS NULL OR projection_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  original_match_id BIGINT,
  c3_event_id TEXT,
  c2b_enrichment_id BIGINT,
  comparison_key TEXT NOT NULL,
  diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'warning', 'missing', 'not_ready', 'failed', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(replay_run_id, comparison_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = stock_identity_key),
  CHECK (stock_identity_key = 'stock:' || exchange || ':' || code),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (condition_key ~ '^(BUY_HINT|SELL_HINT|BUY:.*|SELL:.*)$'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type NOT IN ('B_BUY_30M_VOL', 'BUY_HINT') OR direction = 'buy'),
  CHECK (signal_type NOT IN ('S_SELL_30M_SHRINK', 'SELL_HINT') OR direction = 'sell'),
  CHECK (trigger_bucket <> ''),
  CHECK (comparison_key <> '')
);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_run
ON stock_trigger_replay_audit(replay_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_c3_run
ON stock_trigger_replay_audit(source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_c2b_run
ON stock_trigger_replay_audit(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_classification
ON stock_trigger_replay_audit(replay_classification);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_diff_type
ON stock_trigger_replay_audit(replay_diff_type);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_signal
ON stock_trigger_replay_audit(signal_type);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_replay_audit_identity_trade
ON stock_trigger_replay_audit(identity_key, trade_date);

CREATE TABLE IF NOT EXISTS index_trigger_replay_audit (
  replay_audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  replay_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id) ON DELETE CASCADE,
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_projection_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_context_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_n5_action_run_id TEXT,
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ', 'CSI', 'CNI', 'SW', 'TDX', 'OTH', 'UNKNOWN')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  condition_key TEXT NOT NULL,
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY_30M_VOL', 'S_SELL_30M_SHRINK', 'BUY_HINT', 'SELL_HINT')),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  trigger_period TEXT NOT NULL CHECK (trigger_period = '30m'),
  trigger_bucket TEXT NOT NULL,
  replay_classification TEXT NOT NULL CHECK (replay_classification IN ('would_match', 'would_clear', 'would_change', 'unchanged', 'missing', 'not_ready')),
  replay_diff_type TEXT NOT NULL CHECK (replay_diff_type IN ('projection_not_matched_but_closed_matched', 'projection_matched_but_closed_not_matched', 'both_matched_but_quality_changed', 'unchanged', 'replay_blocked')),
  original_trigger_status TEXT NOT NULL CHECK (original_trigger_status IN ('matched', 'pending_market_data', 'cleared', 'inactive', 'missing', 'unknown')),
  closed_signal_status TEXT NOT NULL CHECK (closed_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  closed_signal_quality_status TEXT NOT NULL CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'unknown')),
  projection_signal_status TEXT CHECK (projection_signal_status IS NULL OR projection_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  original_match_id BIGINT,
  c3_event_id TEXT,
  c2b_enrichment_id BIGINT,
  comparison_key TEXT NOT NULL,
  diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'warning', 'missing', 'not_ready', 'failed', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(replay_run_id, comparison_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = index_identity_key),
  CHECK (index_identity_key = 'index:' || exchange || ':' || code),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (condition_key ~ '^(BUY_HINT|SELL_HINT|BUY:.*|SELL:.*)$'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type NOT IN ('B_BUY_30M_VOL', 'BUY_HINT') OR direction = 'buy'),
  CHECK (signal_type NOT IN ('S_SELL_30M_SHRINK', 'SELL_HINT') OR direction = 'sell'),
  CHECK (trigger_bucket <> ''),
  CHECK (comparison_key <> '')
);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_run
ON index_trigger_replay_audit(replay_run_id);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_c3_run
ON index_trigger_replay_audit(source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_c2b_run
ON index_trigger_replay_audit(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_classification
ON index_trigger_replay_audit(replay_classification);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_diff_type
ON index_trigger_replay_audit(replay_diff_type);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_signal
ON index_trigger_replay_audit(signal_type);

CREATE INDEX IF NOT EXISTS idx_index_trigger_replay_audit_identity_trade
ON index_trigger_replay_audit(identity_key, trade_date);

CREATE TABLE IF NOT EXISTS board_trigger_replay_audit (
  replay_audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  replay_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id) ON DELETE CASCADE,
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_projection_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_context_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_n5_action_run_id TEXT,
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  exchange TEXT NOT NULL CHECK (exchange IN ('SW', 'TDX', 'THS', 'UNKNOWN')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  condition_key TEXT NOT NULL,
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY_30M_VOL', 'S_SELL_30M_SHRINK', 'BUY_HINT', 'SELL_HINT')),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  trigger_period TEXT NOT NULL CHECK (trigger_period = '30m'),
  trigger_bucket TEXT NOT NULL,
  replay_classification TEXT NOT NULL CHECK (replay_classification IN ('would_match', 'would_clear', 'would_change', 'unchanged', 'missing', 'not_ready')),
  replay_diff_type TEXT NOT NULL CHECK (replay_diff_type IN ('projection_not_matched_but_closed_matched', 'projection_matched_but_closed_not_matched', 'both_matched_but_quality_changed', 'unchanged', 'replay_blocked')),
  original_trigger_status TEXT NOT NULL CHECK (original_trigger_status IN ('matched', 'pending_market_data', 'cleared', 'inactive', 'missing', 'unknown')),
  closed_signal_status TEXT NOT NULL CHECK (closed_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  closed_signal_quality_status TEXT NOT NULL CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'unknown')),
  projection_signal_status TEXT CHECK (projection_signal_status IS NULL OR projection_signal_status IN ('up_volume_expanding', 'up_volume_flat', 'up_volume_shrinking', 'down_volume_expanding', 'down_volume_flat', 'down_volume_shrinking', 'flat', 'unknown', 'missing')),
  original_match_id BIGINT,
  c3_event_id TEXT,
  c2b_enrichment_id BIGINT,
  comparison_key TEXT NOT NULL,
  diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'warning', 'missing', 'not_ready', 'failed', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(replay_run_id, comparison_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = board_identity_key),
  CHECK (board_identity_key = 'board:' || exchange || ':' || code),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (condition_key ~ '^(BUY_HINT|SELL_HINT|BUY:.*|SELL:.*)$'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type NOT IN ('B_BUY_30M_VOL', 'BUY_HINT') OR direction = 'buy'),
  CHECK (signal_type NOT IN ('S_SELL_30M_SHRINK', 'SELL_HINT') OR direction = 'sell'),
  CHECK (trigger_bucket <> ''),
  CHECK (comparison_key <> '')
);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_run
ON board_trigger_replay_audit(replay_run_id);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_c3_run
ON board_trigger_replay_audit(source_c3_run_id);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_c2b_run
ON board_trigger_replay_audit(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_classification
ON board_trigger_replay_audit(replay_classification);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_diff_type
ON board_trigger_replay_audit(replay_diff_type);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_signal
ON board_trigger_replay_audit(signal_type);

CREATE INDEX IF NOT EXISTS idx_board_trigger_replay_audit_identity_trade
ON board_trigger_replay_audit(identity_key, trade_date);

COMMIT;
