-- V3 20260615 action-confirmation previous-day scope subscription rollback.
-- Scope: only control rows for market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1. Hard-fails before DELETE if facts/events/downstream refs exist.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE v_count BIGINT; v_run_id TEXT := 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
BEGIN
  SELECT count(*) INTO v_count FROM stock_minute_bar_1m WHERE run_id = v_run_id;
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: stock minute facts exist for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: outbox refs exist for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: inbox refs exist for % rows=%', v_run_id, v_count; END IF;
  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'rollback blocked: checkpoint refs exist for % rows=%', v_run_id, v_count; END IF;
END $$;
DELETE FROM common_market_data_pull_plan WHERE run_id = 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_subscription WHERE run_id = 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
DELETE FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260615_action_confirmation_previous_day_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1';
COMMIT;
