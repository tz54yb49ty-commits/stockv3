-- N3 projection enrichment v4 row-level materialization business rollback.
-- Scope: target_run_id=projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
-- Boundary: hard-fail before any DELETE if event infra, downstream refs, or run flags exist.
-- Delete scope is limited to scoped projection enrichment v4 rows, scoped quality rows, and the scoped run row.

\set ON_ERROR_STOP on
\set projection_run_id 'projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

BEGIN;

DO $$
DECLARE
  v_run_id text := current_setting('app.projection_run_id');
  v_count bigint := 0;
  v_event_refs bigint := 0;
  v_flagged_run_refs bigint := 0;
  v_table text;
  v_column text;
  v_predicates text[];
  v_ref_columns text[] := ARRAY[
    'run_id',
    'source_run_id',
    'source_market_data_run_id',
    'source_projection_run_id',
    'projection_run_id',
    'source_projection_metric_run_id',
    'source_snapshot_run_id',
    'source_event_run_id',
    'trigger_run_id',
    'action_run_id',
    'user_projection_run_id'
  ];
  v_json_columns text[] := ARRAY[
    'payload_json',
    'raw_json',
    'details',
    'trace_json',
    'checkpoint_payload'
  ];
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id
     OR payload_json::text LIKE '%' || v_run_id || '%';
  v_event_refs := v_event_refs + v_count;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR payload_json::text LIKE '%' || v_run_id || '%'
     OR raw_json::text LIKE '%' || v_run_id || '%';
  v_event_refs := v_event_refs + v_count;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%'
     OR last_event_id LIKE '%' || v_run_id || '%';
  v_event_refs := v_event_refs + v_count;

  IF v_event_refs <> 0 THEN
    RAISE EXCEPTION 'N3 projection enrichment v4 rollback blocked for %: event infra refs=%',
      v_run_id, v_event_refs;
  END IF;

  SELECT count(*) INTO v_flagged_run_refs
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (downstream_layers_touched = true OR worker_started = true);

  IF v_flagged_run_refs <> 0 THEN
    RAISE EXCEPTION 'N3 projection enrichment v4 rollback blocked for %: downstream_layers_touched/worker_started flags exist',
      v_run_id;
  END IF;

  -- Downstream guard covers N4 common_trigger_%, N5 common_action_%, and N6 user_projection/user_signal/notification refs.
  FOR v_table IN
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_type = 'BASE TABLE'
      AND (
        table_name LIKE 'common_trigger_%'
        OR table_name LIKE '%_trigger_%'
        OR table_name LIKE 'common_action_%'
        OR table_name LIKE '%_action_%'
        OR table_name LIKE 'user_projection%'
        OR table_name LIKE 'user_signal%'
        OR table_name LIKE '%notification%'
      )
    ORDER BY table_name
  LOOP
    v_predicates := ARRAY[]::text[];

    FOREACH v_column IN ARRAY v_ref_columns LOOP
      IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = v_table
          AND column_name = v_column
      ) THEN
        v_predicates := v_predicates || format('%I = %L', v_column, v_run_id);
      END IF;
    END LOOP;

    FOREACH v_column IN ARRAY v_json_columns LOOP
      IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = v_table
          AND column_name = v_column
      ) THEN
        v_predicates := v_predicates || format('%I::text LIKE %L', v_column, '%' || v_run_id || '%');
      END IF;
    END LOOP;

    IF array_length(v_predicates, 1) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I WHERE %s', v_table, array_to_string(v_predicates, ' OR '))
      INTO v_count;

      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N3 projection enrichment v4 rollback blocked for %: downstream table % has % refs',
          v_run_id, v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM stock_projection_enrichment_v4_metric WHERE projection_run_id = :'projection_run_id';
DELETE FROM index_projection_enrichment_v4_metric WHERE projection_run_id = :'projection_run_id';
DELETE FROM board_projection_enrichment_v4_metric WHERE projection_run_id = :'projection_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'projection_run_id'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'projection_enrichment_v4_row_level';

DELETE FROM common_market_data_run
WHERE run_id = :'projection_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
