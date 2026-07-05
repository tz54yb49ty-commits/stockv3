-- N1 trade calendar 20260605 patch rollback draft.
-- Scope: trade_calendar_20260605_patch_v1.
-- This rollback does not touch 20260604 calendar, daily fact, condition source,
-- Parquet, outbox/inbox/checkpoint, N2/N3/N4/N5/N6, worker, old system, or
-- trading state.
-- If 20260605 N1 daily facts or N2/N3/N4/N5/N6 refs exist, this rollback is
-- expected to hard-fail before DELETE. Roll back downstream scoped runs first,
-- or open a dedicated rollback plan.

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'trade_calendar_20260605_patch_v1';
  v_source_version text := 'trade_calendar_20260605_patch_v1';
  v_scope_key text := 'SSE:20260605';
  v_trade_date text := '20260605';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n1_fact_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_scope_key || '%'
     OR payload_json::text LIKE '%' || v_trade_date || '%';

  SELECT COUNT(*)
  INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_scope_key || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%'
     OR payload_json::text LIKE '%' || v_trade_date || '%'
     OR raw_json::text LIKE '%' || v_trade_date || '%';

  SELECT COUNT(*)
  INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_source_version || '%'
     OR checkpoint_payload::text LIKE '%' || v_scope_key || '%'
     OR checkpoint_payload::text LIKE '%' || v_trade_date || '%';

  SELECT
    (SELECT COUNT(*) FROM stock_daily_bar_fact WHERE trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM index_daily_bar_fact WHERE trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM board_daily_bar_fact WHERE trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM stock_daily_basic WHERE trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM stock_financial_metrics_fact WHERE source_trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM index_membership_fact WHERE trade_date = v_trade_date)
    + (SELECT COUNT(*) FROM board_membership_fact WHERE trade_date = v_trade_date)
  INTO v_n1_fact_refs;

  SELECT COUNT(*)
  INTO v_n2_refs
  FROM common_condition_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_trade_date
     OR source_version = v_source_version
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR source_versions::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT COUNT(*)
  INTO v_n3_refs
  FROM common_market_data_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT COUNT(*)
  INTO v_n4_refs
  FROM common_trigger_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT COUNT(*)
  INTO v_n5_refs
  FROM common_action_run
  WHERE for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT COUNT(*)
  INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text LIKE '%' || v_batch_id || '%'
     OR quality_summary_json::text LIKE '%' || v_source_version || '%'
     OR quality_summary_json::text LIKE '%' || v_scope_key || '%'
     OR source_display_condition_run_id LIKE '%' || v_trade_date || '%'
     OR source_action_run_id LIKE '%' || v_trade_date || '%';

  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.data_domain = 'common'
    AND a.data_type = 'trade_calendar'
    AND a.scope_key = v_scope_key
    AND a.source_batch_id = v_batch_id
    AND a.source_version = v_source_version
    AND a.previous_source_version IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
    );

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n1_fact_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0
     OR missing_previous_batch_count <> 0 THEN
    RAISE EXCEPTION
      'Refusing 20260605 calendar patch rollback: outbox %, inbox %, checkpoint %, N1 facts %, N2 %, N3 %, N4 %, N5 %, N6 %, missing_previous_batch %',
      v_outbox_refs,
      v_inbox_refs,
      v_checkpoint_refs,
      v_n1_fact_refs,
      v_n2_refs,
      v_n3_refs,
      v_n4_refs,
      v_n5_refs,
      v_n6_refs,
      missing_previous_batch_count;
  END IF;
END $$;

UPDATE common_active_source_version a
SET source_version = a.previous_source_version,
    source_batch_id = (
      SELECT b.batch_id
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
      ORDER BY b.finished_at DESC NULLS LAST, b.started_at DESC, b.batch_id DESC
      LIMIT 1
    ),
    previous_source_version = NULL,
    activated_at = now(),
    activated_by = 'rollback:n1_trade_calendar_20260605_patch'
WHERE a.data_domain = 'common'
  AND a.data_type = 'trade_calendar'
  AND a.scope_key = 'SSE:20260605'
  AND a.source_batch_id = 'trade_calendar_20260605_patch_v1'
  AND a.source_version = 'trade_calendar_20260605_patch_v1'
  AND a.previous_source_version IS NOT NULL;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND scope_key = 'SSE:20260605'
  AND source_batch_id = 'trade_calendar_20260605_patch_v1'
  AND source_version = 'trade_calendar_20260605_patch_v1'
  AND previous_source_version IS NULL;

DELETE FROM common_trade_calendar
WHERE trade_date = '20260605'
  AND source_batch_id = 'trade_calendar_20260605_patch_v1'
  AND source_version = 'trade_calendar_20260605_patch_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'trade_calendar_20260605_patch_v1'
   OR source_version = 'trade_calendar_20260605_patch_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'trade_calendar_20260605_patch_v1'
   OR source_version = 'trade_calendar_20260605_patch_v1';

COMMIT;
