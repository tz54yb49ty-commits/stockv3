BEGIN;

DO $gate$
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '058_migration_identity_mismatch';
  END IF;
  IF pg_catalog.to_regclass('public.n6_ai_context_snapshot') IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_agent_context_load(text,date,integer)'
        ) IS NULL THEN
    RAISE EXCEPTION '058_requires_055';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = 'n6_ai_agent'
      AND rolcanlogin = true
      AND rolsuper = false
      AND rolcreaterole = false
      AND rolcreatedb = false
      AND rolreplication = false
      AND rolbypassrls = false
  ) THEN
    RAISE EXCEPTION '058_ai_role_contract_mismatch';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '058_already_applied';
  END IF;
END
$gate$;

ALTER TABLE public.n6_ai_context_snapshot
  ADD COLUMN knowledge_bundle_hash TEXT,
  ADD COLUMN universe_snapshot_hash TEXT,
  ADD COLUMN memory_snapshot_hash TEXT,
  ADD COLUMN workset_hash TEXT,
  ADD CONSTRAINT n6_ai_context_snapshot_058_hashes_ck CHECK (
    (
      knowledge_bundle_hash IS NULL
      AND universe_snapshot_hash IS NULL
      AND memory_snapshot_hash IS NULL
      AND workset_hash IS NULL
    )
    OR
    (
      knowledge_bundle_hash ~ '^[0-9a-f]{64}$'
      AND universe_snapshot_hash ~ '^[0-9a-f]{64}$'
      AND memory_snapshot_hash ~ '^[0-9a-f]{64}$'
      AND workset_hash ~ '^[0-9a-f]{64}$'
    )
  );

