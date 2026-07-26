-- Revoke only the two read-only grants added by migration 079.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_worker_canonical_signal_acl_079_v1', 0
  )
);

DO $preflight$
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '079 rollback owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regclass(
       'public.v_n6_index_condition_display_basis'
     ) IS NULL
     OR pg_catalog.to_regclass(
       'public.v_n6_board_condition_display_basis'
     ) IS NULL
     OR NOT pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.v_n6_index_condition_display_basis', 'SELECT'
     )
     OR NOT pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.v_n6_board_condition_display_basis', 'SELECT'
     ) THEN
    RAISE EXCEPTION '079 rollback grant authority missing';
  END IF;
END
$preflight$;

REVOKE SELECT ON TABLE
  public.v_n6_index_condition_display_basis,
  public.v_n6_board_condition_display_basis
FROM n6_strategy_worker;

DO $postflight$
BEGIN
  IF NOT pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.v_n6_stock_condition_display_basis', 'SELECT'
     )
     OR pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.v_n6_index_condition_display_basis', 'SELECT'
     )
     OR pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.v_n6_board_condition_display_basis', 'SELECT'
     ) THEN
    RAISE EXCEPTION '079 rollback postflight failed';
  END IF;
END
$postflight$;

COMMIT;
