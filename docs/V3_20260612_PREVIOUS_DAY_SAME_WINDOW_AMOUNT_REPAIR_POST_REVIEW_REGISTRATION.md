# V3 20260612 Previous Day Same Window Amount Repair Post Review Registration

Result: `POST_REVIEW_PASS`

Runtime control performed read-only registration only. It did not execute N4/N5/N6, did not restart the scheduler, and did not consume or update outbox/inbox/checkpoint.

## Execute Proof

N3 execute report: `docs/V3_20260612_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_EXECUTE_REPORT.json`

- execute result: `EXECUTE_PASS`
- SQL: `sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql`
- session flag used: `ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair='true'`
- `common_market_data_run/common_market_data_quality_item=1/1`

## Live Metric Proof

`previous_day_same_window_amount` is present and covered:

- stock rows: `62`, covered `62`, missing `0`, trace rows `62`
- index rows: `0`, covered `0`, missing `0`, trace rows `0`
- board rows: `38`, covered `38`, missing `0`, trace rows `38`
- total rows: `100`, covered `100`, missing `0`, trace rows `100`

## N4 Preservation Proof

Reviewed N4 refs are preserved:

- `common_trigger_match=4454`
- reviewed N4 outbox refs `4454`
- non-reviewed outbox refs `0`

## Forbidden Ref Proof

All checked downstream refs are `0`:

- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `common_action_event`
- `user_signal_card`
- `user_notification_queue`
- `user_sim_order`
- `user_sim_trade`
- `user_sim_position`
- `n6_virtual_account/order/trade/position/position_event/pnl_snapshot`
- `user_signal_projection`

## Scheduler Proof

`com.ashare-v3.v3-realtime-engine` remains `not_loaded` with launchctl exit code `113`.

Keep it stopped until N5 replay and scheduler reactivation review are complete.

## Decision

`previous_day_same_window_amount` is ready for N5 replay.

Allowed next gate: `V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_CONTRACT_PREFLIGHT_GATE`.

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_CONTRACT_PREFLIGHT_GATE。

目标：在 N3 previous_day_same_window_amount repair 已 POST_REVIEW_PASS、stale N5 action_mark run 已 rollback POST_REVIEW_PASS、V3 realtime engine scheduler 保持 not_loaded 后，刷新 20260612 N5 scoped replay dry-run/preflight/rollback，使用 N5-owned final action_mark derivation 和 N3 action-confirmation metric 的 previous_day_same_window_amount。要求：不执行 N5、不写 DB、不消费/update outbox/inbox/checkpoint、不重启 scheduler、不进入 N6/voice/mobile/sim/position/trade。输出 DRY_RUN_PREFLIGHT_PASS/BLOCKED、expected N5 action distribution、rollback requirements、next final gate prompt。
```
