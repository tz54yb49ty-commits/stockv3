-- Restore the exact pre-088 N6 proposal transition guard definition.
-- Historical proposals, orders, trades, cash, positions and lots are retained.

BEGIN;

DO $preflight$
DECLARE
  guard_oid oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_proposal_transition_guard()'
  );
  evaluator_oid oid := pg_catalog.to_regprocedure(
    'public.n6_executor_evaluate_next_stop_loss(text)'
  );
  guard_proc record;
  evaluator_proc record;
  guard_sha text;
  evaluator_sha text;
  unexpected_guard_execute boolean;
  business_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  IF current_user <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '088_rollback_owner_execution_required';
  END IF;
  IF guard_oid IS NULL OR evaluator_oid IS NULL THEN
    RAISE EXCEPTION '088_rollback_required_function_missing';
  END IF;

  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO guard_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = guard_oid;
  SELECT p.prosrc INTO evaluator_proc
  FROM pg_catalog.pg_proc p
  WHERE p.oid = evaluator_oid;
  guard_sha := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(guard_proc.prosrc, 'UTF8')),
    'hex'
  );
  evaluator_sha := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(evaluator_proc.prosrc, 'UTF8')),
    'hex'
  );
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
    ) acl
    WHERE target.oid = guard_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
  ) INTO unexpected_guard_execute;

  IF guard_proc.owner_name <> 'ashare_v3_user'
     OR guard_proc.prosecdef IS DISTINCT FROM true
     OR guard_proc.provolatile <> 'v'
     OR guard_proc.proparallel <> 'u'
     OR guard_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR guard_sha <>
        '28aaea4f21b22cece83fa6f494d6d19ad67ec753af3778765749094ccbb21f58'
     OR evaluator_sha <>
        'fe3b0ac7297f24fc0a5925d178ccb1f26e575716baea48dce40ef6b2af0a1443'
     OR unexpected_guard_execute
     OR pg_catalog.has_table_privilege(
          'n6_virtual_executor', 'public.n6_virtual_trade_proposal',
          'INSERT,UPDATE,DELETE'
        ) THEN
    RAISE EXCEPTION '088_rollback_function_or_privilege_drift';
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
    'n6.migration_088_rollback_business_summary',
    business_summary::text,
    true
  );
END
$preflight$;

