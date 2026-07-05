-- N5 scoped rollback for the 20260617 after-N4 TriggerStateChanged closed-loop repair action execute.
--
-- Execute only after an explicitly approved N5 rollback execute gate.
--
-- Scope:
--   action_run_id:
--     action_consumer_execute_20260617_after_n4_trigger_state_changed_closed_loop_repair__trigger_action_confirmation_metric_execute_20260617_full_day_state_changed_closed_loop_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
--   source_trigger_run_id:
--     trigger_action_confirmation_metric_execute_20260617_full_day_state_changed_closed_loop_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
--   consumer_name:
--     n5_action_consumer_v1
--
-- Boundary:
--   Deletes only scoped N5 action-layer rows, scoped tracking rows,
--   scoped N5 outbox rows, and this N5 consumer's N4 inbox/checkpoint rows
--   for the source N4 run. It does not mutate N4 trigger facts, N4 outbox
--   status, N3 facts, N6/user projection, voice, mobile, sim, position,
--   order, real trade, or old-system tables.

BEGIN;

\set action_run_id 'action_consumer_execute_20260617_after_n4_trigger_state_changed_closed_loop_repair__trigger_action_confirmation_metric_execute_20260617_full_day_state_changed_closed_loop_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1'
\set source_trigger_run_id 'trigger_action_confirmation_metric_execute_20260617_full_day_state_changed_closed_loop_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1'
\set consumer_name 'n5_action_consumer_v1'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

-- Hard-fail guard: every check below runs before the first DELETE.
DO $$
DECLARE
  v_action_run_id text := current_setting('n5.rollback_action_run_id');
  v_source_trigger_run_id text := current_setting('n5.rollback_source_trigger_run_id');
  v_consumer_name text := current_setting('n5.rollback_consumer_name');
  v_count bigint := 0;
  v_table_name text;
  v_table_regclass regclass;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: common_action_run has wrong source_trigger_run_id rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM stock_action_fact
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: stock_action_fact has wrong source_trigger_run_id rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM index_action_fact
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: index_action_fact has wrong source_trigger_run_id rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM board_action_fact
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: board_action_fact has wrong source_trigger_run_id rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: common_action_event has wrong source_trigger_run_id rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_tracking_state
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: tracking rows share action_run_id but not source_trigger_run_id (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_events AS (
    SELECT event_id, outbox_id
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
    UNION ALL
    SELECT event_id, NULL::bigint AS outbox_id
    FROM common_event_ledger
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint c
  WHERE c.source_layer = 'N5_action'
    AND (
      c.checkpoint_payload::text LIKE '%' || v_action_run_id || '%'
      OR c.last_event_id IN (SELECT event_id FROM scoped_n5_events)
      OR c.last_outbox_id IN (
        SELECT outbox_id FROM scoped_n5_events WHERE outbox_id IS NOT NULL
      )
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id
    AND consumer_name <> v_consumer_name;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer inbox refs exist for source_trigger_run_id (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND consumer_name <> v_consumer_name
    AND (
      checkpoint_payload::text LIKE '%' || v_action_run_id || '%'
      OR checkpoint_payload::text LIKE '%' || v_source_trigger_run_id || '%'
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer checkpoint payload refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE consumer_name = v_consumer_name
    AND source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id
    AND event_type IN ('TriggerPendingMarketData', 'TriggerStateChanged');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N4 inbox unexpectedly contains non-action-entry rows (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_card_projection',
    'user_signal_projection',
    'user_signal_decision',
    'user_notification_queue',
    'user_notification_projection',
    'user_voice_delivery',
    'user_device_ack',
    'user_market_projection',
    'voice_delivery_queue',
    'mobile_projection',
    'mobile_notification_queue',
    'sim_projection',
    'sim_order',
    'sim_trade',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'common_position_state',
    'common_position_event',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'order_request',
    'order_execution',
    'real_trade_order',
    'real_trade_execution'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table_regclass
      )
      INTO v_count
      USING '%' || v_action_run_id || '%', '%' || v_source_trigger_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N5 rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

-- Preview scoped delete counts before deletion.
SELECT 'common_action_tracking_state' AS table_name, count(*) AS row_count
FROM common_action_tracking_state
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'stock_action_fact', count(*)
FROM stock_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'index_action_fact', count(*)
FROM index_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'board_action_fact', count(*)
FROM board_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_inbox_n4_consumer', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'common_event_consumer_checkpoint', count(*)
FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND checkpoint_payload->>'action_run_id' = :'action_run_id'
UNION ALL
SELECT 'common_action_quality_item', count(*)
FROM common_action_quality_item
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_run', count(*)
FROM common_action_run
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
  UNION
  SELECT event_id
  FROM common_event_ledger
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
)
DELETE FROM common_event_delivery_attempt
WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND checkpoint_payload->>'action_run_id' = :'action_run_id';

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_action_tracking_state
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

DELETE FROM common_action_event
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id'
  AND source_trigger_run_id = :'source_trigger_run_id';

COMMIT;
