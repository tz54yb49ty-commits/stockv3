-- N6 AI shadow observation audit 062 fail-closed rollback.
-- Audit history is immutable: any row blocks rollback.

BEGIN;

DO $rollback_preflight$
DECLARE
  trigger_count integer;
  source_function record;
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '062_rollback_owner_session_required';
  END IF;

  IF pg_catalog.to_regclass(
       'public.n6_ai_shadow_observation_run_audit'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_shadow_observation_run_audit_audit_id_seq'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.idx_062_n6_ai_shadow_observation_dedup'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.idx_062_n6_ai_shadow_observation_window'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_append_only_guard()'
        ) IS NULL THEN
    RAISE EXCEPTION '062_rollback_requires_complete_062';
  END IF;

  SELECT pg_catalog.count(*)::integer
    INTO trigger_count
  FROM pg_catalog.pg_trigger trigger_row
  WHERE trigger_row.tgrelid =
          'public.n6_ai_shadow_observation_run_audit'::regclass
    AND trigger_row.tgname IN (
      'trg_062_n6_ai_shadow_observation_append_only_row',
      'trg_062_n6_ai_shadow_observation_append_only_truncate'
    )
    AND NOT trigger_row.tgisinternal;
  IF trigger_count <> 2 THEN
    RAISE EXCEPTION '062_rollback_requires_complete_062';
  END IF;

  SELECT function_row.prosrc,
         function_owner.rolname AS owner_name
    INTO source_function
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_agent_shadow_decision_record(jsonb)'
        );
  IF source_function.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(source_function.prosrc, 'UTF8')
          ),
          'hex'
        ) <>
          '32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951' THEN
    RAISE EXCEPTION '062_rollback_source_061_mismatch';
  END IF;
END;
$rollback_preflight$;

LOCK TABLE public.n6_ai_shadow_observation_run_audit
  IN ACCESS EXCLUSIVE MODE;

DO $history_gate$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.n6_ai_shadow_observation_run_audit
  ) THEN
    RAISE EXCEPTION '062_rollback_blocked_by_audit_history';
  END IF;
END;
$history_gate$;

REVOKE EXECUTE ON FUNCTION
  public.n6_ai_shadow_observation_run_audit_record(jsonb)
FROM n6_ai_agent;

DROP TRIGGER
  trg_062_n6_ai_shadow_observation_append_only_truncate
ON public.n6_ai_shadow_observation_run_audit;
DROP TRIGGER
  trg_062_n6_ai_shadow_observation_append_only_row
ON public.n6_ai_shadow_observation_run_audit;

DROP FUNCTION
  public.n6_ai_shadow_observation_run_audit_record(jsonb);
DROP FUNCTION
  public.n6_ai_shadow_observation_run_audit_append_only_guard();

DROP INDEX public.idx_062_n6_ai_shadow_observation_window;
DROP INDEX public.idx_062_n6_ai_shadow_observation_dedup;

-- Dropping the table also drops its owned GENERATED ALWAYS identity sequence.
DROP TABLE public.n6_ai_shadow_observation_run_audit;

DO $rollback_postflight$
DECLARE
  source_function record;
BEGIN
  IF pg_catalog.to_regclass(
       'public.n6_ai_shadow_observation_run_audit'
     ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_shadow_observation_run_audit_audit_id_seq'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_062_n6_ai_shadow_observation_dedup'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_062_n6_ai_shadow_observation_window'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_append_only_guard()'
        ) IS NOT NULL THEN
    RAISE EXCEPTION '062_rollback_postflight_object_remains';
  END IF;

  SELECT function_row.prosrc,
         function_owner.rolname AS owner_name
    INTO source_function
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_agent_shadow_decision_record(jsonb)'
        );
  IF source_function.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(source_function.prosrc, 'UTF8')
          ),
          'hex'
        ) <>
          '32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951' THEN
    RAISE EXCEPTION '062_rollback_postflight_source_061_mismatch';
  END IF;
END;
$rollback_postflight$;

COMMIT;
