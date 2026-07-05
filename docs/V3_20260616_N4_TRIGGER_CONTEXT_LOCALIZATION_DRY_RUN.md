# V3 20260616 N4 Trigger Context Localization Dry Run

result: DRY_RUN_PASS
source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
trigger_context_run_id: `trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
source_trade_date / for_trade_date: `20260615` / `20260616`
candidate_context_row_count: `4698`
object_count_by_asset_kind: `{'stock': 1822, 'index': 83, 'board': 127}`
direction_distribution: `{'buy': 2076, 'sell': 2622}`
trigger_candidate_count_by_signal_type: `{'BUY': 1962, 'BUY:FULL': 70, 'BUY_HINT': 44, 'SELL': 2025, 'SELL:FULL': 7, 'SELL_HINT': 590}`
P0/P1/P2: `0` / `0` / `0`

Boundary: no execute, no database write, no N3 outbox consume/update, no worker, no N5/N6.
