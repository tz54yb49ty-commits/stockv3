-- N6 AI Agent v1 identity/account seed rollback.
-- Deletes only an unused, exact 056 seed. AI business history is preserved by blocking.

BEGIN;

LOCK TABLE
  public.n6_principal,
  public.n6_ai_user,
  public.n6_strategy,
  public.n6_principal_account,
  public.n6_virtual_account,
  public.n6_virtual_cash_ledger,
  public.n6_virtual_cash_snapshot,
  public.n6_virtual_trade_proposal,
  public.n6_virtual_order,
  public.n6_virtual_trade,
  public.n6_virtual_position,
  public.n6_virtual_position_event,
  public.n6_virtual_position_lot,
  public.n6_virtual_pnl_snapshot,
  public.n6_virtual_quote_run,
  public.n6_ai_context_snapshot,
  public.n6_ai_decision_run,
  public.n6_ai_decision,
  public.n6_ai_daily_summary,
  public.n6_ai_strategy_evaluation
IN SHARE ROW EXCLUSIVE MODE;

DO $rollback$
DECLARE
  marker constant text := '056_n6_ai_agent_v1_identity_account_seed';
  expected_policy_hash constant text :=
    '0d3f739a34e03637ba0be39f7fcae6fedf8b3aea1b3da20513f2c5d5c823a8ed';
  target_principal_id bigint;
  target_ai_user_id bigint;
  target_strategy_id bigint;
  target_account_id bigint;
  target_ledger_id bigint;
  target_snapshot_id bigint;
  dependency_count bigint;
  principal_mapping_count bigint;
  principal_strategy_count bigint;
  principal_account_count bigint;
  account_ledger_count bigint;
  account_snapshot_count bigint;
