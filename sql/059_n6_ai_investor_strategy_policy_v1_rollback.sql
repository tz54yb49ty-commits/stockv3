-- N6 AI investor strategy policy V1 fail-closed rollback.
-- Rollback is allowed only before any 059 strategy/audit history exists.
-- It never deletes proposals, orders, trades, positions, cash, or AI history.

BEGIN;

DO $rollback_gate$
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '059_rollback_identity_mismatch';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_ai_strategy_shadow_evaluate(date,text,text)'
     ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_position_strategy_episode'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_strategy_action'
        ) IS NULL
     OR pg_catalog.to_regclass(
          'public.n6_ai_candidate_rank_audit'
        ) IS NULL THEN
    RAISE EXCEPTION '059_not_applied';
  END IF;
END
$rollback_gate$;

LOCK TABLE public.n6_ai_position_strategy_episode
  IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_strategy_action
  IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.n6_ai_candidate_rank_audit
  IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_trade_proposal
  IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.n6_virtual_order
  IN SHARE MODE;
LOCK TABLE public.n6_virtual_trade
  IN SHARE MODE;

DO $dependency_gate$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.n6_ai_strategy_action action
    WHERE action.action_status IN (
      'claimed', 'proposal_created', 'executed'
    )
  ) THEN
    RAISE EXCEPTION '059_rollback_blocked_by_processing_action';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_ai_position_strategy_episode episode
    WHERE episode.pending_clear = true
       OR episode.pending_clear_started_trade_date IS NOT NULL
       OR episode.pending_clear_completed_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION '059_rollback_blocked_by_pending_clear';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_trade_proposal proposal
    WHERE proposal.strategy_action_id IS NOT NULL
       OR proposal.source_type IN (
            'ai_target_reduce', 'ai_period_clear', 'ai_pending_clear'
          )
  ) THEN
    RAISE EXCEPTION '059_rollback_blocked_by_strategy_proposal';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_order strategy_order
    JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.proposal_id = strategy_order.source_proposal_id
    WHERE proposal.strategy_action_id IS NOT NULL
  ) OR EXISTS (
    SELECT 1
    FROM public.n6_virtual_trade strategy_trade
    JOIN public.n6_virtual_order strategy_order
      ON strategy_order.virtual_order_id =
           strategy_trade.virtual_order_id
    JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.proposal_id = strategy_order.source_proposal_id
    WHERE proposal.strategy_action_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION
      '059_rollback_blocked_by_strategy_order_or_trade';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.n6_ai_candidate_rank_audit
  ) OR EXISTS (
    SELECT 1 FROM public.n6_ai_strategy_action
  ) OR EXISTS (
    SELECT 1 FROM public.n6_ai_position_strategy_episode
  ) THEN
    RAISE EXCEPTION '059_rollback_blocked_by_strategy_history';
  END IF;
END
$dependency_gate$;

REVOKE EXECUTE ON FUNCTION
public.n6_ai_executor_strategy_action_apply_v1(
  bigint,text
) FROM n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION
public.n6_ai_strategy_proposal_create_confirm_v1(
  jsonb
) FROM n6_virtual_executor;
REVOKE EXECUTE ON FUNCTION public.n6_ai_strategy_shadow_evaluate(
  date,text,text
) FROM n6_ai_agent;

DROP FUNCTION public.n6_ai_executor_strategy_action_apply_v1(
  bigint,text
);
DROP FUNCTION public.n6_ai_strategy_proposal_create_confirm_v1(
  jsonb
);
DROP FUNCTION public.n6_ai_strategy_shadow_evaluate(
  date,text,text
);
DROP FUNCTION public.n6_ai_strategy_context_load_v1(
  text,date,integer,text
);

DROP INDEX public.idx_059_n6_virtual_trade_proposal_strategy_action;

ALTER TABLE public.n6_virtual_trade_proposal
  DROP CONSTRAINT n6_virtual_trade_proposal_059_actor_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_059_source_type_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_059_signal_source_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_059_position_source_ck,
  DROP CONSTRAINT n6_virtual_trade_proposal_059_strategy_action_ck,
  DROP COLUMN strategy_action_id,
  ADD CONSTRAINT n6_virtual_trade_proposal_055_actor_ck
    CHECK (
      (
        principal_type IN ('admin', 'human_user')
        AND user_id IS NOT NULL
        AND actor_ai_user_id IS NULL
        AND source_ai_decision_id IS NULL
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
          )
          OR
          (
            source_type = 'stop_loss'
            AND source_ai_decision_id IS NULL
          )
        )
      )
    ),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_source_type_ck
    CHECK (
      source_type IN (
        'signal', 'manual_position', 'stop_loss', 'ai_risk'
      )
    ),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_signal_source_ck
    CHECK (
      (
        source_type = 'signal'
        AND source_signal_projection_id IS NOT NULL
      )
      OR (
        source_type <> 'signal'
        AND source_signal_projection_id IS NULL
      )
    ),
  ADD CONSTRAINT n6_virtual_trade_proposal_055_position_source_ck
    CHECK (
      (
        source_type IN ('manual_position', 'stop_loss', 'ai_risk')
        AND source_virtual_position_id IS NOT NULL
      )
      OR source_type = 'signal'
    );

DROP TRIGGER trg_059_n6_ai_strategy_episode_locked_fields_immutable
  ON public.n6_ai_position_strategy_episode;
DROP FUNCTION
public.n6_ai_strategy_episode_locked_fields_immutable_v1();

DROP TABLE public.n6_ai_candidate_rank_audit;
DROP TABLE public.n6_ai_strategy_action;
DROP TABLE public.n6_ai_position_strategy_episode;

DROP TRIGGER trg_059_n6_ai_shared_strategy_fields_capture
  ON public.user_signal_projection;
DROP FUNCTION public.n6_ai_shared_strategy_fields_capture_v1();

ALTER TABLE public.n6_ai_shared_signal_projection
  DROP CONSTRAINT n6_ai_shared_signal_projection_059_context_version_ck,
  DROP CONSTRAINT n6_ai_shared_signal_projection_059_target_price_ck,
  DROP CONSTRAINT n6_ai_shared_signal_projection_059_target_quality_ck,
  DROP CONSTRAINT n6_ai_shared_signal_projection_059_sell_period_ck,
  DROP COLUMN financial_score_raw,
  DROP COLUMN up_sell_reference_period,
  DROP COLUMN target_quality_status,
  DROP COLUMN reference_target_price,
  DROP COLUMN strategy_context_version;

COMMIT;
