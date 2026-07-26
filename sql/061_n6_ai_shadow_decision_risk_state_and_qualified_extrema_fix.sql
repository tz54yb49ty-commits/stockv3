BEGIN;

-- Atomically repair six published N6 AI functions from the rolled-back 060 source state.
-- Five qualified-extrema bodies reuse reviewed 060 logic; decision-record isolates duplicate state.
-- Function signatures, business logic outside the isolated defect, owner and ACL are unchanged.

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  source_count integer := 0;
  fixed_count integer := 0;
  error_prefix text := '061_partial_or_source_mismatch';
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '061_owner_session_required';
  END IF;

  FOR expected IN
    SELECT *
    FROM (
      VALUES
      ('n6_ai_agent_daily_summary_record(jsonb)', 'c8e0928d3afb20535792a82b20270d32d66d466a85d0d112aefc64fa8f573a5e', '235b3913734fda03a3d55822d58f785ae3dad36002c38f473bfeaad6636f0042', 'n6_ai_agent'),
      ('n6_ai_agent_context_load(text,date,integer)', 'bbcd60822e8d18e6731ac0f46e68d2dd545dea08a172f28655eead4e1444fa84', '4dae0563b34df9e066c2c91feb6f3a096a09ea2573a31f2cf30c71bfe0704993', NULL::text),
      ('n6_ai_agent_proposal_create_confirm(jsonb)', '2bde0f7d24cd88bc2851fb162b8499730560e8959c8f814d6625a97fe9db063b', 'aa3806a66ed5fa08b3c497e42cfb0142c61759b796891cf81d7c041024de05f2', 'n6_ai_agent'),
      ('n6_ai_executor_risk_recheck(bigint,text)', '51faf7163dd35ead8f290c7a0ec17849f56dd0906339b8de4b7f1c5c932e834c', 'f42d6750d192321f851626428589fdc342355410b7e1c50a33855642661bbf75', 'n6_virtual_executor'),
      ('n6_ai_strategy_shadow_evaluate(date,text,text)', 'a7cd3200d0c4a226c9ea03fc14e62a03f86877f768d991911eafc8b7a13c2cb2', 'fcd1ada453c672c8a2caa5caa4857b15f7d162f2ed5780cda27c7cd41ad6b474', 'n6_ai_agent'),
      ('n6_ai_agent_shadow_decision_record(jsonb)', '8bd6ed7e55ebd3f84178089e64684a66b3b2cbbf03b4f3a8115b997479b953cb', '32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951', 'n6_ai_agent')
    ) AS expected_functions(
      signature, source_sha, fixed_sha, allowed_role
    )
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '061_partial_or_source_mismatch: %',
        expected.signature;
    END IF;
    SELECT function_row.prosrc, function_row.prosecdef,
           function_row.proisstrict, function_row.proleakproof,
           function_row.provolatile, function_row.proparallel,
           function_row.proconfig, function_row.proacl,
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
      SELECT role.oid
        INTO allowed_role_oid
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
      AND function_proc.provolatile = 'v'
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
        (
          expected.allowed_role IS NULL
          AND allowed_role_oid IS NULL
        )
        OR
        (
          expected.allowed_role IS NOT NULL
          AND allowed_role_oid IS NOT NULL
          AND (
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
          (
            function_acl.grantee = function_proc.owner_oid
            OR (
              allowed_role_oid IS NOT NULL
              AND function_acl.grantee = allowed_role_oid
            )
          )
          AND function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
        )
      )
    ) THEN
      RAISE EXCEPTION '%: attributes_or_acl %', error_prefix, expected.signature;
    END IF;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF actual_sha = expected.source_sha THEN
      source_count := source_count + 1;
    ELSIF actual_sha = expected.fixed_sha THEN
      fixed_count := fixed_count + 1;
    ELSE
      RAISE EXCEPTION '061_partial_or_source_mismatch: body %',
        expected.signature;
    END IF;
  END LOOP;
  IF fixed_count = 6 THEN
    RAISE EXCEPTION '061_already_applied';
  END IF;
  IF source_count <> 6 OR fixed_count <> 0 THEN
    RAISE EXCEPTION '061_partial_or_source_mismatch';
  END IF;
END
$preflight$;


CREATE OR REPLACE FUNCTION public.n6_ai_agent_shadow_decision_record(
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  context_row public.n6_ai_context_snapshot%ROWTYPE;
  strategy_row public.n6_strategy%ROWTYPE;
  ai_status text;
  target_run_mode text;
  target_decision_type text;
  target_identity_key text;
  target_signal_id bigint;
  target_position_id bigint;
  target_idempotency_key text;
  target_run_id bigint;
  target_decision_id bigint;
  existing_decision_id bigint;
  existing_server_risk_allowed boolean;
  existing_server_risk_reason text;
  target_strategy_id bigint;
  target_risk_trigger text;
  target_risk_allowed boolean;
  target_risk_reason text;
  target_output_hash text;
  target_risk_assessment jsonb;
  portfolio_cash numeric(24,4);
  portfolio_equity numeric(24,4);
  portfolio_market_value numeric(24,4);
  portfolio_drawdown numeric(18,8);
  identity_market_value numeric(24,4);
  daily_new_buy_count integer;
  autonomous_trade_day_no integer;
  unknown_key text;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_payload IS NULL
     OR pg_catalog.jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_decision_payload'
    );
  END IF;

  SELECT key
    INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN (
    'context_snapshot_id', 'run_bucket', 'run_mode',
    'model_adapter', 'model_version', 'strategy_id',
    'strategy_version', 'strategy_hash', 'knowledge_bundle_version',
    'knowledge_bundle_hash', 'input_payload_hash',
    'decision_type', 'identity_key',
    'source_signal_projection_id', 'source_virtual_position_id',
    'confidence', 'reason_summary', 'evidence', 'counter_evidence',
    'risk_assessment', 'strategy_candidate_notes', 'idempotency_key'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR p_payload ?| ARRAY[
       'price', 'quantity', 'account', 'account_id',
       'virtual_account_id', 'trade_date', 'for_trade_date',
       'principal', 'principal_id', 'principal_type', 'user_id',
       'ai_user_id'
     ] THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'forbidden_decision_field'
    );
  END IF;

  BEGIN
    SELECT *
      INTO context_row
    FROM public.n6_ai_context_snapshot context_snapshot
    WHERE context_snapshot.ai_context_snapshot_id =
          (p_payload->>'context_snapshot_id')::bigint
      AND context_snapshot.context_status = 'frozen'
    FOR SHARE;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'invalid_context_reference'
      );
  END;
  IF NOT FOUND
     OR context_row.for_trade_date <>
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR context_row.run_bucket <> p_payload->>'run_bucket' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'stale_or_mismatched_context'
    );
  END IF;

  SELECT ai.status
    INTO ai_status
  FROM public.n6_ai_user ai
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  WHERE ai.ai_user_id = context_row.ai_user_id
    AND ai.principal_id = context_row.principal_id;
  SELECT *
    INTO strategy_row
  FROM public.n6_strategy strategy
  WHERE strategy.strategy_id = context_row.strategy_id
    AND strategy.principal_id = context_row.principal_id
    AND strategy.status = 'active';

  target_run_mode := p_payload->>'run_mode';
  BEGIN
    target_strategy_id :=
      NULLIF(p_payload->>'strategy_id', '')::bigint;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'agent_run_not_authorized'
      );
  END;
  IF ai_status NOT IN ('sandbox_only', 'active')
     OR strategy_row.strategy_id IS NULL
     OR target_run_mode NOT IN ('shadow', 'autonomous_canary')
     OR (
       target_run_mode = 'autonomous_canary'
       AND ai_status <> 'active'
     )
     OR COALESCE(p_payload->>'model_adapter', '') = ''
     OR pg_catalog.length(p_payload->>'model_adapter') > 100
     OR COALESCE(p_payload->>'model_version', '') = ''
     OR pg_catalog.length(p_payload->>'model_version') > 200
     OR target_strategy_id <> strategy_row.strategy_id
     OR p_payload->>'strategy_version' <>
          strategy_row.policy_version
     OR p_payload->>'strategy_hash' <>
          strategy_row.policy_hash
     OR p_payload->>'knowledge_bundle_version' <>
          'n6_ai_agent_knowledge_v1'
     OR p_payload->>'knowledge_bundle_hash' <>
          '062c8f65f9f666e2872c7c7311389ee112d56574631f1271735ba91cd9cfbe06'
     OR p_payload->>'input_payload_hash' <>
          context_row.decision_input_hash
     OR COALESCE(p_payload->>'idempotency_key', '') !~
          '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'agent_run_not_authorized'
    );
  END IF;

  target_decision_type := p_payload->>'decision_type';
  target_identity_key := NULLIF(p_payload->>'identity_key', '');
  BEGIN
    target_signal_id :=
      NULLIF(p_payload->>'source_signal_projection_id', '')::bigint;
    target_position_id :=
      NULLIF(p_payload->>'source_virtual_position_id', '')::bigint;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'invalid_source_reference'
      );
  END;
  IF target_decision_type NOT IN ('buy', 'sell', 'hold')
     OR COALESCE(p_payload->>'confidence', '') !~
          '^(0([.][0-9]+)?|1([.]0+)?)$'
     OR COALESCE(p_payload->>'reason_summary', '') = ''
     OR pg_catalog.length(p_payload->>'reason_summary') > 1000
     OR pg_catalog.jsonb_typeof(p_payload->'evidence') <> 'array'
     OR pg_catalog.jsonb_array_length(p_payload->'evidence') > 20
     OR (
       target_decision_type IN ('buy', 'sell')
       AND pg_catalog.jsonb_array_length(p_payload->'evidence') = 0
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
              p_payload->'evidence'
            ) item
       WHERE pg_catalog.jsonb_typeof(item) <> 'string'
          OR pg_catalog.length(item #>> '{}') > 500
     )
     OR pg_catalog.jsonb_typeof(p_payload->'counter_evidence') <> 'array'
     OR pg_catalog.jsonb_array_length(p_payload->'counter_evidence') > 20
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
              p_payload->'counter_evidence'
            ) item
       WHERE pg_catalog.jsonb_typeof(item) <> 'string'
          OR pg_catalog.length(item #>> '{}') > 500
     )
     OR pg_catalog.jsonb_typeof(p_payload->'risk_assessment') <>
          'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'decision_contract_failed'
    );
  END IF;

  IF EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_object_keys(
              p_payload->'risk_assessment'
            ) key
       WHERE key NOT IN ('trigger', 'level', 'summary')
     )
     OR COALESCE(p_payload->'risk_assessment'->>'trigger', '') = ''
     OR COALESCE(p_payload->'risk_assessment'->>'level', '') = ''
     OR COALESCE(p_payload->'risk_assessment'->>'summary', '') = ''
     OR pg_catalog.length(
          p_payload->'risk_assessment'->>'trigger'
        ) > 50
     OR pg_catalog.length(
          p_payload->'risk_assessment'->>'level'
        ) > 50
     OR pg_catalog.length(
          p_payload->'risk_assessment'->>'summary'
        ) > 500 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_risk_assessment'
    );
  END IF;
  target_risk_trigger := p_payload->'risk_assessment'->>'trigger';
  IF target_risk_trigger NOT IN (
       'signal', 'portfolio_risk', 'stop_loss', 'none'
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_risk_assessment'
    );
  END IF;

  IF target_decision_type = 'hold' THEN
    IF target_identity_key IS NOT NULL
       OR target_signal_id IS NOT NULL
       OR target_position_id IS NOT NULL
       OR target_risk_trigger <> 'none' THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'hold_scope_rejected'
      );
    END IF;
  ELSIF target_decision_type = 'buy' THEN
    IF target_identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
       OR target_signal_id IS NULL
       OR target_position_id IS NOT NULL
       OR target_risk_trigger <> 'signal'
       OR NOT EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements(
                context_row.context_payload_json->'signals'
              ) signal
         WHERE (signal->>'user_signal_projection_id')::bigint =
               target_signal_id
           AND signal->>'identity_key' = target_identity_key
           AND signal->>'direction' = 'buy'
           AND signal->>'ai_eligible' = 'true'
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'buy_signal_not_in_context'
      );
    END IF;
  ELSE
    IF target_identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
       OR target_position_id IS NULL
       OR NOT EXISTS (
         SELECT 1
         FROM pg_catalog.jsonb_array_elements(
                context_row.context_payload_json->'positions'
              ) position
         WHERE (position->>'virtual_position_id')::bigint =
               target_position_id
           AND position->>'identity_key' = target_identity_key
           AND position->>'position_status' = 'open_virtual'
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'sell_position_not_in_context'
      );
    END IF;
    IF target_risk_trigger = 'signal' THEN
      IF target_signal_id IS NULL
         OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(
                  context_row.context_payload_json->'signals'
                ) signal
           WHERE (signal->>'user_signal_projection_id')::bigint =
                 target_signal_id
             AND signal->>'identity_key' = target_identity_key
             AND signal->>'direction' = 'sell'
             AND signal->>'ai_eligible' = 'true'
         ) THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'sell_signal_not_in_context'
        );
      END IF;
    ELSIF target_risk_trigger IN ('portfolio_risk', 'stop_loss') THEN
      IF target_signal_id IS NOT NULL THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'risk_sell_claimed_signal'
        );
      END IF;
    ELSE
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'sell_reason_rejected'
      );
    END IF;
  END IF;

  IF target_signal_id IS NOT NULL
     AND NOT (
       p_payload->'evidence' ?
       ('projection:' || target_signal_id::text)
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'signal_evidence_reference_required'
    );
  END IF;
  IF target_position_id IS NOT NULL
     AND NOT (
       p_payload->'evidence' ?
       ('position:' || target_position_id::text)
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'position_evidence_reference_required'
    );
  END IF;

  IF target_decision_type = 'hold' THEN
    target_risk_allowed := true;
    target_risk_reason := 'hold_no_trade';
  ELSIF target_decision_type = 'sell' THEN
    target_risk_allowed := true;
    target_risk_reason := 'risk_reducing_sell';
  ELSE
    BEGIN
      portfolio_cash :=
        (context_row.context_payload_json
           ->'portfolio'->>'cash_balance')::numeric;
      portfolio_equity :=
        (context_row.context_payload_json
           ->'portfolio'->>'total_equity')::numeric;
      portfolio_market_value :=
        (context_row.context_payload_json
           ->'portfolio'->>'market_value')::numeric;
      portfolio_drawdown :=
        (context_row.context_payload_json
           ->'portfolio'->>'max_drawdown_pct')::numeric;
      daily_new_buy_count :=
        (context_row.context_payload_json
           ->'portfolio'->>'daily_new_buy_count')::integer;
      autonomous_trade_day_no :=
        (context_row.context_payload_json
           ->'portfolio'->>'autonomous_trade_day_no')::integer;
      SELECT COALESCE(
               pg_catalog.sum(
                 (position->>'market_value')::numeric
               ),
               0
             )
        INTO identity_market_value
      FROM pg_catalog.jsonb_array_elements(
             context_row.context_payload_json->'positions'
           ) position
      WHERE position->>'identity_key' = target_identity_key;
    EXCEPTION
      WHEN OTHERS THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'server_risk_context_invalid'
        );
    END;
    IF portfolio_drawdown >= 5 THEN
      target_risk_allowed := false;
      target_risk_reason := 'max_drawdown_pause';
    ELSIF daily_new_buy_count >=
          (CASE WHEN autonomous_trade_day_no < 3 THEN 1 ELSE 10 END) THEN
      target_risk_allowed := false;
      target_risk_reason := 'daily_buy_limit';
    ELSIF identity_market_value + 300000 > 600000 THEN
      target_risk_allowed := false;
      target_risk_reason := 'identity_exposure_limit';
    ELSIF portfolio_equity <= 0
          OR portfolio_market_value + 300000 >
               portfolio_equity * 0.10 THEN
      target_risk_allowed := false;
      target_risk_reason := 'total_exposure_limit';
    ELSIF portfolio_cash < 300000 THEN
      target_risk_allowed := false;
      target_risk_reason := 'cash_not_ready';
    ELSE
      target_risk_allowed := true;
      target_risk_reason := 'passed';
    END IF;
  END IF;
  target_risk_assessment :=
    p_payload->'risk_assessment' ||
    pg_catalog.jsonb_build_object(
      'server_policy', pg_catalog.jsonb_build_object(
        'policy_version', 'n6_ai_agent_conservative_risk_v1',
        'allowed', target_risk_allowed,
        'reason', target_risk_reason,
        'buy_budget_cny', 300000,
        'max_identity_exposure_cny', 600000,
        'max_total_exposure_ratio', 0.10,
        'max_daily_new_buys', 10,
        'pause_drawdown_pct', 5,
        'computed_by', 'n6_ai_agent_shadow_decision_record'
      )
    );
  target_output_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'decision_type', target_decision_type,
          'identity_key', target_identity_key,
          'source_signal_projection_id', target_signal_id,
          'source_virtual_position_id', target_position_id,
          'confidence', p_payload->>'confidence',
          'reason_summary', p_payload->>'reason_summary',
          'evidence', p_payload->'evidence',
          'counter_evidence', p_payload->'counter_evidence',
          'risk_assessment', p_payload->'risk_assessment',
          'strategy_candidate_notes',
            NULLIF(p_payload->>'strategy_candidate_notes', '')
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );

  target_idempotency_key := p_payload->>'idempotency_key';
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(target_idempotency_key, 0)
  );
  SELECT decision.ai_decision_id,
         decision.server_risk_allowed,
         decision.server_risk_reason
    INTO existing_decision_id, existing_server_risk_allowed,
         existing_server_risk_reason
  FROM public.n6_ai_decision decision
  WHERE decision.idempotency_key = target_idempotency_key;
  IF existing_decision_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'already_recorded',
      'decision_id', existing_decision_id,
      'server_risk_allowed', existing_server_risk_allowed,
      'server_risk_reason', existing_server_risk_reason
    );
  END IF;

  INSERT INTO public.n6_ai_decision_run (
    ai_user_id, principal_id, principal_type, strategy_id,
    ai_context_snapshot_id, run_bucket, run_mode, model_adapter,
    model_version, strategy_version, knowledge_bundle_version,
    knowledge_bundle_hash, input_payload_hash, output_payload_hash,
    run_status, finished_at
  )
  VALUES (
    context_row.ai_user_id, context_row.principal_id, 'ai_user',
    context_row.strategy_id, context_row.ai_context_snapshot_id,
    context_row.run_bucket, target_run_mode,
    p_payload->>'model_adapter', p_payload->>'model_version',
    p_payload->>'strategy_version',
    p_payload->>'knowledge_bundle_version',
    p_payload->>'knowledge_bundle_hash',
    context_row.decision_input_hash,
    target_output_hash,
    'recorded', pg_catalog.clock_timestamp()
  )
  RETURNING ai_decision_run_id INTO target_run_id;

  INSERT INTO public.n6_ai_decision (
    ai_decision_run_id, ai_user_id, principal_id, principal_type,
    decision_type, identity_key, source_signal_projection_id,
    source_virtual_position_id, confidence, reason_summary,
    evidence_json, counter_evidence_json, risk_assessment_json,
    server_risk_allowed, server_risk_reason,
    server_risk_policy_version, strategy_candidate_notes,
    decision_status, idempotency_key
  )
  VALUES (
    target_run_id, context_row.ai_user_id, context_row.principal_id,
    'ai_user', target_decision_type, target_identity_key,
    target_signal_id, target_position_id,
    (p_payload->>'confidence')::numeric,
    p_payload->>'reason_summary', p_payload->'evidence',
    p_payload->'counter_evidence', target_risk_assessment,
    target_risk_allowed, target_risk_reason,
    'n6_ai_agent_conservative_risk_v1',
    NULLIF(p_payload->>'strategy_candidate_notes', ''),
    CASE
      WHEN target_decision_type = 'hold' THEN 'held'
      WHEN target_risk_allowed THEN 'shadow_recorded'
      ELSE 'rejected'
    END,
    target_idempotency_key
  )
  RETURNING ai_decision_id INTO target_decision_id;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'decision_recorded',
    'decision_id', target_decision_id,
    'server_risk_allowed', target_risk_allowed,
    'server_risk_reason', target_risk_reason
  );
