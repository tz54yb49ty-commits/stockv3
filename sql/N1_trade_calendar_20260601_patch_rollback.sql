-- N1 trade calendar 20260601 patch rollback.
-- Scope: trade_calendar_20260601_patch_v1.
--
-- This rollback removes only the 20260601 calendar patch metadata and row.
-- It intentionally refuses to run after N2/N3 or downstream runtime rows have
-- referenced 20260601, because removing the calendar row would invalidate an
-- already-built opening-prep lineage.
--
-- It does not touch daily facts, condition source, condition business rows,
-- Parquet, outbox/inbox/checkpoint, N4/N5/N6, worker, old system, or trading
-- state.

BEGIN;

DO $$
DECLARE
  v_downstream_refs integer := 0;
BEGIN
  IF to_regclass('public.common_condition_run') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM common_condition_run
      WHERE source_trade_date = '20260601'
         OR for_trade_date = '20260601'
         OR prev_trade_date = '20260601'
    $sql$ INTO v_downstream_refs;
  END IF;

  IF v_downstream_refs = 0 AND to_regclass('public.common_market_data_run') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM common_market_data_run
      WHERE for_trade_date = '20260601'
         OR run_id LIKE '%20260601%'
    $sql$ INTO v_downstream_refs;
  END IF;

  IF v_downstream_refs = 0 AND to_regclass('public.common_trigger_run') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM common_trigger_run
      WHERE run_id LIKE '%20260601%'
    $sql$ INTO v_downstream_refs;
  END IF;

  IF v_downstream_refs = 0 AND to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM common_action_run
      WHERE run_id LIKE '%20260601%'
    $sql$ INTO v_downstream_refs;
  END IF;

  IF v_downstream_refs = 0 AND to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $sql$
      SELECT count(*)
      FROM user_projection_run
      WHERE user_projection_run_id LIKE '%20260601%'
    $sql$ INTO v_downstream_refs;
  END IF;

  IF v_downstream_refs > 0 THEN
    RAISE EXCEPTION 'Refusing 20260601 calendar rollback: downstream refs exist, count=%', v_downstream_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND scope_key = 'SSE:20260601'
  AND source_batch_id = 'trade_calendar_20260601_patch_v1'
  AND source_version = 'trade_calendar_20260601_patch_v1';

DELETE FROM common_trade_calendar
WHERE trade_date = '20260601'
  AND source_batch_id = 'trade_calendar_20260601_patch_v1'
  AND source_version = 'trade_calendar_20260601_patch_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'trade_calendar_20260601_patch_v1'
   OR source_version = 'trade_calendar_20260601_patch_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'trade_calendar_20260601_patch_v1'
   OR source_version = 'trade_calendar_20260601_patch_v1';

COMMIT;
