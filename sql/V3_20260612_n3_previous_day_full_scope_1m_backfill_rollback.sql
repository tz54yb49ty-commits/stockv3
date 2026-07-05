-- V3 20260612 N3 previous-day full-scope 1m backfill rollback.
-- Scoped to run_id=v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1.
-- Default hard-fails before any row removal. Does not touch current-day facts,
-- N3 metrics, N4/N5/N6 rows, or event infrastructure.

BEGIN;

DO $$
DECLARE
  target_run_id text := 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';
  v_count bigint;
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_previous_day_full_scope_1m_backfill_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260612_previous_day_full_scope_1m_backfill_rollback=true before DELETE';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_outbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::text LIKE '%' || target_run_id || '%'
     OR raw_json::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id <> target_run_id
    AND raw_json::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: other N3 run refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_run
  WHERE source_market_data_run_id = target_run_id
     OR raw_json::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N4 refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE raw_json::text LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N5 refs=%', v_count;
  END IF;
END $$;

DELETE FROM stock_minute_bar_1m
WHERE run_id = 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';

DELETE FROM index_minute_bar_1m
WHERE run_id = 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';

DELETE FROM board_minute_bar_1m
WHERE run_id = 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1';

COMMIT;
