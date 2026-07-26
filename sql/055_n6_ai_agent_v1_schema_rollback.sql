-- N6 B-track AI simulated investor V1 schema rollback.
-- Fail closed: this rollback is allowed only before any AI identity, account,
-- decision, proposal, lot, quote, order, trade, position, cash, or PnL fact exists.
-- The shared signal projection is derived and may be dropped only while every
-- row is exactly rebuildable from an approved immutable N6 projection source.
-- It never deletes business history and never rolls back schema 041-054.

BEGIN;

LOCK TABLE public.n6_principal IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_user IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_strategy IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_principal_account IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_account IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_trade_proposal IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_position_lot IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_order IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_trade IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_position IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_position_event IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_pnl_snapshot IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_cash_ledger IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_cash_snapshot IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_quote_run IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_quote_snapshot IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.user_projection_run IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.user_signal_projection IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_shared_signal_projection
  IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_context_snapshot IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_decision_run IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_decision IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_daily_summary IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_strategy_evaluation IN SHARE ROW EXCLUSIVE MODE;

DO $rollback_preflight$
DECLARE
  history_count bigint;
  null_human_actor_count bigint;
  active_connection_count bigint;
  non_rebuildable_shared_count bigint;
BEGIN
  SELECT count(*) INTO active_connection_count
  FROM pg_catalog.pg_stat_activity
  WHERE usename IN ('n6_ai_agent', 'n6_virtual_executor', 'n6_btrack_web')
    AND pid <> pg_catalog.pg_backend_pid()
    AND state IS DISTINCT FROM 'idle';
  IF active_connection_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: active restricted-role connections=%',
      active_connection_count;
  END IF;

  SELECT
      (SELECT count(*) FROM public.n6_ai_context_snapshot)
    + (SELECT count(*) FROM public.n6_ai_decision_run)
    + (SELECT count(*) FROM public.n6_ai_decision)
    + (SELECT count(*) FROM public.n6_ai_daily_summary)
    + (SELECT count(*) FROM public.n6_ai_strategy_evaluation)
    INTO history_count;
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI decision/report history=%',
      history_count;
  END IF;

  WITH rebuildable_source AS (
    SELECT
      projection.user_signal_projection_id,
      projection.user_projection_run_id,
      projection.source_event_id,
      (projection.source_payload_json->>'event_time')::timestamptz
        AS source_event_time,
      projection.source_outbox_id,
      projection.source_action_event_id,
      projection.source_action_run_id,
      pg_catalog.to_date(
        COALESCE(
          projection.display_payload_json->>'for_trade_date',
          projection.source_payload_json->>'trade_date'
        ),
        'YYYYMMDD'
      ) AS for_trade_date,
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
      END AS trigger_price,
      CASE
        WHEN projection.display_payload_json->>'action_price'
               ~ '^[0-9]+([.][0-9]+)?$'
          THEN (projection.display_payload_json->>'action_price')::numeric
        ELSE NULL
      END AS action_price,
      projection.expected_return_pct,
      projection.board_identity_key,
      projection.board_code,
      projection.board_name,
      projection.action_state,
      projection.action_mark,
      projection.condition_key,
      projection.original_condition_key,
      safe.reason_fields_json,
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
              'reason_fields', safe.reason_fields_json
            )::text,
            'UTF8'
          )
        ),
        'hex'
      ) AS expected_payload_hash
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
                   projection.display_payload_json
                     ->>'buy_expected_return_pct',
                 'sell_expected_return_pct',
                   projection.display_payload_json
                     ->>'sell_expected_return_pct',
                 'score', projection.display_payload_json->>'score',
                 'pe_core', projection.display_payload_json->>'pe_core'
               )
             ) AS reason_fields_json
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
      AND projection.identity_key <> ''
      AND projection.code <> ''
      AND projection.name <> ''
  )
  SELECT count(*) INTO non_rebuildable_shared_count
  FROM public.n6_ai_shared_signal_projection shared
  LEFT JOIN rebuildable_source source
    ON source.user_signal_projection_id =
         shared.source_signal_projection_id
  WHERE source.user_signal_projection_id IS NULL
     OR shared.user_projection_run_id IS DISTINCT FROM
          source.user_projection_run_id
     OR shared.source_event_id IS DISTINCT FROM source.source_event_id
     OR shared.source_event_time IS DISTINCT FROM source.source_event_time
     OR shared.source_outbox_id IS DISTINCT FROM source.source_outbox_id
     OR shared.source_action_event_id IS DISTINCT FROM
          source.source_action_event_id
     OR shared.source_action_run_id IS DISTINCT FROM
          source.source_action_run_id
     OR shared.for_trade_date IS DISTINCT FROM source.for_trade_date
     OR shared.asset_kind IS DISTINCT FROM source.asset_kind
     OR shared.identity_key IS DISTINCT FROM source.identity_key
     OR shared.code IS DISTINCT FROM source.code
     OR shared.name IS DISTINCT FROM source.name
     OR shared.direction IS DISTINCT FROM source.direction
     OR shared.signal_type IS DISTINCT FROM source.signal_type
     OR shared.target_price IS DISTINCT FROM source.target_price
     OR shared.current_price IS DISTINCT FROM source.current_price
     OR shared.trigger_price IS DISTINCT FROM source.trigger_price
     OR shared.action_price IS DISTINCT FROM source.action_price
     OR shared.expected_return_pct IS DISTINCT FROM
          source.expected_return_pct
     OR shared.board_identity_key IS DISTINCT FROM
          source.board_identity_key
     OR shared.board_code IS DISTINCT FROM source.board_code
     OR shared.board_name IS DISTINCT FROM source.board_name
     OR shared.action_state IS DISTINCT FROM source.action_state
     OR shared.action_mark IS DISTINCT FROM source.action_mark
     OR shared.condition_key IS DISTINCT FROM source.condition_key
     OR shared.original_condition_key IS DISTINCT FROM
          source.original_condition_key
     OR shared.reason_fields_json IS DISTINCT FROM
          source.reason_fields_json
     OR shared.source_payload_hash IS DISTINCT FROM
          source.expected_payload_hash
     OR shared.shared_status <> 'active';
  IF non_rebuildable_shared_count <> 0 THEN
    RAISE EXCEPTION
      '055 rollback blocked: non-rebuildable shared projection rows=%',
      non_rebuildable_shared_count;
  END IF;

  SELECT count(*) INTO history_count
  FROM public.n6_virtual_trade_proposal
  WHERE principal_type = 'ai_user'
     OR actor_ai_user_id IS NOT NULL
     OR source_ai_decision_id IS NOT NULL
     OR source_type = 'ai_risk';
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI proposal history=%', history_count;
  END IF;

  SELECT count(*) INTO history_count
  FROM public.n6_virtual_position_lot
  WHERE principal_type = 'ai_user';
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI position-lot history=%', history_count;
  END IF;

  SELECT
      (SELECT count(*) FROM public.n6_virtual_order
       WHERE principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_virtual_trade
       WHERE principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_virtual_position
       WHERE principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_virtual_position_event
       WHERE principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_virtual_pnl_snapshot
       WHERE principal_type = 'ai_user')
    + (SELECT count(*)
       FROM public.n6_virtual_quote_run run
       JOIN public.n6_principal principal
         ON principal.principal_id = run.principal_id
       WHERE principal.principal_type = 'ai_user')
    INTO history_count;
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI execution/valuation history=%',
      history_count;
  END IF;

  SELECT
      (SELECT count(*) FROM public.n6_principal
       WHERE principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_ai_user)
    + (SELECT count(*)
       FROM public.n6_strategy s
       JOIN public.n6_principal p ON p.principal_id = s.principal_id
       WHERE p.principal_type = 'ai_user')
    + (SELECT count(*)
       FROM public.n6_principal_account pa
       JOIN public.n6_principal p ON p.principal_id = pa.principal_id
       WHERE p.principal_type = 'ai_user')
    + (SELECT count(*) FROM public.n6_virtual_account
       WHERE principal_type = 'ai_user')
    INTO history_count;
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: 056 AI identity/account state=%',
      history_count;
  END IF;

  SELECT count(*) INTO history_count
  FROM public.n6_virtual_cash_ledger ledger
  JOIN public.n6_virtual_account account
    ON account.virtual_account_id = ledger.virtual_account_id
  WHERE account.principal_type = 'ai_user';
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI cash-ledger history=%', history_count;
  END IF;

  SELECT count(*) INTO history_count
  FROM public.n6_virtual_cash_snapshot snapshot
  JOIN public.n6_virtual_account account
    ON account.virtual_account_id = snapshot.virtual_account_id
  WHERE account.principal_type = 'ai_user';
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI cash-snapshot history=%', history_count;
  END IF;

  SELECT count(*) INTO history_count
  FROM public.n6_virtual_quote_run_identity run_identity
  JOIN public.n6_virtual_quote_run run
    ON run.quote_run_id = run_identity.quote_run_id
  JOIN public.n6_principal principal
    ON principal.principal_id = run.principal_id
  WHERE principal.principal_type = 'ai_user'
    AND run_identity.virtual_quote_snapshot_id IS NOT NULL;
  IF history_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: AI quote-snapshot history=%', history_count;
  END IF;

  SELECT count(*) INTO null_human_actor_count
  FROM public.n6_virtual_trade_proposal
  WHERE principal_type IN ('admin', 'human_user')
    AND user_id IS NULL;
  IF null_human_actor_count <> 0 THEN
    RAISE EXCEPTION '055 rollback blocked: human proposal user_id null rows=%',
      null_human_actor_count;
  END IF;
