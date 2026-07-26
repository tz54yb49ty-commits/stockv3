-- N6 B-track projection read-performance migration.
--
-- Default invocation applies only the additive, online-compatible phase:
--   psql -v ON_ERROR_STOP=1 -f sql/073_n6_projection_read_performance.sql
--
-- After the bounded backfill has completed, create indexes and finalize:
--   psql -v ON_ERROR_STOP=1 \
--     -v n6_projection_read_create_indexes=1 \
--     -v n6_projection_read_finalize=1 \
--     -f sql/073_n6_projection_read_performance.sql
--
-- The writer must be stopped for the additive/backfill/finalize sequence. The
-- CREATE INDEX CONCURRENTLY statements intentionally run outside a transaction.

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $preflight$
BEGIN
  IF pg_catalog.to_regclass('public.user_signal_projection') IS NULL
     OR pg_catalog.to_regclass('public.n6_ai_shared_signal_projection') IS NULL THEN
    RAISE EXCEPTION '073 prerequisite projection relations are missing';
  END IF;
END;
$preflight$;

ALTER TABLE public.user_signal_projection
  ADD COLUMN IF NOT EXISTS for_trade_date DATE,
  ADD COLUMN IF NOT EXISTS list_payload_version TEXT,
  ADD COLUMN IF NOT EXISTS list_payload_json JSONB;

CREATE OR REPLACE FUNCTION public.n6_projection_read_model_v1_fill()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, public
AS $function$
DECLARE
  trade_date_text TEXT;
  payload JSONB;
  payload_trace JSONB;
  projection_trace JSONB;
  source_market_trace JSONB;
  payload_source_n4 JSONB;
  payload_trace_source_n4 JSONB;
  projection_trace_source_n4 JSONB;
  display_payload JSONB;
  primary_trigger_period TEXT;
  triggered_periods JSONB;
  baseline_source TEXT;
  compatibility_payload JSONB;