CREATE OR REPLACE FUNCTION public.n6_ai_agent_context_load_v2(
  p_run_bucket text,
  p_for_trade_date date,
  p_max_signals integer,
  p_knowledge_bundle_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  expected_bundle_hash constant text :=
    '1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc';
  base_result jsonb;
  base_status text;
  snapshot_id bigint;
  context_payload jsonb;
  stored_bundle_hash text;
  stored_universe_hash text;
  stored_memory_hash text;
  stored_workset_hash text;
  computed_universe_hash text;
  computed_memory_hash text;
  computed_workset_hash text;
  eligible_signal_count integer;
  market_context_count integer;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_run_bucket IS NULL
     OR p_run_bucket !~
          '^(daily:[0-9]{8}|[0-9]{8}T[0-9]{4}[+-][0-9]{4})$'
     OR p_for_trade_date IS NULL
     OR p_for_trade_date <>
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR (
          CASE
            WHEN p_run_bucket LIKE 'daily:%'
              THEN pg_catalog.substr(p_run_bucket, 7, 8)
            ELSE pg_catalog.substr(p_run_bucket, 1, 8)
          END
        ) <> pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD')
     OR p_knowledge_bundle_hash IS NULL
     OR p_knowledge_bundle_hash <> expected_bundle_hash
     OR p_max_signals <> 1000 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'invalid_context_v2_request'
    );
  END IF;

  LOCK TABLE public.n6_ai_shared_signal_projection IN SHARE MODE;
  LOCK TABLE public.user_projection_run IN SHARE MODE;

  SELECT pg_catalog.count(*) FILTER (
           WHERE eligible_signal.asset_kind = 'stock'
         )::integer,
         pg_catalog.count(*) FILTER (
           WHERE eligible_signal.asset_kind IN ('index', 'board')
         )::integer
    INTO eligible_signal_count, market_context_count
  FROM (
    SELECT DISTINCT shared.asset_kind,
           shared.source_event_id,
           shared.identity_key,
           shared.direction
    FROM public.n6_ai_shared_signal_projection shared
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           shared.user_projection_run_id
     AND projection_run.status IN ('passed', 'ready')
    WHERE shared.shared_status = 'active'
      AND (
        (
          shared.asset_kind = 'stock'
          AND shared.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
        )
        OR (
          shared.asset_kind = 'index'
          AND shared.identity_key ~ '^index:(SH|SZ):[0-9]{6}$'
        )
        OR (
          shared.asset_kind = 'board'
          AND shared.identity_key ~ '^board:TDX:[0-9]{6}$'
        )
      )
      AND shared.direction IN ('buy', 'sell')
      AND shared.for_trade_date = p_for_trade_date
      AND shared.action_state IN ('eligible', 'executed')
  ) eligible_signal;
  IF eligible_signal_count > p_max_signals
     OR market_context_count > p_max_signals THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'signal_universe_too_large',
      'eligible_signal_count', eligible_signal_count,
      'market_context_count', market_context_count
    );
  END IF;

  base_result := public.n6_ai_agent_context_load(
    p_run_bucket,
    p_for_trade_date,
    p_max_signals
  );
  base_status := base_result->>'status';
  IF COALESCE((base_result->>'ok')::boolean, false) = false
     OR base_status NOT IN ('ready', 'already_processed') THEN
    RETURN base_result;
  END IF;
  IF COALESCE(base_result->>'context_snapshot_id', '')
       !~ '^[0-9]+$' THEN
    IF base_status = 'ready' THEN
      RAISE EXCEPTION 'context_v2_created_snapshot_id_missing';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'context_v2_snapshot_missing'
    );
  END IF;
  snapshot_id := (base_result->>'context_snapshot_id')::bigint;

  SELECT snapshot.context_payload_json,
         snapshot.knowledge_bundle_hash,
         snapshot.universe_snapshot_hash,
         snapshot.memory_snapshot_hash,
         snapshot.workset_hash
    INTO context_payload, stored_bundle_hash, stored_universe_hash,
         stored_memory_hash, stored_workset_hash
  FROM public.n6_ai_context_snapshot snapshot
  JOIN public.n6_ai_user ai
    ON ai.ai_user_id = snapshot.ai_user_id
   AND ai.principal_id = snapshot.principal_id
   AND ai.status IN ('sandbox_only', 'active', 'disabled')
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  WHERE snapshot.ai_context_snapshot_id = snapshot_id
    AND snapshot.for_trade_date = p_for_trade_date
    AND snapshot.run_bucket = p_run_bucket
    AND snapshot.principal_type = 'ai_user'
    AND snapshot.context_status = 'frozen'
  FOR UPDATE OF snapshot;
  IF context_payload IS NULL THEN
    IF base_status = 'ready' THEN
      RAISE EXCEPTION 'context_v2_created_snapshot_authority_mismatch';
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'context_v2_authority_mismatch'
    );
  END IF;

  computed_universe_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'signals', context_payload->'signals',
          'market_context', context_payload->'market_context'
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );
  computed_memory_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'positions', context_payload->'positions',
          'portfolio', context_payload->'portfolio',
          'daily_metrics', context_payload->'daily_metrics'
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );
  computed_workset_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'signals', context_payload->'signals',
          'positions', context_payload->'positions',
          'portfolio', context_payload->'portfolio',
          'strategy', context_payload->'strategy'
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );

  IF base_status = 'already_processed' THEN
    IF stored_bundle_hash IS DISTINCT FROM expected_bundle_hash
       OR stored_universe_hash IS DISTINCT FROM computed_universe_hash
       OR stored_memory_hash IS DISTINCT FROM computed_memory_hash
       OR stored_workset_hash IS DISTINCT FROM computed_workset_hash THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false,
        'status', 'context_v2_snapshot_contract_mismatch'
      );
    END IF;
  ELSE
    UPDATE public.n6_ai_context_snapshot snapshot
    SET knowledge_bundle_hash = expected_bundle_hash,
        universe_snapshot_hash = computed_universe_hash,
        memory_snapshot_hash = computed_memory_hash,
        workset_hash = computed_workset_hash
    WHERE snapshot.ai_context_snapshot_id = snapshot_id
      AND snapshot.knowledge_bundle_hash IS NULL
      AND snapshot.universe_snapshot_hash IS NULL
      AND snapshot.memory_snapshot_hash IS NULL
      AND snapshot.workset_hash IS NULL;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'context_v2_created_snapshot_update_failed';
    END IF;
  END IF;

  RETURN base_result || pg_catalog.jsonb_build_object(
    'context_contract_version', 'n6_ai_context_v2',
    'knowledge_bundle_hash', expected_bundle_hash,
    'universe_snapshot_hash', computed_universe_hash,
    'memory_snapshot_hash', computed_memory_hash,
    'workset_hash', computed_workset_hash
  );
END
$function$;

REVOKE ALL ON FUNCTION public.n6_ai_agent_context_load_v2(
  text,date,integer,text
) FROM PUBLIC, n6_btrack_web, n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_context_load(
  text,date,integer
) FROM n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_context_load_v2(
  text,date,integer,text
) TO n6_ai_agent;

COMMIT;
