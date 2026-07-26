-- N6-only multi-user virtual-account bootstrap 047.
-- Execute only through the separately approved owner-migration one-shot gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_btrack_virtual_account_bootstrap_047_v1', 0)
);

LOCK TABLE
  public.user_account,
  public.n6_principal,
  public.n6_virtual_account,
  public.n6_virtual_cash_ledger,
  public.n6_virtual_cash_snapshot,
  public.n6_principal_account,
  public.n6_virtual_trade_proposal,
  public.n6_virtual_order,
  public.n6_virtual_trade,
  public.n6_virtual_position,
  public.n6_virtual_position_lot,
  public.n6_virtual_position_event,
  public.n6_virtual_pnl_snapshot
IN SHARE ROW EXCLUSIVE MODE;

DO $bootstrap$
DECLARE
  admin_account public.n6_virtual_account%ROWTYPE;
  admin_active_snapshot public.n6_virtual_cash_snapshot%ROWTYPE;
  admin_initial_snapshot public.n6_virtual_cash_snapshot%ROWTYPE;
  admin_adjustment_id bigint;
  admin_adjustment_count bigint;
  admin_dependency_count bigint;
  admin_initial_ledger public.n6_virtual_cash_ledger%ROWTYPE;
  admin_ledger_count bigint;
  admin_snapshot_count bigint;
  completed_human_count bigint;
  human_account_id bigint;
  human_cash_ledger_id bigint;
  human_cash_snapshot_id bigint;
  human_principal_id bigint;
  principal_mismatch_count bigint;
  target_trade_date integer := pg_catalog.to_char(CURRENT_DATE, 'YYYYMMDD')::integer;
  provenance constant jsonb := pg_catalog.jsonb_build_object(
    'bootstrap_gate', '047',
    'bootstrap_run_id', 'n6_btrack_virtual_account_bootstrap_047_v1',
    'policy_version', 'n6_btrack_virtual_account_bootstrap_047_policy_v1',
    'policy_hash', '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b'
  );
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(d.datdba)
       FROM pg_catalog.pg_database d
       WHERE d.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '047 owner migration identity rejected';
  END IF;

  PERFORM p.principal_id
  FROM public.n6_principal p
  WHERE p.principal_id IN (1, 3, 4, 5, 6)
  ORDER BY p.principal_id
  FOR UPDATE;

  WITH expected(principal_id, principal_type, owner_user_id, user_role) AS (
    VALUES
      (1::bigint, 'admin'::text, 1::bigint, 'admin'::text),
      (3::bigint, 'human_user'::text, 3::bigint, 'user'::text),
      (4::bigint, 'human_user'::text, 4::bigint, 'user'::text),
      (5::bigint, 'human_user'::text, 5::bigint, 'user'::text),
      (6::bigint, 'human_user'::text, 6::bigint, 'user'::text)
  ),
  actual AS (
    SELECT p.principal_id,
           p.principal_type,
           p.owner_user_id,
           p.principal_status,
           u.user_id,
           u.role,
           u.status
    FROM public.n6_principal p
    JOIN public.user_account u ON u.user_id = p.owner_user_id
    WHERE p.principal_id IN (1, 3, 4, 5, 6)
  )
  SELECT count(*)
    INTO principal_mismatch_count
  FROM expected e
  FULL JOIN actual a ON a.principal_id = e.principal_id
  WHERE e.principal_id IS NULL
     OR a.principal_id IS NULL
     OR a.principal_type IS DISTINCT FROM e.principal_type
     OR a.owner_user_id IS DISTINCT FROM e.owner_user_id
     OR a.user_id IS DISTINCT FROM e.owner_user_id
     OR a.principal_status IS DISTINCT FROM 'active'
     OR a.status IS DISTINCT FROM 'active'
     OR a.role IS DISTINCT FROM e.user_role;

  IF principal_mismatch_count <> 0 THEN
    RAISE EXCEPTION '047 exactly-one active human/admin principal authority rejected';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id IN (1, 3, 4, 5, 6)
      AND (
        p.principal_type IN ('system', 'ai_user')
        OR p.principal_status <> 'active'
      )
  ) THEN
    RAISE EXCEPTION '047 system ai or inactive principal rejected';
  END IF;

  SELECT count(*)
    INTO completed_human_count
  FROM public.n6_virtual_account a
  WHERE a.principal_id IN (3, 4, 5, 6)
    AND a.principal_type = 'human_user'
    AND a.virtual_account_status = 'active'
    AND a.initial_cash = 100000000.0000
    AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND a.policy_version = 'n6_btrack_virtual_account_bootstrap_047_policy_v1'
    AND a.policy_hash = '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b'
    AND a.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND a.source_lineage_json @> provenance;

  SELECT count(*)
    INTO admin_adjustment_count
  FROM public.n6_virtual_cash_ledger l
  JOIN public.n6_virtual_account a
    ON a.virtual_account_id = l.virtual_account_id
  WHERE a.principal_id = 1
    AND a.principal_type = 'admin'
    AND l.ledger_type = 'adjustment'
    AND l.amount = 99000000.0000
    AND l.source_event_type = 'n6_virtual_account_bootstrap_047'
    AND l.source_event_id = '047:principal:1:admin_top_up'
    AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.source_lineage_json @> provenance;

  IF NOT (
    (completed_human_count = 0 AND admin_adjustment_count = 0)
    OR (completed_human_count = 4 AND admin_adjustment_count = 1)
  ) THEN
    RAISE EXCEPTION
      '047 partial bootstrap state rejected: humans=% admin_adjustments=%',
      completed_human_count,
      admin_adjustment_count;
  END IF;

  SELECT a.*
    INTO STRICT admin_account
  FROM public.n6_virtual_account a
  WHERE a.principal_id = 1
    AND a.principal_type = 'admin'
    AND a.virtual_account_status = 'active';

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_account a
    WHERE a.principal_id = 1
      AND a.virtual_account_id <> admin_account.virtual_account_id
  ) THEN
    RAISE EXCEPTION '047 admin account authority not exactly one';
  END IF;

  SELECT count(*)
    INTO admin_dependency_count
  FROM (
    SELECT 1 FROM public.n6_principal_account
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade_proposal
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_order
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_lot
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_event
      WHERE virtual_account_id = admin_account.virtual_account_id
    UNION ALL
    SELECT 1 FROM public.n6_virtual_pnl_snapshot
      WHERE virtual_account_id = admin_account.virtual_account_id
  ) dependencies;

  IF admin_dependency_count <> 0 THEN
    RAISE EXCEPTION '047 admin account has business dependencies: %',
      admin_dependency_count;
  END IF;

  IF admin_adjustment_count = 0 THEN
    SELECT count(*)
      INTO admin_ledger_count
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id;

    SELECT l.*
      INTO STRICT admin_initial_ledger
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id
      AND l.ledger_type = 'initial_deposit'
      AND l.amount = 1000000.0000
      AND l.currency = 'CNY'
      AND l.source_virtual_order_id IS NULL
      AND l.source_virtual_trade_id IS NULL;

    SELECT count(*)
      INTO admin_snapshot_count
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id;

    SELECT s.*
      INTO STRICT admin_active_snapshot
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id
      AND s.snapshot_status = 'active';

    IF admin_ledger_count <> 1
       OR admin_snapshot_count <> 1
       OR admin_account.initial_cash <> 1000000.0000
       OR admin_account.run_id <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_account.rollback_scope <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_account.source_lineage_json->>'seed_key' <>
          'phase3_admin_virtual_account'
       OR admin_initial_ledger.run_id <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_initial_ledger.source_event_type <>
          'phase3_virtual_account_seed'
       OR admin_initial_ledger.source_event_id <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_initial_ledger.source_lineage_json->>'seed_key' <>
          'phase3_admin_initial_cash_ledger'
       OR admin_active_snapshot.run_id <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_active_snapshot.source_lineage_json->>'seed_key' <>
          'phase3_admin_initial_cash_snapshot'
       OR admin_account.current_cash_snapshot_id IS DISTINCT FROM
          admin_active_snapshot.cash_snapshot_id
       OR admin_active_snapshot.source_ledger_max_id IS DISTINCT FROM
          admin_initial_ledger.cash_ledger_id
       OR admin_active_snapshot.available_cash <> 1000000.0000
       OR admin_active_snapshot.frozen_cash <> 0.0000
       OR admin_active_snapshot.total_cash <> 1000000.0000
       OR admin_active_snapshot.currency <> 'CNY' THEN
      RAISE EXCEPTION '047 admin cash authority audit rejected';
    END IF;

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
      admin_account.virtual_account_id,
      'adjustment',
      99000000.0000,
      'CNY',
      target_trade_date,
      'n6_virtual_account_bootstrap_047',
      '047:principal:1:admin_top_up',
      'n6_btrack_virtual_account_bootstrap_047_v1',
      'n6_btrack_virtual_account_bootstrap_047_policy_v1',
      '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
      'n6_btrack_virtual_account_bootstrap_047_v1',
      provenance || pg_catalog.jsonb_build_object(
        'principal_id', 1,
        'operation', 'admin_top_up',
        'previous_cash_snapshot_id', admin_active_snapshot.cash_snapshot_id
      ),
      'passed'
    )
    RETURNING cash_ledger_id INTO admin_adjustment_id;

    UPDATE public.n6_virtual_cash_snapshot
    SET snapshot_status = 'superseded'
    WHERE cash_snapshot_id = admin_active_snapshot.cash_snapshot_id
      AND snapshot_status = 'active';
    IF NOT FOUND THEN
      RAISE EXCEPTION '047 admin prior active snapshot supersession failed';
    END IF;

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
      admin_account.virtual_account_id,
      target_trade_date,
      100000000.0000,
      0.0000,
      100000000.0000,
      'CNY',
      admin_adjustment_id,
      'active',
      'n6_btrack_virtual_account_bootstrap_047_v1',
      'n6_btrack_virtual_account_bootstrap_047_policy_v1',
      '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
      'n6_btrack_virtual_account_bootstrap_047_v1',
      provenance || pg_catalog.jsonb_build_object(
        'principal_id', 1,
        'operation', 'admin_top_up',
        'previous_cash_snapshot_id', admin_active_snapshot.cash_snapshot_id
      ),
      'passed'
    )
    RETURNING cash_snapshot_id INTO human_cash_snapshot_id;

    UPDATE public.n6_virtual_account
    SET current_cash_snapshot_id = human_cash_snapshot_id,
        updated_at = pg_catalog.now()
    WHERE virtual_account_id = admin_account.virtual_account_id
      AND current_cash_snapshot_id = admin_active_snapshot.cash_snapshot_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION '047 admin cash pointer compare-and-swap failed';
    END IF;
  ELSE
    SELECT count(*)
      INTO admin_ledger_count
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id;

    SELECT count(*)
      INTO admin_snapshot_count
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id;

    SELECT l.*
      INTO STRICT admin_initial_ledger
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id
      AND l.ledger_type = 'initial_deposit'
      AND l.amount = 1000000.0000
      AND l.currency = 'CNY'
      AND l.source_event_type = 'phase3_virtual_account_seed'
      AND l.source_event_id =
          'n6_phase3_virtual_account_seed_20260605_v1'
      AND l.source_virtual_order_id IS NULL
      AND l.source_virtual_trade_id IS NULL
      AND l.run_id = 'n6_phase3_virtual_account_seed_20260605_v1'
      AND l.rollback_scope =
          'n6_phase3_virtual_account_seed_20260605_v1'
      AND l.source_lineage_json->>'seed_key' =
          'phase3_admin_initial_cash_ledger';

    SELECT l.cash_ledger_id
      INTO STRICT admin_adjustment_id
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id
      AND l.ledger_type = 'adjustment'
      AND l.amount = 99000000.0000
      AND l.source_event_type = 'n6_virtual_account_bootstrap_047'
      AND l.source_event_id = '047:principal:1:admin_top_up'
      AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND l.rollback_scope =
          'n6_btrack_virtual_account_bootstrap_047_v1'
      AND l.source_lineage_json @> provenance;

    SELECT s.*
      INTO STRICT admin_initial_snapshot
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id
      AND s.snapshot_status = 'superseded'
      AND s.available_cash = 1000000.0000
      AND s.frozen_cash = 0.0000
      AND s.total_cash = 1000000.0000
      AND s.currency = 'CNY'
      AND s.source_ledger_max_id = admin_initial_ledger.cash_ledger_id
      AND s.run_id = 'n6_phase3_virtual_account_seed_20260605_v1'
      AND s.rollback_scope =
          'n6_phase3_virtual_account_seed_20260605_v1'
      AND s.source_lineage_json->>'seed_key' =
          'phase3_admin_initial_cash_snapshot';

    SELECT s.*
      INTO STRICT admin_active_snapshot
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id
      AND s.snapshot_status = 'active'
      AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND s.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND s.available_cash = 100000000.0000
      AND s.frozen_cash = 0.0000
      AND s.total_cash = 100000000.0000
      AND s.source_ledger_max_id = admin_adjustment_id
      AND s.source_lineage_json @> provenance;

    IF admin_ledger_count <> 2
       OR admin_snapshot_count <> 2
       OR admin_account.initial_cash <> 1000000.0000
       OR admin_account.run_id <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_account.rollback_scope <>
          'n6_phase3_virtual_account_seed_20260605_v1'
       OR admin_account.source_lineage_json->>'seed_key' <>
          'phase3_admin_virtual_account'
       OR admin_account.current_cash_snapshot_id IS DISTINCT FROM
       admin_active_snapshot.cash_snapshot_id THEN
      RAISE EXCEPTION '047 rerun admin cash history or pointer drifted';
    END IF;
  END IF;

  FOR human_principal_id IN SELECT unnest(ARRAY[3, 4, 5, 6]::bigint[])
  LOOP
    IF completed_human_count = 0 THEN
      IF EXISTS (
        SELECT 1
        FROM public.n6_virtual_account a
        WHERE a.principal_id = human_principal_id
      ) THEN
        RAISE EXCEPTION '047 human principal % already has account',
          human_principal_id;
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
        human_principal_id,
        'human_user',
        pg_catalog.format('Human User %s Virtual Account', human_principal_id),
        'active',
        'CNY',
        100000000.0000,
        'n6_btrack_virtual_account_bootstrap_047_v1',
        'n6_btrack_virtual_account_bootstrap_047_policy_v1',
        '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
        'n6_btrack_virtual_account_bootstrap_047_v1',
        provenance || pg_catalog.jsonb_build_object(
          'principal_id', human_principal_id,
          'operation', 'human_account_seed'
        ),
        'passed'
      )
      RETURNING virtual_account_id INTO human_account_id;

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
        human_account_id,
        'initial_deposit',
        100000000.0000,
        'CNY',
        target_trade_date,
        'n6_virtual_account_bootstrap_047',
        pg_catalog.format(
          '047:principal:%s:initial_deposit',
          human_principal_id
        ),
        'n6_btrack_virtual_account_bootstrap_047_v1',
        'n6_btrack_virtual_account_bootstrap_047_policy_v1',
        '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
        'n6_btrack_virtual_account_bootstrap_047_v1',
        provenance || pg_catalog.jsonb_build_object(
          'principal_id', human_principal_id,
          'operation', 'human_initial_deposit'
        ),
        'passed'
      )
      RETURNING cash_ledger_id INTO human_cash_ledger_id;

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
        human_account_id,
        target_trade_date,
        100000000.0000,
        0.0000,
        100000000.0000,
        'CNY',
        human_cash_ledger_id,
        'active',
        'n6_btrack_virtual_account_bootstrap_047_v1',
        'n6_btrack_virtual_account_bootstrap_047_policy_v1',
        '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
        'n6_btrack_virtual_account_bootstrap_047_v1',
        provenance || pg_catalog.jsonb_build_object(
          'principal_id', human_principal_id,
          'operation', 'human_initial_snapshot'
        ),
        'passed'
      )
      RETURNING cash_snapshot_id INTO human_cash_snapshot_id;

      UPDATE public.n6_virtual_account
      SET current_cash_snapshot_id = human_cash_snapshot_id,
          updated_at = pg_catalog.now()
      WHERE virtual_account_id = human_account_id
        AND current_cash_snapshot_id IS NULL;
      IF NOT FOUND THEN
        RAISE EXCEPTION '047 human cash pointer initialization failed';
      END IF;
    ELSE
      SELECT a.virtual_account_id
        INTO STRICT human_account_id
      FROM public.n6_virtual_account a
      WHERE a.principal_id = human_principal_id
        AND a.principal_type = 'human_user'
        AND a.virtual_account_status = 'active'
        AND a.initial_cash = 100000000.0000
        AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND a.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND a.source_lineage_json @> provenance;

      SELECT l.cash_ledger_id
        INTO STRICT human_cash_ledger_id
      FROM public.n6_virtual_cash_ledger l
      WHERE l.virtual_account_id = human_account_id
        AND l.ledger_type = 'initial_deposit'
        AND l.amount = 100000000.0000
        AND l.source_event_type = 'n6_virtual_account_bootstrap_047'
        AND l.source_event_id = pg_catalog.format(
          '047:principal:%s:initial_deposit',
          human_principal_id
        )
        AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND l.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND l.source_lineage_json @> provenance;

      SELECT s.cash_snapshot_id
        INTO STRICT human_cash_snapshot_id
      FROM public.n6_virtual_cash_snapshot s
      WHERE s.virtual_account_id = human_account_id
        AND s.snapshot_status = 'active'
        AND s.available_cash = 100000000.0000
        AND s.frozen_cash = 0.0000
        AND s.total_cash = 100000000.0000
        AND s.source_ledger_max_id = human_cash_ledger_id
        AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND s.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND s.source_lineage_json @> provenance;

      IF (
        SELECT a.current_cash_snapshot_id
        FROM public.n6_virtual_account a
        WHERE a.virtual_account_id = human_account_id
      ) IS DISTINCT FROM human_cash_snapshot_id THEN
        RAISE EXCEPTION '047 rerun human % cash pointer drifted',
          human_principal_id;
      END IF;

      IF (SELECT count(*) FROM public.n6_virtual_cash_ledger
          WHERE virtual_account_id = human_account_id) <> 1
         OR (SELECT count(*) FROM public.n6_virtual_cash_snapshot
             WHERE virtual_account_id = human_account_id) <> 1 THEN
        RAISE EXCEPTION '047 rerun human % cash history contaminated',
          human_principal_id;
      END IF;
    END IF;
  END LOOP;

  IF (
    SELECT count(*)
    FROM public.n6_virtual_account a
    WHERE a.principal_id IN (1, 3, 4, 5, 6)
      AND a.virtual_account_status = 'active'
  ) <> 5
     OR EXISTS (
       SELECT 1
       FROM public.n6_virtual_account a
       WHERE a.principal_id IN (1, 3, 4, 5, 6)
         AND (
           a.virtual_account_status <> 'active'
           OR a.current_cash_snapshot_id IS NULL
           OR (SELECT count(*)
               FROM public.n6_virtual_cash_snapshot s
               WHERE s.virtual_account_id = a.virtual_account_id
                 AND s.snapshot_status = 'active') <> 1
           OR NOT EXISTS (
             SELECT 1
             FROM public.n6_virtual_cash_snapshot s
             WHERE s.cash_snapshot_id = a.current_cash_snapshot_id
               AND s.virtual_account_id = a.virtual_account_id
               AND s.snapshot_status = 'active'
               AND s.available_cash = 100000000.0000
               AND s.frozen_cash = 0.0000
               AND s.total_cash = 100000000.0000
           )
         )
     ) THEN
    RAISE EXCEPTION '047 post-write exactly-one account/cash authority failed';
  END IF;
END
$bootstrap$;

COMMIT;
