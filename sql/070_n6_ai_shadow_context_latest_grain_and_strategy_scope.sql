BEGIN;

-- N6 AI Shadow context latest-state workset and bounded strategy membership scope.
-- Function signatures, owner and ACL remain unchanged; no business rows are rewritten.

DO $preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  source_count integer := 0;
  fixed_count integer := 0;
  error_prefix text := '070_partial_or_source_mismatch';
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '070_owner_session_required';
  END IF;

  FOR expected IN
    SELECT *
    FROM (
      VALUES
      ('n6_ai_agent_context_load(text,date,integer)', '4dae0563b34df9e066c2c91feb6f3a096a09ea2573a31f2cf30c71bfe0704993', '1d4283cd96f34032e51049aa6f4c1305dabe37cf0c62e1b2ba7594091290cc5a', NULL::text),
      ('n6_ai_agent_context_load_v2(text,date,integer,text)', 'df2afc2d7583effd10905ed478ab0df7e2147a854784bfc1b6087ca6d9b04681', 'ae000e4593d0de425dce168640740e1186dc7bd8d007e1a3677608cbf3940730', 'n6_ai_agent'),
      ('n6_ai_strategy_context_load_v1(text,date,integer,text)', '79dd370a27ff53b270ab032542cb0fc4eed3262a673919ff8f0d6e751592f504', '4865a77cc5940fb1230dad18339c05d9e8eefc4aadb535b21e52d16689dc4d14', NULL::text)
    ) AS expected_functions(
      signature, source_sha, fixed_sha, allowed_role
    )
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '070_partial_or_source_mismatch: %',
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
      RAISE EXCEPTION '070_partial_or_source_mismatch: body %',
        expected.signature;
    END IF;
  END LOOP;
  IF fixed_count = 3 THEN
    RAISE EXCEPTION '070_already_applied';
  END IF;
  IF source_count <> 3 OR fixed_count <> 0 THEN
    RAISE EXCEPTION '070_partial_or_source_mismatch';
  END IF;
END
$preflight$;

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
             PARTITION BY shared.asset_kind,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_event_time DESC,
                      shared.source_signal_projection_id DESC
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
             PARTITION BY shared.asset_kind,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_event_time DESC,
                      shared.source_signal_projection_id DESC
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
  ), candidate_stock_identity AS (
    SELECT DISTINCT stock.identity_key
    FROM stock_candidate stock
  ), selected_index_context AS (
    SELECT DISTINCT signal.identity_key
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    WHERE signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'index'
      AND signal.identity_key ~ '^index:(SH|SZ):[0-9]{6}$'
      AND signal.direction IN ('buy', 'sell')
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND snapshot_source_signal_ids @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
  ), selected_board_context AS (
    SELECT DISTINCT signal.identity_key
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    WHERE signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'board'
      AND signal.identity_key ~ '^board:TDX:[0-9]{6}$'
      AND signal.direction IN ('buy', 'sell')
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
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
    JOIN candidate_stock_identity stock_scope
      ON stock_scope.identity_key = membership.stock_identity_key
    JOIN selected_index_context market_scope
      ON market_scope.identity_key = membership.index_identity_key
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
  ), index_hint AS MATERIALIZED (
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
    JOIN candidate_stock_identity stock_scope
      ON stock_scope.identity_key = membership.stock_identity_key
    JOIN selected_board_context market_scope
      ON market_scope.identity_key = membership.board_identity_key
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
  ), board_hint AS MATERIALIZED (
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

DO $postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  allowed_role_oid oid;
  actual_sha text;
  error_prefix text := '070_postflight_mismatch';
BEGIN
  FOR expected IN
    SELECT *
    FROM (
      VALUES
      ('n6_ai_agent_context_load(text,date,integer)', '1d4283cd96f34032e51049aa6f4c1305dabe37cf0c62e1b2ba7594091290cc5a', NULL::text),
      ('n6_ai_agent_context_load_v2(text,date,integer,text)', 'ae000e4593d0de425dce168640740e1186dc7bd8d007e1a3677608cbf3940730', 'n6_ai_agent'),
      ('n6_ai_strategy_context_load_v1(text,date,integer,text)', '4865a77cc5940fb1230dad18339c05d9e8eefc4aadb535b21e52d16689dc4d14', NULL::text)
    ) AS expected_functions(signature, expected_sha, allowed_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(
      'public.' || expected.signature
    );
    IF function_oid IS NULL THEN
      RAISE EXCEPTION '070_postflight_mismatch: %', expected.signature;
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
      RAISE EXCEPTION '070_postflight_mismatch: body %', expected.signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
