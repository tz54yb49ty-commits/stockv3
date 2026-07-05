# V3 20260616 Stale N5 Formal Amount Chain Unit Bug Rollback Execute Report

Result: `ROLLBACK_PASS`

Generated at: `2026-06-17 02:02:10 +0800`

Layer role: `N5_action`

## Scope

- action_run_id: `v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1`
- source_trigger_run_id: `v3_n4_trigger_replay_20260616_until_1401_v1`
- consumer_name: `n5_action_consumer_v1_20260616_trigger_price_repair_replay`
- rollback SQL: `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`

Executed approved command:

```bash
/opt/homebrew/opt/postgresql@16/bin/psql \
  "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" \
  -v ON_ERROR_STOP=1 \
  -f sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql
```

## Precheck

```text
N5 outbox delivered/delivering = 0
N5 downstream inbox/checkpoint refs = 0/0
scoped dedicated consumer inbox/checkpoint = 540/452
non-scoped N4 checkpoint refs = 3431 preserved/non-blocking
```

## Delete Count Proof

The rollback transaction committed.

```text
common_event_delivery_attempt = 0
common_event_consumer_checkpoint = 452
common_event_inbox = 540
common_event_outbox = 540
common_event_ledger = 0
common_action_event = 540
board_action_fact = 44
index_action_fact = 18
stock_action_fact = 478
common_action_quality_item = 0
common_action_run = 1
```

## Post-Rollback Zero Proof

```text
common_action_run = 0
stock_action_fact = 0
index_action_fact = 0
board_action_fact = 0
common_action_event = 0
N5 common_event_outbox = 0
N5 common_event_ledger = 0
dedicated consumer N4 inbox = 0
dedicated consumer N4 checkpoint = 0
```

## N4 Preservation Proof

```text
common_trigger_run = 1
common_trigger_state = 4698
common_trigger_match = 540
N4 outbox total = 4698
N4 outbox pending = 4698
N4 outbox delivered/delivering = 0
TriggerMatched pending = 540
TriggerPendingMarketData pending = 4158
```

No N4 trigger facts were deleted. N4 outbox status was not updated.

## N3 Preservation Proof

Metric run:

`action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`

```text
stock metric rows = 564
index metric rows = 17
board metric rows = 53
```

No N3 metric/source facts were deleted.

## Downstream Forbidden Proof

```text
user_projection_run refs = 0
user_signal_projection refs = 0
user_notification_queue refs = 0
common_position_state refs = 0
common_position_event refs = 0
```

Boundary:

- N6 entered: `false`
- worker/scheduler started: `false`
- N5 outbox consumed: `false`
- N4 outbox status updated: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system touched: `false`

## Next Gate

Allowed next gate:

`V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_POST_REVIEW_GATE`

Prompt:

```text
layer_role=N5_action。

进入 V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_POST_REVIEW_GATE。

目标：只读复核 20260616 stale N5 scoped rollback 执行结果。

读取：
- docs/V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_EXECUTE_REPORT.md/json
- sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql

确认：
- scoped N5 common_action_run/action facts/action_event/outbox/ledger 为 0
- dedicated consumer N4 inbox/checkpoint 为 0/0
- N4 trigger run/state/match/outbox 保留且 outbox pending 不变
- N3 metric/source facts 保留
- N6/user/position refs=0
- 未进入 N6，未启动 scheduler/worker，未触碰 voice/mobile/sim/position/order/real trade

输出 POST_REVIEW_PASS / BLOCKED、N5 cleanup proof、N4/N3 preservation proof、downstream forbidden proof、是否允许进入 stale N4 rollback final gate。
```