END
$rollback_preflight$;

REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_context_load(text,date,integer)
  FROM n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_shadow_decision_record(jsonb)
  FROM n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_proposal_create_confirm(jsonb)
  FROM n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_daily_summary_record(jsonb)
  FROM n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_strategy_evaluation_record(jsonb)
  FROM n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_ai_executor_risk_recheck(bigint,text)
  FROM n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_ai_public_snapshot(text,integer,integer,integer)
  FROM n6_btrack_web, n6_ai_agent;
REVOKE EXECUTE ON FUNCTION public.n6_btrack_ai_public_decision_detail(text,bigint)
  FROM n6_btrack_web;
REVOKE USAGE ON SCHEMA public FROM n6_ai_agent;

DROP FUNCTION public.n6_btrack_ai_public_decision_detail(text,bigint);
DROP FUNCTION public.n6_btrack_ai_public_snapshot(text,integer,integer,integer);
DROP FUNCTION public.n6_ai_executor_risk_recheck(bigint,text);
DROP FUNCTION public.n6_ai_agent_strategy_evaluation_record(jsonb);
DROP FUNCTION public.n6_ai_agent_daily_summary_record(jsonb);
DROP FUNCTION public.n6_ai_agent_proposal_create_confirm(jsonb);
DROP FUNCTION public.n6_ai_agent_shadow_decision_record(jsonb);
DROP FUNCTION public.n6_ai_agent_context_load(text,date,integer);
DROP TRIGGER trg_055_n6_ai_shared_signal_projection_capture
  ON public.user_signal_projection;
