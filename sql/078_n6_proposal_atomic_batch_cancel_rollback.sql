-- Roll back only the N6 078 cancellation interface and guard compatibility.
-- Existing cancellation audit history and proposal statuses are preserved.

BEGIN;

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
  business_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  IF current_user <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '078_rollback_owner_execution_required';
  END IF;
  FOR expected IN
    SELECT * FROM (VALUES
      ('public.n6_btrack_proposals_cancel(text,bigint[])',
       '38560d8887b0ca6f626a51f4114f36e1de1c1864442b3bedd8db2a0541722b09'),
      ('public.n6_btrack_proposal_transition_guard()',
       '8c0e5f213c7c3e83eb7c488bb3302f94de86db98c4a95901f4776e44aec2ebf8')
    ) AS expected_functions(signature, source_sha)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '078_rollback_function_missing: %', expected.signature;
    END IF;
    SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
           owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
    WHERE p.oid = function_oid;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(pg_catalog.convert_to(function_proc.prosrc, 'UTF8')),
      'hex'
    );
    IF function_proc.owner_name <> 'ashare_v3_user'
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '078_rollback_definition_drift: %', expected.signature;
    END IF;
  END LOOP;
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
    ) acl
    JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = pg_catalog.to_regprocedure(
            'public.n6_btrack_proposals_cancel(text,bigint[])'
          )
      AND role.rolname = 'n6_btrack_web'
      AND acl.privilege_type = 'EXECUTE'
      AND acl.is_grantable IS FALSE
  ), EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
    ) acl
    LEFT JOIN pg_catalog.pg_roles role ON role.oid = acl.grantee
    WHERE target.oid = pg_catalog.to_regprocedure(
            'public.n6_btrack_proposals_cancel(text,bigint[])'
          )
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
      AND (
        acl.grantee = 0 OR role.rolname IS DISTINCT FROM 'n6_btrack_web'
        OR acl.is_grantable IS NOT FALSE
      )
  ) INTO expected_execute, unexpected_execute;
  IF expected_execute IS DISTINCT FROM true OR unexpected_execute
     OR pg_catalog.has_table_privilege(
       'n6_btrack_web', 'public.n6_virtual_trade_proposal',
       'INSERT,UPDATE,DELETE'
     ) THEN
    RAISE EXCEPTION '078_rollback_acl_drift';
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
    'n6.rollback_078_business_summary', business_summary::text, true
  );
END
$preflight$;

REVOKE ALL ON FUNCTION public.n6_btrack_proposals_cancel(text,bigint[])
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;
DROP FUNCTION public.n6_btrack_proposals_cancel(text,bigint[]);

DO $guard_restore$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT p.prosrc INTO source_text
  FROM pg_catalog.pg_proc p
  WHERE p.oid =
        'public.n6_btrack_proposal_transition_guard()'::regprocedure;

  old_text := $guard_web_078$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF OLD.proposal_status IN ('pending', 'confirmed')
       AND NEW.proposal_status = 'rejected'
       AND NEW.failure_reason = 'cancelled_by_user'
       AND OLD.executed_virtual_order_id IS NULL
       AND NEW.executed_virtual_order_id IS NULL
       AND OLD.executed_virtual_trade_id IS NULL
       AND NEW.executed_virtual_trade_id IS NULL
       AND OLD.executor_run_id IS NULL
       AND NEW.executor_run_id IS NULL
       AND pg_catalog.jsonb_typeof(
             NEW.source_lineage_json->'cancellation_audit'
           ) = 'array'
       AND pg_catalog.jsonb_array_length(
             NEW.source_lineage_json->'cancellation_audit'
           ) = (CASE
                 WHEN pg_catalog.jsonb_typeof(
                        OLD.source_lineage_json->'cancellation_audit'
                      ) = 'array'
                 THEN pg_catalog.jsonb_array_length(
                        OLD.source_lineage_json->'cancellation_audit'
                      ) + 1
                 ELSE 1
               END)
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancelled_at'
           ) IS NOT NULL
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancelled_by_principal_id'
           ) = NEW.principal_id::text
       AND pg_catalog.jsonb_extract_path_text(
             NEW.source_lineage_json, 'cancellation_audit',
             (pg_catalog.jsonb_array_length(
                NEW.source_lineage_json->'cancellation_audit'
              ) - 1)::text,
             'cancellation_policy_version'
           ) =
             'n6_btrack_proposal_cancel_078_v1' THEN
      NULL;
    ELSIF OLD.proposal_status='pending'
       AND NEW.proposal_status IN ('confirmed','expired') THEN
$guard_web_078$;
  new_text := $guard_web_064$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF OLD.proposal_status='pending'
       AND NEW.proposal_status IN ('confirmed','expired') THEN
$guard_web_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '078_rollback_guard_restore_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_btrack_proposal_transition_guard() '
    'RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$guard_restore$;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard()
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;

DO $postflight$
DECLARE
  guard_oid oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_proposal_transition_guard()'
  );
  guard_proc record;
  actual_sha text;
  before_summary jsonb := pg_catalog.current_setting(
    'n6.rollback_078_business_summary', false
  )::jsonb;
  after_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_btrack_proposals_cancel(text,bigint[])'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '078_rollback_cancel_function_still_present';
  END IF;
  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO guard_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = guard_oid;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(guard_proc.prosrc, 'UTF8')),
    'hex'
  );
  IF guard_oid IS NULL
     OR guard_proc.owner_name <> 'ashare_v3_user'
     OR guard_proc.prosecdef IS DISTINCT FROM true
     OR guard_proc.provolatile <> 'v'
     OR guard_proc.proparallel <> 'u'
     OR guard_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'c93231dd1bd456c34c954769016442d7e7fb04f0c040a18ca3a346b6e9745a9c'
     OR EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc target
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              target.proacl,
              pg_catalog.acldefault('f', target.proowner)
            )
          ) acl
          WHERE target.oid = guard_oid
            AND acl.privilege_type = 'EXECUTE'
            AND acl.grantee <> target.proowner
        ) THEN
    RAISE EXCEPTION '078_rollback_guard_roundtrip_failed';
  END IF;
  IF pg_catalog.has_table_privilege(
       'n6_btrack_web', 'public.n6_virtual_trade_proposal',
       'INSERT,UPDATE,DELETE'
     ) THEN
    RAISE EXCEPTION '078_rollback_web_direct_dml_detected';
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
    RAISE EXCEPTION '078_rollback_business_dml_detected';
  END IF;
END
$postflight$;

COMMIT;
