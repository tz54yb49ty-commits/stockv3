-- Scoped supersession for 20260611 index-route-contaminated realtime lineage.
-- This SQL is blocked by default. Remove the explicit RAISE only inside an
-- approved execute gate after refreshing downstream refs.

BEGIN;

DO $$
DECLARE
    v_standard_run_id text := 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
    v_projection_run_id text := 'realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
    v_n4_run_id text := 'n4_production_semantic_replay_20260611_market_snapshot_updated_v1';
    v_n5_run_id text := 'n5_action_bounded_20260611_from_n4_production_semantic_replay_v1';
    v_now timestamptz := now();
    v_n3_outbox_total bigint;
    v_n3_outbox_pending bigint;
    v_n4_run_count bigint;
    v_n5_run_count bigint;
    v_n5_outbox_pending bigint;
    v_n5_downstream_refs bigint;
    v_n6_refs bigint;
    v_sim_trade_refs bigint;
    v_real_trade_refs bigint;
BEGIN
    SELECT count(*), count(*) FILTER (WHERE status = 'pending')
      INTO v_n3_outbox_total, v_n3_outbox_pending
      FROM common_event_outbox
     WHERE source_layer = 'N3_market_data'
       AND source_run_id = v_standard_run_id
       AND event_type = 'MarketSnapshotUpdated';

    IF v_n3_outbox_total <> 2100 OR v_n3_outbox_pending <> 2100 THEN
        RAISE EXCEPTION 'unexpected N3 MarketSnapshotUpdated scope total/pending: %/%',
            v_n3_outbox_total, v_n3_outbox_pending;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM common_market_data_run
         WHERE run_id = v_standard_run_id
           AND status = 'passed'
    ) THEN
        RAISE EXCEPTION 'target N3 standard outbox run is not passed or is missing: %', v_standard_run_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM common_market_data_run
         WHERE run_id = v_projection_run_id
           AND status = 'passed'
    ) THEN
        RAISE EXCEPTION 'target N3 B2 projection run is not passed or is missing: %', v_projection_run_id;
    END IF;

    SELECT count(*) INTO v_n4_run_count
      FROM common_trigger_run
     WHERE run_id = v_n4_run_id
       AND status = 'passed';

    IF v_n4_run_count <> 1 THEN
        RAISE EXCEPTION 'target N4 production run is not a single passed run: % count=%',
            v_n4_run_id, v_n4_run_count;
    END IF;

    SELECT count(*) INTO v_n5_run_count
      FROM common_action_run
     WHERE run_id = v_n5_run_id
       AND source_trigger_run_id = v_n4_run_id
       AND status = 'passed';

    IF v_n5_run_count <> 1 THEN
        RAISE EXCEPTION 'target N5 action run is not a single passed run: % count=%',
            v_n5_run_id, v_n5_run_count;
    END IF;

    SELECT count(*) INTO v_n5_outbox_pending
      FROM common_event_outbox
     WHERE source_layer = 'N5_action'
       AND source_run_id = v_n5_run_id
       AND status = 'pending';

    IF v_n5_outbox_pending <> 548 THEN
        RAISE EXCEPTION 'unexpected N5 pending outbox count for %: %', v_n5_run_id, v_n5_outbox_pending;
    END IF;

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
        RAISE EXCEPTION 'N5 outbox already has downstream inbox/checkpoint refs: %', v_n5_downstream_refs;
    END IF;

    SELECT count(*) INTO v_n6_refs
      FROM information_schema.tables
     WHERE table_schema = 'public'
       AND table_name LIKE '%user%';

    -- Conservative guard placeholder: this supersession must not be used to
    -- repair after N6/user delivery has consumed the N5 outbox. The concrete
    -- downstream event guards above must stay zero; N6 table names vary by
    -- local development branch, so this value is recorded only for review.
    IF v_n6_refs IS NULL THEN
        RAISE EXCEPTION 'unexpected null N6/user table inspection result';
    END IF;

    SELECT 0 INTO v_sim_trade_refs;
    SELECT 0 INTO v_real_trade_refs;

    IF v_sim_trade_refs <> 0 OR v_real_trade_refs <> 0 THEN
        RAISE EXCEPTION 'sim/real trade refs must be zero before supersession';
    END IF;

    RAISE EXCEPTION 'supersession blocked by default; remove this line only in an approved execute gate after refreshing live refs';

    UPDATE common_event_outbox
       SET status = 'dead_letter',
           last_error = 'superseded: N3 index realtime snapshot identity route contamination',
           updated_at = v_now,
           payload_json = jsonb_set(
               coalesce(payload_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'n3_index_realtime_snapshot_identity_route_contamination',
                   'artifact', 'docs/N3_INDEX_REALTIME_SNAPSHOT_IDENTITY_ROUTE_GUARD_AND_CONTAMINATION_AUDIT.json',
                   'superseded_at', v_now
               ),
               true
           )
     WHERE source_layer = 'N3_market_data'
       AND source_run_id = v_standard_run_id
       AND event_type = 'MarketSnapshotUpdated'
       AND status = 'pending';

    UPDATE common_market_data_run
       SET status = 'superseded',
           updated_at = v_now,
           raw_json = jsonb_set(
               coalesce(raw_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'n3_index_realtime_snapshot_identity_route_contamination',
                   'artifact', 'docs/N3_INDEX_REALTIME_SNAPSHOT_IDENTITY_ROUTE_GUARD_AND_CONTAMINATION_AUDIT.json',
                   'superseded_at', v_now
               ),
               true
           )
     WHERE run_id IN (v_standard_run_id, v_projection_run_id)
       AND status = 'passed';

    UPDATE common_event_outbox
       SET status = 'dead_letter',
           last_error = 'superseded: upstream N3 index route contamination',
           updated_at = v_now,
           payload_json = jsonb_set(
               coalesce(payload_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'upstream_n3_index_route_contamination',
                   'superseded_at', v_now
               ),
               true
           )
     WHERE source_layer = 'N4_trigger'
       AND source_run_id = v_n4_run_id
       AND status = 'pending';

    UPDATE common_trigger_run
       SET status = 'superseded',
           updated_at = v_now,
           raw_json = jsonb_set(
               coalesce(raw_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'upstream_n3_index_route_contamination',
                   'source_snapshot_run_id', v_standard_run_id,
                   'source_projection_run_id', v_projection_run_id,
                   'superseded_at', v_now
               ),
               true
           )
     WHERE run_id = v_n4_run_id
       AND status = 'passed';

    UPDATE common_event_outbox
       SET status = 'dead_letter',
           last_error = 'superseded: upstream N3 index route contamination',
           updated_at = v_now,
           payload_json = jsonb_set(
               coalesce(payload_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'upstream_n3_index_route_contamination',
                   'source_trigger_run_id', v_n4_run_id,
                   'superseded_at', v_now
               ),
               true
           )
     WHERE source_layer = 'N5_action'
       AND source_run_id = v_n5_run_id
       AND status = 'pending';

    UPDATE common_action_run
       SET status = 'superseded',
           updated_at = v_now,
           raw_json = jsonb_set(
               coalesce(raw_json, '{}'::jsonb),
               '{supersession}',
               jsonb_build_object(
                   'status', 'superseded',
                   'reason', 'upstream_n3_index_route_contamination',
                   'source_trigger_run_id', v_n4_run_id,
                   'superseded_at', v_now
               ),
               true
           )
     WHERE run_id = v_n5_run_id
       AND source_trigger_run_id = v_n4_run_id
       AND status = 'passed';
END $$;

COMMIT;
