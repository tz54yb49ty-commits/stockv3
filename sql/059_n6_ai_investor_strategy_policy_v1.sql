-- N6 AI investor strategy policy V1 additive schema.
-- REVIEW ONLY until a separate runtime_control migration execution gate.
-- Shadow evaluation may write only the three 059 strategy/audit relations.
-- Autonomous proposal/executor paths are intentionally dormant.

BEGIN;

DO $preflight$
DECLARE
  leaked_privilege record;
  legacy_capture_function_oid oid;
  legacy_constraint_count integer;
  legacy_expected_constraint_count integer;
  legacy_constraint_mismatch_count integer;
  legacy_trigger_count integer;
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '059_migration_identity_mismatch';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
     ) IS NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shared_signal_projection_capture()'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_shared_signal_projection'
        ) IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_context_snapshot') IS NULL
     OR pg_catalog.to_regclass('public.n6_virtual_position') IS NULL
     OR pg_catalog.to_regclass('public.n6_virtual_position_lot') IS NULL
     OR pg_catalog.to_regclass('public.n6_virtual_trade_proposal') IS NULL
     OR pg_catalog.to_regclass('public.n6_virtual_quote_snapshot') IS NULL
     OR pg_catalog.to_regclass('public.common_trade_calendar') IS NULL
     OR pg_catalog.to_regclass(
          'public.v_n6_index_membership_fact'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.v_n6_board_membership_fact'
        ) IS NULL THEN
    RAISE EXCEPTION '059_requires_live_055_through_058';
  END IF;
  IF pg_catalog.to_regclass(
       'public.n6_ai_position_strategy_episode'
     ) IS NOT NULL
     OR pg_catalog.to_regclass('public.n6_ai_strategy_action') IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_candidate_rank_audit'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_strategy_context_load_v1(text,date,integer,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_shared_strategy_fields_capture_v1()'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_strategy_episode_locked_fields_immutable_v1()'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_strategy_shadow_evaluate(date,text,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_strategy_proposal_create_confirm_v1(jsonb)'
        ) IS NOT NULL
     OR pg_catalog.to_regprocedure(
          'public.n6_ai_executor_strategy_action_apply_v1(bigint,text)'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_position_strategy_episode_strategy_episode_id_seq'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_strategy_action_strategy_action_id_seq'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_candidate_rank_audit_candidate_rank_audit_id_seq'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_059_n6_ai_strategy_target_reduce_once'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_059_n6_ai_strategy_action_pending'
        ) IS NOT NULL
     OR pg_catalog.to_regclass(
          'public.idx_059_n6_virtual_trade_proposal_strategy_action'
        ) IS NOT NULL THEN
    RAISE EXCEPTION '059_already_applied';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_attribute attribute
    WHERE attribute.attrelid =
            'public.n6_ai_shared_signal_projection'::regclass
      AND attribute.attnum > 0
      AND attribute.attisdropped = false
      AND attribute.attname = ANY (ARRAY[
        'strategy_context_version',
        'reference_target_price',
        'target_quality_status',
        'up_sell_reference_period',
        'financial_score_raw'
      ]::text[])
  ) OR EXISTS (
    SELECT 1
    FROM pg_catalog.pg_attribute attribute
    WHERE attribute.attrelid =
            'public.n6_virtual_trade_proposal'::regclass
      AND attribute.attnum > 0
      AND attribute.attisdropped = false
      AND attribute.attname = 'strategy_action_id'
  ) OR EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint constraint_row
    WHERE constraint_row.conrelid IN (
      'public.n6_ai_shared_signal_projection'::regclass,
      'public.n6_virtual_trade_proposal'::regclass
    )
      AND constraint_row.conname = ANY (ARRAY[
        'n6_ai_shared_signal_projection_059_context_version_ck',
        'n6_ai_shared_signal_projection_059_target_price_ck',
        'n6_ai_shared_signal_projection_059_target_quality_ck',
        'n6_ai_shared_signal_projection_059_sell_period_ck',
        'n6_virtual_trade_proposal_059_actor_ck',
        'n6_virtual_trade_proposal_059_source_type_ck',
        'n6_virtual_trade_proposal_059_signal_source_ck',
        'n6_virtual_trade_proposal_059_position_source_ck',
        'n6_virtual_trade_proposal_059_strategy_action_ck'
      ]::text[])
  ) OR EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger trigger_row
    WHERE trigger_row.tgrelid =
            'public.user_signal_projection'::regclass
      AND trigger_row.tgname =
            'trg_059_n6_ai_shared_strategy_fields_capture'
      AND trigger_row.tgisinternal = false
  ) THEN
    RAISE EXCEPTION '059_partial_object_conflict';
  END IF;

  SELECT function_row.oid
    INTO legacy_capture_function_oid
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  JOIN pg_catalog.pg_language function_language
    ON function_language.oid = function_row.prolang
  WHERE function_row.oid = pg_catalog.to_regprocedure(
          'public.n6_ai_shared_signal_projection_capture()'
        )
    AND function_owner.rolname = 'ashare_v3_user'
    AND function_language.lanname = 'plpgsql'
    AND function_row.prokind = 'f'
    AND function_row.prorettype =
          'pg_catalog.trigger'::pg_catalog.regtype
    AND function_row.pronargs = 0
    AND function_row.provolatile = 'v'
    AND function_row.prosecdef = true
    AND function_row.proisstrict = false
    AND function_row.proleakproof = false
    AND function_row.proparallel = 'u'
    AND function_row.proconfig IS NOT DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
    AND pg_catalog.encode(
          pg_catalog.sha256(
            pg_catalog.convert_to(function_row.prosrc, 'UTF8')
          ),
          'hex'
        ) =
          '6bd08f39b6421840aaa95a8b1f7b6507bba402b5e3b18b499dfdeaa3ec2e1f04';
  IF legacy_capture_function_oid IS NULL THEN
    RAISE EXCEPTION '059_legacy_projection_capture_function_mismatch';
  END IF;

  SELECT pg_catalog.count(*)
    INTO legacy_trigger_count
  FROM pg_catalog.pg_trigger trigger_row
  WHERE trigger_row.tgrelid =
          'public.user_signal_projection'::regclass
    AND trigger_row.tgname =
          'trg_055_n6_ai_shared_signal_projection_capture'
    AND trigger_row.tgtype = 5
    AND trigger_row.tgenabled = 'O'
    AND trigger_row.tgisinternal = false
    AND trigger_row.tgnargs = 0
    AND trigger_row.tgargs = ''::pg_catalog.bytea
    AND trigger_row.tgattr = ''::pg_catalog.int2vector
    AND trigger_row.tgqual IS NULL
    AND trigger_row.tgconstraint = 0
    AND trigger_row.tgconstrrelid = 0
    AND trigger_row.tgconstrindid = 0
    AND trigger_row.tgdeferrable = false
    AND trigger_row.tginitdeferred = false
    AND trigger_row.tgoldtable IS NULL
    AND trigger_row.tgnewtable IS NULL
    AND trigger_row.tgparentid = 0
    AND trigger_row.tgfoid = legacy_capture_function_oid;
  IF legacy_trigger_count <> 1 THEN
    RAISE EXCEPTION '059_legacy_projection_trigger_mismatch';
  END IF;

  CREATE TEMPORARY TABLE n6_virtual_trade_proposal_055_expected (
    principal_type text,
    user_id bigint,
    actor_ai_user_id bigint,
    source_ai_decision_id bigint,
    source_type text,
    source_signal_projection_id bigint,
    source_virtual_position_id bigint,
    CONSTRAINT n6_virtual_trade_proposal_055_actor_ck
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
    CONSTRAINT n6_virtual_trade_proposal_055_source_type_ck
      CHECK (source_type IN ('signal', 'manual_position', 'stop_loss', 'ai_risk')),
    CONSTRAINT n6_virtual_trade_proposal_055_signal_source_ck
      CHECK (
        (source_type = 'signal'
         AND source_signal_projection_id IS NOT NULL)
        OR
        (source_type <> 'signal'
         AND source_signal_projection_id IS NULL)
      ),
    CONSTRAINT n6_virtual_trade_proposal_055_position_source_ck
      CHECK (
        (source_type IN ('manual_position', 'stop_loss', 'ai_risk')
         AND source_virtual_position_id IS NOT NULL)
        OR source_type = 'signal'
      )
  ) ON COMMIT DROP;

  SELECT pg_catalog.count(*)
    INTO legacy_constraint_count
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.conrelid =
          'public.n6_virtual_trade_proposal'::regclass
    AND constraint_row.conname = ANY (ARRAY[
      'n6_virtual_trade_proposal_055_actor_ck',
      'n6_virtual_trade_proposal_055_source_type_ck',
      'n6_virtual_trade_proposal_055_signal_source_ck',
      'n6_virtual_trade_proposal_055_position_source_ck'
    ]::text[]);
  IF legacy_constraint_count <> 4 THEN
    RAISE EXCEPTION '059_legacy_proposal_contract_mismatch';
  END IF;

  SELECT pg_catalog.count(*)
    INTO legacy_expected_constraint_count
  FROM pg_catalog.pg_constraint expected_constraint
  WHERE expected_constraint.conrelid =
          'pg_temp.n6_virtual_trade_proposal_055_expected'::regclass
    AND expected_constraint.contype = 'c';
  IF legacy_expected_constraint_count <> 4 THEN
    RAISE EXCEPTION '059_expected_proposal_contract_internal_mismatch';
  END IF;

  SELECT pg_catalog.count(*)
    INTO legacy_constraint_mismatch_count
  FROM pg_catalog.pg_constraint expected_constraint
  LEFT JOIN pg_catalog.pg_constraint actual_constraint
    ON actual_constraint.conrelid =
         'public.n6_virtual_trade_proposal'::regclass
   AND actual_constraint.conname = expected_constraint.conname
  WHERE expected_constraint.conrelid =
          'pg_temp.n6_virtual_trade_proposal_055_expected'::regclass
    AND expected_constraint.contype = 'c'
    AND (
      actual_constraint.oid IS NULL
      OR actual_constraint.contype IS DISTINCT FROM 'c'
      OR actual_constraint.convalidated IS DISTINCT FROM true
      OR actual_constraint.connoinherit IS DISTINCT FROM false
      OR actual_constraint.conislocal IS DISTINCT FROM true
      OR actual_constraint.coninhcount IS DISTINCT FROM 0
      OR pg_catalog.pg_get_constraintdef(
           actual_constraint.oid, false
         ) IS DISTINCT FROM pg_catalog.pg_get_constraintdef(
           expected_constraint.oid, false
         )
    );
  IF legacy_constraint_mismatch_count <> 0 THEN
    RAISE EXCEPTION '059_legacy_proposal_contract_mismatch';
  END IF;

  DROP TABLE pg_temp.n6_virtual_trade_proposal_055_expected;

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
  ) OR NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = 'n6_virtual_executor'
      AND rolcanlogin = true
      AND rolsuper = false
      AND rolcreaterole = false
      AND rolcreatedb = false
      AND rolreplication = false
      AND rolbypassrls = false
  ) THEN
    RAISE EXCEPTION '059_required_role_contract_mismatch';
  END IF;

  SELECT relation.relname, requested.privilege_name
    INTO leaked_privilege
  FROM pg_catalog.pg_roles role
  JOIN pg_catalog.pg_class relation ON true
  JOIN pg_catalog.pg_namespace namespace
    ON namespace.oid = relation.relnamespace
  CROSS JOIN (
    VALUES ('SELECT'::text), ('INSERT'::text), ('UPDATE'::text),
           ('DELETE'::text), ('TRUNCATE'::text),
           ('REFERENCES'::text), ('TRIGGER'::text)
  ) requested(privilege_name)
  WHERE role.rolname = 'n6_ai_agent'
    AND namespace.nspname = 'public'
    AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
    AND pg_catalog.has_table_privilege(
          role.oid, relation.oid, requested.privilege_name
        )
  LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION '059_ai_role_direct_relation_privilege_rejected: %.%',
      leaked_privilege.relname, leaked_privilege.privilege_name;
  END IF;

  SELECT relation.relname, requested.privilege_name
    INTO leaked_privilege
  FROM pg_catalog.pg_roles role
  JOIN pg_catalog.pg_class relation ON true
  JOIN pg_catalog.pg_namespace namespace
    ON namespace.oid = relation.relnamespace
  CROSS JOIN (
    VALUES ('USAGE'::text), ('SELECT'::text), ('UPDATE'::text)
  ) requested(privilege_name)
  WHERE role.rolname = 'n6_ai_agent'
    AND namespace.nspname = 'public'
    AND relation.relkind = 'S'
    AND pg_catalog.has_sequence_privilege(
          role.oid, relation.oid, requested.privilege_name
        )
  LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION '059_ai_role_direct_sequence_privilege_rejected: %.%',
      leaked_privilege.relname, leaked_privilege.privilege_name;
  END IF;
