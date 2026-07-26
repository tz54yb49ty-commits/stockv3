-- History-preserving rollback design for N6 bootstrap 047.
-- Admin reversal is blocked unless a separate gate explicitly sets:
--   SET LOCAL n6.bootstrap_047_allow_admin_reverse_adjustment = 'true';

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_btrack_virtual_account_bootstrap_047_v1', 0)
);

LOCK TABLE
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

DO $rollback$
DECLARE
  admin_account public.n6_virtual_account%ROWTYPE;
  admin_current_snapshot public.n6_virtual_cash_snapshot%ROWTYPE;
  admin_dependency_count bigint;
  admin_ledger_count bigint;
  admin_reversal_count bigint;
  admin_reversal_ledger_id bigint;
  admin_reversal_snapshot_id bigint;
  admin_snapshot_count bigint;
  admin_top_up_ledger public.n6_virtual_cash_ledger%ROWTYPE;
  deleted_human_account_count bigint;
  deleted_human_ledger_count bigint;
  deleted_human_snapshot_count bigint;
  human_account_count bigint;
  human_dependency_count bigint;
  human_ledger_count bigint;
  human_snapshot_count bigint;
  nulled_human_pointer_count bigint;
  reversed_already boolean := false;
  rollback_enabled boolean :=
    pg_catalog.coalesce(
      pg_catalog.current_setting(
        'n6.bootstrap_047_allow_admin_reverse_adjustment',
        true
      ),
      'false'
    ) = 'true';
  target_trade_date integer :=
    pg_catalog.to_char(CURRENT_DATE, 'YYYYMMDD')::integer;
  provenance constant jsonb := pg_catalog.jsonb_build_object(
    'bootstrap_gate', '047',
    'bootstrap_run_id', 'n6_btrack_virtual_account_bootstrap_047_v1',
    'policy_version', 'n6_btrack_virtual_account_bootstrap_047_policy_v1',
    'policy_hash', '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b'
  );
  rollback_provenance constant jsonb := pg_catalog.jsonb_build_object(
    'rollback_gate', '047',
    'reverses_bootstrap_run_id',
      'n6_btrack_virtual_account_bootstrap_047_v1',
    'rollback_mode', 'append_only_admin_reverse_adjustment'
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
    RAISE EXCEPTION '047 rollback owner migration identity rejected';
  END IF;

  PERFORM p.principal_id
  FROM public.n6_principal p
  WHERE p.principal_id IN (1, 3, 4, 5, 6)
  ORDER BY p.principal_id
  FOR UPDATE;

  SELECT count(*)
    INTO admin_reversal_count
  FROM public.n6_virtual_cash_ledger l
  JOIN public.n6_virtual_account a
    ON a.virtual_account_id = l.virtual_account_id
  WHERE a.principal_id = 1
    AND l.ledger_type = 'adjustment'
    AND l.amount = -99000000.0000
    AND l.source_event_type = 'n6_virtual_account_bootstrap_047_rollback'
    AND l.source_event_id = '047:principal:1:admin_top_up_reverse'
    AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_rollback_v1'
    AND l.source_lineage_json @> rollback_provenance;

  IF admin_reversal_count NOT IN (0, 1) THEN
    RAISE EXCEPTION '047 rollback admin reversal authority ambiguous';
  END IF;
  reversed_already := admin_reversal_count = 1;

  SELECT count(*)
    INTO human_account_count
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

  IF human_account_count = 0 AND reversed_already THEN
    RETURN;
  END IF;
  IF human_account_count <> 4 THEN
    RAISE EXCEPTION '047 rollback exact four human account provenance failed';
  END IF;

  IF NOT rollback_enabled AND NOT reversed_already THEN
    RAISE EXCEPTION
      '047 admin rollback blocked: append-only reverse adjustment requires separate explicit gate';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_account a
    WHERE a.principal_id IN (3, 4, 5, 6)
      AND NOT (
        a.principal_type = 'human_user'
        AND a.virtual_account_status = 'active'
        AND a.initial_cash = 100000000.0000
        AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND a.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND a.source_lineage_json @> provenance
      )
  ) THEN
    RAISE EXCEPTION '047 rollback human account provenance drifted';
  END IF;

  SELECT count(*)
    INTO human_dependency_count
  FROM (
    SELECT 1
    FROM public.n6_principal_account pa
    JOIN public.n6_virtual_account a
      ON a.virtual_account_id = pa.virtual_account_id
    WHERE a.principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade_proposal
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_order
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_lot
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_event
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
    UNION ALL
    SELECT 1 FROM public.n6_virtual_pnl_snapshot
      WHERE virtual_account_id IN (
        SELECT virtual_account_id FROM public.n6_virtual_account
        WHERE principal_id IN (3, 4, 5, 6)
      )
  ) dependencies;

  IF human_dependency_count <> 0 THEN
    RAISE EXCEPTION '047 rollback blocked by human business dependencies: %',
      human_dependency_count;
  END IF;

  SELECT count(*)
    INTO human_ledger_count
  FROM public.n6_virtual_cash_ledger l
  JOIN public.n6_virtual_account a
    ON a.virtual_account_id = l.virtual_account_id
  WHERE a.principal_id IN (3, 4, 5, 6)
    AND l.ledger_type = 'initial_deposit'
    AND l.amount = 100000000.0000
    AND l.source_event_type = 'n6_virtual_account_bootstrap_047'
    AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.source_lineage_json @> provenance;

  SELECT count(*)
    INTO human_snapshot_count
  FROM public.n6_virtual_cash_snapshot s
  JOIN public.n6_virtual_account a
    ON a.virtual_account_id = s.virtual_account_id
  WHERE a.principal_id IN (3, 4, 5, 6)
    AND s.snapshot_status = 'active'
    AND s.available_cash = 100000000.0000
    AND s.frozen_cash = 0.0000
    AND s.total_cash = 100000000.0000
    AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND s.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND s.source_lineage_json @> provenance
    AND a.current_cash_snapshot_id = s.cash_snapshot_id;

  IF human_ledger_count <> 4
     OR human_snapshot_count <> 4
     OR (
       SELECT count(*)
       FROM public.n6_virtual_cash_ledger l
       JOIN public.n6_virtual_account a
         ON a.virtual_account_id = l.virtual_account_id
       WHERE a.principal_id IN (3, 4, 5, 6)
     ) <> 4
     OR (
       SELECT count(*)
       FROM public.n6_virtual_cash_snapshot s
       JOIN public.n6_virtual_account a
         ON a.virtual_account_id = s.virtual_account_id
       WHERE a.principal_id IN (3, 4, 5, 6)
     ) <> 4 THEN
    RAISE EXCEPTION '047 rollback human cash provenance or dependency failed';
  END IF;

  SELECT a.*
    INTO STRICT admin_account
  FROM public.n6_virtual_account a
  WHERE a.principal_id = 1
    AND a.principal_type = 'admin'
    AND a.virtual_account_status = 'active';

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
    RAISE EXCEPTION '047 rollback blocked by admin business dependencies: %',
      admin_dependency_count;
  END IF;

  IF NOT reversed_already THEN
    SELECT count(*)
      INTO admin_ledger_count
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id;

    SELECT count(*)
      INTO admin_snapshot_count
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id;

    SELECT l.*
      INTO STRICT admin_top_up_ledger
    FROM public.n6_virtual_cash_ledger l
    WHERE l.virtual_account_id = admin_account.virtual_account_id
      AND l.ledger_type = 'adjustment'
      AND l.amount = 99000000.0000
      AND l.source_event_type = 'n6_virtual_account_bootstrap_047'
      AND l.source_event_id = '047:principal:1:admin_top_up'
      AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND l.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND l.source_lineage_json @> provenance;

    SELECT s.*
      INTO STRICT admin_current_snapshot
    FROM public.n6_virtual_cash_snapshot s
    WHERE s.virtual_account_id = admin_account.virtual_account_id
      AND s.snapshot_status = 'active'
      AND s.available_cash = 100000000.0000
      AND s.frozen_cash = 0.0000
      AND s.total_cash = 100000000.0000
      AND s.source_ledger_max_id = admin_top_up_ledger.cash_ledger_id
      AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND s.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
      AND s.source_lineage_json @> provenance;

    IF admin_ledger_count <> 2
       OR admin_snapshot_count <> 2
       OR admin_account.initial_cash <> 1000000.0000
       OR admin_account.current_cash_snapshot_id IS DISTINCT FROM
          admin_current_snapshot.cash_snapshot_id THEN
      RAISE EXCEPTION '047 rollback admin current cash authority rejected';
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
      -99000000.0000,
      'CNY',
      target_trade_date,
      'n6_virtual_account_bootstrap_047_rollback',
      '047:principal:1:admin_top_up_reverse',
      'n6_btrack_virtual_account_bootstrap_047_rollback_v1',
      'n6_btrack_virtual_account_bootstrap_047_policy_v1',
      '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
      'n6_btrack_virtual_account_bootstrap_047_rollback_v1',
      rollback_provenance || pg_catalog.jsonb_build_object(
        'principal_id', 1,
        'reversed_cash_ledger_id', admin_top_up_ledger.cash_ledger_id,
        'previous_cash_snapshot_id', admin_current_snapshot.cash_snapshot_id
      ),
      'passed'
    )
    RETURNING cash_ledger_id INTO admin_reversal_ledger_id;

    UPDATE public.n6_virtual_cash_snapshot
    SET snapshot_status = 'superseded'
    WHERE cash_snapshot_id = admin_current_snapshot.cash_snapshot_id
      AND snapshot_status = 'active';
    IF NOT FOUND THEN
      RAISE EXCEPTION '047 rollback admin snapshot supersession failed';
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
      1000000.0000,
      0.0000,
      1000000.0000,
      'CNY',
      admin_reversal_ledger_id,
      'active',
      'n6_btrack_virtual_account_bootstrap_047_rollback_v1',
      'n6_btrack_virtual_account_bootstrap_047_policy_v1',
      '62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b',
      'n6_btrack_virtual_account_bootstrap_047_rollback_v1',
      rollback_provenance || pg_catalog.jsonb_build_object(
        'principal_id', 1,
        'reversed_cash_ledger_id', admin_top_up_ledger.cash_ledger_id,
        'previous_cash_snapshot_id', admin_current_snapshot.cash_snapshot_id
      ),
      'passed'
    )
    RETURNING cash_snapshot_id INTO admin_reversal_snapshot_id;

    UPDATE public.n6_virtual_account
    SET current_cash_snapshot_id = admin_reversal_snapshot_id,
        updated_at = pg_catalog.now()
    WHERE virtual_account_id = admin_account.virtual_account_id
      AND current_cash_snapshot_id = admin_current_snapshot.cash_snapshot_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION '047 rollback admin pointer compare-and-swap failed';
    END IF;
  END IF;

  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = NULL
  WHERE principal_id IN (3, 4, 5, 6)
    AND run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND source_lineage_json @> provenance
    AND current_cash_snapshot_id IN (
      SELECT s.cash_snapshot_id
      FROM public.n6_virtual_cash_snapshot s
      WHERE s.virtual_account_id = n6_virtual_account.virtual_account_id
        AND s.snapshot_status = 'active'
        AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
        AND s.rollback_scope =
            'n6_btrack_virtual_account_bootstrap_047_v1'
        AND s.source_lineage_json @> provenance
    );
  GET DIAGNOSTICS nulled_human_pointer_count = ROW_COUNT;
  IF nulled_human_pointer_count <> 4 THEN
    RAISE EXCEPTION '047 rollback human pointer clear count failed: %',
      nulled_human_pointer_count;
  END IF;

  DELETE FROM public.n6_virtual_cash_snapshot s
  USING public.n6_virtual_account a
  WHERE a.virtual_account_id = s.virtual_account_id
    AND a.principal_id IN (3, 4, 5, 6)
    AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND s.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND s.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND s.source_lineage_json @> provenance;
  GET DIAGNOSTICS deleted_human_snapshot_count = ROW_COUNT;
  IF deleted_human_snapshot_count <> 4 THEN
    RAISE EXCEPTION '047 rollback human snapshot delete count failed: %',
      deleted_human_snapshot_count;
  END IF;

  DELETE FROM public.n6_virtual_cash_ledger l
  USING public.n6_virtual_account a
  WHERE a.virtual_account_id = l.virtual_account_id
    AND a.principal_id IN (3, 4, 5, 6)
    AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND l.source_lineage_json @> provenance;
  GET DIAGNOSTICS deleted_human_ledger_count = ROW_COUNT;
  IF deleted_human_ledger_count <> 4 THEN
    RAISE EXCEPTION '047 rollback human ledger delete count failed: %',
      deleted_human_ledger_count;
  END IF;

  DELETE FROM public.n6_virtual_account a
  WHERE a.principal_id IN (3, 4, 5, 6)
    AND a.principal_type = 'human_user'
    AND a.run_id = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND a.rollback_scope = 'n6_btrack_virtual_account_bootstrap_047_v1'
    AND a.source_lineage_json @> provenance;
  GET DIAGNOSTICS deleted_human_account_count = ROW_COUNT;
  IF deleted_human_account_count <> 4 THEN
    RAISE EXCEPTION '047 rollback human account delete count failed: %',
      deleted_human_account_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_account a
    WHERE a.principal_id IN (3, 4, 5, 6)
  ) THEN
    RAISE EXCEPTION '047 rollback human account rows remain';
  END IF;
END
$rollback$;

COMMIT;
