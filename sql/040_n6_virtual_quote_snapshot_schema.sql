-- N6-owned virtual-account minute quote persistence (additive draft).
-- Do not execute without a separate migration gate.
-- This schema does not alter N3 facts/events, N2-N5 tables, web routes, or trading state.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_quote_run (
  quote_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL CHECK (principal_id > 0),
  quote_minute TIMESTAMPTZ NOT NULL,
  run_status TEXT NOT NULL
    CHECK (run_status IN ('no_scope', 'passed', 'partial', 'failed')),
  scoped_identity_count INTEGER NOT NULL CHECK (scoped_identity_count >= 0),
  passed_count INTEGER NOT NULL CHECK (passed_count >= 0),
  not_ready_count INTEGER NOT NULL CHECK (not_ready_count >= 0),
  inserted_snapshot_count INTEGER NOT NULL CHECK (inserted_snapshot_count >= 0),
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ NOT NULL,
  CHECK (date_trunc('minute', quote_minute) = quote_minute),
  CHECK (completed_at >= started_at),
  CHECK (scoped_identity_count = passed_count + not_ready_count),
  CHECK (inserted_snapshot_count <= scoped_identity_count),
  CHECK (
    (run_status = 'no_scope'
      AND scoped_identity_count = 0
      AND passed_count = 0
      AND not_ready_count = 0
      AND inserted_snapshot_count = 0)
    OR
    (run_status = 'passed'
      AND scoped_identity_count > 0
      AND passed_count = scoped_identity_count
      AND not_ready_count = 0)
    OR
    (run_status = 'partial'
      AND passed_count > 0
      AND not_ready_count > 0)
    OR
    (run_status = 'failed'
      AND scoped_identity_count > 0
      AND passed_count = 0
      AND not_ready_count = scoped_identity_count)
  ),
  UNIQUE (principal_id, quote_minute)
);

CREATE TABLE IF NOT EXISTS n6_virtual_quote_snapshot (
  virtual_quote_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  stock_code TEXT NOT NULL CHECK (stock_code ~ '^[0-9]{6}$'),
  quote_minute TIMESTAMPTZ NOT NULL,
  provider_batch_id UUID NOT NULL,
  provider_contract_version TEXT NOT NULL CHECK (provider_contract_version = '1.0.0'),
  source_adapter TEXT NOT NULL CHECK (source_adapter = 'mootdx.std'),
  source_version TEXT NOT NULL CHECK (source_version <> ''),
  source_time_semantics TEXT NOT NULL
    CHECK (source_time_semantics = 'provider_intraday_time_without_trade_date'),
  requested_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ NOT NULL,
  batch_status TEXT NOT NULL CHECK (batch_status IN ('passed', 'partial', 'failed')),
  market INTEGER,
  current_price NUMERIC(24, 8),
  last_close NUMERIC(24, 8),
  day_open NUMERIC(24, 8),
  day_high NUMERIC(24, 8),
  day_low NUMERIC(24, 8),
  source_time_text TEXT,
  fetched_at TIMESTAMPTZ NOT NULL,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'not_ready')),
  quality_reason TEXT NOT NULL CHECK (quality_reason IN (
    'ok',
    'missing',
    'identity_mismatch',
    'invalid_price',
    'invalid_source_time',
    'provider_error',
    'unsupported_exchange'
  )),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (identity_key = 'stock:' || exchange || ':' || stock_code),
  CHECK (date_trunc('minute', quote_minute) = quote_minute),
  CHECK (completed_at >= requested_at),
  CHECK (
    (
      quality_status = 'passed'
      AND quality_reason = 'ok'
      AND current_price > 0
      AND day_low > 0
      AND source_time_text IS NOT NULL
      AND ((exchange = 'SH' AND market = 1) OR (exchange = 'SZ' AND market = 0))
    )
    OR
    (
      quality_status = 'not_ready'
      AND quality_reason <> 'ok'
      AND current_price IS NULL
      AND last_close IS NULL
      AND day_open IS NULL
      AND day_high IS NULL
      AND day_low IS NULL
      AND source_time_text IS NULL
    )
  ),
  UNIQUE (identity_key, quote_minute)
);

CREATE INDEX IF NOT EXISTS idx_040_n6_virtual_quote_snapshot_minute
ON n6_virtual_quote_snapshot(quote_minute DESC, identity_key);

CREATE OR REPLACE VIEW v_n6_virtual_quote_latest AS
SELECT DISTINCT ON (identity_key)
       virtual_quote_snapshot_id,
       identity_key,
       exchange,
       stock_code,
       quote_minute,
       provider_batch_id,
       provider_contract_version,
       source_adapter,
       source_version,
       source_time_semantics,
       requested_at,
       completed_at,
       batch_status,
       market,
       current_price,
       last_close,
       day_open,
       day_high,
       day_low,
       source_time_text,
       fetched_at,
       quality_status,
       quality_reason,
       created_at
FROM n6_virtual_quote_snapshot
ORDER BY identity_key, quote_minute DESC, virtual_quote_snapshot_id DESC;

COMMIT;
