-- N5 full-day trigger-state closed-loop tracking schema rollback draft.
-- Scope: rollback only the additive common_action_tracking_state table.
-- Boundary: do not execute without an explicit rollback execute gate. This
-- rollback is safe only before runtime rows exist in the table.

DO $$
DECLARE
  tracking_row_count BIGINT;
BEGIN
  IF to_regclass('public.common_action_tracking_state') IS NULL THEN
    RAISE NOTICE 'common_action_tracking_state is absent; nothing to rollback';
    RETURN;
  END IF;

  SELECT COUNT(*) INTO tracking_row_count
  FROM common_action_tracking_state;

  IF tracking_row_count <> 0 THEN
    RAISE EXCEPTION
      'common_action_tracking_state rollback blocked: table has % rows; require scoped runtime rollback first',
      tracking_row_count;
  END IF;

  DROP TABLE common_action_tracking_state;
END $$;

