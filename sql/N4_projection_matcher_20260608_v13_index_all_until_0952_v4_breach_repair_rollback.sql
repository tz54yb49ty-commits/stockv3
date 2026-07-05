-- N4 projection matcher scoped rollback for 20260608 v13 index-all until 09:52.
-- Scope: target N4 run only. Execute only after N6 and N5 rollback post-review pass.
-- Preserves N3/N2/N1 rows and upstream N3 event rows.

BEGIN;

\set target_run_id 'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952'
SET LOCAL n4.rollback_target_run_id = :'target_run_id';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n4.rollback_target_run_id', true);
  v_count BIGINT := 0;
  v_table_name TEXT;
  v_table_regclass REGCLASS;
  v_outbox_removed INTEGER := 0;
  v_match_removed INTEGER := 0;
  v_state_removed INTEGER := 0;
  v_quality_removed INTEGER := 0;
  v_inbox_removed INTEGER := 0;
  v_checkpoint_removed INTEGER := 0;
  v_run_removed INTEGER := 0;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'N4 rollback blocked: target run id is not set';
  END IF;

  IF v_run_id <> 'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952' THEN
    RAISE EXCEPTION 'N4 rollback blocked: unexpected target run id %', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_trigger_run
   WHERE run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N4 rollback blocked: expected one target run row, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id
     AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: target outbox has delivered or delivering rows %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_ledger
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: event ledger rows exist for target run %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_inbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: downstream inbox rows still reference target run %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_consumer_checkpoint
   WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%'
     AND consumer_name <> 'n4_projection_matcher_consumer_v1';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: non-target checkpoint rows still reference target run %', v_count;
  END IF;

  IF to_regclass('public.common_event_delivery_attempt') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM common_event_delivery_attempt d
      JOIN common_event_outbox o ON o.outbox_id = d.outbox_id
     WHERE o.source_layer = 'N4_trigger'
       AND o.source_run_id = v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: delivery attempt rows reference target outbox %', v_count;
    END IF;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'common_action_run',
    'common_action_event',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'common_event_outbox',
    'common_event_inbox',
    'common_event_consumer_checkpoint',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_signal_decision',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_pnl_snapshot',
    'common_position_state',
    'common_position_event'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NULL THEN
      CONTINUE;
    END IF;

    EXECUTE format('SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1', v_table_regclass)
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      IF v_table_name IN ('common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint') THEN
        IF v_table_name = 'common_event_outbox' THEN
          SELECT count(*) INTO v_count
            FROM common_event_outbox
           WHERE source_layer = 'N4_trigger'
             AND source_run_id = v_run_id;
        ELSIF v_table_name = 'common_event_inbox' THEN
          SELECT count(*) INTO v_count
            FROM common_event_inbox
           WHERE consumer_name = 'n4_projection_matcher_consumer_v1'
             AND raw_json ->> 'execute_run_id' = v_run_id;
        ELSE
          SELECT count(*) INTO v_count
            FROM common_event_consumer_checkpoint
           WHERE consumer_name = 'n4_projection_matcher_consumer_v1'
             AND checkpoint_payload ->> 'execute_run_id' = v_run_id;
        END IF;
        IF v_count = 0 THEN
          RAISE EXCEPTION 'N4 rollback blocked: table % has non-target refs', v_table_name;
        END IF;
      ELSE
        RAISE EXCEPTION 'N4 rollback blocked: downstream table % still references target run', v_table_name;
      END IF;
    END IF;
  END LOOP;

  DELETE FROM common_event_outbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id;
  GET DIAGNOSTICS v_outbox_removed = ROW_COUNT;

  DELETE FROM common_trigger_match
   WHERE run_id = v_run_id;
  GET DIAGNOSTICS v_match_removed = ROW_COUNT;

  DELETE FROM common_trigger_state
   WHERE run_id = v_run_id;
  GET DIAGNOSTICS v_state_removed = ROW_COUNT;

  DELETE FROM common_trigger_quality_item
   WHERE run_id = v_run_id;
  GET DIAGNOSTICS v_quality_removed = ROW_COUNT;

  DELETE FROM common_event_inbox
   WHERE consumer_name = 'n4_projection_matcher_consumer_v1'
     AND raw_json ->> 'execute_run_id' = v_run_id;
  GET DIAGNOSTICS v_inbox_removed = ROW_COUNT;

  DELETE FROM common_event_consumer_checkpoint
   WHERE consumer_name = 'n4_projection_matcher_consumer_v1'
     AND checkpoint_payload ->> 'execute_run_id' = v_run_id;
  GET DIAGNOSTICS v_checkpoint_removed = ROW_COUNT;

  DELETE FROM common_trigger_run
   WHERE run_id = v_run_id;
  GET DIAGNOSTICS v_run_removed = ROW_COUNT;

  IF v_run_removed <> 1 THEN
    RAISE EXCEPTION 'N4 rollback blocked: expected one target run row removal, got %', v_run_removed;
  END IF;

  RAISE NOTICE 'N4 projection matcher rollback completed for %, outbox=%, match=%, state=%, quality=%, inbox=%, checkpoint=%, run=%',
    v_run_id, v_outbox_removed, v_match_removed, v_state_removed, v_quality_removed,
    v_inbox_removed, v_checkpoint_removed, v_run_removed;
END $$;

COMMIT;
