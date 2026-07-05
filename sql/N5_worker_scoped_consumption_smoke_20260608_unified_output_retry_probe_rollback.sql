-- N5 worker scoped consumption smoke rollback draft.
--
-- Target smoke run:
--   n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe
-- Target consumer:
--   n5_action_worker_v1_scoped_consumption_smoke_probe
--
-- This file is intentionally guarded. Do not execute unless a separate
-- rollback final gate authorizes it.

DO $$
BEGIN
  RAISE EXCEPTION 'N5 scoped consumption smoke rollback is disabled by default; remove this guard only after rollback final gate approval.';
END $$;

-- Guard: N4 source outbox for this source run must not have been delivered or
-- marked delivering by the scoped smoke consumer.
DO $$
DECLARE
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry'
    AND event_type = 'TriggerMatched'
    AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N4 source outbox delivered/delivering rows exist (%)', v_count;
  END IF;
END $$;

-- Guard: scoped N5 outbox rows, if any were created by a bad runner, must not
-- have been delivered or marked delivering.
DO $$
DECLARE
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'
    AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: scoped N5 outbox delivered/delivering rows exist (%)', v_count;
  END IF;
END $$;

-- Guard: no downstream N6/user/sim/order/trade/position refs may point at this
-- scoped smoke run.
DO $$
DECLARE
  v_count bigint;
BEGIN
  SELECT
    COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_card WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM user_notification_queue WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM virtual_order WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM virtual_trade WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM virtual_position WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
    + COALESCE((SELECT count(*) FROM virtual_pnl WHERE source_action_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe'), 0)
  INTO v_count;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream refs exist for scoped smoke action run (%)', v_count;
  END IF;
END $$;

-- Scoped cleanup. The intended consumption-only smoke should only write
-- common_action_run, quality, inbox, and checkpoint rows. Action fact/event/N5
-- outbox deletes are scoped safeguards in case an unaligned runner wrote them.
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n5_action_worker_v1_scoped_consumption_smoke_probe';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n5_action_worker_v1_scoped_consumption_smoke_probe'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM common_action_event
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM stock_action_fact
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM index_action_fact
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM board_action_fact
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM common_action_quality_item
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';

DELETE FROM common_action_run
WHERE run_id = 'n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe';
