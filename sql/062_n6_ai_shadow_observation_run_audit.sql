-- N6 AI shadow observation run audit, additive 062 schema.
-- OFFLINE REVIEW ONLY: this file does not authorize migration execution,
-- provider calls, autonomous trading, proposals, or account mutations.

BEGIN;

DO $preflight$
DECLARE
  target_object_count integer;
  unknown_object_count integer;
  source_function record;
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '062_migration_owner_session_required';
  END IF;

  IF pg_catalog.to_regclass('public.n6_ai_user') IS NULL
     OR pg_catalog.to_regclass('public.n6_principal') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_context_snapshot') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_decision_run') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_decision') IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_btrack_resolve_authority(text)'
        ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_agent_shadow_decision_record(jsonb)'
        ) IS NULL THEN
    RAISE EXCEPTION '062_requires_live_055_through_061';
  END IF;

  IF NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_roles role
       WHERE role.rolname = 'ashare_v3_user'
     )
     OR NOT EXISTS (
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
       SELECT 1
       FROM pg_catalog.pg_roles role
       WHERE role.rolname = 'n6_btrack_web'
     )
     OR NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_roles role
       WHERE role.rolname = 'n6_virtual_executor'
     ) THEN
    RAISE EXCEPTION '062_required_role_state_rejected';
  END IF;

  SELECT function_row.prosrc,
         function_owner.rolname AS owner_name,
         function_language.lanname AS language_name,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig
    INTO source_function
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  JOIN pg_catalog.pg_language function_language
    ON function_language.oid = function_row.prolang
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_agent_shadow_decision_record(jsonb)'
        );
  IF source_function.owner_name IS DISTINCT FROM 'ashare_v3_user'
     OR source_function.language_name IS DISTINCT FROM 'plpgsql'
     OR source_function.prosecdef IS DISTINCT FROM true
     OR source_function.provolatile IS DISTINCT FROM 'v'
     OR source_function.proparallel IS DISTINCT FROM 'u'
     OR source_function.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
     OR pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(source_function.prosrc, 'UTF8')
          ),
          'hex'
        ) <>
          '32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951' THEN
    RAISE EXCEPTION '062_source_061_authority_mismatch';
  END IF;

  SELECT pg_catalog.count(*)::integer
    INTO target_object_count
  FROM (
    SELECT class_row.oid
    FROM pg_catalog.pg_class class_row
    JOIN pg_catalog.pg_namespace namespace_row
      ON namespace_row.oid = class_row.relnamespace
    WHERE namespace_row.nspname = 'public'
      AND class_row.relname IN (
        'n6_ai_shadow_observation_run_audit',
        'n6_ai_shadow_observation_run_audit_audit_id_seq',
        'idx_062_n6_ai_shadow_observation_dedup',
        'idx_062_n6_ai_shadow_observation_window'
      )
    UNION ALL
    SELECT function_row.oid
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_namespace namespace_row
      ON namespace_row.oid = function_row.pronamespace
    WHERE namespace_row.nspname = 'public'
      AND function_row.oid IN (
        pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_record(jsonb)'
        ),
        pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_append_only_guard()'
        )
      )
    UNION ALL
    SELECT trigger_row.oid
    FROM pg_catalog.pg_trigger trigger_row
    JOIN pg_catalog.pg_class class_row
      ON class_row.oid = trigger_row.tgrelid
    JOIN pg_catalog.pg_namespace namespace_row
      ON namespace_row.oid = class_row.relnamespace
    WHERE namespace_row.nspname = 'public'
      AND class_row.relname = 'n6_ai_shadow_observation_run_audit'
      AND trigger_row.tgname IN (
        'trg_062_n6_ai_shadow_observation_append_only_row',
        'trg_062_n6_ai_shadow_observation_append_only_truncate'
      )
      AND NOT trigger_row.tgisinternal
  ) target_objects;
  IF target_object_count = 8 THEN
    RAISE EXCEPTION '062_already_applied';
  ELSIF target_object_count <> 0 THEN
    RAISE EXCEPTION '062_partial_state_rejected';
  END IF;

  SELECT pg_catalog.count(*)::integer
    INTO unknown_object_count
  FROM (
    SELECT class_row.oid
    FROM pg_catalog.pg_class class_row
    JOIN pg_catalog.pg_namespace namespace_row
      ON namespace_row.oid = class_row.relnamespace
    WHERE namespace_row.nspname = 'public'
      AND (
        class_row.relname LIKE 'idx_062_n6_ai_shadow_observation_%'
        OR class_row.relname LIKE
             'n6_ai_shadow_observation_run_audit%'
      )
    UNION ALL
    SELECT function_row.oid
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_namespace namespace_row
      ON namespace_row.oid = function_row.pronamespace
    WHERE namespace_row.nspname = 'public'
      AND function_row.proname LIKE
            'n6_ai_shadow_observation_run_audit%'
  ) unknown_objects;
  IF unknown_object_count <> 0 THEN
    RAISE EXCEPTION '062_unknown_state_rejected';
  END IF;
