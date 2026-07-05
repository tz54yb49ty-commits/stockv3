-- N4 projection matcher unified output retry rollback draft.
-- Target run:
--   trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
--
-- This rollback is intentionally guarded and must not be run as-is. It preserves
-- N1/N2/N3 facts, N3 MarketSnapshotUpdated outbox rows, and older N4 lineage.

BEGIN;

\set target_run_id 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry'
\set scoped_consumer_name 'n4_projection_matcher_consumer_v1_until_1500_unified_output_retry'
SET LOCAL n4.rollback_target_run_id = :'target_run_id';
SET LOCAL n4.rollback_scoped_consumer_name = :'scoped_consumer_name';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n4.rollback_target_run_id', true);
  v_consumer_name TEXT := current_setting('n4.rollback_scoped_consumer_name', true);
  v_count BIGINT := 0;
  v_table_name TEXT;
  v_table_regclass REGCLASS;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: target run id is not set';
  END IF;

  IF v_run_id <> 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry' THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: unexpected target run id %', v_run_id;
  END IF;

  IF v_consumer_name <> 'n4_projection_matcher_consumer_v1_until_1500_unified_output_retry' THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: unexpected scoped consumer %', v_consumer_name;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id
     AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: target outbox delivered/delivering rows exist (%)', v_count;
  END IF;

  IF to_regclass('public.common_event_ledger') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM common_event_ledger
     WHERE source_layer = 'N4_trigger'
       AND source_run_id = v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 unified output rollback blocked: event ledger rows reference target run (%)', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_delivery_attempt') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM common_event_delivery_attempt d
      JOIN common_event_outbox o ON o.outbox_id = d.outbox_id
     WHERE o.source_layer = 'N4_trigger'
       AND o.source_run_id = v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 unified output rollback blocked: delivery attempts reference target outbox (%)', v_count;
    END IF;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_inbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: downstream inbox rows reference target N4 outbox (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_consumer_checkpoint c
   WHERE NOT (
       c.consumer_name = v_consumer_name
       AND c.source_layer = 'N3_market_data'
       AND c.checkpoint_payload ->> 'execute_run_id' = v_run_id
     )
     AND (
       c.checkpoint_payload::text LIKE '%' || v_run_id || '%'
       OR EXISTS (
        SELECT 1
          FROM common_event_outbox o
         WHERE o.outbox_id = c.last_outbox_id
           AND o.source_layer = 'N4_trigger'
           AND o.source_run_id = v_run_id
       )
     );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: consumer checkpoint rows reference target run/outbox (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_action_run
   WHERE source_trigger_run_id = v_run_id
      OR run_id LIKE '%' || v_run_id || '%'
      OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: N5 common_action_run refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_action_event
   WHERE source_trigger_run_id = v_run_id
      OR run_id LIKE '%' || v_run_id || '%'
      OR payload_json::text LIKE '%' || v_run_id || '%'
      OR trace_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: N5 common_action_event refs exist (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format(
      'SELECT count(*) FROM %s t WHERE source_trigger_run_id = $1 OR source_payload_json::text LIKE $2 OR raw_json::text LIKE $2 OR trace_json::text LIKE $2',
      v_table_regclass
    )
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 unified output rollback blocked: N5 action fact table % refs exist (%)', v_table_name, v_count;
    END IF;
  END LOOP;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N5_action'
     AND (
       source_run_id LIKE '%' || v_run_id || '%'
       OR payload_json::text LIKE '%' || v_run_id || '%'
     );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: N5 outbox refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_inbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: N5/downstream inbox refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_consumer_checkpoint c
   WHERE NOT (
       c.consumer_name = v_consumer_name
       AND c.source_layer = 'N3_market_data'
       AND c.checkpoint_payload ->> 'execute_run_id' = v_run_id
     )
     AND (
       c.checkpoint_payload::text LIKE '%' || v_run_id || '%'
       OR EXISTS (
        SELECT 1
          FROM common_event_outbox o
         WHERE o.outbox_id = c.last_outbox_id
           AND o.source_layer = 'N4_trigger'
           AND o.source_run_id = v_run_id
       )
     );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 unified output rollback blocked: N5/downstream checkpoint refs exist (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_signal_decision',
    'user_voice_delivery',
    'user_push_delivery',
    'user_mobile_push_queue',
    'voice_delivery_queue',
    'mobile_delivery_queue',
    'delivery_attempt',
    'common_event_delivery_attempt',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl',
    'n6_virtual_pnl_snapshot',
    'common_position_state',
    'common_position_event'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format('SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1', v_table_regclass)
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 unified output rollback blocked: downstream table % refs exist (%)', v_table_name, v_count;
    END IF;
  END LOOP;

  RAISE EXCEPTION 'N4 unified output rollback is hard-failed by default. Review guards, remove this hard-fail intentionally, and rerun only if scoped rollback is approved for % / %.', v_run_id, v_consumer_name;
END $$;

-- Safety preview.
SELECT event_type, status, count(*) AS row_count
FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = :'target_run_id'
GROUP BY event_type, status
ORDER BY event_type, status;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = :'target_run_id';

DELETE FROM common_trigger_match
WHERE run_id = :'target_run_id';

DELETE FROM common_trigger_state
WHERE run_id = :'target_run_id';

DELETE FROM common_trigger_quality_item
WHERE run_id = :'target_run_id';

DELETE FROM common_event_inbox
WHERE consumer_name = :'scoped_consumer_name'
  AND raw_json ->> 'execute_run_id' = :'target_run_id';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'scoped_consumer_name'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = :'target_run_id';

DELETE FROM common_trigger_run
WHERE run_id = :'target_run_id';

COMMIT;