DROP FUNCTION public.n6_ai_shared_signal_projection_capture();

DROP INDEX public.idx_055_n6_virtual_trade_proposal_ai_decision;

ALTER TABLE public.n6_virtual_trade_proposal
  DROP CONSTRAINT n6_virtual_trade_proposal_055_actor_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_position_source_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_signal_source_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_source_type_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_055_principal_type_ck,
  DROP COLUMN source_ai_decision_id,
  DROP COLUMN actor_ai_user_id,
  ALTER COLUMN user_id SET NOT NULL,
  ADD CONSTRAINT n6_virtual_trade_proposal_principal_type_check
    CHECK (principal_type IN ('admin', 'human_user')),
  ADD CONSTRAINT n6_virtual_trade_proposal_source_type_check
    CHECK (source_type IN ('signal', 'manual_position', 'stop_loss')),
  ADD CONSTRAINT n6_virtual_trade_proposal_check
    CHECK ((source_type = 'signal') = (source_signal_projection_id IS NOT NULL)),
  ADD CONSTRAINT n6_virtual_trade_proposal_check1
    CHECK (
      (source_type IN ('manual_position', 'stop_loss'))
      = (source_virtual_position_id IS NOT NULL)
    );

ALTER TABLE public.n6_virtual_position_lot
  DROP CONSTRAINT n6_virtual_position_lot_055_principal_type_ck,
  ADD CONSTRAINT n6_virtual_position_lot_principal_type_check
    CHECK (principal_type IN ('admin', 'human_user'));

DROP TABLE public.n6_ai_strategy_evaluation;
DROP TABLE public.n6_ai_daily_summary;
DROP TABLE public.n6_ai_decision;
DROP TABLE public.n6_ai_decision_run;
DROP TABLE public.n6_ai_context_snapshot;
DROP TABLE public.n6_ai_shared_signal_projection;

COMMIT;
