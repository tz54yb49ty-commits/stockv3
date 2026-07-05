-- N3-C2B closed signal enrichment business rollback.
-- Scope: closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
-- Deletes only C2B enrichment facts, quality rows, and run metadata.
-- Does not touch C2 summary, C2 delta minute rows, C3 outbox, B1/B2/N4/N5 runtime, or downstream layers.

DO $$
DECLARE
  v_c2b_run_id TEXT := 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_c2b_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_outbox has % rows for %', v_count, v_c2b_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_c2b_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_inbox has % rows for %', v_count, v_c2b_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c2b_run_id || '%';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_consumer_checkpoint references % in % rows', v_c2b_run_id, v_count;
  END IF;
END $$;

DELETE FROM board_closed_30m_signal_enrichment WHERE c2b_run_id = 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_closed_30m_signal_enrichment WHERE c2b_run_id = 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_closed_30m_signal_enrichment WHERE c2b_run_id = 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_quality_item WHERE run_id = 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_run WHERE run_id = 'closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
