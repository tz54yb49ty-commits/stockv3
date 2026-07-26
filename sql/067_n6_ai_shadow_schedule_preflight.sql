-- N6 AI Shadow open-trade-date four-slot read-only preflight.
-- This migration does not call DeepSeek, load private context, or authorize trading.

BEGIN;

DO $preflight$
DECLARE
  function_state record;
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '067_owner_session_required';
  END IF;

  IF pg_catalog.to_regprocedure(
       'public.n6_ai_agent_shadow_schedule_preflight(text,date)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '067_already_applied';
  END IF;

  IF pg_catalog.to_regclass(
       'public.common_trade_calendar'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_context_snapshot'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_decision_run'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_shadow_observation_run_audit'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        ) IS NULL THEN
    RAISE EXCEPTION '067_requires_058_and_062';
  END IF;

  IF NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_roles role
       WHERE role.rolname = 'n6_ai_agent'
         AND role.rolcanlogin
         AND NOT role.rolinherit
         AND NOT role.rolsuper
         AND NOT role.rolcreatedb
         AND NOT role.rolcreaterole
         AND NOT role.rolreplication
         AND NOT role.rolbypassrls
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles
       WHERE rolname = 'n6_btrack_web'
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles
       WHERE rolname = 'n6_virtual_executor'
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles
       WHERE rolname = 'n6_quote_writer'
     ) THEN
    RAISE EXCEPTION '067_required_role_state_rejected';
  END IF;

  SELECT function_owner.rolname AS owner_name,
         function_language.lanname AS language_name,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(function_row.prosrc, 'UTF8')
           ),
           'hex'
         ) AS source_sha256
    INTO function_state
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  JOIN pg_catalog.pg_language function_language
    ON function_language.oid = function_row.prolang
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
        );
  IF function_state.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR function_state.language_name IS DISTINCT FROM 'plpgsql'
     OR function_state.prosecdef IS DISTINCT FROM true
     OR function_state.provolatile IS DISTINCT FROM 'v'
     OR function_state.proparallel IS DISTINCT FROM 'u'
     OR function_state.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR function_state.source_sha256 IS DISTINCT FROM
          'df2afc2d7583effd10905ed478ab0df7e2147a854784bfc1b6087ca6d9b04681' THEN
    RAISE EXCEPTION '067_context_source_authority_mismatch';
  END IF;

  SELECT function_owner.rolname AS owner_name,
         function_language.lanname AS language_name,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         pg_catalog.encode(
           pg_catalog.sha256(
             pg_catalog.convert_to(function_row.prosrc, 'UTF8')
           ),
           'hex'
         ) AS source_sha256
    INTO function_state
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  JOIN pg_catalog.pg_language function_language
    ON function_language.oid = function_row.prolang
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        );
  IF function_state.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR function_state.language_name IS DISTINCT FROM 'plpgsql'
     OR function_state.prosecdef IS DISTINCT FROM true
     OR function_state.provolatile IS DISTINCT FROM 'v'
     OR function_state.proparallel IS DISTINCT FROM 'u'
     OR function_state.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR function_state.source_sha256 IS DISTINCT FROM
          'c1e431a4de6af0e7ca9cc22a35b9b39aa889621713e5c1412db0e500a1022e69' THEN
    RAISE EXCEPTION '067_observation_source_authority_mismatch';
  END IF;
END;
$preflight$;

CREATE OR REPLACE FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(
  p_run_bucket text,
  p_for_trade_date date
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  local_now timestamp without time zone :=
    pg_catalog.statement_timestamp() AT TIME ZONE 'Asia/Shanghai';
  local_trade_date date;
  slot_start timestamp without time zone;
  slot_end timestamp without time zone;
  expected_run_bucket text;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION 'shadow_schedule_preflight_authority_rejected';
  END IF;

  local_trade_date := local_now::date;
  slot_start := CASE
    WHEN local_now::time >= time '10:25:00'
     AND local_now::time < time '10:30:00'
      THEN local_trade_date + time '10:25:00'
    WHEN local_now::time >= time '11:25:00'
     AND local_now::time < time '11:30:00'
      THEN local_trade_date + time '11:25:00'
    WHEN local_now::time >= time '13:55:00'
     AND local_now::time < time '14:00:00'
      THEN local_trade_date + time '13:55:00'
    WHEN local_now::time >= time '14:55:00'
     AND local_now::time < time '15:00:00'
      THEN local_trade_date + time '14:55:00'
    ELSE NULL
  END;

  IF slot_start IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'outside_shadow_slot'
    );
  END IF;

  slot_end := slot_start + interval '5 minutes';
  expected_run_bucket :=
    pg_catalog.to_char(local_trade_date, 'YYYYMMDD') ||
    'T' || pg_catalog.to_char(slot_start, 'HH24MI') || '+0800';
  IF p_for_trade_date IS DISTINCT FROM local_trade_date
     OR p_run_bucket IS NULL
     OR p_run_bucket IS DISTINCT FROM expected_run_bucket THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'outside_shadow_slot'
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date =
          pg_catalog.to_char(local_trade_date, 'YYYYMMDD')
      AND calendar.is_open = true
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_open_trade_date'
    );
  END IF;

  IF EXISTS (
       SELECT 1
       FROM public.n6_ai_context_snapshot context_snapshot
       WHERE context_snapshot.for_trade_date = local_trade_date
         AND context_snapshot.run_bucket = expected_run_bucket
     )
     OR EXISTS (
       SELECT 1
       FROM public.n6_ai_decision_run decision_run
       WHERE decision_run.run_bucket = expected_run_bucket
     )
     OR EXISTS (
       SELECT 1
       FROM public.n6_ai_shadow_observation_run_audit audit
       WHERE audit.trade_date = local_trade_date
         AND audit.identity_probe_succeeded = true
         AND (
               audit.started_at AT TIME ZONE 'Asia/Shanghai'
             ) >= slot_start
         AND (
               audit.started_at AT TIME ZONE 'Asia/Shanghai'
             ) < slot_end
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'already_processed'
    );
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'open_slot_ready'
  );
END;
$function$;

ALTER FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(text,date)
OWNER TO ashare_v3_user;

REVOKE ALL ON FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(text,date)
FROM PUBLIC, n6_btrack_web, n6_virtual_executor, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
public.n6_ai_agent_shadow_schedule_preflight(text,date)
TO n6_ai_agent;

DO $postflight$
DECLARE
  target_oid oid;
  target_proc record;
  ai_role_oid oid;
BEGIN
  target_oid := pg_catalog.to_regprocedure(
    'public.n6_ai_agent_shadow_schedule_preflight(text,date)'
  );
  IF target_oid IS NULL THEN
    RAISE EXCEPTION '067_postflight_function_missing';
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
    RAISE EXCEPTION '067_postflight_function_contract_mismatch';
  END IF;
END;
$postflight$;

COMMIT;
