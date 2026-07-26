-- Roll back only principals created by migration 072.
-- Any downstream reference hard-fails; no dependent row is changed or deleted.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('n6_web_user_principal_backfill_072_v1', 0)
);

LOCK TABLE
  public.user_account,
  public.n6_principal,
  public.user_monitor_stock,
  public.user_monitor_index,
  public.user_monitor_board,
  public.user_realtime_monitor_scope,
  public.n6_ai_user,
  public.n6_principal_account,
  public.n6_watchlist_ownership,
  public.n6_strategy,
  public.n6_virtual_account,
  public.n6_virtual_cash_ledger,
  public.n6_virtual_cash_snapshot,
  public.n6_virtual_quote_run,
  public.n6_virtual_order,
  public.n6_virtual_trade,
  public.n6_virtual_position,
  public.n6_virtual_position_event,
  public.n6_virtual_pnl_snapshot,
  public.n6_virtual_trade_proposal,
  public.n6_virtual_position_lot,
  public.n6_ai_context_snapshot,
  public.n6_ai_decision_run,
  public.n6_ai_decision,
  public.n6_ai_daily_summary,
  public.n6_ai_position_strategy_episode,
  public.n6_ai_strategy_action,
  public.n6_ai_candidate_rank_audit,
  public.n6_ai_shadow_observation_run_audit
IN SHARE ROW EXCLUSIVE MODE;

