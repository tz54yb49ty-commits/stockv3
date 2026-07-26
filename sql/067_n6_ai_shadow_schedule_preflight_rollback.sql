-- Roll back only the N6 AI Shadow 067 schedule-preflight function.
-- Existing decisions, observations, contexts, proposals, and trades are preserved.

BEGIN;

DO $preflight$
DECLARE
  target_oid oid;
  target_proc record;
  ai_role_oid oid;
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '067_rollback_owner_session_required';
  END IF;

  target_oid := pg_catalog.to_regprocedure(
    'public.n6_ai_agent_shadow_schedule_preflight(text,date)'
  );
  IF target_oid IS NULL THEN
    RAISE EXCEPTION '067_rollback_function_missing';
  END IF;

  SELECT function_row.proowner AS owner_oid,
         function_owner.rolname AS owner_name,
         function_language.lanname AS language_name,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         function_row.proacl,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(function_row.prosrc, 'UTF8')
           ),
           'hex'
         ) AS source_sha256
    INTO target_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  JOIN pg_catalog.pg_language function_language
    ON function_language.oid = function_row.prolang
  WHERE function_row.oid = target_oid;

  SELECT role.oid INTO ai_role_oid
  FROM pg_catalog.pg_roles role
  WHERE role.rolname = 'n6_ai_agent';
  IF target_proc.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR target_proc.language_name IS DISTINCT FROM 'plpgsql'
     OR target_proc.prosecdef IS DISTINCT FROM true
     OR target_proc.provolatile IS DISTINCT FROM 's'
     OR target_proc.proparallel IS DISTINCT FROM 'u'
     OR target_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR target_proc.source_sha256 IS DISTINCT FROM
          '1ec882400c5cb95e1743e7f8829327d6cf42e3bfb7ea68a64c70795a1d73731d'
     OR ai_role_oid IS NULL
     OR (
       SELECT pg_catalog.count(*)
       FROM pg_catalog.aclexplode(
         COALESCE(
           target_proc.proacl,
           pg_catalog.acldefault('f', target_proc.owner_oid)
         )
       ) acl
       WHERE acl.privilege_type = 'EXECUTE'
         AND NOT acl.is_grantable
     ) <> 2
     OR NOT EXISTS (
       SELECT 1
       FROM pg_catalog.aclexplode(
         COALESCE(
           target_proc.proacl,
           pg_catalog.acldefault('f', target_proc.owner_oid)
         )
       ) acl
       WHERE acl.grantee = target_proc.owner_oid
         AND acl.privilege_type = 'EXECUTE'
         AND NOT acl.is_grantable
     )
     OR NOT EXISTS (
       SELECT 1
       FROM pg_catalog.aclexplode(
         COALESCE(
           target_proc.proacl,
           pg_catalog.acldefault('f', target_proc.owner_oid)
         )
       ) acl
       WHERE acl.grantee = ai_role_oid
         AND acl.privilege_type = 'EXECUTE'
         AND NOT acl.is_grantable
     ) THEN
    RAISE EXCEPTION '067_rollback_function_contract_mismatch';
  END IF;
END;
$preflight$;

REVOKE ALL ON FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(text,date)
FROM PUBLIC, n6_ai_agent, n6_btrack_web,
     n6_virtual_executor, n6_quote_writer;
DROP FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(text,date);

DO $postflight$
DECLARE
  source_proc record;
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_ai_agent_shadow_schedule_preflight(text,date)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '067_rollback_drop_failed';
  END IF;

  SELECT pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(function_row.prosrc, 'UTF8')
           ),
           'hex'
         ) AS source_sha256
    INTO source_proc
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
        );
  IF source_proc.source_sha256 IS DISTINCT FROM
       'df2afc2d7583effd10905ed478ab0df7e2147a854784bfc1b6087ca6d9b04681' THEN
    RAISE EXCEPTION '067_rollback_context_source_mismatch';
  END IF;

  SELECT pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(function_row.prosrc, 'UTF8')
           ),
           'hex'
         ) AS source_sha256
    INTO source_proc
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        );
  IF source_proc.source_sha256 IS DISTINCT FROM
       'c1e431a4de6af0e7ca9cc22a35b9b39aa889621713e5c1412db0e500a1022e69' THEN
    RAISE EXCEPTION '067_rollback_observation_source_mismatch';
  END IF;
END;
$postflight$;

COMMIT;