END;
$preflight$;

CREATE TABLE public.n6_ai_shadow_observation_run_audit (
  audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  observation_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  trade_date DATE NOT NULL,
  ai_user_id BIGINT NOT NULL
    REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user',
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  system_fingerprint TEXT NOT NULL,
  one_shot_status TEXT NOT NULL,
  identity_probe_succeeded BOOLEAN NOT NULL,
  decision_call_attempted BOOLEAN NOT NULL,
  structure_valid BOOLEAN,
  context_snapshot_id BIGINT
    REFERENCES public.n6_ai_context_snapshot(ai_context_snapshot_id),
  decision_run_id BIGINT
    REFERENCES public.n6_ai_decision_run(ai_decision_run_id),
  decision_id BIGINT
    REFERENCES public.n6_ai_decision(ai_decision_id),
  server_risk_allowed BOOLEAN,
  server_risk_reason TEXT,
  proposal_created BOOLEAN NOT NULL,
  proposal_created_count BIGINT NOT NULL,
  order_created_count BIGINT NOT NULL,
  trade_created_count BIGINT NOT NULL,
  position_mutation_count BIGINT NOT NULL,
  lot_mutation_count BIGINT NOT NULL,
  cash_mutation_count BIGINT NOT NULL,
  input_token_count BIGINT,
  output_token_count BIGINT,
  total_token_count BIGINT,
  cache_hit_token_count BIGINT,
  cache_miss_token_count BIGINT,
  latency_ms BIGINT,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CONSTRAINT n6_ai_shadow_observation_062_run_id_ck CHECK (
    observation_run_id ~ '^[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}$'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_dedup_ck CHECK (
    dedup_key ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_actor_ck CHECK (
    principal_type = 'ai_user'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_provider_ck CHECK (
    provider = 'deepseek' AND model = 'deepseek-v4-pro'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_fingerprint_ck CHECK (
    system_fingerprint ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_status_ck CHECK (
    one_shot_status ~ '^[a-z][a-z0-9_]{0,63}$'
  ),
  CONSTRAINT n6_ai_shadow_observation_062_probe_ck CHECK (
    identity_probe_succeeded = true
  ),
  CONSTRAINT n6_ai_shadow_observation_062_attempt_matrix_ck CHECK (
    (
      decision_call_attempted = false
      AND structure_valid IS NULL
      AND decision_run_id IS NULL
      AND decision_id IS NULL
      AND server_risk_allowed IS NULL
      AND server_risk_reason IS NULL
    )
    OR
    (
      decision_call_attempted = true
      AND structure_valid IS NOT NULL
    )
  ),
  CONSTRAINT n6_ai_shadow_observation_062_invalid_structure_ck CHECK (
    structure_valid IS DISTINCT FROM false
    OR (
      decision_run_id IS NULL
      AND decision_id IS NULL
      AND server_risk_allowed IS NULL
      AND server_risk_reason IS NULL
    )
  ),
  CONSTRAINT n6_ai_shadow_observation_062_decision_reference_ck CHECK (
    (decision_run_id IS NULL) = (decision_id IS NULL)
    AND (
      decision_id IS NULL
      OR (
        decision_call_attempted = true
        AND structure_valid = true
        AND context_snapshot_id IS NOT NULL
        AND server_risk_allowed IS NOT NULL
        AND server_risk_reason IS NOT NULL
        AND server_risk_reason ~ '^[a-z][a-z0-9_]{0,127}$'
      )
    )
  ),
  CONSTRAINT n6_ai_shadow_observation_062_risk_pair_ck CHECK (
    (server_risk_allowed IS NULL) =
      (server_risk_reason IS NULL)
    AND (
      server_risk_reason IS NULL
      OR server_risk_reason ~ '^[a-z][a-z0-9_]{0,127}$'
    )
  ),
  CONSTRAINT n6_ai_shadow_observation_062_no_new_input_ck CHECK (
    one_shot_status <> 'no_new_input'
    OR (
      decision_call_attempted = false
      AND structure_valid IS NULL
      AND context_snapshot_id IS NULL
      AND decision_run_id IS NULL
      AND decision_id IS NULL
      AND server_risk_allowed IS NULL
      AND server_risk_reason IS NULL
      AND proposal_created = false
      AND proposal_created_count = 0
      AND order_created_count = 0
      AND trade_created_count = 0
      AND position_mutation_count = 0
      AND lot_mutation_count = 0
      AND cash_mutation_count = 0
    )
  ),
  CONSTRAINT n6_ai_shadow_observation_062_side_effect_ck CHECK (
    proposal_created_count >= 0
    AND order_created_count >= 0
    AND trade_created_count >= 0
    AND position_mutation_count >= 0
    AND lot_mutation_count >= 0
    AND cash_mutation_count >= 0
    AND proposal_created = (proposal_created_count > 0)
  ),
  CONSTRAINT n6_ai_shadow_observation_062_usage_ck CHECK (
    pg_catalog.num_nonnulls(
      input_token_count, output_token_count, total_token_count
    ) IN (0, 3)
    AND (
      total_token_count IS NULL
      OR (
        input_token_count >= 0
        AND output_token_count >= 0
        AND total_token_count >= input_token_count + output_token_count
      )
    )
    AND pg_catalog.num_nonnulls(
      cache_hit_token_count, cache_miss_token_count
    ) IN (0, 2)
    AND COALESCE(cache_hit_token_count >= 0, true)
    AND COALESCE(cache_miss_token_count >= 0, true)
    AND COALESCE(latency_ms >= 0, true)
  ),
  CONSTRAINT n6_ai_shadow_observation_062_time_ck CHECK (
    finished_at >= started_at
  ),
  CONSTRAINT n6_ai_shadow_observation_062_payload_hash_ck CHECK (
    payload_hash ~ '^[0-9a-f]{64}$'
  )
);

ALTER TABLE public.n6_ai_shadow_observation_run_audit
  OWNER TO ashare_v3_user;
ALTER SEQUENCE
  public.n6_ai_shadow_observation_run_audit_audit_id_seq
  OWNER TO ashare_v3_user;

CREATE UNIQUE INDEX idx_062_n6_ai_shadow_observation_dedup
ON public.n6_ai_shadow_observation_run_audit(dedup_key);

CREATE INDEX idx_062_n6_ai_shadow_observation_window
ON public.n6_ai_shadow_observation_run_audit(
  provider, model, system_fingerprint, trade_date, audit_id
);

CREATE OR REPLACE FUNCTION
public.n6_ai_shadow_observation_run_audit_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION '062_append_only_audit_history';
END;
$function$;

ALTER FUNCTION
public.n6_ai_shadow_observation_run_audit_append_only_guard()
OWNER TO ashare_v3_user;

CREATE TRIGGER trg_062_n6_ai_shadow_observation_append_only_row
BEFORE UPDATE OR DELETE
ON public.n6_ai_shadow_observation_run_audit
FOR EACH ROW
EXECUTE FUNCTION
  public.n6_ai_shadow_observation_run_audit_append_only_guard();

CREATE TRIGGER trg_062_n6_ai_shadow_observation_append_only_truncate
BEFORE TRUNCATE
ON public.n6_ai_shadow_observation_run_audit
FOR EACH STATEMENT
EXECUTE FUNCTION
  public.n6_ai_shadow_observation_run_audit_append_only_guard();

CREATE OR REPLACE FUNCTION
public.n6_ai_shadow_observation_run_audit_record(p_payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  actor record;
  unknown_key text;
  target_observation_run_id text;
  target_dedup_key text;
  target_trade_date date;
  target_provider text;
  target_model text;
  target_system_fingerprint text;
  target_one_shot_status text;
  target_identity_probe_succeeded boolean;
  target_decision_call_attempted boolean;
  target_structure_valid boolean;
  target_context_snapshot_id bigint;
  target_decision_run_id bigint;
  target_decision_id bigint;
  resolved_decision_run_id bigint;
  resolved_decision_count bigint;
  target_server_risk_allowed boolean;
  target_server_risk_reason text;
  target_proposal_created boolean;
  target_proposal_created_count bigint;
  target_order_created_count bigint;
  target_trade_created_count bigint;
  target_position_mutation_count bigint;
  target_lot_mutation_count bigint;
  target_cash_mutation_count bigint;
  target_input_token_count bigint;
  target_output_token_count bigint;
  target_total_token_count bigint;
  target_cache_hit_token_count bigint;
  target_cache_miss_token_count bigint;
  target_latency_ms bigint;
  target_started_at timestamptz;
  target_finished_at timestamptz;
  target_payload_hash text;
  existing_audit_id bigint;
  existing_payload_hash text;
  created_audit_id bigint;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR CURRENT_USER <> 'ashare_v3_user'
     OR p_payload IS NULL
     OR pg_catalog.jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_request_rejected'
    );
  END IF;

  SELECT key
    INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN (
    'observation_run_id', 'dedup_key', 'trade_date',
    'provider', 'model', 'system_fingerprint', 'one_shot_status',
    'identity_probe_succeeded', 'decision_call_attempted',
    'structure_valid', 'context_snapshot_id', 'decision_run_id',
    'decision_id', 'server_risk_allowed', 'server_risk_reason',
    'proposal_created', 'proposal_created_count',
    'order_created_count', 'trade_created_count',
    'position_mutation_count', 'lot_mutation_count',
    'cash_mutation_count', 'input_token_count',
    'output_token_count', 'total_token_count',
    'cache_hit_token_count', 'cache_miss_token_count',
    'latency_ms', 'started_at', 'finished_at'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR NOT (
       p_payload ?& ARRAY[
         'observation_run_id', 'dedup_key', 'trade_date',
         'provider', 'model', 'system_fingerprint',
         'one_shot_status', 'identity_probe_succeeded',
         'decision_call_attempted', 'proposal_created',
         'proposal_created_count', 'order_created_count',
         'trade_created_count', 'position_mutation_count',
         'lot_mutation_count', 'cash_mutation_count',
         'started_at', 'finished_at'
       ]
     )
     OR p_payload ?| ARRAY[
       'prompt', 'prompt_text', 'content', 'raw_content',
       'reasoning', 'reasoning_content', 'credential',
       'api_key', 'session', 'session_id', 'session_token',
       'session_token_hash', 'human_user_id', 'owner_user_id',
       'human_private_data'
     ] THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_contract_rejected'
    );
  END IF;

  IF COALESCE(p_payload->>'trade_date', '') !~
       '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
     OR COALESCE(p_payload->>'started_at', '') !~
       '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
     OR COALESCE(p_payload->>'finished_at', '') !~
       '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_time_format_rejected'
    );
  END IF;

  BEGIN
    target_observation_run_id := p_payload->>'observation_run_id';
    target_dedup_key := p_payload->>'dedup_key';
    target_trade_date := (p_payload->>'trade_date')::date;
    target_provider := p_payload->>'provider';
    target_model := p_payload->>'model';
    target_system_fingerprint := p_payload->>'system_fingerprint';
    target_one_shot_status := p_payload->>'one_shot_status';
    target_identity_probe_succeeded :=
      (p_payload->>'identity_probe_succeeded')::boolean;
    target_decision_call_attempted :=
      (p_payload->>'decision_call_attempted')::boolean;
    target_structure_valid :=
      NULLIF(p_payload->>'structure_valid', '')::boolean;
    target_context_snapshot_id :=
      NULLIF(p_payload->>'context_snapshot_id', '')::bigint;
    target_decision_run_id :=
      NULLIF(p_payload->>'decision_run_id', '')::bigint;
    target_decision_id :=
      NULLIF(p_payload->>'decision_id', '')::bigint;
    target_server_risk_allowed :=
      NULLIF(p_payload->>'server_risk_allowed', '')::boolean;
    target_server_risk_reason :=
      NULLIF(p_payload->>'server_risk_reason', '');
    target_proposal_created :=
      (p_payload->>'proposal_created')::boolean;
    target_proposal_created_count :=
      (p_payload->>'proposal_created_count')::bigint;
    target_order_created_count :=
      (p_payload->>'order_created_count')::bigint;
    target_trade_created_count :=
      (p_payload->>'trade_created_count')::bigint;
    target_position_mutation_count :=
      (p_payload->>'position_mutation_count')::bigint;
    target_lot_mutation_count :=
      (p_payload->>'lot_mutation_count')::bigint;
    target_cash_mutation_count :=
      (p_payload->>'cash_mutation_count')::bigint;
    target_input_token_count :=
      NULLIF(p_payload->>'input_token_count', '')::bigint;
    target_output_token_count :=
      NULLIF(p_payload->>'output_token_count', '')::bigint;
    target_total_token_count :=
      NULLIF(p_payload->>'total_token_count', '')::bigint;
    target_cache_hit_token_count :=
      NULLIF(p_payload->>'cache_hit_token_count', '')::bigint;
    target_cache_miss_token_count :=
      NULLIF(p_payload->>'cache_miss_token_count', '')::bigint;
    target_latency_ms :=
      NULLIF(p_payload->>'latency_ms', '')::bigint;
    target_started_at := (p_payload->>'started_at')::timestamptz;
    target_finished_at := (p_payload->>'finished_at')::timestamptz;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'observation_audit_value_rejected'
      );
  END;

  IF target_decision_id IS NULL
     AND target_decision_run_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'observation_audit_decision_reference_rejected'
    );
  ELSIF target_decision_id IS NOT NULL THEN
    SELECT pg_catalog.count(*),
           pg_catalog.min(decision.ai_decision_run_id)
      INTO resolved_decision_count, resolved_decision_run_id
    FROM public.n6_ai_decision decision
    JOIN public.n6_ai_decision_run decision_run
      ON decision_run.ai_decision_run_id =
           decision.ai_decision_run_id
    WHERE decision.ai_decision_id = target_decision_id;
    IF resolved_decision_count <> 1
       OR resolved_decision_run_id IS NULL
       OR (
         target_decision_run_id IS NOT NULL
         AND target_decision_run_id IS DISTINCT FROM
               resolved_decision_run_id
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false,
        'status', 'observation_audit_decision_reference_rejected'
      );
    END IF;
    target_decision_run_id := resolved_decision_run_id;
  END IF;

  IF target_observation_run_id !~
       '^[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}$'
     OR target_dedup_key !~ '^[0-9a-f]{64}$'
     OR target_provider <> 'deepseek'
     OR target_model <> 'deepseek-v4-pro'
     OR target_system_fingerprint !~
          '^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$'
     OR target_one_shot_status !~ '^[a-z][a-z0-9_]{0,63}$'
     OR target_identity_probe_succeeded IS DISTINCT FROM true
     OR (
       target_decision_call_attempted = false
       AND target_structure_valid IS NOT NULL
     )
     OR (
       target_decision_call_attempted = true
       AND target_structure_valid IS NULL
     )
     OR (
       target_structure_valid IS false
       AND (
         target_decision_run_id IS NOT NULL
         OR target_decision_id IS NOT NULL
         OR target_server_risk_allowed IS NOT NULL
         OR target_server_risk_reason IS NOT NULL
       )
     )
     OR (target_decision_run_id IS NULL) <>
          (target_decision_id IS NULL)
     OR (target_server_risk_allowed IS NULL) <>
          (target_server_risk_reason IS NULL)
     OR (
       target_server_risk_reason IS NOT NULL
       AND target_server_risk_reason !~
             '^[a-z][a-z0-9_]{0,127}$'
     )
     OR (
       target_decision_id IS NOT NULL
       AND (
         target_structure_valid IS DISTINCT FROM true
         OR target_context_snapshot_id IS NULL
         OR target_server_risk_allowed IS NULL
       )
     )
     OR (
       target_one_shot_status = 'no_new_input'
       AND (
         target_decision_call_attempted IS DISTINCT FROM false
         OR target_structure_valid IS NOT NULL
         OR target_context_snapshot_id IS NOT NULL
         OR target_decision_run_id IS NOT NULL
         OR target_decision_id IS NOT NULL
         OR target_server_risk_allowed IS NOT NULL
         OR target_server_risk_reason IS NOT NULL
         OR target_proposal_created IS DISTINCT FROM false
         OR target_proposal_created_count <> 0
         OR target_order_created_count <> 0
         OR target_trade_created_count <> 0
         OR target_position_mutation_count <> 0
         OR target_lot_mutation_count <> 0
         OR target_cash_mutation_count <> 0
       )
     )
     OR target_proposal_created_count < 0
     OR target_order_created_count < 0
     OR target_trade_created_count < 0
     OR target_position_mutation_count < 0
     OR target_lot_mutation_count < 0
     OR target_cash_mutation_count < 0
     OR target_proposal_created <>
          (target_proposal_created_count > 0)
     OR pg_catalog.num_nonnulls(
          target_input_token_count,
          target_output_token_count,
          target_total_token_count
        ) NOT IN (0, 3)
     OR (
       target_total_token_count IS NOT NULL
       AND (
         target_input_token_count < 0
         OR target_output_token_count < 0
         OR target_total_token_count <
              target_input_token_count + target_output_token_count
       )
     )
     OR pg_catalog.num_nonnulls(
          target_cache_hit_token_count,
          target_cache_miss_token_count
        ) NOT IN (0, 2)
     OR COALESCE(target_cache_hit_token_count < 0, false)
     OR COALESCE(target_cache_miss_token_count < 0, false)
     OR COALESCE(target_latency_ms < 0, false)
     OR target_finished_at < target_started_at THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_state_rejected'
    );
  END IF;

  SELECT pg_catalog.min(ai.ai_user_id) AS ai_user_id,
         pg_catalog.min(ai.principal_id) AS principal_id,
         pg_catalog.count(*) AS authority_count
    INTO actor
  FROM public.n6_ai_user ai
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  WHERE ai.status IN ('sandbox_only', 'active');
  IF actor.authority_count <> 1
     OR actor.ai_user_id IS NULL
     OR actor.principal_id IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_authority_rejected'
    );
  END IF;

  IF target_context_snapshot_id IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
       FROM public.n6_ai_context_snapshot context_snapshot
       WHERE context_snapshot.ai_context_snapshot_id =
               target_context_snapshot_id
         AND context_snapshot.ai_user_id = actor.ai_user_id
         AND context_snapshot.principal_id = actor.principal_id
         AND context_snapshot.principal_type = 'ai_user'
         AND context_snapshot.for_trade_date = target_trade_date
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_context_rejected'
    );
  END IF;

  IF target_decision_id IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
       FROM public.n6_ai_decision decision
       JOIN public.n6_ai_decision_run decision_run
         ON decision_run.ai_decision_run_id =
              decision.ai_decision_run_id
       JOIN public.n6_ai_context_snapshot context_snapshot
         ON context_snapshot.ai_context_snapshot_id =
              decision_run.ai_context_snapshot_id
       WHERE decision.ai_decision_id = target_decision_id
         AND decision.ai_decision_run_id = target_decision_run_id
         AND decision.ai_user_id = actor.ai_user_id
         AND decision.principal_id = actor.principal_id
         AND decision.principal_type = 'ai_user'
         AND decision.server_risk_allowed =
               target_server_risk_allowed
         AND decision.server_risk_reason =
               target_server_risk_reason
         AND context_snapshot.ai_context_snapshot_id =
               target_context_snapshot_id
         AND context_snapshot.for_trade_date = target_trade_date
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'observation_audit_decision_rejected'
    );
  END IF;

  target_payload_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'observation_run_id', target_observation_run_id,
          'dedup_key', target_dedup_key,
          'trade_date',
            pg_catalog.to_char(target_trade_date, 'YYYY-MM-DD'),
          'ai_user_id', actor.ai_user_id,
          'principal_id', actor.principal_id,
          'provider', target_provider,
          'model', target_model,
          'system_fingerprint', target_system_fingerprint,
          'one_shot_status', target_one_shot_status,
          'identity_probe_succeeded',
            target_identity_probe_succeeded,
          'decision_call_attempted',
            target_decision_call_attempted,
          'structure_valid', target_structure_valid,
          'context_snapshot_id', target_context_snapshot_id,
          'decision_run_id', target_decision_run_id,
          'decision_id', target_decision_id,
          'server_risk_allowed', target_server_risk_allowed,
          'server_risk_reason', target_server_risk_reason,
          'proposal_created', target_proposal_created,
          'proposal_created_count', target_proposal_created_count,
          'order_created_count', target_order_created_count,
          'trade_created_count', target_trade_created_count,
          'position_mutation_count', target_position_mutation_count,
          'lot_mutation_count', target_lot_mutation_count,
          'cash_mutation_count', target_cash_mutation_count,
          'input_token_count', target_input_token_count,
          'output_token_count', target_output_token_count,
          'total_token_count', target_total_token_count,
          'cache_hit_token_count', target_cache_hit_token_count,
          'cache_miss_token_count', target_cache_miss_token_count,
          'latency_ms', target_latency_ms,
          'started_at_epoch',
            EXTRACT(EPOCH FROM target_started_at),
          'finished_at_epoch',
            EXTRACT(EPOCH FROM target_finished_at)
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );

  INSERT INTO public.n6_ai_shadow_observation_run_audit (
    observation_run_id, dedup_key, trade_date,
    ai_user_id, principal_id, principal_type,
    provider, model, system_fingerprint, one_shot_status,
    identity_probe_succeeded, decision_call_attempted,
    structure_valid, context_snapshot_id, decision_run_id,
    decision_id, server_risk_allowed, server_risk_reason,
    proposal_created, proposal_created_count,
    order_created_count, trade_created_count,
    position_mutation_count, lot_mutation_count,
    cash_mutation_count, input_token_count, output_token_count,
    total_token_count, cache_hit_token_count,
    cache_miss_token_count, latency_ms,
    started_at, finished_at, payload_hash
  )
  VALUES (
    target_observation_run_id, target_dedup_key, target_trade_date,
    actor.ai_user_id, actor.principal_id, 'ai_user',
    target_provider, target_model, target_system_fingerprint,
    target_one_shot_status, target_identity_probe_succeeded,
    target_decision_call_attempted, target_structure_valid,
    target_context_snapshot_id, target_decision_run_id,
    target_decision_id, target_server_risk_allowed,
    target_server_risk_reason, target_proposal_created,
    target_proposal_created_count, target_order_created_count,
    target_trade_created_count, target_position_mutation_count,
    target_lot_mutation_count, target_cash_mutation_count,
    target_input_token_count, target_output_token_count,
    target_total_token_count, target_cache_hit_token_count,
    target_cache_miss_token_count, target_latency_ms,
    target_started_at, target_finished_at, target_payload_hash
  )
  ON CONFLICT (dedup_key) DO NOTHING
  RETURNING audit_id INTO created_audit_id;

  IF created_audit_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'observation_audit_recorded',
      'audit_id', created_audit_id
    );
  END IF;

  SELECT audit.audit_id, audit.payload_hash
    INTO existing_audit_id, existing_payload_hash
  FROM public.n6_ai_shadow_observation_run_audit audit
  WHERE audit.dedup_key = target_dedup_key;
  IF existing_payload_hash = target_payload_hash THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'observation_audit_already_recorded',
      'audit_id', existing_audit_id
    );
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'ok', false, 'status', 'observation_audit_dedup_conflict'
  );
