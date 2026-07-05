-- N2 condition layer 20260526 v2 rollback.
-- Scope:
--   delete only v2 rows by run_id/source_version
--   restore v1.status = passed_active
--   do not delete v1 rows
--   do not touch N1 source_version, N3/N4/N5/N6, outbox/inbox/checkpoint
--
-- Usage:
--   psql "$ASHARE_V3_POSTGRES_DSN" -v ON_ERROR_STOP=1 \
--     -f sql/N2_condition_layer_20260526_v2_rollback.sql

\set ON_ERROR_STOP on
\set run_id 'condition_layer_20260526_source_20260526_v2'
\set previous_active_run_id 'condition_layer_20260526_source_20260526_v1'

BEGIN;

CREATE TEMP TABLE _n2_v2_rollback_params ON COMMIT DROP AS
SELECT
  :'run_id'::text AS run_id,
  :'previous_active_run_id'::text AS previous_active_run_id;

DO $$
DECLARE
  v_run_id text;
  v_previous_active_run_id text;
  v_count bigint;
BEGIN
  SELECT run_id, previous_active_run_id
    INTO v_run_id, v_previous_active_run_id
  FROM _n2_v2_rollback_params;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 v2 rollback BLOCKED: expected exactly one v2 common_condition_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_previous_active_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 v2 rollback BLOCKED: previous active v1 run % is missing or duplicated, found %', v_previous_active_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N2 v2 rollback BLOCKED: common_event_outbox refs for % = %', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N2 v2 rollback BLOCKED: common_event_inbox refs for % = %', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N2 v2 rollback BLOCKED: checkpoint refs for % = %', v_run_id, v_count;
  END IF;

  IF to_regclass('public.common_market_data_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = $1'
      INTO v_count
      USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 v2 rollback BLOCKED: N3 common_market_data_run refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = $1'
      INTO v_count
      USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 v2 rollback BLOCKED: N4 common_trigger_run refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'common_action_run'
         AND column_name = 'raw_json'
     ) THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE raw_json::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 v2 rollback BLOCKED: N5 common_action_run raw refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_projection_run'
         AND column_name = 'raw_json'
     ) THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE raw_json::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 v2 rollback BLOCKED: N6 user_projection_run raw refs for % = %', v_run_id, v_count;
    END IF;
  END IF;
END
$$;

DELETE FROM stock_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM index_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM board_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);

DELETE FROM stock_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM board_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM index_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);

DELETE FROM board_condition_pool WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM index_condition_pool WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM stock_condition_pool WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);

DELETE FROM board_condition_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM index_condition_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM stock_condition_basis WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);

DELETE FROM board_monitor_target WHERE source_version = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM index_monitor_target WHERE source_version = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM stock_monitor_target WHERE source_version = (SELECT run_id FROM _n2_v2_rollback_params);

DELETE FROM common_condition_quality_item WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);
DELETE FROM common_condition_run WHERE run_id = (SELECT run_id FROM _n2_v2_rollback_params);

UPDATE common_condition_run
SET status = 'passed_active',
    updated_at = now()
WHERE run_id = (SELECT previous_active_run_id FROM _n2_v2_rollback_params)
  AND status IN ('passed', 'passed_active', 'superseded');

DO $$
DECLARE
  v_run_id text;
  v_previous_active_run_id text;
  v_count bigint;
BEGIN
  SELECT run_id, previous_active_run_id
    INTO v_run_id, v_previous_active_run_id
  FROM _n2_v2_rollback_params;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N2 v2 rollback FAILED: v2 common_condition_run still exists for %, count=%', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_previous_active_run_id
    AND status = 'passed_active';
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 v2 rollback FAILED: v1 % was not restored to passed_active, count=%', v_previous_active_run_id, v_count;
  END IF;
END
$$;

COMMIT;
