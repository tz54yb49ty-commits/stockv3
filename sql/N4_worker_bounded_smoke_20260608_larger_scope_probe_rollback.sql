-- N4 worker bounded smoke rollback.
-- Target smoke run_id: n4_worker_bounded_smoke_20260608_larger_scope_probe
-- Consumer: n4_trigger_worker_v1_bounded_smoke_larger_scope_probe
-- This draft is intentionally guarded; review downstream refs before enabling row removal.

DO $$
BEGIN
  RAISE EXCEPTION 'N4 worker bounded smoke rollback is guarded. Review delivered/delivering N4 outbox, active worker heartbeat, N5 refs, N6 refs, user/sim/order/trade/position refs before enabling scoped row removal for n4_worker_bounded_smoke_20260608_larger_scope_probe.';
END $$;

-- Guard checklist before row removal:
-- 1. N4 common_event_outbox delivered/delivering rows for n4_worker_bounded_smoke_20260608_larger_scope_probe must be 0.
-- 2. N5 common_action_run/common_action_event refs for n4_worker_bounded_smoke_20260608_larger_scope_probe must be 0.
-- 3. N6/user_signal_projection/user_signal_card/user_notification_queue refs must be 0.
-- 4. user_sim/order/trade/position/real_trade refs must be 0.
-- 5. worker heartbeat/running status for n4_worker_bounded_smoke_20260608_larger_scope_probe must be stopped.
-- 6. N3 facts and N3 common_event_outbox status must not be touched.

DELETE FROM common_event_inbox
WHERE consumer_name = 'n4_trigger_worker_v1_bounded_smoke_larger_scope_probe'
  AND raw_json ->> 'bounded_smoke_run_id' = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n4_trigger_worker_v1_bounded_smoke_larger_scope_probe'
  AND checkpoint_payload ->> 'bounded_smoke_run_id' = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_trigger_match
WHERE run_id = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_trigger_state
WHERE run_id = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';

DELETE FROM common_trigger_run
WHERE run_id = 'n4_worker_bounded_smoke_20260608_larger_scope_probe';
