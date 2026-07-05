-- N3 subscription 20260601 v6 rebuild rollback guard.
-- Scope: market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1
-- This rollback is scoped to the rebuild subscription control rows only.
-- It must not touch the original 20260601 v6 subscription run, N2 condition rows,
-- market data facts, snapshot/minute/projection facts, outbox/inbox/checkpoint,
-- N4/N5/N6, user/voice/mobile/sim/position/real-trade state, workers, or the old system.

BEGIN;

DO $$
DECLARE
  v_run_id text := 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';
  v_outbox_count bigint;
  v_inbox_count bigint;
  v_checkpoint_count bigint;
  v_downstream_market_run_refs bigint;
  v_snapshot_refs bigint;
  v_minute_refs bigint;
  v_preload_status_refs bigint;
  v_realtime_projection_refs bigint;
  v_action_metric_refs bigint;
  v_eod_refs bigint;
  v_n4_n5_n6_refs bigint := 0;
  v_scan record;
  v_scan_count bigint;
BEGIN
  SELECT count(*) INTO v_outbox_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id
     OR payload_json::text LIKE '%' || v_run_id || '%';

  SELECT count(*) INTO v_inbox_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR payload_json::text LIKE '%' || v_run_id || '%';

  SELECT count(*) INTO v_checkpoint_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';

  -- Guard A1/B1/B2/C1/EOD/action-confirmation or other N3 runs that
  -- reference this subscription run through run_id naming or raw_json lineage.
  SELECT count(*) INTO v_downstream_market_run_refs
  FROM common_market_data_run
  WHERE run_id <> v_run_id
    AND (
      run_id LIKE '%' || v_run_id || '%'
      OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%'
    );

  -- Guard B1 realtime snapshot facts.
  SELECT
    (SELECT count(*) FROM stock_realtime_daily_snapshot WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_realtime_daily_snapshot WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_realtime_daily_snapshot WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_snapshot_refs;

  -- Guard A1/C1 minute facts.
  SELECT
    (SELECT count(*) FROM stock_minute_bar_1m WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_minute_bar_1m WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_minute_bar_1m WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_minute_refs;

  -- Guard previous-day preload status rows.
  SELECT
    (SELECT count(*) FROM stock_previous_day_minute_preload_status WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_previous_day_minute_preload_status WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_previous_day_minute_preload_status WHERE run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_preload_status_refs;

  -- Guard B2 realtime projection metric facts.
  SELECT
    (SELECT count(*) FROM stock_realtime_projection_metric WHERE projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_realtime_projection_metric WHERE projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_realtime_projection_metric WHERE projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_realtime_projection_refs;

  -- Guard N3 action-confirmation projection metrics.
  SELECT
    (SELECT count(*) FROM stock_action_confirmation_projection_metric WHERE source_subscription_run_id = v_run_id OR projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_action_confirmation_projection_metric WHERE source_subscription_run_id = v_run_id OR projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_action_confirmation_projection_metric WHERE source_subscription_run_id = v_run_id OR projection_run_id LIKE '%' || v_run_id || '%' OR source_snapshot_run_id LIKE '%' || v_run_id || '%' OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_action_metric_refs;

  -- Guard EOD settlement facts.
  SELECT
    (SELECT count(*) FROM stock_eod_snapshot WHERE source_subscription_run_id = v_run_id OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_eod_snapshot WHERE source_subscription_run_id = v_run_id OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_eod_snapshot WHERE source_subscription_run_id = v_run_id OR COALESCE(raw_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM stock_eod_reconciliation_item WHERE source_run_id = v_run_id OR eod_run_id LIKE '%' || v_run_id || '%' OR COALESCE(trace_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM index_eod_reconciliation_item WHERE source_run_id = v_run_id OR eod_run_id LIKE '%' || v_run_id || '%' OR COALESCE(trace_json::text, '') LIKE '%' || v_run_id || '%') +
    (SELECT count(*) FROM board_eod_reconciliation_item WHERE source_run_id = v_run_id OR eod_run_id LIKE '%' || v_run_id || '%' OR COALESCE(trace_json::text, '') LIKE '%' || v_run_id || '%')
  INTO v_eod_refs;

  -- Guard N4/N5/N6 and user/voice/mobile/sim/position/real-trade refs with a
  -- dynamic text/jsonb scan. These are evidence checks only; no rows are
  -- modified here.
  FOR v_scan IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND data_type IN ('text', 'jsonb')
      AND (
        table_name LIKE '%trigger%'
        OR table_name LIKE '%action%'
        OR table_name LIKE '%user%'
        OR table_name LIKE '%voice%'
        OR table_name LIKE '%mobile%'
        OR table_name LIKE '%sim%'
        OR table_name LIKE '%position%'
        OR table_name LIKE '%trade%'
      )
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM %I WHERE %I::text LIKE $1',
      v_scan.table_name,
      v_scan.column_name
    )
    INTO v_scan_count
    USING '%' || v_run_id || '%';
    v_n4_n5_n6_refs := v_n4_n5_n6_refs + v_scan_count;
  END LOOP;

  IF v_outbox_count <> 0
     OR v_inbox_count <> 0
     OR v_checkpoint_count <> 0
     OR v_downstream_market_run_refs <> 0
     OR v_snapshot_refs <> 0
     OR v_minute_refs <> 0
     OR v_preload_status_refs <> 0
     OR v_realtime_projection_refs <> 0
     OR v_action_metric_refs <> 0
     OR v_eod_refs <> 0
     OR v_n4_n5_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing N3 subscription rebuild rollback for %: outbox %, inbox %, checkpoint %, downstream_market_run %, snapshot %, minute %, preload_status %, realtime_projection %, action_metric %, eod %, N4_N5_N6_user_refs %',
      v_run_id,
      v_outbox_count,
      v_inbox_count,
      v_checkpoint_count,
      v_downstream_market_run_refs,
      v_snapshot_refs,
      v_minute_refs,
      v_preload_status_refs,
      v_realtime_projection_refs,
      v_action_metric_refs,
      v_eod_refs,
      v_n4_n5_n6_refs;
  END IF;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1';

COMMIT;
