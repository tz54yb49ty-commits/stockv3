-- N2 20260529 anchor segment alignment v4 active-supersede rollback.
-- Scope: remove only condition_layer_20260529_source_20260529_v4 rows and
-- restore condition_layer_20260529_source_20260529_v3 to passed_active.
--
-- Boundary:
-- - Does not touch v3/v2/v1 rows except restoring v3 common_condition_run.status.
-- - Does not touch N1 source_version.
-- - Does not touch common_event_outbox / common_event_inbox / common_event_consumer_checkpoint.
-- - Blocks rollback if v4 has already been consumed by N3/N4/N5/N6 downstream refs.
--
-- Usage:
--   psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 \
--     -f sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql

BEGIN;

CREATE TEMP TABLE _n2_v4_downstream_ref_guard (
  table_name TEXT NOT NULL,
  column_name TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _n2_v4_downstream_ref_guard(table_name, column_name) VALUES
  ('common_market_data_run', 'source_condition_run_id'),
  ('common_market_data_subscription_candidate', 'source_condition_run_id'),
  ('common_market_data_subscription', 'source_condition_run_id'),
  ('common_market_data_pull_plan', 'source_condition_run_id'),
  ('common_market_data_quality_item', 'source_condition_run_id'),
  ('stock_previous_day_minute_preload_status', 'source_condition_run_id'),
  ('index_previous_day_minute_preload_status', 'source_condition_run_id'),
  ('board_previous_day_minute_preload_status', 'source_condition_run_id'),
  ('stock_realtime_daily_snapshot', 'source_condition_run_id'),
  ('index_realtime_daily_snapshot', 'source_condition_run_id'),
  ('board_realtime_daily_snapshot', 'source_condition_run_id'),
  ('stock_minute_bar_1m', 'source_condition_run_id'),
  ('index_minute_bar_1m', 'source_condition_run_id'),
  ('board_minute_bar_1m', 'source_condition_run_id'),
  ('stock_realtime_projection_metric', 'source_condition_run_id'),
  ('index_realtime_projection_metric', 'source_condition_run_id'),
  ('board_realtime_projection_metric', 'source_condition_run_id'),
  ('stock_closed_30m_summary', 'source_condition_run_id'),
  ('index_closed_30m_summary', 'source_condition_run_id'),
  ('board_closed_30m_summary', 'source_condition_run_id'),
  ('stock_closed_30m_signal_enrichment', 'source_condition_run_id'),
  ('index_closed_30m_signal_enrichment', 'source_condition_run_id'),
  ('board_closed_30m_signal_enrichment', 'source_condition_run_id'),
  ('stock_eod_snapshot', 'source_condition_run_id'),
  ('index_eod_snapshot', 'source_condition_run_id'),
  ('board_eod_snapshot', 'source_condition_run_id'),
  ('common_trigger_run', 'source_condition_run_id'),
  ('common_trigger_quality_item', 'source_condition_run_id'),
  ('stock_trigger_context_snapshot', 'source_condition_run_id'),
  ('index_trigger_context_snapshot', 'source_condition_run_id'),
  ('board_trigger_context_snapshot', 'source_condition_run_id'),
  ('common_trigger_state', 'source_condition_run_id'),
  ('common_trigger_match', 'source_condition_run_id'),
  ('stock_trigger_replay_audit', 'source_condition_run_id'),
  ('index_trigger_replay_audit', 'source_condition_run_id'),
  ('board_trigger_replay_audit', 'source_condition_run_id'),
  ('common_action_run', 'source_condition_run_id'),
  ('stock_action_fact', 'source_condition_run_id'),
  ('index_action_fact', 'source_condition_run_id'),
  ('board_action_fact', 'source_condition_run_id'),
  ('common_action_event', 'source_condition_run_id'),
  ('common_position_event', 'source_condition_run_id'),
  ('user_projection_run', 'source_display_condition_run_id'),
  ('user_signal_projection', 'source_condition_display_run_id');

DO $$
DECLARE
  v_run_id TEXT := 'condition_layer_20260529_source_20260529_v4';
  v_previous_run_id TEXT := 'condition_layer_20260529_source_20260529_v3';
  ref RECORD;
  ref_count BIGINT;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM common_condition_run WHERE run_id = v_previous_run_id) THEN
    RAISE EXCEPTION 'rollback blocked: previous N2 run % does not exist', v_previous_run_id;
  END IF;

  FOR ref IN SELECT table_name, column_name FROM _n2_v4_downstream_ref_guard LOOP
    EXECUTE format('SELECT count(*) FROM %I WHERE %I = $1', ref.table_name, ref.column_name)
      INTO ref_count
      USING v_run_id;
    IF ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: %.% has % downstream refs to %',
        ref.table_name, ref.column_name, ref_count, v_run_id;
    END IF;
  END LOOP;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM index_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM board_condition_display_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';

DELETE FROM stock_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM index_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM board_minute_target_scope WHERE run_id = 'condition_layer_20260529_source_20260529_v4';

DELETE FROM stock_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM index_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM board_condition_pool WHERE run_id = 'condition_layer_20260529_source_20260529_v4';

DELETE FROM stock_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM index_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM board_condition_basis WHERE run_id = 'condition_layer_20260529_source_20260529_v4';

DELETE FROM stock_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM index_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM board_monitor_target WHERE source_version = 'condition_layer_20260529_source_20260529_v4';

DELETE FROM common_condition_quality_item WHERE run_id = 'condition_layer_20260529_source_20260529_v4';
DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260529_source_20260529_v4';

UPDATE common_condition_run
SET status = 'passed_active'
WHERE run_id = 'condition_layer_20260529_source_20260529_v3'
  AND status IN ('superseded', 'passed');

DO $$
DECLARE
  v_previous_status TEXT;
BEGIN
  SELECT status INTO v_previous_status
  FROM common_condition_run
  WHERE run_id = 'condition_layer_20260529_source_20260529_v3';

  IF v_previous_status <> 'passed_active' THEN
    RAISE EXCEPTION 'rollback blocked: previous run status after restore is %, expected passed_active', v_previous_status;
  END IF;
END $$;

COMMIT;
