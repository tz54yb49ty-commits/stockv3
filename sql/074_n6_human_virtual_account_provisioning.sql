-- N6 human virtual-account provisioning contract.
-- DO NOT EXECUTE without a separate migration/deployment gate.
-- N6-only: creates no proposal/order/trade/position/lot/outbox rows.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $preflight$
DECLARE
  required_relation regclass;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '074 owner migration identity rejected';
  END IF;

  FOREACH required_relation IN ARRAY ARRAY[
    'public.user_account'::regclass,
    'public.n6_principal'::regclass,
    'public.n6_principal_account'::regclass,
    'public.n6_virtual_account'::regclass,
    'public.n6_virtual_cash_ledger'::regclass,
    'public.n6_virtual_cash_snapshot'::regclass
  ]
  LOOP
    IF required_relation IS NULL THEN
      RAISE EXCEPTION '074 required relation missing';
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'n6_btrack_web'
  ) THEN
    RAISE EXCEPTION '074 required n6_btrack_web role missing';
  END IF;

  IF pg_catalog.to_regprocedure(
       'public.n6_provision_human_virtual_account(bigint)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '074 provisioning function already exists';
  END IF;
END;
$preflight$;

CREATE FUNCTION public.n6_provision_human_virtual_account(
  p_principal_id bigint
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  v_account public.n6_virtual_account%ROWTYPE;
  v_account_count bigint;
  v_account_id bigint;
  v_current_snapshot_count bigint;
  v_initial_ledger_count bigint;
  v_initial_ledger_id bigint;
  v_initial_snapshot_count bigint;
  v_initial_snapshot_id bigint;
  v_mapping public.n6_principal_account%ROWTYPE;
  v_mapping_count bigint;
  v_principal public.n6_principal%ROWTYPE;
  v_trade_date integer := pg_catalog.to_char(CURRENT_DATE, 'YYYYMMDD')::integer;
  v_user public.user_account%ROWTYPE;
  c_initial_cash constant numeric(24, 4) := 100000000.0000;
  c_policy_hash constant text :=
    '2c121818a66dc7b4d56c85a421e76c5e81be56fb85e8d446a16705fed7a50fd5';
  c_policy_version constant text :=
    'n6_human_virtual_account_provisioning_074_policy_v1';
  c_run_id constant text :=
    'n6_human_virtual_account_provisioning_074_v1';
  v_provenance jsonb;
BEGIN
  IF p_principal_id IS NULL OR p_principal_id <= 0 THEN
    RAISE EXCEPTION '074 invalid principal_id';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      pg_catalog.format(
        'n6_human_virtual_account_provisioning_074:principal:%s',
        p_principal_id
      ),
      0
    )
  );

  SELECT principal.*
    INTO v_principal
  FROM public.n6_principal principal
  WHERE principal.principal_id = p_principal_id
  FOR UPDATE;

  IF NOT FOUND
     OR v_principal.principal_type IS DISTINCT FROM 'human_user'
     OR v_principal.principal_status IS DISTINCT FROM 'active'
     OR v_principal.owner_user_id IS NULL THEN
    RAISE EXCEPTION '074 active human principal invariant failed for %',
      p_principal_id;
  END IF;

  SELECT user_row.*
    INTO v_user
  FROM public.user_account user_row
  WHERE user_row.user_id = v_principal.owner_user_id
  FOR UPDATE;

  IF NOT FOUND
     OR v_user.status IS DISTINCT FROM 'active'
     OR v_user.role IS DISTINCT FROM 'user' THEN
    RAISE EXCEPTION '074 active human owner invariant failed for %',
      p_principal_id;
  END IF;

  v_provenance := pg_catalog.jsonb_build_object(
    'migration_gate', '074',
    'migration_run_id', c_run_id,
    'policy_version', c_policy_version,
    'policy_hash', c_policy_hash,
    'principal_id', p_principal_id,
    'user_id', v_user.user_id
  );

  SELECT pg_catalog.count(*), pg_catalog.min(account.virtual_account_id)
    INTO v_account_count, v_account_id
  FROM public.n6_virtual_account account
  WHERE account.principal_id = p_principal_id;

  SELECT pg_catalog.count(*)
    INTO v_mapping_count
  FROM public.n6_principal_account mapping
  WHERE mapping.principal_id = p_principal_id;

  IF v_account_count = 1 AND v_mapping_count = 1 THEN
    SELECT account.*
      INTO STRICT v_account
    FROM public.n6_virtual_account account
    WHERE account.virtual_account_id = v_account_id;

    SELECT mapping.*
      INTO STRICT v_mapping
    FROM public.n6_principal_account mapping
    WHERE mapping.principal_id = p_principal_id;

    IF v_account.principal_type IS DISTINCT FROM 'human_user'
       OR v_account.virtual_account_status IS DISTINCT FROM 'active'
       OR v_account.base_currency IS DISTINCT FROM 'CNY'
       OR v_account.initial_cash IS DISTINCT FROM c_initial_cash
       OR v_account.current_cash_snapshot_id IS NULL
       OR v_mapping.virtual_account_id IS DISTINCT FROM v_account.virtual_account_id
       OR v_mapping.account_type IS DISTINCT FROM 'virtual'
       OR v_mapping.virtual_account_source IS DISTINCT FROM 'future_virtual_account'
       OR v_mapping.account_status IS DISTINCT FROM 'active'
       OR (SELECT pg_catalog.count(*)
           FROM public.n6_principal_account account_mapping
           WHERE account_mapping.virtual_account_id = v_account.virtual_account_id) <> 1 THEN
      RAISE EXCEPTION '074 existing account chain drifted for principal %',
        p_principal_id;
    END IF;

    SELECT pg_catalog.count(*)
      INTO v_current_snapshot_count
    FROM public.n6_virtual_cash_snapshot snapshot
    JOIN public.n6_virtual_cash_ledger ledger
      ON ledger.cash_ledger_id = snapshot.source_ledger_max_id
     AND ledger.virtual_account_id = snapshot.virtual_account_id
    WHERE snapshot.cash_snapshot_id = v_account.current_cash_snapshot_id
      AND snapshot.virtual_account_id = v_account.virtual_account_id
      AND snapshot.snapshot_status = 'active';

    SELECT pg_catalog.count(*), pg_catalog.min(ledger.cash_ledger_id)
      INTO v_initial_ledger_count, v_initial_ledger_id
    FROM public.n6_virtual_cash_ledger ledger
    WHERE ledger.virtual_account_id = v_account.virtual_account_id
      AND ledger.ledger_type = 'initial_deposit'
      AND ledger.amount = c_initial_cash
      AND ledger.currency = 'CNY';

    SELECT pg_catalog.count(*), pg_catalog.min(snapshot.cash_snapshot_id)
      INTO v_initial_snapshot_count, v_initial_snapshot_id
    FROM public.n6_virtual_cash_snapshot snapshot
    WHERE snapshot.virtual_account_id = v_account.virtual_account_id
      AND snapshot.available_cash = c_initial_cash
      AND snapshot.frozen_cash = 0.0000
      AND snapshot.total_cash = c_initial_cash
      AND snapshot.currency = 'CNY'
      AND snapshot.source_ledger_max_id = v_initial_ledger_id
      AND snapshot.snapshot_status = 'active';

    IF v_current_snapshot_count <> 1
       OR v_initial_ledger_count <> 1
       OR v_initial_snapshot_count <> 1 THEN
      RAISE EXCEPTION '074 existing cash chain drifted for principal %',
        p_principal_id;
    END IF;

    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'noop',
      'principal_id', p_principal_id,
      'user_id', v_user.user_id,
      'virtual_account_id', v_account.virtual_account_id,
      'cash_ledger_id', v_initial_ledger_id,
      'cash_snapshot_id', v_initial_snapshot_id,
      'current_cash_snapshot_id', v_account.current_cash_snapshot_id,
      'initial_cash', c_initial_cash,
      'proposal_rows_created', 0,
      'order_rows_created', 0,
      'trade_rows_created', 0,
      'position_rows_created', 0,
      'lot_rows_created', 0,
      'outbox_rows_created', 0
    );
  END IF;

  IF v_account_count <> 0 OR v_mapping_count <> 0 THEN
    RAISE EXCEPTION
      '074 partial or duplicate account chain blocked for principal %: accounts %, mappings %',
      p_principal_id,
      v_account_count,
      v_mapping_count;
  END IF;

  INSERT INTO public.n6_virtual_account (
    principal_id,
    principal_type,
    account_name,
    virtual_account_status,
    base_currency,
    initial_cash,
    run_id,
    policy_version,
    policy_hash,
    rollback_scope,
    source_lineage_json,
    quality_status
  )
  VALUES (
    p_principal_id,
    'human_user',
    pg_catalog.format('Human User %s Virtual Account', p_principal_id),
    'active',
    'CNY',
    c_initial_cash,
    c_run_id,
    c_policy_version,
    c_policy_hash,
    c_run_id,
    v_provenance || pg_catalog.jsonb_build_object(
      'operation', 'human_virtual_account'
    ),
    'passed'
  )
  RETURNING virtual_account_id INTO v_account_id;

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
    v_account_id,
    'initial_deposit',
    c_initial_cash,
    'CNY',
    v_trade_date,
    'n6_human_virtual_account_provisioning_074',
    pg_catalog.format('074:principal:%s:initial_deposit', p_principal_id),
    c_run_id,
    c_policy_version,
    c_policy_hash,
    c_run_id,
    v_provenance || pg_catalog.jsonb_build_object(
      'operation', 'human_initial_deposit'
    ),
    'passed'
  )
  RETURNING cash_ledger_id INTO v_initial_ledger_id;

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
    v_account_id,
    v_trade_date,
    c_initial_cash,
    0.0000,
    c_initial_cash,
    'CNY',
    v_initial_ledger_id,
    'active',
    c_run_id,
    c_policy_version,
    c_policy_hash,
    c_run_id,
    v_provenance || pg_catalog.jsonb_build_object(
      'operation', 'human_initial_snapshot'
    ),
    'passed'
  )
  RETURNING cash_snapshot_id INTO v_initial_snapshot_id;

  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = v_initial_snapshot_id,
      updated_at = pg_catalog.now()
  WHERE virtual_account_id = v_account_id
    AND current_cash_snapshot_id IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION '074 current cash pointer initialization failed';
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
    p_principal_id,
    'virtual',
    v_account_id,
    'future_virtual_account',
    'active',
    c_policy_version,
    c_policy_hash,
    v_provenance || pg_catalog.jsonb_build_object(
      'operation', 'human_principal_account_mapping'
    )
  );

  IF (SELECT pg_catalog.count(*) FROM public.n6_virtual_account account
      WHERE account.principal_id = p_principal_id) <> 1
     OR (SELECT pg_catalog.count(*) FROM public.n6_principal_account mapping
         WHERE mapping.principal_id = p_principal_id
           AND mapping.virtual_account_id = v_account_id) <> 1
     OR (SELECT pg_catalog.count(*) FROM public.n6_virtual_cash_ledger ledger
         WHERE ledger.virtual_account_id = v_account_id) <> 1
     OR (SELECT pg_catalog.count(*) FROM public.n6_virtual_cash_snapshot snapshot
         WHERE snapshot.virtual_account_id = v_account_id) <> 1 THEN
    RAISE EXCEPTION '074 created account chain invariant failed';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'created',
    'principal_id', p_principal_id,
    'user_id', v_user.user_id,
    'virtual_account_id', v_account_id,
    'cash_ledger_id', v_initial_ledger_id,
    'cash_snapshot_id', v_initial_snapshot_id,
    'current_cash_snapshot_id', v_initial_snapshot_id,
    'initial_cash', c_initial_cash,
    'proposal_rows_created', 0,
    'order_rows_created', 0,
    'trade_rows_created', 0,
    'position_rows_created', 0,
    'lot_rows_created', 0,
    'outbox_rows_created', 0
  );
END;
$function$;

ALTER FUNCTION public.n6_provision_human_virtual_account(bigint)
  OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION public.n6_provision_human_virtual_account(bigint)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_provision_human_virtual_account(bigint)
  TO n6_btrack_web;

COMMENT ON FUNCTION public.n6_provision_human_virtual_account(bigint) IS
  '074 fixed N6 human virtual-account provisioning; atomic, idempotent, fail-closed, no trade/outbox side effects';

COMMIT;