DO $guard_rewrite$
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

  old_text := $guard_executor_insert_088$  ELSIF TG_OP='INSERT' AND SESSION_USER='n6_virtual_executor' THEN
    IF COALESCE((
      NEW.source_type = 'stop_loss'
      AND NEW.source_id IS NOT NULL
      AND pg_catalog.btrim(NEW.source_id) <> ''
      AND NEW.source_signal_projection_id IS NULL
      AND NEW.strategy_action_id IS NULL
      AND NEW.source_virtual_position_id IS NOT NULL
      AND NEW.source_virtual_position_id > 0
      AND NEW.holding_episode_no IS NOT NULL
      AND NEW.holding_episode_no > 0
      AND NEW.asset_kind = 'stock'
      AND NEW.identity_key LIKE 'stock:%'
      AND NEW.proposal_side = 'sell'
      AND NEW.signal_reference_kind = 'stop_loss'
      AND NEW.signal_reference_price IS NOT NULL
      AND NEW.signal_reference_price > 0
      AND NEW.signal_reference_price::text NOT IN (
            'NaN', 'Infinity', '-Infinity'
          )
      AND NEW.locked_target_price IS NULL
      AND NEW.proposal_status = 'confirmed'
      AND NEW.expires_at IS NOT NULL
      AND NEW.confirmed_at IS NOT NULL
      AND NEW.expires_at > NEW.confirmed_at
      AND NEW.expires_at <= NEW.confirmed_at + interval '61 seconds'
      AND NEW.confirmed_at >=
          pg_catalog.clock_timestamp() - interval '5 seconds'
      AND NEW.confirmed_at <=
          pg_catalog.clock_timestamp() + interval '1 second'
      AND NEW.confirm_idempotency_key = 'stop_loss:' || NEW.source_id
      AND NEW.executed_virtual_order_id IS NULL
      AND NEW.executed_virtual_trade_id IS NULL
      AND NEW.executor_run_id IS NULL
      AND NEW.failure_reason IS NULL
      AND NEW.source_ai_decision_id IS NULL
      AND NEW.policy_hash = NEW.policy_version
      AND (
        (
          NEW.principal_type IN ('admin', 'human_user')
          AND NEW.user_id IS NOT NULL
          AND NEW.actor_ai_user_id IS NULL
          AND NEW.policy_version = 'n6_virtual_stop_loss_049_v1'
          AND EXISTS (
            SELECT 1
            FROM public.n6_principal principal
            WHERE principal.principal_id = NEW.principal_id
              AND principal.principal_type = NEW.principal_type
              AND principal.owner_user_id = NEW.user_id
              AND principal.principal_status = 'active'
          )
        )
        OR
        (
          NEW.principal_type = 'ai_user'
          AND NEW.user_id IS NULL
          AND NEW.actor_ai_user_id IS NOT NULL
          AND NEW.policy_version =
              'n6_ai_agent_execution_compat_057_v1'
          AND EXISTS (
            SELECT 1
            FROM public.n6_ai_user ai_user
            WHERE ai_user.ai_user_id = NEW.actor_ai_user_id
              AND ai_user.principal_id = NEW.principal_id
              AND ai_user.principal_type = NEW.principal_type
              AND ai_user.status = 'active'
          )
        )
      )
      AND pg_catalog.jsonb_typeof(NEW.source_lineage_json) = 'object'
      AND NEW.source_lineage_json ?& ARRAY[
            'virtual_position_id',
            'holding_episode_no',
            'first_trigger_quote_snapshot_id',
            'confirm_trigger_quote_snapshot_id',
            'stop_loss_price',
            'trigger_price',
            'stop_loss_source_quote_snapshot_id',
            'stop_loss_policy_version',
            'stop_loss_policy_hash',
            'executor_run_id',
            'rearmed_after_terminal_proposal_id'
          ]::text[]
      AND (
        NEW.source_lineage_json - ARRAY[
          'virtual_position_id',
          'holding_episode_no',
          'first_trigger_quote_snapshot_id',
          'confirm_trigger_quote_snapshot_id',
          'stop_loss_price',
          'trigger_price',
          'stop_loss_source_quote_snapshot_id',
          'stop_loss_policy_version',
          'stop_loss_policy_hash',
          'executor_run_id',
          'rearmed_after_terminal_proposal_id'
        ]::text[]
      ) = '{}'::jsonb
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'virtual_position_id'
          ) = 'number'
      AND (NEW.source_lineage_json->>'virtual_position_id')::bigint =
          NEW.source_virtual_position_id
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'holding_episode_no'
          ) = 'number'
      AND (NEW.source_lineage_json->>'holding_episode_no')::integer =
          NEW.holding_episode_no
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'first_trigger_quote_snapshot_id'
          ) = 'number'
      AND (
            NEW.source_lineage_json->>'first_trigger_quote_snapshot_id'
          )::bigint > 0
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'confirm_trigger_quote_snapshot_id'
          ) = 'number'
      AND (
            NEW.source_lineage_json->>'confirm_trigger_quote_snapshot_id'
          )::bigint > 0
      AND NEW.source_id =
          NEW.source_virtual_position_id::text || ':' ||
          NEW.holding_episode_no::text || ':' ||
          (NEW.source_lineage_json
             ->>'confirm_trigger_quote_snapshot_id')
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'stop_loss_price'
          ) = 'number'
      AND (NEW.source_lineage_json->>'stop_loss_price')::numeric =
          NEW.signal_reference_price
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'trigger_price'
          ) = 'number'
      AND (NEW.source_lineage_json->>'trigger_price')::numeric > 0
      AND (NEW.source_lineage_json->>'trigger_price') NOT IN (
            'NaN', 'Infinity', '-Infinity'
          )
      AND COALESCE(
            pg_catalog.btrim(
              NEW.source_lineage_json->>'executor_run_id'
            ),
            ''
          ) <> ''
      AND EXISTS (
        SELECT 1
        FROM public.n6_virtual_position position
        WHERE position.virtual_position_id =
              NEW.source_virtual_position_id
          AND position.virtual_account_id = NEW.virtual_account_id
          AND position.principal_id = NEW.principal_id
          AND position.principal_type = NEW.principal_type
          AND position.asset_kind = NEW.asset_kind
          AND position.identity_key = NEW.identity_key
          AND position.position_status = 'open_virtual'
          AND position.quantity > 0
          AND position.holding_episode_no = NEW.holding_episode_no
          AND position.stop_loss_status = 'frozen'
          AND position.stop_loss_price =
              NEW.signal_reference_price
          AND position.stop_loss_source_quote_snapshot_id::text
              IS NOT DISTINCT FROM
              NEW.source_lineage_json
                ->>'stop_loss_source_quote_snapshot_id'
          AND position.stop_loss_policy_version
              IS NOT DISTINCT FROM
              NEW.source_lineage_json->>'stop_loss_policy_version'
          AND position.stop_loss_policy_hash
              IS NOT DISTINCT FROM
              NEW.source_lineage_json->>'stop_loss_policy_hash'
      )
    ), false) THEN
      NULL;
    ELSE
      RAISE EXCEPTION 'executor proposal insert rejected';
    END IF;