END
$preflight$;

ALTER TABLE public.n6_ai_shared_signal_projection
  ADD COLUMN strategy_context_version TEXT,
  ADD COLUMN reference_target_price NUMERIC(24,8),
  ADD COLUMN target_quality_status TEXT,
  ADD COLUMN up_sell_reference_period TEXT,
  ADD COLUMN financial_score_raw NUMERIC(18,8),
  ADD CONSTRAINT n6_ai_shared_signal_projection_059_context_version_ck
    CHECK (
      strategy_context_version IS NULL
      OR strategy_context_version = 'n6_ai_investor_strategy_policy_v1'
    ),
  ADD CONSTRAINT n6_ai_shared_signal_projection_059_target_price_ck
    CHECK (
      reference_target_price IS NULL
      OR reference_target_price > 0
    ),
  ADD CONSTRAINT n6_ai_shared_signal_projection_059_target_quality_ck
    CHECK (
      target_quality_status IS NULL
      OR target_quality_status IN ('passed', 'not_ready')
    ),
  ADD CONSTRAINT n6_ai_shared_signal_projection_059_sell_period_ck
    CHECK (
      up_sell_reference_period IS NULL
      OR up_sell_reference_period IN ('Y', 'Q', 'M', 'W', 'D')
    );

CREATE OR REPLACE FUNCTION public.n6_ai_shared_strategy_fields_capture_v1()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  safe_context_fields jsonb;
  safe_target_text text;
  safe_financial_score_text text;
  safe_target_price numeric(24,8);
  safe_target_quality text;
  safe_up_sell_period text;
  safe_clear_sell_period text;
  safe_sell_period text;
  safe_financial_score numeric(18,8);
