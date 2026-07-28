-- N6 virtual stop-loss evaluator numeric COALESCE compatibility repair.
-- REVIEWED MIGRATION: execute only through a separately authorized N6 gate.
-- Function-definition and ACL change only; no proposal, order, trade, cash,
-- position or lot rows are created, updated or deleted by this migration.

BEGIN;

DO $preflight$
DECLARE
  function_oid oid := pg_catalog.to_regprocedure(
    'public.n6_executor_evaluate_next_stop_loss(text)'
  );
  function_proc record;
  actual_sha text;
  executor_execute boolean;
  unexpected_execute boolean;
  business_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  IF current_user <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '087_owner_execution_required';
  END IF;
  IF function_oid IS NULL THEN
    RAISE EXCEPTION '087_stop_loss_evaluator_missing';
  END IF;

  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = function_oid;

  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND role.rolname = 'n6_virtual_executor'
      AND acl.privilege_type = 'EXECUTE'
      AND acl.is_grantable IS FALSE
  ), EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0
        OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
        OR acl.is_grantable IS DISTINCT FROM false
      )
  ) INTO executor_execute, unexpected_execute;

  IF function_proc.owner_name <> 'ashare_v3_user'
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'a858e12f58ef032946fa08c8eb067ae680cd6660389880f4c664fd739fdebccb'
     OR executor_execute IS DISTINCT FROM true
     OR unexpected_execute THEN
    RAISE EXCEPTION '087_stop_loss_evaluator_baseline_drift';
  END IF;

  FOREACH relation_name IN ARRAY ARRAY[
    'n6_virtual_trade_proposal', 'n6_virtual_order', 'n6_virtual_trade',
    'n6_virtual_cash_ledger', 'n6_virtual_cash_snapshot',
    'n6_virtual_position', 'n6_virtual_position_lot'
  ] LOOP
    IF pg_catalog.to_regclass('public.' || relation_name) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'SELECT count(*) FROM public.%I', relation_name
      ) INTO row_count;
      business_summary := business_summary ||
        pg_catalog.jsonb_build_object(relation_name, row_count);
    END IF;
  END LOOP;
  PERFORM pg_catalog.set_config(
    'n6.migration_087_business_summary', business_summary::text, true
  );
END
$preflight$;

DO $rewrite$
DECLARE
  function_oid oid := 'public.n6_executor_evaluate_next_stop_loss(text)'::regprocedure;
  source_text text;
  old_text text :=
    'IF pg_catalog.coalesce(matured_quantity, 0) <= 0 THEN';
  new_text text :=
    'IF COALESCE(matured_quantity, 0::numeric) <= 0 THEN';
BEGIN
  SELECT p.prosrc INTO source_text
  FROM pg_catalog.pg_proc p
  WHERE p.oid = function_oid;

  IF pg_catalog.strpos(source_text, old_text) = 0
     OR pg_catalog.strpos(
          pg_catalog.replace(source_text, old_text, ''),
          old_text
        ) <> 0
     OR pg_catalog.strpos(source_text, new_text) <> 0 THEN
    RAISE EXCEPTION '087_stop_loss_evaluator_rewrite_scope_drift';
  END IF;

  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_evaluate_next_stop_loss('
    'p_executor_run_id text) RETURNS jsonb LANGUAGE plpgsql VOLATILE '
    'SECURITY DEFINER SET search_path = pg_catalog AS %L',
    source_text
  );
END
$rewrite$;

ALTER FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM n6_btrack_web;
REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM n6_ai_agent;
REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  function_oid oid := pg_catalog.to_regprocedure(
    'public.n6_executor_evaluate_next_stop_loss(text)'
  );
  function_proc record;
  actual_sha text;
  executor_execute boolean;
  unexpected_execute boolean;
  before_summary jsonb := pg_catalog.current_setting(
    'n6.migration_087_business_summary', false
  )::jsonb;
  after_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = function_oid;

  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND role.rolname = 'n6_virtual_executor'
      AND acl.privilege_type = 'EXECUTE'
      AND acl.is_grantable IS FALSE
  ), EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0
        OR role.rolname IS DISTINCT FROM 'n6_virtual_executor'
        OR acl.is_grantable IS DISTINCT FROM false
      )
  ) INTO executor_execute, unexpected_execute;

  IF function_proc.owner_name <> 'ashare_v3_user'
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'fe3b0ac7297f24fc0a5925d178ccb1f26e575716baea48dce40ef6b2af0a1443'
     OR executor_execute IS DISTINCT FROM true
     OR unexpected_execute
     OR pg_catalog.strpos(
          function_proc.prosrc,
          'IF pg_catalog.coalesce(matured_quantity, 0) <= 0 THEN'
        ) <> 0
     OR pg_catalog.strpos(
          function_proc.prosrc,
          'IF COALESCE(matured_quantity, 0::numeric) <= 0 THEN'
        ) = 0 THEN
    RAISE EXCEPTION '087_postflight_definition_or_acl_drift';
  END IF;

  FOREACH relation_name IN ARRAY ARRAY[
    'n6_virtual_trade_proposal', 'n6_virtual_order', 'n6_virtual_trade',
    'n6_virtual_cash_ledger', 'n6_virtual_cash_snapshot',
    'n6_virtual_position', 'n6_virtual_position_lot'
  ] LOOP
    IF pg_catalog.to_regclass('public.' || relation_name) IS NOT NULL THEN
      EXECUTE pg_catalog.format(
        'SELECT count(*) FROM public.%I', relation_name
      ) INTO row_count;
      after_summary := after_summary ||
        pg_catalog.jsonb_build_object(relation_name, row_count);
    END IF;
  END LOOP;
  IF after_summary IS DISTINCT FROM before_summary THEN
    RAISE EXCEPTION '087_unexpected_business_dml';
  END IF;
END
$postflight$;

COMMIT;
