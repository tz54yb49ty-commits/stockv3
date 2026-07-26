-- N6 B-track current-open-trade-date all-day manual virtual BUY.
-- REVIEWED MIGRATION: execute only through the separately authorized N6 deployment gate.
-- This migration changes no N1-N5 facts and creates no proposal, order or trade.

BEGIN;

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
     ) IS NOT NULL THEN
    RAISE EXCEPTION '064_helper_already_exists';
  END IF;
  IF pg_catalog.to_regprocedure(
       'pg_catalog.gen_random_uuid()'
     ) IS NULL THEN
    RAISE EXCEPTION '064_confirmation_generation_source_missing';
  END IF;

  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_proposal_create(text,text,bigint)',
        'n6_btrack_web',
        '9c48b25da0b8e25dfcb0887c57f0c947a57d5d647d2fe2df9d66bdf210e1189f'
      ),
      (
        'public.n6_btrack_proposal_list(text,integer)',
        'n6_btrack_web',
        'cb8347a41f10cdf8b0a74da7307ead67b35cca533cfd8cbd4478bb73990df8ce'
      ),
      (
        'public.n6_btrack_proposal_confirm(text,bigint,text)',
        'n6_btrack_web',
        'a2ded4aee0885c8ca29fe05d528ce28f29ea2f26d183cb02e0bf009ffff2b22c'
      ),
      (
        'public.n6_btrack_proposal_transition_guard()',
        NULL::text,
        '3551fd5d1137dab8eff8185fe8f9ab5e48e65b8f316f3c11abb75e80f88254f2'
      ),
      (
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        'n6_virtual_executor',
        '2ba49faf1d4f6cf5f3765b8eb892c9e900f81f6f7add6013e4e6022f10bedce3'
      )
    ) AS expected_functions(signature, allowed_role, source_sha)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '064_required_function_missing: %',
        expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = function_oid;

    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '064_baseline_definition_drift: %',
        expected.signature;
    END IF;

    SELECT
      CASE
        WHEN expected.allowed_role IS NULL THEN true
        ELSE EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc target
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              target.proacl,
              pg_catalog.acldefault('f', target.proowner)
            )
          ) acl
          JOIN pg_catalog.pg_roles role
            ON role.oid = acl.grantee
          WHERE target.oid = function_oid
            AND role.rolname = expected.allowed_role
            AND acl.privilege_type = 'EXECUTE'
            AND acl.is_grantable IS FALSE
        )
      END,
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(
            target.proacl,
            pg_catalog.acldefault('f', target.proowner)
          )
        ) acl
        LEFT JOIN pg_catalog.pg_roles role
          ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            expected.allowed_role IS NULL
            OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.allowed_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '064_baseline_acl_drift: %', expected.signature;
    END IF;
  END LOOP;
END
$preflight$;