BEGIN
  safe_context_fields := COALESCE(
    NEW.display_payload_json
      ->'condition_projection_context'->'fields',
    '{}'::jsonb
  );
  safe_target_text := COALESCE(
    safe_context_fields->>'buy_target_price',
    NEW.display_payload_json->>'buy_target_price',
    NEW.target_price::text
  );
  safe_financial_score_text := COALESCE(
    safe_context_fields->>'score',
    NEW.display_payload_json->>'score'
  );
  safe_target_price := CASE
    WHEN safe_target_text ~ '^[0-9]+([.][0-9]+)?$'
      AND pg_catalog.pg_input_is_valid(
            safe_target_text, 'numeric(24,8)'
          )
      THEN CASE
        WHEN safe_target_text::numeric(24,8) > 0
          THEN safe_target_text::numeric(24,8)
        ELSE NULL
      END
    ELSE NULL
  END;
  safe_target_quality := CASE
    WHEN safe_target_price IS NOT NULL
     AND (
       NEW.display_payload_json->>'target_price_quality_status' = 'passed'
       OR (
         NEW.display_payload_json
           ->>'condition_projection_context_status' = 'ready'
         AND NEW.display_payload_json
               ->'condition_projection_context'->>'status' = 'ready'
       )
     )
      THEN 'passed'
    ELSE 'not_ready'
  END;
  safe_up_sell_period := COALESCE(
    safe_context_fields->>'up_sell_reference_period',
    NEW.display_payload_json->>'up_sell_reference_period'
  );
  safe_clear_sell_period := COALESCE(
    safe_context_fields->>'clear_sell_ref_period',
    NEW.display_payload_json->>'clear_sell_ref_period'
  );
  safe_sell_period := CASE
    WHEN safe_up_sell_period IS NOT NULL
     AND safe_clear_sell_period IS NOT NULL
     AND safe_up_sell_period IS DISTINCT FROM safe_clear_sell_period
      THEN NULL
    WHEN COALESCE(safe_up_sell_period, safe_clear_sell_period)
           IN ('Y', 'Q', 'M', 'W', 'D')
      THEN COALESCE(safe_up_sell_period, safe_clear_sell_period)
    ELSE NULL
  END;
  safe_financial_score := CASE
    WHEN safe_financial_score_text ~ '^-?[0-9]+([.][0-9]+)?$'
     AND pg_catalog.pg_input_is_valid(
           safe_financial_score_text, 'numeric(18,8)'
         )
      THEN safe_financial_score_text::numeric(18,8)
    ELSE NULL
  END;

  UPDATE public.n6_ai_shared_signal_projection
  SET strategy_context_version = 'n6_ai_investor_strategy_policy_v1',
      reference_target_price = safe_target_price,
      target_quality_status = safe_target_quality,
      up_sell_reference_period = safe_sell_period,
      financial_score_raw = safe_financial_score
  WHERE source_signal_projection_id = NEW.user_signal_projection_id;
  RETURN NEW;
END
$function$;

REVOKE ALL ON FUNCTION public.n6_ai_shared_strategy_fields_capture_v1()
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;

CREATE TRIGGER trg_059_n6_ai_shared_strategy_fields_capture
AFTER INSERT ON public.user_signal_projection
FOR EACH ROW
EXECUTE FUNCTION public.n6_ai_shared_strategy_fields_capture_v1();

WITH backfill_source AS (
  SELECT shared.source_signal_projection_id,
         projection.display_payload_json AS backfill_display_payload_json,
         COALESCE(
           projection.display_payload_json
             ->'condition_projection_context'->'fields'
             ->>'buy_target_price',
           projection.display_payload_json->>'buy_target_price',
           shared.target_price::text
         ) AS backfill_target_text,
         COALESCE(
           projection.display_payload_json
             ->'condition_projection_context'->'fields'->>'score',
           projection.display_payload_json->>'score'
         ) AS backfill_financial_score_text,
         COALESCE(
           projection.display_payload_json
             ->'condition_projection_context'->'fields'
             ->>'up_sell_reference_period',
           projection.display_payload_json->>'up_sell_reference_period'
         ) AS backfill_up_sell_period,
         COALESCE(
           projection.display_payload_json
             ->'condition_projection_context'->'fields'
             ->>'clear_sell_ref_period',
           projection.display_payload_json->>'clear_sell_ref_period'
         ) AS backfill_clear_sell_period
  FROM public.n6_ai_shared_signal_projection shared
  JOIN public.user_signal_projection projection
    ON projection.user_signal_projection_id =
         shared.source_signal_projection_id
), validated_source AS (
  SELECT source_signal_projection_id,
         backfill_display_payload_json,
         backfill_up_sell_period,
         backfill_clear_sell_period,
         CASE
           WHEN backfill_target_text ~ '^[0-9]+([.][0-9]+)?$'
            AND pg_catalog.pg_input_is_valid(
                  backfill_target_text, 'numeric(24,8)'
                )
             THEN backfill_target_text::numeric(24,8)
           ELSE NULL
         END AS backfill_target_price,
         CASE
           WHEN backfill_financial_score_text ~
                  '^-?[0-9]+([.][0-9]+)?$'
            AND pg_catalog.pg_input_is_valid(
                  backfill_financial_score_text, 'numeric(18,8)'
                )
             THEN backfill_financial_score_text::numeric(18,8)
           ELSE NULL
         END AS backfill_financial_score
  FROM backfill_source
)
UPDATE public.n6_ai_shared_signal_projection shared
SET strategy_context_version = 'n6_ai_investor_strategy_policy_v1',
    reference_target_price = CASE
      WHEN backfill_target_price > 0
        THEN backfill_target_price
      ELSE NULL
    END,
    target_quality_status = CASE
      WHEN backfill_target_price > 0
       AND (
         backfill_display_payload_json
           ->>'target_price_quality_status' = 'passed'
         OR (
           backfill_display_payload_json
             ->>'condition_projection_context_status' = 'ready'
           AND backfill_display_payload_json
                 ->'condition_projection_context'->>'status' = 'ready'
         )
       )
        THEN 'passed'
      ELSE 'not_ready'
    END,
    up_sell_reference_period = CASE
      WHEN backfill_up_sell_period IS NOT NULL
       AND backfill_clear_sell_period IS NOT NULL
       AND backfill_up_sell_period IS DISTINCT FROM
             backfill_clear_sell_period
        THEN NULL
      WHEN COALESCE(
             backfill_up_sell_period,
             backfill_clear_sell_period
           ) IN ('Y', 'Q', 'M', 'W', 'D')
        THEN COALESCE(
               backfill_up_sell_period,
               backfill_clear_sell_period
             )
      ELSE NULL
    END,
    financial_score_raw = backfill_financial_score
FROM validated_source
WHERE validated_source.source_signal_projection_id =
      shared.source_signal_projection_id;

