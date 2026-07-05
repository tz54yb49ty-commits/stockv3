# N4 Real MarketSnapshotUpdated Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N4_trigger
- trigger_context_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- real_n3_event_source_run_id: realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- input_filter: {'source_layer': 'N3_market_data', 'event_type': 'MarketSnapshotUpdated', 'source_run_id': 'realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute', 'status': 'pending'}
- event_count: 2188
- context_candidate_count: 4512
- matched_plan_count: 4372
- pending_plan_count: 0
- minute_bar_dependency_count: 4512
- P0/P1/P2: 0/1/0

## Match Summary

- matched_by_asset_kind: {'board': 254, 'index': 18, 'stock': 4100}
- matched_by_direction: {'buy': 2187, 'sell': 2185}
- matched_by_signal_type: {'B_BUY': 2187, 'S_SELL': 2185}
- matched_trigger_period_distribution: {'D': 3674, 'M': 255, 'Q': 86, 'W': 301, 'Y': 56}
- full_matched_plan_count: 66
- BUY_HINT matched/dependency: 0/71
- SELL_HINT matched/dependency: 0/69

## Trigger Type Summary

- B_BUY: {'matched_plan_count': 2187, 'source_event_type': 'MarketSnapshotUpdated'}
- S_SELL: {'matched_plan_count': 2185, 'source_event_type': 'MarketSnapshotUpdated'}
- BUY_FULL: {'matched_plan_count': 43, 'source_event_type': 'MarketSnapshotUpdated', 'signal_type': 'B_BUY'}
- SELL_FULL: {'matched_plan_count': 23, 'source_event_type': 'MarketSnapshotUpdated', 'signal_type': 'S_SELL'}
- B_BUY_30M_VOL: {'matched_plan_count': 0, 'minute_bar_dependency_count': 2187, 'required_event_type': 'MinuteBarClosed_or_N3_30m_summary'}
- S_SELL_30M_SHRINK: {'matched_plan_count': 0, 'minute_bar_dependency_count': 2185, 'required_event_type': 'MinuteBarClosed_or_N3_30m_summary'}
- BUY_HINT: {'matched_plan_count': 0, 'minute_bar_dependency_count': 71, 'required_event_type': 'MinuteBarClosed_or_N3_30m_summary'}
- SELL_HINT: {'matched_plan_count': 0, 'minute_bar_dependency_count': 69, 'required_event_type': 'MinuteBarClosed_or_N3_30m_summary'}

## Minute-Bar Dependency

- requires_minute_bar_or_30m_summary: true
- dependency_count: 4512
- non_hint_30m_dependency_count: 4372
- hint_dependency_count: 140
- by_signal_type: {'BUY_HINT': 71, 'B_BUY_30M_VOL': 2187, 'SELL_HINT': 69, 'S_SELL_30M_SHRINK': 2185}
- explanation: MarketSnapshotUpdated can plan ordinary B_BUY/S_SELL/FULL triggers; 30m and hint signal types remain waiting for N3 MinuteBarClosed or an N3 closed 30m summary.

## Synthetic Isolation

- denylist: ['trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute']
- read_real_n3_source_run_id_only: realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- disallowed_plan_source_runs: []
- stale_synthetic_outbox_total: 53304
- current_context_run_n4_outbox_count: 0

## Future Execute Writes

- allowed_tables_after_separate_authorization: ['common_event_inbox', 'common_event_consumer_checkpoint', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item', 'common_event_outbox']
- forbidden_tables: ['stock/index/board_condition_*', 'stock/index/board_realtime_daily_snapshot', 'stock/index/board_minute_bar_1m', 'action/user/voice/sim/position tables']
- execute_gate_note: Future execute must be separately authorized, consume only current N3 source_run_id, and write trigger facts + N4 outbox atomically with inbox/checkpoint updates.

## Rollback

- this_dry_run: No DB rollback required; delete docs/N4_REAL_MARKET_SNAPSHOT_DRY_RUN_REPORT.json and docs/N4_REAL_MARKET_SNAPSHOT_DRY_RUN_REPORT.md if the report must be discarded.
- future_real_execute:
  - Precheck N4 outbox rows for the execute run have not been delivered or consumed downstream.
  - Delete N4 common_event_outbox rows for source_run_id=current N4 context run and source_event_id values from current snapshot_run_id.
  - Delete common_trigger_match/common_trigger_state rows for current N4 context run created by real execute.
  - Delete N4 common_event_inbox/checkpoint rows for the N3 snapshot events consumed by that execute.
  - Do not touch N3 snapshot facts/outbox except delivery status rollback if execute explicitly changed status in the same authorized transaction.

## Execute Gate

- allow_enter_real_execute_review: true
- allow_direct_execute: false
- scope: current N3-B1 MarketSnapshotUpdated snapshot-only ordinary BUY/SELL/FULL plans; 30m/hint signals wait for MinuteBarClosed or N3 30m summary
- required_review_items: ['Confirm whether real execute may use the current event-contract matcher for ordinary snapshot triggers, or must first implement price/period threshold comparison using N3 snapshot values and period_trigger_baseline_json.', 'Confirm inbox/checkpoint/ack semantics and rollback SQL before any write.', 'Confirm stale synthetic denylist remains excluded from N5.']

## Boundary Confirmation

- read_only_database_checks: true
- writes_performed: false
- common_event_inbox_written: false
- consumer_checkpoint_updated: false
- trigger_state_written: false
- trigger_match_written: false
- event_outbox_written: false
- n3_outbox_consumed_or_acked: false
- market_data_pulled: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false
- synthetic_outbox_read_as_input: false
- external_n2_runtime_path_accessed: false
