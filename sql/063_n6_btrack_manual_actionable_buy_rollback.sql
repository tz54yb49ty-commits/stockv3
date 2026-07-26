-- Roll back N6 B-track manual actionable buy support.
-- Restores the exact published 053 proposal function and 057 executor function.
-- Proposal, order, trade, cash, lot, position, and event history are preserved.

BEGIN;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_create(
  p_session_token_hash text, p_source_type text, p_source_id bigint
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  authority jsonb := public.n6_btrack_resolve_authority(p_session_token_hash);
  account_id bigint;
  account_count integer;
  shanghai_local_time time without time zone;
  current_trade_date text;
  current_trade_date_count integer;
  v_identity_key text;
  v_side text;
  v_reference_kind text;
  v_reference_price numeric(24,8);
  v_target_price numeric(24,8);
  v_position_id bigint;
  v_projection_id bigint;
  v_episode integer;
  v_for_trade_date text;
  v_scope_authority text;
  v_score_json jsonb;
  result_row public.n6_virtual_trade_proposal%ROWTYPE;
BEGIN
  IF authority IS NULL
     OR p_source_id IS NULL
     OR p_source_id <= 0
     OR p_source_type NOT IN ('signal', 'manual_position') THEN
    RETURN NULL;
  END IF;

  SELECT min(a.virtual_account_id), count(*)
    INTO account_id, account_count
  FROM public.n6_virtual_account a
  WHERE a.principal_id = (authority->>'principal_id')::bigint
    AND a.principal_type = authority->>'principal_type'
    AND a.virtual_account_status = 'active';
  IF account_count <> 1 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'exactly_one_active_virtual_account_required'
    );
  END IF;

  SELECT min(c.trade_date), count(*)
    INTO current_trade_date, current_trade_date_count
  FROM public.common_trade_calendar c
  WHERE c.trade_date = pg_catalog.to_char(
          pg_catalog.now() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        )
    AND c.is_open = true;
  IF current_trade_date_count <> 1 OR current_trade_date IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', false, 'status', 'not_ready',
      'error', 'current_open_trade_date_required'
    );
  END IF;

  shanghai_local_time := (
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

  IF p_source_type = 'signal' THEN
    WITH source_projection AS (
      SELECT p.user_signal_projection_id,
             p.identity_key,
             p.direction,
             p.projection_status,
             p.display_payload_json,
             p.target_price AS projection_target_price,
             c.card_payload_json,
             c.target_price AS card_target_price,
             c.card_status,
             p.display_payload_json->>'for_trade_date' AS for_trade_date,
             COALESCE(
               c.card_payload_json->>'action_state',
               p.display_payload_json->>'action_state'
             ) AS action_state,
             COALESCE(
               c.card_payload_json->'score',
               p.display_payload_json->'score'
             ) AS score_json
      FROM public.user_projection_run r
      JOIN public.user_signal_projection p
        ON p.user_projection_run_id = r.user_projection_run_id
      JOIN public.user_signal_card c
        ON c.user_signal_projection_id = p.user_signal_projection_id
       AND c.user_projection_run_id = p.user_projection_run_id
       AND c.user_id = p.user_id
       AND c.asset_kind = p.asset_kind
       AND c.identity_key = p.identity_key
       AND c.direction = p.direction
      WHERE p.user_signal_projection_id = p_source_id
        AND p.user_id = (authority->>'user_id')::bigint
        AND r.status IN ('passed', 'ready')
        AND p.asset_kind = 'stock'
        AND p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
        AND p.direction IN ('buy', 'sell')
        AND p.projection_status IN ('visible', 'blocked')
        AND c.card_status IN ('active', 'blocked')
        AND p.display_payload_json->>'for_trade_date' = current_trade_date
        AND (
          c.card_payload_json->>'for_trade_date' IS NULL
          OR c.card_payload_json->>'for_trade_date' = current_trade_date
        )
    ), approved_batch AS (
      SELECT min(v.source_trade_date::text) AS source_trade_date,
             min(v.for_trade_date::text) AS for_trade_date,
             min(v.run_id::text) AS source_run_id
      FROM public.v_n6_stock_condition_display_basis v
      WHERE v.for_trade_date = (
        SELECT max(current_view.for_trade_date)
        FROM public.v_n6_stock_condition_display_basis current_view
      )
      HAVING count(*) > 0
         AND count(v.source_trade_date) = count(*)
         AND count(v.for_trade_date) = count(*)
         AND count(v.run_id) = count(*)
         AND count(DISTINCT (
               v.source_trade_date::text,
               v.for_trade_date::text,
               v.run_id::text
             )) = 1
    ), approved_identity AS (
      SELECT DISTINCT v.identity_key,
             b.source_trade_date,
             b.for_trade_date,
             b.source_run_id
      FROM approved_batch b
      JOIN public.v_n6_stock_condition_display_basis v
        ON v.source_trade_date::text = b.source_trade_date
       AND v.for_trade_date::text = b.for_trade_date
       AND v.run_id::text = b.source_run_id
      WHERE b.for_trade_date = current_trade_date
    ), authorized_source AS (
      SELECT s.*,
             approved.source_trade_date AS approved_source_trade_date,
             approved.source_run_id AS approved_source_run_id,
             scope.scope_authority,
             scope.virtual_position_id,
             scope.holding_episode_no
      FROM source_projection s
      JOIN approved_identity approved
        ON approved.identity_key = s.identity_key
       AND approved.for_trade_date = s.for_trade_date
      JOIN LATERAL (
        SELECT candidate.scope_authority,
               candidate.virtual_position_id,
               candidate.holding_episode_no
        FROM (
          SELECT 'open_position'::text AS scope_authority,
                 pos.virtual_position_id,
                 pos.holding_episode_no,
                 1 AS scope_priority
          FROM public.n6_virtual_position pos
          WHERE pos.virtual_account_id = account_id
            AND pos.principal_id = (authority->>'principal_id')::bigint
            AND pos.principal_type = authority->>'principal_type'
            AND pos.asset_kind = 'stock'
            AND pos.identity_key = s.identity_key
            AND pos.position_status = 'open_virtual'
            AND pos.quantity > 0
            AND pos.holding_episode_no > 0
            AND (
              s.direction = 'buy'
              OR EXISTS (
                SELECT 1
                FROM public.n6_virtual_position_lot lot
                WHERE lot.virtual_position_id = pos.virtual_position_id
                  AND lot.virtual_account_id = pos.virtual_account_id
                  AND lot.principal_id = pos.principal_id
                  AND lot.principal_type = pos.principal_type
                  AND lot.identity_key = pos.identity_key
                  AND lot.holding_episode_no = pos.holding_episode_no
                  AND lot.remaining_quantity > 0
                  AND lot.available_trade_date <= pg_catalog.to_date(
                    current_trade_date, 'YYYYMMDD'
                  )
                  AND lot.lot_status IN ('locked_t1', 'available')
              )
            )
          UNION ALL
          SELECT 'monitor'::text, NULL::bigint, NULL::integer, 2
          FROM public.user_monitor_stock m
          WHERE s.direction = 'buy'
            AND m.principal_id = (authority->>'principal_id')::bigint
            AND m.principal_type = authority->>'principal_type'
            AND m.user_id = (authority->>'user_id')::bigint
            AND m.asset_kind = 'stock'
            AND m.identity_key = s.identity_key
            AND m.direction = 'buy'
            AND m.status = 'active'
            AND m.quality_status = 'reviewed'
            AND m.valid_source_trade_date = approved.source_trade_date
            AND m.valid_for_trade_date = approved.for_trade_date
            AND m.valid_source_run_id = approved.source_run_id
            AND m.source_run_id = approved.source_run_id
            AND m.source_snapshot_json->>'identity_key' = m.identity_key
            AND m.source_snapshot_json->>'source_trade_date' = approved.source_trade_date
            AND m.source_snapshot_json->>'for_trade_date' = approved.for_trade_date
            AND m.source_snapshot_json->>'source_run_id' = approved.source_run_id
          UNION ALL
          SELECT 'realtime'::text, NULL::bigint, NULL::integer, 3
          FROM public.user_realtime_monitor_scope rs
          WHERE s.direction = 'buy'
            AND rs.principal_id = (authority->>'principal_id')::bigint
            AND rs.principal_type = authority->>'principal_type'
            AND rs.user_id = (authority->>'user_id')::bigint
            AND rs.asset_kind = 'stock'
            AND rs.identity_key = s.identity_key
            AND rs.status = 'active'
            AND rs.deleted_at IS NULL
            AND rs.source_type = 'single_row'
            AND rs.source_snapshot_json->>'identity_key' = rs.identity_key
        ) candidate
        ORDER BY candidate.scope_priority
        LIMIT 1
      ) scope ON true
      WHERE s.for_trade_date = current_trade_date
    )
    SELECT s.identity_key,
           s.direction,
           CASE
             WHEN s.action_state = 'executed' THEN 'action_price'
             WHEN s.action_state = 'eligible' THEN 'trigger_price'
           END,
           CASE
             WHEN s.action_state = 'executed'
              AND COALESCE(
                    s.card_payload_json->>'action_price',
                    s.display_payload_json->>'action_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      s.card_payload_json->>'action_price',
                      s.display_payload_json->>'action_price'
                    )::numeric
             WHEN s.action_state = 'eligible'
              AND COALESCE(
                    s.card_payload_json->>'trigger_price',
                    s.display_payload_json->>'trigger_price'
                  ) ~ '^[0-9]+([.][0-9]+)?$'
               THEN COALESCE(
                      s.card_payload_json->>'trigger_price',
                      s.display_payload_json->>'trigger_price'
                    )::numeric
           END,
           CASE
             WHEN s.card_target_price IS NOT NULL THEN s.card_target_price
             ELSE s.projection_target_price
           END,
           s.user_signal_projection_id,
           s.virtual_position_id,
           s.holding_episode_no,
           s.for_trade_date,
           s.scope_authority,
           s.score_json
      INTO v_identity_key, v_side, v_reference_kind, v_reference_price,
           v_target_price, v_projection_id, v_position_id, v_episode,
           v_for_trade_date, v_scope_authority, v_score_json
    FROM authorized_source s;

    IF v_projection_id IS NULL
       OR v_identity_key IS NULL
       OR v_side IS NULL
       OR v_for_trade_date IS DISTINCT FROM current_trade_date
       OR v_reference_kind IS NULL
       OR v_reference_price IS NULL
       OR v_reference_price <= 0
       OR v_target_price IS NULL
       OR v_target_price <= 0
       OR v_scope_authority IS NULL
       OR (v_side = 'sell' AND (
             v_scope_authority <> 'open_position'
             OR v_position_id IS NULL
             OR v_episode IS NULL
             OR v_episode <= 0
           )) THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'signal_not_in_effective_scope'
      );
    END IF;
  ELSE
    SELECT p.identity_key, 'sell', 'manual', NULL,
           p.virtual_position_id, p.holding_episode_no
      INTO v_identity_key, v_side, v_reference_kind, v_reference_price,
           v_position_id, v_episode
    FROM public.n6_virtual_position p
    WHERE p.virtual_position_id = p_source_id
      AND p.virtual_account_id = account_id
      AND p.principal_id = (authority->>'principal_id')::bigint
      AND p.principal_type = authority->>'principal_type'
      AND p.asset_kind = 'stock'
      AND p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
      AND p.position_status = 'open_virtual'
      AND p.quantity > 0
      AND p.holding_episode_no > 0
      AND EXISTS (
        SELECT 1
        FROM public.n6_virtual_position_lot lot
        WHERE lot.virtual_position_id = p.virtual_position_id
          AND lot.virtual_account_id = p.virtual_account_id
          AND lot.principal_id = p.principal_id
          AND lot.principal_type = p.principal_type
          AND lot.identity_key = p.identity_key
          AND lot.holding_episode_no = p.holding_episode_no
          AND lot.remaining_quantity > 0
          AND lot.available_trade_date <= pg_catalog.to_date(
            current_trade_date, 'YYYYMMDD'
          )
          AND lot.lot_status IN ('locked_t1', 'available')
      );
    IF v_position_id IS NULL OR v_episode IS NULL THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'not_found',
        'error', 'sellable_position_not_found'
      );
    END IF;
    v_for_trade_date := current_trade_date;
    v_scope_authority := 'manual_position';
  END IF;

  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id, principal_type, user_id, virtual_account_id, source_type, source_id,
    source_signal_projection_id, source_virtual_position_id, holding_episode_no,
    asset_kind, identity_key, proposal_side, signal_reference_kind,
    signal_reference_price, locked_target_price, proposal_status, expires_at,
    policy_version, policy_hash, source_lineage_json
  ) VALUES (
    (authority->>'principal_id')::bigint, authority->>'principal_type',
    (authority->>'user_id')::bigint, account_id, p_source_type, p_source_id::text,
    v_projection_id,
    CASE WHEN p_source_type = 'manual_position' THEN v_position_id ELSE NULL END,
    v_episode, 'stock', v_identity_key, v_side, v_reference_kind,
    v_reference_price, v_target_price, 'pending',
    pg_catalog.now() + interval '60 seconds',
    'n6_virtual_trade_proposal_v2_048',
    '4db44fa6cd1cbfd9cdb7e02c697f1354f7b938dd8262c41149c40ee5a409b2a8',
    pg_catalog.jsonb_build_object(
      'source_type', p_source_type,
      'source_id', p_source_id::text,
      'for_trade_date', v_for_trade_date,
      'scope_authority', v_scope_authority,
      'frozen_virtual_position_id', v_position_id,
      'frozen_holding_episode_no', v_episode,
      'frozen_score', v_score_json
    )
  ) RETURNING * INTO result_row;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'created', 'item',
    pg_catalog.jsonb_build_object(
      'proposal_id', result_row.proposal_id,
      'proposal_status', result_row.proposal_status,
      'expires_at', result_row.expires_at,
      'proposal_side', result_row.proposal_side,
      'identity_key', result_row.identity_key,
      'signal_reference_kind', result_row.signal_reference_kind,
      'signal_reference_price', result_row.signal_reference_price
    )
  );
