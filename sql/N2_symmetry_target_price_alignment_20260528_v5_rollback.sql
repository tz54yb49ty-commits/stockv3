-- N2 symmetry target price alignment v5 rollback.
-- Do not execute without explicit user confirmation.
--
-- Scope:
--   Delete only condition_layer_20260528_source_20260528_v5 rows.
--   Restore condition_layer_20260528_source_20260528_v4 to passed_active.
--   Do not delete or modify v4/v3/v2/v1 business rows.
--
-- Boundary:
--   Does not touch N1 source_version.
--   Does not touch common_event_outbox / common_event_inbox / checkpoints.
--   Does not touch N3/N4/N5/N6 business rows.
--   Blocks if v5 already has downstream N3/N4/N5/N6 references.

\set ON_ERROR_STOP on
\set run_id 'condition_layer_20260528_source_20260528_v5'
\set previous_active_run_id 'condition_layer_20260528_source_20260528_v4'

BEGIN;

CREATE TEMP TABLE _n2_symmetry_v5_rollback_params ON COMMIT DROP AS
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
  FROM _n2_symmetry_v5_rollback_params;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: expected exactly one common_condition_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_previous_active_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: previous active run % is missing or duplicated, found %', v_previous_active_run_id, v_count;
  END IF;

  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_event_outbox WHERE source_run_id = $1'
      INTO v_count
      USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: common_event_outbox refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_event_inbox WHERE source_run_id = $1'
      INTO v_count
      USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: common_event_inbox refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'common_event_consumer_checkpoint'
         AND column_name = 'checkpoint_payload'
     ) THEN
    EXECUTE 'SELECT count(*) FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: checkpoint refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_market_data_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = $1 OR run_id LIKE $2'
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N3 common_market_data_run refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = $1 OR run_id LIKE $2'
      INTO v_count
      USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N4 common_trigger_run refs for % = %', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    IF EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'common_action_run'
         AND column_name = 'source_condition_run_id'
    ) THEN
      EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_condition_run_id = $1 OR run_id LIKE $2'
        INTO v_count
        USING v_run_id, '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N5 common_action_run refs for % = %', v_run_id, v_count;
      END IF;
    END IF;

    IF EXISTS (
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
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N5 common_action_run raw refs for % = %', v_run_id, v_count;
      END IF;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    IF EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_projection_run'
         AND column_name = 'source_display_condition_run_id'
    ) THEN
      EXECUTE 'SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = $1 OR user_projection_run_id LIKE $2'
        INTO v_count
        USING v_run_id, '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N6 user_projection_run refs for % = %', v_run_id, v_count;
      END IF;
    END IF;

    IF EXISTS (
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
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N6 user_projection_run raw refs for % = %', v_run_id, v_count;
      END IF;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    IF EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_signal_projection'
         AND column_name = 'source_condition_display_run_id'
    ) THEN
      EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE source_condition_display_run_id = $1'
        INTO v_count
        USING v_run_id;
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N6 user_signal_projection run refs for % = %', v_run_id, v_count;
      END IF;
    END IF;

    IF EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'user_signal_projection'
         AND column_name = 'source_condition_display_basis_id'
    ) THEN
      EXECUTE $sql$
        SELECT count(*)
        FROM user_signal_projection
        WHERE source_condition_display_basis_id IN (
          SELECT stock_condition_display_basis_id FROM stock_condition_display_basis WHERE run_id = $1
          UNION ALL
          SELECT index_condition_display_basis_id FROM index_condition_display_basis WHERE run_id = $1
          UNION ALL
          SELECT board_condition_display_basis_id FROM board_condition_display_basis WHERE run_id = $1
        )
      $sql$
        INTO v_count
        USING v_run_id;
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N2 symmetry v5 rollback BLOCKED: N6 user_signal_projection display-basis refs for % = %', v_run_id, v_count;
      END IF;
    END IF;
  END IF;
END
$$;

DELETE FROM stock_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM index_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM board_condition_display_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

DELETE FROM stock_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM board_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM index_minute_target_scope WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

DELETE FROM board_condition_pool WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM index_condition_pool WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM stock_condition_pool WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

DELETE FROM board_condition_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM index_condition_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM stock_condition_basis WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

DELETE FROM board_monitor_target WHERE source_version = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM index_monitor_target WHERE source_version = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM stock_monitor_target WHERE source_version = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

DELETE FROM common_condition_quality_item WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);
DELETE FROM common_condition_run WHERE run_id = (SELECT run_id FROM _n2_symmetry_v5_rollback_params);

UPDATE common_condition_run
SET status = 'passed_active',
    updated_at = now()
WHERE run_id = (SELECT previous_active_run_id FROM _n2_symmetry_v5_rollback_params)
  AND status IN ('passed', 'passed_active', 'superseded');

DO $$
DECLARE
  v_run_id text;
  v_previous_active_run_id text;
  v_count bigint;
BEGIN
  SELECT run_id, previous_active_run_id
    INTO v_run_id, v_previous_active_run_id
  FROM _n2_symmetry_v5_rollback_params;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N2 symmetry v5 rollback FAILED: common_condition_run still exists for %, count=%', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE run_id = v_previous_active_run_id
    AND status = 'passed_active';
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 symmetry v5 rollback FAILED: previous active % was not restored to passed_active, count=%', v_previous_active_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_condition_run
  WHERE source_trade_date = '20260528'
    AND for_trade_date = '20260529'
    AND status = 'passed_active';
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N2 symmetry v5 rollback FAILED: passed_active count for 20260528->20260529 = %', v_count;
  END IF;
END
$$;

COMMIT;
