-- A-share monitor v3 common event infrastructure schema draft.
-- Stage N3-1 only: review before running in any PostgreSQL database.
-- Boundary: common event ledger/outbox/inbox/checkpoint metadata only;
-- no market data pull, no market data fact writes, no trigger/action/user
-- business objects, and no worker state.

BEGIN;

CREATE TABLE common_event_ledger (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board', 'common')),
  identity_key TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N3_market_data', 'N4_trigger', 'N5_action', 'N6_user')),
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  first_outbox_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (event_type !~ '^User'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (event_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (source_run_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> ''),
  CHECK (
    source_layer <> 'N3_market_data'
    OR event_type IN (
      'MarketSnapshotUpdated',
      'MinuteBarClosed',
      'MinuteBarCorrected',
      'MarketDataDelayed',
      'MarketDataMissing',
      'MarketDisplaySnapshotUpdated'
    )
  )
);

CREATE UNIQUE INDEX uq_common_event_ledger_dedup
ON common_event_ledger(source_layer, event_type, source_run_id, dedup_key, event_schema_version);

CREATE INDEX idx_common_event_ledger_partition
ON common_event_ledger(source_layer, partition_key, event_time, event_id);

CREATE INDEX idx_common_event_ledger_trade_date
ON common_event_ledger(trade_date, event_type, asset_kind);

CREATE TABLE common_event_outbox (
  outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board', 'common')),
  identity_key TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N3_market_data', 'N4_trigger', 'N5_action', 'N6_user')),
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivering', 'delivered', 'failed', 'dead_letter')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TIMESTAMPTZ,
  locked_by TEXT,
  locked_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_common_event_outbox_event_id UNIQUE(event_id),
  CONSTRAINT uq_common_event_outbox_dedup UNIQUE(source_layer, event_type, source_run_id, dedup_key, event_schema_version),
  CHECK (event_type !~ '^User'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (event_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (source_run_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> ''),
  CHECK (
    source_layer <> 'N3_market_data'
    OR event_type IN (
      'MarketSnapshotUpdated',
      'MinuteBarClosed',
      'MinuteBarCorrected',
      'MarketDataDelayed',
      'MarketDataMissing',
      'MarketDisplaySnapshotUpdated'
    )
  )
);

CREATE INDEX idx_common_event_outbox_pending
ON common_event_outbox(status, next_attempt_at NULLS FIRST, created_at, outbox_id);

CREATE INDEX idx_common_event_outbox_partition
ON common_event_outbox(source_layer, partition_key, event_time, event_id);

CREATE TABLE common_event_inbox (
  inbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  consumer_name TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  source_layer TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'processing', 'processed', 'failed', 'skipped')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  last_error TEXT,
  raw_json JSONB,
  CONSTRAINT uq_common_event_inbox_consumer_event UNIQUE(consumer_name, event_id),
  CONSTRAINT uq_common_event_inbox_consumer_dedup UNIQUE(consumer_name, source_layer, event_type, source_run_id, dedup_key, event_schema_version),
  CHECK (consumer_name <> ''),
  CHECK (event_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> '')
);

CREATE INDEX idx_common_event_inbox_status
ON common_event_inbox(consumer_name, status, received_at);

CREATE TABLE common_event_consumer_checkpoint (
  consumer_name TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  source_layer TEXT NOT NULL,
  last_event_id TEXT,
  last_event_time TIMESTAMPTZ,
  last_outbox_id BIGINT,
  checkpoint_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_name, partition_key, source_layer),
  CHECK (consumer_name <> ''),
  CHECK (partition_key <> '')
);

CREATE TABLE common_event_delivery_attempt (
  delivery_attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL,
  outbox_id BIGINT REFERENCES common_event_outbox(outbox_id) ON DELETE SET NULL,
  consumer_name TEXT,
  attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
  status TEXT NOT NULL CHECK (status IN ('started', 'delivered', 'failed', 'skipped')),
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  raw_json JSONB,
  CHECK (event_id <> ''),
  CHECK (finished_at IS NULL OR finished_at >= attempted_at)
);

CREATE INDEX idx_common_event_delivery_attempt_event
ON common_event_delivery_attempt(event_id, attempted_at DESC);

CREATE INDEX idx_common_event_delivery_attempt_consumer
ON common_event_delivery_attempt(consumer_name, status, attempted_at DESC);

COMMIT;