EXCEPTION WHEN unique_violation THEN
  RETURN pg_catalog.jsonb_build_object(
    'ok', false, 'status', 'conflict', 'error', 'proposal_already_exists'
  );
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_apply_claimed_proposal(
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
  account public.n6_virtual_account%ROWTYPE;
  cash_before public.n6_virtual_cash_snapshot%ROWTYPE;
  quote public.n6_virtual_quote_snapshot%ROWTYPE;
  position_before public.n6_virtual_position%ROWTYPE;
  lot_row public.n6_virtual_position_lot%ROWTYPE;
  trade_date_date date;
  next_trade_date date;
  trade_date_integer integer;
  fill_quantity numeric(24,4);
  fill_price numeric(24,6);
  gross_amount numeric(24,4);
  position_cost_delta numeric(24,4);
  cash_delta numeric(24,4);
  new_available_cash numeric(24,4);
  new_quantity numeric(24,4);
  new_available_quantity numeric(24,4);
  new_locked_quantity numeric(24,4);
  new_average_cost numeric(24,6);
  position_id bigint;
  order_id bigint;
  trade_id bigint;
  ledger_id bigint;
  new_cash_snapshot_id bigint;
  new_position_event_id bigint;
  episode_no integer;
  remaining_to_sell numeric(24,4);
  old_available_lot_quantity numeric(24,4) := 0;
  old_locked_lot_quantity numeric(24,4) := 0;
  active_cash_snapshot_count integer;
  active_cash_snapshot_id bigint;
  position_pointer_update_count integer;
  lineage jsonb;
  ai_risk_result jsonb;
BEGIN
  IF p_proposal_id IS NULL OR p_proposal_id <= 0
     OR p_executor_run_id IS NULL OR btrim(p_executor_run_id) = ''
     OR length(p_executor_run_id) > 200 THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;

  SELECT * INTO proposal
  FROM public.n6_virtual_trade_proposal
  WHERE proposal_id = p_proposal_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_not_found');
  END IF;

  IF proposal.proposal_status = 'executed'
     AND proposal.executor_run_id = p_executor_run_id
     AND proposal.executed_virtual_order_id IS NOT NULL
     AND proposal.executed_virtual_trade_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'executed', 'idempotent', true,
      'proposal_id', proposal.proposal_id,
      'virtual_order_id', proposal.executed_virtual_order_id,
      'virtual_trade_id', proposal.executed_virtual_trade_id
    );
  END IF;
  IF proposal.proposal_status <> 'processing'
     OR proposal.executor_run_id IS DISTINCT FROM p_executor_run_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'not_claimed');
  END IF;
  IF proposal.expires_at <= pg_catalog.clock_timestamp() THEN
    IF proposal.source_type = 'stop_loss' THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'expired', failure_reason = 'proposal_expired',
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id;
      RETURN pg_catalog.jsonb_build_object('ok', true, 'status', 'expired',
        'proposal_id', proposal.proposal_id, 'account_writes', 0);
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_expired');
  END IF;
  IF proposal.source_type NOT IN (
       'signal', 'manual_position', 'stop_loss', 'ai_risk'
     )
     OR proposal.asset_kind <> 'stock'
     OR proposal.identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
     OR proposal.proposal_side NOT IN ('buy', 'sell') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_not_eligible');
  END IF;

  IF proposal.principal_type = 'ai_user' THEN
    IF proposal.user_id IS NOT NULL
       OR proposal.actor_ai_user_id IS NULL
       OR (
         proposal.source_type IN ('signal', 'ai_risk')
         AND proposal.source_ai_decision_id IS NULL
       )
       OR (
         proposal.source_type = 'stop_loss'
         AND proposal.source_ai_decision_id IS NOT NULL
       )
       OR proposal.source_type NOT IN ('signal', 'ai_risk', 'stop_loss')
       OR NOT EXISTS (
         SELECT 1
         FROM public.n6_principal principal
         JOIN public.n6_ai_user ai
           ON ai.principal_id = principal.principal_id
          AND ai.principal_type = principal.principal_type
          AND ai.ai_user_id = proposal.actor_ai_user_id
          AND ai.status = 'active'
         WHERE principal.principal_id = proposal.principal_id
           AND principal.principal_type = proposal.principal_type
           AND principal.principal_status = 'active'
           AND principal.owner_user_id IS NULL
       ) THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'failed',
          failure_reason = 'ai_actor_authority_failed',
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id
        AND proposal_status = 'processing'
        AND executor_run_id = p_executor_run_id;
      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'failed', 'proposal_id', proposal.proposal_id,
        'failure_reason', 'ai_actor_authority_failed', 'account_writes', 0
      );
    END IF;

    BEGIN
      ai_risk_result := public.n6_ai_executor_risk_recheck(
        proposal.proposal_id, p_executor_run_id
      );
    EXCEPTION
      WHEN OTHERS THEN
        ai_risk_result := NULL;
    END;
    IF ai_risk_result IS NULL
       OR pg_catalog.jsonb_typeof(ai_risk_result) <> 'object'
       OR ai_risk_result->>'ok' <> 'true'
       OR ai_risk_result->>'status' <> 'passed' THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'failed',
          failure_reason = 'ai_risk_recheck_failed_closed',
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id
        AND proposal_status = 'processing'
        AND executor_run_id = p_executor_run_id;
      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'failed', 'proposal_id', proposal.proposal_id,
        'failure_reason', 'ai_risk_recheck_failed_closed',
        'account_writes', 0
      );
    END IF;
  ELSE
    IF proposal.principal_type NOT IN ('admin', 'human_user')
       OR proposal.actor_ai_user_id IS NOT NULL
       OR proposal.source_ai_decision_id IS NOT NULL
       OR proposal.source_type = 'ai_risk' THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', false, 'status', 'proposal_actor_scope_mismatch'
      );
    END IF;
  END IF;

  SELECT * INTO account
  FROM public.n6_virtual_account
  WHERE virtual_account_id = proposal.virtual_account_id
  FOR UPDATE;
  IF NOT FOUND
     OR account.virtual_account_status <> 'active'
     OR account.principal_id <> proposal.principal_id
     OR account.principal_type <> proposal.principal_type THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'account_scope_mismatch');
  END IF;

  SELECT * INTO cash_before
  FROM public.n6_virtual_cash_snapshot
  WHERE cash_snapshot_id = account.current_cash_snapshot_id
    AND virtual_account_id = account.virtual_account_id
    AND snapshot_status = 'active'
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_not_ready');
  END IF;

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
  IF cash_before.trade_date > trade_date_integer THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_trade_date_ahead');
  END IF;
  WITH locked_cash AS (
    SELECT cash_snapshot_id
    FROM public.n6_virtual_cash_snapshot
    WHERE virtual_account_id = proposal.virtual_account_id
      AND snapshot_status = 'active'
    FOR UPDATE
  )
  SELECT count(*), min(cash_snapshot_id)
  INTO active_cash_snapshot_count, active_cash_snapshot_id
  FROM locked_cash;
  IF active_cash_snapshot_count <> 1
     OR active_cash_snapshot_id <> cash_before.cash_snapshot_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_authority_conflict');
  END IF;

  SELECT * INTO position_before
  FROM public.n6_virtual_position
  WHERE virtual_account_id = proposal.virtual_account_id
    AND asset_kind = 'stock'
    AND identity_key = proposal.identity_key
  FOR UPDATE;
  IF FOUND AND (
       position_before.principal_id <> proposal.principal_id
       OR position_before.principal_type <> proposal.principal_type
  ) THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'position_scope_mismatch');
  END IF;
  IF position_before.virtual_position_id IS NOT NULL THEN
    WITH locked_lots AS (
      SELECT remaining_quantity, available_trade_date, lot_status
      FROM public.n6_virtual_position_lot
      WHERE virtual_position_id = position_before.virtual_position_id
        AND virtual_account_id = proposal.virtual_account_id
        AND principal_id = proposal.principal_id
        AND principal_type = proposal.principal_type
        AND identity_key = proposal.identity_key
        AND (
          proposal.source_type <> 'stop_loss'
          OR holding_episode_no = proposal.holding_episode_no
        )
        AND remaining_quantity > 0
      FOR UPDATE
    )
    SELECT
      COALESCE(sum(remaining_quantity) FILTER (
        WHERE available_trade_date <= trade_date_date
          AND lot_status IN ('locked_t1', 'available')
      ), 0),
      COALESCE(sum(remaining_quantity) FILTER (
        WHERE available_trade_date > trade_date_date
          AND lot_status = 'locked_t1'
      ), 0)
    INTO old_available_lot_quantity, old_locked_lot_quantity
    FROM locked_lots;
  END IF;

  IF proposal.source_type = 'stop_loss' THEN
    IF proposal.proposal_side <> 'sell'
       OR proposal.source_virtual_position_id IS DISTINCT FROM position_before.virtual_position_id
       OR proposal.holding_episode_no IS NULL
       OR proposal.holding_episode_no IS DISTINCT FROM position_before.holding_episode_no
       OR position_before.position_status <> 'open_virtual'
       OR position_before.quantity <= 0
       OR position_before.stop_loss_status <> 'frozen'
       OR position_before.stop_loss_effective_trade_date IS NULL
       OR position_before.stop_loss_effective_trade_date > trade_date_date
       OR position_before.stop_loss_price IS NULL
       OR position_before.stop_loss_price <= 0
       OR position_before.stop_loss_price::text IN ('NaN', 'Infinity', '-Infinity')
       OR quote.current_price > position_before.stop_loss_price
       OR old_available_lot_quantity <= 0 THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'failed',
          failure_reason = CASE
            WHEN quote.current_price > position_before.stop_loss_price
              THEN 'stop_loss_quote_recovered'
            WHEN old_available_lot_quantity <= 0
              THEN 'stop_loss_t1_lot_not_sellable'
            ELSE 'stop_loss_revalidation_failed'
          END,
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id;
      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'failed', 'proposal_id', proposal.proposal_id,
        'account_writes', 0
      );
    END IF;
  END IF;

  IF proposal.source_type <> 'stop_loss'
     AND position_before.position_status = 'open_virtual'
     AND position_before.quantity
         <> old_available_lot_quantity + old_locked_lot_quantity THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'lot_position_mismatch');
  END IF;

  IF proposal.proposal_side = 'buy' THEN
    IF proposal.source_type <> 'signal' THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'buy_source_not_allowed');
    END IF;
    IF (
         position_before.virtual_position_id IS NULL
         OR position_before.position_status = 'closed_virtual'
         OR position_before.quantity = 0
       )
       AND (
         proposal.locked_target_price IS NULL
         OR proposal.locked_target_price <= 0
         OR proposal.source_signal_projection_id IS NULL
       ) THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'target_price_not_ready');
    END IF;
    fill_quantity := pg_catalog.floor(
      LEAST(300000::numeric, cash_before.available_cash) / fill_price / 100
    ) * 100;
    IF fill_quantity < 100 THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'budget_below_one_lot');
    END IF;
    gross_amount := pg_catalog.round(fill_quantity * fill_price, 4);
    IF cash_before.available_cash < gross_amount THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'insufficient_cash');
    END IF;
    SELECT pg_catalog.to_date(min(trade_date)::text, 'YYYYMMDD') INTO next_trade_date
    FROM public.common_trade_calendar
    WHERE trade_date > trade_date_integer::text AND is_open = true;
    IF next_trade_date IS NULL THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'next_trade_date_not_ready');
    END IF;
    episode_no := CASE
      WHEN position_before.virtual_position_id IS NULL THEN 1
      WHEN position_before.position_status = 'closed_virtual' OR position_before.quantity = 0
        THEN position_before.holding_episode_no + 1
      ELSE position_before.holding_episode_no
    END;
    new_quantity := COALESCE(position_before.quantity, 0) + fill_quantity;
    new_available_quantity := old_available_lot_quantity;
    new_locked_quantity := old_locked_lot_quantity + fill_quantity;
    new_average_cost := pg_catalog.round(
      ((COALESCE(position_before.quantity, 0) * COALESCE(position_before.average_cost, 0))
        + gross_amount) / new_quantity, 6
    );
    cash_delta := -gross_amount;
    position_cost_delta := gross_amount;
  ELSE
    IF position_before.virtual_position_id IS NULL
       OR position_before.position_status <> 'open_virtual'
       OR position_before.quantity <= 0
       OR (
         proposal.source_type IN ('manual_position', 'stop_loss', 'ai_risk')
         AND proposal.source_virtual_position_id IS DISTINCT FROM position_before.virtual_position_id
       ) THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'position_not_sellable');
    END IF;
    IF proposal.holding_episode_no IS NULL
       OR proposal.holding_episode_no <> position_before.holding_episode_no THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'holding_episode_mismatch');
    END IF;
    fill_quantity := old_available_lot_quantity;
    IF fill_quantity <= 0 OR fill_quantity > position_before.quantity THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 't1_quantity_not_sellable');
    END IF;
    gross_amount := pg_catalog.round(fill_quantity * fill_price, 4);
    episode_no := position_before.holding_episode_no;
    new_quantity := position_before.quantity - fill_quantity;
    new_available_quantity := 0;
    new_locked_quantity := old_locked_lot_quantity;
    IF new_quantity <> new_available_quantity + new_locked_quantity THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'lot_position_mismatch');
    END IF;
    new_average_cost := CASE WHEN new_quantity = 0 THEN 0 ELSE position_before.average_cost END;
    cash_delta := gross_amount;
    position_cost_delta := -pg_catalog.round(
      fill_quantity * position_before.average_cost, 4
    );
  END IF;

  new_available_cash := cash_before.available_cash + cash_delta;
  IF new_available_cash < 0 THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'insufficient_cash');
  END IF;
  lineage := pg_catalog.jsonb_build_object(
    'source_proposal_id', proposal.proposal_id,
    'confirm_idempotency_key', proposal.confirm_idempotency_key,
    'fill_quote_snapshot_id', quote.virtual_quote_snapshot_id,
    'executor_run_id', p_executor_run_id
  );

  INSERT INTO public.n6_virtual_order (
    virtual_account_id, principal_id, principal_type, asset_kind, identity_key,
    signal_type, order_side, order_type, order_status, requested_quantity,
    requested_price, estimated_fee_amount, estimated_tax_amount,
    fee_policy_version, tax_policy_version, execution_policy_version,
    execution_policy_hash, market_rule_set, run_id, policy_version, policy_hash,
    rollback_scope, source_lineage_json, quality_status, source_proposal_id,
    source_signal_projection_id, signal_reference_kind, signal_reference_price,
    fill_quote_snapshot_id
  ) VALUES (
    proposal.virtual_account_id, proposal.principal_id, proposal.principal_type,
    'stock', proposal.identity_key,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'B_BUY' ELSE 'S_SELL' END,
    proposal.proposal_side, 'market_virtual', 'filled_virtual', fill_quantity,
    fill_price, 0, 0, 'n6_046_zero_fee_v1', 'n6_046_zero_tax_v1',
    'n6_046_latest_quote_fill_v1', 'n6_046_latest_quote_fill_v1',
    'a_share_t_plus_1_virtual_v1', p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, lineage, 'passed', proposal.proposal_id,
    proposal.source_signal_projection_id,
    proposal.signal_reference_kind, proposal.signal_reference_price,
    quote.virtual_quote_snapshot_id
  ) RETURNING virtual_order_id INTO order_id;

  INSERT INTO public.n6_virtual_trade (
    virtual_order_id, virtual_account_id, principal_id, principal_type,
    asset_kind, identity_key, trade_side, filled_quantity, filled_price,
    gross_amount, commission_amount, stamp_tax_amount, transfer_fee_amount,
    total_fee_amount, net_amount, fill_policy_version, fill_policy_hash,
    replay_deterministic_seed, trade_status, trade_time, source_lineage_json,
    run_id, policy_version, policy_hash, rollback_scope, quality_status,
    source_proposal_id, signal_reference_kind, signal_reference_price,
    fill_quote_snapshot_id
  ) VALUES (
    order_id, proposal.virtual_account_id, proposal.principal_id,
    proposal.principal_type, 'stock', proposal.identity_key,
    proposal.proposal_side, fill_quantity, fill_price, gross_amount,
    0, 0, 0, 0, gross_amount, 'n6_046_latest_quote_fill_v1',
    'n6_046_latest_quote_fill_v1', 'source_proposal:' || proposal.proposal_id,
    'filled_virtual', pg_catalog.clock_timestamp(), lineage, p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, 'passed', proposal.proposal_id,
    proposal.signal_reference_kind, proposal.signal_reference_price,
    quote.virtual_quote_snapshot_id
  ) RETURNING virtual_trade_id INTO trade_id;

  INSERT INTO public.n6_virtual_cash_ledger (
    virtual_account_id, ledger_type, amount, currency, trade_date, event_time,
    source_event_type, source_event_id, source_virtual_order_id,
    source_virtual_trade_id, run_id, policy_version, policy_hash,
    rollback_scope, source_lineage_json, quality_status
  ) VALUES (
    proposal.virtual_account_id,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'virtual_buy' ELSE 'virtual_sell' END,
    cash_delta, 'CNY', trade_date_integer, pg_catalog.clock_timestamp(),
    'n6_virtual_executor_046', proposal.proposal_id::text, order_id, trade_id,
    p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
    'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed'
  ) RETURNING cash_ledger_id INTO ledger_id;

  UPDATE public.n6_virtual_cash_snapshot
  SET snapshot_status = 'superseded'
  WHERE cash_snapshot_id = cash_before.cash_snapshot_id;
  INSERT INTO public.n6_virtual_cash_snapshot (
    virtual_account_id, snapshot_time, trade_date, available_cash, frozen_cash,
    total_cash, currency, source_ledger_max_id, snapshot_status, run_id,
    policy_version, policy_hash, rollback_scope, source_lineage_json,
    quality_status
  ) VALUES (
    proposal.virtual_account_id, pg_catalog.clock_timestamp(), trade_date_integer,
    new_available_cash, cash_before.frozen_cash,
    new_available_cash + cash_before.frozen_cash, 'CNY', ledger_id, 'active',
    p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
    'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed'
  ) RETURNING cash_snapshot_id INTO new_cash_snapshot_id;
  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = new_cash_snapshot_id, updated_at = pg_catalog.now()
  WHERE virtual_account_id = proposal.virtual_account_id;

  UPDATE public.n6_virtual_position_lot
  SET lot_status = 'available', updated_at = pg_catalog.now()
  WHERE virtual_position_id = position_before.virtual_position_id
    AND remaining_quantity > 0
    AND available_trade_date <= trade_date_date
    AND lot_status = 'locked_t1';

  IF position_before.virtual_position_id IS NULL THEN
    INSERT INTO public.n6_virtual_position (
      virtual_account_id, principal_id, principal_type, asset_kind, identity_key,
      position_status, quantity, available_quantity, locked_quantity,
      average_cost, last_virtual_trade_id, run_id, policy_version, policy_hash,
      rollback_scope, source_lineage_json, quality_status, holding_episode_no,
      first_open_trade_date, locked_target_price, target_price_status,
      target_price_source_signal_projection_id, stop_loss_status
    ) VALUES (
      proposal.virtual_account_id, proposal.principal_id, proposal.principal_type,
      'stock', proposal.identity_key, 'open_virtual', new_quantity,
      new_available_quantity, new_locked_quantity, new_average_cost, trade_id,
      p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
      'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed',
      episode_no, trade_date_date, proposal.locked_target_price, 'frozen',
      proposal.source_signal_projection_id, 'provisional_first_day'
    ) RETURNING virtual_position_id INTO position_id;
  ELSE
    position_id := position_before.virtual_position_id;
    UPDATE public.n6_virtual_position
    SET position_status = CASE WHEN new_quantity = 0 THEN 'closed_virtual' ELSE 'open_virtual' END,
        quantity = new_quantity, available_quantity = new_available_quantity,
        locked_quantity = new_locked_quantity, average_cost = new_average_cost,
        last_virtual_trade_id = trade_id, run_id = p_executor_run_id,
        policy_version = 'n6_btrack_virtual_executor_046_v1',
        policy_hash = 'n6_btrack_virtual_executor_046_v1',
        rollback_scope = p_executor_run_id, source_lineage_json = lineage,
        quality_status = 'passed', holding_episode_no = episode_no,
        first_open_trade_date = CASE
          WHEN position_before.position_status = 'closed_virtual' OR position_before.quantity = 0
            THEN trade_date_date
          ELSE position_before.first_open_trade_date
        END,
        locked_target_price = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN proposal.locked_target_price
          ELSE position_before.locked_target_price
        END,
        target_price_status = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN 'frozen'
          ELSE position_before.target_price_status
        END,
        target_price_source_signal_projection_id = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN proposal.source_signal_projection_id
          ELSE position_before.target_price_source_signal_projection_id
        END,
        stop_loss_status = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN 'provisional_first_day'
          ELSE position_before.stop_loss_status
        END,
        stop_loss_price = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_price
        END,
        stop_loss_source_quote_snapshot_id = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_source_quote_snapshot_id
        END,
        stop_loss_frozen_at = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_frozen_at
        END,
        stop_loss_effective_trade_date = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_effective_trade_date
        END,
        stop_loss_policy_version = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_policy_version
        END,
        stop_loss_policy_hash = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_policy_hash
        END,
        updated_at = pg_catalog.now()
    WHERE virtual_position_id = position_id;
  END IF;

  IF proposal.proposal_side = 'buy' THEN
    INSERT INTO public.n6_virtual_position_lot (
      virtual_position_id, virtual_account_id, principal_id, principal_type,
      identity_key, holding_episode_no, source_virtual_trade_id, open_trade_date,
      available_trade_date, original_quantity, remaining_quantity, cost_price,
      lot_status
    ) VALUES (
      position_id, proposal.virtual_account_id, proposal.principal_id,
      proposal.principal_type, proposal.identity_key, episode_no, trade_id,
      trade_date_date, next_trade_date, fill_quantity, fill_quantity, fill_price,
      'locked_t1'
    );
  ELSE
    remaining_to_sell := fill_quantity;
    FOR lot_row IN
      SELECT * FROM public.n6_virtual_position_lot
      WHERE virtual_position_id = position_id
        AND remaining_quantity > 0
        AND available_trade_date <= trade_date_date
      ORDER BY available_trade_date, virtual_position_lot_id
      FOR UPDATE
    LOOP
      EXIT WHEN remaining_to_sell <= 0;
      UPDATE public.n6_virtual_position_lot
      SET remaining_quantity = remaining_quantity - LEAST(remaining_quantity, remaining_to_sell),
          lot_status = CASE
            WHEN remaining_quantity - LEAST(remaining_quantity, remaining_to_sell) = 0 THEN 'closed'
            ELSE 'available'
          END,
          updated_at = pg_catalog.now()
      WHERE virtual_position_lot_id = lot_row.virtual_position_lot_id;
      remaining_to_sell := remaining_to_sell - LEAST(lot_row.remaining_quantity, remaining_to_sell);
    END LOOP;
    IF remaining_to_sell <> 0 THEN
      RAISE EXCEPTION '046 sell lot allocation mismatch';
    END IF;
  END IF;

  INSERT INTO public.n6_virtual_position_event (
    virtual_position_id, virtual_account_id, principal_id, principal_type,
    asset_kind, identity_key, event_type, quantity_delta, cost_delta,
    source_virtual_order_id, source_virtual_trade_id, event_time, run_id,
    policy_version, policy_hash, rollback_scope, source_lineage_json,
    quality_status
  ) VALUES (
    position_id, proposal.virtual_account_id, proposal.principal_id,
    proposal.principal_type, 'stock', proposal.identity_key,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'virtual_buy_fill' ELSE 'virtual_sell_fill' END,
    CASE WHEN proposal.proposal_side = 'buy' THEN fill_quantity ELSE -fill_quantity END,
    position_cost_delta,
    order_id, trade_id, pg_catalog.clock_timestamp(), p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, lineage, 'passed'
  ) RETURNING position_event_id INTO new_position_event_id;

  UPDATE public.n6_virtual_position
  SET source_position_event_id = new_position_event_id,
      updated_at = pg_catalog.now()
  WHERE virtual_position_id = position_id;
  GET DIAGNOSTICS position_pointer_update_count = ROW_COUNT;
  IF position_pointer_update_count <> 1 THEN
    RAISE EXCEPTION '046 position event pointer update count: %',
      position_pointer_update_count;
  END IF;

  UPDATE public.n6_virtual_trade_proposal
  SET proposal_status = 'executed',
      executed_virtual_order_id = order_id,
      executed_virtual_trade_id = trade_id,
      failure_reason = NULL,
      updated_at = pg_catalog.now()
  WHERE proposal_id = proposal.proposal_id
    AND proposal_status = 'processing'
    AND executor_run_id = p_executor_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION '046 proposal lost processing ownership';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'executed', 'idempotent', false,
    'proposal_id', proposal.proposal_id, 'virtual_order_id', order_id,
    'virtual_trade_id', trade_id, 'cash_ledger_id', ledger_id,
    'cash_snapshot_id', new_cash_snapshot_id, 'virtual_position_id', position_id,
    'position_event_id', new_position_event_id, 'fill_quote_snapshot_id',
    quote.virtual_quote_snapshot_id, 'filled_quantity', fill_quantity,
    'filled_price', fill_price
  );
