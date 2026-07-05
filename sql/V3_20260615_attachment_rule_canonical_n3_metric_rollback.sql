-- V3 20260615 full-universe N3 action-confirmation metric rollback.
-- Scope: projection_run_id=v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1
BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';
  v_count BIGINT;
BEGIN
  RAISE EXCEPTION 'hard-fail: reviewed manual rollback only for %', v_run_id;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: outbox refs=%', v_count;
  END IF;
END $$;

DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';
DELETE FROM common_market_data_quality_item WHERE run_id = 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';
DELETE FROM common_market_data_run WHERE run_id = 'v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1';

COMMIT;
