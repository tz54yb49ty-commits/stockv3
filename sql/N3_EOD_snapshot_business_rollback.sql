-- N3-EOD snapshot refresh business rollback.
-- Scope: eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
-- Deletes only EOD snapshot facts, reconciliation facts, quality rows, and run metadata.
-- Does not touch B1/B2/C2/C2B/C3/N4/N5 runtime, event outbox, inbox, checkpoint, minute bars, snapshots, projections, or downstream layers.

DO $$
DECLARE
  v_eod_run_id TEXT := 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_eod_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_outbox has % rows for %', v_count, v_eod_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_eod_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_inbox has % rows for %', v_count, v_eod_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_eod_run_id || '%';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_consumer_checkpoint references % in % rows', v_eod_run_id, v_count;
  END IF;
END $$;

DELETE FROM board_eod_reconciliation_item WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_eod_reconciliation_item WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_eod_reconciliation_item WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM board_eod_snapshot WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM index_eod_snapshot WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM stock_eod_snapshot WHERE eod_run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_quality_item WHERE run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
DELETE FROM common_market_data_run WHERE run_id = 'eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute';