END;
$function$;
CREATE OR REPLACE FUNCTION public.n6_ai_agent_daily_summary_record(
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  context_row record;
  account_row public.n6_virtual_account%ROWTYPE;
  cash_row public.n6_virtual_cash_snapshot%ROWTYPE;
  existing_summary_id bigint;
  unknown_key text;
  target_trade_date date;
  position_market_value numeric(24,4);
  invalid_position_quote_count integer;
  total_asset numeric(24,4);
  previous_total_asset numeric(24,4);
  daily_net_pnl numeric(24,4);
  peak_asset numeric(24,4);
  current_drawdown numeric(18,8);
  prior_drawdown numeric(18,8);
  max_drawdown numeric(18,8);
  net_return numeric(18,8);
  turnover numeric(18,8);
  score numeric(18,8);
  decision_count integer;
  buy_trade_count integer;
  sell_trade_count integer;
  payload_net_return numeric;
  payload_drawdown numeric;
  payload_turnover numeric;
  payload_score numeric;
  snapshot_hash text;
  created_summary_id bigint;
  current_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
  current_time time :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_payload IS NULL
     OR pg_catalog.jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_daily_summary_request'
    );
  END IF;
  SELECT key
    INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN (
    'context_snapshot_id', 'for_trade_date', 'strategy_id',
    'strategy_version', 'strategy_hash', 'knowledge_bundle_version',
    'knowledge_bundle_hash', 'net_return_pct', 'max_drawdown_pct',
    'turnover_pct', 'risk_adjusted_score', 'decision_count',
    'buy_trade_count', 'sell_trade_count', 'summary_text',
    'highlights', 'lessons', 'next_day_watch', 'idempotency_key'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR p_payload ?| ARRAY[
       'price', 'quantity', 'account', 'account_id', 'principal',
       'principal_id', 'user_id', 'prompt', 'reasoning'
     ]
     OR COALESCE(p_payload->>'idempotency_key', '') !~
          '^[0-9a-f]{64}$'
     OR pg_catalog.jsonb_typeof(p_payload->'highlights') <> 'array'
     OR pg_catalog.jsonb_typeof(p_payload->'lessons') <> 'array'
     OR pg_catalog.jsonb_typeof(p_payload->'next_day_watch') <> 'array'
     OR pg_catalog.jsonb_array_length(p_payload->'highlights') > 20
     OR pg_catalog.jsonb_array_length(p_payload->'lessons') > 20
     OR pg_catalog.jsonb_array_length(p_payload->'next_day_watch') > 20
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
              p_payload->'highlights'
            ) item
       WHERE pg_catalog.jsonb_typeof(item) <> 'string'
          OR pg_catalog.length(item #>> '{}') > 300
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
              p_payload->'lessons'
            ) item
       WHERE pg_catalog.jsonb_typeof(item) <> 'string'
          OR pg_catalog.length(item #>> '{}') > 300
     )
     OR EXISTS (
       SELECT 1
       FROM pg_catalog.jsonb_array_elements(
              p_payload->'next_day_watch'
            ) item
       WHERE pg_catalog.jsonb_typeof(item) <> 'string'
          OR pg_catalog.length(item #>> '{}') > 300
     )
     OR COALESCE(p_payload->>'summary_text', '') = ''
     OR pg_catalog.length(p_payload->>'summary_text') > 2000 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_contract_rejected'
    );
  END IF;

  BEGIN
    target_trade_date := (p_payload->>'for_trade_date')::date;
    payload_net_return := (p_payload->>'net_return_pct')::numeric;
    payload_drawdown := (p_payload->>'max_drawdown_pct')::numeric;
    payload_turnover := (p_payload->>'turnover_pct')::numeric;
    payload_score := (p_payload->>'risk_adjusted_score')::numeric;
    decision_count := (p_payload->>'decision_count')::integer;
    buy_trade_count := (p_payload->>'buy_trade_count')::integer;
    sell_trade_count := (p_payload->>'sell_trade_count')::integer;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'daily_summary_value_rejected'
      );
  END;
  IF target_trade_date <> current_trade_date
     OR current_time < time '15:15:00'
     OR decision_count < 0
     OR buy_trade_count < 0
     OR sell_trade_count < 0
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date =
             pg_catalog.to_char(target_trade_date, 'YYYYMMDD')
         AND calendar.is_open = true
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_window_rejected'
    );
  END IF;

  BEGIN
    SELECT snapshot.ai_context_snapshot_id,
           snapshot.ai_user_id,
           snapshot.principal_id,
           snapshot.strategy_id,
           snapshot.virtual_account_id,
           snapshot.for_trade_date,
           snapshot.run_bucket,
           snapshot.context_status,
           ai.status AS ai_status,
           principal.principal_status,
           strategy.status AS strategy_status,
           strategy.policy_version AS strategy_version,
           strategy.policy_hash AS strategy_hash
      INTO context_row
    FROM public.n6_ai_context_snapshot snapshot
    JOIN public.n6_ai_user ai
      ON ai.ai_user_id = snapshot.ai_user_id
     AND ai.principal_id = snapshot.principal_id
    JOIN public.n6_principal principal
      ON principal.principal_id = snapshot.principal_id
     AND principal.principal_type = 'ai_user'
     AND principal.owner_user_id IS NULL
    JOIN public.n6_strategy strategy
      ON strategy.strategy_id = snapshot.strategy_id
     AND strategy.principal_id = snapshot.principal_id
    WHERE snapshot.ai_context_snapshot_id =
          (p_payload->>'context_snapshot_id')::bigint
    FOR SHARE OF snapshot;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'daily_summary_context_rejected'
      );
  END;
  IF NOT FOUND
     OR context_row.for_trade_date <> target_trade_date
     OR context_row.run_bucket <>
          'daily:' || pg_catalog.to_char(target_trade_date, 'YYYYMMDD')
     OR context_row.context_status <> 'frozen'
     OR context_row.ai_status NOT IN ('sandbox_only', 'active', 'disabled')
     OR context_row.principal_status <> 'active'
     OR context_row.strategy_status <> 'active'
     OR COALESCE(p_payload->>'strategy_id', '') <>
          context_row.strategy_id::text
     OR p_payload->>'strategy_version' <>
          context_row.strategy_version
     OR p_payload->>'strategy_hash' <>
          context_row.strategy_hash
     OR p_payload->>'knowledge_bundle_version' <>
          'n6_ai_agent_knowledge_v1'
     OR p_payload->>'knowledge_bundle_hash' <>
          '062c8f65f9f666e2872c7c7311389ee112d56574631f1271735ba91cd9cfbe06' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_authority_rejected'
    );
  END IF;

  SELECT summary.ai_daily_summary_id
    INTO existing_summary_id
  FROM public.n6_ai_daily_summary summary
  WHERE summary.ai_user_id = context_row.ai_user_id
    AND summary.for_trade_date = target_trade_date;
  IF existing_summary_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'already_recorded',
      'daily_summary_id', existing_summary_id
    );
  END IF;

  SELECT *
    INTO account_row
  FROM public.n6_virtual_account account
  WHERE account.virtual_account_id = context_row.virtual_account_id
    AND account.principal_id = context_row.principal_id
    AND account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active'
  FOR SHARE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_account_not_ready'
    );
  END IF;
  SELECT *
    INTO cash_row
  FROM public.n6_virtual_cash_snapshot cash
  WHERE cash.cash_snapshot_id = account_row.current_cash_snapshot_id
    AND cash.virtual_account_id = account_row.virtual_account_id
    AND cash.snapshot_status = 'active'
  FOR SHARE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_cash_not_ready'
    );
  END IF;

  SELECT COALESCE(
           pg_catalog.sum(
             CASE
               WHEN quote.quality_status = 'passed'
                AND quote.quality_reason = 'ok'
                AND quote.current_price > 0
                AND quote.current_price::text NOT IN (
                      'NaN', 'Infinity', '-Infinity'
                    )
                AND (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date =
                      target_trade_date
                AND (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time
                      BETWEEN time '14:55:00' AND time '15:05:00'
                AND quote.fetched_at >= quote.quote_minute
                 THEN position.quantity * quote.current_price
               ELSE NULL
             END
           ),
           0
         ),
         count(*) FILTER (
           WHERE quote.quality_status IS DISTINCT FROM 'passed'
              OR quote.quality_reason IS DISTINCT FROM 'ok'
              OR quote.current_price IS NULL
              OR quote.current_price <= 0
              OR quote.current_price::text IN (
                   'NaN', 'Infinity', '-Infinity'
                 )
              OR (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date
                   IS DISTINCT FROM target_trade_date
              OR (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time
                   NOT BETWEEN time '14:55:00' AND time '15:05:00'
              OR quote.fetched_at < quote.quote_minute
         )::integer
    INTO position_market_value, invalid_position_quote_count
  FROM public.n6_virtual_position position
  LEFT JOIN public.v_n6_virtual_quote_latest quote
    ON quote.identity_key = position.identity_key
  WHERE position.virtual_account_id = account_row.virtual_account_id
    AND position.principal_id = context_row.principal_id
    AND position.principal_type = 'ai_user'
    AND position.asset_kind = 'stock'
    AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
    AND position.position_status = 'open_virtual'
    AND position.quantity > 0;
  IF invalid_position_quote_count > 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_quote_not_ready'
    );
  END IF;
  total_asset :=
    cash_row.available_cash + cash_row.frozen_cash +
    position_market_value;
  SELECT COALESCE(
           (
             SELECT summary.total_asset
             FROM public.n6_ai_daily_summary summary
             WHERE summary.ai_user_id = context_row.ai_user_id
               AND summary.for_trade_date < target_trade_date
             ORDER BY summary.for_trade_date DESC
             LIMIT 1
           ),
           account_row.initial_cash
         )
    INTO previous_total_asset;
  daily_net_pnl := total_asset - previous_total_asset;
  SELECT GREATEST(
           account_row.initial_cash,
           COALESCE(pg_catalog.max(summary.total_asset), 0),
           total_asset
         ),
         COALESCE(pg_catalog.max(summary.max_drawdown_pct), 0)
    INTO peak_asset, prior_drawdown
  FROM public.n6_ai_daily_summary summary
  WHERE summary.ai_user_id = context_row.ai_user_id;
  current_drawdown := CASE
    WHEN peak_asset > 0
      THEN GREATEST(
        0, (peak_asset - total_asset) / peak_asset * 100
      )
    ELSE 0
  END;
  max_drawdown := GREATEST(prior_drawdown, current_drawdown);
  net_return := CASE
    WHEN account_row.initial_cash > 0
      THEN (total_asset - account_row.initial_cash) /
           account_row.initial_cash * 100
    ELSE 0
  END;
  SELECT CASE
           WHEN account_row.initial_cash > 0 THEN
             COALESCE(pg_catalog.sum(trade.gross_amount), 0) /
             account_row.initial_cash * 100
           ELSE 0
         END,
         count(*) FILTER (
           WHERE trade.trade_side = 'buy'
         )::integer,
         count(*) FILTER (
           WHERE trade.trade_side = 'sell'
         )::integer
    INTO turnover, buy_trade_count, sell_trade_count
  FROM public.n6_virtual_trade trade
  WHERE trade.virtual_account_id = account_row.virtual_account_id
    AND trade.principal_id = context_row.principal_id
    AND trade.principal_type = 'ai_user'
    AND trade.trade_status = 'filled_virtual'
    AND (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date =
          target_trade_date;
  SELECT count(*)::integer
    INTO decision_count
  FROM public.n6_ai_decision decision
  WHERE decision.ai_user_id = context_row.ai_user_id
    AND (decision.created_at AT TIME ZONE 'Asia/Shanghai')::date =
          target_trade_date;
  score := pg_catalog.round(
    net_return - 1.5 * max_drawdown - 0.02 * turnover,
    6
  );

  IF pg_catalog.round(payload_net_return, 6) <>
       pg_catalog.round(net_return, 6)
     OR pg_catalog.round(payload_drawdown, 6) <>
          pg_catalog.round(max_drawdown, 6)
     OR pg_catalog.round(payload_turnover, 6) <>
          pg_catalog.round(turnover, 6)
     OR pg_catalog.round(payload_score, 6) <> score
     OR (p_payload->>'decision_count')::integer <> decision_count
     OR (p_payload->>'buy_trade_count')::integer <> buy_trade_count
     OR (p_payload->>'sell_trade_count')::integer <> sell_trade_count THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'daily_summary_context_drift'
    );
  END IF;

  snapshot_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'virtual_account_id', account_row.virtual_account_id,
          'cash_snapshot_id', cash_row.cash_snapshot_id,
          'total_asset', total_asset,
          'market_value', position_market_value,
          'decision_count', decision_count,
          'buy_trade_count', buy_trade_count,
          'sell_trade_count', sell_trade_count
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );
  INSERT INTO public.n6_ai_daily_summary (
    ai_user_id, principal_id, principal_type, strategy_id,
    strategy_version, strategy_hash, knowledge_bundle_version,
    knowledge_bundle_hash, for_trade_date, virtual_account_id,
    total_asset, available_cash, market_value, daily_net_pnl,
    net_return_pct, max_drawdown_pct, turnover_pct,
    risk_adjusted_score, decision_count, buy_trade_count,
    sell_trade_count, trade_review_json, success_reasons_json,
    failure_reasons_json, next_day_watch_json, summary_text,
    account_snapshot_hash
  )
  VALUES (
    context_row.ai_user_id, context_row.principal_id, 'ai_user',
    context_row.strategy_id, context_row.strategy_version,
    context_row.strategy_hash, p_payload->>'knowledge_bundle_version',
    p_payload->>'knowledge_bundle_hash', target_trade_date,
    account_row.virtual_account_id, total_asset,
    cash_row.available_cash, position_market_value, daily_net_pnl,
    net_return,
    max_drawdown, turnover, score, decision_count, buy_trade_count,
    sell_trade_count, p_payload->'highlights', p_payload->'highlights',
    p_payload->'lessons', p_payload->'next_day_watch',
    p_payload->>'summary_text', snapshot_hash
  )
  RETURNING ai_daily_summary_id INTO created_summary_id;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'daily_summary_recorded',
    'daily_summary_id', created_summary_id
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.n6_ai_agent_context_load(
  p_run_bucket text,
  p_for_trade_date date,
  p_max_signals integer
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  actor record;
  actor_count integer;
  context_payload jsonb;
  context_payload_sha256 text;
  decision_input_sha256 text;
  source_run_ids jsonb;
  source_signal_ids jsonb;
  source_position_ids jsonb;
  source_cash_ids jsonb;
  created_snapshot_id bigint;
  existing_snapshot_id bigint;
  latest_decision_input_sha256 text;
  invalid_position_quote_count integer;
  current_equity numeric(24,4);
  peak_equity numeric(24,4);
  prior_drawdown numeric(18,8);
  current_drawdown numeric(18,8);
  effective_drawdown numeric(18,8);
  context_time timestamptz := pg_catalog.clock_timestamp();
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_run_bucket IS NULL
     OR p_run_bucket !~
          '^(daily:[0-9]{8}|[0-9]{8}T[0-9]{4}[+-][0-9]{4})$'
     OR p_for_trade_date IS NULL
     OR p_for_trade_date <>
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR p_max_signals IS NULL
     OR p_max_signals < 0
     OR p_max_signals > 1000 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'invalid_context_request'
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date =
          pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD')
      AND calendar.is_open = true
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'not_open_trade_date'
    );
  END IF;

  SELECT min(ai.ai_user_id) AS ai_user_id,
         min(ai.principal_id) AS principal_id,
         min(ai.status) AS ai_status,
         min(strategy.strategy_id) AS strategy_id,
         min(strategy.policy_version) AS strategy_version,
         min(strategy.policy_hash) AS strategy_hash,
         min(account.virtual_account_id) AS virtual_account_id,
         min(account.initial_cash) AS initial_cash,
         min(cash.cash_snapshot_id) AS cash_snapshot_id,
         min(cash.available_cash) AS available_cash,
         min(cash.frozen_cash) AS frozen_cash,
         count(*) AS authority_count
    INTO actor
  FROM public.n6_ai_user ai
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  JOIN public.n6_strategy strategy
    ON strategy.strategy_id = ai.strategy_profile_id
   AND strategy.principal_id = principal.principal_id
   AND strategy.status = 'active'
  JOIN public.n6_virtual_account account
    ON account.principal_id = principal.principal_id
   AND account.principal_type = 'ai_user'
   AND account.virtual_account_status = 'active'
  JOIN public.n6_virtual_cash_snapshot cash
    ON cash.cash_snapshot_id = account.current_cash_snapshot_id
   AND cash.virtual_account_id = account.virtual_account_id
   AND cash.snapshot_status = 'active'
  WHERE ai.status IN ('sandbox_only', 'active', 'disabled');
  actor_count := actor.authority_count;
  IF actor_count <> 1
     OR actor.strategy_hash !~ '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'agent_disabled'
    );
  END IF;
  IF actor.ai_status = 'disabled'
     AND p_run_bucket NOT LIKE 'daily:%' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'agent_disabled'
    );
  END IF;

  SELECT min(snapshot.ai_context_snapshot_id)
    INTO existing_snapshot_id
  FROM public.n6_ai_context_snapshot snapshot
  WHERE snapshot.ai_user_id = actor.ai_user_id
    AND snapshot.run_bucket = p_run_bucket;
  IF existing_snapshot_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'already_processed',
      'context_snapshot_id', existing_snapshot_id
    );
  END IF;

  WITH ranked_signal AS (
    SELECT shared.source_signal_projection_id,
           shared.user_projection_run_id,
           shared.source_event_id,
           shared.identity_key,
           shared.direction,
           shared.reason_fields_json,
           shared.action_state,
           shared.action_mark,
           shared.source_event_time,
           shared.created_at,
           pg_catalog.row_number() OVER (
             PARTITION BY shared.source_event_id,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_signal_projection_id
           ) AS duplicate_rank
    FROM public.n6_ai_shared_signal_projection shared
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           shared.user_projection_run_id
     AND projection_run.status IN ('passed', 'ready')
    WHERE p_max_signals > 0
      AND shared.shared_status = 'active'
      AND shared.asset_kind = 'stock'
      AND shared.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND shared.direction IN ('buy', 'sell')
      AND shared.for_trade_date = p_for_trade_date
      AND shared.action_state IN ('eligible', 'executed')
  ), ranked_market_context AS (
    SELECT shared.source_signal_projection_id,
           shared.user_projection_run_id,
           shared.source_event_id,
           shared.asset_kind,
           shared.identity_key,
           shared.direction,
           shared.reason_fields_json,
           shared.action_state,
           shared.action_mark,
           shared.source_event_time,
           shared.created_at,
           pg_catalog.row_number() OVER (
             PARTITION BY shared.source_event_id,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_signal_projection_id
           ) AS duplicate_rank
    FROM public.n6_ai_shared_signal_projection shared
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           shared.user_projection_run_id
     AND projection_run.status IN ('passed', 'ready')
    WHERE p_max_signals > 0
      AND shared.shared_status = 'active'
      AND (
        (
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
  ), selected_signal AS (
    SELECT *
    FROM ranked_signal
    WHERE duplicate_rank = 1
    ORDER BY source_signal_projection_id DESC
    LIMIT p_max_signals
  ), selected_market_context AS (
    SELECT *
    FROM ranked_market_context
    WHERE duplicate_rank = 1
    ORDER BY source_signal_projection_id DESC
    LIMIT p_max_signals
  ), signal_payload AS (
    SELECT COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.jsonb_build_object(
                 'user_signal_projection_id',
                   signal.source_signal_projection_id,
                 'asset_kind', 'stock',
                 'identity_key', signal.identity_key,
                 'direction', signal.direction,
                 'for_trade_date',
                   pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD'),
                 'event_time', signal.source_event_time,
                 'action_state', signal.action_state,
                 'ai_eligible', true,
                 'reason_fields', signal.reason_fields_json
               )
               ORDER BY signal.source_signal_projection_id DESC
             ),
             '[]'::jsonb
           ) AS rows,
           COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(signal.source_signal_projection_id)
               ORDER BY signal.source_signal_projection_id
             ),
             '[]'::jsonb
           ) AS signal_ids,
           COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(signal.user_projection_run_id)
               ORDER BY signal.user_projection_run_id
             ),
             '[]'::jsonb
           ) AS run_ids
    FROM selected_signal signal
  ), market_context_payload AS (
    SELECT COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.jsonb_build_object(
                 'user_signal_projection_id',
                   signal.source_signal_projection_id,
                 'asset_kind', signal.asset_kind,
                 'identity_key', signal.identity_key,
                 'direction', signal.direction,
                 'for_trade_date',
                   pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD'),
                 'context_only', true,
                 'event_time', signal.source_event_time,
                 'action_state', signal.action_state,
                 'reason_fields', signal.reason_fields_json
               )
               ORDER BY signal.source_signal_projection_id DESC
             ),
             '[]'::jsonb
           ) AS rows,
           COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(signal.source_signal_projection_id)
               ORDER BY signal.source_signal_projection_id
             ),
             '[]'::jsonb
           ) AS signal_ids,
           COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(signal.user_projection_run_id)
               ORDER BY signal.user_projection_run_id
             ),
             '[]'::jsonb
           ) AS run_ids
    FROM selected_market_context signal
  ), position_payload AS (
    SELECT COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.jsonb_build_object(
                 'virtual_position_id', position.virtual_position_id,
                 'asset_kind', 'stock',
                 'identity_key', position.identity_key,
                 'position_status', 'open_virtual',
                 'quantity', position.quantity,
                 'available_quantity', position.available_quantity,
                 'current_price', quote.current_price,
                 'quote_minute', quote.quote_minute,
                 'quote_quality_status', quote.quality_status,
                 'market_value',
                   CASE
                     WHEN quote.quality_status = 'passed'
                      AND quote.quality_reason = 'ok'
                      AND quote.current_price > 0
                      AND quote.current_price::text NOT IN (
                            'NaN', 'Infinity', '-Infinity'
                          )
                      AND quote.quote_minute <= context_time
                      AND quote.quote_minute >=
                            context_time - interval '120 seconds'
                      AND quote.fetched_at >= quote.quote_minute
                      AND quote.fetched_at >=
                            context_time - interval '120 seconds'
                       THEN position.quantity * quote.current_price
                     ELSE NULL
                   END,
                 'stop_loss_status', position.stop_loss_status
               )
               ORDER BY position.identity_key
             ),
             '[]'::jsonb
           ) AS rows,
           COALESCE(
             pg_catalog.jsonb_agg(
               pg_catalog.to_jsonb(position.virtual_position_id)
               ORDER BY position.virtual_position_id
             ),
             '[]'::jsonb
           ) AS ids,
           COALESCE(
             pg_catalog.sum(
               CASE
                 WHEN quote.quality_status = 'passed'
                  AND quote.quality_reason = 'ok'
                  AND quote.current_price > 0
                  AND quote.current_price::text NOT IN (
                        'NaN', 'Infinity', '-Infinity'
                      )
                  AND quote.quote_minute <= context_time
                  AND quote.quote_minute >=
                        context_time - interval '120 seconds'
                  AND quote.fetched_at >= quote.quote_minute
                  AND quote.fetched_at >=
                        context_time - interval '120 seconds'
                   THEN position.quantity * quote.current_price
                 ELSE NULL
               END
             ),
             0
           ) AS market_value,
           count(*) FILTER (
             WHERE quote.quality_status IS DISTINCT FROM 'passed'
                OR quote.quality_reason IS DISTINCT FROM 'ok'
                OR quote.current_price IS NULL
                OR quote.current_price <= 0
                OR quote.current_price::text IN (
                     'NaN', 'Infinity', '-Infinity'
                   )
                OR quote.quote_minute > context_time
                OR quote.quote_minute <
                     context_time - interval '120 seconds'
                OR quote.fetched_at < quote.quote_minute
                OR quote.fetched_at <
                     context_time - interval '120 seconds'
           )::integer AS invalid_quote_count
    FROM public.n6_virtual_position position
    LEFT JOIN public.v_n6_virtual_quote_latest quote
      ON quote.identity_key = position.identity_key
    WHERE position.virtual_account_id = actor.virtual_account_id
      AND position.principal_id = actor.principal_id
      AND position.principal_type = 'ai_user'
      AND position.asset_kind = 'stock'
      AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
  ), trade_metrics AS (
    SELECT count(*) FILTER (
             WHERE trade.trade_side = 'buy'
               AND (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date =
                     p_for_trade_date
           )::integer AS buy_count,
           count(*) FILTER (
             WHERE trade.trade_side = 'sell'
               AND (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date =
                     p_for_trade_date
           )::integer AS sell_count,
           COALESCE(
             pg_catalog.sum(trade.gross_amount) FILTER (
               WHERE (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date =
                     p_for_trade_date
             ),
             0
           ) AS turnover_amount,
           count(DISTINCT
                 (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date
           ) FILTER (
             WHERE trade.trade_side = 'buy'
           )::integer AS autonomous_trade_days
    FROM public.n6_virtual_trade trade
    WHERE trade.virtual_account_id = actor.virtual_account_id
      AND trade.principal_id = actor.principal_id
      AND trade.principal_type = 'ai_user'
      AND trade.trade_status = 'filled_virtual'
  ), decision_metrics AS (
    SELECT count(*)::integer AS decision_count
    FROM public.n6_ai_decision decision
    WHERE decision.ai_user_id = actor.ai_user_id
      AND (decision.created_at AT TIME ZONE 'Asia/Shanghai')::date =
            p_for_trade_date
  ), latest_summary AS (
    SELECT COALESCE(summary.max_drawdown_pct, 0) AS max_drawdown_pct
    FROM public.n6_ai_daily_summary summary
    WHERE summary.ai_user_id = actor.ai_user_id
    ORDER BY summary.for_trade_date DESC
    LIMIT 1
  )
  SELECT pg_catalog.jsonb_build_object(
           'contract_version', 'n6_ai_agent_v1',
           'for_trade_date',
             pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD'),
           'signals', signal_payload.rows,
           'market_context', market_context_payload.rows,
           'positions', position_payload.rows,
           'portfolio', pg_catalog.jsonb_build_object(
             'cash_balance', actor.available_cash,
             'total_equity',
               actor.available_cash + actor.frozen_cash +
               position_payload.market_value,
             'market_value', position_payload.market_value,
             'max_drawdown_pct',
               COALESCE(
                 (SELECT max_drawdown_pct FROM latest_summary),
                 0
               ),
             'daily_new_buy_count', trade_metrics.buy_count,
             'autonomous_trade_day_no',
               trade_metrics.autonomous_trade_days
           ),
           'strategy', pg_catalog.jsonb_build_object(
             'strategy_id', actor.strategy_id,
             'strategy_version', actor.strategy_version,
             'strategy_hash', actor.strategy_hash
           ),
           'daily_metrics', pg_catalog.jsonb_build_object(
             'net_return_pct',
               CASE
                 WHEN actor.initial_cash > 0 THEN
                   (
                     actor.available_cash + actor.frozen_cash +
                     position_payload.market_value - actor.initial_cash
                   ) / actor.initial_cash * 100
                 ELSE 0
               END,
             'max_drawdown_pct',
               COALESCE(
                 (SELECT max_drawdown_pct FROM latest_summary),
                 0
               ),
             'turnover_pct',
               CASE
                 WHEN actor.initial_cash > 0 THEN
                   trade_metrics.turnover_amount /
                   actor.initial_cash * 100
                 ELSE 0
               END,
             'decision_count', decision_metrics.decision_count,
             'buy_trade_count', trade_metrics.buy_count,
             'sell_trade_count', trade_metrics.sell_count,
             'highlights',
               CASE
                 WHEN decision_metrics.decision_count > 0
                   OR trade_metrics.buy_count + trade_metrics.sell_count > 0
                   THEN pg_catalog.jsonb_build_array(
                     '当日决策与模拟成交均已纳入不可变审计链。'
                   )
                 ELSE pg_catalog.jsonb_build_array()
               END,
             'lessons', pg_catalog.jsonb_build_array(
               '继续以报价质量、T+1与组合风险门槛作为成交前置条件。'
             ),
             'next_day_watch',
               COALESCE(
                 (
                   SELECT pg_catalog.jsonb_agg(
                            '继续关注持仓 ' ||
                            watch.identity_key ||
                            ' 的报价质量与止损状态。'
                            ORDER BY watch.identity_key
                          )
                   FROM (
                     SELECT position->>'identity_key' AS identity_key
                     FROM pg_catalog.jsonb_array_elements(
                            position_payload.rows
                          ) position
                     ORDER BY position->>'identity_key'
                     LIMIT 20
                   ) watch
                 ),
                 pg_catalog.jsonb_build_array(
                   '等待下一交易日新的共享N6买入信号。'
                 )
               )
           )
         ),
         signal_payload.run_ids || market_context_payload.run_ids,
         signal_payload.signal_ids || market_context_payload.signal_ids,
         position_payload.ids,
         position_payload.invalid_quote_count
    INTO context_payload, source_run_ids, source_signal_ids,
         source_position_ids, invalid_position_quote_count
  FROM signal_payload, market_context_payload, position_payload,
       trade_metrics, decision_metrics;

  IF invalid_position_quote_count > 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'position_quote_not_ready'
    );
  END IF;

  current_equity :=
    (context_payload->'portfolio'->>'total_equity')::numeric;
  SELECT GREATEST(
           actor.initial_cash,
           COALESCE(pg_catalog.max(summary.total_asset), 0),
           current_equity
         ),
         COALESCE(pg_catalog.max(summary.max_drawdown_pct), 0)
    INTO peak_equity, prior_drawdown
  FROM public.n6_ai_daily_summary summary
  WHERE summary.ai_user_id = actor.ai_user_id;
  current_drawdown := CASE
    WHEN peak_equity > 0
      THEN GREATEST(
        0, (peak_equity - current_equity) / peak_equity * 100
      )
    ELSE 0
  END;
  effective_drawdown :=
    GREATEST(prior_drawdown, current_drawdown);
  context_payload := pg_catalog.jsonb_set(
    pg_catalog.jsonb_set(
      context_payload,
      ARRAY['portfolio', 'max_drawdown_pct'],
      pg_catalog.to_jsonb(effective_drawdown),
      false
    ),
    ARRAY['daily_metrics', 'max_drawdown_pct'],
    pg_catalog.to_jsonb(effective_drawdown),
    false
  );
  IF effective_drawdown >= 5
     AND p_run_bucket NOT LIKE 'daily:%' THEN
    UPDATE public.n6_ai_user ai
    SET status = 'disabled',
        updated_at = pg_catalog.now()
    WHERE ai.ai_user_id = actor.ai_user_id
      AND ai.principal_id = actor.principal_id
      AND ai.status IN ('sandbox_only', 'active');
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'agent_drawdown_paused',
      'pause_reason', 'max_drawdown_pause'
    );
  END IF;

  source_cash_ids :=
    pg_catalog.jsonb_build_array(actor.cash_snapshot_id);
  context_payload_sha256 := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(context_payload::text, 'UTF8')
    ),
    'hex'
  );
  decision_input_sha256 := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        (context_payload - 'daily_metrics')::text,
        'UTF8'
      )
    ),
    'hex'
  );

  SELECT snapshot.decision_input_hash
    INTO latest_decision_input_sha256
  FROM public.n6_ai_context_snapshot snapshot
  WHERE snapshot.ai_user_id = actor.ai_user_id
    AND snapshot.for_trade_date = p_for_trade_date
  ORDER BY snapshot.ai_context_snapshot_id DESC
  LIMIT 1;
  IF p_run_bucket NOT LIKE 'daily:%'
     AND latest_decision_input_sha256 = decision_input_sha256 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'no_new_input'
    );
  END IF;

  INSERT INTO public.n6_ai_context_snapshot (
    ai_user_id, principal_id, principal_type, strategy_id,
    virtual_account_id, for_trade_date, run_bucket,
    source_projection_run_ids_json, source_signal_projection_ids_json,
    source_virtual_position_ids_json, source_account_snapshot_ids_json,
    context_payload_json, context_payload_hash, decision_input_hash,
    context_hash_algorithm
  )
  VALUES (
    actor.ai_user_id, actor.principal_id, 'ai_user', actor.strategy_id,
    actor.virtual_account_id, p_for_trade_date, p_run_bucket,
    source_run_ids, source_signal_ids, source_position_ids,
    source_cash_ids, context_payload, context_payload_sha256,
    decision_input_sha256, 'sha256'
  )
  RETURNING ai_context_snapshot_id INTO created_snapshot_id;

  RETURN context_payload || pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'ready',
    'context_snapshot_id', created_snapshot_id,
    'decision_input_hash', decision_input_sha256
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.n6_ai_agent_proposal_create_confirm(
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  source record;
  account_row public.n6_virtual_account%ROWTYPE;
  cash_row public.n6_virtual_cash_snapshot%ROWTYPE;
  target_position_id bigint;
  target_episode_no integer;
  target_source_type text;
  target_source_id text;
  target_reference_kind text;
  target_reference_price numeric(24,8);
  target_price numeric(24,8);
  target_proposal_id bigint;
  existing_confirm_key text;
  account_count integer;
  daily_buy_count integer;
  autonomous_trade_days integer;
  position_market_value numeric(24,4);
  identity_market_value numeric(24,4);
  outstanding_buy_reservation numeric(24,4);
  outstanding_identity_reservation numeric(24,4);
  invalid_position_quote_count integer;
  current_equity numeric(24,4);
  peak_equity numeric(24,4);
  current_drawdown numeric(18,8);
  latest_drawdown numeric(18,8);
  valuation_time timestamptz := pg_catalog.clock_timestamp();
  current_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
  current_time time :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time;
  unknown_key text;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_payload IS NULL
     OR pg_catalog.jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_proposal_request'
    );
  END IF;
  SELECT key
    INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN ('decision_id', 'idempotency_key')
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR COALESCE(p_payload->>'idempotency_key', '') !~
          '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'forbidden_proposal_field'
    );
  END IF;

  BEGIN
    SELECT decision.ai_decision_id, decision.ai_user_id,
           decision.principal_id, decision.decision_type,
           decision.identity_key,
           decision.source_signal_projection_id,
           decision.source_virtual_position_id,
           decision.decision_status,
           decision.server_risk_allowed,
           decision.server_risk_reason,
           decision.risk_assessment_json,
           decision.proposal_id,
           decision_run.run_mode,
           context_snapshot.for_trade_date,
           ai.status AS ai_status,
           strategy.strategy_id,
           strategy.status AS strategy_status,
           principal.principal_status
      INTO source
    FROM public.n6_ai_decision decision
    JOIN public.n6_ai_decision_run decision_run
      ON decision_run.ai_decision_run_id =
           decision.ai_decision_run_id
    JOIN public.n6_ai_context_snapshot context_snapshot
      ON context_snapshot.ai_context_snapshot_id =
           decision_run.ai_context_snapshot_id
    JOIN public.n6_ai_user ai
      ON ai.ai_user_id = decision.ai_user_id
     AND ai.principal_id = decision.principal_id
    JOIN public.n6_principal principal
      ON principal.principal_id = decision.principal_id
     AND principal.principal_type = 'ai_user'
     AND principal.owner_user_id IS NULL
    JOIN public.n6_strategy strategy
      ON strategy.strategy_id = decision_run.strategy_id
     AND strategy.principal_id = decision.principal_id
    WHERE decision.ai_decision_id =
          (p_payload->>'decision_id')::bigint
    FOR UPDATE OF decision;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'invalid_decision_reference'
      );
  END;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'decision_not_found'
    );
  END IF;

  IF source.proposal_id IS NOT NULL THEN
    SELECT proposal.confirm_idempotency_key
      INTO existing_confirm_key
    FROM public.n6_virtual_trade_proposal proposal
    WHERE proposal.proposal_id = source.proposal_id
      AND proposal.source_ai_decision_id = source.ai_decision_id;
    IF existing_confirm_key = p_payload->>'idempotency_key' THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', true,
        'status', 'already_confirmed',
        'proposal_id', source.proposal_id
      );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'decision_already_used'
    );
  END IF;

  IF source.run_mode <> 'autonomous_canary'
     OR source.ai_status <> 'active'
     OR source.principal_status <> 'active'
     OR source.strategy_status <> 'active'
     OR source.decision_status <> 'shadow_recorded'
     OR source.server_risk_allowed IS DISTINCT FROM true
     OR source.decision_type NOT IN ('buy', 'sell')
     OR source.for_trade_date <> current_trade_date
  THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'decision_not_autonomous_eligible'
    );
  END IF;
  IF NOT (
       current_time BETWEEN time '09:30:00' AND time '11:30:00'
       OR current_time BETWEEN time '13:00:00' AND time '15:00:00'
     )
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date =
             pg_catalog.to_char(current_trade_date, 'YYYYMMDD')
         AND calendar.is_open = true
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'outside_trading_session'
    );
  END IF;

  SELECT count(*)
    INTO account_count
  FROM public.n6_virtual_account account
  WHERE account.principal_id = source.principal_id
    AND account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active';
  IF account_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_account_authority_conflict'
    );
  END IF;
  SELECT *
    INTO account_row
  FROM public.n6_virtual_account account
  WHERE account.principal_id = source.principal_id
    AND account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active'
  FOR UPDATE;
  SELECT *
    INTO cash_row
  FROM public.n6_virtual_cash_snapshot cash
  WHERE cash.cash_snapshot_id = account_row.current_cash_snapshot_id
    AND cash.virtual_account_id = account_row.virtual_account_id
    AND cash.snapshot_status = 'active'
  FOR SHARE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'cash_not_ready'
    );
  END IF;

  IF source.decision_type = 'buy' THEN
    SELECT CASE
             WHEN projection.action_state = 'executed'
               THEN 'action_price'
             ELSE 'trigger_price'
           END,
           CASE
             WHEN projection.action_state = 'executed'
               THEN projection.action_price
             WHEN projection.action_state = 'eligible'
               THEN projection.trigger_price
             ELSE NULL
           END,
           projection.target_price
      INTO target_reference_kind, target_reference_price, target_price
    FROM public.n6_ai_shared_signal_projection projection
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           projection.user_projection_run_id
     AND projection_run.status IN ('passed', 'ready')
    WHERE projection.source_signal_projection_id =
          source.source_signal_projection_id
      AND projection.asset_kind = 'stock'
      AND projection.identity_key = source.identity_key
      AND projection.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND projection.direction = 'buy'
      AND projection.shared_status = 'active'
      AND projection.for_trade_date = current_trade_date
      AND projection.action_state IN ('eligible', 'executed');
    IF NOT FOUND
       OR target_reference_price IS NULL
       OR target_reference_price <= 0
       OR target_price IS NULL
       OR target_price <= 0 THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'current_buy_signal_not_ready'
      );
    END IF;
    target_source_type := 'signal';
    target_source_id := source.source_signal_projection_id::text;
  ELSE
    SELECT position.virtual_position_id,
           position.holding_episode_no
      INTO target_position_id, target_episode_no
    FROM public.n6_virtual_position position
    WHERE position.virtual_account_id =
          account_row.virtual_account_id
      AND position.principal_id = source.principal_id
      AND position.principal_type = 'ai_user'
      AND position.asset_kind = 'stock'
      AND position.identity_key = source.identity_key
      AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
      AND position.available_quantity > 0
      AND position.virtual_position_id =
          source.source_virtual_position_id
    FOR SHARE;
    IF NOT FOUND THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'sellable_ai_position_required'
      );
    END IF;
    IF source.source_signal_projection_id IS NOT NULL THEN
      SELECT CASE
               WHEN projection.action_state = 'executed'
                 THEN 'action_price'
               ELSE 'trigger_price'
             END,
             CASE
               WHEN projection.action_state = 'executed'
                 THEN projection.action_price
               WHEN projection.action_state = 'eligible'
                 THEN projection.trigger_price
               ELSE NULL
             END
        INTO target_reference_kind, target_reference_price
      FROM public.n6_ai_shared_signal_projection projection
      JOIN public.user_projection_run projection_run
        ON projection_run.user_projection_run_id =
             projection.user_projection_run_id
       AND projection_run.status IN ('passed', 'ready')
      WHERE projection.source_signal_projection_id =
            source.source_signal_projection_id
        AND projection.asset_kind = 'stock'
        AND projection.identity_key = source.identity_key
        AND projection.direction = 'sell'
        AND projection.shared_status = 'active'
        AND projection.for_trade_date = current_trade_date
        AND projection.action_state IN ('eligible', 'executed');
      IF NOT FOUND OR target_reference_price IS NULL THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'current_sell_signal_not_ready'
        );
      END IF;
      target_source_type := 'signal';
      target_source_id := source.source_signal_projection_id::text;
    ELSIF source.risk_assessment_json->>'trigger'
          IN ('portfolio_risk', 'stop_loss') THEN
      target_source_type := 'ai_risk';
      target_source_id := source.ai_decision_id::text;
      target_reference_kind := CASE
        WHEN source.risk_assessment_json->>'trigger' = 'stop_loss'
          THEN 'stop_loss'
        ELSE 'manual'
      END;
      target_reference_price := NULL;
    ELSE
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'sell_reason_rejected'
      );
    END IF;
  END IF;

  SELECT count(DISTINCT
               (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date)
    INTO autonomous_trade_days
  FROM public.n6_virtual_trade trade
  WHERE trade.virtual_account_id = account_row.virtual_account_id
    AND trade.principal_id = source.principal_id
    AND trade.principal_type = 'ai_user'
    AND trade.trade_side = 'buy'
    AND trade.trade_status = 'filled_virtual';
  SELECT count(*)
    INTO daily_buy_count
  FROM public.n6_virtual_trade_proposal proposal
  WHERE proposal.virtual_account_id = account_row.virtual_account_id
    AND proposal.principal_id = source.principal_id
    AND proposal.principal_type = 'ai_user'
    AND proposal.proposal_side = 'buy'
    AND (proposal.created_at AT TIME ZONE 'Asia/Shanghai')::date =
          current_trade_date
    AND proposal.proposal_status IN (
      'confirmed', 'processing', 'executed'
    );
  SELECT COALESCE(
           pg_catalog.sum(
             CASE
               WHEN quote.quality_status = 'passed'
                AND quote.quality_reason = 'ok'
                AND quote.current_price > 0
                AND quote.current_price::text NOT IN (
                      'NaN', 'Infinity', '-Infinity'
                    )
                AND quote.quote_minute <= valuation_time
                AND quote.quote_minute >=
                      valuation_time - interval '120 seconds'
                AND quote.fetched_at >= quote.quote_minute
                AND quote.fetched_at >=
                      valuation_time - interval '120 seconds'
                 THEN position.quantity * quote.current_price
               ELSE NULL
             END
           ),
           0
         ),
         COALESCE(
           pg_catalog.sum(
             CASE
               WHEN quote.quality_status = 'passed'
                AND quote.quality_reason = 'ok'
                AND quote.current_price > 0
                AND quote.current_price::text NOT IN (
                      'NaN', 'Infinity', '-Infinity'
                    )
                AND quote.quote_minute <= valuation_time
                AND quote.quote_minute >=
                      valuation_time - interval '120 seconds'
                AND quote.fetched_at >= quote.quote_minute
                AND quote.fetched_at >=
                      valuation_time - interval '120 seconds'
                 THEN position.quantity * quote.current_price
               ELSE NULL
             END
           ) FILTER (
             WHERE position.identity_key = source.identity_key
           ),
           0
         ),
         count(*) FILTER (
           WHERE quote.quality_status IS DISTINCT FROM 'passed'
              OR quote.quality_reason IS DISTINCT FROM 'ok'
              OR quote.current_price IS NULL
              OR quote.current_price <= 0
              OR quote.current_price::text IN (
                   'NaN', 'Infinity', '-Infinity'
                 )
              OR quote.quote_minute > valuation_time
              OR quote.quote_minute <
                   valuation_time - interval '120 seconds'
              OR quote.fetched_at < quote.quote_minute
              OR quote.fetched_at <
                   valuation_time - interval '120 seconds'
         )::integer
    INTO position_market_value, identity_market_value,
         invalid_position_quote_count
  FROM public.n6_virtual_position position
  LEFT JOIN public.v_n6_virtual_quote_latest quote
    ON quote.identity_key = position.identity_key
  WHERE position.virtual_account_id = account_row.virtual_account_id
    AND position.principal_id = source.principal_id
    AND position.principal_type = 'ai_user'
    AND position.asset_kind = 'stock'
    AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
    AND position.position_status = 'open_virtual'
    AND position.quantity > 0;
  IF invalid_position_quote_count > 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'portfolio_quote_not_ready'
    );
  END IF;
  SELECT COALESCE(
           pg_catalog.sum(300000) FILTER (
             WHERE proposal.proposal_status IN ('confirmed', 'processing')
               AND proposal.expires_at > valuation_time
           ),
           0
         ),
         COALESCE(
           pg_catalog.sum(300000) FILTER (
             WHERE proposal.proposal_status IN ('confirmed', 'processing')
               AND proposal.expires_at > valuation_time
               AND proposal.identity_key = source.identity_key
           ),
           0
         )
    INTO outstanding_buy_reservation,
         outstanding_identity_reservation
  FROM public.n6_virtual_trade_proposal proposal
  WHERE proposal.virtual_account_id = account_row.virtual_account_id
    AND proposal.principal_id = source.principal_id
    AND proposal.principal_type = 'ai_user'
    AND proposal.proposal_side = 'buy';
  current_equity :=
    cash_row.available_cash + cash_row.frozen_cash +
    position_market_value;
  SELECT GREATEST(
           account_row.initial_cash,
           COALESCE(pg_catalog.max(summary.total_asset), 0),
           current_equity
         ),
         COALESCE(pg_catalog.max(summary.max_drawdown_pct), 0)
    INTO peak_equity, latest_drawdown
  FROM public.n6_ai_daily_summary summary
  WHERE summary.ai_user_id = source.ai_user_id;
  current_drawdown := CASE
    WHEN peak_equity > 0
      THEN GREATEST(
        0, (peak_equity - current_equity) / peak_equity * 100
      )
    ELSE 0
  END;
  latest_drawdown :=
    GREATEST(latest_drawdown, current_drawdown);

  IF source.decision_type = 'buy'
     AND COALESCE(latest_drawdown, 0) >= 5 THEN
    UPDATE public.n6_ai_user ai
    SET status = 'disabled',
        updated_at = pg_catalog.now()
    WHERE ai.ai_user_id = source.ai_user_id
      AND ai.principal_id = source.principal_id
      AND ai.status = 'active';
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'agent_drawdown_paused'
    );
  END IF;
  IF source.decision_type = 'buy'
     AND (
       daily_buy_count >=
         (CASE WHEN autonomous_trade_days < 3 THEN 1 ELSE 10 END)
       OR identity_market_value +
            outstanding_identity_reservation + 300000 > 600000
       OR current_equity <= 0
       OR position_market_value +
            outstanding_buy_reservation + 300000 >
            current_equity * 0.10
       OR cash_row.available_cash <
            outstanding_buy_reservation + 300000
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_risk_limit_rejected'
    );
  END IF;

  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id, principal_type, user_id, actor_ai_user_id,
    virtual_account_id, source_type, source_id,
    source_signal_projection_id, source_virtual_position_id,
    source_ai_decision_id, holding_episode_no, asset_kind,
    identity_key, proposal_side, signal_reference_kind,
    signal_reference_price, locked_target_price, proposal_status,
    expires_at, confirmed_at, confirm_idempotency_key,
    policy_version, policy_hash, source_lineage_json
  )
  VALUES (
    source.principal_id, 'ai_user', NULL, source.ai_user_id,
    account_row.virtual_account_id, target_source_type,
    target_source_id, source.source_signal_projection_id,
    target_position_id, source.ai_decision_id, target_episode_no,
    'stock', source.identity_key, source.decision_type,
    target_reference_kind, target_reference_price, target_price,
    'confirmed', pg_catalog.clock_timestamp() + interval '60 seconds',
    pg_catalog.clock_timestamp(), p_payload->>'idempotency_key',
    'n6_ai_agent_v1',
    '9e7eaa75b8168967b3e90c0ea59edbc7cf9c73c85d60aa625fd60908e01fa471',
    pg_catalog.jsonb_build_object(
      'source', 'n6_ai_decision',
      'source_ai_decision_id', source.ai_decision_id,
      'strategy_id', source.strategy_id,
      'risk_limits_rechecked', true,
      'paper_only', true
    )
  )
  RETURNING n6_virtual_trade_proposal.proposal_id
    INTO target_proposal_id;

  UPDATE public.n6_ai_decision decision
  SET proposal_id = target_proposal_id,
      decision_status = 'proposal_confirmed',
      updated_at = pg_catalog.now()
  WHERE decision.ai_decision_id = source.ai_decision_id
    AND decision.proposal_id IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION '055 AI decision proposal pointer conflict';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'confirmed',
    'proposal_id', target_proposal_id
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.n6_ai_executor_risk_recheck(
  p_proposal_id bigint,
  p_executor_run_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  proposal public.n6_virtual_trade_proposal%ROWTYPE;
  decision_row record;
  account_row public.n6_virtual_account%ROWTYPE;
  cash_row public.n6_virtual_cash_snapshot%ROWTYPE;
  account_count integer;
  daily_buy_count integer;
  autonomous_trade_days integer;
  position_market_value numeric(24,4);
  identity_market_value numeric(24,4);
  outstanding_buy_reservation numeric(24,4);
  outstanding_identity_reservation numeric(24,4);
  invalid_position_quote_count integer;
  current_equity numeric(24,4);
  peak_equity numeric(24,4);
  current_drawdown numeric(18,8);
  latest_drawdown numeric(18,8);
  valuation_time timestamptz := pg_catalog.clock_timestamp();
  current_trade_date date :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
  current_time time :=
    (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time;
BEGIN
  IF SESSION_USER <> 'n6_virtual_executor'
     OR p_proposal_id IS NULL
     OR p_proposal_id <= 0
     OR p_executor_run_id IS NULL
     OR pg_catalog.btrim(p_executor_run_id) = ''
     OR pg_catalog.length(p_executor_run_id) > 200 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_risk_recheck_request'
    );
  END IF;
  SELECT *
    INTO proposal
  FROM public.n6_virtual_trade_proposal target
  WHERE target.proposal_id = p_proposal_id
    AND target.proposal_status = 'processing'
    AND target.executor_run_id = p_executor_run_id
    AND target.principal_type = 'ai_user'
  FOR UPDATE;
  IF NOT FOUND
     OR proposal.user_id IS NOT NULL
     OR proposal.actor_ai_user_id IS NULL
     OR proposal.asset_kind <> 'stock'
     OR proposal.identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
     OR proposal.proposal_side NOT IN ('buy', 'sell')
     OR proposal.source_type NOT IN ('signal', 'ai_risk', 'stop_loss')
     OR proposal.expires_at <= pg_catalog.clock_timestamp()
     OR (
       proposal.source_type IN ('signal', 'ai_risk')
       AND proposal.source_ai_decision_id IS NULL
     )
     OR (
       proposal.source_type = 'stop_loss'
       AND proposal.source_ai_decision_id IS NOT NULL
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_proposal_authority_rejected'
    );
  END IF;
  IF NOT (
       current_time BETWEEN time '09:30:00' AND time '11:30:00'
       OR current_time BETWEEN time '13:00:00' AND time '15:00:00'
     )
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date =
             pg_catalog.to_char(current_trade_date, 'YYYYMMDD')
         AND calendar.is_open = true
     )
     OR NOT EXISTS (
       SELECT 1
       FROM public.n6_principal principal
       JOIN public.n6_ai_user ai
         ON ai.principal_id = principal.principal_id
        AND ai.principal_type = principal.principal_type
        AND ai.ai_user_id = proposal.actor_ai_user_id
        AND ai.status = 'active'
       WHERE principal.principal_id = proposal.principal_id
         AND principal.principal_type = 'ai_user'
         AND principal.principal_status = 'active'
         AND principal.owner_user_id IS NULL
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_runtime_authority_rejected'
    );
  END IF;

  IF proposal.source_ai_decision_id IS NOT NULL THEN
    SELECT decision.ai_decision_id, decision.ai_user_id,
           decision.principal_id, decision.decision_type,
           decision.identity_key,
           decision.source_signal_projection_id,
           decision.source_virtual_position_id,
           decision.server_risk_allowed,
           decision.server_risk_reason,
           decision.risk_assessment_json,
           decision.decision_status,
           decision.proposal_id,
           decision_run.run_mode,
           context_snapshot.for_trade_date,
           strategy.status AS strategy_status
      INTO decision_row
    FROM public.n6_ai_decision decision
    JOIN public.n6_ai_decision_run decision_run
      ON decision_run.ai_decision_run_id =
           decision.ai_decision_run_id
    JOIN public.n6_ai_context_snapshot context_snapshot
      ON context_snapshot.ai_context_snapshot_id =
           decision_run.ai_context_snapshot_id
    JOIN public.n6_strategy strategy
      ON strategy.strategy_id = decision_run.strategy_id
     AND strategy.principal_id = decision.principal_id
    WHERE decision.ai_decision_id =
          proposal.source_ai_decision_id
    FOR SHARE OF decision;
    IF NOT FOUND
       OR decision_row.ai_user_id <> proposal.actor_ai_user_id
       OR decision_row.principal_id <> proposal.principal_id
       OR decision_row.decision_type <> proposal.proposal_side
       OR decision_row.identity_key <> proposal.identity_key
       OR decision_row.decision_status <> 'proposal_confirmed'
       OR decision_row.proposal_id <> proposal.proposal_id
       OR decision_row.run_mode <> 'autonomous_canary'
       OR decision_row.for_trade_date <> current_trade_date
       OR decision_row.strategy_status <> 'active'
       OR decision_row.server_risk_allowed IS DISTINCT FROM true THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'ai_decision_link_rejected'
      );
    END IF;
  END IF;

  SELECT count(*)
    INTO account_count
  FROM public.n6_virtual_account account
  WHERE account.principal_id = proposal.principal_id
    AND account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active';
  IF account_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_account_authority_conflict'
    );
  END IF;
  SELECT *
    INTO account_row
  FROM public.n6_virtual_account account
  WHERE account.principal_id = proposal.principal_id
    AND account.principal_type = 'ai_user'
    AND account.virtual_account_status = 'active'
  FOR UPDATE;
  IF account_row.virtual_account_id <>
       proposal.virtual_account_id THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_account_scope_mismatch'
    );
  END IF;
  SELECT *
    INTO cash_row
  FROM public.n6_virtual_cash_snapshot cash
  WHERE cash.cash_snapshot_id = account_row.current_cash_snapshot_id
    AND cash.virtual_account_id = account_row.virtual_account_id
    AND cash.snapshot_status = 'active'
  FOR SHARE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_cash_not_ready'
    );
  END IF;

  IF proposal.source_type = 'signal' THEN
    IF decision_row.source_signal_projection_id IS NULL
       OR proposal.source_signal_projection_id <>
            decision_row.source_signal_projection_id
       OR proposal.source_id <>
            decision_row.source_signal_projection_id::text
       OR NOT EXISTS (
         SELECT 1
         FROM public.n6_ai_shared_signal_projection projection
         JOIN public.user_projection_run projection_run
           ON projection_run.user_projection_run_id =
                projection.user_projection_run_id
          AND projection_run.status IN ('passed', 'ready')
         WHERE projection.source_signal_projection_id =
               proposal.source_signal_projection_id
           AND projection.shared_status = 'active'
           AND projection.asset_kind = 'stock'
           AND projection.identity_key = proposal.identity_key
           AND projection.direction = proposal.proposal_side
           AND projection.for_trade_date = current_trade_date
           AND projection.action_state IN ('eligible', 'executed')
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'ai_signal_recheck_rejected'
      );
    END IF;
  ELSIF proposal.source_type = 'ai_risk' THEN
    IF proposal.proposal_side <> 'sell'
       OR proposal.source_virtual_position_id IS NULL
       OR decision_row.source_virtual_position_id IS DISTINCT FROM
            proposal.source_virtual_position_id
       OR decision_row.source_signal_projection_id IS NOT NULL
       OR decision_row.risk_assessment_json->>'trigger'
            NOT IN ('portfolio_risk', 'stop_loss') THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'ai_risk_sell_recheck_rejected'
      );
    END IF;
  ELSIF proposal.proposal_side <> 'sell'
        OR proposal.source_virtual_position_id IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_stop_loss_recheck_rejected'
    );
  END IF;

  IF proposal.proposal_side = 'sell'
     AND NOT EXISTS (
       SELECT 1
       FROM public.n6_virtual_position position
       WHERE position.virtual_position_id =
             proposal.source_virtual_position_id
         AND position.virtual_account_id =
             account_row.virtual_account_id
         AND position.principal_id = proposal.principal_id
         AND position.principal_type = 'ai_user'
         AND position.asset_kind = 'stock'
         AND position.identity_key = proposal.identity_key
         AND position.position_status = 'open_virtual'
         AND position.quantity > 0
         AND position.available_quantity > 0
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'ai_sellable_position_rejected'
    );
  END IF;

  IF proposal.proposal_side = 'buy' THEN
    SELECT count(DISTINCT
                 (trade.trade_time AT TIME ZONE 'Asia/Shanghai')::date)
      INTO autonomous_trade_days
    FROM public.n6_virtual_trade trade
    WHERE trade.virtual_account_id = account_row.virtual_account_id
      AND trade.principal_id = proposal.principal_id
      AND trade.principal_type = 'ai_user'
      AND trade.trade_side = 'buy'
      AND trade.trade_status = 'filled_virtual';
    SELECT count(*)
      INTO daily_buy_count
    FROM public.n6_virtual_trade_proposal other
    WHERE other.virtual_account_id = account_row.virtual_account_id
      AND other.principal_id = proposal.principal_id
      AND other.principal_type = 'ai_user'
      AND other.proposal_side = 'buy'
      AND other.proposal_id <> proposal.proposal_id
      AND (other.created_at AT TIME ZONE 'Asia/Shanghai')::date =
            current_trade_date
      AND other.proposal_status IN (
        'confirmed', 'processing', 'executed'
      );
    SELECT COALESCE(
             pg_catalog.sum(
               CASE
                 WHEN quote.quality_status = 'passed'
                  AND quote.quality_reason = 'ok'
                  AND quote.current_price > 0
                  AND quote.current_price::text NOT IN (
                        'NaN', 'Infinity', '-Infinity'
                      )
                  AND quote.quote_minute <= valuation_time
                  AND quote.quote_minute >=
                        valuation_time - interval '120 seconds'
                  AND quote.fetched_at >= quote.quote_minute
                  AND quote.fetched_at >=
                        valuation_time - interval '120 seconds'
                   THEN position.quantity * quote.current_price
                 ELSE NULL
               END
             ),
             0
           ),
           COALESCE(
             pg_catalog.sum(
               CASE
                 WHEN quote.quality_status = 'passed'
                  AND quote.quality_reason = 'ok'
                  AND quote.current_price > 0
                  AND quote.current_price::text NOT IN (
                        'NaN', 'Infinity', '-Infinity'
                      )
                  AND quote.quote_minute <= valuation_time
                  AND quote.quote_minute >=
                        valuation_time - interval '120 seconds'
                  AND quote.fetched_at >= quote.quote_minute
                  AND quote.fetched_at >=
                        valuation_time - interval '120 seconds'
                   THEN position.quantity * quote.current_price
                 ELSE NULL
               END
             ) FILTER (
               WHERE position.identity_key = proposal.identity_key
             ),
             0
           ),
           count(*) FILTER (
             WHERE quote.quality_status IS DISTINCT FROM 'passed'
                OR quote.quality_reason IS DISTINCT FROM 'ok'
                OR quote.current_price IS NULL
                OR quote.current_price <= 0
                OR quote.current_price::text IN (
                     'NaN', 'Infinity', '-Infinity'
                   )
                OR quote.quote_minute > valuation_time
                OR quote.quote_minute <
                     valuation_time - interval '120 seconds'
                OR quote.fetched_at < quote.quote_minute
                OR quote.fetched_at <
                     valuation_time - interval '120 seconds'
           )::integer
      INTO position_market_value, identity_market_value,
           invalid_position_quote_count
    FROM public.n6_virtual_position position
    LEFT JOIN public.v_n6_virtual_quote_latest quote
      ON quote.identity_key = position.identity_key
    WHERE position.virtual_account_id =
          account_row.virtual_account_id
      AND position.principal_id = proposal.principal_id
      AND position.principal_type = 'ai_user'
      AND position.asset_kind = 'stock'
      AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0;
    IF invalid_position_quote_count > 0 THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'ai_portfolio_quote_not_ready'
      );
    END IF;
    SELECT COALESCE(
             pg_catalog.sum(300000) FILTER (
               WHERE other.proposal_status IN ('confirmed', 'processing')
                 AND other.expires_at > valuation_time
             ),
             0
           ),
           COALESCE(
             pg_catalog.sum(300000) FILTER (
               WHERE other.proposal_status IN ('confirmed', 'processing')
                 AND other.expires_at > valuation_time
                 AND other.identity_key = proposal.identity_key
             ),
             0
           )
      INTO outstanding_buy_reservation,
           outstanding_identity_reservation
    FROM public.n6_virtual_trade_proposal other
    WHERE other.virtual_account_id = account_row.virtual_account_id
      AND other.principal_id = proposal.principal_id
      AND other.principal_type = 'ai_user'
      AND other.proposal_side = 'buy'
      AND other.proposal_id <> proposal.proposal_id;
    current_equity :=
      cash_row.available_cash + cash_row.frozen_cash +
      position_market_value;
    SELECT GREATEST(
             account_row.initial_cash,
             COALESCE(pg_catalog.max(summary.total_asset), 0),
             current_equity
           ),
           COALESCE(pg_catalog.max(summary.max_drawdown_pct), 0)
      INTO peak_equity, latest_drawdown
    FROM public.n6_ai_daily_summary summary
    WHERE summary.ai_user_id = proposal.actor_ai_user_id;
    current_drawdown := CASE
      WHEN peak_equity > 0
        THEN GREATEST(
          0, (peak_equity - current_equity) / peak_equity * 100
        )
      ELSE 0
    END;
    latest_drawdown :=
      GREATEST(latest_drawdown, current_drawdown);
    IF COALESCE(latest_drawdown, 0) >= 5 THEN
      UPDATE public.n6_ai_user ai
      SET status = 'disabled',
          updated_at = pg_catalog.now()
      WHERE ai.ai_user_id = proposal.actor_ai_user_id
        AND ai.principal_id = proposal.principal_id
        AND ai.status = 'active';
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'agent_drawdown_paused'
      );
    END IF;
    IF daily_buy_count >=
         (CASE WHEN autonomous_trade_days < 3 THEN 1 ELSE 10 END)
       OR identity_market_value +
            outstanding_identity_reservation + 300000 > 600000
       OR current_equity <= 0
       OR position_market_value +
            outstanding_buy_reservation + 300000 >
            current_equity * 0.10
       OR cash_row.available_cash <
            outstanding_buy_reservation + 300000 THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'ai_risk_limit_rejected'
      );
    END IF;
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'passed',
    'proposal_id', proposal.proposal_id,
    'serialized_by_virtual_account_id',
      account_row.virtual_account_id
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.n6_ai_strategy_shadow_evaluate(
  p_for_trade_date date,
  p_run_bucket text,
  p_policy_document_sha256 text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  expected_policy_document_sha256 constant text :=
    '56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7';
  live_context_bundle_hash constant text :=
    '1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc';
  promoted_knowledge_bundle_version constant text :=
    'N6_AI_KNOWLEDGE_BUNDLE_V3';
  promoted_knowledge_bundle_sha256 constant text :=
    '95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b';
  strategy_context jsonb;
  context_snapshot_id bigint;
  authority record;
  candidate jsonb;
  candidate_count integer := 0;
  action_count integer := 0;
  completed_episode_count integer := 0;
  inserted_count integer := 0;
  local_strategy_timestamp timestamp :=
    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai';
  local_strategy_time time :=
    local_strategy_timestamp::time;
  current_strategy_run_bucket text :=
    pg_catalog.to_char(
      local_strategy_timestamp, 'YYYYMMDD"T"HH24'
    )
    || pg_catalog.lpad(
         (
           (
             EXTRACT(
               MINUTE FROM local_strategy_timestamp
             )::integer / 5
           ) * 5
         )::text,
         2,
         '0'
       )
    || '+0800';
  position_row public.n6_virtual_position%ROWTYPE;
  episode_row public.n6_ai_position_strategy_episode%ROWTYPE;
  target_source_signal_id bigint;
  target_source_quality_status text;
  target_source_reference_price numeric(24,8);
  target_source_matches_locked_price boolean;
  target_source_sell_period text;
  sell_source_signal_id bigint;
  quote_snapshot_id bigint;
  positive_episode_lot_quantity numeric(24,4);
  invalid_positive_episode_lot_count bigint;
  server_sellable_quantity numeric(24,4);
  sellable_lot_state_hash text;
  planned_quantity numeric(24,4);
  action_type text;
  action_idempotency_key text;
  period_clear_priority boolean;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_for_trade_date IS NULL
     OR p_for_trade_date <>
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR NOT (
       local_strategy_time BETWEEN time '09:30' AND time '11:30'
       OR local_strategy_time BETWEEN time '13:00' AND time '15:00'
     )
     OR p_run_bucket IS NULL
     OR p_run_bucket !~
          '^[0-9]{8}T[0-9]{4}[+]0800$'
     OR pg_catalog.substr(p_run_bucket, 1, 8) <>
          pg_catalog.to_char(p_for_trade_date, 'YYYYMMDD')
     OR (
          pg_catalog.substr(p_run_bucket, 12, 2)::integer % 5
        ) <> 0
     OR p_run_bucket IS DISTINCT FROM current_strategy_run_bucket
     OR p_policy_document_sha256 IS DISTINCT FROM
          expected_policy_document_sha256 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'invalid_shadow_strategy_request',
      'policy_version', 'n6_ai_investor_strategy_policy_v1',
      'policy_document_sha256', expected_policy_document_sha256,
      'knowledge_bundle_version', promoted_knowledge_bundle_version,
      'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
      'proposal_created', false,
      'order_created', false,
      'trade_created', false,
      'position_mutated', false,
      'cash_mutated', false,
      'execution_authorized', false
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date =
          pg_catalog.to_char(
            p_for_trade_date, 'YYYYMMDD'
          )
      AND calendar.is_open = true
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'not_open_trade_date',
      'policy_version', 'n6_ai_investor_strategy_policy_v1',
      'policy_document_sha256', expected_policy_document_sha256,
      'knowledge_bundle_version', promoted_knowledge_bundle_version,
      'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
      'candidate_rank_audit_count', 0,
      'strategy_action_audit_count', 0,
      'completed_strategy_episode_count', 0,
      'proposal_created', false,
      'order_created', false,
      'trade_created', false,
      'position_mutated', false,
      'cash_mutated', false,
      'execution_authorized', false
    );
  END IF;

  strategy_context := public.n6_ai_strategy_context_load_v1(
    p_run_bucket,
    p_for_trade_date,
    1000,
    live_context_bundle_hash
  );
  IF COALESCE((strategy_context->>'ok')::boolean, false) = false
     OR strategy_context->>'status'
          NOT IN ('ready', 'already_processed')
     OR COALESCE(
          strategy_context->>'strategy_context_snapshot_id', ''
        ) !~ '^[0-9]+$'
     OR COALESCE(
          strategy_context->>'strategy_workset_hash', ''
        ) !~ '^[0-9a-f]{64}$'
     OR COALESCE(
          strategy_context->>'base_snapshot_workset_hash', ''
        ) !~ '^[0-9a-f]{64}$'
     OR pg_catalog.jsonb_typeof(
          strategy_context->'strategy_candidates'
        ) <> 'array' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', COALESCE(
        strategy_context->>'status', 'strategy_context_not_ready'
      ),
      'policy_version', 'n6_ai_investor_strategy_policy_v1',
      'policy_document_sha256', expected_policy_document_sha256,
      'knowledge_bundle_version', promoted_knowledge_bundle_version,
      'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
      'proposal_created', false,
      'order_created', false,
      'trade_created', false,
      'position_mutated', false,
      'cash_mutated', false,
      'execution_authorized', false
    );
  END IF;
  context_snapshot_id :=
    (strategy_context->>'strategy_context_snapshot_id')::bigint;

  SELECT snapshot.ai_user_id, snapshot.principal_id,
         snapshot.strategy_id, snapshot.virtual_account_id,
         snapshot.source_signal_projection_ids_json,
         snapshot.workset_hash AS strategy_workset_hash
    INTO authority
  FROM public.n6_ai_context_snapshot snapshot
  JOIN public.n6_ai_user ai
    ON ai.ai_user_id = snapshot.ai_user_id
   AND ai.principal_id = snapshot.principal_id
   AND ai.status IN ('sandbox_only', 'active')
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  JOIN public.n6_strategy strategy
    ON strategy.strategy_id = snapshot.strategy_id
   AND strategy.principal_id = snapshot.principal_id
   AND strategy.status = 'active'
  JOIN public.n6_virtual_account account
    ON account.virtual_account_id = snapshot.virtual_account_id
   AND account.principal_id = snapshot.principal_id
   AND account.principal_type = 'ai_user'
   AND account.virtual_account_status = 'active'
  WHERE snapshot.ai_context_snapshot_id = context_snapshot_id
    AND snapshot.for_trade_date = p_for_trade_date
    AND snapshot.context_status = 'frozen'
    AND snapshot.knowledge_bundle_hash =
          live_context_bundle_hash
    AND snapshot.workset_hash =
          strategy_context->>'base_snapshot_workset_hash'
  FOR UPDATE OF account;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'shadow_strategy_authority_not_ready',
      'policy_version', 'n6_ai_investor_strategy_policy_v1',
      'policy_document_sha256', expected_policy_document_sha256,
      'knowledge_bundle_version', promoted_knowledge_bundle_version,
      'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
      'proposal_created', false,
      'order_created', false,
      'trade_created', false,
      'position_mutated', false,
      'cash_mutated', false,
      'execution_authorized', false
    );
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_ai_candidate_rank_audit prior_audit
    WHERE prior_audit.ai_context_snapshot_id = context_snapshot_id
      AND COALESCE(
            prior_audit.audit_payload_json->>'strategy_workset_hash',
            ''
          ) IS DISTINCT FROM
          strategy_context->>'strategy_workset_hash'
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'status', 'strategy_context_replay_drift',
      'reason', 'strategy_context_replay_drift',
      'policy_version', 'n6_ai_investor_strategy_policy_v1',
      'policy_document_sha256', expected_policy_document_sha256,
      'knowledge_bundle_version', promoted_knowledge_bundle_version,
      'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
      'candidate_rank_audit_count', 0,
      'strategy_action_audit_count', 0,
      'completed_strategy_episode_count', 0,
      'strategy_workset_hash',
        strategy_context->>'strategy_workset_hash',
      'proposal_created', false,
      'order_created', false,
      'trade_created', false,
      'position_mutated', false,
      'cash_mutated', false,
      'execution_authorized', false
    );
  END IF;

  INSERT INTO public.n6_ai_candidate_rank_audit (
    ai_context_snapshot_id, ai_user_id, principal_id,
    principal_type, strategy_id, virtual_account_id,
    for_trade_date, source_signal_projection_id, identity_key,
    financial_score_raw, financial_rank_score, score_status,
    index_hint_evidence_refs, board_hint_evidence_refs,
    index_membership_refs, board_membership_refs,
    index_hint_adjustment, board_hint_adjustment,
    index_hint_conflict_zeroed, board_hint_conflict_zeroed,
    candidate_qualified, strategy_hash, knowledge_bundle_hash,
    audit_payload_json
  )
  VALUES (
    context_snapshot_id, authority.ai_user_id,
    authority.principal_id, 'ai_user', authority.strategy_id,
    authority.virtual_account_id, p_for_trade_date,
    NULL, NULL, NULL, 0, 'missing',
    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
    0, 0, false, false, false,
    expected_policy_document_sha256,
    promoted_knowledge_bundle_sha256,
    pg_catalog.jsonb_build_object(
      'mode', 'shadow',
      'source', 'strategy_workset_anchor',
      'policy_document_sha256',
        expected_policy_document_sha256,
      'context_knowledge_bundle_sha256',
        live_context_bundle_hash,
      'strategy_workset_hash',
        strategy_context->>'strategy_workset_hash'
    )
  )
  ON CONFLICT (
    ai_context_snapshot_id, source_signal_projection_id
  ) DO NOTHING;

  WITH closed_position AS (
    SELECT position.virtual_account_id,
           position.virtual_position_id,
           position.principal_id,
           position.principal_type,
           position.identity_key,
           position.holding_episode_no
    FROM public.n6_virtual_position position
    WHERE position.virtual_account_id = authority.virtual_account_id
      AND position.principal_id = authority.principal_id
      AND position.principal_type = 'ai_user'
      AND position.asset_kind = 'stock'
      AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND position.position_status = 'closed_virtual'
      AND position.quantity = 0
      AND position.available_quantity = 0
      AND position.locked_quantity = 0
      AND position.quality_status = 'passed'
      AND position.holding_episode_no > 0
    FOR SHARE OF position
  )
  UPDATE public.n6_ai_position_strategy_episode episode
  SET pending_clear = false,
      episode_status = 'closed',
      pending_clear_completed_at = pg_catalog.clock_timestamp(),
      updated_at = pg_catalog.now()
  FROM closed_position
  WHERE episode.ai_user_id = authority.ai_user_id
    AND episode.principal_id = authority.principal_id
    AND episode.principal_type = 'ai_user'
    AND episode.virtual_account_id =
          closed_position.virtual_account_id
    AND episode.virtual_position_id =
          closed_position.virtual_position_id
    AND episode.identity_key = closed_position.identity_key
    AND episode.holding_episode_no =
          closed_position.holding_episode_no
    AND episode.pending_clear = true
    AND episode.pending_clear_completed_at IS NULL
    AND episode.episode_status = 'open'
    AND EXISTS (
      SELECT 1
      FROM public.n6_virtual_position_lot lot
      WHERE lot.virtual_position_id =
              closed_position.virtual_position_id
        AND lot.holding_episode_no =
              closed_position.holding_episode_no
        AND lot.virtual_account_id =
              closed_position.virtual_account_id
        AND lot.principal_id = authority.principal_id
        AND lot.principal_type = 'ai_user'
        AND lot.identity_key = closed_position.identity_key
    )
    AND NOT EXISTS (
      SELECT 1
      FROM public.n6_virtual_position_lot lot
      WHERE lot.virtual_position_id =
              closed_position.virtual_position_id
        AND lot.holding_episode_no =
              closed_position.holding_episode_no
        AND (
          lot.virtual_account_id IS DISTINCT FROM
            closed_position.virtual_account_id
          OR lot.principal_id IS DISTINCT FROM authority.principal_id
          OR lot.principal_type IS DISTINCT FROM 'ai_user'
          OR lot.identity_key IS DISTINCT FROM
               closed_position.identity_key
          OR lot.remaining_quantity <> 0
          OR lot.lot_status <> 'closed'
        )
    );
  GET DIAGNOSTICS completed_episode_count = ROW_COUNT;

  FOR position_row IN
    SELECT position.*
    FROM public.n6_virtual_position position
    WHERE position.virtual_account_id = authority.virtual_account_id
      AND position.principal_id = authority.principal_id
      AND position.principal_type = 'ai_user'
      AND position.asset_kind = 'stock'
      AND position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
      AND position.holding_episode_no > 0
    ORDER BY position.virtual_position_id
    FOR SHARE
  LOOP
    SELECT COALESCE(
             pg_catalog.sum(lot.remaining_quantity)
               FILTER (WHERE lot.remaining_quantity > 0),
             0
           ),
           pg_catalog.count(*) FILTER (
             WHERE lot.remaining_quantity > 0
               AND (
                 lot.virtual_account_id <> authority.virtual_account_id
                 OR lot.principal_id <> authority.principal_id
                 OR lot.principal_type <> 'ai_user'
                 OR lot.identity_key <> position_row.identity_key
                 OR lot.lot_status NOT IN ('available', 'locked_t1')
               )
           )
      INTO positive_episode_lot_quantity,
           invalid_positive_episode_lot_count
    FROM public.n6_virtual_position_lot lot
    WHERE lot.virtual_position_id = position_row.virtual_position_id
      AND lot.holding_episode_no = position_row.holding_episode_no;
    IF positive_episode_lot_quantity IS DISTINCT FROM
         position_row.quantity
       OR invalid_positive_episode_lot_count > 0 THEN
      RAISE EXCEPTION 'shadow_strategy_position_lot_invariant_failed';
    END IF;

    target_source_signal_id := NULL;
    target_source_quality_status := NULL;
    target_source_reference_price := NULL;
    target_source_matches_locked_price := false;
    target_source_sell_period := NULL;
    IF position_row.target_price_source_signal_projection_id > 0 THEN
      SELECT signal.source_signal_projection_id,
             signal.target_quality_status,
             signal.reference_target_price,
             signal.reference_target_price =
               position_row.locked_target_price,
             signal.up_sell_reference_period
        INTO target_source_signal_id,
             target_source_quality_status,
             target_source_reference_price,
             target_source_matches_locked_price,
             target_source_sell_period
      FROM public.n6_ai_shared_signal_projection signal
      JOIN public.user_projection_run projection_run
        ON projection_run.user_projection_run_id =
             signal.user_projection_run_id
       AND projection_run.source_layer = 'N5_action'
       AND projection_run.status = 'passed'
       AND projection_run.quality_summary_json
             ->>'b_track_signal_projection' = 'passed'
      WHERE signal.source_signal_projection_id =
              position_row.target_price_source_signal_projection_id
        AND signal.asset_kind = 'stock'
        AND signal.identity_key = position_row.identity_key
        AND signal.shared_status = 'active'
        AND signal.strategy_context_version =
              'n6_ai_investor_strategy_policy_v1';
    END IF;

    INSERT INTO public.n6_ai_position_strategy_episode (
      ai_user_id, principal_id, principal_type, strategy_id,
      virtual_account_id, virtual_position_id, identity_key,
      holding_episode_no, locked_target_price,
      locked_target_quality_status,
      locked_target_source_signal_projection_id,
      up_sell_reference_period, policy_hash
    )
    VALUES (
      authority.ai_user_id, authority.principal_id, 'ai_user',
      authority.strategy_id, authority.virtual_account_id,
      position_row.virtual_position_id, position_row.identity_key,
      position_row.holding_episode_no,
      CASE
        WHEN position_row.target_price_status = 'frozen'
         AND position_row.locked_target_price > 0
         AND target_source_quality_status = 'passed'
         AND target_source_reference_price =
               position_row.locked_target_price
         AND target_source_matches_locked_price
         AND target_source_signal_id > 0
          THEN position_row.locked_target_price
        ELSE NULL
      END,
      CASE
        WHEN position_row.target_price_status = 'frozen'
         AND position_row.locked_target_price > 0
         AND target_source_quality_status = 'passed'
         AND target_source_reference_price =
               position_row.locked_target_price
         AND target_source_matches_locked_price
         AND target_source_signal_id > 0
          THEN 'passed'
        ELSE 'not_ready'
      END,
      CASE
        WHEN position_row.target_price_status = 'frozen'
         AND position_row.locked_target_price > 0
         AND target_source_quality_status = 'passed'
         AND target_source_reference_price =
               position_row.locked_target_price
         AND target_source_matches_locked_price
         AND target_source_signal_id > 0
          THEN target_source_signal_id
        ELSE NULL
      END,
      target_source_sell_period,
      expected_policy_document_sha256
    )
    ON CONFLICT (
      virtual_account_id, virtual_position_id, holding_episode_no
    ) DO NOTHING;

    SELECT *
      INTO episode_row
    FROM public.n6_ai_position_strategy_episode episode
    WHERE episode.virtual_account_id = authority.virtual_account_id
      AND episode.virtual_position_id =
            position_row.virtual_position_id
      AND episode.holding_episode_no =
            position_row.holding_episode_no
    FOR UPDATE;
    IF episode_row.ai_user_id IS DISTINCT FROM authority.ai_user_id
       OR episode_row.principal_id IS DISTINCT FROM authority.principal_id
       OR episode_row.principal_type IS DISTINCT FROM 'ai_user'
       OR episode_row.virtual_account_id IS DISTINCT FROM
            authority.virtual_account_id
       OR episode_row.virtual_position_id IS DISTINCT FROM
            position_row.virtual_position_id
       OR episode_row.holding_episode_no IS DISTINCT FROM
            position_row.holding_episode_no
       OR episode_row.identity_key IS DISTINCT FROM
            position_row.identity_key
       OR episode_row.episode_status IS DISTINCT FROM 'open'
       OR episode_row.policy_version IS DISTINCT FROM
            'n6_ai_investor_strategy_policy_v1'
       OR episode_row.policy_hash IS DISTINCT FROM
            expected_policy_document_sha256 THEN
      RAISE EXCEPTION 'shadow_strategy_episode_mismatch';
    END IF;

    SELECT COALESCE(pg_catalog.sum(lot.remaining_quantity), 0),
           pg_catalog.encode(
             pg_catalog.sha256(
               pg_catalog.convert_to(
                 COALESCE(
                   pg_catalog.jsonb_agg(
                     pg_catalog.jsonb_build_array(
                       lot.virtual_position_lot_id,
                       lot.remaining_quantity,
                       lot.available_trade_date,
                       lot.lot_status
                     )
                     ORDER BY lot.virtual_position_lot_id
                   ),
                   '[]'::jsonb
                 )::text,
                 'UTF8'
               )
             ),
             'hex'
           )
      INTO server_sellable_quantity, sellable_lot_state_hash
    FROM public.n6_virtual_position_lot lot
    WHERE lot.virtual_account_id = authority.virtual_account_id
      AND lot.virtual_position_id = position_row.virtual_position_id
      AND lot.principal_id = authority.principal_id
      AND lot.principal_type = 'ai_user'
      AND lot.identity_key = position_row.identity_key
      AND lot.holding_episode_no = position_row.holding_episode_no
      AND lot.remaining_quantity > 0
      AND lot.available_trade_date <= p_for_trade_date
      AND lot.lot_status IN ('available', 'locked_t1');

    sell_source_signal_id := NULL;
    SELECT signal.source_signal_projection_id
      INTO sell_source_signal_id
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    WHERE signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'stock'
      AND signal.identity_key = position_row.identity_key
      AND signal.direction = 'sell'
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND authority.source_signal_projection_ids_json @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
      AND signal.reason_fields_json->>'primary_trigger_period'
            = episode_row.up_sell_reference_period
    ORDER BY signal.source_event_time DESC,
             signal.source_signal_projection_id DESC
    LIMIT 1;
    period_clear_priority :=
      FOUND AND episode_row.pending_clear IS DISTINCT FROM true;

    IF period_clear_priority THEN
      UPDATE public.n6_ai_position_strategy_episode
      SET pending_clear = true,
          pending_clear_source_signal_projection_id =
            sell_source_signal_id,
          pending_clear_started_trade_date = p_for_trade_date,
          updated_at = pg_catalog.now()
      WHERE strategy_episode_id = episode_row.strategy_episode_id;
    END IF;

    IF server_sellable_quantity <= 0 THEN
      CONTINUE;
    END IF;

    quote_snapshot_id := NULL;
    IF NOT period_clear_priority
       AND episode_row.pending_clear IS DISTINCT FROM true
       AND episode_row.locked_target_quality_status = 'passed'
       AND episode_row.locked_target_price IS NOT NULL THEN
      SELECT quote.virtual_quote_snapshot_id
        INTO quote_snapshot_id
      FROM public.n6_virtual_quote_snapshot quote
      WHERE quote.identity_key = position_row.identity_key
        AND quote.quality_status = 'passed'
        AND quote.quality_reason = 'ok'
        AND quote.source_adapter = 'mootdx.std'
        AND quote.exchange IN ('SH', 'SZ')
        AND quote.current_price::text ~ '^[0-9]+([.][0-9]+)?$'
        AND quote.current_price > 0
        AND quote.current_price >= episode_row.locked_target_price
        AND (
          quote.quote_minute AT TIME ZONE 'Asia/Shanghai'
        )::date = p_for_trade_date
        AND (
          (
            quote.quote_minute AT TIME ZONE 'Asia/Shanghai'
          )::time BETWEEN time '09:30' AND time '11:30'
          OR (
            quote.quote_minute AT TIME ZONE 'Asia/Shanghai'
          )::time BETWEEN time '13:00' AND time '15:00'
        )
        AND (
          quote.fetched_at AT TIME ZONE 'Asia/Shanghai'
        )::date = p_for_trade_date
        AND (
          (
            quote.fetched_at AT TIME ZONE 'Asia/Shanghai'
          )::time BETWEEN time '09:30' AND time '11:30'
          OR (
            quote.fetched_at AT TIME ZONE 'Asia/Shanghai'
          )::time BETWEEN time '13:00' AND time '15:00'
        )
        AND quote.quote_minute <= pg_catalog.clock_timestamp()
        AND quote.quote_minute >=
              pg_catalog.clock_timestamp() - interval '2 minutes'
        AND quote.fetched_at >= quote.quote_minute
        AND quote.fetched_at <=
              quote.quote_minute + interval '2 minutes'
        AND quote.fetched_at <= pg_catalog.clock_timestamp()
        AND quote.fetched_at >=
              pg_catalog.clock_timestamp() - interval '2 minutes'
      ORDER BY quote.quote_minute DESC,
               quote.virtual_quote_snapshot_id DESC
      LIMIT 1
      FOR SHARE;
    END IF;

    IF period_clear_priority THEN
      action_type := 'period_clear';
      planned_quantity := CASE
        WHEN server_sellable_quantity < 100
          THEN server_sellable_quantity
        ELSE pg_catalog.floor(server_sellable_quantity / 100) * 100
      END;
    ELSIF episode_row.pending_clear THEN
      action_type := 'pending_clear_continue';
      planned_quantity := CASE
        WHEN server_sellable_quantity < 100
          THEN server_sellable_quantity
        ELSE pg_catalog.floor(server_sellable_quantity / 100) * 100
      END;
    ELSIF quote_snapshot_id IS NOT NULL THEN
      action_type := 'target_reduce';
      planned_quantity := CASE
        WHEN server_sellable_quantity < 100
          THEN server_sellable_quantity
        ELSE LEAST(
          server_sellable_quantity,
          GREATEST(
            100,
            pg_catalog.floor(
              server_sellable_quantity / 3 / 100
            ) * 100
          )
        )
      END;
    ELSE
      CONTINUE;
    END IF;

    action_idempotency_key := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(
          pg_catalog.jsonb_build_object(
            'strategy_episode_id', episode_row.strategy_episode_id,
            'for_trade_date', CASE
              WHEN action_type = 'target_reduce'
                THEN p_for_trade_date
              ELSE NULL
            END,
            'action_family', CASE
              WHEN action_type IN (
                'period_clear', 'pending_clear_continue'
              ) THEN 'clear'
              ELSE action_type
            END,
            'locked_target_price', episode_row.locked_target_price,
            'sellable_lot_state_hash', sellable_lot_state_hash,
            'source_signal_projection_id',
              CASE
                WHEN action_type IN (
                  'period_clear', 'pending_clear_continue'
                ) THEN COALESCE(
                  episode_row.pending_clear_source_signal_projection_id,
                  sell_source_signal_id
                )
                ELSE NULL
              END
          )::text,
          'UTF8'
        )
      ),
      'hex'
    );
    INSERT INTO public.n6_ai_strategy_action (
      strategy_episode_id, ai_user_id, principal_id,
      principal_type, strategy_id, virtual_account_id,
      virtual_position_id, identity_key, holding_episode_no,
      for_trade_date, action_type, action_status,
      source_signal_projection_id,
      source_virtual_quote_snapshot_id,
      server_sellable_quantity, planned_quantity,
      locked_target_price, execution_authorized,
      idempotency_key, audit_payload_json
    )
    VALUES (
      episode_row.strategy_episode_id, authority.ai_user_id,
      authority.principal_id, 'ai_user', episode_row.strategy_id,
      authority.virtual_account_id, position_row.virtual_position_id,
      position_row.identity_key, position_row.holding_episode_no,
      p_for_trade_date, action_type, 'shadow_recorded',
      CASE
        WHEN action_type = 'period_clear'
          THEN sell_source_signal_id
        WHEN action_type = 'pending_clear_continue'
          THEN episode_row.pending_clear_source_signal_projection_id
        ELSE NULL
      END,
      CASE WHEN action_type = 'target_reduce'
           THEN quote_snapshot_id ELSE NULL END,
      server_sellable_quantity, planned_quantity,
      episode_row.locked_target_price, false,
      action_idempotency_key,
      pg_catalog.jsonb_build_object(
        'mode', 'shadow',
        'quantity_authority', 'mature_position_lots',
        'sellable_lot_state_hash', sellable_lot_state_hash,
        'period_clear_priority', period_clear_priority,
        'evaluation_strategy_id', authority.strategy_id,
        'episode_strategy_id', episode_row.strategy_id,
        't1_enforced', true,
        'odd_lot_rule', 'sell_all_when_server_sellable_below_100',
        'execution_authorized', false
      )
    )
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    action_count := action_count + inserted_count;
  END LOOP;

  FOR candidate IN
    SELECT value
    FROM pg_catalog.jsonb_array_elements(
      strategy_context->'strategy_candidates'
    )
  LOOP
    INSERT INTO public.n6_ai_candidate_rank_audit (
      ai_context_snapshot_id, ai_user_id, principal_id,
      principal_type, strategy_id, virtual_account_id,
      for_trade_date, source_signal_projection_id, identity_key,
      financial_score_raw, financial_rank_score, score_status,
      index_hint_evidence_refs, board_hint_evidence_refs,
      index_membership_refs, board_membership_refs,
      index_hint_adjustment, board_hint_adjustment,
      index_hint_conflict_zeroed, board_hint_conflict_zeroed,
      candidate_qualified, strategy_hash, knowledge_bundle_hash,
      audit_payload_json
    )
    SELECT context_snapshot_id, authority.ai_user_id,
           authority.principal_id, 'ai_user', authority.strategy_id,
           authority.virtual_account_id, p_for_trade_date,
           signal.source_signal_projection_id, signal.identity_key,
           signal.financial_score_raw,
           COALESCE(signal.financial_score_raw, 0),
           CASE WHEN signal.financial_score_raw IS NULL
                THEN 'missing' ELSE 'available' END,
           candidate->'index_hint_evidence_refs',
           candidate->'board_hint_evidence_refs',
           candidate->'index_membership_refs',
           candidate->'board_membership_refs',
           (candidate->>'index_hint_adjustment')::integer,
           (candidate->>'board_hint_adjustment')::integer,
           (candidate->>'index_hint_conflict_zeroed')::boolean,
           (candidate->>'board_hint_conflict_zeroed')::boolean,
           NOT qualification.pending_clear_blocked,
           expected_policy_document_sha256,
           promoted_knowledge_bundle_sha256,
           pg_catalog.jsonb_build_object(
             'mode', 'shadow',
             'source', 'approved_n6_strategy_context',
             'qualification_reason',
               CASE
                 WHEN qualification.pending_clear_blocked
                   THEN 'pending_clear_same_account_identity'
                 ELSE 'qualified'
               END,
             'policy_document_sha256',
               expected_policy_document_sha256,
             'context_knowledge_bundle_sha256',
               live_context_bundle_hash,
             'strategy_workset_hash',
               strategy_context->>'strategy_workset_hash'
           )
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    CROSS JOIN LATERAL (
      SELECT EXISTS (
        SELECT 1
        FROM public.n6_ai_position_strategy_episode episode
        WHERE episode.ai_user_id = authority.ai_user_id
          AND episode.principal_id = authority.principal_id
          AND episode.principal_type = 'ai_user'
          AND episode.virtual_account_id =
                authority.virtual_account_id
          AND episode.identity_key = signal.identity_key
          AND episode.pending_clear = true
          AND episode.episode_status = 'open'
      ) AS pending_clear_blocked
    ) qualification
    WHERE signal.source_signal_projection_id =
            (candidate->>'source_signal_projection_id')::bigint
      AND signal.identity_key = candidate->>'identity_key'
      AND signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'stock'
      AND signal.direction = 'buy'
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND authority.source_signal_projection_ids_json @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
    ON CONFLICT (
      ai_context_snapshot_id, source_signal_projection_id
    ) DO NOTHING;
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    candidate_count := candidate_count + inserted_count;
  END LOOP;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'status', 'shadow_policy_evaluated',
    'policy_version', 'n6_ai_investor_strategy_policy_v1',
    'policy_document_sha256', expected_policy_document_sha256,
    'knowledge_bundle_version', promoted_knowledge_bundle_version,
    'knowledge_bundle_sha256', promoted_knowledge_bundle_sha256,
    'candidate_rank_audit_count', candidate_count,
    'strategy_action_audit_count', action_count,
    'completed_strategy_episode_count', completed_episode_count,
    'strategy_workset_hash',
      strategy_context->>'strategy_workset_hash',
    'proposal_created', false,
    'order_created', false,
    'trade_created', false,
    'position_mutated', false,
    'cash_mutated', false,
    'execution_authorized', false
  );
