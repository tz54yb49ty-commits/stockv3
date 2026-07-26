-- N6 B-track AI simulated investor V1 additive schema and function-only authority.
-- Roles/credentials are provisioned by runtime_control. This migration never
-- starts an agent, enables autonomous trading, or writes an AI identity/account.

BEGIN;

DO $preflight$
DECLARE
  role_row record;
  privilege_hit record;
  object_name text;
BEGIN
  FOREACH object_name IN ARRAY ARRAY[
    'n6_ai_shared_signal_projection',
    'n6_ai_context_snapshot',
    'n6_ai_decision_run',
    'n6_ai_decision',
    'n6_ai_daily_summary',
    'n6_ai_strategy_evaluation'
  ]
  LOOP
    IF pg_catalog.to_regclass('public.' || object_name) IS NOT NULL THEN
      RAISE EXCEPTION '055 target relation already exists: %', object_name;
    END IF;
  END LOOP;

  FOR role_row IN
    SELECT required.rolname AS required_role_name,
           actual.oid,
           actual.rolcanlogin,
           actual.rolinherit,
           actual.rolsuper,
           actual.rolcreatedb,
           actual.rolcreaterole,
           actual.rolreplication,
           actual.rolbypassrls
    FROM (
      VALUES
        ('n6_ai_agent'::text),
        ('n6_btrack_web'::text),
        ('n6_virtual_executor'::text)
    ) required(rolname)
    LEFT JOIN pg_catalog.pg_roles actual ON actual.rolname = required.rolname
  LOOP
    IF role_row.oid IS NULL THEN
      RAISE EXCEPTION '055 required role missing: %', role_row.required_role_name;
    END IF;
    IF NOT role_row.rolcanlogin
       OR role_row.rolinherit
       OR role_row.rolsuper
       OR role_row.rolcreatedb
       OR role_row.rolcreaterole
       OR role_row.rolreplication
       OR role_row.rolbypassrls THEN
      RAISE EXCEPTION '055 role attributes rejected: %', role_row.required_role_name;
    END IF;

    SELECT n.nspname, c.relname, requested.privilege_name
      INTO privilege_hit
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN (
      VALUES ('SELECT'::text), ('INSERT'::text), ('UPDATE'::text),
             ('DELETE'::text), ('TRUNCATE'::text), ('REFERENCES'::text),
             ('TRIGGER'::text)
    ) requested(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND pg_catalog.has_table_privilege(
            role_row.oid, c.oid, requested.privilege_name
          )
    ORDER BY c.relname, requested.privilege_name
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION '055 direct relation privilege rejected: role=% relation=%.% privilege=%',
        role_row.required_role_name, privilege_hit.nspname,
        privilege_hit.relname, privilege_hit.privilege_name;
    END IF;

    SELECT n.nspname, c.relname, requested.privilege_name
      INTO privilege_hit
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN (
      VALUES ('USAGE'::text), ('SELECT'::text), ('UPDATE'::text)
    ) requested(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind = 'S'
      AND pg_catalog.has_sequence_privilege(
            role_row.oid, c.oid, requested.privilege_name
          )
    ORDER BY c.relname, requested.privilege_name
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION '055 direct sequence privilege rejected: role=% sequence=%.% privilege=%',
        role_row.required_role_name, privilege_hit.nspname,
        privilege_hit.relname, privilege_hit.privilege_name;
    END IF;
  END LOOP;

  IF pg_catalog.to_regclass('public.n6_virtual_trade_proposal') IS NULL
     OR pg_catalog.to_regclass('public.n6_virtual_position_lot') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_user') IS NULL
     OR pg_catalog.to_regclass('public.n6_strategy') IS NULL THEN
    RAISE EXCEPTION '055 prerequisite N6 relations are missing';
  END IF;
END;
$preflight$;

CREATE TABLE public.n6_ai_shared_signal_projection (
  source_signal_projection_id BIGINT PRIMARY KEY
    REFERENCES public.user_signal_projection(user_signal_projection_id),
  user_projection_run_id TEXT NOT NULL
    REFERENCES public.user_projection_run(user_projection_run_id),
  source_event_id TEXT NOT NULL,
  source_event_time TIMESTAMPTZ NOT NULL,
  source_outbox_id BIGINT,
  source_action_event_id TEXT NOT NULL,
  source_action_run_id TEXT NOT NULL,
  for_trade_date DATE NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL,
  target_price NUMERIC,
  current_price NUMERIC,
  trigger_price NUMERIC,
  action_price NUMERIC,
  expected_return_pct NUMERIC,
  board_identity_key TEXT,
  board_code TEXT,
  board_name TEXT,
  action_state TEXT,
  action_mark TEXT,
  condition_key TEXT,
  original_condition_key TEXT,
  reason_fields_json JSONB NOT NULL,
  source_payload_hash TEXT NOT NULL,
  shared_status TEXT NOT NULL DEFAULT 'active'
    CHECK (shared_status IN ('active', 'superseded', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  CHECK (source_event_id <> ''),
  CHECK (source_action_event_id <> ''),
  CHECK (source_action_run_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (code <> ''),
  CHECK (name <> ''),
  CHECK (jsonb_typeof(reason_fields_json) = 'object'),
  CHECK (source_payload_hash ~ '^[0-9a-f]{64}$'),
  UNIQUE (source_event_id, identity_key, direction)
);

CREATE INDEX idx_055_n6_ai_shared_signal_date_asset
ON public.n6_ai_shared_signal_projection(
  for_trade_date, asset_kind, direction, source_signal_projection_id DESC
);

CREATE OR REPLACE FUNCTION public.n6_ai_shared_signal_projection_capture()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  trade_date_text text;
  event_time_text text;
  safe_reason_fields jsonb;
BEGIN
  trade_date_text := COALESCE(
    NEW.display_payload_json->>'for_trade_date',
    NEW.source_payload_json->>'trade_date'
  );
  event_time_text := NEW.source_payload_json->>'event_time';
  IF NEW.projection_status <> 'visible'
     OR trade_date_text !~ '^[0-9]{8}$'
     OR NOT pg_catalog.pg_input_is_valid(
              event_time_text, 'timestamp with time zone'
            )
     OR NEW.asset_kind NOT IN ('stock', 'index', 'board')
     OR NEW.direction NOT IN ('buy', 'sell')
     OR NEW.identity_key = ''
     OR NEW.code = ''
     OR NEW.name = '' THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.user_projection_run projection_run
    WHERE projection_run.user_projection_run_id =
          NEW.user_projection_run_id
      AND projection_run.source_layer = 'N5_action'
      AND projection_run.status = 'passed'
      AND projection_run.quality_summary_json
            ->>'b_track_signal_projection' = 'passed'
  ) THEN
    RETURN NEW;
  END IF;

  safe_reason_fields := pg_catalog.jsonb_strip_nulls(
    pg_catalog.jsonb_build_object(
      'condition_key', NEW.condition_key,
      'action_state', NEW.action_state,
      'action_mark', NEW.action_mark,
      'primary_trigger_period',
        NEW.display_payload_json->>'primary_trigger_period',
      'all_trigger_periods',
        NEW.display_payload_json->>'all_trigger_periods',
      'buy_expected_return_pct',
        NEW.display_payload_json->>'buy_expected_return_pct',
      'sell_expected_return_pct',
        NEW.display_payload_json->>'sell_expected_return_pct',
      'score', NEW.display_payload_json->>'score',
      'pe_core', NEW.display_payload_json->>'pe_core'
    )
  );

  INSERT INTO public.n6_ai_shared_signal_projection (
    source_signal_projection_id, user_projection_run_id,
    source_event_id, source_event_time, source_outbox_id,
    source_action_event_id,
    source_action_run_id, for_trade_date, asset_kind, identity_key,
    code, name, direction, signal_type, target_price, current_price,
    trigger_price, action_price, expected_return_pct,
    board_identity_key, board_code, board_name,
    action_state, action_mark, condition_key, original_condition_key,
    reason_fields_json, source_payload_hash
  )
  VALUES (
    NEW.user_signal_projection_id, NEW.user_projection_run_id,
    NEW.source_event_id, event_time_text::timestamptz,
    NEW.source_outbox_id, NEW.source_action_event_id,
    NEW.source_action_run_id,
    pg_catalog.to_date(trade_date_text, 'YYYYMMDD'),
    NEW.asset_kind, NEW.identity_key, NEW.code, NEW.name, NEW.direction,
    NEW.signal_type, NEW.target_price, NEW.current_price,
    CASE
      WHEN NEW.display_payload_json->>'trigger_price'
             ~ '^[0-9]+([.][0-9]+)?$'
        THEN (NEW.display_payload_json->>'trigger_price')::numeric
      ELSE NULL
    END,
    CASE
      WHEN NEW.display_payload_json->>'action_price'
             ~ '^[0-9]+([.][0-9]+)?$'
        THEN (NEW.display_payload_json->>'action_price')::numeric
      ELSE NULL
    END,
    NEW.expected_return_pct, NEW.board_identity_key, NEW.board_code,
    NEW.board_name, NEW.action_state, NEW.action_mark,
    NEW.condition_key, NEW.original_condition_key, safe_reason_fields,
    pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(
          pg_catalog.jsonb_build_object(
            'source_event_id', NEW.source_event_id,
            'source_action_run_id', NEW.source_action_run_id,
            'for_trade_date', trade_date_text,
            'asset_kind', NEW.asset_kind,
            'identity_key', NEW.identity_key,
            'direction', NEW.direction,
            'signal_type', NEW.signal_type,
            'reason_fields', safe_reason_fields
          )::text,
          'UTF8'
        )
      ),
      'hex'
    )
  )
  ON CONFLICT (source_event_id, identity_key, direction) DO NOTHING;
  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.n6_ai_shared_signal_projection_capture()
  FROM PUBLIC;

CREATE TRIGGER trg_055_n6_ai_shared_signal_projection_capture
AFTER INSERT ON public.user_signal_projection
FOR EACH ROW
EXECUTE FUNCTION public.n6_ai_shared_signal_projection_capture();

INSERT INTO public.n6_ai_shared_signal_projection (
  source_signal_projection_id, user_projection_run_id,
  source_event_id, source_event_time, source_outbox_id,
  source_action_event_id,
  source_action_run_id, for_trade_date, asset_kind, identity_key,
  code, name, direction, signal_type, target_price, current_price,
  trigger_price, action_price, expected_return_pct,
  board_identity_key, board_code, board_name,
  action_state, action_mark, condition_key, original_condition_key,
  reason_fields_json, source_payload_hash
)
SELECT DISTINCT ON (
         projection.source_event_id,
         projection.identity_key,
         projection.direction
       )
       projection.user_signal_projection_id,
       projection.user_projection_run_id,
       projection.source_event_id,
       (projection.source_payload_json->>'event_time')::timestamptz,
       projection.source_outbox_id,
       projection.source_action_event_id,
       projection.source_action_run_id,
       pg_catalog.to_date(
         COALESCE(
           projection.display_payload_json->>'for_trade_date',
           projection.source_payload_json->>'trade_date'
         ),
         'YYYYMMDD'
       ),
       projection.asset_kind,
       projection.identity_key,
       projection.code,
       projection.name,
       projection.direction,
       projection.signal_type,
       projection.target_price,
       projection.current_price,
       CASE
         WHEN projection.display_payload_json->>'trigger_price'
                ~ '^[0-9]+([.][0-9]+)?$'
           THEN (projection.display_payload_json->>'trigger_price')::numeric
         ELSE NULL
       END,
       CASE
         WHEN projection.display_payload_json->>'action_price'
                ~ '^[0-9]+([.][0-9]+)?$'
           THEN (projection.display_payload_json->>'action_price')::numeric
         ELSE NULL
       END,
       projection.expected_return_pct,
       projection.board_identity_key,
       projection.board_code,
       projection.board_name,
       projection.action_state,
       projection.action_mark,
       projection.condition_key,
       projection.original_condition_key,
       safe.reason_fields,
       pg_catalog.encode(
         pg_catalog.sha256(
           pg_catalog.convert_to(
             pg_catalog.jsonb_build_object(
               'source_event_id', projection.source_event_id,
               'source_action_run_id', projection.source_action_run_id,
               'for_trade_date',
                 COALESCE(
                   projection.display_payload_json->>'for_trade_date',
                   projection.source_payload_json->>'trade_date'
                 ),
               'asset_kind', projection.asset_kind,
               'identity_key', projection.identity_key,
               'direction', projection.direction,
               'signal_type', projection.signal_type,
               'reason_fields', safe.reason_fields
             )::text,
             'UTF8'
           )
         ),
         'hex'
       )
FROM public.user_signal_projection projection
JOIN public.user_projection_run projection_run
  ON projection_run.user_projection_run_id =
       projection.user_projection_run_id
 AND projection_run.source_layer = 'N5_action'
 AND projection_run.status = 'passed'
 AND projection_run.quality_summary_json
       ->>'b_track_signal_projection' = 'passed'
CROSS JOIN LATERAL (
  SELECT pg_catalog.jsonb_strip_nulls(
           pg_catalog.jsonb_build_object(
             'condition_key', projection.condition_key,
             'action_state', projection.action_state,
             'action_mark', projection.action_mark,
             'primary_trigger_period',
               projection.display_payload_json->>'primary_trigger_period',
             'all_trigger_periods',
               projection.display_payload_json->>'all_trigger_periods',
             'buy_expected_return_pct',
               projection.display_payload_json->>'buy_expected_return_pct',
             'sell_expected_return_pct',
               projection.display_payload_json->>'sell_expected_return_pct',
             'score', projection.display_payload_json->>'score',
             'pe_core', projection.display_payload_json->>'pe_core'
           )
         ) AS reason_fields
) safe
WHERE projection.projection_status = 'visible'
  AND COALESCE(
        projection.display_payload_json->>'for_trade_date',
        projection.source_payload_json->>'trade_date'
      ) ~ '^[0-9]{8}$'
  AND pg_catalog.pg_input_is_valid(
        projection.source_payload_json->>'event_time',
        'timestamp with time zone'
      )
  AND projection.asset_kind IN ('stock', 'index', 'board')
  AND projection.direction IN ('buy', 'sell')
ORDER BY projection.source_event_id, projection.identity_key,
         projection.direction, projection.user_signal_projection_id;

CREATE TABLE public.n6_ai_context_snapshot (
  ai_context_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user' CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  virtual_account_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_account(virtual_account_id),
  for_trade_date DATE NOT NULL,
  run_bucket TEXT NOT NULL CHECK (
    run_bucket ~ '^(daily:[0-9]{8}|[0-9]{8}T[0-9]{4}[+-][0-9]{4})$'
  ),
  source_projection_run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_signal_projection_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_virtual_position_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_account_snapshot_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  context_payload_json JSONB NOT NULL,
  context_payload_hash TEXT NOT NULL,
  decision_input_hash TEXT NOT NULL,
  context_hash_algorithm TEXT NOT NULL DEFAULT 'sha256',
  context_status TEXT NOT NULL DEFAULT 'frozen'
    CHECK (context_status IN ('frozen', 'superseded', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(source_projection_run_ids_json) = 'array'),
  CHECK (jsonb_typeof(source_signal_projection_ids_json) = 'array'),
  CHECK (jsonb_typeof(source_virtual_position_ids_json) = 'array'),
  CHECK (jsonb_typeof(source_account_snapshot_ids_json) = 'array'),
  CHECK (jsonb_typeof(context_payload_json) = 'object'),
  CHECK (context_payload_hash ~ '^[0-9a-f]{64}$'),
  CHECK (decision_input_hash ~ '^[0-9a-f]{64}$'),
  CHECK (context_hash_algorithm = 'sha256')
);

CREATE INDEX idx_055_n6_ai_context_user_date
ON public.n6_ai_context_snapshot(ai_user_id, for_trade_date, ai_context_snapshot_id DESC);
CREATE UNIQUE INDEX idx_055_n6_ai_context_user_bucket
ON public.n6_ai_context_snapshot(ai_user_id, run_bucket);

CREATE TABLE public.n6_ai_decision_run (
  ai_decision_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user' CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  ai_context_snapshot_id BIGINT NOT NULL
    REFERENCES public.n6_ai_context_snapshot(ai_context_snapshot_id),
  run_bucket TEXT NOT NULL,
  run_mode TEXT NOT NULL CHECK (run_mode IN ('shadow', 'autonomous_canary')),
  model_adapter TEXT NOT NULL CHECK (model_adapter <> ''),
  model_version TEXT NOT NULL CHECK (model_version <> ''),
  strategy_version TEXT NOT NULL CHECK (strategy_version <> ''),
  knowledge_bundle_version TEXT NOT NULL CHECK (knowledge_bundle_version <> ''),
  knowledge_bundle_hash TEXT NOT NULL CHECK (knowledge_bundle_hash ~ '^[0-9a-f]{64}$'),
  input_payload_hash TEXT NOT NULL CHECK (input_payload_hash ~ '^[0-9a-f]{64}$'),
  output_payload_hash TEXT NOT NULL CHECK (output_payload_hash ~ '^[0-9a-f]{64}$'),
  run_status TEXT NOT NULL
    CHECK (run_status IN ('started', 'recorded', 'rejected', 'failed')),
  failure_reason TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_055_n6_ai_decision_run_user_time
ON public.n6_ai_decision_run(ai_user_id, created_at DESC);

CREATE TABLE public.n6_ai_decision (
  ai_decision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_decision_run_id BIGINT NOT NULL
    REFERENCES public.n6_ai_decision_run(ai_decision_run_id),
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user' CHECK (principal_type = 'ai_user'),
  decision_type TEXT NOT NULL CHECK (decision_type IN ('buy', 'sell', 'hold')),
  identity_key TEXT,
  source_signal_projection_id BIGINT
    REFERENCES public.n6_ai_shared_signal_projection(
      source_signal_projection_id
    ),
  source_virtual_position_id BIGINT
    REFERENCES public.n6_virtual_position(virtual_position_id),
  confidence NUMERIC(8,7) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  reason_summary TEXT NOT NULL CHECK (btrim(reason_summary) <> ''),
  evidence_json JSONB NOT NULL,
  counter_evidence_json JSONB NOT NULL,
  risk_assessment_json JSONB NOT NULL,
  server_risk_allowed BOOLEAN NOT NULL,
  server_risk_reason TEXT NOT NULL CHECK (btrim(server_risk_reason) <> ''),
  server_risk_policy_version TEXT NOT NULL
    DEFAULT 'n6_ai_agent_conservative_risk_v1'
    CHECK (server_risk_policy_version = 'n6_ai_agent_conservative_risk_v1'),
  strategy_candidate_notes TEXT,
  decision_status TEXT NOT NULL DEFAULT 'shadow_recorded'
    CHECK (decision_status IN (
      'shadow_recorded', 'held', 'proposal_confirmed', 'rejected', 'failed'
    )),
  proposal_id BIGINT REFERENCES public.n6_virtual_trade_proposal(proposal_id),
  idempotency_key TEXT NOT NULL UNIQUE
    CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(evidence_json) = 'array'),
  CHECK (jsonb_typeof(counter_evidence_json) = 'array'),
  CHECK (jsonb_typeof(risk_assessment_json) = 'object'),
  CHECK (
    (decision_type = 'hold' AND proposal_id IS NULL)
    OR (decision_type IN ('buy', 'sell') AND identity_key ~ '^stock:(SH|SZ):[0-9]{6}$')
  ),
  CHECK (decision_type <> 'buy' OR source_signal_projection_id IS NOT NULL),
  CHECK (
    decision_type <> 'sell'
    OR source_signal_projection_id IS NOT NULL
    OR source_virtual_position_id IS NOT NULL
  )
);

CREATE INDEX idx_055_n6_ai_decision_user_time
ON public.n6_ai_decision(ai_user_id, created_at DESC);
CREATE INDEX idx_055_n6_ai_decision_identity
ON public.n6_ai_decision(identity_key, created_at DESC)
WHERE identity_key IS NOT NULL;

CREATE TABLE public.n6_ai_daily_summary (
  ai_daily_summary_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user' CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  strategy_version TEXT NOT NULL CHECK (strategy_version <> ''),
  strategy_hash TEXT NOT NULL CHECK (strategy_hash ~ '^[0-9a-f]{64}$'),
  knowledge_bundle_version TEXT NOT NULL
    CHECK (knowledge_bundle_version <> ''),
  knowledge_bundle_hash TEXT NOT NULL
    CHECK (knowledge_bundle_hash ~ '^[0-9a-f]{64}$'),
  for_trade_date DATE NOT NULL,
  virtual_account_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_account(virtual_account_id),
  total_asset NUMERIC(24,4) NOT NULL CHECK (total_asset >= 0),
  available_cash NUMERIC(24,4) NOT NULL CHECK (available_cash >= 0),
  market_value NUMERIC(24,4) NOT NULL CHECK (market_value >= 0),
  daily_net_pnl NUMERIC(24,4) NOT NULL,
  net_return_pct NUMERIC(18,8) NOT NULL,
  max_drawdown_pct NUMERIC(18,8) NOT NULL CHECK (max_drawdown_pct >= 0),
  turnover_pct NUMERIC(18,8) NOT NULL CHECK (turnover_pct >= 0),
  risk_adjusted_score NUMERIC(18,8) NOT NULL,
  decision_count INTEGER NOT NULL DEFAULT 0 CHECK (decision_count >= 0),
  buy_trade_count INTEGER NOT NULL DEFAULT 0 CHECK (buy_trade_count >= 0),
  sell_trade_count INTEGER NOT NULL DEFAULT 0 CHECK (sell_trade_count >= 0),
  trade_review_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  success_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  failure_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  next_day_watch_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_text TEXT NOT NULL CHECK (btrim(summary_text) <> ''),
  account_snapshot_hash TEXT NOT NULL CHECK (account_snapshot_hash ~ '^[0-9a-f]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(trade_review_json) = 'array'),
  CHECK (jsonb_typeof(success_reasons_json) = 'array'),
  CHECK (jsonb_typeof(failure_reasons_json) = 'array'),
  CHECK (jsonb_typeof(next_day_watch_json) = 'array'),
  UNIQUE (ai_user_id, for_trade_date)
);

CREATE TABLE public.n6_ai_strategy_evaluation (
  ai_strategy_evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  candidate_strategy_version TEXT NOT NULL CHECK (candidate_strategy_version <> ''),
  candidate_strategy_hash TEXT NOT NULL CHECK (candidate_strategy_hash ~ '^[0-9a-f]{64}$'),
  candidate_payload_json JSONB NOT NULL,
  replay_start_date DATE,
  replay_end_date DATE,
  replay_metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  shadow_trading_days INTEGER NOT NULL DEFAULT 0 CHECK (shadow_trading_days >= 0),
  shadow_metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  net_return_pct NUMERIC(18,8),
  max_drawdown_pct NUMERIC(18,8),
  turnover_pct NUMERIC(18,8),
  risk_adjusted_score NUMERIC(18,8),
  promotion_status TEXT NOT NULL DEFAULT 'candidate'
    CHECK (promotion_status IN (
      'candidate', 'replay_passed', 'shadow', 'eligible_for_review',
      'approved', 'rejected', 'archived'
    )),
  reviewed_by_user_id BIGINT REFERENCES public.user_account(user_id),
  reviewed_at TIMESTAMPTZ,
  review_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  CHECK (jsonb_typeof(candidate_payload_json) = 'object'),
  CHECK (jsonb_typeof(replay_metrics_json) = 'object'),
  CHECK (jsonb_typeof(shadow_metrics_json) = 'object'),
  CHECK (replay_end_date IS NULL OR replay_start_date IS NULL OR replay_end_date >= replay_start_date),
  CHECK (
    promotion_status NOT IN ('eligible_for_review', 'approved')
    OR shadow_trading_days >= 10
  ),
  CHECK (
    promotion_status <> 'approved'
    OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)
  ),
  UNIQUE (ai_user_id, candidate_strategy_hash)
);

DO $constraint_upgrade$
DECLARE
  constraint_name text;
  constraint_count integer;
BEGIN
  SELECT min(c.conname), count(*)
    INTO constraint_name, constraint_count
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = 'public.n6_virtual_trade_proposal'::regclass
    AND c.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%principal_type%admin%human_user%'
    AND pg_catalog.pg_get_constraintdef(c.oid) NOT LIKE '%ai_user%';
  IF constraint_count <> 1 THEN
    RAISE EXCEPTION '055 expected one legacy proposal principal-type constraint, found %',
      constraint_count;
  END IF;
  EXECUTE pg_catalog.format(
    'ALTER TABLE public.n6_virtual_trade_proposal DROP CONSTRAINT %I',
    constraint_name
  );

  SELECT min(c.conname), count(*)
    INTO constraint_name, constraint_count
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = 'public.n6_virtual_trade_proposal'::regclass
    AND c.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%source_type%signal%manual_position%stop_loss%'
    AND pg_catalog.pg_get_constraintdef(c.oid) NOT LIKE '%source_signal_projection_id%';
  IF constraint_count <> 1 THEN
    RAISE EXCEPTION '055 expected one legacy proposal source-type constraint, found %',
      constraint_count;
  END IF;
  EXECUTE pg_catalog.format(
    'ALTER TABLE public.n6_virtual_trade_proposal DROP CONSTRAINT %I',
    constraint_name
  );

  SELECT min(c.conname), count(*)
    INTO constraint_name, constraint_count
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = 'public.n6_virtual_trade_proposal'::regclass
    AND c.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%source_type = ''signal''%'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%source_signal_projection_id%';
  IF constraint_count <> 1 THEN
    RAISE EXCEPTION '055 expected one legacy signal-source constraint, found %',
      constraint_count;
  END IF;
  EXECUTE pg_catalog.format(
    'ALTER TABLE public.n6_virtual_trade_proposal DROP CONSTRAINT %I',
    constraint_name
  );

  SELECT min(c.conname), count(*)
    INTO constraint_name, constraint_count
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = 'public.n6_virtual_trade_proposal'::regclass
    AND c.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%manual_position%stop_loss%'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%source_virtual_position_id%';
  IF constraint_count <> 1 THEN
    RAISE EXCEPTION '055 expected one legacy position-source constraint, found %',
      constraint_count;
  END IF;
  EXECUTE pg_catalog.format(
    'ALTER TABLE public.n6_virtual_trade_proposal DROP CONSTRAINT %I',
    constraint_name
  );

  SELECT min(c.conname), count(*)
    INTO constraint_name, constraint_count
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = 'public.n6_virtual_position_lot'::regclass
    AND c.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(c.oid) LIKE '%principal_type%admin%human_user%'
    AND pg_catalog.pg_get_constraintdef(c.oid) NOT LIKE '%ai_user%';
  IF constraint_count <> 1 THEN
    RAISE EXCEPTION '055 expected one legacy lot principal-type constraint, found %',
      constraint_count;
  END IF;
  EXECUTE pg_catalog.format(
    'ALTER TABLE public.n6_virtual_position_lot DROP CONSTRAINT %I',
    constraint_name
  );
END;
$constraint_upgrade$;

ALTER TABLE public.n6_virtual_trade_proposal
  ALTER COLUMN user_id DROP NOT NULL,
  ADD COLUMN actor_ai_user_id BIGINT REFERENCES public.n6_ai_user(ai_user_id),
  ADD COLUMN source_ai_decision_id BIGINT REFERENCES public.n6_ai_decision(ai_decision_id),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_principal_type_ck
    CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_actor_ck
    CHECK (
      (principal_type IN ('admin', 'human_user')
       AND user_id IS NOT NULL
       AND actor_ai_user_id IS NULL
       AND source_ai_decision_id IS NULL)
      OR
      (principal_type = 'ai_user'
       AND user_id IS NULL
       AND actor_ai_user_id IS NOT NULL
       AND (
         (source_type IN ('signal', 'ai_risk')
          AND source_ai_decision_id IS NOT NULL)
         OR
         (source_type = 'stop_loss'
          AND source_ai_decision_id IS NULL)
       ))
    ),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_source_type_ck
    CHECK (source_type IN ('signal', 'manual_position', 'stop_loss', 'ai_risk')),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_signal_source_ck
    CHECK (
      (source_type = 'signal' AND source_signal_projection_id IS NOT NULL)
      OR (source_type <> 'signal' AND source_signal_projection_id IS NULL)
    ),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_position_source_ck
    CHECK (
      (source_type IN ('manual_position', 'stop_loss', 'ai_risk')
       AND source_virtual_position_id IS NOT NULL)
      OR source_type = 'signal'
    );

ALTER TABLE public.n6_virtual_position_lot
  ADD CONSTRAINT n6_virtual_position_lot_055_principal_type_ck
    CHECK (principal_type IN ('admin', 'human_user', 'ai_user'));

CREATE UNIQUE INDEX idx_055_n6_virtual_trade_proposal_ai_decision
ON public.n6_virtual_trade_proposal(source_ai_decision_id)
WHERE source_ai_decision_id IS NOT NULL;

-- Function definitions and the exact execute-grant matrix follow below.


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
  SELECT pg_catalog.greatest(
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
      THEN pg_catalog.greatest(
        0, (peak_asset - total_asset) / peak_asset * 100
      )
    ELSE 0
  END;
  max_drawdown := pg_catalog.greatest(prior_drawdown, current_drawdown);
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

CREATE OR REPLACE FUNCTION public.n6_ai_agent_strategy_evaluation_record(
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  actor record;
  unknown_key text;
  existing_evaluation_id bigint;
  created_evaluation_id bigint;
  replay_start date;
  replay_end date;
  shadow_days integer;
  net_return numeric;
  max_drawdown numeric;
  turnover numeric;
  score numeric;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_payload IS NULL
     OR pg_catalog.jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_strategy_evaluation_request'
    );
  END IF;
  SELECT key
    INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN (
    'candidate_strategy_version', 'candidate_strategy_hash',
    'candidate_payload', 'replay_start_date', 'replay_end_date',
    'replay_metrics', 'shadow_trading_days', 'shadow_metrics',
    'net_return_pct', 'max_drawdown_pct', 'turnover_pct',
    'risk_adjusted_score'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR COALESCE(p_payload->>'candidate_strategy_version', '') = ''
     OR pg_catalog.length(
          p_payload->>'candidate_strategy_version'
        ) > 200
     OR COALESCE(p_payload->>'candidate_strategy_hash', '') !~
          '^[0-9a-f]{64}$'
     OR pg_catalog.jsonb_typeof(p_payload->'candidate_payload') <>
          'object'
     OR pg_catalog.jsonb_typeof(p_payload->'replay_metrics') <>
          'object'
     OR pg_catalog.jsonb_typeof(p_payload->'shadow_metrics') <>
          'object'
     OR p_payload ?| ARRAY[
       'promotion_status', 'reviewed_by_user_id', 'reviewed_at',
       'price', 'quantity', 'account', 'principal', 'user_id',
       'prompt', 'reasoning'
     ] THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_candidate_contract_rejected'
    );
  END IF;
  BEGIN
    replay_start := NULLIF(p_payload->>'replay_start_date', '')::date;
    replay_end := NULLIF(p_payload->>'replay_end_date', '')::date;
    shadow_days := (p_payload->>'shadow_trading_days')::integer;
    net_return := NULLIF(p_payload->>'net_return_pct', '')::numeric;
    max_drawdown := NULLIF(p_payload->>'max_drawdown_pct', '')::numeric;
    turnover := NULLIF(p_payload->>'turnover_pct', '')::numeric;
    score := NULLIF(p_payload->>'risk_adjusted_score', '')::numeric;
  EXCEPTION
    WHEN OTHERS THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'strategy_candidate_value_rejected'
      );
  END;
  IF shadow_days < 0
     OR (replay_start IS NULL) <> (replay_end IS NULL)
     OR (replay_start IS NOT NULL AND replay_end < replay_start)
     OR (max_drawdown IS NOT NULL AND max_drawdown < 0)
     OR (turnover IS NOT NULL AND turnover < 0)
     OR (
       score IS NOT NULL
       AND (
         net_return IS NULL
         OR max_drawdown IS NULL
         OR turnover IS NULL
         OR pg_catalog.round(score, 6) <>
              pg_catalog.round(
                net_return - 1.5 * max_drawdown - 0.02 * turnover,
                6
              )
       )
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_candidate_metrics_rejected'
    );
  END IF;

  SELECT min(ai.ai_user_id) AS ai_user_id,
         count(*) AS authority_count
    INTO actor
  FROM public.n6_ai_user ai
  JOIN public.n6_principal principal
    ON principal.principal_id = ai.principal_id
   AND principal.principal_type = 'ai_user'
   AND principal.principal_status = 'active'
   AND principal.owner_user_id IS NULL
  WHERE ai.status IN ('sandbox_only', 'active');
  IF actor.authority_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_candidate_authority_rejected'
    );
  END IF;
  SELECT evaluation.ai_strategy_evaluation_id
    INTO existing_evaluation_id
  FROM public.n6_ai_strategy_evaluation evaluation
  WHERE evaluation.ai_user_id = actor.ai_user_id
    AND evaluation.candidate_strategy_hash =
          p_payload->>'candidate_strategy_hash';
  IF existing_evaluation_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'already_recorded',
      'strategy_evaluation_id', existing_evaluation_id
    );
  END IF;

  INSERT INTO public.n6_ai_strategy_evaluation (
    ai_user_id, candidate_strategy_version, candidate_strategy_hash,
    candidate_payload_json, replay_start_date, replay_end_date,
    replay_metrics_json, shadow_trading_days, shadow_metrics_json,
    net_return_pct, max_drawdown_pct, turnover_pct,
    risk_adjusted_score, promotion_status
  )
  VALUES (
    actor.ai_user_id, p_payload->>'candidate_strategy_version',
    p_payload->>'candidate_strategy_hash',
    p_payload->'candidate_payload', replay_start, replay_end,
    p_payload->'replay_metrics', shadow_days,
    p_payload->'shadow_metrics', net_return, max_drawdown,
    turnover, score, 'candidate'
  )
  RETURNING ai_strategy_evaluation_id INTO created_evaluation_id;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'strategy_candidate_recorded',
    'strategy_evaluation_id', created_evaluation_id,
    'promotion_status', 'candidate'
  );
