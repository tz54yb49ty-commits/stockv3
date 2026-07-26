-- Replace the 067 four-slot N6 AI Shadow preflight with the 071 nine-slot policy.
-- This migration reads only schedule/audit facts and grants no trading authority.

BEGIN;

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  error_prefix text := '071_dependency_or_source_mismatch';
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '071_owner_session_required';
  END IF;

  IF pg_catalog.to_regclass('public.common_trade_calendar') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_context_snapshot') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_decision_run') IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_shadow_observation_run_audit'
        ) IS NULL THEN
    RAISE EXCEPTION '071_required_relation_missing';
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
    RAISE EXCEPTION '071_required_role_state_rejected';
  END IF;

  FOR expected IN
    SELECT *
    FROM (
      VALUES
      (
        'n6_ai_agent_context_load(text,date,integer)',
        '1d4283cd96f34032e51049aa6f4c1305dabe37cf0c62e1b2ba7594091290cc5a',
        'v'::text,
        NULL::text
      ),
      (
        'n6_ai_agent_context_load_v2(text,date,integer,text)',
        'ae000e4593d0de425dce168640740e1186dc7bd8d007e1a3677608cbf3940730',
        'v'::text,
        'n6_ai_agent'::text
      ),
      (
        'n6_ai_strategy_context_load_v1(text,date,integer,text)',
        '4865a77cc5940fb1230dad18339c05d9e8eefc4aadb535b21e52d16689dc4d14',
        'v'::text,
        NULL::text
      ),
      (
        'n6_ai_shadow_observation_run_audit_record(jsonb)',
        'c1e431a4de6af0e7ca9cc22a35b9b39aa889621713e5c1412db0e500a1022e69',
        'v'::text,
        'n6_ai_agent'::text
      ),
      (
        'n6_ai_agent_shadow_schedule_preflight(text,date)',
        '1ec882400c5cb95e1743e7f8829327d6cf42e3bfb7ea68a64c70795a1d73731d',
        's'::text,
        'n6_ai_agent'::text
      )
    ) AS expected_functions(
      signature, expected_sha, expected_volatility, allowed_role
    )
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '%: function %', error_prefix, expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proisstrict,
           function_row.proleakproof,
           function_row.provolatile,
           function_row.proparallel,
           function_row.proconfig,
           function_row.proacl,
           function_row.proowner AS owner_oid,
           function_owner.rolname AS owner_name,
           function_language.lanname AS language_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    JOIN pg_catalog.pg_language function_language
      ON function_language.oid = function_row.prolang
    WHERE function_row.oid = function_oid;

    allowed_role_oid := NULL;
    IF expected.allowed_role IS NOT NULL THEN
      SELECT role.oid INTO allowed_role_oid
      FROM pg_catalog.pg_roles role
      WHERE role.rolname = expected.allowed_role;
      IF allowed_role_oid IS NULL THEN
        RAISE EXCEPTION '%: allowed_role %',
          error_prefix, expected.signature;
      END IF;
    END IF;

    IF NOT (
      function_proc.owner_name = 'ashare_v3_user'
      AND function_proc.language_name = 'plpgsql'
      AND function_proc.prosecdef
      AND NOT function_proc.proisstrict
      AND NOT function_proc.proleakproof
      AND function_proc.provolatile::text = expected.expected_volatility
      AND function_proc.proparallel = 'u'
      AND function_proc.proconfig IS NOT DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
      AND (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.aclexplode(
          COALESCE(
            function_proc.proacl,
            pg_catalog.acldefault('f', function_proc.owner_oid)
          )
        ) function_acl
        WHERE function_acl.grantee = function_proc.owner_oid
          AND function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
      ) = 1
      AND (
        expected.allowed_role IS NULL
        OR (
          SELECT pg_catalog.count(*)
          FROM pg_catalog.aclexplode(
            COALESCE(
              function_proc.proacl,
              pg_catalog.acldefault('f', function_proc.owner_oid)
            )
          ) function_acl
          WHERE function_acl.grantee = allowed_role_oid
            AND function_acl.privilege_type = 'EXECUTE'
            AND NOT function_acl.is_grantable
        ) = 1
      )
      AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.aclexplode(
          COALESCE(
            function_proc.proacl,
            pg_catalog.acldefault('f', function_proc.owner_oid)
          )
        ) function_acl
        WHERE NOT (
          function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
          AND (
            function_acl.grantee = function_proc.owner_oid
            OR (
              allowed_role_oid IS NOT NULL
              AND function_acl.grantee = allowed_role_oid
            )
          )
        )
      )
    ) THEN
      RAISE EXCEPTION '%: attributes_or_acl %',
        error_prefix, expected.signature;
    END IF;

    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF expected.signature =
         'n6_ai_agent_shadow_schedule_preflight(text,date)'
       AND actual_sha = 'e3b625acaa39cecc7ac41614ea3a3a129968e19efd8cd8e1cdc41fedbb287aa9' THEN
      RAISE EXCEPTION '071_already_applied';
    END IF;
    IF actual_sha <> expected.expected_sha THEN
      RAISE EXCEPTION '%: body %', error_prefix, expected.signature;
    END IF;
  END LOOP;
