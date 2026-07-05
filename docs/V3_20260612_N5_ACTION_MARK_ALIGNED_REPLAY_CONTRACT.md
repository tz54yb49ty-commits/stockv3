# V3 20260612 N5 Action Mark Aligned Replay Contract

Result: `CONTRACT_PASS`

This contract prepares a scoped N5 replay for:

- `source_trigger_run_id`: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- `action_run_id`: `v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1`
- `consumer_name`: `n5_action_consumer_v1`
- `for_trade_date`: `20260612`

## Preconditions

- N3 `previous_day_same_window_amount` repair post-review: `POST_REVIEW_PASS`
- Stale N5 action_mark run rollback post-review: `POST_REVIEW_PASS`
- V3 realtime engine scheduler: stopped / not loaded; no restart in this gate

## Input Contract

N5 reads only the scoped N4 source run. Standard N4 inputs remain:

- `TriggerMatched`: only action confirmation entry
- `TriggerPendingMarketData`: quality-only / no action fact
- `TriggerStateChanged`: state-gate only; none present in this run

Runtime `signal_type` is canonical `B_BUY` / `S_SELL`. `BUY_HINT` / `SELL_HINT` remain trace only.

## Metric And Action Mark Contract

Final `action_mark` is N5-owned. The replay uses N3 action-confirmation metric facts and the repaired `previous_day_same_window_amount` evidence. N5 must not trust opaque `payload.action_confirmation`, pull realtime quotes, read raw K, or rewrite N4/N3 facts.

## Dry-Run Summary

- read events: `4454`
- `TriggerMatched`: `49`
- `TriggerPendingMarketData`: `4405`
- `TriggerStateChanged`: `0`
- planned action facts after dedup: `43`
- quality-only plans: `4405`
- duplicate action confirmation grain skipped: `6`
- period trigger baseline trace: `4454/4454 present`
- N3 metric facts available for matched entries: `49/49`

## Expected Writes If Executed

- `common_action_run`: `1`
- `common_action_quality_item`: `4405`
- `stock_action_fact`: `33`
- `index_action_fact`: `0`
- `board_action_fact`: `10`
- `common_action_event`: `43`
- `common_event_outbox`: `43`
- `common_event_inbox`: `4454`
- `common_event_consumer_checkpoint`: `2082`
- `common_position_state/common_position_event`: `0/0`

## Expected Event Distribution

- `ActionExecuted`: `43`
- `ActionBlocked`: `0`
- `ActionEligible`: `0`
- `ActionSkipped`: `0`
- legacy `ActionEvent/HintEvent/RiskEvent/PositionEvent`: `0`

After dedup, expected final `action_mark` distribution is:

- `normal`: `38`
- `30m_volume`: `5`
- `30m_shrink`: `0`

## Boundary

This gate did not execute N5, write DB rows, consume or update outbox/inbox/checkpoint, restart scheduler, enter N6, or touch voice/mobile/sim/position/trade.

`execute_authorized=false` until runtime_control final gate and explicit user confirmation.
