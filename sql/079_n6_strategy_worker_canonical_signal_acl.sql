-- N6 strategy worker canonical signal DTO read-only ACL.
-- REVIEW ONLY until a separate migration execution gate.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_worker_canonical_signal_acl_079_v1', 0
  )
);

DO $preflight$
DECLARE
  target_view_name text;
  target_base_name text;
  view_row record;
  dependency_count integer;
  public_privilege_count integer;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '079 owner migration identity rejected';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles role
    WHERE role.rolname = 'n6_strategy_worker'
      AND role.rolcanlogin
      AND NOT role.rolinherit
      AND NOT role.rolsuper
      AND NOT role.rolcreatedb
      AND NOT role.rolcreaterole
      AND NOT role.rolreplication
      AND NOT role.rolbypassrls
  ) THEN
    RAISE EXCEPTION '079 strategy worker role contract rejected';
  END IF;

  FOR target_view_name, target_base_name IN
    SELECT expected.expected_view_name,
           expected.expected_base_name
    FROM (VALUES
      ('v_n6_stock_condition_display_basis'::text,
       'stock_condition_display_basis'::text),
      ('v_n6_index_condition_display_basis'::text,
       'index_condition_display_basis'::text),
      ('v_n6_board_condition_display_basis'::text,
       'board_condition_display_basis'::text)
    ) expected(expected_view_name, expected_base_name)
  LOOP
    SELECT relation.relkind,
           pg_catalog.pg_get_userbyid(relation.relowner) AS owner_name,
           relation.reloptions
      INTO view_row
    FROM pg_catalog.pg_class relation
    JOIN pg_catalog.pg_namespace namespace
      ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'public'
      AND relation.relname = target_view_name;
    IF NOT FOUND
       OR view_row.relkind <> 'v'
       OR view_row.owner_name <> 'ashare_v3_user'
       OR COALESCE(
            view_row.reloptions @> ARRAY['security_invoker=true'], false
          ) THEN
      RAISE EXCEPTION '079 canonical view contract rejected: %',
        target_view_name;
    END IF;

    SELECT count(*) INTO dependency_count
    FROM information_schema.view_table_usage dependency
    WHERE dependency.view_schema = 'public'
      AND dependency.view_name = target_view_name
      AND dependency.table_schema = 'public'
      AND dependency.table_name = target_base_name;
    IF dependency_count <> 1 OR EXISTS (
      SELECT 1
      FROM information_schema.view_table_usage dependency
      WHERE dependency.view_schema = 'public'
        AND dependency.view_name = target_view_name
        AND (
          dependency.table_schema <> 'public'
          OR dependency.table_name <> target_base_name
        )
    ) THEN
      RAISE EXCEPTION '079 canonical view dependency drift: %',
        target_view_name;
    END IF;

    SELECT count(*) INTO public_privilege_count
    FROM pg_catalog.pg_class relation
    JOIN pg_catalog.pg_namespace namespace
      ON namespace.oid = relation.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('r', relation.relowner)
      )
    ) acl
    WHERE namespace.nspname = 'public'
      AND relation.relname = target_view_name
      AND acl.grantee = 0;
    IF public_privilege_count <> 0
       OR pg_catalog.has_table_privilege(
            'n6_strategy_worker', 'public.' || target_view_name,
            'INSERT,UPDATE,DELETE'
          ) THEN
      RAISE EXCEPTION '079 canonical view ACL drift: %', target_view_name;
    END IF;
  END LOOP;

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
    RAISE EXCEPTION '079 already applied or partial ACL conflict';
  END IF;

  FOREACH target_base_name IN ARRAY ARRAY[
    'stock_condition_display_basis',
    'index_condition_display_basis',
    'board_condition_display_basis',
    'n6_virtual_trade_proposal',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_cash_ledger',
    'n6_virtual_cash_snapshot',
    'n6_virtual_position',
    'n6_virtual_position_lot'
  ] LOOP
    IF pg_catalog.to_regclass('public.' || target_base_name) IS NOT NULL
       AND pg_catalog.has_table_privilege(
         'n6_strategy_worker', 'public.' || target_base_name,
         'INSERT,UPDATE,DELETE'
       ) THEN
      RAISE EXCEPTION '079 forbidden write privilege present: %',
        target_base_name;
    END IF;
  END LOOP;
END
$preflight$;

GRANT SELECT ON TABLE
  public.v_n6_index_condition_display_basis,
  public.v_n6_board_condition_display_basis
TO n6_strategy_worker;

DO $postflight$
DECLARE
  target_view_name text;
  public_privilege_count integer;
BEGIN
  FOREACH target_view_name IN ARRAY ARRAY[
    'v_n6_stock_condition_display_basis',
    'v_n6_index_condition_display_basis',
    'v_n6_board_condition_display_basis'
  ] LOOP
    IF NOT pg_catalog.has_table_privilege(
         'n6_strategy_worker', 'public.' || target_view_name, 'SELECT'
       )
       OR pg_catalog.has_table_privilege(
         'n6_strategy_worker', 'public.' || target_view_name,
         'INSERT,UPDATE,DELETE'
       ) THEN
      RAISE EXCEPTION '079 canonical view postflight failed: %',
        target_view_name;
    END IF;
    SELECT count(*) INTO public_privilege_count
    FROM pg_catalog.pg_class relation
    JOIN pg_catalog.pg_namespace namespace
      ON namespace.oid = relation.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('r', relation.relowner)
      )
    ) acl
    WHERE namespace.nspname = 'public'
      AND relation.relname = target_view_name
      AND acl.grantee = 0;
    IF public_privilege_count <> 0 THEN
      RAISE EXCEPTION '079 PUBLIC privilege postflight failed: %',
        target_view_name;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
