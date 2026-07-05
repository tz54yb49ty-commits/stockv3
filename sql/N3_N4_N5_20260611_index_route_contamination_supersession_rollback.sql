-- Rollback for scoped supersession registration.
-- This restores statuses only if the superseded N5 outbox has not been
-- consumed. It is blocked by default and should normally remain unexecuted
-- once clean replacement lineage exists.

BEGIN;

DO $$
DECLARE
    v_standard_run_id text := 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
    v_projection_run_id text := 'realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
    v_n4_run_id text := 'n4_production_semantic_replay_20260611_market_snapshot_updated_v1';
    v_n5_run_id text := 'n5_action_bounded_20260611_from_n4_production_semantic_replay_v1';
    v_now timestamptz := now();
    v_n5_downstream_refs bigint;
BEGIN
    WITH n5_events AS (
        SELECT event_id FROM common_event_outbox
         WHERE source_layer = 'N5_action'
           AND source_run_id = v_n5_run_id
    )
    SELECT
        (SELECT count(*) FROM common_event_inbox i JOIN n5_events e ON i.event_id = e.event_id)
      + (SELECT count(*) FROM common_event_consumer_checkpoint c JOIN n5_events e ON c.last_event_id = e.event_id)
      INTO v_n5_downstream_refs;

    IF v_n5_downstream_refs <> 0 THEN
        RAISE EXCEPTION 'cannot rollback supersession after N5 outbox downstream refs: %', v_n5_downstream_refs;
    END IF;

    RAISE EXCEPTION 'supersession rollback blocked by default; remove this line only in an approved rollback gate';

    UPDATE common_market_data_run
       SET status = 'passed',
           updated_at = v_now,
           raw_json = coalesce(raw_json, '{}'::jsonb) - 'supersession'
     WHERE run_id IN (v_standard_run_id, v_projection_run_id)
       AND status = 'superseded';

    UPDATE common_trigger_run
       SET status = 'passed',
           updated_at = v_now,
           raw_json = coalesce(raw_json, '{}'::jsonb) - 'supersession'
     WHERE run_id = v_n4_run_id
       AND status = 'superseded';

    UPDATE common_action_run
       SET status = 'passed',
           updated_at = v_now,
           raw_json = coalesce(raw_json, '{}'::jsonb) - 'supersession'
     WHERE run_id = v_n5_run_id
       AND status = 'superseded';

    UPDATE common_event_outbox
       SET status = 'pending',
           last_error = NULL,
           updated_at = v_now,
           payload_json = coalesce(payload_json, '{}'::jsonb) - 'supersession'
     WHERE source_run_id IN (v_standard_run_id, v_n4_run_id, v_n5_run_id)
       AND status = 'dead_letter'
       AND payload_json->'supersession'->>'reason' IN (
           'n3_index_realtime_snapshot_identity_route_contamination',
           'upstream_n3_index_route_contamination'
       );
END $$;

COMMIT;
