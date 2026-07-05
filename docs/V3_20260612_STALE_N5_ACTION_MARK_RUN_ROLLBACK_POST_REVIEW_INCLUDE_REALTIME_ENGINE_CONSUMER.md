# V3 20260612 Stale N5 Action Mark Rollback Post Review Including Realtime Engine Consumer

Result: `POST_REVIEW_PASS`

Runtime control performed only read-only post-review. The scoped rollback execution was performed in `N5_action` according to the final gate.

## Execute Proof

Execute report: `docs/V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_EXECUTE_INCLUDE_REALTIME_ENGINE_CONSUMER_REPORT.json`

Result: `ROLLBACK_PASS`

The rollback SQL committed and reported:

- `common_event_consumer_checkpoint=43`
- `common_event_inbox=49`
- `common_event_outbox=43`
- `common_action_event=43`
- `board_action_fact=10`
- `index_action_fact=0`
- `stock_action_fact=33`
- `common_action_quality_item=0`
- `common_action_run=1`

## Live Post-Rollback Proof

The stale N5 run is now clean:

- `common_action_run=0`
- `common_action_quality_item=0`
- `stock_action_fact=0`
- `index_action_fact=0`
- `board_action_fact=0`
- `common_action_event=0`
- N5 outbox `0`
- N5 ledger `0`
- reviewed stale consumers inbox/checkpoint `0/0`
- non-stale inbox refs for source N4 `0`

Reviewed stale consumers:

- `n5_action_consumer_v1`
- `v3_realtime_engine_n5_consumer_20260612`

## N4 Preservation Proof

N4 is preserved:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_event_outbox_n4=4454`
- N4 outbox pending `4454`
- N4 outbox delivered/delivering `0`
- N4 outbox status updated: `false`

## Scheduler Proof

`com.ashare-v3.v3-realtime-engine` remains stopped:

- launchctl print exit code: `113`
- state: `not_loaded`
- wrapper/child process count: `0`

Keep it stopped until N3 repair and N5 replay readiness are complete.

## Downstream Boundary Proof

Refs are `0` for:

- `user_projection_run`
- `user_signal_projection`
- `user_signal_decision`
- `user_notification_queue`
- `user_sim_order`
- `user_sim_trade`
- `user_sim_position`
- `common_position_state`
- `common_position_event`

No N6, voice, mobile, sim, position, or trade path was touched.

## Decision

The stale N5 action_mark run rollback is complete.

Allowed next route: refresh N3 `previous_day_same_window_amount` repair SQL so it allows reviewed N4 refs while continuing to block N5/N6/user refs.

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_20260612_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_SQL_REFRESH_ALLOW_N4_REFS_GATE。

目标：在 stale N5 action_mark run 已 rollback POST_REVIEW_PASS、V3 realtime engine scheduler 保持 not_loaded 后，刷新 previous_day_same_window_amount additive schema/backfill repair SQL，使其允许 reviewed N4 refs（保留 N4 trigger run/outbox），但继续 hard-fail 阻断 N5/N6/user/sim/voice/mobile refs。不得执行 SQL、不得写 DB、不得重启 scheduler、不得执行 N4/N5/N6。输出 REPAIR_PASS/BLOCKED、SQL guard proof、rollback/static tests、forbidden scope proof。
```