BEGIN
  IF TG_OP = 'INSERT'
     AND NEW.for_trade_date IS NOT NULL
     AND NEW.list_payload_version = 'n6_projection_list_v1'
     AND pg_catalog.jsonb_typeof(NEW.list_payload_json) = 'object' THEN
    RETURN NEW;
  END IF;

  payload := CASE
    WHEN pg_catalog.jsonb_typeof(NEW.source_payload_json->'payload_json') = 'object'
      THEN NEW.source_payload_json->'payload_json'
    ELSE '{}'::JSONB
  END;
  payload_trace := CASE
    WHEN pg_catalog.jsonb_typeof(payload->'trace_json') = 'object' THEN payload->'trace_json'
    ELSE '{}'::JSONB
  END;
  projection_trace := CASE
    WHEN pg_catalog.jsonb_typeof(NEW.trace_json) = 'object' THEN NEW.trace_json
    ELSE '{}'::JSONB
  END;
  source_market_trace := CASE
    WHEN pg_catalog.jsonb_typeof(payload->'source_market_trace') = 'object'
      THEN payload->'source_market_trace'
    ELSE '{}'::JSONB
  END;
  payload_source_n4 := CASE
    WHEN pg_catalog.jsonb_typeof(payload->'source_n4_payload') = 'object'
      THEN payload->'source_n4_payload'
    ELSE '{}'::JSONB
  END;
  payload_trace_source_n4 := CASE
    WHEN pg_catalog.jsonb_typeof(payload_trace->'source_n4_payload') = 'object'
      THEN payload_trace->'source_n4_payload'
    ELSE '{}'::JSONB
  END;
  projection_trace_source_n4 := CASE
    WHEN pg_catalog.jsonb_typeof(projection_trace->'source_n4_payload') = 'object'
      THEN projection_trace->'source_n4_payload'
    ELSE '{}'::JSONB
  END;
  display_payload := CASE
    WHEN pg_catalog.jsonb_typeof(NEW.display_payload_json) = 'object'
      THEN NEW.display_payload_json
    ELSE '{}'::JSONB
  END;

  IF NEW.for_trade_date IS NULL THEN
    trade_date_text := pg_catalog.replace(
      COALESCE(
        NEW.source_payload_json->>'trade_date',
        display_payload->>'for_trade_date',
        display_payload->>'trade_date',
        projection_trace->>'trade_date',
        payload_trace->>'trade_date'
      ),
      '-',
      ''
    );
    IF trade_date_text IS NULL OR trade_date_text !~ '^[0-9]{8}$' THEN
      RAISE EXCEPTION 'n6_projection_for_trade_date_missing_or_invalid';
    END IF;
    NEW.for_trade_date := pg_catalog.to_date(trade_date_text, 'YYYYMMDD');
    IF pg_catalog.to_char(NEW.for_trade_date, 'YYYYMMDD') <> trade_date_text THEN
      RAISE EXCEPTION 'n6_projection_for_trade_date_invalid_calendar_date';
    END IF;
  END IF;

  primary_trigger_period := COALESCE(
    NULLIF(payload->>'primary_trigger_period', ''),
    NULLIF(payload->>'trigger_period', ''),
    NULLIF(payload_source_n4->>'primary_trigger_period', ''),
    NULLIF(payload_source_n4->>'trigger_period', ''),
    NULLIF(payload_trace_source_n4->>'primary_trigger_period', ''),
    NULLIF(payload_trace_source_n4->>'trigger_period', ''),
    NULLIF(projection_trace_source_n4->>'primary_trigger_period', ''),
    NULLIF(projection_trace_source_n4->>'trigger_period', ''),
    NULLIF(display_payload->>'primary_trigger_period', '')
  );
  triggered_periods := COALESCE(
    payload->'all_trigger_periods',
    payload->'triggered_periods',
    payload_source_n4->'all_trigger_periods',
    payload_source_n4->'triggered_periods',
    payload_trace_source_n4->'all_trigger_periods',
    payload_trace_source_n4->'triggered_periods',
    projection_trace_source_n4->'all_trigger_periods',
    projection_trace_source_n4->'triggered_periods',
    payload_trace->'all_trigger_periods',
    payload_trace->'triggered_periods',
    projection_trace->'all_trigger_periods',
    projection_trace->'triggered_periods',
    CASE
      WHEN primary_trigger_period IS NOT NULL
        THEN pg_catalog.jsonb_build_array(primary_trigger_period)
      ELSE NULL
    END
  );
  IF primary_trigger_period IS NOT NULL THEN
    baseline_source := COALESCE(
      payload #>> ARRAY['period_trigger_baseline_trace', 'traced_periods', primary_trigger_period, 'baseline_source'],
      payload_trace #>> ARRAY['period_trigger_baseline_trace', 'traced_periods', primary_trigger_period, 'baseline_source'],
      source_market_trace #>> ARRAY['period_trigger_baseline_trace', 'traced_periods', primary_trigger_period, 'baseline_source'],
      projection_trace #>> ARRAY['period_trigger_baseline_trace', 'traced_periods', primary_trigger_period, 'baseline_source']
    );
  END IF;
  baseline_source := COALESCE(
    baseline_source,
    payload->>'baseline_source',
    payload_trace->>'baseline_source',
    projection_trace->>'baseline_source',
    display_payload->>'baseline_source'
  );

  compatibility_payload := pg_catalog.jsonb_strip_nulls(
    pg_catalog.jsonb_build_object(
      'event_time', COALESCE(
        NEW.source_payload_json->>'event_time', payload->>'event_time',
        projection_trace->>'event_time', payload_trace->>'event_time', display_payload->>'event_time'
      ),
      'blocked_reason', COALESCE(
        payload->>'blocked_reason', projection_trace->>'blocked_reason',
        payload_trace->>'blocked_reason', display_payload->>'blocked_reason'
      ),
      'trigger_kind', COALESCE(
        payload->>'trigger_kind', payload_source_n4->>'trigger_kind',
        payload_trace_source_n4->>'trigger_kind', projection_trace_source_n4->>'trigger_kind',
        display_payload->>'trigger_kind', projection_trace->>'trigger_kind',
        NEW.source_payload_json->>'trigger_kind'
      ),
      'condition_key', COALESCE(NEW.condition_key, payload->>'condition_key'),
      'original_condition_key', COALESCE(
        NEW.original_condition_key, payload->>'original_condition_key'
      ),
      'primary_trigger_period', primary_trigger_period,
      'trigger_time', COALESCE(
        projection_trace->>'trigger_time', payload_trace->>'trigger_time',
        NEW.source_payload_json->>'event_time', payload->>'event_time'
      ),
      'source_n4_run_id', COALESCE(
        payload->>'source_n4_run_id', projection_trace->>'source_n4_run_id',
        payload_trace->>'source_n4_run_id', NEW.source_payload_json->>'source_n4_run_id',
        projection_trace->>'source_trigger_run_id', payload_trace->>'source_trigger_run_id'
      ),
      'n4_trigger_event_id', COALESCE(
        payload->>'source_trigger_event_id',
        projection_trace #>> ARRAY['condition_provenance', 'source_trigger_event_ids', '0'],
        payload_trace #>> ARRAY['condition_provenance', 'source_trigger_event_ids', '0']
      ),
      'source_action_status', COALESCE(
        payload->>'confirmation_status', projection_trace->>'confirmation_status',
        payload_trace->>'confirmation_status', NEW.action_state
      ),
      'trigger_price', COALESCE(
        payload->>'trigger_price', payload_trace->>'trigger_price',
        projection_trace->>'trigger_price', payload_source_n4->>'trigger_price',
        payload_trace_source_n4->>'trigger_price', projection_trace_source_n4->>'trigger_price'
      ),
      'triggered_periods', triggered_periods,
      'all_trigger_periods', COALESCE(
        display_payload->'all_trigger_periods', payload->'all_trigger_periods', triggered_periods
      ),
      'baseline_source', baseline_source,
      'quality_status', COALESCE(
        display_payload->>'quality_status', payload->>'quality_status', 'reviewed'
      ),
      'condition_projection_context', COALESCE(
        display_payload->'condition_projection_context', payload->'condition_projection_context'
      ),
      'condition_projection_context_status', COALESCE(
        display_payload->'condition_projection_context_status', payload->'condition_projection_context_status'
      ),
      'condition_projection_context_trace', COALESCE(
        display_payload->'condition_projection_context_trace', payload->'condition_projection_context_trace'
      ),
      'projection_message_contract_version', COALESCE(
        display_payload->'projection_message_contract_version', payload->'projection_message_contract_version'
      ),
      'projection_message_contract_hash', COALESCE(
        display_payload->'projection_message_contract_hash', payload->'projection_message_contract_hash'
      ),
      'projection_message_not_ready_reasons', COALESCE(
        display_payload->'projection_message_not_ready_reasons', payload->'projection_message_not_ready_reasons'
      ),
      'buy_expected_return_pct', display_payload->'buy_expected_return_pct',
      'up_secondary_expected_return_pct', display_payload->'up_secondary_expected_return_pct',
      'sell_expected_return_pct', display_payload->'sell_expected_return_pct',
      'up_reference_period', display_payload->'up_reference_period',
      'down_reference_period', display_payload->'down_reference_period',
      'score', display_payload->'score',
      'pe_core', display_payload->'pe_core',
      'trigger_pct', COALESCE(
        display_payload->'trigger_pct', payload->'trigger_pct',
        payload_trace->'trigger_pct', projection_trace->'trigger_pct'
      ),
      'trigger_pct_status', COALESCE(
        display_payload->'trigger_pct_status', payload->'trigger_pct_status'
      ),
      'action_price', COALESCE(
        display_payload->'action_price', payload->'action_price',
        payload_trace->'action_price', projection_trace->'action_price'
      ),
      'action_pct', COALESCE(
        display_payload->'action_pct', payload->'action_pct',
        payload_trace->'action_pct', projection_trace->'action_pct'
      ),
      'action_pct_status', COALESCE(
        display_payload->'action_pct_status', payload->'action_pct_status'
      ),
      'projection_message_status', COALESCE(
        display_payload->>'projection_message_status', payload->>'projection_message_status', 'not_ready'
      ),
      'industry_status', COALESCE(
        display_payload->'industry_status', payload->'industry_status'
      ),
      'industry_provenance', COALESCE(
        display_payload->'industry_provenance', payload->'industry_provenance'
      )
    )
  );

  IF NEW.list_payload_json IS NOT NULL
     AND pg_catalog.jsonb_typeof(NEW.list_payload_json) <> 'object' THEN
    RAISE EXCEPTION 'n6_projection_list_payload_json_not_object';
  END IF;
  NEW.list_payload_version := COALESCE(
    NULLIF(NEW.list_payload_version, ''),
    'n6_projection_list_v1'
  );
  NEW.list_payload_json := compatibility_payload || COALESCE(
    NEW.list_payload_json,
    '{}'::JSONB
  );
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_073_n6_projection_read_model_v1_fill
ON public.user_signal_projection;

