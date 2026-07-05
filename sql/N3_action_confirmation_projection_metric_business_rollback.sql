-- A-share monitor v3 N3 action-confirmation projection metric business rollback draft.
-- Scope: delete only rows for one projection_run_id from N3 action-confirmation
-- metric facts, common_market_data_quality_item, and common_market_data_run.
-- Do not touch N2 condition rows, B1 snapshot rows, C1 minute rows, N4/N5/N6
-- facts, outbox, inbox, checkpoint, worker state, or real-trade state.

\set ON_ERROR_STOP on
\set projection_run_id 'REPLACE_WITH_N3_ACTION_CONFIRMATION_PROJECTION_RUN_ID'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

-- Hard guard: future N3 action-confirmation projection facts must not be rolled
-- after downstream layers have consumed or referenced the projection_run_id.
DO $$
DECLARE
  target_run_id TEXT := current_setting('app.projection_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id;

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id;

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%';

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0 THEN
    RAISE EXCEPTION
      'action_confirmation metric business rollback blocked: scoped refs outbox=%, inbox=%, checkpoint=% for projection_run_id=%',
      outbox_refs,
      inbox_refs,
      checkpoint_refs,
      target_run_id;
  END IF;
END $$;

BEGIN;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'projection_run_id'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'action_confirmation_projection_metric';

DELETE FROM common_market_data_run
WHERE run_id = :'projection_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