END
$function$;

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  error_prefix text := '061_postflight_mismatch';
BEGIN
  FOR expected IN
    SELECT *
    FROM (
      VALUES
      ('n6_ai_agent_daily_summary_record(jsonb)', '235b3913734fda03a3d55822d58f785ae3dad36002c38f473bfeaad6636f0042', 'n6_ai_agent'),
      ('n6_ai_agent_context_load(text,date,integer)', '4dae0563b34df9e066c2c91feb6f3a096a09ea2573a31f2cf30c71bfe0704993', NULL::text),
      ('n6_ai_agent_proposal_create_confirm(jsonb)', 'aa3806a66ed5fa08b3c497e42cfb0142c61759b796891cf81d7c041024de05f2', 'n6_ai_agent'),
      ('n6_ai_executor_risk_recheck(bigint,text)', 'f42d6750d192321f851626428589fdc342355410b7e1c50a33855642661bbf75', 'n6_virtual_executor'),
      ('n6_ai_strategy_shadow_evaluate(date,text,text)', 'fcd1ada453c672c8a2caa5caa4857b15f7d162f2ed5780cda27c7cd41ad6b474', 'n6_ai_agent'),
      ('n6_ai_agent_shadow_decision_record(jsonb)', '32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951', 'n6_ai_agent')
    ) AS expected_functions(signature, expected_sha, allowed_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '061_postflight_mismatch: %', expected.signature;
    END IF;
    SELECT function_row.prosrc, function_row.prosecdef,
           function_row.proisstrict, function_row.proleakproof,
           function_row.provolatile, function_row.proparallel,
           function_row.proconfig, function_row.proacl,
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
      SELECT role.oid
        INTO allowed_role_oid
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
      AND function_proc.provolatile = 'v'
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
        (
          expected.allowed_role IS NULL
          AND allowed_role_oid IS NULL
        )
        OR
        (
          expected.allowed_role IS NOT NULL
          AND allowed_role_oid IS NOT NULL
          AND (
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
          (
            function_acl.grantee = function_proc.owner_oid
            OR (
              allowed_role_oid IS NOT NULL
              AND function_acl.grantee = allowed_role_oid
            )
          )
          AND function_acl.privilege_type = 'EXECUTE'
          AND NOT function_acl.is_grantable
        )
      )
    ) THEN
      RAISE EXCEPTION '%: attributes_or_acl %', error_prefix, expected.signature;
    END IF;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF actual_sha <> expected.expected_sha THEN
      RAISE EXCEPTION '061_postflight_mismatch: body %', expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
