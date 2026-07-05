-- N2 context enrichment row-level materialization rollback.
-- Scope: only rows for condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1.
-- Hard-fails before DELETE if event infra or downstream N3/N4/N5/N6 refs exist.
DO $$
DECLARE
  v_run_id text := 'condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1';
  v_ref_count bigint := 0;
BEGIN
  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE last_event_id LIKE '%' || v_run_id || '%' OR checkpoint_payload::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_state WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_match WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_action_event WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = v_run_id OR quality_summary_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_condition_display_run_id = v_run_id OR source_payload_json::text LIKE '%' || v_run_id || '%' OR display_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_card WHERE card_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_notification_queue WHERE notification_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
  INTO v_ref_count;

  IF v_ref_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has event/downstream refs: %', v_run_id, v_ref_count;
  END IF;

  IF EXISTS (SELECT 1 FROM common_condition_context_enrichment_run WHERE run_id = v_run_id AND COALESCE((raw_json->>'downstream_layers_touched')::boolean, false)) THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has downstream_layers_touched=true', v_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_condition_context_enrichment_run WHERE run_id = v_run_id AND COALESCE((raw_json->>'worker_started')::boolean, false)) THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has worker_started=true', v_run_id;
  END IF;

  DELETE FROM stock_condition_context_enrichment WHERE materialization_run_id = v_run_id;
  DELETE FROM index_condition_context_enrichment WHERE materialization_run_id = v_run_id;
  DELETE FROM board_condition_context_enrichment WHERE materialization_run_id = v_run_id;
  DELETE FROM common_condition_context_enrichment_run WHERE run_id = v_run_id;
END $$;
