-- N6 Phase 2 owner/principal seed rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: delete only rows created by the configured seed_run_id.
-- Boundary: no 036/037 schema or permission drop, no N5 outbox change, no
-- N1-N6 fact rollback, no worker, no delivery/push/voice/mobile/sim/position
-- or real trade.

BEGIN;

DO $$
DECLARE
  v_seed_run_id TEXT := current_setting('n6.seed_run_id', true);
  v_seed_principal_ids BIGINT[];
  v_seed_account_ids BIGINT[];
  v_count BIGINT;
  v_table TEXT;
  v_column TEXT;
  v_optional_checks TEXT[][] := ARRAY[
    ARRAY['n6_virtual_order', 'principal_id'],
    ARRAY['n6_virtual_order', 'account_id'],
    ARRAY['n6_virtual_position', 'principal_id'],
    ARRAY['n6_virtual_position', 'account_id'],
    ARRAY['n6_ai_decision', 'principal_id'],
    ARRAY['n6_ai_decision', 'account_id'],
    ARRAY['n6_leaderboard_entry', 'principal_id'],
    ARRAY['n6_leaderboard_snapshot', 'principal_id'],
    ARRAY['n6_voice_delivery', 'principal_id'],
    ARRAY['n6_mobile_delivery', 'principal_id']
  ];
  v_check TEXT[];
BEGIN
  IF v_seed_run_id IS NULL OR v_seed_run_id = '' THEN
    RAISE EXCEPTION 'rollback blocked: n6.seed_run_id is required';
  END IF;

  IF v_seed_run_id <> 'n6_phase2_owner_principal_initialization_20260605_v1' THEN
    RAISE EXCEPTION 'rollback blocked: unexpected seed_run_id %', v_seed_run_id;
  END IF;

  SELECT coalesce(array_agg(principal_id), ARRAY[]::BIGINT[])
  INTO v_seed_principal_ids
  FROM n6_principal
  WHERE principal_policy_json->>'seed_run_id' = v_seed_run_id;

  SELECT coalesce(array_agg(account_id), ARRAY[]::BIGINT[])
  INTO v_seed_account_ids
  FROM n6_principal_account
  WHERE account_policy_json->>'seed_run_id' = v_seed_run_id;

  SELECT count(*) INTO v_count
  FROM n6_watchlist_ownership
  WHERE principal_id = ANY(v_seed_principal_ids);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: linked watchlist ownership refs exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_strategy
  WHERE principal_id = ANY(v_seed_principal_ids)
    AND coalesce(strategy_payload_json->>'seed_run_id', '') <> v_seed_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: non-seed strategy refs exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_ai_user
  WHERE principal_id = ANY(v_seed_principal_ids)
    AND coalesce(readable_scope_policy->>'seed_run_id', '') <> v_seed_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: non-seed ai user refs exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_principal_account
  WHERE principal_id = ANY(v_seed_principal_ids)
    AND coalesce(account_policy_json->>'seed_run_id', '') <> v_seed_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: non-seed principal account refs exist: %', v_count;
  END IF;

  FOREACH v_check SLICE 1 IN ARRAY v_optional_checks LOOP
    v_table := v_check[1];
    v_column := v_check[2];

    IF to_regclass('public.' || v_table) IS NOT NULL
       AND EXISTS (
         SELECT 1
         FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = v_table
           AND column_name = v_column
       ) THEN
      IF v_column = 'principal_id' THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE %I = ANY($1)', v_table, v_column)
        INTO v_count
        USING v_seed_principal_ids;
      ELSIF v_column = 'account_id' THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE %I = ANY($1)', v_table, v_column)
        INTO v_count
        USING v_seed_account_ids;
      ELSE
        EXECUTE format('SELECT count(*) FROM %I WHERE %I IS NOT NULL', v_table, v_column)
        INTO v_count;
      END IF;

      IF v_count <> 0 THEN
        RAISE EXCEPTION 'rollback blocked: linked optional refs exist in %.% count=%', v_table, v_column, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM n6_strategy
WHERE strategy_payload_json->>'seed_run_id' = current_setting('n6.seed_run_id');

DELETE FROM n6_ai_user
WHERE readable_scope_policy->>'seed_run_id' = current_setting('n6.seed_run_id');

DELETE FROM n6_principal_account
WHERE account_policy_json->>'seed_run_id' = current_setting('n6.seed_run_id');

DELETE FROM n6_principal
WHERE principal_policy_json->>'seed_run_id' = current_setting('n6.seed_run_id');

COMMIT;