DO $rollback$
DECLARE
  deleted_count bigint;
  dependency_count bigint;
  marker_trace_count bigint;
  target_count bigint;
  target_owner_user_ids bigint[];
  target_principal_ids bigint[];
  sequence_last_value bigint;
  provenance constant jsonb := pg_catalog.jsonb_build_object(
    'source', 'n6_web_user_principal_backfill',
    'contract_version', 'n6-web-user-principal-v1',
    'migration_gate', '072',
    'migration_run_id', 'n6_web_user_principal_backfill_072_v1'
  );
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user'
     OR (
       SELECT pg_catalog.pg_get_userbyid(database_row.datdba)
       FROM pg_catalog.pg_database database_row
       WHERE database_row.datname = pg_catalog.current_database()
     ) IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '072 rollback owner migration identity rejected';
  END IF;

  SELECT count(*)
    INTO marker_trace_count
  FROM public.n6_principal principal
  WHERE principal.principal_policy_json->>'migration_gate' = '072'
     OR principal.principal_policy_json->>'migration_run_id' =
          'n6_web_user_principal_backfill_072_v1'
     OR principal.principal_policy_json->>'source' =
          'n6_web_user_principal_backfill';

  IF marker_trace_count = 0 THEN
    RETURN;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal principal
    LEFT JOIN public.user_account user_row
      ON user_row.user_id = principal.owner_user_id
    WHERE (
      principal.principal_policy_json->>'migration_gate' = '072'
      OR principal.principal_policy_json->>'migration_run_id' =
           'n6_web_user_principal_backfill_072_v1'
      OR principal.principal_policy_json->>'source' =
           'n6_web_user_principal_backfill'
    )
      AND (
        user_row.user_id IS NULL
        OR user_row.status <> 'active'
        OR user_row.role NOT IN ('user', 'admin')
        OR NOT (user_row.user_policy_json @> '{"n6_web_created":true}'::jsonb)
        OR principal.principal_type IS DISTINCT FROM CASE user_row.role
             WHEN 'admin' THEN 'admin'
             ELSE 'human_user'
           END
        OR principal.principal_status IS DISTINCT FROM 'active'
        OR principal.principal_label IS DISTINCT FROM COALESCE(
             NULLIF(pg_catalog.btrim(user_row.display_name), ''),
             user_row.login_name
           )
        OR principal.principal_policy_json IS DISTINCT FROM
             provenance || pg_catalog.jsonb_build_object(
               'created_by_user_id', user_row.created_by_user_id
             )
        OR EXISTS (
          SELECT 1
          FROM public.n6_principal other_principal
          WHERE other_principal.owner_user_id = user_row.user_id
            AND other_principal.principal_id <> principal.principal_id
        )
      )
  ) THEN
    RAISE EXCEPTION '072 rollback target provenance or fields drifted';
  END IF;

  SELECT count(*),
         pg_catalog.array_agg(principal.principal_id ORDER BY principal.principal_id),
         pg_catalog.array_agg(principal.owner_user_id ORDER BY principal.principal_id)
    INTO target_count, target_principal_ids, target_owner_user_ids
  FROM public.n6_principal principal
  JOIN public.user_account user_row
    ON user_row.user_id = principal.owner_user_id
  WHERE principal.principal_policy_json =
        provenance || pg_catalog.jsonb_build_object(
          'created_by_user_id', user_row.created_by_user_id
        );

  IF target_count <> marker_trace_count THEN
    RAISE EXCEPTION
      '072 rollback exact target count mismatch: traces=% exact=%',
      marker_trace_count,
      target_count;
  END IF;

  SELECT count(*)
    INTO dependency_count
  FROM (
    SELECT 1 FROM public.user_monitor_stock
      WHERE principal_id = ANY(target_principal_ids)
         OR user_id = ANY(target_owner_user_ids)
    UNION ALL
    SELECT 1 FROM public.user_monitor_index
      WHERE principal_id = ANY(target_principal_ids)
         OR user_id = ANY(target_owner_user_ids)
    UNION ALL
    SELECT 1 FROM public.user_monitor_board
      WHERE principal_id = ANY(target_principal_ids)
         OR user_id = ANY(target_owner_user_ids)
    UNION ALL
    SELECT 1 FROM public.user_realtime_monitor_scope
      WHERE principal_id = ANY(target_principal_ids)
         OR user_id = ANY(target_owner_user_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_user
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_principal_account
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_watchlist_ownership
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_strategy
      WHERE principal_id = ANY(target_principal_ids)
         OR created_by_principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_account
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1
    FROM public.n6_virtual_cash_ledger cash_ledger
    JOIN public.n6_virtual_account account
      ON account.virtual_account_id = cash_ledger.virtual_account_id
    WHERE account.principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1
    FROM public.n6_virtual_cash_snapshot cash_snapshot
    JOIN public.n6_virtual_account account
      ON account.virtual_account_id = cash_snapshot.virtual_account_id
    WHERE account.principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_quote_run
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_order
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_event
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_pnl_snapshot
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade_proposal
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_lot
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_context_snapshot
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_decision_run
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_decision
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_daily_summary
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_position_strategy_episode
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_strategy_action
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_candidate_rank_audit
      WHERE principal_id = ANY(target_principal_ids)
    UNION ALL
    SELECT 1 FROM public.n6_ai_shadow_observation_run_audit
      WHERE principal_id = ANY(target_principal_ids)
  ) protected_dependency;

  IF dependency_count <> 0 THEN
    RAISE EXCEPTION
      '072 rollback blocked by protected dependencies: %',
      dependency_count;
  END IF;

  SELECT last_value
    INTO sequence_last_value
  FROM public.n6_principal_principal_id_seq;

  DELETE FROM public.n6_principal principal
  USING public.user_account user_row
  WHERE principal.owner_user_id = user_row.user_id
    AND principal.principal_id = ANY(target_principal_ids)
    AND principal.principal_type = CASE user_row.role
          WHEN 'admin' THEN 'admin'
          ELSE 'human_user'
        END
    AND principal.principal_status = 'active'
    AND principal.principal_policy_json =
        provenance || pg_catalog.jsonb_build_object(
          'created_by_user_id', user_row.created_by_user_id
        );

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  IF deleted_count <> target_count THEN
    RAISE EXCEPTION
      '072 rollback deleted row count mismatch: expected=% actual=%',
      target_count,
      deleted_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal principal
    WHERE principal.principal_policy_json->>'migration_gate' = '072'
       OR principal.principal_policy_json->>'migration_run_id' =
            'n6_web_user_principal_backfill_072_v1'
       OR principal.principal_policy_json->>'source' =
            'n6_web_user_principal_backfill'
  ) THEN
    RAISE EXCEPTION '072 rollback target principal rows remain';
  END IF;

  IF (SELECT last_value FROM public.n6_principal_principal_id_seq) <
     sequence_last_value THEN
    RAISE EXCEPTION '072 rollback must not lower principal identity sequence';
  END IF;
END
$rollback$;

COMMIT;