END
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
  daily_identity_probe_count bigint;
  daily_decision_call_count bigint;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION 'shadow_schedule_preflight_authority_rejected';
  END IF;

  local_trade_date := local_now::date;
  slot_start := CASE
    WHEN local_now::time >= time '09:30:00'
     AND local_now::time < time '09:35:00'
      THEN local_trade_date + time '09:30:00'
    WHEN local_now::time >= time '10:00:00'
     AND local_now::time < time '10:05:00'
      THEN local_trade_date + time '10:00:00'
    WHEN local_now::time >= time '10:30:00'
     AND local_now::time < time '10:35:00'
      THEN local_trade_date + time '10:30:00'
    WHEN local_now::time >= time '11:00:00'
     AND local_now::time < time '11:05:00'
      THEN local_trade_date + time '11:00:00'
    WHEN local_now::time >= time '11:30:00'
     AND local_now::time < time '11:31:00'
      THEN local_trade_date + time '11:30:00'
    WHEN local_now::time >= time '13:30:00'
     AND local_now::time < time '13:35:00'
      THEN local_trade_date + time '13:30:00'
    WHEN local_now::time >= time '14:00:00'
     AND local_now::time < time '14:05:00'
      THEN local_trade_date + time '14:00:00'
    WHEN local_now::time >= time '14:30:00'
     AND local_now::time < time '14:35:00'
      THEN local_trade_date + time '14:30:00'
    WHEN local_now::time >= time '15:00:00'
     AND local_now::time < time '15:01:00'
      THEN local_trade_date + time '15:00:00'
    ELSE NULL
  END;

  IF slot_start IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'outside_shadow_slot'
    );
  END IF;

  slot_end := CASE slot_start::time
    WHEN time '09:30:00' THEN local_trade_date + time '09:35:00'
    WHEN time '10:00:00' THEN local_trade_date + time '10:05:00'
    WHEN time '10:30:00' THEN local_trade_date + time '10:35:00'
    WHEN time '11:00:00' THEN local_trade_date + time '11:05:00'
    WHEN time '11:30:00' THEN local_trade_date + time '11:31:00'
    WHEN time '13:30:00' THEN local_trade_date + time '13:35:00'
    WHEN time '14:00:00' THEN local_trade_date + time '14:05:00'
    WHEN time '14:30:00' THEN local_trade_date + time '14:35:00'
    WHEN time '15:00:00' THEN local_trade_date + time '15:01:00'
    ELSE NULL
  END;
  IF slot_end IS NULL THEN
    RAISE EXCEPTION 'shadow_schedule_slot_end_unreachable';
  END IF;

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

  SELECT pg_catalog.count(*) FILTER (
           WHERE audit.identity_probe_succeeded = true
         ),
         pg_catalog.count(*) FILTER (
           WHERE audit.decision_call_attempted = true
         )
    INTO daily_identity_probe_count, daily_decision_call_count
  FROM public.n6_ai_shadow_observation_run_audit audit
  WHERE audit.trade_date = local_trade_date;

  IF daily_identity_probe_count > 9
     OR daily_decision_call_count > 9
     OR daily_decision_call_count > daily_identity_probe_count THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'daily_request_budget_exceeded',
      'identity_probe_count', daily_identity_probe_count,
      'decision_call_count', daily_decision_call_count
    );
  END IF;
  IF daily_identity_probe_count >= 9 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'daily_identity_probe_budget_exhausted',
      'identity_probe_count', daily_identity_probe_count,
      'decision_call_count', daily_decision_call_count
    );
  END IF;
  IF daily_decision_call_count >= 9 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'daily_decision_call_budget_exhausted',
      'identity_probe_count', daily_identity_probe_count,
      'decision_call_count', daily_decision_call_count
    );
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'open_slot_ready',
    'identity_probe_count', daily_identity_probe_count,
    'decision_call_count', daily_decision_call_count,
    'identity_probe_remaining', 9 - daily_identity_probe_count,
    'decision_call_remaining', 9 - daily_decision_call_count
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
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  error_prefix text := '071_postflight_mismatch';
BEGIN
  FOR expected IN
    SELECT *
    FROM (
      VALUES
      (
        'n6_ai_agent_context_load(text,date,integer)',
        '1d4283cd96f34032e51049aa6f4c1305dabe37cf0c62e1b2ba7594091290cc5a',
        'v'::text,
        NULL::text
      ),
      (
        'n6_ai_agent_context_load_v2(text,date,integer,text)',
        'ae000e4593d0de425dce168640740e1186dc7bd8d007e1a3677608cbf3940730',
        'v'::text,
        'n6_ai_agent'::text
      ),
      (
        'n6_ai_strategy_context_load_v1(text,date,integer,text)',
        '4865a77cc5940fb1230dad18339c05d9e8eefc4aadb535b21e52d16689dc4d14',
        'v'::text,
        NULL::text
      ),
      (
        'n6_ai_shadow_observation_run_audit_record(jsonb)',
        'c1e431a4de6af0e7ca9cc22a35b9b39aa889621713e5c1412db0e500a1022e69',
        'v'::text,
        'n6_ai_agent'::text
      ),
      (
        'n6_ai_agent_shadow_schedule_preflight(text,date)',
        'e3b625acaa39cecc7ac41614ea3a3a129968e19efd8cd8e1cdc41fedbb287aa9',
        's'::text,
        'n6_ai_agent'::text
      )
    ) AS expected_functions(
      signature, expected_sha, expected_volatility, allowed_role
    )
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '%: function %', error_prefix, expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proisstrict,
           function_row.proleakproof,
           function_row.provolatile,
           function_row.proparallel,
           function_row.proconfig,
           function_row.proacl,
           function_row.proowner AS owner_oid,
           function_owner.rolname AS owner_name,
           function_language.lanname AS language_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    JOIN pg_catalog.pg_language function_language
      ON function_language.oid = function_row.prolang
    WHERE function_row.oid = function_oid;

    allowed_role_oid := NULL;
    IF expected.allowed_role IS NOT NULL THEN
      SELECT role.oid INTO allowed_role_oid
      FROM pg_catalog.pg_roles role
      WHERE role.rolname = expected.allowed_role;
    END IF;

    IF NOT (
      function_proc.owner_name = 'ashare_v3_user'
      AND function_proc.language_name = 'plpgsql'
      AND function_proc.prosecdef
      AND NOT function_proc.proisstrict
      AND NOT function_proc.proleakproof
      AND function_proc.provolatile::text = expected.expected_volatility
      AND function_proc.proparallel = 'u'
      AND function_proc.proconfig IS NOT DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
      AND (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.aclexplode(
          COALESCE(
            function_proc.proacl,
            pg_catalog.acldefault('f', function_proc.owner_oid)
          )
        ) function_acl
        WHERE function_acl.grantee = function_proc.owner_oid
          AND function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
      ) = 1
      AND (
        expected.allowed_role IS NULL
        OR (
          SELECT pg_catalog.count(*)
          FROM pg_catalog.aclexplode(
            COALESCE(
              function_proc.proacl,
              pg_catalog.acldefault('f', function_proc.owner_oid)
            )
          ) function_acl
          WHERE function_acl.grantee = allowed_role_oid
            AND function_acl.privilege_type = 'EXECUTE'
            AND NOT function_acl.is_grantable
        ) = 1
      )
      AND NOT EXISTS (
        SELECT 1
        FROM pg_catalog.aclexplode(
          COALESCE(
            function_proc.proacl,
            pg_catalog.acldefault('f', function_proc.owner_oid)
          )
        ) function_acl
        WHERE NOT (
          function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
          AND (
            function_acl.grantee = function_proc.owner_oid
            OR (
              allowed_role_oid IS NOT NULL
              AND function_acl.grantee = allowed_role_oid
            )
          )
        )
      )
    ) THEN
      RAISE EXCEPTION '%: attributes_or_acl %',
        error_prefix, expected.signature;
    END IF;

    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF actual_sha <> expected.expected_sha THEN
      RAISE EXCEPTION '%: body %', error_prefix, expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
