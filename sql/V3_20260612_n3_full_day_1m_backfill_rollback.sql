-- V3 20260612 N3 full-day 1m backfill rollback
-- Scoped to run_id=v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1
DO $$
DECLARE
  target_run_id text := 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_full_day_1m_backfill_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260612_full_day_1m_backfill_rollback=true before DELETE';
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_outbox
    WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_outbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_inbox
    WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%' OR raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_inbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_consumer_checkpoint
    WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_consumer_checkpoint refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_trigger_run
    WHERE source_market_data_run_id = target_run_id OR raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_trigger_run refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_action_run
    WHERE raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_action_run refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_signal_projection
    WHERE source_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_signal_projection refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_signal_card
    WHERE card_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_signal_card refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_notification_queue
    WHERE notification_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_notification_queue refs exist for %', target_run_id;
  END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
DELETE FROM index_minute_bar_1m WHERE run_id = 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
DELETE FROM board_minute_bar_1m WHERE run_id = 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
DELETE FROM common_market_data_run WHERE run_id = 'v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1';
