# N4 C3 MinuteBarClosed Replay Dry-Run Report

- result: `DRY_RUN_PASS`
- layer_role: `N4_trigger`
- replay_run_id: `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`
- allowed_c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2b_run_id: `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- trigger_context_run_id: `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- original_n4_projection_execute_run_id: `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`
- generated_at: `2026-05-28T06:49:35.437802+00:00`

## Input Boundary

- accepted C3 rows: `17432`
- rejected C3 rows: `0`
- forbidden inputs: B1 outbox, B2 projection facts as consumption input, old synthetic N4 outbox, N5 outbox, non-allowlisted C3 outbox, raw minute tables, external adapters, old system

## Classification Summary

- candidate_count: `35970`
- by_classification: `{'missing': 18, 'unchanged': 30973, 'would_clear': 245, 'would_match': 4734}`

## Replay Diff Summary

- projection_matched_but_closed_not_matched: `245`
- projection_not_matched_but_closed_matched: `4734`
- both_matched_but_quality_changed: `0`
- unchanged: `30973`
- replay_blocked: `18`

## Closed Signal Summary

- closed_signal_status_missing_count: `0`
- closed_signal_status_distribution: `{'down_volume_expanding': 5770, 'down_volume_flat': 4962, 'down_volume_shrinking': 4154, 'flat': 5445, 'missing': 18, 'up_volume_expanding': 5794, 'up_volume_flat': 5147, 'up_volume_shrinking': 4680}`
- enrichment_row_count: `17432`

## Signal Summary

- by_signal_type: `{'BUY_HINT': 568, 'B_BUY': 17433, 'SELL_HINT': 552, 'S_SELL': 17417}`
- by_action_mark: `{'30m_shrink': 17489, '30m_volume': 17534, 'normal': 947}`
- by_legacy_signal_type: `{'BUY_HINT': 568, 'B_BUY_30M_VOL': 17433, 'SELL_HINT': 552, 'S_SELL_30M_SHRINK': 17417}`
- by_signal_type_and_classification: `{'BUY_HINT:unchanged': 471, 'BUY_HINT:would_clear': 2, 'BUY_HINT:would_match': 95, 'B_BUY:missing': 9, 'B_BUY:unchanged': 14677, 'B_BUY:would_clear': 126, 'B_BUY:would_match': 2621, 'SELL_HINT:unchanged': 481, 'SELL_HINT:would_clear': 2, 'SELL_HINT:would_match': 69, 'S_SELL:missing': 9, 'S_SELL:unchanged': 15344, 'S_SELL:would_clear': 115, 'S_SELL:would_match': 1949}`
- by_action_mark_and_classification: `{'30m_shrink:missing': 9, '30m_shrink:unchanged': 15345, '30m_shrink:would_clear': 117, '30m_shrink:would_match': 2018, '30m_volume:missing': 9, '30m_volume:unchanged': 14681, '30m_volume:would_clear': 128, '30m_volume:would_match': 2716, 'normal:unchanged': 947}`

## Boundary Confirmation

- database_written: `False`
- c3_outbox_consumed: `False`
- common_event_inbox_written: `False`
- checkpoint_written: `False`
- trigger_match_written: `False`
- trigger_state_written: `False`
- n4_outbox_written: `False`
- n5_n6_touched: `False`
- worker_started: `False`

## Quality

- P0/P1/P2: `0/1/0`
- quality_items: `16`

## Next Gate

- allow_n4_c3_replay_dry_run_review: `True`
- replay execute remains blocked until a separate replay execute/event contract is approved.