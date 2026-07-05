-- N2 condition layer 20260528 rollback draft.
-- Scope: condition_layer_20260528_source_20260528_v1.
-- This rollback is intended only after the N2 run is executed and before any
-- downstream N3/N4/N5/N6 lineage references this run.
-- Does not touch N1 source_version, event outbox/inbox/checkpoint, N3-N6,
-- workers, old system, market data, or trading interfaces.
--
-- Usage:
--   psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 \
--     -f sql/N2_condition_layer_20260528_rollback.sql

BEGIN;

DO $$
DECLARE
  v_run_id text := 'condition_layer_20260528_source_20260528_v1';
  v_ref_count bigint;
BEGIN
  SELECT
    (SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id)
    + (SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id)
    + (SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id)
    + (SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id)
    + (SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id)
  INTO v_ref_count;

  IF v_ref_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: condition_layer_20260528_source_20260528_v1 already has downstream refs: %', v_ref_count;
  END IF;

  DELETE FROM stock_condition_display_basis WHERE run_id = v_run_id;
  DELETE FROM index_condition_display_basis WHERE run_id = v_run_id;
  DELETE FROM board_condition_display_basis WHERE run_id = v_run_id;

  DELETE FROM stock_minute_target_scope WHERE run_id = v_run_id;
  DELETE FROM board_minute_target_scope WHERE run_id = v_run_id;
  DELETE FROM index_minute_target_scope WHERE run_id = v_run_id;

  DELETE FROM board_condition_pool WHERE run_id = v_run_id;
  DELETE FROM index_condition_pool WHERE run_id = v_run_id;
  DELETE FROM stock_condition_pool WHERE run_id = v_run_id;

  DELETE FROM board_condition_basis WHERE run_id = v_run_id;
  DELETE FROM index_condition_basis WHERE run_id = v_run_id;
  DELETE FROM stock_condition_basis WHERE run_id = v_run_id;

  DELETE FROM board_monitor_target WHERE source_version = v_run_id;
  DELETE FROM index_monitor_target WHERE source_version = v_run_id;
  DELETE FROM stock_monitor_target WHERE source_version = v_run_id;

  DELETE FROM common_condition_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_condition_run WHERE run_id = v_run_id;
END $$;

COMMIT;
