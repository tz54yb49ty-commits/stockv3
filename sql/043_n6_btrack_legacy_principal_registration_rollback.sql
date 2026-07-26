-- Roll back only the four principals created by migration 043.
-- Legacy monitor/realtime ownership and all business history are preserved.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE public.n6_principal IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE
  public.user_monitor_stock,
  public.user_monitor_index,
  public.user_monitor_board,
  public.user_realtime_monitor_scope,
  public.n6_ai_user,
  public.n6_principal_account,
  public.n6_strategy,
  public.n6_watchlist_ownership,
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
  public.n6_virtual_position_lot
IN SHARE ROW EXCLUSIVE MODE;

DO $rollback$
DECLARE
  deleted_count bigint;
  legacy_mismatch_count bigint;
  protected_dependency_count bigint;
  registered_count bigint;
  sequence_last_value bigint;
  sequence_is_called boolean;
  registration_marker constant jsonb := pg_catalog.jsonb_build_object(
    'registration_source',
    '043_n6_btrack_legacy_principal_registration_v1',
    'registration_mode',
    'deterministic_principal_id_equals_user_id'
  );
BEGIN
  SELECT count(*)
    INTO registered_count
  FROM public.n6_principal p
  WHERE p.principal_id IN (3, 4, 5, 6)
    AND p.principal_type = 'human_user'
    AND p.owner_user_id = p.principal_id
    AND p.principal_status = 'active'
    AND p.principal_label IS NULL
    AND p.principal_policy_json = registration_marker;

  IF registered_count <> 4
     OR EXISTS (
       SELECT 1
       FROM public.n6_principal p
       WHERE p.principal_id IN (3, 4, 5, 6)
         AND NOT (
           p.principal_type = 'human_user'
           AND p.owner_user_id = p.principal_id
           AND p.principal_status = 'active'
           AND p.principal_label IS NULL
           AND p.principal_policy_json = registration_marker
         )
     ) THEN
    RAISE EXCEPTION '043 rollback target marker or fields drifted';
  END IF;

  SELECT count(*)
    INTO protected_dependency_count
  FROM (
    SELECT 1 FROM public.n6_ai_user WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_principal_account WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_strategy
      WHERE principal_id IN (3, 4, 5, 6)
         OR created_by_principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_watchlist_ownership WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_account WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1
    FROM public.n6_virtual_cash_ledger cash_ledger
    JOIN public.n6_virtual_account cash_ledger_account
      ON cash_ledger_account.virtual_account_id = cash_ledger.virtual_account_id
    WHERE cash_ledger_account.principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_quote_run WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_order WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_event WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_pnl_snapshot WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_trade_proposal WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1 FROM public.n6_virtual_position_lot WHERE principal_id IN (3, 4, 5, 6)
    UNION ALL
    SELECT 1
    FROM public.n6_virtual_cash_snapshot cash
    JOIN public.n6_virtual_account account
      ON account.virtual_account_id = cash.virtual_account_id
    WHERE account.principal_id IN (3, 4, 5, 6)
  ) dependencies;

  IF protected_dependency_count <> 0 THEN
    RAISE EXCEPTION '043 rollback blocked by protected dependencies: %',
      protected_dependency_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_stock
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_index
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_monitor_board
      UNION ALL
      SELECT principal_id, principal_type, user_id FROM public.user_realtime_monitor_scope
    ) legacy
    WHERE legacy.principal_id IN (3, 4, 5, 6)
      AND (
        legacy.principal_type <> 'human_user'
        OR legacy.user_id <> legacy.principal_id
      )
  ) THEN
    RAISE EXCEPTION '043 rollback legacy principal ownership mismatch';
  END IF;

  WITH actual(source_name, principal_id, row_count) AS (
    SELECT 'stock', principal_id, count(*)::bigint
    FROM public.user_monitor_stock
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'index', principal_id, count(*)::bigint
    FROM public.user_monitor_index
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'board', principal_id, count(*)::bigint
    FROM public.user_monitor_board
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
    UNION ALL
    SELECT 'realtime', principal_id, count(*)::bigint
    FROM public.user_realtime_monitor_scope
    WHERE principal_id IN (3, 4, 5, 6)
    GROUP BY principal_id
  ),
  expected(source_name, principal_id, row_count) AS (
    VALUES
      ('stock'::text, 3::bigint, 1074::bigint),
      ('index'::text, 3::bigint, 79::bigint),
      ('board'::text, 3::bigint, 256::bigint),
      ('realtime'::text, 3::bigint, 1886::bigint),
      ('stock'::text, 4::bigint, 0::bigint),
      ('index'::text, 4::bigint, 0::bigint),
      ('board'::text, 4::bigint, 0::bigint),
      ('realtime'::text, 4::bigint, 9::bigint),
      ('stock'::text, 5::bigint, 2586::bigint),
      ('index'::text, 5::bigint, 18::bigint),
      ('board'::text, 5::bigint, 273::bigint),
      ('realtime'::text, 5::bigint, 0::bigint),
      ('stock'::text, 6::bigint, 1850::bigint),
      ('index'::text, 6::bigint, 0::bigint),
      ('board'::text, 6::bigint, 0::bigint),
      ('realtime'::text, 6::bigint, 9::bigint)
  )
  SELECT count(*)
    INTO legacy_mismatch_count
  FROM expected e
  FULL JOIN actual a
    ON a.source_name = e.source_name
   AND a.principal_id = e.principal_id
  WHERE e.source_name IS NULL
     OR COALESCE(a.row_count, 0) IS DISTINCT FROM e.row_count;

  IF legacy_mismatch_count <> 0 THEN
    RAISE EXCEPTION '043 rollback frozen legacy scope matrix drifted';
  END IF;

  SELECT last_value, is_called
    INTO sequence_last_value, sequence_is_called
  FROM public.n6_principal_principal_id_seq;
  IF sequence_last_value < 6 OR NOT sequence_is_called THEN
    RAISE EXCEPTION '043 rollback sequence safety invariant failed';
  END IF;

  DELETE FROM public.n6_principal p
  WHERE p.principal_id IN (3, 4, 5, 6)
    AND p.principal_type = 'human_user'
    AND p.owner_user_id = p.principal_id
    AND p.principal_status = 'active'
    AND p.principal_label IS NULL
    AND p.principal_policy_json = registration_marker;

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  IF deleted_count <> 4 THEN
    RAISE EXCEPTION '043 rollback deleted row count mismatch: %', deleted_count;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_principal p
    WHERE p.principal_id IN (3, 4, 5, 6)
  ) THEN
    RAISE EXCEPTION '043 rollback target principal rows remain';
  END IF;

  IF (SELECT last_value FROM public.n6_principal_principal_id_seq) < sequence_last_value THEN
    RAISE EXCEPTION '043 rollback must not lower principal identity sequence';
  END IF;
END
$rollback$;

COMMIT;
