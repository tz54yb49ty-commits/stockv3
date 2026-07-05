-- N5 20260611 bounded action run rollback registry.
-- Default state: hard-fail before any row-removal statement.
--
-- Scope:
--   action_run_id: n5_action_bounded_20260611_from_n4_production_semantic_replay_v1
--   source_trigger_run_id: n4_production_semantic_replay_20260611_market_snapshot_updated_v1
--   consumer_name: n5_action_consumer_v1
--
-- Boundary:
--   Intended rollback scope is limited to this N5 action run, this N5
--   consumer's inbox/checkpoint rows for the scoped N4 source run, and this
--   N5 run's ActionBlocked outbox rows. It must not mutate N3/N4 source
--   outbox status, N6/user projection, voice, mobile, sim, position, order,
--   trade, or old-system data.

BEGIN;

\set action_run_id 'n5_action_bounded_20260611_from_n4_production_semantic_replay_v1'
\set source_trigger_run_id 'n4_production_semantic_replay_20260611_market_snapshot_updated_v1'
\set consumer_name 'n5_action_consumer_v1'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

-- Guards run before the default hard-fail and before the first DELETE.
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
  FROM common_event_consumer_checkpoint cp
  WHERE cp.source_layer = 'N5_action'
    AND cp.last_event_id IN (
      SELECT event_id
      FROM common_event_outbox
      WHERE source_layer = 'N5_action'
        AND source_run_id = v_action_run_id
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_position_event
  WHERE run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped position event refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_position_state
  WHERE run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped position state refs exist (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
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
    'common_order_event',
    'common_trade_event'
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

DO $$
BEGIN
  RAISE EXCEPTION 'N5 rollback blocked by default. Remove this hard-fail only in an explicitly approved rollback execute gate.';
END $$;

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE source_layer = 'N5_action'
  AND last_event_id IN (SELECT event_id FROM scoped_n5_event_ids);

WITH scoped_n4_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_name'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_trigger_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_n4_partitions)
  AND last_event_id IN (
    SELECT event_id
    FROM common_event_outbox
    WHERE source_layer = 'N4_trigger'
      AND source_run_id = :'source_trigger_run_id'
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
