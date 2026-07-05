-- V3 20260612 stale N5 trigger-period fabrication rollback.
-- Execute only after runtime_control final gate PASS and explicit user confirmation.
-- Scope:
--   stale action runs:
--     v3_n5_action_replay_20260612_after_n4_state_machine_v3
--     v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1
--   reviewed unique stale consumer:
--     v3_n5_action_replay_20260612_state_machine_consumer_v3
-- Boundary:
--   Deletes only scoped N5 facts/events/outbox/run rows and the reviewed
--   unique stale consumer's N4 inbox/checkpoint rows. It does not mutate N4
--   trigger facts, N4 outbox status, N3 facts/metrics, N6/user projection,
--   voice, mobile, sim, position, order, real-trade, scheduler, or old system.

BEGIN;

\set run_state_machine 'v3_n5_action_replay_20260612_after_n4_state_machine_v3'
\set run_hint_basis 'v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1'
\set source_state_machine 'v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3'
\set source_hint_basis 'v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1'
\set consumer_state_machine 'v3_n5_action_replay_20260612_state_machine_consumer_v3'
\set shared_default_consumer 'n5_action_consumer_v1'

SET LOCAL n5.rollback_run_state_machine = :'run_state_machine';
SET LOCAL n5.rollback_run_hint_basis = :'run_hint_basis';
SET LOCAL n5.rollback_source_state_machine = :'source_state_machine';
SET LOCAL n5.rollback_source_hint_basis = :'source_hint_basis';
SET LOCAL n5.rollback_consumer_state_machine = :'consumer_state_machine';
SET LOCAL n5.rollback_shared_default_consumer = :'shared_default_consumer';

-- Hard-fail guard: every check below runs before the first DELETE.
DO $$
DECLARE
  v_run_ids text[] := ARRAY[
    current_setting('n5.rollback_run_state_machine'),
    current_setting('n5.rollback_run_hint_basis')
  ];
  v_source_hint_basis text := current_setting('n5.rollback_source_hint_basis');
  v_shared_default_consumer text := current_setting('n5.rollback_shared_default_consumer');
  v_count bigint := 0;
  v_table_name text;
  v_table_regclass regclass;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = ANY(v_run_ids)
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = ANY(v_run_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_partitions AS (
    SELECT DISTINCT partition_key
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND source_run_id = ANY(v_run_ids)
    UNION
    SELECT DISTINCT partition_key
    FROM common_event_ledger
    WHERE source_layer = 'N5_action'
      AND source_run_id = ANY(v_run_ids)
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_n5_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_source_hint_basis
    AND consumer_name = v_shared_default_consumer;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: shared default consumer inbox refs for hint-basis source are ambiguous (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND consumer_name = v_shared_default_consumer
    AND partition_key IN (
      SELECT DISTINCT partition_key
      FROM common_event_outbox
      WHERE source_layer = 'N4_trigger'
        AND source_run_id = v_source_hint_basis
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: shared default consumer checkpoint refs for hint-basis source are ambiguous (%)', v_count;
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
      USING '%' || v_run_ids[1] || '%', '%' || v_run_ids[2] || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N5 stale trigger-period rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

SELECT 'common_action_run' AS table_name, count(*) AS row_count
FROM common_action_run
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'common_action_quality_item', count(*)
FROM common_action_quality_item
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'stock_action_fact', count(*)
FROM stock_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'index_action_fact', count(*)
FROM index_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'board_action_fact', count(*)
FROM board_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id IN (:'run_state_machine', :'run_hint_basis')
UNION ALL
SELECT 'common_event_inbox_unique_stale_consumer', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_state_machine'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_state_machine';

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id IN (:'run_state_machine', :'run_hint_basis')
  UNION
  SELECT event_id
  FROM common_event_ledger
  WHERE source_layer = 'N5_action'
    AND source_run_id IN (:'run_state_machine', :'run_hint_basis')
)
DELETE FROM common_event_delivery_attempt
WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);

WITH scoped_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_state_machine'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_state_machine'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_state_machine'
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_partitions);

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_state_machine'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_state_machine';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM common_action_event
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM board_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM index_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM stock_action_fact
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM common_action_quality_item
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

DELETE FROM common_action_run
WHERE run_id IN (:'run_state_machine', :'run_hint_basis');

COMMIT;