CREATE TRIGGER trg_073_n6_projection_read_model_v1_fill
BEFORE INSERT OR UPDATE OF
  for_trade_date,
  list_payload_version,
  list_payload_json,
  source_payload_json,
  display_payload_json,
  trace_json,
  condition_key,
  original_condition_key,
  action_state
ON public.user_signal_projection
FOR EACH ROW
EXECUTE FUNCTION public.n6_projection_read_model_v1_fill();

ALTER TABLE public.user_signal_projection
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_for_trade_date_present,
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_list_payload_version,
  DROP CONSTRAINT IF EXISTS chk_073_n6_projection_list_payload_object;

ALTER TABLE public.user_signal_projection
  ADD CONSTRAINT chk_073_n6_projection_for_trade_date_present
    CHECK (for_trade_date IS NOT NULL) NOT VALID,
  ADD CONSTRAINT chk_073_n6_projection_list_payload_version
    CHECK (list_payload_version = 'n6_projection_list_v1') NOT VALID,
  ADD CONSTRAINT chk_073_n6_projection_list_payload_object
    CHECK (
      list_payload_json IS NOT NULL
      AND pg_catalog.jsonb_typeof(list_payload_json) = 'object'
    ) NOT VALID;

COMMIT;

\if :{?n6_projection_read_create_indexes}
  \if :n6_projection_read_create_indexes
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_073_n6_projection_shared_date_order
      ON public.user_signal_projection(
        for_trade_date,
        created_at DESC,
        user_signal_projection_id DESC
      )
      WHERE projection_status IN ('visible', 'blocked');

    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_073_n6_projection_user_date_order
      ON public.user_signal_projection(
        user_id,
        for_trade_date,
        created_at DESC,
        user_signal_projection_id DESC
      )
      WHERE projection_status IN ('visible', 'blocked');
  \endif
\endif

\if :{?n6_projection_read_finalize}
  \if :n6_projection_read_finalize
    BEGIN;
    SET LOCAL lock_timeout = '2s';
    SET LOCAL statement_timeout = '30s';

    ALTER TABLE public.user_signal_projection
      VALIDATE CONSTRAINT chk_073_n6_projection_for_trade_date_present;
    ALTER TABLE public.user_signal_projection
      VALIDATE CONSTRAINT chk_073_n6_projection_list_payload_version;
    ALTER TABLE public.user_signal_projection
      VALIDATE CONSTRAINT chk_073_n6_projection_list_payload_object;

    ALTER TABLE public.user_signal_projection
      ALTER COLUMN for_trade_date SET NOT NULL,
      ALTER COLUMN list_payload_version SET NOT NULL,
      ALTER COLUMN list_payload_json SET NOT NULL;
    COMMIT;

    ANALYZE public.user_signal_projection;
  \endif
\endif
