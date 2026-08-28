-- Windows N3 post-close compressed previous-day minute context.
-- Stores one bounded row per N2 object; it does not persist raw 1m bars or
-- intraday N3/N4 runtime state.

BEGIN;

CREATE TABLE common_n3_previous_day_context_run (
  context_run_id TEXT PRIMARY KEY,
  source_condition_run_id TEXT NOT NULL
    REFERENCES common_condition_run(run_id) ON DELETE CASCADE,
  source_trade_date TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'completed', 'failed')),
  expected_stock_count INTEGER NOT NULL CHECK (expected_stock_count >= 0),
  expected_index_count INTEGER NOT NULL CHECK (expected_index_count >= 0),
  expected_board_count INTEGER NOT NULL CHECK (expected_board_count >= 0),
  terminal_stock_count INTEGER NOT NULL DEFAULT 0 CHECK (terminal_stock_count >= 0),
  terminal_index_count INTEGER NOT NULL DEFAULT 0 CHECK (terminal_index_count >= 0),
  terminal_board_count INTEGER NOT NULL DEFAULT 0 CHECK (terminal_board_count >= 0),
  result_summary JSONB NOT NULL DEFAULT '{}'::JSONB,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_condition_run_id),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date < for_trade_date),
  CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_common_n3_previous_day_context_run_date
ON common_n3_previous_day_context_run(for_trade_date, status);

CREATE TABLE stock_n3_previous_day_context (
  context_run_id TEXT NOT NULL
    REFERENCES common_n3_previous_day_context_run(context_run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL
    REFERENCES common_condition_run(run_id) ON DELETE CASCADE,
  source_trade_date TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  basis_trade_date TEXT,
  provider TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ready', 'partial', 'unavailable', 'failed')),
  minute_count INTEGER NOT NULL CHECK (minute_count BETWEEN 0 AND 240),
  tq_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (tq_minute_count BETWEEN 0 AND 240),
  eltdx_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (eltdx_minute_count BETWEEN 0 AND 240),
  cumulative_amounts NUMERIC[] NOT NULL DEFAULT ARRAY[]::NUMERIC[],
  windows_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  error_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(context_run_id, stock_identity_key),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (basis_trade_date IS NULL OR basis_trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%'),
  CHECK (jsonb_typeof(windows_json) = 'array'),
  CHECK (
    (status = 'ready' AND minute_count = 240
      AND cardinality(cumulative_amounts) = 240
      AND jsonb_array_length(windows_json) = 8)
    OR
    (status = 'partial' AND minute_count BETWEEN 1 AND 239
      AND cardinality(cumulative_amounts) = minute_count)
    OR
    (status IN ('unavailable', 'failed') AND minute_count = 0
      AND cardinality(cumulative_amounts) = 0
      AND jsonb_array_length(windows_json) = 0)
  )
);

CREATE INDEX idx_stock_n3_previous_day_context_lookup
ON stock_n3_previous_day_context(source_condition_run_id, for_trade_date, status);

CREATE TABLE index_n3_previous_day_context (
  context_run_id TEXT NOT NULL
    REFERENCES common_n3_previous_day_context_run(context_run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL
    REFERENCES common_condition_run(run_id) ON DELETE CASCADE,
  source_trade_date TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  basis_trade_date TEXT,
  provider TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ready', 'partial', 'unavailable', 'failed')),
  minute_count INTEGER NOT NULL CHECK (minute_count BETWEEN 0 AND 240),
  tq_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (tq_minute_count BETWEEN 0 AND 240),
  eltdx_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (eltdx_minute_count BETWEEN 0 AND 240),
  cumulative_amounts NUMERIC[] NOT NULL DEFAULT ARRAY[]::NUMERIC[],
  windows_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  error_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(context_run_id, index_identity_key),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (basis_trade_date IS NULL OR basis_trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%'),
  CHECK (jsonb_typeof(windows_json) = 'array'),
  CHECK (
    (status = 'ready' AND minute_count = 240
      AND cardinality(cumulative_amounts) = 240
      AND jsonb_array_length(windows_json) = 8)
    OR
    (status = 'partial' AND minute_count BETWEEN 1 AND 239
      AND cardinality(cumulative_amounts) = minute_count)
    OR
    (status IN ('unavailable', 'failed') AND minute_count = 0
      AND cardinality(cumulative_amounts) = 0
      AND jsonb_array_length(windows_json) = 0)
  )
);

CREATE INDEX idx_index_n3_previous_day_context_lookup
ON index_n3_previous_day_context(source_condition_run_id, for_trade_date, status);

CREATE TABLE board_n3_previous_day_context (
  context_run_id TEXT NOT NULL
    REFERENCES common_n3_previous_day_context_run(context_run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL
    REFERENCES common_condition_run(run_id) ON DELETE CASCADE,
  source_trade_date TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  basis_trade_date TEXT,
  provider TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ready', 'partial', 'unavailable', 'failed')),
  minute_count INTEGER NOT NULL CHECK (minute_count BETWEEN 0 AND 240),
  tq_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (tq_minute_count BETWEEN 0 AND 240),
  eltdx_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (eltdx_minute_count BETWEEN 0 AND 240),
  cumulative_amounts NUMERIC[] NOT NULL DEFAULT ARRAY[]::NUMERIC[],
  windows_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  error_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(context_run_id, board_identity_key),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (basis_trade_date IS NULL OR basis_trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%'),
  CHECK (jsonb_typeof(windows_json) = 'array'),
  CHECK (
    (status = 'ready' AND minute_count = 240
      AND cardinality(cumulative_amounts) = 240
      AND jsonb_array_length(windows_json) = 8)
    OR
    (status = 'partial' AND minute_count BETWEEN 1 AND 239
      AND cardinality(cumulative_amounts) = minute_count)
    OR
    (status IN ('unavailable', 'failed') AND minute_count = 0
      AND cardinality(cumulative_amounts) = 0
      AND jsonb_array_length(windows_json) = 0)
  )
);

CREATE INDEX idx_board_n3_previous_day_context_lookup
ON board_n3_previous_day_context(source_condition_run_id, for_trade_date, status);

GRANT SELECT, INSERT, UPDATE
ON common_n3_previous_day_context_run
TO ashare_v3_user;

GRANT SELECT, INSERT
ON stock_n3_previous_day_context,
   index_n3_previous_day_context,
   board_n3_previous_day_context
TO ashare_v3_user;

COMMIT;
