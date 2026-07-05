-- V3 20260615 formal amount guard polluted lineage rollback.
-- Scope:
--   N4: n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000
--   N5:
--     n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000
--     n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1
--   N6:
--     v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000
--     v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1
--
-- Boundary:
--   Deletes only the scoped N6/N5/N4 lineage above, in N6 -> N5 -> N4 order.
--   Preserves all N3 facts and N3 outbox status. Does not touch voice/mobile,
--   sim, position, order, real-trade, scheduler, or worker state.

BEGIN;

SET LOCAL ashare_v3.allow_v3_20260615_formal_amount_guard_polluted_lineage_rollback = 'true';

DO $$
DECLARE
  v_n4_run_id text := 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';
  v_n5_run_ids text[] := ARRAY[
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  ];
  v_n5_consumer_names text[] := ARRAY[
    'n5_action_bounded_consumer_20260615_from_n4_until_1000',
    'n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1'
  ];
  v_n6_run_ids text[] := ARRAY[
    'v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1'
  ];
  v_count bigint := 0;
  v_table_name text;
  v_table_regclass regclass;
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260615_formal_amount_guard_polluted_lineage_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: set ashare_v3.allow_v3_20260615_formal_amount_guard_polluted_lineage_rollback=true in this transaction';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer IN ('N4_trigger', 'N5_action')
    AND (
      source_run_id = v_n4_run_id
      OR source_run_id = ANY(v_n5_run_ids)
    )
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: scoped N4/N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = ANY(v_n5_run_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND checkpoint_payload::text LIKE ANY(ARRAY[
      '%' || v_n5_run_ids[1] || '%',
      '%' || v_n5_run_ids[2] || '%'
    ]);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_n4_run_id
    AND consumer_name <> ALL(v_n5_consumer_names);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: non-scoped N4 consumer inbox refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE source_trigger_run_id = v_n4_run_id
    AND run_id <> ALL(v_n5_run_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: non-scoped N5 action runs reference N4 source (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_projection_run
  WHERE source_action_run_id = ANY(v_n5_run_ids)
    AND user_projection_run_id <> ALL(v_n6_run_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: non-scoped N6 projection runs reference scoped N5 (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_notification_queue
  WHERE user_projection_run_id = ANY(v_n6_run_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: scoped N6 notification queue rows exist (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_signal_decision',
    'common_event_delivery_attempt',
    'user_notification_delivery',
    'user_delivery_event',
    'user_push_delivery',
    'user_voice_delivery',
    'user_voice_queue',
    'user_voice_delivery_log',
    'user_mobile_delivery',
    'user_mobile_queue',
    'user_device_ack',
    'user_position_projection',
    'user_position_state',
    'common_position_state',
    'common_position_event',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot',
    'n6_virtual_order_proposal',
    'real_trade_order',
    'real_trade_execution',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format(
      'SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2 OR to_jsonb(t)::text LIKE $3',
      v_table_regclass
    )
    INTO v_count
    USING '%' || v_n4_run_id || '%', '%' || v_n5_run_ids[1] || '%', '%' || v_n5_run_ids[2] || '%';
    IF v_count > 0 THEN
      RAISE EXCEPTION 'V3 20260615 formal amount guard rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
    END IF;
  END LOOP;
END $$;

DELETE FROM user_signal_card
WHERE user_projection_run_id IN (
  'v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
  'v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1'
);

DELETE FROM user_signal_projection
WHERE user_projection_run_id IN (
  'v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
  'v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1'
);

DELETE FROM user_projection_run
WHERE user_projection_run_id IN (
  'v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
  'v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1'
);

WITH scoped_n4_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name IN (
    'n5_action_bounded_consumer_20260615_from_n4_until_1000',
    'n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1'
  )
    AND source_layer = 'N4_trigger'
    AND source_run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name IN (
    'n5_action_bounded_consumer_20260615_from_n4_until_1000',
    'n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1'
  )
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_n4_partitions);

DELETE FROM common_event_inbox
WHERE consumer_name IN (
    'n5_action_bounded_consumer_20260615_from_n4_until_1000',
    'n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1'
  )
  AND source_layer = 'N4_trigger'
  AND source_run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM common_action_event
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM board_action_fact
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM index_action_fact
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM stock_action_fact
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM common_action_quality_item
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM common_action_run
WHERE run_id IN (
    'n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000',
    'n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1'
  );

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_event_ledger
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_trigger_match
WHERE run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_trigger_state
WHERE run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000'
  AND raw_json ->> 'execute_run_id' = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

DELETE FROM common_trigger_run
WHERE run_id = 'n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000';

COMMIT;
