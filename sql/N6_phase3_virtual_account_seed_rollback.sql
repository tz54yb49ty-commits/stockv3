-- N6 Phase 3 admin virtual account seed rollback.
-- Do not execute without an explicit rollback gate.
-- Scope: delete only rows created by seed_run_id
-- n6_phase3_virtual_account_seed_20260605_v1.

BEGIN;

SET n6.phase3_virtual_account_seed_run_id = 'n6_phase3_virtual_account_seed_20260605_v1';

DO $$
DECLARE
  target_seed_run_id TEXT := current_setting('n6.phase3_virtual_account_seed_run_id', true);
  ref_count BIGINT;
BEGIN
  IF target_seed_run_id IS DISTINCT FROM 'n6_phase3_virtual_account_seed_20260605_v1' THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: unexpected seed_run_id %', target_seed_run_id;
  END IF;

  SELECT count(*) INTO ref_count
  FROM n6_virtual_order
  WHERE run_id = target_seed_run_id
     OR rollback_scope = target_seed_run_id
     OR virtual_account_id IN (
       SELECT virtual_account_id
       FROM n6_virtual_account
       WHERE run_id = target_seed_run_id OR rollback_scope = target_seed_run_id
     );
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_virtual_order refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM n6_virtual_trade
  WHERE run_id = target_seed_run_id
     OR rollback_scope = target_seed_run_id
     OR virtual_account_id IN (
       SELECT virtual_account_id
       FROM n6_virtual_account
       WHERE run_id = target_seed_run_id OR rollback_scope = target_seed_run_id
     );
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_virtual_trade refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM n6_virtual_position
  WHERE run_id = target_seed_run_id
     OR rollback_scope = target_seed_run_id
     OR virtual_account_id IN (
       SELECT virtual_account_id
       FROM n6_virtual_account
       WHERE run_id = target_seed_run_id OR rollback_scope = target_seed_run_id
     );
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_virtual_position refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM n6_virtual_position_event
  WHERE run_id = target_seed_run_id
     OR rollback_scope = target_seed_run_id
     OR virtual_account_id IN (
       SELECT virtual_account_id
       FROM n6_virtual_account
       WHERE run_id = target_seed_run_id OR rollback_scope = target_seed_run_id
     );
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_virtual_position_event refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM n6_virtual_pnl_snapshot
  WHERE run_id = target_seed_run_id
     OR rollback_scope = target_seed_run_id
     OR virtual_account_id IN (
       SELECT virtual_account_id
       FROM n6_virtual_account
       WHERE run_id = target_seed_run_id OR rollback_scope = target_seed_run_id
     );
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_virtual_pnl_snapshot refs=%', ref_count;
  END IF;

  IF to_regclass('public.n6_ai_decision') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_ai_decision WHERE run_id = $1 OR rollback_scope = $1'
      INTO ref_count
      USING target_seed_run_id;
    IF ref_count <> 0 THEN
      RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_ai_decision refs=%', ref_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_ai_evaluation') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_ai_evaluation WHERE run_id = $1 OR rollback_scope = $1'
      INTO ref_count
      USING target_seed_run_id;
    IF ref_count <> 0 THEN
      RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_ai_evaluation refs=%', ref_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_leaderboard') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_leaderboard WHERE run_id = $1 OR rollback_scope = $1'
      INTO ref_count
      USING target_seed_run_id;
    IF ref_count <> 0 THEN
      RAISE EXCEPTION 'N6 Phase 3 virtual account seed rollback blocked: linked n6_leaderboard refs=%', ref_count;
    END IF;
  END IF;
END $$;

DELETE FROM n6_virtual_cash_snapshot
WHERE run_id = current_setting('n6.phase3_virtual_account_seed_run_id')
   OR rollback_scope = current_setting('n6.phase3_virtual_account_seed_run_id')
   OR virtual_account_id IN (
     SELECT virtual_account_id
     FROM n6_virtual_account
     WHERE run_id = current_setting('n6.phase3_virtual_account_seed_run_id')
        OR rollback_scope = current_setting('n6.phase3_virtual_account_seed_run_id')
   );

DELETE FROM n6_virtual_cash_ledger
WHERE run_id = current_setting('n6.phase3_virtual_account_seed_run_id')
   OR rollback_scope = current_setting('n6.phase3_virtual_account_seed_run_id')
   OR virtual_account_id IN (
     SELECT virtual_account_id
     FROM n6_virtual_account
     WHERE run_id = current_setting('n6.phase3_virtual_account_seed_run_id')
        OR rollback_scope = current_setting('n6.phase3_virtual_account_seed_run_id')
   );

DELETE FROM n6_virtual_account
WHERE run_id = current_setting('n6.phase3_virtual_account_seed_run_id')
   OR rollback_scope = current_setting('n6.phase3_virtual_account_seed_run_id');

COMMIT;
