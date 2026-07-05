-- V3 20260615 N5 replay after N4 formal amount guard rollback.
-- Execute only after an explicitly approved N5_action rollback final gate.
-- Scope:
--   action_run_id: n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1000_v1
--   source_trigger_run_id: n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_amount_guard_fix_v1
--   consumer_name: n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1000_v1
-- Boundary:
--   Deletes only scoped N5 replay rows and this dedicated consumer's
--   inbox/checkpoint rows for the fixed N4 source run. It preserves N4 trigger
--   facts, N4 outbox status, N3 metric facts, N6/user rows, scheduler state,
--   voice, mobile, sim, position, order, and real-trade tables.

BEGIN;

\set action_run_id 'n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1000_v1'
\set source_trigger_run_id 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_amount_guard_fix_v1'
\set consumer_name 'n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1000_v1'

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
  IF current_setting('ashare_v3.allow_n4_formal_amount_guard_n5_replay_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: set ashare_v3.allow_n4_formal_amount_guard_n5_replay_rollback=true before rollback';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_partitions AS (
    SELECT DISTINCT partition_key
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
    UNION
    SELECT DISTINCT partition_key
    FROM common_event_ledger
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_n5_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id
    AND consumer_name <> v_consumer_name;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: non-scoped consumer inbox refs for fixed N4 source (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_card_projection',
    'user_signal_projection',
    'user_signal_card',
    'user_signal_decision',
    'user_notification_queue',
    'user_notification_projection',
    'user_voice_delivery',
    'user_device_ack',
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
    'common_position_event'
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
        RAISE EXCEPTION 'N5 formal amount guard replay rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

SELECT 'common_action_run' AS table_name, count(*) AS row_count
FROM common_action_run
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_quality_item', count(*)
FROM common_action_quality_item
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
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_inbox_fixed_consumer', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

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

WITH scoped_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_name'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_trigger_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_partitions);

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

DELETE FROM common_action_event
WHERE run_id = :'action_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id';

COMMIT;