CREATE TABLE public.n6_ai_position_strategy_episode (
  strategy_episode_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user'
    CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  virtual_account_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_account(virtual_account_id),
  virtual_position_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_position(virtual_position_id),
  identity_key TEXT NOT NULL
    CHECK (identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'),
  holding_episode_no INTEGER NOT NULL CHECK (holding_episode_no > 0),
  locked_target_price NUMERIC(24,8)
    CHECK (locked_target_price IS NULL OR locked_target_price > 0),
  locked_target_quality_status TEXT NOT NULL DEFAULT 'not_ready'
    CHECK (locked_target_quality_status IN ('passed', 'not_ready')),
  locked_target_source_signal_projection_id BIGINT
    REFERENCES public.n6_ai_shared_signal_projection(
      source_signal_projection_id
    ),
  up_sell_reference_period TEXT
    CHECK (
      up_sell_reference_period IS NULL
      OR up_sell_reference_period IN ('Y', 'Q', 'M', 'W', 'D')
    ),
  pending_clear BOOLEAN NOT NULL DEFAULT false,
  pending_clear_source_signal_projection_id BIGINT
    REFERENCES public.n6_ai_shared_signal_projection(
      source_signal_projection_id
    ),
  pending_clear_started_trade_date DATE,
  pending_clear_completed_at TIMESTAMPTZ,
  episode_status TEXT NOT NULL DEFAULT 'open'
    CHECK (episode_status IN ('open', 'closed')),
  policy_version TEXT NOT NULL
    DEFAULT 'n6_ai_investor_strategy_policy_v1'
    CHECK (policy_version = 'n6_ai_investor_strategy_policy_v1'),
  policy_hash TEXT NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (
    locked_target_quality_status <> 'passed'
    OR (
      locked_target_price IS NOT NULL
      AND locked_target_source_signal_projection_id IS NOT NULL
    )
  ),
  CHECK (
    pending_clear = false
    OR (
      pending_clear_source_signal_projection_id IS NOT NULL
      AND pending_clear_started_trade_date IS NOT NULL
      AND episode_status = 'open'
    )
  ),
  CHECK (
    pending_clear_completed_at IS NULL
    OR (pending_clear = false AND episode_status = 'closed')
  ),
  UNIQUE (
    virtual_account_id, virtual_position_id, holding_episode_no
  ),
  UNIQUE (
    strategy_episode_id, ai_user_id, principal_id, principal_type,
    strategy_id, virtual_account_id, virtual_position_id,
    identity_key, holding_episode_no
  )
);

CREATE OR REPLACE FUNCTION
public.n6_ai_strategy_episode_locked_fields_immutable_v1()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF OLD.ai_user_id IS DISTINCT FROM NEW.ai_user_id
     OR OLD.principal_id IS DISTINCT FROM NEW.principal_id
     OR OLD.principal_type IS DISTINCT FROM NEW.principal_type
     OR OLD.strategy_id IS DISTINCT FROM NEW.strategy_id
     OR OLD.virtual_account_id IS DISTINCT FROM NEW.virtual_account_id
     OR OLD.virtual_position_id IS DISTINCT FROM NEW.virtual_position_id
     OR OLD.holding_episode_no IS DISTINCT FROM NEW.holding_episode_no
     OR OLD.identity_key IS DISTINCT FROM NEW.identity_key
     OR OLD.locked_target_price IS DISTINCT FROM NEW.locked_target_price
     OR OLD.locked_target_quality_status IS DISTINCT FROM
          NEW.locked_target_quality_status
     OR OLD.locked_target_source_signal_projection_id IS DISTINCT FROM
          NEW.locked_target_source_signal_projection_id
     OR OLD.up_sell_reference_period IS DISTINCT FROM
          NEW.up_sell_reference_period
     OR OLD.policy_version IS DISTINCT FROM NEW.policy_version
     OR OLD.policy_hash IS DISTINCT FROM NEW.policy_hash THEN
    RAISE EXCEPTION 'strategy_episode_locked_fields_immutable';
  END IF;
  RETURN NEW;
END
$function$;

REVOKE ALL ON FUNCTION
public.n6_ai_strategy_episode_locked_fields_immutable_v1()
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;

CREATE TRIGGER trg_059_n6_ai_strategy_episode_locked_fields_immutable
BEFORE UPDATE ON public.n6_ai_position_strategy_episode
FOR EACH ROW
EXECUTE FUNCTION
  public.n6_ai_strategy_episode_locked_fields_immutable_v1();

CREATE TABLE public.n6_ai_strategy_action (
  strategy_action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  strategy_episode_id BIGINT NOT NULL
    REFERENCES public.n6_ai_position_strategy_episode(
      strategy_episode_id
    ),
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user'
    CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  virtual_account_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_account(virtual_account_id),
  virtual_position_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_position(virtual_position_id),
  identity_key TEXT NOT NULL
    CHECK (identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'),
  holding_episode_no INTEGER NOT NULL CHECK (holding_episode_no > 0),
  for_trade_date DATE NOT NULL,
  action_type TEXT NOT NULL CHECK (
    action_type IN (
      'target_reduce', 'period_clear', 'pending_clear_continue'
    )
  ),
  action_status TEXT NOT NULL DEFAULT 'shadow_recorded' CHECK (
    action_status IN (
      'shadow_recorded', 'dormant', 'claimed', 'proposal_created',
      'executed', 'rejected', 'failed'
    )
  ),
  source_signal_projection_id BIGINT
    REFERENCES public.n6_ai_shared_signal_projection(
      source_signal_projection_id
    ),
  source_virtual_quote_snapshot_id BIGINT
    REFERENCES public.n6_virtual_quote_snapshot(
      virtual_quote_snapshot_id
    ),
  server_sellable_quantity NUMERIC(24,4) NOT NULL
    CHECK (server_sellable_quantity > 0),
  planned_quantity NUMERIC(24,4) NOT NULL
    CHECK (
      planned_quantity > 0
      AND planned_quantity <= server_sellable_quantity
    ),
  locked_target_price NUMERIC(24,8)
    CHECK (locked_target_price IS NULL OR locked_target_price > 0),
  execution_authorized BOOLEAN NOT NULL DEFAULT false,
  proposal_id BIGINT,
  idempotency_key TEXT NOT NULL UNIQUE
    CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
  audit_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  FOREIGN KEY (
    strategy_episode_id, ai_user_id, principal_id, principal_type,
    strategy_id, virtual_account_id, virtual_position_id,
    identity_key, holding_episode_no
  ) REFERENCES public.n6_ai_position_strategy_episode (
    strategy_episode_id, ai_user_id, principal_id, principal_type,
    strategy_id, virtual_account_id, virtual_position_id,
    identity_key, holding_episode_no
  ),
  CHECK (execution_authorized = false),
  CHECK (jsonb_typeof(audit_payload_json) = 'object'),
  CHECK (
    action_type <> 'target_reduce'
    OR (
      locked_target_price IS NOT NULL
      AND source_virtual_quote_snapshot_id IS NOT NULL
    )
  ),
  CHECK (
    action_type <> 'period_clear'
    OR source_signal_projection_id IS NOT NULL
  )
);

CREATE UNIQUE INDEX idx_059_n6_ai_strategy_target_reduce_once
ON public.n6_ai_strategy_action(
  virtual_account_id, virtual_position_id,
  holding_episode_no, locked_target_price
)
WHERE action_type = 'target_reduce'
  AND action_status NOT IN ('rejected', 'failed');

CREATE INDEX idx_059_n6_ai_strategy_action_pending
ON public.n6_ai_strategy_action(action_status, action_type, strategy_action_id);

CREATE TABLE public.n6_ai_candidate_rank_audit (
  candidate_rank_audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ai_context_snapshot_id BIGINT NOT NULL
    REFERENCES public.n6_ai_context_snapshot(ai_context_snapshot_id),
  ai_user_id BIGINT NOT NULL REFERENCES public.n6_ai_user(ai_user_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL DEFAULT 'ai_user'
    CHECK (principal_type = 'ai_user'),
  strategy_id BIGINT NOT NULL REFERENCES public.n6_strategy(strategy_id),
  virtual_account_id BIGINT NOT NULL
    REFERENCES public.n6_virtual_account(virtual_account_id),
  for_trade_date DATE NOT NULL,
  source_signal_projection_id BIGINT
    REFERENCES public.n6_ai_shared_signal_projection(
      source_signal_projection_id
    ),
  identity_key TEXT,
  financial_score_raw NUMERIC(18,8),
  financial_rank_score NUMERIC(18,8) NOT NULL,
  score_status TEXT NOT NULL CHECK (score_status IN ('available', 'missing')),
  index_hint_evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  board_hint_evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  index_membership_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  board_membership_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  index_hint_adjustment INTEGER NOT NULL
    CHECK (index_hint_adjustment BETWEEN -1 AND 1),
  board_hint_adjustment INTEGER NOT NULL
    CHECK (board_hint_adjustment BETWEEN -1 AND 1),
  index_hint_conflict_zeroed BOOLEAN NOT NULL,
  board_hint_conflict_zeroed BOOLEAN NOT NULL,
  hint_adjustment INTEGER GENERATED ALWAYS AS (
    index_hint_adjustment + board_hint_adjustment
  ) STORED CHECK (hint_adjustment BETWEEN -2 AND 2),
  decision_rank_score NUMERIC(20,8) GENERATED ALWAYS AS (
    financial_rank_score
      + index_hint_adjustment
      + board_hint_adjustment
  ) STORED,
  candidate_qualified BOOLEAN NOT NULL,
  strategy_version TEXT NOT NULL
    DEFAULT 'n6_ai_investor_strategy_policy_v1'
    CHECK (strategy_version = 'n6_ai_investor_strategy_policy_v1'),
  strategy_hash TEXT NOT NULL CHECK (strategy_hash ~ '^[0-9a-f]{64}$'),
  knowledge_bundle_hash TEXT NOT NULL
    CHECK (knowledge_bundle_hash ~ '^[0-9a-f]{64}$'),
  audit_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  FOREIGN KEY (principal_id, principal_type)
    REFERENCES public.n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(index_hint_evidence_refs) = 'array'),
  CHECK (jsonb_typeof(board_hint_evidence_refs) = 'array'),
  CHECK (jsonb_typeof(index_membership_refs) = 'array'),
  CHECK (jsonb_typeof(board_membership_refs) = 'array'),
  CHECK (jsonb_typeof(audit_payload_json) = 'object'),
  CHECK (
    (
      (
        source_signal_projection_id IS NULL
        AND identity_key IS NULL
        AND audit_payload_json->>'source' =
              'strategy_workset_anchor'
        AND audit_payload_json->>'strategy_workset_hash'
              ~ '^[0-9a-f]{64}$'
        AND financial_score_raw IS NULL
        AND financial_rank_score = 0
        AND score_status = 'missing'
        AND index_hint_evidence_refs = '[]'::jsonb
        AND board_hint_evidence_refs = '[]'::jsonb
        AND index_membership_refs = '[]'::jsonb
        AND board_membership_refs = '[]'::jsonb
        AND index_hint_adjustment = 0
        AND board_hint_adjustment = 0
        AND index_hint_conflict_zeroed = false
        AND board_hint_conflict_zeroed = false
        AND candidate_qualified = false
      )
      OR
      (
        source_signal_projection_id IS NOT NULL
        AND identity_key IS NOT NULL
        AND identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
        AND audit_payload_json->>'source' =
              'approved_n6_strategy_context'
      )
    ) IS TRUE
  ),
  CHECK (
    (financial_score_raw IS NULL AND score_status = 'missing'
     AND financial_rank_score = 0)
    OR
    (financial_score_raw IS NOT NULL AND score_status = 'available'
     AND financial_rank_score = financial_score_raw)
  ),
  UNIQUE NULLS NOT DISTINCT (
    ai_context_snapshot_id, source_signal_projection_id
  )
);

REVOKE ALL ON TABLE public.n6_ai_position_strategy_episode
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON TABLE public.n6_ai_strategy_action
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON TABLE public.n6_ai_candidate_rank_audit
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;

REVOKE ALL ON SEQUENCE
  public.n6_ai_position_strategy_episode_strategy_episode_id_seq
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON SEQUENCE
  public.n6_ai_strategy_action_strategy_action_id_seq
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON SEQUENCE
  public.n6_ai_candidate_rank_audit_candidate_rank_audit_id_seq
  FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;

ALTER TABLE public.n6_virtual_trade_proposal
  DROP CONSTRAINT n6_virtual_trade_proposal_055_actor_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_source_type_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_signal_source_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_position_source_ck,
  ADD COLUMN strategy_action_id BIGINT
    REFERENCES public.n6_ai_strategy_action(strategy_action_id),
  ADD CONSTRAINT n6_virtual_trade_proposal_059_actor_ck CHECK (
    (
      principal_type IN ('admin', 'human_user')
      AND user_id IS NOT NULL
      AND actor_ai_user_id IS NULL
      AND source_ai_decision_id IS NULL
      AND strategy_action_id IS NULL
    )
    OR
    (
      principal_type = 'ai_user'
      AND user_id IS NULL
      AND actor_ai_user_id IS NOT NULL
      AND (
        (
          source_type IN ('signal', 'ai_risk')
          AND source_ai_decision_id IS NOT NULL
          AND strategy_action_id IS NULL
        )
        OR
        (
          source_type = 'stop_loss'
          AND source_ai_decision_id IS NULL
          AND strategy_action_id IS NULL
        )
        OR
        (
          source_type IN (
            'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
          )
          AND source_ai_decision_id IS NULL
          AND strategy_action_id IS NOT NULL
        )
      )
    )
  ),
  ADD CONSTRAINT n6_virtual_trade_proposal_059_source_type_ck CHECK (
    source_type IN (
      'signal', 'manual_position', 'stop_loss', 'ai_risk',
      'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
    )
  ),
  ADD CONSTRAINT n6_virtual_trade_proposal_059_signal_source_ck CHECK (
    (source_type = 'signal' AND source_signal_projection_id IS NOT NULL)
    OR (source_type <> 'signal' AND source_signal_projection_id IS NULL)
  ),
  ADD CONSTRAINT n6_virtual_trade_proposal_059_position_source_ck CHECK (
    (
      source_type IN (
        'manual_position', 'stop_loss', 'ai_risk',
        'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
      )
      AND source_virtual_position_id IS NOT NULL
    )
    OR source_type = 'signal'
  ),
  ADD CONSTRAINT n6_virtual_trade_proposal_059_strategy_action_ck CHECK (
    (
      source_type IN (
        'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
      )
      AND strategy_action_id IS NOT NULL
    )
    OR
    (
      source_type NOT IN (
        'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
      )
      AND strategy_action_id IS NULL
    )
  );

CREATE UNIQUE INDEX idx_059_n6_virtual_trade_proposal_strategy_action
ON public.n6_virtual_trade_proposal(strategy_action_id)
WHERE strategy_action_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.n6_ai_strategy_context_load_v1(
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
  base_result jsonb;
  context_snapshot_id bigint;
  snapshot_source_signal_ids jsonb;
  snapshot_workset_hash text;
  strategy_candidates jsonb;
  strategy_workset_hash text;
BEGIN
  IF SESSION_USER <> 'n6_ai_agent'
     OR p_for_trade_date IS NULL
     OR p_max_signals <> 1000
     OR p_knowledge_bundle_hash !~ '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_strategy_context_request'
    );
  END IF;

  base_result := public.n6_ai_agent_context_load_v2(
    p_run_bucket, p_for_trade_date, p_max_signals,
    p_knowledge_bundle_hash
  );
  IF COALESCE((base_result->>'ok')::boolean, false) = false
     OR base_result->>'status' NOT IN ('ready', 'already_processed') THEN
    RETURN base_result;
  END IF;
  IF COALESCE(base_result->>'context_snapshot_id', '') !~ '^[0-9]+$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_context_snapshot_missing'
    );
  END IF;
  context_snapshot_id := (base_result->>'context_snapshot_id')::bigint;

  SELECT snapshot.source_signal_projection_ids_json,
         snapshot.workset_hash
    INTO snapshot_source_signal_ids, snapshot_workset_hash
  FROM public.n6_ai_context_snapshot snapshot
  WHERE snapshot.ai_context_snapshot_id = context_snapshot_id
    AND snapshot.for_trade_date = p_for_trade_date
    AND snapshot.run_bucket = p_run_bucket
    AND snapshot.principal_type = 'ai_user'
    AND snapshot.context_status = 'frozen'
    AND snapshot.knowledge_bundle_hash = p_knowledge_bundle_hash
  FOR SHARE OF snapshot;
  IF NOT FOUND
     OR pg_catalog.jsonb_typeof(snapshot_source_signal_ids) <> 'array'
     OR snapshot_workset_hash !~ '^[0-9a-f]{64}$' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_context_snapshot_contract_mismatch'
    );
  END IF;

  WITH stock_candidate AS (
    SELECT signal.source_signal_projection_id,
           signal.identity_key,
           signal.reference_target_price,
           signal.target_quality_status,
           signal.up_sell_reference_period,
           signal.financial_score_raw,
           COALESCE(signal.financial_score_raw, 0)::numeric(18,8)
             AS financial_rank_score,
           CASE WHEN signal.financial_score_raw IS NULL
                THEN 'missing' ELSE 'available' END AS score_status
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
      AND signal.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND signal.direction = 'buy'
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND signal.strategy_context_version =
            'n6_ai_investor_strategy_policy_v1'
      AND snapshot_source_signal_ids @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
  ), index_membership_ranked AS (
    SELECT membership.stock_identity_key,
           membership.index_identity_key,
           membership.trade_date,
           membership.source_version,
           pg_catalog.row_number() OVER (
             PARTITION BY membership.stock_identity_key,
                          membership.index_identity_key
             ORDER BY membership.trade_date DESC NULLS LAST,
                      membership.created_at DESC NULLS LAST,
                      membership.source_version DESC NULLS LAST
           ) AS membership_rank,
           pg_catalog.count(*) OVER (
             PARTITION BY membership.stock_identity_key,
                          membership.index_identity_key,
                          membership.trade_date,
                          membership.created_at,
                          membership.source_version
           ) AS membership_tie_count
    FROM public.v_n6_index_membership_fact membership
    WHERE membership.stock_identity_key
            ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND membership.index_identity_key
            ~ '^index:(SH|SZ):[0-9]{6}$'
      AND membership.created_at IS NOT NULL
      AND membership.source_version IS NOT NULL
      AND pg_catalog.btrim(membership.source_version) <> ''
      AND membership.trade_date ~ '^[0-9]{8}$'
      AND membership.trade_date <= pg_catalog.to_char(
            p_for_trade_date, 'YYYYMMDD'
          )
  ), index_membership AS (
    SELECT *
    FROM index_membership_ranked
    WHERE membership_rank = 1
      AND membership_tie_count = 1
  ), index_hint AS (
    SELECT membership.stock_identity_key,
           pg_catalog.jsonb_agg(
             DISTINCT pg_catalog.jsonb_build_object(
               'source_signal_projection_id',
                 hint.source_signal_projection_id,
               'identity_key', hint.identity_key,
               'direction', hint.direction
             )
             ORDER BY pg_catalog.jsonb_build_object(
               'source_signal_projection_id',
                 hint.source_signal_projection_id,
               'identity_key', hint.identity_key,
               'direction', hint.direction
             )
           ) AS evidence_refs,
           pg_catalog.jsonb_agg(
             DISTINCT pg_catalog.jsonb_build_object(
               'identity_key', membership.index_identity_key,
               'trade_date', membership.trade_date,
               'source_version', membership.source_version
             )
             ORDER BY pg_catalog.jsonb_build_object(
               'identity_key', membership.index_identity_key,
               'trade_date', membership.trade_date,
               'source_version', membership.source_version
             )
           ) AS membership_refs,
           pg_catalog.bool_or(hint.direction = 'buy') AS has_buy,
           pg_catalog.bool_or(hint.direction = 'sell') AS has_sell
    FROM index_membership membership
    JOIN public.n6_ai_shared_signal_projection hint
      ON hint.identity_key = membership.index_identity_key
     AND hint.asset_kind = 'index'
     AND hint.for_trade_date = p_for_trade_date
     AND hint.shared_status = 'active'
     AND hint.action_state IN ('eligible', 'executed')
     AND hint.direction IN ('buy', 'sell')
     AND snapshot_source_signal_ids @>
           pg_catalog.jsonb_build_array(
             hint.source_signal_projection_id
           )
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           hint.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
     AND (
       (
         hint.direction = 'buy'
         AND (
           COALESCE(
             hint.original_condition_key ~ '^BUY_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^BUY_HINT(?::|$)', false
           )
         )
         AND NOT (
           COALESCE(
             hint.original_condition_key ~ '^SELL_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^SELL_HINT(?::|$)', false
           )
         )
       )
       OR
       (
         hint.direction = 'sell'
         AND (
           COALESCE(
             hint.original_condition_key ~ '^SELL_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^SELL_HINT(?::|$)', false
           )
         )
         AND NOT (
           COALESCE(
             hint.original_condition_key ~ '^BUY_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^BUY_HINT(?::|$)', false
           )
         )
       )
     )
    GROUP BY membership.stock_identity_key
  ), board_membership_ranked AS (
    SELECT membership.stock_identity_key,
           membership.board_identity_key,
           membership.trade_date,
           membership.source_version,
           pg_catalog.row_number() OVER (
             PARTITION BY membership.stock_identity_key,
                          membership.board_identity_key
             ORDER BY membership.trade_date DESC NULLS LAST,
                      membership.created_at DESC NULLS LAST,
                      membership.source_version DESC NULLS LAST
           ) AS membership_rank,
           pg_catalog.count(*) OVER (
             PARTITION BY membership.stock_identity_key,
                          membership.board_identity_key,
                          membership.trade_date,
                          membership.created_at,
                          membership.source_version
           ) AS membership_tie_count
    FROM public.v_n6_board_membership_fact membership
    WHERE membership.stock_identity_key
            ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND membership.board_identity_key IS NOT NULL
      AND pg_catalog.btrim(membership.board_identity_key) <> ''
      AND membership.created_at IS NOT NULL
      AND membership.source_version IS NOT NULL
      AND pg_catalog.btrim(membership.source_version) <> ''
      AND membership.trade_date ~ '^[0-9]{8}$'
      AND membership.trade_date <= pg_catalog.to_char(
            p_for_trade_date, 'YYYYMMDD'
          )
  ), board_membership AS (
    SELECT *
    FROM board_membership_ranked
    WHERE membership_rank = 1
      AND membership_tie_count = 1
  ), board_hint AS (
    SELECT membership.stock_identity_key,
           pg_catalog.jsonb_agg(
             DISTINCT pg_catalog.jsonb_build_object(
               'source_signal_projection_id',
                 hint.source_signal_projection_id,
               'identity_key', hint.identity_key,
               'direction', hint.direction
             )
             ORDER BY pg_catalog.jsonb_build_object(
               'source_signal_projection_id',
                 hint.source_signal_projection_id,
               'identity_key', hint.identity_key,
               'direction', hint.direction
             )
           ) AS evidence_refs,
           pg_catalog.jsonb_agg(
             DISTINCT pg_catalog.jsonb_build_object(
               'identity_key', membership.board_identity_key,
               'trade_date', membership.trade_date,
               'source_version', membership.source_version
             )
             ORDER BY pg_catalog.jsonb_build_object(
               'identity_key', membership.board_identity_key,
               'trade_date', membership.trade_date,
               'source_version', membership.source_version
             )
           ) AS membership_refs,
           pg_catalog.bool_or(hint.direction = 'buy') AS has_buy,
           pg_catalog.bool_or(hint.direction = 'sell') AS has_sell
    FROM board_membership membership
    JOIN public.n6_ai_shared_signal_projection hint
      ON hint.identity_key = membership.board_identity_key
     AND hint.asset_kind = 'board'
     AND hint.for_trade_date = p_for_trade_date
     AND hint.shared_status = 'active'
     AND hint.action_state IN ('eligible', 'executed')
     AND hint.direction IN ('buy', 'sell')
     AND snapshot_source_signal_ids @>
           pg_catalog.jsonb_build_array(
             hint.source_signal_projection_id
           )
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           hint.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
     AND (
       (
         hint.direction = 'buy'
         AND (
           COALESCE(
             hint.original_condition_key ~ '^BUY_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^BUY_HINT(?::|$)', false
           )
         )
         AND NOT (
           COALESCE(
             hint.original_condition_key ~ '^SELL_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^SELL_HINT(?::|$)', false
           )
         )
       )
       OR
       (
         hint.direction = 'sell'
         AND (
           COALESCE(
             hint.original_condition_key ~ '^SELL_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^SELL_HINT(?::|$)', false
           )
         )
         AND NOT (
           COALESCE(
             hint.original_condition_key ~ '^BUY_HINT(?::|$)', false
           )
           OR COALESCE(
             hint.condition_key ~ '^BUY_HINT(?::|$)', false
           )
         )
       )
     )
    GROUP BY membership.stock_identity_key
  ), adjusted AS (
    SELECT stock.*,
           COALESCE(index_hint.evidence_refs, '[]'::jsonb)
             AS index_hint_evidence_refs,
           COALESCE(board_hint.evidence_refs, '[]'::jsonb)
             AS board_hint_evidence_refs,
           COALESCE(index_hint.membership_refs, '[]'::jsonb)
             AS index_membership_refs,
           COALESCE(board_hint.membership_refs, '[]'::jsonb)
             AS board_membership_refs,
           CASE
             WHEN index_hint.has_buy AND index_hint.has_sell THEN 0
             WHEN index_hint.has_buy THEN 1
             WHEN index_hint.has_sell THEN -1
             ELSE 0
           END AS index_hint_adjustment,
           CASE
             WHEN board_hint.has_buy AND board_hint.has_sell THEN 0
             WHEN board_hint.has_buy THEN 1
             WHEN board_hint.has_sell THEN -1
             ELSE 0
           END AS board_hint_adjustment,
           COALESCE(index_hint.has_buy AND index_hint.has_sell, false)
             AS index_hint_conflict_zeroed,
           COALESCE(board_hint.has_buy AND board_hint.has_sell, false)
             AS board_hint_conflict_zeroed
    FROM stock_candidate stock
    LEFT JOIN index_hint
      ON index_hint.stock_identity_key = stock.identity_key
    LEFT JOIN board_hint
      ON board_hint.stock_identity_key = stock.identity_key
  )
  SELECT COALESCE(
           pg_catalog.jsonb_agg(
             pg_catalog.jsonb_build_object(
               'source_signal_projection_id',
                 source_signal_projection_id,
               'identity_key', identity_key,
               'reference_target_price', reference_target_price,
               'target_quality_status', target_quality_status,
               'up_sell_reference_period', up_sell_reference_period,
               'financial_score_raw', financial_score_raw,
               'financial_rank_score', financial_rank_score,
               'score_status', score_status,
               'index_hint_evidence_refs',
                 index_hint_evidence_refs,
               'board_hint_evidence_refs',
                 board_hint_evidence_refs,
               'index_membership_refs', index_membership_refs,
               'board_membership_refs', board_membership_refs,
               'index_hint_adjustment', index_hint_adjustment,
               'board_hint_adjustment', board_hint_adjustment,
               'index_hint_conflict_zeroed',
                 index_hint_conflict_zeroed,
               'board_hint_conflict_zeroed',
                 board_hint_conflict_zeroed,
               'hint_adjustment',
                 index_hint_adjustment + board_hint_adjustment,
               'decision_rank_score',
                 financial_rank_score
                   + index_hint_adjustment
                   + board_hint_adjustment
             )
             ORDER BY (
               financial_rank_score
                 + index_hint_adjustment
                 + board_hint_adjustment
             ) DESC, identity_key, source_signal_projection_id
           ),
           '[]'::jsonb
         )
    INTO strategy_candidates
  FROM adjusted;

  strategy_workset_hash := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        pg_catalog.jsonb_build_object(
          'base_snapshot_workset_hash', snapshot_workset_hash,
          'strategy_candidates', strategy_candidates
        )::text,
        'UTF8'
      )
    ),
    'hex'
  );

  RETURN base_result || pg_catalog.jsonb_build_object(
    'strategy_contract_version',
      'n6_ai_investor_strategy_policy_v1',
    'strategy_context_snapshot_id', context_snapshot_id,
    'base_snapshot_workset_hash', snapshot_workset_hash,
    'strategy_workset_hash', strategy_workset_hash,
    'strategy_candidates', strategy_candidates,
    'strategy_runtime_mode', 'shadow'
  );
