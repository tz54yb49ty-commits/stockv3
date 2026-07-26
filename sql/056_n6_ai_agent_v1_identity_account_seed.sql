-- N6 AI Agent v1 deterministic identity, strategy, and virtual-account seed.
-- Execute only after 055 schema/authority migration and an approved DB canary gate.

BEGIN;

LOCK TABLE
  public.n6_principal,
  public.n6_ai_user,
  public.n6_strategy,
  public.n6_principal_account,
  public.n6_virtual_account,
  public.n6_virtual_cash_ledger,
  public.n6_virtual_cash_snapshot
IN SHARE ROW EXCLUSIVE MODE;

DO $seed$
DECLARE
  marker constant text := '056_n6_ai_agent_v1_identity_account_seed';
  expected_policy_hash constant text :=
    '0d3f739a34e03637ba0be39f7fcae6fedf8b3aea1b3da20513f2c5d5c823a8ed';
  target_trade_date integer;
  target_principal_id bigint;
  target_ai_user_id bigint;
  target_strategy_id bigint;
  target_account_id bigint;
  target_ledger_id bigint;
  target_snapshot_id bigint;
  marker_principal_count integer;
  complete_count integer;
  active_ai_principal_count integer;
  active_ai_user_count integer;
  active_ai_strategy_count integer;
  active_ai_account_count integer;
