-- A-share monitor v3 N6 local display cache sync rollback.
-- Scope: rollback only cache rows for
-- n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1.
-- This rollback does not drop schema tables and does not touch N1/N2 sources,
-- N3/N4/N5 facts, N6 projections/cards, or event infrastructure.

\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
  v_cache_run_id TEXT := 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1';
  v_cache_version TEXT := 'n6_display_cache_v1';
  v_run_exists BIGINT;
  v_outbox_refs BIGINT;
  v_inbox_refs BIGINT;
  v_checkpoint_refs BIGINT;
  v_user_projection_refs BIGINT;
  v_user_signal_refs BIGINT;
  v_user_card_refs BIGINT;
  v_user_notification_refs BIGINT;
BEGIN
  SELECT count(*)
    INTO v_run_exists
    FROM n6_display_cache_run
   WHERE cache_run_id = v_cache_run_id
     AND cache_version = v_cache_version;

  IF v_run_exists = 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: target cache_run_id/cache_version does not exist: % / %',
      v_cache_run_id,
      v_cache_version;
  END IF;

  SELECT count(*)
    INTO v_outbox_refs
    FROM common_event_outbox
   WHERE source_run_id = v_cache_run_id
      OR payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR dedup_key LIKE '%' || v_cache_run_id || '%';

  IF v_outbox_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: common_event_outbox refs=% for cache_run_id=%',
      v_outbox_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_inbox_refs
    FROM common_event_inbox
   WHERE source_run_id = v_cache_run_id
      OR payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR dedup_key LIKE '%' || v_cache_run_id || '%';

  IF v_inbox_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: common_event_inbox refs=% for cache_run_id=%',
      v_inbox_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_checkpoint_refs
    FROM common_event_consumer_checkpoint
   WHERE checkpoint_payload::TEXT LIKE '%' || v_cache_run_id || '%'
      OR partition_key LIKE '%' || v_cache_run_id || '%';

  IF v_checkpoint_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: common_event_consumer_checkpoint refs=% for cache_run_id=%',
      v_checkpoint_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_user_projection_refs
    FROM user_projection_run
   WHERE quality_summary_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR source_n5_outbox_range::TEXT LIKE '%' || v_cache_run_id || '%';

  IF v_user_projection_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: user_projection_run refs=% for cache_run_id=%',
      v_user_projection_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_user_signal_refs
    FROM user_signal_projection
   WHERE source_payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR display_payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR trace_json::TEXT LIKE '%' || v_cache_run_id || '%';

  IF v_user_signal_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: user_signal_projection refs=% for cache_run_id=%',
      v_user_signal_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_user_card_refs
    FROM user_signal_card
   WHERE card_payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR trace_json::TEXT LIKE '%' || v_cache_run_id || '%';

  IF v_user_card_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: user_signal_card refs=% for cache_run_id=%',
      v_user_card_refs,
      v_cache_run_id;
  END IF;

  SELECT count(*)
    INTO v_user_notification_refs
    FROM user_notification_queue
   WHERE notification_payload_json::TEXT LIKE '%' || v_cache_run_id || '%'
      OR trace_json::TEXT LIKE '%' || v_cache_run_id || '%';

  IF v_user_notification_refs > 0 THEN
    RAISE EXCEPTION
      'N6 local display cache sync rollback blocked: user_notification_queue refs=% for cache_run_id=%',
      v_user_notification_refs,
      v_cache_run_id;
  END IF;
END $$;

UPDATE n6_display_cache_run
   SET is_active = FALSE,
       status = 'rolled_back',
       updated_at = now()
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_board_membership_display_cache
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_index_membership_display_cache
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_board_display_cache
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_index_display_cache
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_stock_display_cache
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

DELETE FROM n6_display_cache_run
 WHERE cache_run_id = 'n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1'
   AND cache_version = 'n6_display_cache_v1';

COMMIT;