END
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
        ELSE pg_catalog.least(
          server_sellable_quantity,
          pg_catalog.greatest(
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

CREATE OR REPLACE FUNCTION
public.n6_ai_strategy_proposal_create_confirm_v1(
  p_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  execution_activated constant boolean := false;
BEGIN
  IF SESSION_USER <> 'n6_virtual_executor' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_executor_authority'
    );
  END IF;
  IF execution_activated IS DISTINCT FROM true THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_execution_not_activated'
    );
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'ok', false, 'status', 'strategy_execution_not_activated'
  );
END
$function$;

CREATE OR REPLACE FUNCTION
public.n6_ai_executor_strategy_action_apply_v1(
  p_strategy_action_id bigint,
  p_executor_run_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  execution_activated constant boolean := false;
BEGIN
  IF SESSION_USER <> 'n6_virtual_executor' THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'invalid_executor_authority'
    );
  END IF;
  IF execution_activated IS DISTINCT FROM true THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'strategy_execution_not_activated'
    );
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'ok', false, 'status', 'strategy_execution_not_activated'
  );
END
$function$;

REVOKE ALL ON FUNCTION public.n6_ai_strategy_context_load_v1(
  text,date,integer,text
) FROM PUBLIC, n6_ai_agent, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION public.n6_ai_strategy_shadow_evaluate(
  date,text,text
) FROM PUBLIC, n6_btrack_web, n6_virtual_executor;
REVOKE ALL ON FUNCTION
public.n6_ai_strategy_proposal_create_confirm_v1(
  jsonb
) FROM PUBLIC, n6_ai_agent, n6_btrack_web;
REVOKE ALL ON FUNCTION
public.n6_ai_executor_strategy_action_apply_v1(
  bigint,text
) FROM PUBLIC, n6_ai_agent, n6_btrack_web;

