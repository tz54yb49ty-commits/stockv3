-- N6 B-track Product V3 virtual executor persistence interface.
-- DRAFT ONLY: do not execute without a separate migration gate.
-- Function-only authority with an N6-owned write allowlist.

BEGIN;

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
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_expired');
  END IF;
  IF proposal.source_type = 'stop_loss' THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'source_not_allowed');
  END IF;
  IF proposal.source_type NOT IN ('signal', 'manual_position')
     OR proposal.asset_kind <> 'stock'
     OR proposal.identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
     OR proposal.proposal_side NOT IN ('buy', 'sell') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_not_eligible');
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
    IF position_before.position_status = 'open_virtual'
       AND position_before.quantity
           <> old_available_lot_quantity + old_locked_lot_quantity THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'lot_position_mismatch');
    END IF;
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
         proposal.source_type = 'manual_position'
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

REVOKE EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) FROM n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text) TO n6_virtual_executor;

COMMIT;