END
$function$;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  FROM PUBLIC, n6_ai_agent, n6_quote_writer, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  TO n6_virtual_executor;

DO $authority_check$
DECLARE
  function_name text;
  expected_role text;
  function_owner text;
  function_security_definer boolean;
  function_config text[];
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR function_name, expected_role IN
    SELECT *
    FROM (VALUES
      ('public.n6_btrack_proposal_create(text,text,bigint)', 'n6_btrack_web'),
      ('public.n6_executor_apply_claimed_proposal(bigint,text)', 'n6_virtual_executor')
    ) expected(function_name, expected_role)
  LOOP
    IF pg_catalog.to_regprocedure(function_name) IS NULL THEN
      RAISE EXCEPTION '063 required function missing: %', function_name;
    END IF;

    SELECT pg_catalog.pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig
      INTO function_owner, function_security_definer, function_config
    FROM pg_catalog.pg_proc p
    WHERE p.oid = function_name::pg_catalog.regprocedure;

    IF function_owner <> current_user
       OR function_security_definer IS DISTINCT FROM true
       OR function_config IS DISTINCT FROM ARRAY['search_path=pg_catalog']::text[] THEN
      RAISE EXCEPTION '063 function authority drift: %', function_name;
    END IF;

    SELECT
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl
        JOIN pg_catalog.pg_roles role
          ON role.oid = acl.grantee
        WHERE target.oid = function_name::pg_catalog.regprocedure
          AND role.rolname = expected_role
          AND acl.privilege_type = 'EXECUTE'
          AND acl.is_grantable IS FALSE
      ),
      EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(target.proacl, pg_catalog.acldefault('f', target.proowner))
        ) acl
        LEFT JOIN pg_catalog.pg_roles role
          ON role.oid = acl.grantee
        WHERE target.oid = function_name::pg_catalog.regprocedure
          AND acl.privilege_type = 'EXECUTE'
          AND acl.grantee <> target.proowner
          AND (
            acl.grantee = 0
            OR role.rolname IS DISTINCT FROM expected_role
            OR acl.is_grantable IS NOT FALSE
          )
      )
      INTO expected_execute, unexpected_execute;

    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '063 function ACL drift: %', function_name;
    END IF;
  END LOOP;
END
$authority_check$;

COMMIT;
