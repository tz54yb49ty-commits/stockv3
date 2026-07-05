-- N6 delivery notification queue schema alignment draft.
-- Scope: user_notification_queue CHECK constraints only.
-- Adds support for:
--   notification_source = n6_delivery_materialized_noop
--   channel = in_app_notification_preview

BEGIN;

DO $$
DECLARE
  v_constraint RECORD;
BEGIN
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
  ADD CONSTRAINT chk_unq_notification_source_n6_delivery
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
      'n5_action_skipped',
      'n6_delivery_materialized_noop'
    )
  ) NOT VALID;

ALTER TABLE user_notification_queue
  ADD CONSTRAINT chk_unq_channel_n6_delivery
  CHECK (
    channel IN (
      'broadcast_queue',
      'voice_future',
      'mobile_future',
      'in_app_future',
      'in_app_notification_preview'
    )
  ) NOT VALID;

COMMIT;
