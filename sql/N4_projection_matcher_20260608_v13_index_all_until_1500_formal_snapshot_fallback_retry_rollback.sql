-- N4 projection matcher execute rollback.
-- Scope: N4 execute run only. Run only after confirming N4 outbox rows for
-- this execute_run_id have not been delivered to N5 and no downstream layer
-- has consumed them. This rollback intentionally keeps all N3 facts and the
-- original N3 outbox rows intact.

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'N4 projection matcher rollback is guarded. Review delivered outbox, inbox/checkpoint, N5/N6, notification, sim, position, and trade refs before enabling scoped deletes for trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry.';
END $$;

-- Safety preview.
SELECT event_type, status, count(*) AS row_count
FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry'
GROUP BY event_type, status
ORDER BY event_type, status;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n4_projection_matcher_consumer_v1_until_1500_formal_snapshot_fallback_retry'
  AND raw_json ->> 'execute_run_id' = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n4_projection_matcher_consumer_v1_until_1500_formal_snapshot_fallback_retry'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry';

COMMIT;
