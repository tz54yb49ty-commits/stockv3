-- N6 delivery notification queue schema alignment rollback draft.
-- Scope: user_notification_queue CHECK constraints only.
-- Restores pre-delivery-preview allowed values.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
  v_constraint RECORD;
BEGIN
  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE notification_source = 'n6_delivery_materialized_noop';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 delivery schema rollback blocked: n6_delivery_materialized_noop rows exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE channel = 'in_app_notification_preview';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 delivery schema rollback blocked: in_app_notification_preview rows exist: %', v_count;
  END IF;

  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_notification_queue'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%notification_source%'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', 'public', 'user_notification_queue', v_constraint.conname);
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_notification_queue'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%channel%'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', 'public', 'user_notification_queue', v_constraint.conname);
  END LOOP;
END $$;

ALTER TABLE user_notification_queue
  ADD CONSTRAINT chk_user_notification_queue_notification_source_n6_canonical_compat
  CHECK (
    notification_source IN (
      'index_signal',
      'board_signal',
      'stock_filter_signal',
      'n5_action_event',
      'n5_hint_event',
      'n5_action_eligible',
      'n5_action_blocked',
      'n5_action_executed',
      'n5_action_skipped'
    )
  ) NOT VALID;

ALTER TABLE user_notification_queue
  ADD CONSTRAINT user_notification_queue_channel_check
  CHECK (
    channel IN (
      'broadcast_queue',
      'voice_future',
      'mobile_future',
      'in_app_future'
    )
  ) NOT VALID;

COMMIT;
