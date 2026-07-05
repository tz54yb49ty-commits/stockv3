-- N5 asset_unit_fix_v1 full-406 supersession scoped rollback.
--
-- Execute only after an explicitly approved rollback execute gate.
--
-- Scope:
--   action_run_id:
--     action_provisional_active_monitor_v2_20260626_until_1447__asset_unit_fix_v1_supersession
--   source_trigger_run_id:
--     trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v1__atomic_rule_v1
--   consumer_name:
--     n5p_active_monitor_v2_asset_unit_fix_v1_supersession_consumer
--
-- Boundary:
--   Deletes only scoped N5 action-layer rows and this scoped consumer's N4
--   inbox/checkpoint rows. It does not mutate corrected N3P/N4 rows, old
--   unified N5 rows, N6/user projection, voice/mobile/sim/order/real-trade,
--   or old system tables.

BEGIN;

\set action_run_id 'action_provisional_active_monitor_v2_20260626_until_1447__asset_unit_fix_v1_supersession'
\set source_trigger_run_id 'trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_asset_unit_fix_v1__atomic_rule_v1'
\set consumer_name 'n5p_active_monitor_v2_asset_unit_fix_v1_supersession_consumer'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

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
  FROM common_action_tracking_state
  WHERE run_id = v_action_run_id
    AND source_trigger_run_id <> v_source_trigger_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: tracking rows share action_run_id but not source_trigger_run_id (%)', v_count;
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

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND (
      checkpoint_payload::text LIKE '%' || v_action_run_id || '%'
      OR last_event_id IN (
        SELECT event_id
        FROM common_event_outbox
        WHERE source_layer = 'N5_action'
          AND source_run_id = v_action_run_id
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
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer inbox refs exist for selected N4 source run (%)', v_count;
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
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer checkpoint refs exist for selected N4 source run (%)', v_count;
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
    'order_request',
    'order_execution',
    'real_trade_order',
    'real_trade_execution',
    'n6_virtual_order'
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

SELECT 'common_event_consumer_checkpoint_scoped' AS table_name, count(*) AS row_count
FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND (
    checkpoint_payload::text LIKE '%' || :'source_trigger_run_id' || '%'
    OR checkpoint_payload::text LIKE '%' || :'action_run_id' || '%'
  )
UNION ALL
SELECT 'common_event_inbox_scoped', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'stock_action_fact', count(*)
FROM stock_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'index_action_fact', count(*)
FROM index_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'board_action_fact', count(*)
FROM board_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_tracking_state', count(*)
FROM common_action_tracking_state
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_quality_item', count(*)
FROM common_action_quality_item
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_run', count(*)
FROM common_action_run
WHERE run_id = :'action_run_id';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND (
    checkpoint_payload::text LIKE '%' || :'source_trigger_run_id' || '%'
    OR checkpoint_payload::text LIKE '%' || :'action_run_id' || '%'
  );

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_action_event
WHERE run_id = :'action_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM common_action_tracking_state
WHERE run_id = :'action_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id';

COMMIT;
