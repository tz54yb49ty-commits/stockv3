-- Rollback for N5 multi action window fact grain migration.
--
-- This rollback restores the old one-action-per-trigger unique constraints.
-- It is intentionally fail-closed: if any table already contains multiple rows
-- for the old grain (run_id, source_trigger_event_id, action_type), rollback
-- raises and does not recreate the old unique constraint.

BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.stock_action_fact
    GROUP BY run_id, source_trigger_event_id, action_type
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'N5 multi action rollback blocked: stock_action_fact has duplicate old action grain rows';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.index_action_fact
    GROUP BY run_id, source_trigger_event_id, action_type
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'N5 multi action rollback blocked: index_action_fact has duplicate old action grain rows';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.board_action_fact
    GROUP BY run_id, source_trigger_event_id, action_type
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'N5 multi action rollback blocked: board_action_fact has duplicate old action grain rows';
  END IF;
END $$;

DROP INDEX IF EXISTS public.idx_stock_action_fact_source_trigger_action_lookup;
DROP INDEX IF EXISTS public.idx_index_action_fact_source_trigger_action_lookup;
DROP INDEX IF EXISTS public.idx_board_action_fact_source_trigger_action_lookup;

ALTER TABLE public.stock_action_fact
  ADD CONSTRAINT stock_action_fact_run_id_source_trigger_event_id_action_typ_key
  UNIQUE (run_id, source_trigger_event_id, action_type);

ALTER TABLE public.index_action_fact
  ADD CONSTRAINT index_action_fact_run_id_source_trigger_event_id_action_typ_key
  UNIQUE (run_id, source_trigger_event_id, action_type);

ALTER TABLE public.board_action_fact
  ADD CONSTRAINT board_action_fact_run_id_source_trigger_event_id_action_typ_key
  UNIQUE (run_id, source_trigger_event_id, action_type);

COMMIT;
