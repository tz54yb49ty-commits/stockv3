-- Scoped rollback for 20260615 N6 user projection after N5 metric replay until_1342.
-- Scope:
--   projection_run_id: v3_n6_user_projection_20260615_after_n5_metric_replay_until_1342_v1
-- Boundary:
--   Deletes only scoped N6 user_projection_run/user_signal_projection/user_signal_card rows.
--   Preserves N5/N4/N3 facts and all event outbox/inbox/checkpoint rows.

BEGIN;

\set projection_run_id 'v3_n6_user_projection_20260615_after_n5_metric_replay_until_1342_v1'

SET LOCAL n6.rollback_projection_run_id = :'projection_run_id';

-- Hard-fail guards before first DELETE.
DO $$
DECLARE
  v_projection_run_id text := current_setting('n6.rollback_projection_run_id');
  v_count bigint := 0;
BEGIN
  SELECT count(*) INTO v_count
  FROM user_notification_queue
  WHERE projection_run_id = v_projection_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: scoped notification queue rows exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_projection_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: scoped outbox rows exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_projection_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: scoped inbox rows exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_projection_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: scoped checkpoint refs exist (%)', v_count;
  END IF;
END $$;

SELECT 'user_projection_run' AS table_name, count(*) AS row_count
FROM user_projection_run
WHERE projection_run_id = :'projection_run_id'
UNION ALL
SELECT 'user_signal_projection', count(*)
FROM user_signal_projection
WHERE projection_run_id = :'projection_run_id'
UNION ALL
SELECT 'user_signal_card', count(*)
FROM user_signal_card
WHERE projection_run_id = :'projection_run_id'
UNION ALL
SELECT 'user_notification_queue', count(*)
FROM user_notification_queue
WHERE projection_run_id = :'projection_run_id';

DELETE FROM user_signal_card
WHERE projection_run_id = :'projection_run_id';

DELETE FROM user_signal_projection
WHERE projection_run_id = :'projection_run_id';

DELETE FROM user_projection_run
WHERE projection_run_id = :'projection_run_id';

COMMIT;
