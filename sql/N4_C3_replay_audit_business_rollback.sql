-- A-share monitor v3 N4 C3 replay audit business rollback draft.
--
-- Scope: future audit-only replay execute rows for one replay_run_id.
-- Default replay_run_id:
--   trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b
--
-- This rollback intentionally does not touch:
--   - original N4 projection matcher run
--   - original N5 current-real action run
--   - N3 C3 outbox / facts
--   - common_event_outbox / inbox / checkpoint
--   - common_trigger_match / common_trigger_state

BEGIN;

DO $$
DECLARE
  v_replay_run_id TEXT := 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_replay_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing replay audit rollback: N4 outbox has % rows for replay_run_id %', v_count, v_replay_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE raw_json ->> 'replay_run_id' = v_replay_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing replay audit rollback: common_event_inbox has % rows for replay_run_id %', v_count, v_replay_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload ->> 'replay_run_id' = v_replay_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing replay audit rollback: checkpoint has % rows for replay_run_id %', v_count, v_replay_run_id;
  END IF;
END $$;

DELETE FROM stock_trigger_replay_audit
WHERE replay_run_id = 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';

DELETE FROM index_trigger_replay_audit
WHERE replay_run_id = 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';

DELETE FROM board_trigger_replay_audit
WHERE replay_run_id = 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b';

COMMIT;
