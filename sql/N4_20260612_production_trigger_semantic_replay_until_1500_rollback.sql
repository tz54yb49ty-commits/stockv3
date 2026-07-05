-- N4 projection matcher execute rollback.
-- Scope: N4 execute run only. Run only after confirming N4 outbox rows for
-- this execute_run_id have not been delivered to N5 and no downstream layer
-- has consumed them. This rollback intentionally keeps all N3 facts and the
-- original N3 outbox rows intact.

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'N4 projection matcher rollback is guarded. Review delivered outbox, inbox/checkpoint, N5/N6, notification, sim, position, and trade refs before enabling scoped deletes for n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500.';
END $$;

-- Safety preview.
SELECT event_type, status, count(*) AS row_count
FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500'
GROUP BY event_type, status
ORDER BY event_type, status;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_trigger_match
WHERE run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_trigger_state
WHERE run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500'
  AND raw_json ->> 'execute_run_id' = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

DELETE FROM common_trigger_run
WHERE run_id = 'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500';

COMMIT;