CREATE FUNCTION public.n6_btrack_manual_signal_buy_current_scope(
  p_principal_id bigint,
  p_principal_type text,
  p_user_id bigint,
  p_virtual_account_id bigint,
  p_signal_projection_id bigint,
  p_identity_key text,
  p_signal_reference_kind text,
  p_signal_reference_price numeric,
  p_for_trade_date text
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  current_trade_date text := pg_catalog.to_char(
    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
    'YYYYMMDD'
  );
  matching_source_count integer;
  open_trade_date_count integer;
BEGIN
  IF p_principal_id IS NULL
     OR p_principal_type NOT IN ('admin', 'human_user')
     OR p_user_id IS NULL
     OR p_virtual_account_id IS NULL
     OR p_signal_projection_id IS NULL
     OR p_signal_projection_id <= 0
     OR p_identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
     OR p_signal_reference_kind NOT IN (
          'trigger_price', 'action_price'
        )
     OR p_signal_reference_price IS NULL
     OR p_signal_reference_price <= 0
     OR p_signal_reference_price::text IN (
          'NaN', 'Infinity', '-Infinity'
        )
     OR p_for_trade_date IS DISTINCT FROM current_trade_date THEN
    RETURN false;
  END IF;

  SELECT count(*)
    INTO open_trade_date_count
  FROM public.common_trade_calendar calendar
  WHERE calendar.trade_date = current_trade_date
    AND calendar.is_open = true;
  IF open_trade_date_count <> 1 THEN
    RETURN false;
  END IF;

  WITH source_projection AS (
    SELECT projection.user_signal_projection_id,
           projection.identity_key,
           projection.direction,
           COALESCE(
             projection.display_payload_json->>'trade_date',
             projection.source_payload_json->>'trade_date',
             card.card_payload_json->>'trade_date',
             projection.trace_json->>'trade_date'
           ) AS for_trade_date,
           COALESCE(
             card.card_payload_json->>'action_state',
             projection.display_payload_json->>'action_state'
           ) AS action_state,
           CASE
             WHEN COALESCE(
                    card.card_payload_json->>'action_state',
                    projection.display_payload_json->>'action_state'
                  ) = 'executed'
              AND COALESCE(
                    card.card_payload_json->>'action_price',
                    projection.display_payload_json->>'action_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      card.card_payload_json->>'action_price',
                      projection.display_payload_json->>'action_price'
                    )::numeric
             WHEN COALESCE(
                    card.card_payload_json->>'action_state',
                    projection.display_payload_json->>'action_state'
                  ) = 'eligible'
              AND COALESCE(
                    card.card_payload_json->>'trigger_price',
                    projection.display_payload_json->>'trigger_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      card.card_payload_json->>'trigger_price',
                      projection.display_payload_json->>'trigger_price'
                    )::numeric
           END AS current_reference_price
    FROM public.user_projection_run projection_run
    JOIN public.user_signal_projection projection
      ON projection.user_projection_run_id =
         projection_run.user_projection_run_id
    JOIN public.user_signal_card card
      ON card.user_signal_projection_id =
         projection.user_signal_projection_id
     AND card.user_projection_run_id =
         projection.user_projection_run_id
     AND card.user_id = projection.user_id
     AND card.asset_kind = projection.asset_kind
     AND card.identity_key = projection.identity_key
     AND card.direction = projection.direction
    WHERE projection.user_signal_projection_id =
            p_signal_projection_id
      AND projection.user_id = p_user_id
      AND projection_run.status IN ('passed', 'ready')
      AND projection.asset_kind = 'stock'
      AND projection.identity_key = p_identity_key
      AND projection.direction = 'buy'
      AND projection.projection_status IN ('visible', 'blocked')
      AND (
        (
          COALESCE(
            card.card_payload_json->>'action_state',
            projection.display_payload_json->>'action_state'
          ) = 'eligible'
          AND p_signal_reference_kind = 'trigger_price'
          AND card.card_status IN ('candidate', 'active', 'blocked')
        )
        OR (
          COALESCE(
            card.card_payload_json->>'action_state',
            projection.display_payload_json->>'action_state'
          ) = 'executed'
          AND p_signal_reference_kind = 'action_price'
          AND card.card_status IN (
            'action_confirmed', 'active', 'blocked'
          )
        )
      )
      AND COALESCE(
            projection.display_payload_json->>'trade_date',
            projection.source_payload_json->>'trade_date',
            card.card_payload_json->>'trade_date',
            projection.trace_json->>'trade_date'
          ) = current_trade_date
      AND (
        card.card_payload_json->>'for_trade_date' IS NULL
        OR card.card_payload_json->>'for_trade_date' =
           current_trade_date
      )
  ), approved_batch AS (
    SELECT min(basis.source_trade_date::text) AS source_trade_date,
           min(basis.for_trade_date::text) AS for_trade_date,
           min(basis.run_id::text) AS source_run_id
    FROM public.v_n6_stock_condition_display_basis basis
    WHERE basis.for_trade_date = (
      SELECT max(current_basis.for_trade_date)
      FROM public.v_n6_stock_condition_display_basis current_basis
    )
    HAVING count(*) > 0
       AND count(basis.source_trade_date) = count(*)
       AND count(basis.for_trade_date) = count(*)
       AND count(basis.run_id) = count(*)
       AND count(DISTINCT (
             basis.source_trade_date::text,
             basis.for_trade_date::text,
             basis.run_id::text
           )) = 1
  ), approved_identity AS (
    SELECT DISTINCT basis.identity_key,
           batch.source_trade_date,
           batch.for_trade_date,
           batch.source_run_id
    FROM approved_batch batch
    JOIN public.v_n6_stock_condition_display_basis basis
      ON basis.source_trade_date::text = batch.source_trade_date
     AND basis.for_trade_date::text = batch.for_trade_date
     AND basis.run_id::text = batch.source_run_id
    WHERE batch.for_trade_date = current_trade_date
  ), authorized_source AS (
    SELECT source.*,
           approved.source_trade_date,
           approved.source_run_id
    FROM source_projection source
    JOIN approved_identity approved
      ON approved.identity_key = source.identity_key
     AND approved.for_trade_date = source.for_trade_date
    WHERE source.for_trade_date = current_trade_date
      AND source.current_reference_price =
          p_signal_reference_price
      AND source.current_reference_price > 0
      AND EXISTS (
        SELECT 1
        FROM public.n6_principal principal
        WHERE principal.principal_id = p_principal_id
          AND principal.principal_type = p_principal_type
          AND principal.owner_user_id = p_user_id
          AND principal.principal_status = 'active'
      )
      AND EXISTS (
        SELECT 1
        FROM public.n6_virtual_account account
        WHERE account.virtual_account_id = p_virtual_account_id
          AND account.principal_id = p_principal_id
          AND account.principal_type = p_principal_type
          AND account.virtual_account_status = 'active'
      )
      AND (
        EXISTS (
          SELECT 1
          FROM public.n6_virtual_position position
          WHERE position.virtual_account_id =
                p_virtual_account_id
            AND position.principal_id = p_principal_id
            AND position.principal_type = p_principal_type
            AND position.asset_kind = 'stock'
            AND position.identity_key = source.identity_key
            AND position.position_status = 'open_virtual'
            AND position.quantity > 0
            AND position.holding_episode_no > 0
        )
        OR EXISTS (
          SELECT 1
          FROM public.user_monitor_stock monitor
          WHERE monitor.principal_id = p_principal_id
            AND monitor.principal_type = p_principal_type
            AND monitor.user_id = p_user_id
            AND monitor.asset_kind = 'stock'
            AND monitor.identity_key = source.identity_key
            AND monitor.direction = 'buy'
            AND monitor.status = 'active'
            AND monitor.quality_status = 'reviewed'
            AND monitor.valid_source_trade_date =
                approved.source_trade_date
            AND monitor.valid_for_trade_date =
                current_trade_date
            AND monitor.valid_source_run_id =
                approved.source_run_id
            AND monitor.source_run_id =
                approved.source_run_id
            AND monitor.source_snapshot_json->>'identity_key' =
                monitor.identity_key
            AND monitor.source_snapshot_json->>'source_trade_date' =
                approved.source_trade_date
            AND monitor.source_snapshot_json->>'for_trade_date' =
                current_trade_date
            AND monitor.source_snapshot_json->>'source_run_id' =
                approved.source_run_id
        )
        OR EXISTS (
          SELECT 1
          FROM public.user_realtime_monitor_scope realtime_scope
          WHERE realtime_scope.principal_id = p_principal_id
            AND realtime_scope.principal_type = p_principal_type
            AND realtime_scope.user_id = p_user_id
            AND realtime_scope.asset_kind = 'stock'
            AND realtime_scope.identity_key = source.identity_key
            AND realtime_scope.status = 'active'
            AND realtime_scope.deleted_at IS NULL
            AND realtime_scope.source_type = 'single_row'
            AND realtime_scope.source_snapshot_json->>'identity_key' =
                realtime_scope.identity_key
        )
      )
  )
  SELECT count(*)
    INTO matching_source_count
  FROM authorized_source;

  RETURN matching_source_count = 1;
END
$function$;

REVOKE ALL ON FUNCTION
  public.n6_btrack_manual_signal_buy_current_scope(
    bigint,text,bigint,bigint,bigint,text,text,numeric,text
  )
  FROM PUBLIC, n6_btrack_web, n6_virtual_executor, n6_ai_agent,
       n6_quote_writer;

DO $rewrite$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_list(text,integer)'::regprocedure;

  old_text := $proposal_list_status_042$           p.signal_reference_price,p.proposal_status,p.expires_at,p.confirmed_at,
$proposal_list_status_042$;
  new_text := $proposal_list_status_064$           p.signal_reference_price,
           p.source_lineage_json->>'confirmation_generation_token'
             AS confirmation_generation_token,
           CASE
             WHEN p.proposal_status IN ('pending', 'confirmed')
              AND p.expires_at <= pg_catalog.now()
               THEN 'expired'
             ELSE p.proposal_status
           END AS proposal_status,
           p.expires_at,p.confirmed_at,
$proposal_list_status_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_list_status_baseline_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_list_json_042$        'proposal_side',proposal_side,'signal_reference_kind',signal_reference_kind,
        'signal_reference_price',signal_reference_price,'proposal_status',proposal_status,'expires_at',expires_at,
$proposal_list_json_042$;
  new_text := $proposal_list_json_064$        'proposal_side',proposal_side,'signal_reference_kind',signal_reference_kind,
        'signal_reference_price',signal_reference_price,
        'confirmation_generation_token',confirmation_generation_token,
        'proposal_status',proposal_status,'expires_at',expires_at,
$proposal_list_json_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_list_json_baseline_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_list('
    'p_session_token_hash text,p_limit integer DEFAULT 100) '
    'RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_transition_guard()'::regprocedure;

  old_text := $proposal_guard_web_042$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF NOT (OLD.proposal_status='pending' AND NEW.proposal_status IN ('confirmed','expired')) THEN
      RAISE EXCEPTION 'web proposal transition rejected: % -> %',OLD.proposal_status,NEW.proposal_status;
    END IF;
    IF NEW.executed_virtual_order_id IS DISTINCT FROM OLD.executed_virtual_order_id
       OR NEW.executed_virtual_trade_id IS DISTINCT FROM OLD.executed_virtual_trade_id
       OR NEW.executor_run_id IS DISTINCT FROM OLD.executor_run_id
       OR NEW.failure_reason IS DISTINCT FROM OLD.failure_reason THEN
      RAISE EXCEPTION 'web executor fields rejected';
    END IF;
$proposal_guard_web_042$;
  new_text := $proposal_guard_web_064$  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN
    IF OLD.proposal_status='pending'
       AND NEW.proposal_status IN ('confirmed','expired') THEN
      IF COALESCE((
           OLD.source_type = 'signal'
           AND OLD.principal_type IN ('admin', 'human_user')
           AND OLD.proposal_side = 'buy'
           AND OLD.source_lineage_json
                 ->>'manual_buy_policy_version' =
               'n6_btrack_trade_date_all_day_buy_064_v1'
         ), false)
         AND NEW.proposal_status = 'confirmed'
         AND (
           NEW.confirm_idempotency_key IS NULL
           OR pg_catalog.split_part(
                NEW.confirm_idempotency_key, ':', 1
              ) <> 'n6v3'
           OR pg_catalog.split_part(
                NEW.confirm_idempotency_key, ':', 2
              ) IS DISTINCT FROM
              OLD.source_lineage_json
                ->>'confirmation_generation_token'
           OR pg_catalog.split_part(
                NEW.confirm_idempotency_key, ':', 3
              ) = ''
         ) THEN
        RAISE EXCEPTION 'web proposal confirmation generation rejected';
      END IF;
      IF NEW.executed_virtual_order_id IS DISTINCT FROM OLD.executed_virtual_order_id
         OR NEW.executed_virtual_trade_id IS DISTINCT FROM OLD.executed_virtual_trade_id
         OR NEW.executor_run_id IS DISTINCT FROM OLD.executor_run_id
         OR NEW.failure_reason IS DISTINCT FROM OLD.failure_reason THEN
        RAISE EXCEPTION 'web executor fields rejected';
      END IF;
    -- n6_064_manual_signal_retry_transition
    ELSIF COALESCE((
      OLD.source_type = 'signal'
      AND NEW.source_type = 'signal'
      AND OLD.principal_type IN ('admin', 'human_user')
      AND NEW.principal_type = OLD.principal_type
      AND OLD.user_id IS NOT NULL
      AND NEW.user_id = OLD.user_id
      AND OLD.actor_ai_user_id IS NULL
      AND NEW.actor_ai_user_id IS NULL
      AND OLD.source_ai_decision_id IS NULL
      AND NEW.source_ai_decision_id IS NULL
      AND OLD.strategy_action_id IS NULL
      AND NEW.strategy_action_id IS NULL
      AND OLD.proposal_side = 'buy'
      AND NEW.proposal_side = 'buy'
      AND OLD.source_signal_projection_id IS NOT NULL
      AND NEW.source_signal_projection_id =
          OLD.source_signal_projection_id
      AND OLD.source_virtual_position_id IS NULL
      AND NEW.source_virtual_position_id IS NULL
      AND NEW.principal_id = OLD.principal_id
      AND NEW.virtual_account_id = OLD.virtual_account_id
      AND NEW.source_id = OLD.source_id
      AND NEW.asset_kind = OLD.asset_kind
      AND NEW.identity_key = OLD.identity_key
      AND NEW.created_at = OLD.created_at
      AND (
        OLD.proposal_status IN ('expired', 'failed', 'rejected')
        OR (
          OLD.proposal_status IN ('pending', 'confirmed')
          AND OLD.expires_at <= pg_catalog.clock_timestamp()
        )
      )
      AND NEW.proposal_status = 'pending'
      AND NEW.expires_at > pg_catalog.clock_timestamp()
      AND NEW.expires_at <=
          pg_catalog.clock_timestamp() + interval '65 seconds'
      AND NEW.confirmed_at IS NULL
      AND NEW.confirm_idempotency_key IS NULL
      AND OLD.executed_virtual_order_id IS NULL
      AND NEW.executed_virtual_order_id IS NULL
      AND OLD.executed_virtual_trade_id IS NULL
      AND NEW.executed_virtual_trade_id IS NULL
      AND NEW.executor_run_id IS NULL
      AND NEW.failure_reason IS NULL
      AND NEW.signal_reference_kind IN (
            'trigger_price', 'action_price'
          )
      AND NEW.signal_reference_price IS NOT NULL
      AND NEW.signal_reference_price > 0
      AND NEW.signal_reference_price::text NOT IN (
            'NaN', 'Infinity', '-Infinity'
          )
      AND (
        NEW.locked_target_price IS NULL
        OR (
          NEW.locked_target_price > 0
          AND NEW.locked_target_price::text NOT IN (
                'NaN', 'Infinity', '-Infinity'
              )
        )
      )
      AND NEW.policy_version = 'n6_virtual_trade_proposal_v2_048'
      AND NEW.policy_hash =
          '4db44fa6cd1cbfd9cdb7e02c697f1354f7b938dd8262c41149c40ee5a409b2a8'
      AND NEW.source_lineage_json->>'manual_buy_policy_version' =
          'n6_btrack_trade_date_all_day_buy_064_v1'
      AND NEW.source_lineage_json
            ->>'confirmation_generation_token' IS NOT NULL
      AND NEW.source_lineage_json
            ->>'confirmation_generation_token'
          IS DISTINCT FROM
          OLD.source_lineage_json
            ->>'confirmation_generation_token'
      AND NEW.source_lineage_json->>'for_trade_date' =
          pg_catalog.to_char(
            pg_catalog.clock_timestamp()
              AT TIME ZONE 'Asia/Shanghai',
            'YYYYMMDD'
          )
      AND public.n6_btrack_manual_signal_buy_current_scope(
            NEW.principal_id,
            NEW.principal_type,
            NEW.user_id,
            NEW.virtual_account_id,
            NEW.source_signal_projection_id,
            NEW.identity_key,
            NEW.signal_reference_kind,
            NEW.signal_reference_price,
            NEW.source_lineage_json->>'for_trade_date'
          )
      AND pg_catalog.jsonb_typeof(
            NEW.source_lineage_json->'manual_retry_audit'
          ) = 'array'
      AND pg_catalog.jsonb_array_length(
            NEW.source_lineage_json->'manual_retry_audit'
          ) > 0
      AND NOT EXISTS (
        SELECT 1
        FROM public.n6_virtual_order existing_order
        WHERE existing_order.source_proposal_id = OLD.proposal_id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.n6_virtual_trade existing_trade
        WHERE existing_trade.source_proposal_id = OLD.proposal_id
      )
    ), false) THEN
      NULL;
    ELSE
      RAISE EXCEPTION 'web proposal transition rejected: % -> %',
        OLD.proposal_status, NEW.proposal_status;
    END IF;
$proposal_guard_web_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_guard_baseline_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_btrack_proposal_transition_guard() '
    'RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_create(text,text,bigint)'::regprocedure;

  old_text := $proposal_session_063$  shanghai_local_time := (
    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
  )::time;
  IF NOT (
    shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'
    OR shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'outside_trading_session'
    );
  END IF;
$proposal_session_063$;
  new_text := $proposal_session_064$  shanghai_local_time := (
    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
  )::time;
$proposal_session_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_session_baseline_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_scope_guard_063$    IF v_projection_id IS NULL
$proposal_scope_guard_063$;
  new_text := $proposal_scope_guard_064$    IF v_projection_id IS NULL THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'signal_not_in_effective_scope'
      );
    END IF;

    IF v_reference_kind IS NULL
       OR v_reference_price IS NULL
       OR v_reference_price <= 0
       OR v_reference_price::text IN (
            'NaN', 'Infinity', '-Infinity'
          ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_ready',
        'error', 'signal_reference_price_invalid'
      );
    END IF;

    IF v_projection_id IS NULL
$proposal_scope_guard_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_reference_guard_insert_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_reference_guard_063$       OR v_reference_kind IS NULL
       OR v_reference_price IS NULL
       OR v_reference_price <= 0
       OR (v_side <> 'buy' AND v_target_price IS NULL)
$proposal_reference_guard_063$;
  new_text := $proposal_reference_guard_064$       OR (v_side <> 'buy' AND v_target_price IS NULL)
$proposal_reference_guard_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_reference_guard_remove_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_insert_063$  INSERT INTO public.n6_virtual_trade_proposal (
$proposal_insert_063$;
  new_text := $proposal_insert_064$  IF p_source_type = 'signal'
     AND v_side = 'buy'
     AND authority->>'principal_type' IN ('admin', 'human_user')
     AND NOT public.n6_btrack_manual_signal_buy_current_scope(
       (authority->>'principal_id')::bigint,
       authority->>'principal_type',
       (authority->>'user_id')::bigint,
       account_id,
       v_projection_id,
       v_identity_key,
       v_reference_kind,
       v_reference_price,
       v_for_trade_date
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_found',
      'error', 'signal_not_in_effective_scope'
    );
  END IF;

  IF NOT (
    p_source_type = 'signal'
    AND v_side = 'buy'
    AND authority->>'principal_type' IN ('admin', 'human_user')
  )
  AND NOT (
    shanghai_local_time BETWEEN time '09:30:00' AND time '11:30:00'
    OR shanghai_local_time BETWEEN time '13:00:00' AND time '15:00:00'
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'outside_trading_session'
    );
  END IF;

  INSERT INTO public.n6_virtual_trade_proposal (
$proposal_insert_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_insert_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_lineage_063$      'frozen_score', v_score_json
$proposal_lineage_063$;
  new_text := $proposal_lineage_064$      'frozen_score', v_score_json,
      'manual_buy_policy_version',
        'n6_btrack_trade_date_all_day_buy_064_v1',
      'confirmation_generation_token',
        pg_catalog.gen_random_uuid()::text
$proposal_lineage_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_lineage_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_return_063$      'signal_reference_kind', result_row.signal_reference_kind,
      'signal_reference_price', result_row.signal_reference_price
$proposal_return_063$;
  new_text := $proposal_return_064$      'signal_reference_kind', result_row.signal_reference_kind,
      'signal_reference_price', result_row.signal_reference_price,
      'confirmation_generation_token',
        result_row.source_lineage_json
          ->>'confirmation_generation_token'
$proposal_return_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_return_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $proposal_retry_anchor_064$  INSERT INTO public.n6_virtual_trade_proposal (
$proposal_retry_anchor_064$;
  new_text := $proposal_retry_064$  -- n6_064_manual_signal_retry_rearm
  IF p_source_type = 'signal'
     AND v_side = 'buy'
     AND authority->>'principal_type' IN ('admin', 'human_user') THEN
    SELECT existing_proposal.*
      INTO result_row
    FROM public.n6_virtual_trade_proposal existing_proposal
    WHERE existing_proposal.principal_id =
          (authority->>'principal_id')::bigint
      AND existing_proposal.principal_type =
          authority->>'principal_type'
      AND existing_proposal.source_type = 'signal'
      AND existing_proposal.source_signal_projection_id = v_projection_id
    FOR UPDATE;

    IF FOUND THEN
      IF result_row.user_id IS DISTINCT FROM
           (authority->>'user_id')::bigint
         OR result_row.virtual_account_id IS DISTINCT FROM account_id
         OR result_row.source_id IS DISTINCT FROM p_source_id::text
         OR result_row.asset_kind IS DISTINCT FROM 'stock'
         OR result_row.identity_key IS DISTINCT FROM v_identity_key
         OR result_row.proposal_side IS DISTINCT FROM 'buy'
         OR result_row.actor_ai_user_id IS NOT NULL
         OR result_row.source_ai_decision_id IS NOT NULL
         OR result_row.strategy_action_id IS NOT NULL THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'conflict',
          'error', 'proposal_retry_scope_mismatch'
        );
      END IF;

      IF result_row.executed_virtual_order_id IS NOT NULL
         OR result_row.executed_virtual_trade_id IS NOT NULL
         OR EXISTS (
           SELECT 1
           FROM public.n6_virtual_order existing_order
           WHERE existing_order.source_proposal_id =
                 result_row.proposal_id
         )
         OR EXISTS (
           SELECT 1
           FROM public.n6_virtual_trade existing_trade
           WHERE existing_trade.source_proposal_id =
                 result_row.proposal_id
         )
         OR result_row.proposal_status IN ('processing', 'executed')
         OR NOT (
           result_row.proposal_status IN (
             'expired', 'failed', 'rejected'
           )
           OR (
             result_row.proposal_status IN ('pending', 'confirmed')
             AND result_row.expires_at <=
                 pg_catalog.clock_timestamp()
           )
         ) THEN
        RETURN pg_catalog.jsonb_build_object(
          'ok', false, 'status', 'conflict',
          'error', 'proposal_already_exists'
        );
      END IF;

      UPDATE public.n6_virtual_trade_proposal
      SET holding_episode_no = v_episode,
          signal_reference_kind = v_reference_kind,
          signal_reference_price = v_reference_price,
          locked_target_price = v_target_price,
          proposal_status = 'pending',
          expires_at =
            pg_catalog.clock_timestamp() + interval '60 seconds',
          confirmed_at = NULL,
          confirm_idempotency_key = NULL,
          executed_virtual_order_id = NULL,
          executed_virtual_trade_id = NULL,
          executor_run_id = NULL,
          failure_reason = NULL,
          policy_version = 'n6_virtual_trade_proposal_v2_048',
          policy_hash =
            '4db44fa6cd1cbfd9cdb7e02c697f1354f7b938dd8262c41149c40ee5a409b2a8',
          source_lineage_json =
            (
              result_row.source_lineage_json
              - 'manual_retry_audit'
            )
            || pg_catalog.jsonb_build_object(
              'source_type', p_source_type,
              'source_id', p_source_id::text,
              'for_trade_date', v_for_trade_date,
              'scope_authority', v_scope_authority,
              'frozen_virtual_position_id', v_position_id,
              'frozen_holding_episode_no', v_episode,
              'frozen_score', v_score_json,
              'manual_buy_policy_version',
                'n6_btrack_trade_date_all_day_buy_064_v1',
              'confirmation_generation_token',
                pg_catalog.gen_random_uuid()::text,
              'manual_retry_audit',
                COALESCE(
                  CASE
                    WHEN pg_catalog.jsonb_typeof(
                           result_row.source_lineage_json
                             ->'manual_retry_audit'
                         ) = 'array'
                      THEN result_row.source_lineage_json
                             ->'manual_retry_audit'
                  END,
                  '[]'::jsonb
                )
                || pg_catalog.jsonb_build_array(
                  pg_catalog.jsonb_build_object(
                    'previous_proposal_status',
                      result_row.proposal_status,
                    'previous_expires_at', result_row.expires_at,
                    'previous_confirmed_at', result_row.confirmed_at,
                    'previous_failure_reason',
                      result_row.failure_reason,
                    'retried_at', pg_catalog.clock_timestamp(),
                    'retry_policy_version',
                      'n6_btrack_trade_date_all_day_buy_064_v1'
                  )
                )
            ),
          updated_at = pg_catalog.clock_timestamp()
      WHERE proposal_id = result_row.proposal_id
      RETURNING * INTO result_row;

      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'created', 'rearmed', true, 'item',
        pg_catalog.jsonb_build_object(
          'proposal_id', result_row.proposal_id,
          'proposal_status', result_row.proposal_status,
          'expires_at', result_row.expires_at,
          'proposal_side', result_row.proposal_side,
          'identity_key', result_row.identity_key,
          'signal_reference_kind', result_row.signal_reference_kind,
          'signal_reference_price', result_row.signal_reference_price,
          'confirmation_generation_token',
            result_row.source_lineage_json
              ->>'confirmation_generation_token'
        )
      );
    END IF;
  END IF;

  INSERT INTO public.n6_virtual_trade_proposal (
$proposal_retry_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_proposal_retry_anchor_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_create('
    'p_session_token_hash text,p_source_type text,p_source_id bigint) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_confirm(text,bigint,text)'::regprocedure;

  old_text := $confirm_declare_042$DECLARE authority jsonb:=public.n6_btrack_resolve_authority(p_session_token_hash); row_value public.n6_virtual_trade_proposal%ROWTYPE;
$confirm_declare_042$;
  new_text := $confirm_declare_064$DECLARE
  authority jsonb :=
    public.n6_btrack_resolve_authority(p_session_token_hash);
  row_value public.n6_virtual_trade_proposal%ROWTYPE;
  current_trade_date text;
  current_trade_date_count integer;
$confirm_declare_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_confirm_declare_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $confirm_revalidation_042$  IF row_value.proposal_status='confirmed' AND row_value.confirm_idempotency_key=p_idempotency_key THEN
$confirm_revalidation_042$;
  new_text := $confirm_revalidation_064$  IF row_value.proposal_status IN ('pending', 'confirmed')
     AND row_value.principal_type IN ('admin', 'human_user')
     AND row_value.user_id IS NOT NULL
     AND row_value.actor_ai_user_id IS NULL
     AND row_value.source_ai_decision_id IS NULL
     AND row_value.source_type = 'signal'
     AND row_value.proposal_side = 'buy'
     AND row_value.source_signal_projection_id IS NOT NULL
     AND row_value.source_virtual_position_id IS NULL THEN
    IF row_value.source_lineage_json
         ->>'confirmation_generation_token' IS NULL
       OR pg_catalog.split_part(p_idempotency_key, ':', 1) <> 'n6v3'
       OR pg_catalog.split_part(p_idempotency_key, ':', 2)
          IS DISTINCT FROM
          row_value.source_lineage_json
            ->>'confirmation_generation_token'
       OR pg_catalog.split_part(p_idempotency_key, ':', 3) = '' THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'conflict',
        'error', 'proposal_generation_mismatch'
      );
    END IF;
    current_trade_date := pg_catalog.to_char(
      pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
      'YYYYMMDD'
    );
    IF row_value.source_lineage_json->>'for_trade_date'
       IS DISTINCT FROM current_trade_date THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_ready',
        'error', 'proposal_trade_date_not_current'
      );
    END IF;
    SELECT count(*)
      INTO current_trade_date_count
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date = current_trade_date
      AND calendar.is_open = true;
    IF current_trade_date_count <> 1 THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_ready',
        'error', 'current_open_trade_date_required'
      );
    END IF;
    IF row_value.signal_reference_kind NOT IN (
         'trigger_price', 'action_price'
       )
       OR row_value.signal_reference_price IS NULL
       OR row_value.signal_reference_price <= 0
       OR row_value.signal_reference_price::text IN (
            'NaN', 'Infinity', '-Infinity'
          ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_ready',
        'error', 'signal_reference_price_invalid'
      );
    END IF;
    IF NOT public.n6_btrack_manual_signal_buy_current_scope(
         row_value.principal_id,
         row_value.principal_type,
         row_value.user_id,
         row_value.virtual_account_id,
         row_value.source_signal_projection_id,
         row_value.identity_key,
         row_value.signal_reference_kind,
         row_value.signal_reference_price,
         row_value.source_lineage_json->>'for_trade_date'
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'signal_not_in_effective_scope'
      );
    END IF;
  END IF;
  -- n6_064_confirm_expiry_precedes_idempotency
  IF row_value.proposal_status = 'confirmed'
     AND row_value.expires_at <= pg_catalog.clock_timestamp() THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'expired',
      'error', 'proposal_expired'
    );
  END IF;
  IF row_value.proposal_status='confirmed' AND row_value.confirm_idempotency_key=p_idempotency_key THEN