GRANT EXECUTE ON FUNCTION public.n6_ai_strategy_shadow_evaluate(
  date,text,text
) TO n6_ai_agent;
GRANT EXECUTE ON FUNCTION
public.n6_ai_strategy_proposal_create_confirm_v1(
  jsonb
) TO n6_virtual_executor;
GRANT EXECUTE ON FUNCTION
public.n6_ai_executor_strategy_action_apply_v1(
  bigint,text
) TO n6_virtual_executor;

DO $postflight$
DECLARE
  function_name text;
  function_owner text;
  function_security_definer boolean;
  function_config text[];
  function_expectation record;
  role_expectation record;
  relation_expectation record;
  function_oid oid;
  role_oid oid;
  allowed_role_oid oid;
  relation_oid oid;
  relation_kind "char";
  direct_execute_count integer;
  direct_grantable_count integer;
  public_privilege_count integer;
  unexpected_acl_count integer;
  privilege_name text;
BEGIN
  FOREACH function_name IN ARRAY ARRAY[
    'public.n6_ai_strategy_context_load_v1(text,date,integer,text)',
    'public.n6_ai_strategy_shadow_evaluate(date,text,text)',
    'public.n6_ai_strategy_proposal_create_confirm_v1(jsonb)',
    'public.n6_ai_executor_strategy_action_apply_v1(bigint,text)',
    'public.n6_ai_shared_strategy_fields_capture_v1()',
    'public.n6_ai_strategy_episode_locked_fields_immutable_v1()'
  ]
  LOOP
    SELECT pg_catalog.pg_get_userbyid(procedure.proowner),
           procedure.prosecdef, procedure.proconfig
      INTO function_owner, function_security_definer, function_config
    FROM pg_catalog.pg_proc procedure
    WHERE procedure.oid = function_name::pg_catalog.regprocedure;
    IF function_owner <> current_user
       OR function_security_definer IS DISTINCT FROM true
       OR function_config IS DISTINCT FROM
            ARRAY['search_path=pg_catalog']::text[] THEN
      RAISE EXCEPTION '059_function_authority_drift: %', function_name;
    END IF;
  END LOOP;

  FOR function_expectation IN
    SELECT expected.function_name, expected.allowed_role
    FROM (VALUES
      ('public.n6_ai_strategy_context_load_v1(text,date,integer,text)'::text,
       'none'::text),
      ('public.n6_ai_strategy_shadow_evaluate(date,text,text)'::text,
       'n6_ai_agent'::text),
      ('public.n6_ai_strategy_proposal_create_confirm_v1(jsonb)'::text,
       'n6_virtual_executor'::text),
      ('public.n6_ai_executor_strategy_action_apply_v1(bigint,text)'::text,
       'n6_virtual_executor'::text),
      ('public.n6_ai_shared_strategy_fields_capture_v1()'::text,
       'none'::text),
      ('public.n6_ai_strategy_episode_locked_fields_immutable_v1()'::text,
       'none'::text)
    ) expected(function_name, allowed_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      function_expectation.function_name
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %',
        function_expectation.function_name;
    END IF;

    allowed_role_oid := NULL;
    IF function_expectation.allowed_role <> 'none' THEN
      SELECT role.oid
        INTO allowed_role_oid
      FROM pg_catalog.pg_roles role
      WHERE role.rolname = function_expectation.allowed_role;
      IF allowed_role_oid IS NULL THEN
        RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %.%',
          function_expectation.function_name,
          function_expectation.allowed_role;
      END IF;
    END IF;

    SELECT pg_catalog.count(*)
      INTO unexpected_acl_count
    FROM pg_catalog.pg_proc function_row
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        function_row.proacl,
        pg_catalog.acldefault('f', function_row.proowner)
      )
    ) function_acl
    WHERE function_row.oid = function_oid
      AND function_acl.grantee <> function_row.proowner
      AND (
        allowed_role_oid IS NULL
        OR function_acl.grantee IS DISTINCT FROM allowed_role_oid
        OR function_acl.privilege_type <> 'EXECUTE'
        OR function_acl.is_grantable = true
      );
    IF unexpected_acl_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %',
        function_expectation.function_name;
    END IF;

    SELECT pg_catalog.count(*)
      INTO public_privilege_count
    FROM pg_catalog.pg_proc function_row
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        function_row.proacl,
        pg_catalog.acldefault('f', function_row.proowner)
      )
    ) public_acl
    WHERE function_row.oid = function_oid
      AND public_acl.grantee = 0
      AND public_acl.privilege_type = 'EXECUTE';
    IF public_privilege_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %',
        function_expectation.function_name;
    END IF;

    FOR role_expectation IN
      SELECT expected_role.role_name
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
      IF role_oid IS NULL THEN
        RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %.%',
          function_expectation.function_name,
          role_expectation.role_name;
      END IF;

      SELECT pg_catalog.count(*)
        INTO direct_execute_count
      FROM pg_catalog.pg_proc function_row
      CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) direct_acl
      WHERE function_row.oid = function_oid
        AND direct_acl.grantee = role_oid
        AND direct_acl.privilege_type = 'EXECUTE';
      SELECT pg_catalog.count(*)
        INTO direct_grantable_count
      FROM pg_catalog.pg_proc function_row
      CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(
          function_row.proacl,
          pg_catalog.acldefault('f', function_row.proowner)
        )
      ) direct_acl
      WHERE function_row.oid = function_oid
        AND direct_acl.grantee = role_oid
        AND direct_acl.privilege_type = 'EXECUTE'
        AND direct_acl.is_grantable = true;

      IF role_expectation.role_name =
           function_expectation.allowed_role THEN
        IF NOT pg_catalog.has_function_privilege(
                 role_expectation.role_name,
                 function_expectation.function_name,
                 'EXECUTE'
               )
           OR direct_execute_count <> 1
           OR direct_grantable_count <> 0 THEN
          RAISE EXCEPTION
            '059_postflight_function_acl_matrix_drift: %.%',
            function_expectation.function_name,
            role_expectation.role_name;
        END IF;
      ELSIF pg_catalog.has_function_privilege(
              role_expectation.role_name,
              function_expectation.function_name,
              'EXECUTE'
            )
            OR direct_execute_count <> 0
            OR direct_grantable_count <> 0 THEN
        RAISE EXCEPTION '059_postflight_function_acl_matrix_drift: %.%',
          function_expectation.function_name,
          role_expectation.role_name;
      END IF;
    END LOOP;
  END LOOP;

  FOR relation_expectation IN
    SELECT expected_relation.relation_name
    FROM (VALUES
      ('public.n6_ai_position_strategy_episode'::text),
      ('public.n6_ai_strategy_action'::text),
      ('public.n6_ai_candidate_rank_audit'::text)
    ) expected_relation(relation_name)
  LOOP
    relation_oid := pg_catalog.to_regclass(
      relation_expectation.relation_name
    );
    SELECT relation.relkind
      INTO relation_kind
    FROM pg_catalog.pg_class relation
    WHERE relation.oid = relation_oid;
    IF relation_oid IS NULL OR relation_kind IS DISTINCT FROM 'r' THEN
      RAISE EXCEPTION '059_postflight_table_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    SELECT pg_catalog.count(*)
      INTO unexpected_acl_count
    FROM pg_catalog.pg_class relation
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('r', relation.relowner)
      )
    ) table_acl
    WHERE relation.oid = relation_oid
      AND table_acl.grantee <> relation.relowner;
    IF unexpected_acl_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_table_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    SELECT pg_catalog.count(*)
      INTO public_privilege_count
    FROM pg_catalog.pg_class relation
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('r', relation.relowner)
      )
    ) public_acl
    WHERE relation.oid = relation_oid
      AND public_acl.grantee = 0
      AND public_acl.privilege_type = ANY (ARRAY[
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
        'REFERENCES', 'TRIGGER'
      ]::text[]);
    IF public_privilege_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_table_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    FOR role_expectation IN
      SELECT expected_role.role_name
      FROM (VALUES
        ('n6_ai_agent'::text),
        ('n6_btrack_web'::text),
        ('n6_virtual_executor'::text)
      ) expected_role(role_name)
    LOOP
      IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles role
        WHERE role.rolname = role_expectation.role_name
      ) THEN
        RAISE EXCEPTION '059_postflight_table_acl_drift: %.%',
          relation_expectation.relation_name,
          role_expectation.role_name;
      END IF;
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
          RAISE EXCEPTION '059_postflight_table_acl_drift: %.%.%',
            relation_expectation.relation_name,
            role_expectation.role_name,
            privilege_name;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;

  FOR relation_expectation IN
    SELECT expected_relation.relation_name
    FROM (VALUES
      ('public.n6_ai_position_strategy_episode_strategy_episode_id_seq'::text),
      ('public.n6_ai_strategy_action_strategy_action_id_seq'::text),
      ('public.n6_ai_candidate_rank_audit_candidate_rank_audit_id_seq'::text)
    ) expected_relation(relation_name)
  LOOP
    relation_oid := pg_catalog.to_regclass(
      relation_expectation.relation_name
    );
    SELECT relation.relkind
      INTO relation_kind
    FROM pg_catalog.pg_class relation
    WHERE relation.oid = relation_oid;
    IF relation_oid IS NULL OR relation_kind IS DISTINCT FROM 'S' THEN
      RAISE EXCEPTION '059_postflight_sequence_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    SELECT pg_catalog.count(*)
      INTO unexpected_acl_count
    FROM pg_catalog.pg_class relation
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('s', relation.relowner)
      )
    ) sequence_acl
    WHERE relation.oid = relation_oid
      AND sequence_acl.grantee <> relation.relowner;
    IF unexpected_acl_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_sequence_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    SELECT pg_catalog.count(*)
      INTO public_privilege_count
    FROM pg_catalog.pg_class relation
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('s', relation.relowner)
      )
    ) public_acl
    WHERE relation.oid = relation_oid
      AND public_acl.grantee = 0
      AND public_acl.privilege_type = ANY (
        ARRAY['USAGE', 'SELECT', 'UPDATE']::text[]
      );
    IF public_privilege_count <> 0 THEN
      RAISE EXCEPTION '059_postflight_sequence_acl_drift: %',
        relation_expectation.relation_name;
    END IF;

    FOR role_expectation IN
      SELECT expected_role.role_name
      FROM (VALUES
        ('n6_ai_agent'::text),
        ('n6_btrack_web'::text),
        ('n6_virtual_executor'::text)
      ) expected_role(role_name)
    LOOP
      IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles role
        WHERE role.rolname = role_expectation.role_name
      ) THEN
        RAISE EXCEPTION '059_postflight_sequence_acl_drift: %.%',
          relation_expectation.relation_name,
          role_expectation.role_name;
      END IF;
      FOREACH privilege_name IN ARRAY ARRAY[
        'USAGE', 'SELECT', 'UPDATE'
      ]::text[]
      LOOP
        IF pg_catalog.has_sequence_privilege(
             role_expectation.role_name,
             relation_expectation.relation_name,
             privilege_name
           ) THEN
          RAISE EXCEPTION '059_postflight_sequence_acl_drift: %.%.%',
            relation_expectation.relation_name,
            role_expectation.role_name,
            privilege_name;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
END
$postflight$;

COMMIT;