$guard_executor_insert_088$;
  new_text := $guard_executor_insert_078$  ELSIF TG_OP='INSERT' AND SESSION_USER='n6_virtual_executor' THEN
    RAISE EXCEPTION 'executor cannot create proposal';
$guard_executor_insert_078$;

  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1
     OR pg_catalog.strpos(source_text, new_text) <> 0 THEN
    RAISE EXCEPTION '088_rollback_transition_guard_rewrite_scope_drift';
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
$guard_rewrite$;

ALTER FUNCTION public.n6_btrack_proposal_transition_guard()
  OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard()
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;

DO $postflight$
DECLARE
  guard_oid oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_proposal_transition_guard()'
  );
  guard_proc record;
  guard_sha text;
  unexpected_guard_execute boolean;
  before_summary jsonb := pg_catalog.current_setting(
    'n6.migration_088_rollback_business_summary', false
  )::jsonb;
  after_summary jsonb := '{}'::jsonb;
  relation_name text;
  row_count bigint;
BEGIN
  SELECT p.prosrc, p.prosecdef, p.provolatile, p.proparallel, p.proconfig,
         owner.rolname AS owner_name
    INTO guard_proc
  FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
  WHERE p.oid = guard_oid;
  guard_sha := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(guard_proc.prosrc, 'UTF8')),
    'hex'
  );
  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
    ) acl
    WHERE target.oid = guard_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
  ) INTO unexpected_guard_execute;

  IF guard_proc.owner_name <> 'ashare_v3_user'
     OR guard_proc.prosecdef IS DISTINCT FROM true
     OR guard_proc.provolatile <> 'v'
     OR guard_proc.proparallel <> 'u'
     OR guard_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR guard_sha <>
        '8c0e5f213c7c3e83eb7c488bb3302f94de86db98c4a95901f4776e44aec2ebf8'
     OR unexpected_guard_execute
     OR pg_catalog.has_table_privilege(
          'n6_virtual_executor', 'public.n6_virtual_trade_proposal',
          'INSERT,UPDATE,DELETE'
        ) THEN
    RAISE EXCEPTION '088_rollback_postflight_drift';
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
    RAISE EXCEPTION '088_rollback_unexpected_business_dml';
  END IF;
END
$postflight$;

COMMIT;