$confirm_revalidation_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_confirm_revalidation_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_confirm('
    'p_session_token_hash text,p_proposal_id bigint,p_idempotency_key text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure;

  old_text := $executor_declare_063$  ai_risk_result jsonb;
$executor_declare_063$;
  new_text := $executor_declare_064$  ai_risk_result jsonb;
  shanghai_now timestamp without time zone;
  current_trade_date text;
  current_trade_date_count integer;
  current_local_time time without time zone;
  is_manual_all_day_buy boolean := false;
  fill_quote_snapshot_id bigint;
  fill_price_source text;
  fill_price_field text;
  fill_fallback_reason text;
  fill_policy_id text;
$executor_declare_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_declare_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_account_063$  SELECT * INTO account
$executor_account_063$;
  new_text := $executor_account_064$  shanghai_now :=
    pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai';
  current_trade_date :=
    pg_catalog.to_char(shanghai_now, 'YYYYMMDD');
  current_local_time := shanghai_now::time;
  is_manual_all_day_buy := (
    proposal.principal_type IN ('admin', 'human_user')
    AND proposal.user_id IS NOT NULL
    AND proposal.actor_ai_user_id IS NULL
    AND proposal.source_ai_decision_id IS NULL
    AND proposal.source_type = 'signal'
    AND proposal.proposal_side = 'buy'
    AND proposal.source_signal_projection_id IS NOT NULL
    AND proposal.source_virtual_position_id IS NULL
  );

  SELECT * INTO account
$executor_account_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_account_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_quote_063$  SELECT * INTO quote
  FROM public.n6_virtual_quote_snapshot
  WHERE identity_key = proposal.identity_key
  ORDER BY quote_minute DESC, virtual_quote_snapshot_id DESC
  LIMIT 1
  FOR SHARE;
  IF NOT FOUND
     OR quote.quality_status <> 'passed'
     OR quote.quality_reason <> 'ok'
     OR quote.exchange NOT IN ('SH', 'SZ')
     OR quote.identity_key <> proposal.identity_key
     OR quote.quote_minute > pg_catalog.clock_timestamp()
     OR quote.quote_minute < pg_catalog.clock_timestamp() - interval '2 minutes'
     OR quote.fetched_at > pg_catalog.clock_timestamp()
     OR (proposal.source_type = 'stop_loss' AND quote.fetched_at < quote.quote_minute)
     OR quote.fetched_at < pg_catalog.clock_timestamp() - interval '2 minutes'
     OR quote.current_price IS NULL
     OR quote.current_price <= 0
     OR quote.current_price::text IN ('NaN', 'Infinity', '-Infinity') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'quote_not_ready');
  END IF;

  trade_date_date := (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date;
  trade_date_integer := pg_catalog.to_char(trade_date_date, 'YYYYMMDD')::integer;
  fill_price := quote.current_price::numeric(24,6);
  IF trade_date_date <> (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR NOT (
       (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '09:30' AND time '11:30'
       OR (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '13:00' AND time '15:00'
     )
     OR NOT (
       (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '09:30' AND time '11:30'
       OR (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '13:00' AND time '15:00'
     )
     OR NOT EXISTS (
       SELECT 1 FROM public.common_trade_calendar
       WHERE trade_date = trade_date_integer::text AND is_open = true
     ) THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'trade_session_not_ready');
  END IF;
$executor_quote_063$;
  new_text := $executor_quote_064$  IF is_manual_all_day_buy THEN
    IF proposal.source_lineage_json->>'for_trade_date'
       IS DISTINCT FROM current_trade_date THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'proposal_trade_date_not_current'
      );
    END IF;
    SELECT count(*)
      INTO current_trade_date_count
    FROM public.common_trade_calendar calendar
    WHERE calendar.trade_date = current_trade_date
      AND calendar.is_open = true;
    IF current_trade_date_count <> 1 THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'current_open_trade_date_required'
      );
    END IF;
    IF proposal.signal_reference_kind NOT IN (
         'trigger_price', 'action_price'
       )
       OR proposal.signal_reference_price IS NULL
       OR proposal.signal_reference_price <= 0
       OR proposal.signal_reference_price::text IN (
            'NaN', 'Infinity', '-Infinity'
          ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'signal_reference_price_invalid'
      );
    END IF;
    IF NOT public.n6_btrack_manual_signal_buy_current_scope(
         proposal.principal_id,
         proposal.principal_type,
         proposal.user_id,
         proposal.virtual_account_id,
         proposal.source_signal_projection_id,
         proposal.identity_key,
         proposal.signal_reference_kind,
         proposal.signal_reference_price,
         proposal.source_lineage_json->>'for_trade_date'
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'signal_not_in_effective_scope'
      );
    END IF;

    trade_date_date := pg_catalog.to_date(
      current_trade_date, 'YYYYMMDD'
    );
    trade_date_integer := current_trade_date::integer;

    SELECT * INTO quote
    FROM public.n6_virtual_quote_snapshot candidate
    WHERE candidate.identity_key = proposal.identity_key
      AND candidate.quality_status = 'passed'
      AND candidate.quality_reason = 'ok'
      AND candidate.exchange =
          pg_catalog.split_part(proposal.identity_key, ':', 2)
      AND candidate.quote_minute <= pg_catalog.clock_timestamp()
      AND candidate.quote_minute >=
          pg_catalog.clock_timestamp() - interval '2 minutes'
      AND candidate.fetched_at <= pg_catalog.clock_timestamp()
      AND candidate.fetched_at >= candidate.quote_minute
      AND candidate.fetched_at >=
          pg_catalog.clock_timestamp() - interval '2 minutes'
      AND (
        candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
      )::date = trade_date_date
      AND (
        (
          candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
        )::time BETWEEN time '09:30' AND time '11:30'
        OR (
          candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
        )::time BETWEEN time '13:00' AND time '15:00'
      )
      AND candidate.current_price IS NOT NULL
      AND candidate.current_price > 0
      AND candidate.current_price::text NOT IN (
            'NaN', 'Infinity', '-Infinity'
          )
    ORDER BY candidate.quote_minute DESC,
             candidate.virtual_quote_snapshot_id DESC
    LIMIT 1
    FOR SHARE;

    IF FOUND THEN
      fill_price := quote.current_price::numeric(24,6);
      fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
      fill_price_source := 'quote_current_price';
      fill_price_field := 'current_price';
      fill_fallback_reason := NULL;
      fill_policy_id := 'n6_064_fresh_quote_fill_v1';
    ELSE
      IF (
        current_local_time > time '11:30'
        AND current_local_time < time '13:00'
      )
      OR current_local_time > time '15:00' THEN
        SELECT * INTO quote
        FROM public.n6_virtual_quote_snapshot candidate
        WHERE candidate.identity_key = proposal.identity_key
          AND candidate.quality_status = 'passed'
          AND candidate.quality_reason = 'ok'
          AND candidate.exchange =
              pg_catalog.split_part(
                proposal.identity_key, ':', 2
              )
          AND candidate.quote_minute <= pg_catalog.clock_timestamp()
          AND candidate.fetched_at <= pg_catalog.clock_timestamp()
          AND candidate.fetched_at >= candidate.quote_minute
          AND (
            candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
          )::date = trade_date_date
          AND (
            (
              candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '09:30' AND time '11:30'
            OR (
              candidate.quote_minute AT TIME ZONE 'Asia/Shanghai'
            )::time BETWEEN time '13:00' AND time '15:00'
          )
          AND candidate.current_price IS NOT NULL
          AND candidate.current_price > 0
          AND candidate.current_price::text NOT IN (
                'NaN', 'Infinity', '-Infinity'
              )
        ORDER BY candidate.quote_minute DESC,
                 candidate.virtual_quote_snapshot_id DESC
        LIMIT 1
        FOR SHARE;
      END IF;

      IF FOUND THEN
        fill_price := quote.current_price::numeric(24,6);
        fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
        fill_price_source :=
          'same_day_last_quote_current_price';
        fill_price_field := 'current_price';
        fill_fallback_reason := 'fresh_quote_not_ready';
        fill_policy_id :=
          'n6_064_same_day_last_quote_fill_v1';
      ELSE
        fill_price :=
          proposal.signal_reference_price::numeric(24,6);
        fill_quote_snapshot_id := NULL;
        fill_price_source := 'signal_reference_price';
        fill_price_field := proposal.signal_reference_kind;
        fill_fallback_reason := CASE
          WHEN current_local_time < time '09:30'
            THEN 'preopen_no_same_day_quote'
          WHEN (
            current_local_time > time '11:30'
            AND current_local_time < time '13:00'
          )
          OR current_local_time > time '15:00'
            THEN 'outside_session_no_usable_same_day_quote'
          ELSE 'fresh_quote_not_ready'
        END;
        fill_policy_id :=
          'n6_064_signal_reference_fill_v1';
      END IF;
    END IF;
  ELSE
    SELECT * INTO quote
    FROM public.n6_virtual_quote_snapshot
    WHERE identity_key = proposal.identity_key
    ORDER BY quote_minute DESC, virtual_quote_snapshot_id DESC
    LIMIT 1
    FOR SHARE;
    IF NOT FOUND
       OR quote.quality_status <> 'passed'
       OR quote.quality_reason <> 'ok'
       OR quote.exchange NOT IN ('SH', 'SZ')
       OR quote.identity_key <> proposal.identity_key
       OR quote.quote_minute > pg_catalog.clock_timestamp()
       OR quote.quote_minute <
          pg_catalog.clock_timestamp() - interval '2 minutes'
       OR quote.fetched_at > pg_catalog.clock_timestamp()
       OR (
         proposal.source_type = 'stop_loss'
         AND quote.fetched_at < quote.quote_minute
       )
       OR quote.fetched_at <
          pg_catalog.clock_timestamp() - interval '2 minutes'
       OR quote.current_price IS NULL
       OR quote.current_price <= 0
       OR quote.current_price::text IN (
            'NaN', 'Infinity', '-Infinity'
          ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'quote_not_ready'
      );
    END IF;

    trade_date_date :=
      (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date;
    trade_date_integer :=
      pg_catalog.to_char(trade_date_date, 'YYYYMMDD')::integer;
    fill_price := quote.current_price::numeric(24,6);
    fill_quote_snapshot_id := quote.virtual_quote_snapshot_id;
    fill_price_source := 'quote_current_price';
    fill_price_field := 'current_price';
    fill_fallback_reason := NULL;
    fill_policy_id := 'n6_046_latest_quote_fill_v1';
    IF trade_date_date <>
         (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
       OR NOT (
         (
           quote.quote_minute AT TIME ZONE 'Asia/Shanghai'
         )::time BETWEEN time '09:30' AND time '11:30'
         OR (
           quote.quote_minute AT TIME ZONE 'Asia/Shanghai'
         )::time BETWEEN time '13:00' AND time '15:00'
       )
       OR NOT (
         (
           pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
         )::time BETWEEN time '09:30' AND time '11:30'
         OR (
           pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
         )::time BETWEEN time '13:00' AND time '15:00'
       )
       OR NOT EXISTS (
         SELECT 1
         FROM public.common_trade_calendar
         WHERE trade_date = trade_date_integer::text
           AND is_open = true
       ) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'trade_session_not_ready'
      );
    END IF;
  END IF;
$executor_quote_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_quote_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_lineage_063$  lineage := pg_catalog.jsonb_build_object(
    'source_proposal_id', proposal.proposal_id,
    'confirm_idempotency_key', proposal.confirm_idempotency_key,
    'fill_quote_snapshot_id', quote.virtual_quote_snapshot_id,
    'executor_run_id', p_executor_run_id,
    'policy_version', 'n6_btrack_manual_actionable_buy_063_v1'
  );
$executor_lineage_063$;
  new_text := $executor_lineage_064$  lineage := pg_catalog.jsonb_build_object(
    'source_proposal_id', proposal.proposal_id,
    'confirm_idempotency_key', proposal.confirm_idempotency_key,
    'fill_quote_snapshot_id', fill_quote_snapshot_id,
    'fill_price_source', fill_price_source,
    'fill_price_field', fill_price_field,
    'fill_fallback_reason', fill_fallback_reason,
    'fill_policy_version', fill_policy_id,
    'for_trade_date', trade_date_integer::text,
    'executor_run_id', p_executor_run_id,
    'policy_version', 'n6_btrack_trade_date_all_day_buy_064_v1'
  );
$executor_lineage_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_lineage_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_fill_policy_063$    'n6_046_latest_quote_fill_v1', 'n6_046_latest_quote_fill_v1',
$executor_fill_policy_063$;
  new_text := $executor_fill_policy_064$    fill_policy_id, fill_policy_id,
$executor_fill_policy_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_order_fill_policy_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_trade_fill_policy_063$    0, 0, 0, 0, gross_amount, 'n6_046_latest_quote_fill_v1',
    'n6_046_latest_quote_fill_v1', 'source_proposal:' || proposal.proposal_id,
$executor_trade_fill_policy_063$;
  new_text := $executor_trade_fill_policy_064$    0, 0, 0, 0, gross_amount, fill_policy_id,
    fill_policy_id, 'source_proposal:' || proposal.proposal_id,
$executor_trade_fill_policy_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_trade_fill_policy_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_row_quote_id_063$proposal.signal_reference_kind, proposal.signal_reference_price,
    quote.virtual_quote_snapshot_id
$executor_row_quote_id_063$;
  new_text := $executor_row_quote_id_064$proposal.signal_reference_kind, proposal.signal_reference_price,
    fill_quote_snapshot_id
$executor_row_quote_id_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 2 THEN
    RAISE EXCEPTION '064_executor_row_quote_id_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  old_text := $executor_return_quote_id_063$    quote.virtual_quote_snapshot_id, 'filled_quantity', fill_quantity,
$executor_return_quote_id_063$;
  new_text := $executor_return_quote_id_064$    fill_quote_snapshot_id, 'filled_quantity', fill_quantity,
$executor_return_quote_id_064$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '064_executor_return_quote_id_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  source_text := pg_catalog.replace(
    source_text,
    'n6_btrack_manual_actionable_buy_063_v1',
    'n6_btrack_trade_date_all_day_buy_064_v1'
  );

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_apply_claimed_proposal('
    'p_proposal_id bigint,p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rewrite$;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  FROM PUBLIC, n6_ai_agent, n6_quote_writer, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_list(text,integer)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_list(text,integer)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_confirm(text,bigint,text)
  FROM PUBLIC, n6_ai_agent, n6_quote_writer, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_confirm(text,bigint,text)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard()
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;

REVOKE ALL ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)',
        NULL::text,
        'open_trade_date_count'
      ),
      (
        'public.n6_btrack_proposal_create(text,text,bigint)',
        'n6_btrack_web',
        'n6_064_manual_signal_retry_rearm'
      ),
      (
        'public.n6_btrack_proposal_list(text,integer)',
        'n6_btrack_web',
        'END AS proposal_status'
      ),
      (
        'public.n6_btrack_proposal_confirm(text,bigint,text)',
        'n6_btrack_web',
        'n6_064_confirm_expiry_precedes_idempotency'
      ),
      (
        'public.n6_btrack_proposal_transition_guard()',
        NULL::text,
        'n6_064_manual_signal_retry_transition'
      ),
      (
        'public.n6_executor_apply_claimed_proposal(bigint,text)',
        'n6_virtual_executor',
        'n6_064_signal_reference_fill_v1'
      )
    ) AS expected_functions(signature, allowed_role, required_marker)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '064_postflight_function_missing: %',
        expected.signature;
    END IF;

    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = function_oid;
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR pg_catalog.strpos(
            function_proc.prosrc, expected.required_marker
          ) = 0 THEN
      RAISE EXCEPTION '064_postflight_definition_drift: %',
        expected.signature;
    END IF;

    SELECT
      CASE
        WHEN expected.allowed_role IS NULL THEN true
        ELSE EXISTS (
          SELECT 1
          FROM pg_catalog.pg_proc target
          CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
              target.proacl,
              pg_catalog.acldefault('f', target.proowner)
            )
          ) acl
          JOIN pg_catalog.pg_roles role
            ON role.oid = acl.grantee
          WHERE target.oid = function_oid
            AND role.rolname = expected.allowed_role
            AND acl.privilege_type = 'EXECUTE'
            AND acl.is_grantable IS FALSE
        )
      END,
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(
            target.proacl,
            pg_catalog.acldefault('f', target.proowner)
          )
        ) acl
        LEFT JOIN pg_catalog.pg_roles role
          ON role.oid = acl.grantee
        WHERE target.oid = function_oid
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            expected.allowed_role IS NULL
            OR acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected.allowed_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '064_postflight_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
