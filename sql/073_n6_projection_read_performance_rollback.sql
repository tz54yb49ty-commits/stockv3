-- Exact schema rollback for 073. Run only after the previous immutable web and
-- writer release is active and the N6 projection writer is confirmed stopped.
-- Business projection rows are preserved; only the additive read model is removed.

\set ON_ERROR_STOP on

DROP INDEX CONCURRENTLY IF EXISTS public.idx_073_n6_projection_user_date_order;
DROP INDEX CONCURRENTLY IF EXISTS public.idx_073_n6_projection_shared_date_order;

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DROP TRIGGER IF EXISTS trg_073_n6_projection_read_model_v1_fill
ON public.user_signal_projection;

DROP FUNCTION IF EXISTS public.n6_projection_read_model_v1_fill();

ALTER TABLE public.user_signal_projection
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_list_payload_object,
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_list_payload_version,
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_for_trade_date_present;

ALTER TABLE public.user_signal_projection
  DROP COLUMN IF EXISTS list_payload_json,
  DROP COLUMN IF EXISTS list_payload_version,
  DROP COLUMN IF EXISTS for_trade_date;

COMMIT;