END;
$function$;

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
    INTO target_decision_id, target_risk_allowed, target_risk_reason
  FROM public.n6_ai_decision decision
  WHERE decision.idempotency_key = target_idempotency_key;
  IF target_decision_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'already_recorded',
      'decision_id', target_decision_id,
      'server_risk_allowed', target_risk_allowed,
      'server_risk_reason', target_risk_reason
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

-- Final reviewed function contracts follow.

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
  SELECT pg_catalog.greatest(
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
      THEN pg_catalog.greatest(
        0, (peak_equity - current_equity) / peak_equity * 100
      )
    ELSE 0
  END;
  effective_drawdown :=
    pg_catalog.greatest(prior_drawdown, current_drawdown);
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

CREATE OR REPLACE FUNCTION public.n6_ai_agent_shadow_decision_record_bootstrap(
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
  decision_payload jsonb;
  decision_type text;
  identity_key text;
  signal_id bigint;
  position_id bigint;
  run_mode text;
  run_id bigint;
  decision_id bigint;
  ai_status text;
  unknown_key text;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_payload IS NULL
     OR jsonb_typeof(p_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'invalid_decision_envelope'
    );
  END IF;

  SELECT key INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(p_payload) key
  WHERE key NOT IN (
    'ai_context_snapshot_id', 'run_mode', 'model_adapter', 'model_version',
    'strategy_version', 'knowledge_bundle_hash', 'input_payload_hash',
    'output_payload_hash', 'decision'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR p_payload ?| ARRAY[
       'price', 'quantity', 'account', 'account_id', 'trade_date',
       'for_trade_date', 'principal', 'principal_id', 'user_id'
     ] THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'forbidden_decision_field'
    );
  END IF;

  decision_payload := p_payload->'decision';
  IF jsonb_typeof(decision_payload) <> 'object' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'invalid_decision_payload'
    );
  END IF;
  SELECT key INTO unknown_key
  FROM pg_catalog.jsonb_object_keys(decision_payload) key
  WHERE key NOT IN (
    'decision_type', 'identity_key', 'source_signal_projection_id',
    'source_virtual_position_id', 'confidence', 'reason_summary',
    'evidence', 'counter_evidence', 'risk_assessment',
    'strategy_candidate_notes'
  )
  LIMIT 1;
  IF unknown_key IS NOT NULL
     OR decision_payload ?| ARRAY[
       'price', 'quantity', 'account', 'account_id', 'trade_date',
       'for_trade_date', 'principal', 'principal_id', 'user_id'
     ] THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'forbidden_model_output_field'
    );
  END IF;

  BEGIN
    SELECT * INTO context_row
    FROM public.n6_ai_context_snapshot
    WHERE ai_context_snapshot_id =
          (p_payload->>'ai_context_snapshot_id')::bigint
      AND context_status = 'frozen'
    FOR SHARE;
  EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'invalid_context_reference'
    );
  END;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'context_not_found'
    );
  END IF;

  SELECT ai.status INTO ai_status
  FROM public.n6_ai_user ai
  JOIN public.n6_principal p
    ON p.principal_id = ai.principal_id
   AND p.principal_type = 'ai_user'
   AND p.principal_status = 'active'
  WHERE ai.ai_user_id = context_row.ai_user_id
    AND ai.principal_id = context_row.principal_id;
  run_mode := p_payload->>'run_mode';
  IF ai_status NOT IN ('sandbox_only', 'active')
     OR run_mode NOT IN ('shadow', 'autonomous_canary')
     OR (run_mode = 'autonomous_canary' AND ai_status <> 'active')
     OR COALESCE(p_payload->>'model_adapter', '') = ''
     OR COALESCE(p_payload->>'model_version', '') = ''
     OR COALESCE(p_payload->>'strategy_version', '') = ''
     OR COALESCE(p_payload->>'knowledge_bundle_hash', '') !~ '^[0-9a-f]{64}$'
     OR COALESCE(p_payload->>'input_payload_hash', '') !~ '^[0-9a-f]{64}$'
     OR COALESCE(p_payload->>'output_payload_hash', '') !~ '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'agent_run_not_authorized'
    );
  END IF;

  decision_type := decision_payload->>'decision_type';
  identity_key := NULLIF(decision_payload->>'identity_key', '');
  BEGIN
    signal_id := NULLIF(decision_payload->>'source_signal_projection_id', '')::bigint;
    position_id := NULLIF(decision_payload->>'source_virtual_position_id', '')::bigint;
  EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'invalid_source_reference'
    );
  END;
  IF decision_type NOT IN ('buy', 'sell', 'hold')
     OR jsonb_typeof(decision_payload->'evidence') <> 'array'
     OR jsonb_typeof(decision_payload->'counter_evidence') <> 'array'
     OR jsonb_typeof(decision_payload->'risk_assessment') <> 'object'
     OR COALESCE(decision_payload->>'reason_summary', '') = ''
     OR COALESCE(decision_payload->>'confidence', '') !~
          '^(0(\\.[0-9]+)?|1(\\.0+)?)$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'decision_contract_failed'
    );
  END IF;
  IF decision_type = 'buy'
     AND (
       signal_id IS NULL
       OR identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
       OR NOT context_row.source_signal_projection_ids_json
                @> pg_catalog.jsonb_build_array(signal_id)
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'buy_signal_not_in_context'
    );
  END IF;
  IF decision_type = 'sell'
     AND signal_id IS NULL
     AND (
       position_id IS NULL
       OR NOT context_row.source_virtual_position_ids_json
                @> pg_catalog.jsonb_build_array(position_id)
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'rejected', 'error', 'sell_position_not_in_context'
    );
  END IF;

  INSERT INTO public.n6_ai_decision_run (
    ai_user_id, principal_id, principal_type, strategy_id,
    ai_context_snapshot_id, run_mode, model_adapter, model_version,
    strategy_version, knowledge_bundle_hash, input_payload_hash,
    output_payload_hash, run_status, finished_at
  )
  VALUES (
    context_row.ai_user_id, context_row.principal_id, 'ai_user',
    context_row.strategy_id, context_row.ai_context_snapshot_id, run_mode,
    p_payload->>'model_adapter', p_payload->>'model_version',
    p_payload->>'strategy_version', p_payload->>'knowledge_bundle_hash',
    p_payload->>'input_payload_hash', p_payload->>'output_payload_hash',
    'recorded', pg_catalog.clock_timestamp()
  )
  RETURNING ai_decision_run_id INTO run_id;

  INSERT INTO public.n6_ai_decision (
    ai_decision_run_id, ai_user_id, principal_id, principal_type,
    decision_type, identity_key, source_signal_projection_id,
    source_virtual_position_id, confidence, reason_summary, evidence_json,
    counter_evidence_json, risk_assessment_json, strategy_candidate_notes,
    decision_status
  )
  VALUES (
    run_id, context_row.ai_user_id, context_row.principal_id, 'ai_user',
    decision_type, identity_key, signal_id, position_id,
    (decision_payload->>'confidence')::numeric,
    decision_payload->>'reason_summary', decision_payload->'evidence',
    decision_payload->'counter_evidence',
    decision_payload->'risk_assessment',
    NULLIF(decision_payload->>'strategy_candidate_notes', ''),
    CASE WHEN decision_type = 'hold' THEN 'held' ELSE 'shadow_recorded' END
  )
  RETURNING ai_decision_id INTO decision_id;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status',
    CASE WHEN run_mode = 'shadow' THEN 'shadow_recorded' ELSE 'decision_recorded' END,
    'ai_decision_run_id', run_id, 'ai_decision_id', decision_id,
    'proposal_created', false
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
  SELECT pg_catalog.greatest(
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
      THEN pg_catalog.greatest(
        0, (peak_equity - current_equity) / peak_equity * 100
      )
    ELSE 0
  END;
  latest_drawdown :=
    pg_catalog.greatest(latest_drawdown, current_drawdown);

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
    SELECT pg_catalog.greatest(
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
        THEN pg_catalog.greatest(
          0, (peak_equity - current_equity) / peak_equity * 100
        )
      ELSE 0
    END;
    latest_drawdown :=
      pg_catalog.greatest(latest_drawdown, current_drawdown);
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

CREATE OR REPLACE FUNCTION public.n6_btrack_ai_public_snapshot(
  p_session_token_hash text,
  p_decision_limit integer,
  p_trade_limit integer,
  p_summary_limit integer
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb;
  actor record;
  actor_count integer;
  positions jsonb;
  trades jsonb;
  decisions jsonb;
  summaries jsonb;
  position_market_value numeric(24,4);
  invalid_position_quote_count integer;
  latest_summary record;
  latest_run record;
  valuation_trade_date date;
  valuation_mode text;
  valuation_time timestamptz := pg_catalog.statement_timestamp();
  local_current_date date :=
    (pg_catalog.statement_timestamp() AT TIME ZONE 'Asia/Shanghai')::date;
  local_current_time time :=
    (pg_catalog.statement_timestamp() AT TIME ZONE 'Asia/Shanghai')::time;
BEGIN
  IF SESSION_USER NOT IN ('n6_btrack_web', 'n6_ai_agent')
     OR p_decision_limit IS NULL
     OR p_decision_limit < 1
     OR p_decision_limit > 200
     OR p_trade_limit IS NULL
     OR p_trade_limit < 1
     OR p_trade_limit > 200
     OR p_summary_limit IS NULL
     OR p_summary_limit < 1
     OR p_summary_limit > 200 THEN
    RETURN NULL;
  END IF;
  IF SESSION_USER = 'n6_btrack_web' THEN
    IF p_session_token_hash !~ '^[0-9a-f]{64}$' THEN
      RETURN NULL;
    END IF;
    authority :=
      public.n6_btrack_resolve_authority(p_session_token_hash);
    IF authority IS NULL
       OR authority->>'principal_status' <> 'active'
       OR authority->>'principal_type' NOT IN ('admin', 'human_user') THEN
      RETURN NULL;
    END IF;
  ELSIF p_session_token_hash <> pg_catalog.repeat('0', 64) THEN
    RETURN NULL;
  END IF;

  SELECT min(ai.ai_user_id) AS ai_user_id,
         min(ai.ai_name) AS ai_name,
         min(ai.status) AS ai_status,
         min(strategy.strategy_id) AS strategy_id,
         min(strategy.strategy_name) AS strategy_name,
         min(strategy.policy_version) AS strategy_version,
         min(strategy.policy_hash) AS strategy_hash,
         min(strategy.status) AS strategy_status,
         min(strategy.risk_labels::text)::text[] AS risk_labels,
         min(account.virtual_account_id) AS virtual_account_id,
         min(account.account_name) AS account_name,
         min(account.virtual_account_status) AS account_status,
         min(account.base_currency) AS currency,
         min(account.initial_cash) AS initial_cash,
         min(cash.cash_snapshot_id) AS cash_snapshot_id,
         min(cash.available_cash) AS available_cash,
         min(cash.frozen_cash) AS frozen_cash,
         min(cash.total_cash) AS total_cash,
         min(cash.snapshot_time) AS snapshot_time,
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
   AND strategy.visibility = 'public_leaderboard'
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
  IF actor_count = 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'contract_version', 'n6-ai-agent-public-v1',
      'profile', '{}'::jsonb,
      'account', '{}'::jsonb,
      'positions', '[]'::jsonb,
      'trades', '[]'::jsonb,
      'decisions', '[]'::jsonb,
      'daily_summaries', '[]'::jsonb,
      'performance', '{}'::jsonb,
      'strategy', '{}'::jsonb,
      'runtime', pg_catalog.jsonb_build_object(
        'run_mode', 'disabled',
        'run_status', 'not_registered'
      )
    );
  ELSIF actor_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false,
      'contract_version', 'n6-ai-agent-public-v1',
      'status', 'ai_public_authority_conflict'
    );
  END IF;

  IF local_current_time >= time '09:30:00'
     AND EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date =
             pg_catalog.to_char(local_current_date, 'YYYYMMDD')
         AND calendar.is_open = true
     ) THEN
    valuation_trade_date := local_current_date;
  ELSE
    SELECT pg_catalog.max(
             pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD')
           )
      INTO valuation_trade_date
    FROM public.common_trade_calendar calendar
    WHERE calendar.is_open = true
      AND calendar.trade_date <
            pg_catalog.to_char(local_current_date, 'YYYYMMDD');
  END IF;
  valuation_mode := CASE
    WHEN valuation_trade_date = local_current_date
         AND (
           local_current_time BETWEEN time '09:30:00' AND time '11:30:00'
           OR local_current_time BETWEEN time '13:00:00' AND time '15:00:00'
         )
      THEN 'fresh_120s'
    WHEN valuation_trade_date = local_current_date
         AND local_current_time > time '11:30:00'
         AND local_current_time < time '13:00:00'
      THEN 'midday_close'
    ELSE 'daily_close'
  END;

  SELECT COALESCE(
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'virtual_position_id', row.virtual_position_id,
               'identity_key', row.identity_key,
               'stock_code',
                 pg_catalog.split_part(row.identity_key, ':', 3),
               'display_name', row.display_name,
               'quantity', row.quantity,
               'available_quantity', row.available_quantity,
               'locked_quantity', row.locked_quantity,
               'average_cost', row.average_cost,
               'current_price', row.current_price,
               'market_value', row.market_value,
               'unrealized_pnl', row.unrealized_pnl,
               'unrealized_return_pct',
                 CASE
                   WHEN row.average_cost > 0
                        AND row.quantity > 0
                     THEN row.unrealized_pnl /
                          (row.average_cost * row.quantity) * 100
                   ELSE NULL
                 END,
               'quote_status',
                 CASE
                   WHEN row.quote_ready THEN 'passed'
                   ELSE 'not_ready'
                 END,
               'target_price', row.locked_target_price,
               'target_price_status', row.target_price_status,
               'stop_loss_price', row.stop_loss_price,
               'stop_loss_status', row.stop_loss_status,
               'holding_episode_no', row.holding_episode_no,
               'first_open_trade_date', row.first_open_trade_date,
               'updated_at',
                 COALESCE(row.quote_minute, row.updated_at)
             )
             ORDER BY row.identity_key
           ),
           '[]'::jsonb
         ),
         COALESCE(pg_catalog.sum(row.market_value), 0),
         count(*) FILTER (WHERE NOT row.quote_ready)::integer
    INTO positions, position_market_value,
         invalid_position_quote_count
  FROM (
    SELECT position.virtual_position_id,
           position.identity_key,
           identity_name.display_name,
           position.quantity,
           position.available_quantity,
           position.locked_quantity,
           position.average_cost,
           CASE
             WHEN quote_ready.value THEN quote.current_price
             ELSE NULL
           END AS current_price,
           CASE
             WHEN quote_ready.value
               THEN position.quantity * quote.current_price
             ELSE NULL
           END AS market_value,
           CASE
             WHEN quote_ready.value
               THEN position.quantity *
                    (quote.current_price - position.average_cost)
             ELSE NULL
           END AS unrealized_pnl,
           quote_ready.value AS quote_ready,
           quote.quality_status,
           quote.quote_minute,
           position.locked_target_price,
           position.target_price_status,
           position.stop_loss_price,
           position.stop_loss_status,
           position.holding_episode_no,
           position.first_open_trade_date,
           position.updated_at
    FROM public.n6_virtual_position position
    LEFT JOIN public.v_n6_virtual_quote_latest quote
      ON quote.identity_key = position.identity_key
    LEFT JOIN LATERAL (
      SELECT shared.name AS display_name
      FROM public.n6_ai_shared_signal_projection shared
      WHERE shared.identity_key = position.identity_key
        AND shared.shared_status = 'active'
      ORDER BY shared.for_trade_date DESC,
               shared.source_signal_projection_id DESC
      LIMIT 1
    ) identity_name ON true
    CROSS JOIN LATERAL (
      SELECT COALESCE((
        quote.quality_status = 'passed'
        AND quote.quality_reason = 'ok'
        AND quote.current_price > 0
        AND quote.current_price::text NOT IN (
              'NaN', 'Infinity', '-Infinity'
            )
        AND quote.quote_minute IS NOT NULL
        AND quote.fetched_at >= quote.quote_minute
        AND (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date =
              valuation_trade_date
        AND (
          (
            valuation_mode = 'fresh_120s'
            AND quote.quote_minute <= valuation_time
            AND quote.quote_minute >=
                  valuation_time - interval '120 seconds'
            AND quote.fetched_at >=
                  valuation_time - interval '120 seconds'
          )
          OR (
            valuation_mode = 'midday_close'
            AND (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time
                  BETWEEN time '11:28:00' AND time '11:31:00'
          )
          OR (
            valuation_mode = 'daily_close'
            AND (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time
                  BETWEEN time '14:55:00' AND time '15:05:00'
          )
        )
      ), false) AS value
    ) quote_ready
    WHERE position.virtual_account_id = actor.virtual_account_id
      AND position.principal_type = 'ai_user'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
    ORDER BY position.identity_key
    LIMIT 200
  ) row;
  IF invalid_position_quote_count > 0 THEN
    position_market_value := NULL;
  END IF;

  SELECT COALESCE(
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'virtual_trade_id', row.virtual_trade_id,
               'ai_decision_id', row.ai_decision_id,
               'trade_time', row.trade_time,
               'identity_key', row.identity_key,
               'display_name', row.display_name,
               'trade_side', row.trade_side,
               'filled_quantity', row.filled_quantity,
               'filled_price', row.filled_price,
               'gross_amount', row.gross_amount,
               'total_fee_amount', row.total_fee_amount,
               'net_amount', row.net_amount,
               'trade_status', row.trade_status,
               'reason_summary', row.reason_summary
             )
             ORDER BY row.trade_time DESC, row.virtual_trade_id DESC
           ),
           '[]'::jsonb
         )
    INTO trades
  FROM (
    SELECT trade.virtual_trade_id,
           decision.ai_decision_id,
           trade.trade_time,
           trade.identity_key,
           identity_name.display_name,
           trade.trade_side,
           trade.filled_quantity,
           trade.filled_price,
           trade.gross_amount,
           trade.total_fee_amount,
           trade.net_amount,
           trade.trade_status,
           decision.reason_summary
    FROM public.n6_virtual_trade trade
    LEFT JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.executed_virtual_trade_id =
           trade.virtual_trade_id
     AND proposal.principal_type = 'ai_user'
    LEFT JOIN public.n6_ai_decision decision
      ON decision.ai_decision_id =
           proposal.source_ai_decision_id
    LEFT JOIN LATERAL (
      SELECT shared.name AS display_name
      FROM public.n6_ai_shared_signal_projection shared
      WHERE shared.identity_key = trade.identity_key
        AND shared.shared_status = 'active'
      ORDER BY shared.for_trade_date DESC,
               shared.source_signal_projection_id DESC
      LIMIT 1
    ) identity_name ON true
    WHERE trade.virtual_account_id = actor.virtual_account_id
      AND trade.principal_type = 'ai_user'
    ORDER BY trade.trade_time DESC, trade.virtual_trade_id DESC
    LIMIT p_trade_limit
  ) row;

  SELECT COALESCE(
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'ai_decision_id', row.ai_decision_id,
               'ai_decision_run_id', row.ai_decision_run_id,
               'ai_context_snapshot_id', row.ai_context_snapshot_id,
               'for_trade_date', row.for_trade_date,
               'created_at', row.created_at,
               'decision_type', row.decision_type,
               'identity_key', row.identity_key,
               'display_name', row.display_name,
               'confidence', row.confidence,
               'reason_summary', row.reason_summary,
               'evidence', row.evidence_json,
               'counter_evidence', row.counter_evidence_json,
               'risk_assessment', row.risk_assessment_json,
               'risk_status',
                 CASE
                   WHEN row.server_risk_allowed
                     THEN 'passed'
                   ELSE 'blocked'
                 END,
               'risk_reason', row.server_risk_reason,
               'proposal_status', row.proposal_status,
               'execution_status', row.decision_status,
               'source_signal_projection_id',
                 row.source_signal_projection_id,
               'source_virtual_position_id',
                 row.source_virtual_position_id,
               'source_virtual_trade_proposal_id', row.proposal_id,
               'strategy_version', row.strategy_version
             )
             ORDER BY row.created_at DESC, row.ai_decision_id DESC
           ),
           '[]'::jsonb
         )
    INTO decisions
  FROM (
    SELECT decision.ai_decision_id,
           decision.ai_decision_run_id,
           decision_run.ai_context_snapshot_id,
           context_snapshot.for_trade_date,
           decision.created_at,
           decision.decision_type,
           decision.identity_key,
           identity_name.display_name,
           decision.confidence,
           decision.reason_summary,
           decision.evidence_json,
           decision.counter_evidence_json,
           decision.risk_assessment_json,
           decision.server_risk_allowed,
           decision.server_risk_reason,
           decision.decision_status,
           decision.source_signal_projection_id,
           decision.source_virtual_position_id,
           decision.proposal_id,
           decision_run.strategy_version,
           proposal.proposal_status
    FROM public.n6_ai_decision decision
    JOIN public.n6_ai_decision_run decision_run
      ON decision_run.ai_decision_run_id =
           decision.ai_decision_run_id
    JOIN public.n6_ai_context_snapshot context_snapshot
      ON context_snapshot.ai_context_snapshot_id =
           decision_run.ai_context_snapshot_id
    LEFT JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.proposal_id = decision.proposal_id
    LEFT JOIN LATERAL (
      SELECT shared.name AS display_name
      FROM public.n6_ai_shared_signal_projection shared
      WHERE shared.identity_key = decision.identity_key
        AND shared.shared_status = 'active'
      ORDER BY shared.for_trade_date DESC,
               shared.source_signal_projection_id DESC
      LIMIT 1
    ) identity_name ON true
    WHERE decision.ai_user_id = actor.ai_user_id
    ORDER BY decision.created_at DESC, decision.ai_decision_id DESC
    LIMIT p_decision_limit
  ) row;

  SELECT COALESCE(
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'ai_daily_summary_id', row.ai_daily_summary_id,
               'trade_date', row.for_trade_date,
               'summary_text', row.summary_text,
               'decision_count', row.decision_count,
               'trade_count',
                 row.buy_trade_count + row.sell_trade_count,
               'net_return_pct', row.net_return_pct,
               'max_drawdown_pct', row.max_drawdown_pct,
               'turnover_pct', row.turnover_pct,
               'risk_adjusted_score', row.risk_adjusted_score,
               'total_asset_value', row.total_asset,
               'current_cash', row.available_cash,
               'position_market_value', row.market_value,
               'daily_net_pnl', row.daily_net_pnl,
               'success_reasons', row.success_reasons_json,
               'lessons', row.failure_reasons_json,
               'next_day_watch_plan', row.next_day_watch_json,
               'strategy_version', row.strategy_version,
               'strategy_hash', row.strategy_hash,
               'knowledge_bundle_version',
                 row.knowledge_bundle_version,
               'knowledge_bundle_hash', row.knowledge_bundle_hash,
               'generated_at', row.created_at
             )
             ORDER BY row.for_trade_date DESC
           ),
           '[]'::jsonb
         )
    INTO summaries
  FROM (
    SELECT summary.*
    FROM public.n6_ai_daily_summary summary
    WHERE summary.ai_user_id = actor.ai_user_id
    ORDER BY summary.for_trade_date DESC
    LIMIT p_summary_limit
  ) row;

  SELECT summary.*
    INTO latest_summary
  FROM public.n6_ai_daily_summary summary
  WHERE summary.ai_user_id = actor.ai_user_id
  ORDER BY summary.for_trade_date DESC
  LIMIT 1;
  SELECT decision_run.*
    INTO latest_run
  FROM public.n6_ai_decision_run decision_run
  WHERE decision_run.ai_user_id = actor.ai_user_id
  ORDER BY decision_run.created_at DESC,
           decision_run.ai_decision_run_id DESC
  LIMIT 1;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true,
    'contract_version', 'n6-ai-agent-public-v1',
    'profile', pg_catalog.jsonb_build_object(
      'ai_user_id', actor.ai_user_id,
      'ai_name', actor.ai_name,
      'ai_status', actor.ai_status,
      'agent_mode',
        COALESCE(latest_run.run_mode, 'disabled'),
      'model_adapter', latest_run.model_adapter,
      'model_version', latest_run.model_version,
      'strategy_version', actor.strategy_version,
      'last_success_at', latest_run.finished_at,
      'pause_reason',
        CASE
          WHEN actor.ai_status = 'disabled'
               AND COALESCE(latest_summary.max_drawdown_pct, 0) >= 5
            THEN 'max_drawdown_pause'
          WHEN actor.ai_status = 'disabled' THEN 'ai_user_disabled'
          WHEN actor.ai_status <> 'active' THEN 'ai_user_inactive'
          WHEN latest_run.ai_decision_run_id IS NULL THEN 'not_started'
          WHEN latest_run.run_status = 'started'
            THEN 'agent_run_in_progress'
          WHEN latest_run.run_status = 'rejected'
            THEN 'agent_run_rejected'
          WHEN latest_run.run_status = 'failed'
            THEN 'agent_run_failed'
          WHEN latest_run.run_status <> 'recorded'
            THEN 'agent_run_unavailable'
          ELSE NULL
        END
    ),
    'account', pg_catalog.jsonb_build_object(
      'virtual_account_id', actor.virtual_account_id,
      'account_name', actor.account_name,
      'account_status', actor.account_status,
      'currency', actor.currency,
      'initial_cash', actor.initial_cash,
      'cash_balance', actor.total_cash,
      'available_cash', actor.available_cash,
      'frozen_cash', actor.frozen_cash,
      'valuation_status',
        CASE
          WHEN invalid_position_quote_count = 0 THEN 'ready'
          ELSE 'not_ready'
        END,
      'not_ready_position_count', invalid_position_quote_count,
      'market_value', position_market_value,
      'total_equity', actor.total_cash + position_market_value,
      'net_pnl',
        actor.total_cash + position_market_value -
        actor.initial_cash,
      'total_return_pct',
        CASE
          WHEN actor.initial_cash > 0 THEN
            (
              actor.total_cash + position_market_value -
              actor.initial_cash
            ) / actor.initial_cash * 100
          ELSE 0
        END,
      'max_drawdown_pct',
        COALESCE(latest_summary.max_drawdown_pct, 0),
      'as_of', actor.snapshot_time
    ),
    'positions', positions,
    'trades', trades,
    'decisions', decisions,
    'daily_summaries', summaries,
    'performance', pg_catalog.jsonb_build_object(
      'trade_date', latest_summary.for_trade_date,
      'total_asset_value',
        COALESCE(
          latest_summary.total_asset,
          actor.total_cash + position_market_value
        ),
      'current_cash', actor.available_cash,
      'position_market_value', position_market_value,
      'daily_net_pnl',
        CASE
          WHEN latest_summary.ai_daily_summary_id IS NULL
            THEN NULL
          ELSE latest_summary.daily_net_pnl
        END,
      'net_return_pct', latest_summary.net_return_pct,
      'max_drawdown_pct', latest_summary.max_drawdown_pct,
      'turnover_pct', latest_summary.turnover_pct,
      'risk_adjusted_score', latest_summary.risk_adjusted_score,
      'total_trade_count',
        (
          SELECT count(*)
          FROM public.n6_virtual_trade trade
          WHERE trade.virtual_account_id =
                actor.virtual_account_id
            AND trade.principal_type = 'ai_user'
            AND trade.trade_status = 'filled_virtual'
        ),
      'winning_trade_count', 0,
      'as_of',
        COALESCE(latest_summary.created_at, actor.snapshot_time)
    ),
    'strategy', pg_catalog.jsonb_build_object(
      'strategy_id', actor.strategy_id,
      'strategy_name', actor.strategy_name,
      'policy_version', actor.strategy_version,
      'policy_hash', actor.strategy_hash,
      'status', actor.strategy_status,
      'risk_labels', pg_catalog.to_jsonb(actor.risk_labels)
    ),
    'runtime', pg_catalog.jsonb_build_object(
      'latest_run_id', latest_run.ai_decision_run_id,
      'run_mode', latest_run.run_mode,
      'run_status', latest_run.run_status,
      'model_adapter', latest_run.model_adapter,
      'model_version', latest_run.model_version,
      'last_started_at', latest_run.started_at,
      'last_finished_at', latest_run.finished_at
    )
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.n6_btrack_ai_public_decision_detail(
  p_session_token_hash text,
  p_ai_decision_id bigint
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb;
  actor record;
  actor_count integer;
  result jsonb;
BEGIN
  IF SESSION_USER <> 'n6_btrack_web'
     OR p_session_token_hash !~ '^[0-9a-f]{64}$'
     OR p_ai_decision_id IS NULL
     OR p_ai_decision_id <= 0 THEN
    RETURN NULL;
  END IF;
  authority :=
    public.n6_btrack_resolve_authority(p_session_token_hash);
  IF authority IS NULL
     OR authority->>'principal_status' <> 'active'
     OR authority->>'principal_type' NOT IN ('admin', 'human_user') THEN
    RETURN NULL;
  END IF;

  SELECT min(ai.ai_user_id) AS ai_user_id,
         min(ai.principal_id) AS principal_id,
         min(strategy.strategy_id) AS strategy_id,
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
   AND strategy.visibility = 'public_leaderboard'
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
  IF actor_count <> 1 THEN
    RETURN NULL;
  END IF;

  SELECT pg_catalog.jsonb_build_object(
           'ok', true,
           'contract_version', 'n6-ai-agent-public-v1',
           'decision', pg_catalog.jsonb_build_object(
             'ai_decision_id', decision.ai_decision_id,
             'ai_decision_run_id', decision.ai_decision_run_id,
             'ai_context_snapshot_id',
               decision_run.ai_context_snapshot_id,
             'for_trade_date', context_snapshot.for_trade_date,
             'created_at', decision.created_at,
             'decision_type', decision.decision_type,
             'identity_key', decision.identity_key,
             'display_name', identity_name.display_name,
             'confidence', decision.confidence,
             'reason_summary', decision.reason_summary,
             'evidence', decision.evidence_json,
             'counter_evidence', decision.counter_evidence_json,
             'risk_assessment', decision.risk_assessment_json,
             'risk_status',
               CASE
                 WHEN decision.server_risk_allowed
                   THEN 'passed'
                 ELSE 'blocked'
               END,
             'risk_reason', decision.server_risk_reason,
             'proposal_status', proposal.proposal_status,
             'execution_status', decision.decision_status,
             'source_signal_projection_id',
               decision.source_signal_projection_id,
             'source_virtual_position_id',
               decision.source_virtual_position_id,
             'source_virtual_trade_proposal_id',
               decision.proposal_id,
             'strategy_version', decision_run.strategy_version
           )
         )
    INTO result
  FROM public.n6_ai_decision decision
  JOIN public.n6_ai_decision_run decision_run
    ON decision_run.ai_decision_run_id =
         decision.ai_decision_run_id
  JOIN public.n6_ai_context_snapshot context_snapshot
    ON context_snapshot.ai_context_snapshot_id =
         decision_run.ai_context_snapshot_id
  LEFT JOIN public.n6_virtual_trade_proposal proposal
    ON proposal.proposal_id = decision.proposal_id
  LEFT JOIN LATERAL (
    SELECT shared.name AS display_name
    FROM public.n6_ai_shared_signal_projection shared
    WHERE shared.identity_key = decision.identity_key
      AND shared.shared_status = 'active'
    ORDER BY shared.for_trade_date DESC,
             shared.source_signal_projection_id DESC
    LIMIT 1
  ) identity_name ON true
  WHERE decision.ai_decision_id = p_ai_decision_id
    AND decision.ai_user_id = actor.ai_user_id
    AND decision.principal_id = actor.principal_id
    AND decision_run.strategy_id = actor.strategy_id;
  RETURN result;
END;
$function$;

-- The bootstrap body exists only to satisfy same-transaction dependency
-- ordering.  It is removed before COMMIT and is never a published authority.
DROP FUNCTION public.n6_ai_agent_shadow_decision_record_bootstrap(jsonb);

REVOKE ALL ON FUNCTION public.n6_ai_agent_context_load(text,date,integer)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_ai_agent_shadow_decision_record(jsonb)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_ai_agent_proposal_create_confirm(jsonb)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_ai_agent_daily_summary_record(jsonb)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_ai_agent_strategy_evaluation_record(jsonb)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_ai_executor_risk_recheck(bigint,text)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_btrack_ai_public_snapshot(
  text,integer,integer,integer
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.n6_btrack_ai_public_decision_detail(text,bigint)
  FROM PUBLIC;

REVOKE ALL ON FUNCTION public.n6_ai_agent_context_load(text,date,integer)
  FROM n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_agent_shadow_decision_record(jsonb)
  FROM n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_agent_proposal_create_confirm(jsonb)
  FROM n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_agent_daily_summary_record(jsonb)
  FROM n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_agent_strategy_evaluation_record(jsonb)
  FROM n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_executor_risk_recheck(bigint,text)
  FROM n6_ai_agent, n6_btrack_web;
REVOKE ALL ON FUNCTION public.n6_btrack_ai_public_snapshot(
  text,integer,integer,integer
) FROM n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_btrack_ai_public_decision_detail(text,bigint)
  FROM n6_ai_agent, n6_virtual_executor;

GRANT USAGE ON SCHEMA public TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_context_load(text,date,integer)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_shadow_decision_record(jsonb)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_proposal_create_confirm(jsonb)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_daily_summary_record(jsonb)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_strategy_evaluation_record(jsonb)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_ai_executor_risk_recheck(bigint,text)
  TO n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_ai_public_snapshot(text,integer,integer,integer)
  TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_ai_public_snapshot(text,integer,integer,integer)
  TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION public.n6_btrack_ai_public_decision_detail(text,bigint)
  TO n6_btrack_web;

DO $postcheck$
DECLARE
  function_name text;
  expected_roles text[];
  public_execute boolean;
  expected_execute boolean;
  cross_execute boolean;
  hardened_count integer;
  privilege_hit record;
  expected_role text;
BEGIN
  SELECT count(*)
    INTO hardened_count
  FROM (VALUES
    ('public.n6_ai_shared_signal_projection_capture()'),
    ('public.n6_ai_agent_context_load(text,date,integer)'),
    ('public.n6_ai_agent_shadow_decision_record(jsonb)'),
    ('public.n6_ai_agent_proposal_create_confirm(jsonb)'),
    ('public.n6_ai_agent_daily_summary_record(jsonb)'),
    ('public.n6_ai_agent_strategy_evaluation_record(jsonb)'),
    ('public.n6_ai_executor_risk_recheck(bigint,text)'),
    ('public.n6_btrack_ai_public_snapshot(text,integer,integer,integer)'),
    ('public.n6_btrack_ai_public_decision_detail(text,bigint)')
  ) required(signature)
  JOIN pg_catalog.pg_proc function_row
    ON function_row.oid =
         pg_catalog.to_regprocedure(required.signature)
  WHERE function_row.prosecdef
    AND function_row.proowner =
          (SELECT role.oid
           FROM pg_catalog.pg_roles role
           WHERE role.rolname = CURRENT_USER)
    AND function_row.proconfig @>
          ARRAY['search_path=pg_catalog']::text[];
  IF hardened_count <> 9 THEN
    RAISE EXCEPTION
      '055 hardened function property mismatch: %', hardened_count;
  END IF;
  IF (
    SELECT count(*)
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid =
          'public.user_signal_projection'::pg_catalog.regclass
      AND trigger_row.tgname =
          'trg_055_n6_ai_shared_signal_projection_capture'
      AND NOT trigger_row.tgisinternal
  ) <> 1 THEN
    RAISE EXCEPTION '055 shared signal capture trigger mismatch';
  END IF;
  IF EXISTS (
       SELECT 1
       FROM pg_catalog.pg_proc target
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         COALESCE(
           target.proacl,
           pg_catalog.acldefault('f', target.proowner)
         )
       ) acl
       WHERE target.oid = pg_catalog.to_regprocedure(
               'public.n6_ai_shared_signal_projection_capture()'
             )
         AND acl.grantee = 0
         AND acl.privilege_type = 'EXECUTE'
     )
     OR EXISTS (
       SELECT 1
       FROM (VALUES
         ('n6_ai_agent'::text),
         ('n6_btrack_web'::text),
         ('n6_virtual_executor'::text)
       ) role_name(name)
       WHERE pg_catalog.has_function_privilege(
         role_name.name,
         'public.n6_ai_shared_signal_projection_capture()',
         'EXECUTE'
       )
     ) THEN
    RAISE EXCEPTION '055 shared signal capture execute leaked';
  END IF;

  FOR function_name, expected_roles IN
    SELECT *
    FROM (VALUES
      ('public.n6_ai_agent_context_load(text,date,integer)',
       ARRAY['n6_ai_agent']::text[]),
      ('public.n6_ai_agent_shadow_decision_record(jsonb)',
       ARRAY['n6_ai_agent']::text[]),
      ('public.n6_ai_agent_proposal_create_confirm(jsonb)',
       ARRAY['n6_ai_agent']::text[]),
      ('public.n6_ai_agent_daily_summary_record(jsonb)',
       ARRAY['n6_ai_agent']::text[]),
      ('public.n6_ai_agent_strategy_evaluation_record(jsonb)',
       ARRAY['n6_ai_agent']::text[]),
      ('public.n6_ai_executor_risk_recheck(bigint,text)',
       ARRAY['n6_virtual_executor']::text[]),
      ('public.n6_btrack_ai_public_snapshot(text,integer,integer,integer)',
       ARRAY['n6_btrack_web', 'n6_ai_agent']::text[]),
      ('public.n6_btrack_ai_public_decision_detail(text,bigint)',
       ARRAY['n6_btrack_web']::text[])
    ) expected(function_name, expected_roles)
  LOOP
    SELECT EXISTS (
             SELECT 1
             FROM pg_catalog.pg_proc target
             CROSS JOIN LATERAL pg_catalog.aclexplode(
               COALESCE(
                 target.proacl,
                 pg_catalog.acldefault('f', target.proowner)
               )
             ) acl
             WHERE target.oid =
                   function_name::pg_catalog.regprocedure
               AND acl.grantee = 0
               AND acl.privilege_type = 'EXECUTE'
           ),
           NOT EXISTS (
             SELECT 1
             FROM pg_catalog.unnest(expected_roles)
                    expected_role(role_name)
             WHERE pg_catalog.has_function_privilege(
                     expected_role.role_name,
                     function_name,
                     'EXECUTE'
                   ) IS DISTINCT FROM true
           ),
           EXISTS (
             SELECT 1
             FROM pg_catalog.pg_roles role
             WHERE role.rolname IN (
               'n6_ai_agent', 'n6_btrack_web',
               'n6_virtual_executor'
             )
               AND NOT role.rolname = ANY(expected_roles)
               AND pg_catalog.has_function_privilege(
                     role.rolname, function_name, 'EXECUTE'
                   )
           )
      INTO public_execute, expected_execute, cross_execute;
    IF public_execute
       OR expected_execute IS DISTINCT FROM true
       OR cross_execute THEN
      RAISE EXCEPTION '055 function ACL mismatch: %', function_name;
    END IF;
  END LOOP;

  FOR expected_role IN
    SELECT role_name
    FROM (VALUES
      ('n6_ai_agent'::text),
      ('n6_btrack_web'::text),
      ('n6_virtual_executor'::text)
    ) required(role_name)
  LOOP
    SELECT n.nspname, c.relname, requested.privilege_name
      INTO privilege_hit
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n
      ON n.oid = c.relnamespace
    CROSS JOIN (VALUES
      ('SELECT'::text), ('INSERT'::text), ('UPDATE'::text),
      ('DELETE'::text), ('TRUNCATE'::text), ('REFERENCES'::text),
      ('TRIGGER'::text)
    ) requested(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND pg_catalog.has_table_privilege(
            expected_role, c.oid, requested.privilege_name
          )
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION
        '055 direct relation privilege after migration: role=% relation=%.% privilege=%',
        expected_role, privilege_hit.nspname, privilege_hit.relname,
        privilege_hit.privilege_name;
    END IF;

    SELECT n.nspname, c.relname, requested.privilege_name
      INTO privilege_hit
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n
      ON n.oid = c.relnamespace
    CROSS JOIN (VALUES
      ('USAGE'::text), ('SELECT'::text), ('UPDATE'::text)
    ) requested(privilege_name)
    WHERE n.nspname = 'public'
      AND c.relkind = 'S'
      AND pg_catalog.has_sequence_privilege(
            expected_role, c.oid, requested.privilege_name
          )
    LIMIT 1;
    IF FOUND THEN
      RAISE EXCEPTION
        '055 direct sequence privilege after migration: role=% sequence=%.% privilege=%',
        expected_role, privilege_hit.nspname, privilege_hit.relname,
        privilege_hit.privilege_name;
    END IF;
  END LOOP;
END;
$postcheck$;

COMMIT;
