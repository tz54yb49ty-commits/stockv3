-- N3 subscription 20260529 rollback draft.
-- Scope: market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
-- This rollback is scoped to N3 subscription control rows only.
-- It must not touch N2 scope, market facts, outbox/inbox/checkpoint, or N4-N6.

BEGIN;

DO $$
DECLARE
  v_run_id text := 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';
  v_outbox_count bigint;
  v_inbox_count bigint;
  v_checkpoint_count bigint;
BEGIN
  SELECT count(*) INTO v_outbox_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id;

  SELECT count(*) INTO v_inbox_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id;

  SELECT count(*) INTO v_checkpoint_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';

  IF v_outbox_count <> 0 OR v_inbox_count <> 0 OR v_checkpoint_count <> 0 THEN
    RAISE EXCEPTION
      'Refusing N3 subscription rollback: event refs exist for run %, outbox %, inbox %, checkpoint %',
      v_run_id, v_outbox_count, v_inbox_count, v_checkpoint_count;
  END IF;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1';

COMMIT;
