-- Exact rollback for N6 human virtual-account provisioning 074.
-- DO NOT EXECUTE without a separate rollback gate and fresh downstream proof.
-- Deletes only pristine 074-created account chains; every reference blocks all work.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_human_virtual_account_provisioning_074_v1',
    0
  )
);

LOCK TABLE
  public.user_account,
  public.n6_principal,
  public.n6_principal_account,
  public.n6_virtual_account,
  public.n6_virtual_cash_ledger,
  public.n6_virtual_cash_snapshot,
  public.n6_virtual_trade_proposal,
  public.n6_virtual_order,
  public.n6_virtual_trade,
  public.n6_virtual_position,
  public.n6_virtual_position_lot,
  public.n6_virtual_position_event,
  public.n6_virtual_pnl_snapshot,
  public.n6_ai_context_snapshot,
  public.n6_ai_daily_summary,
  public.n6_ai_position_strategy_episode,
  public.n6_ai_strategy_action,
  public.n6_ai_candidate_rank_audit,
  public.common_event_ledger,
  public.common_event_outbox,
  public.common_event_inbox
IN SHARE ROW EXCLUSIVE MODE;

DO $rollback$
DECLARE
  account_row public.n6_virtual_account%ROWTYPE;
  deleted_count bigint;
  dependency_count bigint;
  ledger_id bigint;
  mapping_count bigint;
  snapshot_id bigint;
  c_initial_cash constant numeric(24, 4) := 100000000.0000;
  c_policy_hash constant text :=
    '2c121818a66dc7b4d56c85a421e76c5e81be56fb85e8d446a16705fed7a50fd5';
  c_policy_version constant text :=
    'n6_human_virtual_account_provisioning_074_policy_v1';
  c_run_id constant text :=
    'n6_human_virtual_account_provisioning_074_v1';
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '074 rollback owner migration identity rejected';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_account account
    WHERE (
      account.run_id = c_run_id
      OR account.rollback_scope = c_run_id
      OR account.source_lineage_json->>'migration_gate' = '074'
    )
      AND NOT (
        account.run_id = c_run_id
        AND account.rollback_scope = c_run_id
        AND account.policy_version = c_policy_version
        AND account.policy_hash = c_policy_hash
        AND account.source_lineage_json @> pg_catalog.jsonb_build_object(
          'migration_gate', '074',
          'migration_run_id', c_run_id,
          'policy_version', c_policy_version,
          'policy_hash', c_policy_hash
        )
      )
  ) THEN
    RAISE EXCEPTION '074 rollback target account provenance drifted';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal_account mapping
    WHERE mapping.account_policy_json->>'migration_gate' = '074'
      AND NOT EXISTS (
        SELECT 1
        FROM public.n6_virtual_account account
        WHERE account.virtual_account_id = mapping.virtual_account_id
          AND account.run_id = c_run_id
          AND account.rollback_scope = c_run_id
      )
  ) THEN
    RAISE EXCEPTION '074 rollback orphan mapping provenance drifted';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_cash_ledger ledger
    LEFT JOIN public.n6_virtual_account account
      ON account.virtual_account_id = ledger.virtual_account_id
    WHERE (
      ledger.run_id = c_run_id
      OR ledger.rollback_scope = c_run_id
      OR ledger.source_lineage_json->>'migration_gate' = '074'
    )
      AND NOT (
        account.run_id = c_run_id
        AND ledger.run_id = c_run_id
        AND ledger.rollback_scope = c_run_id
      )
  ) THEN
    RAISE EXCEPTION '074 rollback ledger provenance drifted';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_cash_snapshot snapshot
    LEFT JOIN public.n6_virtual_account account
      ON account.virtual_account_id = snapshot.virtual_account_id
    WHERE (
      snapshot.run_id = c_run_id
      OR snapshot.rollback_scope = c_run_id
      OR snapshot.source_lineage_json->>'migration_gate' = '074'
    )
      AND NOT (
        account.run_id = c_run_id
        AND snapshot.run_id = c_run_id
        AND snapshot.rollback_scope = c_run_id
      )
  ) THEN
    RAISE EXCEPTION '074 rollback snapshot provenance drifted';
  END IF;

  FOR account_row IN
    SELECT account.*
    FROM public.n6_virtual_account account
    WHERE account.run_id = c_run_id
      AND account.rollback_scope = c_run_id
    ORDER BY account.virtual_account_id
    FOR UPDATE
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        pg_catalog.format(
          'n6_human_virtual_account_provisioning_074:principal:%s',
          account_row.principal_id
        ),
        0
      )
    );

    IF account_row.principal_type IS DISTINCT FROM 'human_user'
       OR account_row.virtual_account_status IS DISTINCT FROM 'active'
       OR account_row.base_currency IS DISTINCT FROM 'CNY'
       OR account_row.initial_cash IS DISTINCT FROM c_initial_cash
       OR account_row.policy_version IS DISTINCT FROM c_policy_version
       OR account_row.policy_hash IS DISTINCT FROM c_policy_hash
       OR account_row.current_cash_snapshot_id IS NULL
       OR NOT EXISTS (
         SELECT 1
         FROM public.n6_principal principal
         JOIN public.user_account user_row
           ON user_row.user_id = principal.owner_user_id
         WHERE principal.principal_id = account_row.principal_id
           AND principal.principal_type = 'human_user'
           AND principal.principal_status = 'active'
           AND user_row.status = 'active'
           AND user_row.role = 'user'
       ) THEN
      RAISE EXCEPTION '074 rollback ownership or account fields drifted for %',
        account_row.virtual_account_id;
    END IF;

    SELECT pg_catalog.count(*)
      INTO mapping_count
    FROM public.n6_principal_account mapping
    WHERE mapping.principal_id = account_row.principal_id
      AND mapping.virtual_account_id = account_row.virtual_account_id
      AND mapping.account_type = 'virtual'
      AND mapping.virtual_account_source = 'future_virtual_account'
      AND mapping.account_status = 'active'
      AND mapping.account_policy_version = c_policy_version
      AND mapping.account_policy_hash = c_policy_hash
      AND mapping.account_policy_json @> pg_catalog.jsonb_build_object(
        'migration_gate', '074',
        'migration_run_id', c_run_id,
        'policy_version', c_policy_version,
        'policy_hash', c_policy_hash,
        'principal_id', account_row.principal_id
      );

    IF mapping_count <> 1
       OR (SELECT pg_catalog.count(*)
           FROM public.n6_principal_account mapping
           WHERE mapping.principal_id = account_row.principal_id) <> 1
       OR (SELECT pg_catalog.count(*)
           FROM public.n6_principal_account mapping
           WHERE mapping.virtual_account_id = account_row.virtual_account_id) <> 1 THEN
      RAISE EXCEPTION '074 rollback mapping drifted for %',
        account_row.virtual_account_id;
    END IF;

    SELECT pg_catalog.min(ledger.cash_ledger_id)
      INTO ledger_id
    FROM public.n6_virtual_cash_ledger ledger
    WHERE ledger.virtual_account_id = account_row.virtual_account_id
      AND ledger.ledger_type = 'initial_deposit'
      AND ledger.amount = c_initial_cash
      AND ledger.currency = 'CNY'
      AND ledger.source_event_type = 'n6_human_virtual_account_provisioning_074'
      AND ledger.source_event_id = pg_catalog.format(
        '074:principal:%s:initial_deposit',
        account_row.principal_id
      )
      AND ledger.run_id = c_run_id
      AND ledger.policy_version = c_policy_version
      AND ledger.policy_hash = c_policy_hash
      AND ledger.rollback_scope = c_run_id
      AND ledger.source_lineage_json @> pg_catalog.jsonb_build_object(
        'migration_gate', '074',
        'migration_run_id', c_run_id,
        'principal_id', account_row.principal_id
      );

    IF ledger_id IS NULL
       OR (SELECT pg_catalog.count(*)
           FROM public.n6_virtual_cash_ledger ledger
           WHERE ledger.virtual_account_id = account_row.virtual_account_id) <> 1 THEN
      RAISE EXCEPTION '074 rollback cash ledger drifted for %',
        account_row.virtual_account_id;
    END IF;

    SELECT pg_catalog.min(snapshot.cash_snapshot_id)
      INTO snapshot_id
    FROM public.n6_virtual_cash_snapshot snapshot
    WHERE snapshot.virtual_account_id = account_row.virtual_account_id
      AND snapshot.available_cash = c_initial_cash
      AND snapshot.frozen_cash = 0.0000
      AND snapshot.total_cash = c_initial_cash
      AND snapshot.currency = 'CNY'
      AND snapshot.source_ledger_max_id = ledger_id
      AND snapshot.snapshot_status = 'active'
      AND snapshot.run_id = c_run_id
      AND snapshot.policy_version = c_policy_version
      AND snapshot.policy_hash = c_policy_hash
      AND snapshot.rollback_scope = c_run_id
      AND snapshot.source_lineage_json @> pg_catalog.jsonb_build_object(
        'migration_gate', '074',
        'migration_run_id', c_run_id,
        'principal_id', account_row.principal_id
      );

    IF snapshot_id IS NULL
       OR snapshot_id IS DISTINCT FROM account_row.current_cash_snapshot_id
       OR (SELECT pg_catalog.count(*)
           FROM public.n6_virtual_cash_snapshot snapshot
           WHERE snapshot.virtual_account_id = account_row.virtual_account_id) <> 1 THEN
      RAISE EXCEPTION '074 rollback cash snapshot or pointer drifted for %',
        account_row.virtual_account_id;
    END IF;

    SELECT pg_catalog.count(*)
      INTO dependency_count
    FROM (
      SELECT 1 FROM public.n6_virtual_trade_proposal row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_order row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_trade row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_position row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_position_lot row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_position_event row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_virtual_pnl_snapshot row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_ai_context_snapshot row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_ai_daily_summary row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_ai_position_strategy_episode row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_ai_strategy_action row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.n6_ai_candidate_rank_audit row_value
        WHERE row_value.virtual_account_id = account_row.virtual_account_id
      UNION ALL
      SELECT 1 FROM public.common_event_ledger row_value
        WHERE pg_catalog.jsonb_path_exists(
          row_value.payload_json,
          '$.**.virtual_account_id ? (@ == $account_id || @ == $account_id_text)',
          pg_catalog.jsonb_build_object(
            'account_id', account_row.virtual_account_id,
            'account_id_text', account_row.virtual_account_id::text
          )
        )
      UNION ALL
      SELECT 1 FROM public.common_event_outbox row_value
        WHERE pg_catalog.jsonb_path_exists(
          row_value.payload_json,
          '$.**.virtual_account_id ? (@ == $account_id || @ == $account_id_text)',
          pg_catalog.jsonb_build_object(
            'account_id', account_row.virtual_account_id,
            'account_id_text', account_row.virtual_account_id::text
          )
        )
      UNION ALL
      SELECT 1 FROM public.common_event_inbox row_value
        WHERE (
          pg_catalog.jsonb_path_exists(
            row_value.payload_json,
            '$.**.virtual_account_id ? (@ == $account_id || @ == $account_id_text)',
            pg_catalog.jsonb_build_object(
              'account_id', account_row.virtual_account_id,
              'account_id_text', account_row.virtual_account_id::text
            )
          )
          OR pg_catalog.jsonb_path_exists(
            row_value.raw_json,
            '$.**.virtual_account_id ? (@ == $account_id || @ == $account_id_text)',
            pg_catalog.jsonb_build_object(
              'account_id', account_row.virtual_account_id,
              'account_id_text', account_row.virtual_account_id::text
            )
          )
        )
    ) protected_dependencies;

    IF dependency_count <> 0 THEN
      RAISE EXCEPTION
        '074 rollback BLOCKED by downstream references for account %: %',
        account_row.virtual_account_id,
        dependency_count;
    END IF;

    UPDATE public.n6_virtual_account
    SET current_cash_snapshot_id = NULL,
        updated_at = pg_catalog.now()
    WHERE virtual_account_id = account_row.virtual_account_id
      AND current_cash_snapshot_id = snapshot_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 1 THEN
      RAISE EXCEPTION '074 rollback pointer clear failed';
    END IF;

    DELETE FROM public.n6_virtual_cash_snapshot
    WHERE cash_snapshot_id = snapshot_id
      AND virtual_account_id = account_row.virtual_account_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 1 THEN
      RAISE EXCEPTION '074 rollback snapshot delete failed';
    END IF;

    DELETE FROM public.n6_virtual_cash_ledger
    WHERE cash_ledger_id = ledger_id
      AND virtual_account_id = account_row.virtual_account_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 1 THEN
      RAISE EXCEPTION '074 rollback ledger delete failed';
    END IF;

    DELETE FROM public.n6_principal_account
    WHERE principal_id = account_row.principal_id
      AND virtual_account_id = account_row.virtual_account_id
      AND account_policy_hash = c_policy_hash;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 1 THEN
      RAISE EXCEPTION '074 rollback mapping delete failed';
    END IF;

    DELETE FROM public.n6_virtual_account
    WHERE virtual_account_id = account_row.virtual_account_id
      AND run_id = c_run_id
      AND rollback_scope = c_run_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 1 THEN
      RAISE EXCEPTION '074 rollback account delete failed';
    END IF;
  END LOOP;

  IF EXISTS (
    SELECT 1 FROM public.n6_virtual_account
    WHERE run_id = c_run_id OR rollback_scope = c_run_id
  )
     OR EXISTS (
       SELECT 1 FROM public.n6_principal_account
       WHERE account_policy_json->>'migration_gate' = '074'
     )
     OR EXISTS (
       SELECT 1 FROM public.n6_virtual_cash_ledger
       WHERE run_id = c_run_id OR rollback_scope = c_run_id
     )
     OR EXISTS (
       SELECT 1 FROM public.n6_virtual_cash_snapshot
       WHERE run_id = c_run_id OR rollback_scope = c_run_id
     ) THEN
    RAISE EXCEPTION '074 rollback residue remained';
  END IF;
END;
$rollback$;

DO $ddl$
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_provision_human_virtual_account(bigint)'
     ) IS NOT NULL THEN
    EXECUTE
      'REVOKE ALL ON FUNCTION public.n6_provision_human_virtual_account(bigint) FROM n6_btrack_web';
    EXECUTE
      'REVOKE ALL ON FUNCTION public.n6_provision_human_virtual_account(bigint) FROM PUBLIC';
    EXECUTE
      'DROP FUNCTION public.n6_provision_human_virtual_account(bigint)';
  END IF;
END;
$ddl$;

COMMIT;