BEGIN
  SELECT max(c.trade_date)::integer
    INTO target_trade_date
  FROM public.common_trade_calendar c
  WHERE c.is_open = true
    AND c.trade_date <= pg_catalog.to_char(
          pg_catalog.now() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
  IF target_trade_date IS NULL THEN
    RAISE EXCEPTION '056 current-or-prior open trade date required';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.user_account u
    WHERE u.user_id = 1
      AND u.role = 'admin'
      AND u.status = 'active'
  ) THEN
    RAISE EXCEPTION '056 active admin user 1 required as registration authority';
  END IF;

  SELECT count(*)
    INTO marker_principal_count
  FROM public.n6_principal p
  WHERE p.principal_type = 'ai_user'
    AND p.principal_policy_json->>'registration_marker' = marker;

  SELECT count(*)
    INTO complete_count
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
  JOIN public.n6_principal_account mapping
    ON mapping.principal_id = p.principal_id
   AND mapping.virtual_account_id = account.virtual_account_id
  JOIN public.n6_virtual_cash_snapshot snapshot
    ON snapshot.cash_snapshot_id = account.current_cash_snapshot_id
   AND snapshot.virtual_account_id = account.virtual_account_id
  JOIN public.n6_virtual_cash_ledger ledger
    ON ledger.cash_ledger_id = snapshot.source_ledger_max_id
   AND ledger.virtual_account_id = account.virtual_account_id
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
    AND strategy.strategy_type = 'ai_generated'
    AND strategy.policy_version = 'n6_ai_agent_v1_strategy_v1'
    AND strategy.policy_hash = expected_policy_hash
    AND strategy.status = 'active'
    AND strategy.visibility = 'public_leaderboard'
    AND strategy.risk_labels @> ARRAY['experimental', 'ai_generated']::text[]
    AND account.account_name = 'N6 AI Investor Virtual Account'
    AND account.virtual_account_status = 'active'
    AND account.base_currency = 'CNY'
    AND account.initial_cash = 100000000.0000
    AND account.run_id = marker
    AND account.policy_version = 'n6_ai_agent_v1_account_policy'
    AND account.policy_hash = expected_policy_hash
    AND account.rollback_scope = marker
    AND account.source_lineage_json->>'registration_marker' = marker
    AND mapping.account_type = 'ai_virtual'
    AND mapping.virtual_account_source = 'future_virtual_account'
    AND mapping.account_status = 'active'
    AND mapping.account_policy_version = 'n6_ai_agent_v1_account_policy'
    AND mapping.account_policy_hash = expected_policy_hash
    AND mapping.account_policy_json->>'registration_marker' = marker
    AND snapshot.snapshot_status = 'active'
    AND snapshot.available_cash = 100000000.0000
    AND snapshot.frozen_cash = 0.0000
    AND snapshot.total_cash = 100000000.0000
    AND snapshot.currency = 'CNY'
    AND snapshot.run_id = marker
    AND snapshot.policy_version = 'n6_ai_agent_v1_account_policy'
    AND snapshot.policy_hash = expected_policy_hash
    AND snapshot.rollback_scope = marker
    AND snapshot.source_lineage_json->>'registration_marker' = marker
    AND ledger.ledger_type = 'initial_deposit'
    AND ledger.amount = 100000000.0000
    AND ledger.currency = 'CNY'
    AND ledger.source_event_type = 'n6_ai_agent_identity_account_seed'
    AND ledger.source_event_id = marker
    AND ledger.run_id = marker
    AND ledger.policy_version = 'n6_ai_agent_v1_account_policy'
    AND ledger.policy_hash = expected_policy_hash
    AND ledger.rollback_scope = marker
    AND ledger.source_lineage_json->>'registration_marker' = marker;

  SELECT count(*)
    INTO active_ai_principal_count
  FROM public.n6_principal p
  WHERE p.principal_type = 'ai_user'
    AND p.principal_status = 'active';

  SELECT count(*)
    INTO active_ai_user_count
  FROM public.n6_ai_user ai
  WHERE ai.status IN ('active', 'sandbox_only');

  SELECT count(*)
    INTO active_ai_strategy_count
  FROM public.n6_strategy strategy
  JOIN public.n6_principal p
    ON p.principal_id = strategy.principal_id
  WHERE p.principal_type = 'ai_user'
    AND strategy.status = 'active';

  SELECT count(*)
    INTO active_ai_account_count
  FROM public.n6_virtual_account account
  WHERE account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active';

  IF marker_principal_count = 1 AND complete_count = 1 THEN
    IF active_ai_principal_count <> 1
       OR active_ai_user_count <> 1
       OR active_ai_strategy_count <> 1
       OR active_ai_account_count <> 1 THEN
      RAISE EXCEPTION
        '056 exact seed is not the unique active AI: principal=% user=% strategy=% account=%',
        active_ai_principal_count,
        active_ai_user_count,
        active_ai_strategy_count,
        active_ai_account_count;
    END IF;
    RETURN;
  END IF;
  IF marker_principal_count <> 0 OR complete_count <> 0 THEN
    RAISE EXCEPTION
      '056 partial or drifted seed state rejected: marker=% complete=%',
      marker_principal_count,
      complete_count;
  END IF;

  IF active_ai_principal_count <> 0
     OR active_ai_user_count <> 0
     OR active_ai_strategy_count <> 0
     OR active_ai_account_count <> 0 THEN
    RAISE EXCEPTION '056 another active or sandbox AI identity already exists';
  END IF;

  INSERT INTO public.n6_principal (
    principal_type,
    owner_user_id,
    principal_status,
    principal_label,
    principal_policy_json
  )
  VALUES (
    'ai_user',
    NULL,
    'active',
    'N6 AI Investor v1',
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'paper_only', true,
      'public_read', true,
      'human_private_data_read', false,
      'real_trade_enabled', false
    )
  )
  RETURNING principal_id INTO target_principal_id;

  INSERT INTO public.n6_ai_user (
    principal_id,
    principal_type,
    ai_name,
    strategy_profile_id,
    status,
    readable_scope_policy,
    readable_scope_policy_version,
    readable_scope_policy_hash,
    created_by_user_id
  )
  VALUES (
    target_principal_id,
    'ai_user',
    'N6 AI Investor',
    NULL,
    'sandbox_only',
    pg_catalog.jsonb_build_object(
      'allowed_sources', pg_catalog.jsonb_build_array(
        'v_n6_stock_condition_display_basis',
        'v_n6_index_condition_display_basis',
        'v_n6_board_condition_display_basis',
        'user_projection_run',
        'n6_ai_shared_signal_projection',
        'n6_ai_owned_virtual_account'
      ),
      'forbidden_sources', pg_catalog.jsonb_build_array(
        'human_private_scope',
        'human_virtual_account',
        'raw_k',
        'n1_n5_raw_facts',
        'common_event_outbox',
        'common_event_inbox',
        'common_event_checkpoint',
        'direct_market_provider',
        'real_trade_api'
      )
    ),
    'n6_ai_agent_v1_read_scope',
    expected_policy_hash,
    1
  )
  RETURNING ai_user_id INTO target_ai_user_id;

  INSERT INTO public.n6_strategy (
    principal_id,
    strategy_name,
    strategy_type,
    policy_version,
    policy_hash,
    status,
    visibility,
    risk_labels,
    strategy_payload_json,
    created_by_principal_id
  )
  VALUES (
    target_principal_id,
    'N6 AI Conservative Signal Strategy',
    'ai_generated',
    'n6_ai_agent_v1_strategy_v1',
    expected_policy_hash,
    'active',
    'public_leaderboard',
    ARRAY['experimental', 'ai_generated']::text[],
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'tradable_asset_kind', 'stock',
      'allowed_exchanges', pg_catalog.jsonb_build_array('SH', 'SZ'),
      'buy_budget_cny', 300000,
      'max_identity_exposure_cny', 600000,
      'max_gross_exposure_pct', 10,
      'max_daily_new_buys', 10,
      'autonomous_canary_daily_buys', 1,
      'drawdown_pause_pct', 5,
      'risk_adjusted_score',
        'net_return_pct - 1.5*max_drawdown_pct - 0.02*turnover_pct'
    ),
    target_principal_id
  )
  RETURNING strategy_id INTO target_strategy_id;

  UPDATE public.n6_ai_user
  SET strategy_profile_id = target_strategy_id,
      updated_at = pg_catalog.now()
  WHERE ai_user_id = target_ai_user_id
    AND principal_id = target_principal_id
    AND strategy_profile_id IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 AI strategy pointer initialization failed';
  END IF;

  INSERT INTO public.n6_virtual_account (
    principal_id,
    principal_type,
    account_name,
    virtual_account_status,
    base_currency,
    initial_cash,
    current_cash_snapshot_id,
    run_id,
    policy_version,
    policy_hash,
    rollback_scope,
    source_lineage_json,
    quality_status
  )
  VALUES (
    target_principal_id,
    'ai_user',
    'N6 AI Investor Virtual Account',
    'active',
    'CNY',
    100000000.0000,
    NULL,
    marker,
    'n6_ai_agent_v1_account_policy',
    expected_policy_hash,
    marker,
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'ai_user_id', target_ai_user_id,
      'strategy_id', target_strategy_id,
      'paper_only', true
    ),
    'passed'
  )
  RETURNING virtual_account_id INTO target_account_id;

  INSERT INTO public.n6_virtual_cash_ledger (
    virtual_account_id,
    ledger_type,
    amount,
    currency,
    trade_date,
    source_event_type,
    source_event_id,
    run_id,
    policy_version,
    policy_hash,
    rollback_scope,
    source_lineage_json,
    quality_status
  )
  VALUES (
    target_account_id,
    'initial_deposit',
    100000000.0000,
    'CNY',
    target_trade_date,
    'n6_ai_agent_identity_account_seed',
    marker,
    marker,
    'n6_ai_agent_v1_account_policy',
    expected_policy_hash,
    marker,
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'ai_user_id', target_ai_user_id
    ),
    'passed'
  )
  RETURNING cash_ledger_id INTO target_ledger_id;

  INSERT INTO public.n6_virtual_cash_snapshot (
    virtual_account_id,
    trade_date,
    available_cash,
    frozen_cash,
    total_cash,
    currency,
    source_ledger_max_id,
    snapshot_status,
    run_id,
    policy_version,
    policy_hash,
    rollback_scope,
    source_lineage_json,
    quality_status
  )
  VALUES (
    target_account_id,
    target_trade_date,
    100000000.0000,
    0.0000,
    100000000.0000,
    'CNY',
    target_ledger_id,
    'active',
    marker,
    'n6_ai_agent_v1_account_policy',
    expected_policy_hash,
    marker,
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'ai_user_id', target_ai_user_id
    ),
    'passed'
  )
  RETURNING cash_snapshot_id INTO target_snapshot_id;

  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = target_snapshot_id,
      updated_at = pg_catalog.now()
  WHERE virtual_account_id = target_account_id
    AND principal_id = target_principal_id
    AND principal_type = 'ai_user'
    AND current_cash_snapshot_id IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION '056 AI cash pointer initialization failed';
  END IF;

  INSERT INTO public.n6_principal_account (
    principal_id,
    account_type,
    virtual_account_id,
    virtual_account_source,
    account_status,
    account_policy_version,
    account_policy_hash,
    account_policy_json
  )
  VALUES (
    target_principal_id,
    'ai_virtual',
    target_account_id,
    'future_virtual_account',
    'active',
    'n6_ai_agent_v1_account_policy',
    expected_policy_hash,
    pg_catalog.jsonb_build_object(
      'registration_marker', marker,
      'ai_user_id', target_ai_user_id,
      'public_read', true,
      'paper_only', true
    )
  );
END
$seed$;

COMMIT;
