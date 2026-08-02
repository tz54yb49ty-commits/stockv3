-- Add the N6-owned current trigger-status episode read model.
-- OFFLINE REVIEWED MIGRATION: execute only in a later independent N6_user gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('089_n6_trigger_status_current_v1', 0)
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '089 owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regclass('public.common_event_outbox') IS NULL
     OR pg_catalog.to_regclass('public.common_event_inbox') IS NULL
     OR pg_catalog.to_regclass('public.common_event_consumer_checkpoint') IS NULL THEN
    RAISE EXCEPTION '089 canonical event infrastructure missing';
  END IF;
  IF NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_btrack_web'
     ) THEN
    RAISE EXCEPTION '089 n6_btrack_web role missing';
  END IF;
  IF pg_catalog.to_regclass('public.n6_trigger_status_current') IS NOT NULL THEN
    RAISE EXCEPTION '089 trigger status object already exists';
  END IF;
END
$preflight$;

CREATE TABLE public.n6_trigger_status_current (
  trigger_status_episode_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contract_version text NOT NULL,
  consumer_name text NOT NULL,
  projection_run_id text NOT NULL,
  trade_date text NOT NULL,
  tracking_state_key text NOT NULL,
  entry_trigger_event_id text NOT NULL,
  action_eligible_event_id text NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  asset_code text NOT NULL,
  asset_name text NOT NULL,
  direction text NOT NULL,
  signal_type text NOT NULL,
  condition_key text NOT NULL,
  trigger_time timestamptz NOT NULL,
  trigger_price numeric(24,6),
  trigger_period text,
  triggered_periods text[] NOT NULL DEFAULT ARRAY[]::text[],
  action_eligible_outbox_id bigint NOT NULL,
  last_status_outbox_id bigint NOT NULL,
  last_event_id text NOT NULL,
  last_event_type text NOT NULL,
  source_action_run_id text NOT NULL,
  source_trigger_event_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  CONSTRAINT uq_089_n6_trigger_status_episode UNIQUE (
    trade_date, asset_kind, identity_key, direction, signal_type,
    condition_key, entry_trigger_event_id
  ),
  CONSTRAINT uq_089_n6_trigger_status_state_entry UNIQUE (
    tracking_state_key, entry_trigger_event_id
  ),
  CONSTRAINT ck_089_n6_trigger_status_contract CHECK (
    contract_version = 'N5-N6-trigger-status-forward-v1'
  ),
  CONSTRAINT ck_089_n6_trigger_status_consumer CHECK (
    consumer_name = 'n6_trigger_status_projection_v1'
  ),
  CONSTRAINT ck_089_n6_trigger_status_trade_date CHECK (
    trade_date ~ '^[0-9]{8}$'
  ),
  CONSTRAINT ck_089_n6_trigger_status_asset_kind CHECK (
    asset_kind IN ('stock', 'index', 'board')
  ),
  CONSTRAINT ck_089_n6_trigger_status_direction CHECK (
    direction IN ('buy', 'sell')
  ),
  CONSTRAINT ck_089_n6_trigger_status_signal_type CHECK (
    signal_type IN ('B_BUY', 'S_SELL')
  ),
  CONSTRAINT ck_089_n6_trigger_status_period CHECK (
    trigger_period IS NULL OR trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')
  ),
  CONSTRAINT ck_089_n6_trigger_status_periods CHECK (
    triggered_periods <@ ARRAY['Y', 'Q', 'M', 'W', 'D']::text[]
  ),
  CONSTRAINT ck_089_n6_trigger_status_watermarks CHECK (
    action_eligible_outbox_id > 0
    AND last_status_outbox_id >= action_eligible_outbox_id
  ),
  CONSTRAINT ck_089_n6_trigger_status_event_type CHECK (
    last_event_type IN ('ActionEligible', 'TriggerStatusUpdated')
  ),
  CONSTRAINT ck_089_n6_trigger_status_timestamps CHECK (updated_at >= created_at)
);

CREATE INDEX idx_089_n6_trigger_status_public_group
ON public.n6_trigger_status_current(
  trade_date, asset_kind, identity_key, direction,
  last_status_outbox_id DESC, entry_trigger_event_id
);

COMMENT ON TABLE public.n6_trigger_status_current IS
  'migration=089_n6_trigger_status_current.sql;schema_hash=sha256:e50cea0987f7f3b99989e2c23ef2d0f9d526617c688ac7f61a18e765ec439ef2;contract=N5-N6-trigger-status-forward-v1';

ALTER TABLE public.n6_trigger_status_current OWNER TO ashare_v3_user;
REVOKE ALL ON TABLE public.n6_trigger_status_current FROM PUBLIC;
REVOKE ALL ON SEQUENCE public.n6_trigger_status_current_trigger_status_episode_id_seq FROM PUBLIC;
GRANT SELECT ON TABLE public.n6_trigger_status_current TO n6_btrack_web;

DO $postflight$
DECLARE
  table_owner text;
BEGIN
  SELECT owner.rolname INTO table_owner
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_roles owner ON owner.oid = relation.relowner
  WHERE relation.oid = 'public.n6_trigger_status_current'::regclass;
  IF table_owner IS DISTINCT FROM 'ashare_v3_user'
     OR NOT pg_catalog.has_table_privilege(
          'n6_btrack_web', 'public.n6_trigger_status_current', 'SELECT'
        )
     OR pg_catalog.has_table_privilege(
          'n6_btrack_web', 'public.n6_trigger_status_current',
          'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
        ) THEN
    RAISE EXCEPTION '089 ownership or Web privilege postflight failed';
  END IF;
END
$postflight$;

COMMIT;