BEGIN
  SELECT p.principal_id, ai.ai_user_id, strategy.strategy_id,
         account.virtual_account_id, ledger.cash_ledger_id,
         snapshot.cash_snapshot_id
    INTO target_principal_id, target_ai_user_id, target_strategy_id,
         target_account_id, target_ledger_id, target_snapshot_id
  FROM public.n6_principal p
  JOIN public.n6_ai_user ai
    ON ai.principal_id = p.principal_id
   AND ai.principal_type = p.principal_type
  JOIN public.n6_strategy strategy
    ON strategy.strategy_id = ai.strategy_profile_id
   AND strategy.principal_id = p.principal_id
  JOIN public.n6_virtual_account account
    ON account.principal_id = p.principal_id
   AND account.principal_type = p.principal_type
  JOIN public.n6_virtual_cash_snapshot snapshot
    ON snapshot.cash_snapshot_id = account.current_cash_snapshot_id
  JOIN public.n6_virtual_cash_ledger ledger
    ON ledger.cash_ledger_id = snapshot.source_ledger_max_id
  WHERE p.principal_type = 'ai_user'
    AND p.owner_user_id IS NULL
    AND p.principal_status = 'active'
    AND p.principal_label = 'N6 AI Investor v1'
    AND p.principal_policy_json->>'registration_marker' = marker
    AND ai.ai_name = 'N6 AI Investor'
    AND ai.status = 'sandbox_only'
    AND ai.readable_scope_policy_version = 'n6_ai_agent_v1_read_scope'
    AND ai.readable_scope_policy_hash = expected_policy_hash
    AND strategy.strategy_name = 'N6 AI Conservative Signal Strategy'
    AND strategy.policy_version = 'n6_ai_agent_v1_strategy_v1'
    AND strategy.policy_hash = expected_policy_hash
    AND strategy.status = 'active'
    AND account.account_name = 'N6 AI Investor Virtual Account'
    AND account.initial_cash = 100000000.0000
    AND account.run_id = marker
    AND account.policy_hash = expected_policy_hash
    AND ledger.ledger_type = 'initial_deposit'
    AND ledger.amount = 100000000.0000
    AND ledger.run_id = marker
    AND snapshot.available_cash = 100000000.0000
    AND snapshot.frozen_cash = 0.0000
    AND snapshot.total_cash = 100000000.0000
    AND snapshot.run_id = marker;

  IF target_principal_id IS NULL THEN
    IF NOT EXISTS (
      SELECT 1 FROM public.n6_principal p
      WHERE p.principal_policy_json->>'registration_marker' = marker
    ) THEN
      RETURN;
    END IF;
    RAISE EXCEPTION '056 rollback exact seed state not found';
  END IF;

  SELECT count(*)
    INTO principal_mapping_count
  FROM public.n6_principal_account mapping
  WHERE mapping.principal_id = target_principal_id
     OR mapping.virtual_account_id = target_account_id;
  IF principal_mapping_count <> 1 THEN
    RAISE EXCEPTION
      '056 rollback blocked by extra or missing principal-account mappings: %',
      principal_mapping_count;
  END IF;

  SELECT count(*)
    INTO principal_strategy_count
  FROM public.n6_strategy strategy
  WHERE strategy.principal_id = target_principal_id
     OR strategy.created_by_principal_id = target_principal_id;
  IF principal_strategy_count <> 1 THEN
    RAISE EXCEPTION
      '056 rollback blocked by extra or missing target-principal strategies: %',
      principal_strategy_count;
  END IF;

  SELECT count(*)
    INTO principal_account_count
  FROM public.n6_virtual_account account
  WHERE account.principal_id = target_principal_id;
  IF principal_account_count <> 1 THEN
    RAISE EXCEPTION
      '056 rollback blocked by extra or missing target-principal accounts: %',
      principal_account_count;
  END IF;

  SELECT count(*)
    INTO account_ledger_count
  FROM public.n6_virtual_cash_ledger ledger
  WHERE ledger.virtual_account_id = target_account_id;
  IF account_ledger_count <> 1 THEN
    RAISE EXCEPTION
      '056 rollback blocked by extra or missing cash ledger history: %',
      account_ledger_count;
  END IF;

  SELECT count(*)
    INTO account_snapshot_count
  FROM public.n6_virtual_cash_snapshot snapshot
  WHERE snapshot.virtual_account_id = target_account_id;
  IF account_snapshot_count <> 1 THEN
    RAISE EXCEPTION
      '056 rollback blocked by extra or missing cash snapshot history: %',
      account_snapshot_count;
  END IF;

  SELECT count(*)
    INTO dependency_count
  FROM (
    SELECT 1 FROM public.n6_virtual_trade_proposal
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_order
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_event
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_lot
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_pnl_snapshot
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_quote_run
      WHERE principal_id = target_principal_id
    UNION ALL
    SELECT 1 FROM public.n6_ai_context_snapshot
      WHERE ai_user_id = target_ai_user_id
    UNION ALL
    SELECT 1 FROM public.n6_ai_decision_run
      WHERE ai_user_id = target_ai_user_id
    UNION ALL
    SELECT 1 FROM public.n6_ai_decision
      WHERE ai_user_id = target_ai_user_id
    UNION ALL
    SELECT 1 FROM public.n6_ai_daily_summary
      WHERE ai_user_id = target_ai_user_id
    UNION ALL
    SELECT 1 FROM public.n6_ai_strategy_evaluation
      WHERE ai_user_id = target_ai_user_id
  ) dependencies;
  IF dependency_count <> 0 THEN
    RAISE EXCEPTION
      '056 rollback blocked by preserved AI business history: %',
      dependency_count;
  END IF;

  DELETE FROM public.n6_principal_account
  WHERE principal_id = target_principal_id
    AND account_type = 'ai_virtual'
    AND virtual_account_id = target_account_id
    AND account_policy_hash = expected_policy_hash
    AND account_policy_json->>'registration_marker' = marker;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback principal-account mapping drifted';
  END IF;

  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = NULL,
      updated_at = pg_catalog.now()
  WHERE virtual_account_id = target_account_id
    AND current_cash_snapshot_id = target_snapshot_id
    AND run_id = marker;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback account cash pointer drifted';
  END IF;

  DELETE FROM public.n6_virtual_cash_snapshot
  WHERE cash_snapshot_id = target_snapshot_id
    AND virtual_account_id = target_account_id
    AND run_id = marker
    AND policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback cash snapshot drifted';
  END IF;

  DELETE FROM public.n6_virtual_cash_ledger
  WHERE cash_ledger_id = target_ledger_id
    AND virtual_account_id = target_account_id
    AND run_id = marker
    AND policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback cash ledger drifted';
  END IF;

  DELETE FROM public.n6_virtual_account
  WHERE virtual_account_id = target_account_id
    AND principal_id = target_principal_id
    AND principal_type = 'ai_user'
    AND run_id = marker
    AND policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback virtual account drifted';
  END IF;

  UPDATE public.n6_ai_user
  SET strategy_profile_id = NULL,
      updated_at = pg_catalog.now()
  WHERE ai_user_id = target_ai_user_id
    AND strategy_profile_id = target_strategy_id
    AND readable_scope_policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback strategy pointer drifted';
  END IF;

  DELETE FROM public.n6_strategy
  WHERE strategy_id = target_strategy_id
    AND principal_id = target_principal_id
    AND policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback strategy drifted';
  END IF;

  DELETE FROM public.n6_ai_user
  WHERE ai_user_id = target_ai_user_id
    AND principal_id = target_principal_id
    AND status = 'sandbox_only'
    AND readable_scope_policy_hash = expected_policy_hash;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback AI user drifted';
  END IF;

  DELETE FROM public.n6_principal
  WHERE principal_id = target_principal_id
    AND principal_type = 'ai_user'
    AND owner_user_id IS NULL
    AND principal_policy_json->>'registration_marker' = marker;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 rollback principal drifted';
  END IF;
END
$rollback$;

COMMIT;
