-- N5 multi action window fact grain migration.
--
-- Purpose:
--   Allow one N4 TriggerMatched live window to produce multiple N5 action facts
--   when distinct metric minutes satisfy N5 action confirmation.
--
-- Scope:
--   Only stock/index/board action fact tables.
--
-- Idempotency after this migration remains enforced by:
--   *_action_fact_run_id_action_key_key
--   *_action_fact_run_id_dedup_key_key
--
-- This migration intentionally does not touch common_action_event,
-- common_event_outbox, or common_action_tracking_state.

BEGIN;

-- Keep existing action_key/dedup_key unique constraints as the canonical
-- idempotency grain for future selected_metric_id / executed_metric_time keys.
ALTER TABLE public.stock_action_fact
  DROP CONSTRAINT IF EXISTS stock_action_fact_run_id_source_trigger_event_id_action_typ_key;

ALTER TABLE public.index_action_fact
  DROP CONSTRAINT IF EXISTS index_action_fact_run_id_source_trigger_event_id_action_typ_key;

ALTER TABLE public.board_action_fact
  DROP CONSTRAINT IF EXISTS board_action_fact_run_id_source_trigger_event_id_action_typ_key;

CREATE INDEX IF NOT EXISTS idx_stock_action_fact_source_trigger_action_lookup
  ON public.stock_action_fact (run_id, source_trigger_event_id, action_type);

CREATE INDEX IF NOT EXISTS idx_index_action_fact_source_trigger_action_lookup
  ON public.index_action_fact (run_id, source_trigger_event_id, action_type);

CREATE INDEX IF NOT EXISTS idx_board_action_fact_source_trigger_action_lookup
  ON public.board_action_fact (run_id, source_trigger_event_id, action_type);

COMMENT ON INDEX public.idx_stock_action_fact_source_trigger_action_lookup
  IS 'Non-unique lookup index replacing old one-action-per-trigger unique grain for N5 multi action window.';

COMMENT ON INDEX public.idx_index_action_fact_source_trigger_action_lookup
  IS 'Non-unique lookup index replacing old one-action-per-trigger unique grain for N5 multi action window.';

COMMENT ON INDEX public.idx_board_action_fact_source_trigger_action_lookup
  IS 'Non-unique lookup index replacing old one-action-per-trigger unique grain for N5 multi action window.';

COMMENT ON CONSTRAINT stock_action_fact_run_id_action_key_key ON public.stock_action_fact
  IS 'N5 action fact idempotency key; retained for multi-action window selected metric grain.';

COMMENT ON CONSTRAINT stock_action_fact_run_id_dedup_key_key ON public.stock_action_fact
  IS 'N5 action fact dedup key; retained for multi-action window selected metric grain.';

COMMENT ON CONSTRAINT index_action_fact_run_id_action_key_key ON public.index_action_fact
  IS 'N5 action fact idempotency key; retained for multi-action window selected metric grain.';

COMMENT ON CONSTRAINT index_action_fact_run_id_dedup_key_key ON public.index_action_fact
  IS 'N5 action fact dedup key; retained for multi-action window selected metric grain.';

COMMENT ON CONSTRAINT board_action_fact_run_id_action_key_key ON public.board_action_fact
  IS 'N5 action fact idempotency key; retained for multi-action window selected metric grain.';

COMMENT ON CONSTRAINT board_action_fact_run_id_dedup_key_key ON public.board_action_fact
  IS 'N5 action fact dedup key; retained for multi-action window selected metric grain.';

COMMIT;
