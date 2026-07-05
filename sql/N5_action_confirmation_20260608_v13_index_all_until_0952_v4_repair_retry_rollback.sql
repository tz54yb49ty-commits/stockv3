-- N5 scoped action rollback for v4 repair retry.
-- Scope action_run_id: action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
-- Scope source_trigger_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
-- Scope consumer_name: n5_action_consumer_v1

BEGIN;

\set action_run_id 'action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry'
\set source_trigger_run_id 'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry'
\set consumer_name 'n5_action_consumer_v1'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

-- Hard-fail guard runs before any row removal.
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
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped outbox has delivered/delivering rows (%)', v_count;
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
    AND checkpoint_payload::text LIKE '%' || v_action_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id
    AND consumer_name <> v_consumer_name;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped N4 consumer inbox refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND consumer_name <> v_consumer_name
    AND (checkpoint_payload::text LIKE '%' || v_source_trigger_run_id || '%'
      OR checkpoint_payload::text LIKE '%' || v_action_run_id || '%');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped N4 consumer checkpoint refs exist (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'common_action_run',
    'common_action_event',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1 AND to_jsonb(t)::text NOT LIKE $2',
        v_table_regclass
      )
      INTO v_count
      USING '%' || v_source_trigger_run_id || '%', '%' || v_action_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N5 rollback blocked: non-target N5 table % references source run (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id <> v_action_run_id
    AND to_jsonb(common_event_outbox)::text LIKE '%' || v_source_trigger_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-target N5_action outbox references source run (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'common_event_ledger',
    'common_event_delivery_attempt',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_signal_decision',
    'common_position_state',
    'common_position_event',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'user_sim_position_event',
    'user_sim_pnl',
    'user_sim_pnl_snapshot',
    'sim_order',
    'sim_trade',
    'sim_projection',
    'virtual_order',
    'virtual_trade',
    'virtual_position',
    'virtual_pnl_snapshot'
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

WITH scoped_checkpoint_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_name'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_trigger_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND (
    checkpoint_payload::text LIKE '%' || :'action_run_id' || '%'
    OR checkpoint_payload::text LIKE '%' || :'source_trigger_run_id' || '%'
    OR partition_key IN (SELECT partition_key FROM scoped_checkpoint_partitions)
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
