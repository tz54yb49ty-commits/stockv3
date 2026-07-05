# V3 20260615 Full-Day N3/N4/N5/N6 Amount Guard Replay Closeout

- result: `CLOSEOUT_PASS`
- trade_date: `20260615`
- scope: `full_day_until_1500_replay_with_amount_guard_and_trigger_period_baseline_fix`

## Lineage

- N3 metric: `action_confirmation_projection_metric_20260615_until_1500_after_n4_amount_guard_fix_v1`
- N4 fixed replay: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1500_amount_guard_fix_v1`
- N5 replay: `n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1500_v1`
- N6 projection: `v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1500_v1`

## Live Proof

- N3 metric rows stock/index/board/total: `25/0/0/25`; ready `25/25`
- N4 outbox: `TriggerMatched=25`, `TriggerPendingMarketData=4203`; ordinary formal matched `0`, HINT matched `25`
- N5 events: `ActionBlocked=25`, `ActionExecuted=0`, `ActionEligible=0`, `ActionSkipped=0`
- N5 blocked reasons: `[{'blocked_reason': 'price_confirmation_failed', 'c': 21}, {'blocked_reason': 'amount_confirmation_failed', 'c': 4}]`
- N6 writes: `user_projection_run=1`, `user_signal_projection=0`, `user_signal_card=0`, `user_notification_queue=0`

## Interpretation

N3 -> N4 -> N5 -> N6 is replay-closeout complete for the fixed full-day lineage. N5 received the fixed N4 `TriggerMatched` rows and joined N3 action-confirmation metrics 25/25. The final business result is all `ActionBlocked`: 21 price confirmation failures and 4 amount confirmation failures. Therefore N6 correctly produced zero ordinary user messages because ordinary user messages only include `ActionEligible` / `ActionExecuted`.

## Boundary

- old system touched: `false`
- scheduler/worker started: `false`
- N4/N5 outbox consumed or status-updated: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- rollback executed: `false`

## Validation

- focused N4 tests: `32 OK`
- trigger test group: `142 OK`
- action/N6 tests: `131 OK`
- `scripts/check_n4_contract.py`: `PASS`
- `compileall`: `PASS`
- JSON parse: `PASS`
- rollback static check: `PASS`
- `git diff --check`: `PASS`