END;
$function$;

ALTER FUNCTION
public.n6_ai_shadow_observation_run_audit_record(jsonb)
OWNER TO ashare_v3_user;

REVOKE ALL ON TABLE
  public.n6_ai_shadow_observation_run_audit
FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON SEQUENCE
  public.n6_ai_shadow_observation_run_audit_audit_id_seq
FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION
  public.n6_ai_shadow_observation_run_audit_append_only_guard()
FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION
  public.n6_ai_shadow_observation_run_audit_record(jsonb)
FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION
  public.n6_ai_shadow_observation_run_audit_record(jsonb)
TO n6_ai_agent;

DO $postflight$
DECLARE
  relation_expectation record;
  function_expectation record;
  role_expectation record;
  relation_oid oid;
  relation_kind "char";
  function_oid oid;
  function_row record;
  allowed_role_oid oid;
  unexpected_acl_count integer;
  privilege_name text;
  trigger_count integer;
  role_oid oid;
  direct_execute_count integer;
  direct_grantable_count integer;
BEGIN
  FOR relation_expectation IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_ai_shadow_observation_run_audit'::text,
        'r'::text
      ),
      (
        'public.n6_ai_shadow_observation_run_audit_audit_id_seq'::text,
        'S'::text
      )
    ) expected_relation(relation_name, expected_kind)
  LOOP
    relation_oid :=
      pg_catalog.to_regclass(relation_expectation.relation_name);
    SELECT class_row.relkind
      INTO relation_kind
    FROM pg_catalog.pg_class class_row
    JOIN pg_catalog.pg_roles owner_role
      ON owner_role.oid = class_row.relowner
    WHERE class_row.oid = relation_oid
      AND owner_role.rolname = 'ashare_v3_user';
    IF relation_oid IS NULL
       OR relation_kind::text <>
            relation_expectation.expected_kind THEN
      RAISE EXCEPTION '062_postflight_relation_state_mismatch: %',
        relation_expectation.relation_name;
    END IF;

    SELECT pg_catalog.count(*)::integer
      INTO unexpected_acl_count
    FROM pg_catalog.pg_class class_row
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        class_row.relacl,
        pg_catalog.acldefault(
          CASE
            WHEN relation_kind = 'S' THEN 's'::"char"
            ELSE 'r'::"char"
          END,
          class_row.relowner
        )
      )
    ) relation_acl
    WHERE class_row.oid = relation_oid
      AND relation_acl.grantee <> class_row.relowner;
    IF unexpected_acl_count <> 0 THEN
      RAISE EXCEPTION '062_postflight_relation_acl_mismatch: %',
        relation_expectation.relation_name;
    END IF;

    FOR role_expectation IN
      SELECT role_name
      FROM (VALUES
        ('n6_ai_agent'::text),
        ('n6_btrack_web'::text),
        ('n6_virtual_executor'::text)
      ) expected_role(role_name)
    LOOP
      IF relation_kind = 'S' THEN
        FOREACH privilege_name IN ARRAY
          ARRAY['USAGE', 'SELECT', 'UPDATE']::text[]
        LOOP
          IF pg_catalog.has_sequence_privilege(
               role_expectation.role_name,
               relation_expectation.relation_name,
               privilege_name
             ) THEN
            RAISE EXCEPTION
              '062_postflight_sequence_privilege_mismatch: %.%.%',
              relation_expectation.relation_name,
              role_expectation.role_name,
              privilege_name;
          END IF;
        END LOOP;
      ELSE
        FOREACH privilege_name IN ARRAY ARRAY[
          'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
          'REFERENCES', 'TRIGGER'
        ]::text[]
        LOOP
          IF pg_catalog.has_table_privilege(
               role_expectation.role_name,
               relation_expectation.relation_name,
               privilege_name
             ) THEN
            RAISE EXCEPTION
              '062_postflight_table_privilege_mismatch: %.%.%',
              relation_expectation.relation_name,
              role_expectation.role_name,
              privilege_name;
          END IF;
        END LOOP;
      END IF;
    END LOOP;
  END LOOP;

  FOR function_expectation IN
    SELECT *
    FROM (VALUES
      (
        'n6_ai_shadow_observation_run_audit_record(jsonb)'::text,
        'n6_ai_agent'::text
      ),
      (
        'n6_ai_shadow_observation_run_audit_append_only_guard()'::text,
        NULL::text
      )
    ) expected_function(signature, allowed_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || function_expectation.signature
    );
    SELECT function_proc.prosecdef,
           function_proc.proisstrict,
           function_proc.proleakproof,
           function_proc.provolatile,
           function_proc.proparallel,
           function_proc.proconfig,
           function_proc.proacl,
           function_proc.proowner,
           owner_role.rolname AS owner_name,
           language_row.lanname AS language_name
      INTO function_row
    FROM pg_catalog.pg_proc function_proc
    JOIN pg_catalog.pg_roles owner_role
      ON owner_role.oid = function_proc.proowner
    JOIN pg_catalog.pg_language language_row
      ON language_row.oid = function_proc.prolang
    WHERE function_proc.oid = function_oid;
    IF function_oid IS NULL
       OR function_row.owner_name IS DISTINCT FROM 'ashare_v3_user'
       OR function_row.language_name IS DISTINCT FROM 'plpgsql'
       OR function_row.prosecdef IS DISTINCT FROM true
       OR function_row.proisstrict IS DISTINCT FROM false
       OR function_row.proleakproof IS DISTINCT FROM false
       OR function_row.provolatile IS DISTINCT FROM 'v'
       OR function_row.proparallel IS DISTINCT FROM 'u'
       OR function_row.proconfig IS DISTINCT FROM
            ARRAY['search_path=pg_catalog']::text[] THEN
      RAISE EXCEPTION '062_postflight_function_state_mismatch: %',
        function_expectation.signature;
    END IF;

    allowed_role_oid := NULL;
    IF function_expectation.allowed_role IS NOT NULL THEN
      SELECT role.oid
        INTO allowed_role_oid
      FROM pg_catalog.pg_roles role
      WHERE role.rolname = function_expectation.allowed_role;
    END IF;
    IF (
      SELECT pg_catalog.count(*)
      FROM pg_catalog.aclexplode(
        COALESCE(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) function_acl
      WHERE NOT (
        (
          function_acl.grantee = function_row.proowner
          OR (
            allowed_role_oid IS NOT NULL
            AND function_acl.grantee = allowed_role_oid
          )
        )
        AND function_acl.privilege_type = 'EXECUTE'
        AND NOT function_acl.is_grantable
      )
    ) <> 0 THEN
      RAISE EXCEPTION '062_postflight_function_acl_mismatch: %',
        function_expectation.signature;
    END IF;

    FOR role_expectation IN
      SELECT role_name
      FROM (VALUES
        ('n6_ai_agent'::text),
        ('n6_btrack_web'::text),
        ('n6_virtual_executor'::text)
      ) expected_role(role_name)
    LOOP
      SELECT role.oid
        INTO role_oid
      FROM pg_catalog.pg_roles role
      WHERE role.rolname = role_expectation.role_name;
      SELECT pg_catalog.count(*) FILTER (
               WHERE function_acl.privilege_type = 'EXECUTE'
                 AND NOT function_acl.is_grantable
             )::integer,
             pg_catalog.count(*) FILTER (
               WHERE function_acl.privilege_type = 'EXECUTE'
                 AND function_acl.is_grantable
             )::integer
        INTO direct_execute_count, direct_grantable_count
      FROM pg_catalog.aclexplode(
        COALESCE(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) function_acl
      WHERE function_acl.grantee = role_oid;
      IF role_expectation.role_name =
           function_expectation.allowed_role THEN
        IF NOT pg_catalog.has_function_privilege(
                 role_expectation.role_name,
                 'public.' || function_expectation.signature,
                 'EXECUTE'
               )
           OR direct_execute_count <> 1
           OR direct_grantable_count <> 0 THEN
          RAISE EXCEPTION
            '062_postflight_function_grant_mismatch: %.%',
            function_expectation.signature,
            role_expectation.role_name;
        END IF;
      ELSIF pg_catalog.has_function_privilege(
              role_expectation.role_name,
              'public.' || function_expectation.signature,
              'EXECUTE'
            )
            OR direct_execute_count <> 0
            OR direct_grantable_count <> 0 THEN
        RAISE EXCEPTION
          '062_postflight_function_grant_mismatch: %.%',
          function_expectation.signature,
          role_expectation.role_name;
      END IF;
    END LOOP;
  END LOOP;

  SELECT pg_catalog.count(*)::integer
    INTO trigger_count
  FROM pg_catalog.pg_trigger trigger_row
  JOIN pg_catalog.pg_class class_row
    ON class_row.oid = trigger_row.tgrelid
  WHERE class_row.oid =
          'public.n6_ai_shadow_observation_run_audit'::regclass
    AND NOT trigger_row.tgisinternal
    AND (
      (
        trigger_row.tgname =
          'trg_062_n6_ai_shadow_observation_append_only_row'
        AND trigger_row.tgtype = 27
        AND trigger_row.tgenabled = 'O'
      )
      OR
      (
        trigger_row.tgname =
          'trg_062_n6_ai_shadow_observation_append_only_truncate'
        AND trigger_row.tgtype = 34
        AND trigger_row.tgenabled = 'O'
      )
    )
    AND trigger_row.tgfoid = pg_catalog.to_regprocedure(
          'public.n6_ai_shadow_observation_run_audit_append_only_guard()'
        );
  IF trigger_count <> 2 THEN
    RAISE EXCEPTION '062_postflight_append_only_trigger_mismatch';
  END IF;

  IF NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_index index_row
       WHERE index_row.indexrelid =
         'public.idx_062_n6_ai_shadow_observation_dedup'::regclass
         AND index_row.indrelid =
           'public.n6_ai_shadow_observation_run_audit'::regclass
         AND index_row.indisunique
         AND index_row.indisvalid
     )
     OR NOT EXISTS (
       SELECT 1
       FROM pg_catalog.pg_index index_row
       WHERE index_row.indexrelid =
         'public.idx_062_n6_ai_shadow_observation_window'::regclass
         AND index_row.indrelid =
           'public.n6_ai_shadow_observation_run_audit'::regclass
         AND NOT index_row.indisunique
         AND index_row.indisvalid
     ) THEN
    RAISE EXCEPTION '062_postflight_index_mismatch';
  END IF;
END;
$postflight$;

COMMIT;
