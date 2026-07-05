# V3 Realtime Engine Scheduler Stop After Stale N5 Rollback Partial

Result: `STOP_PASS`

This gate performed only the authorized scoped scheduler stop and read-only post-checks. It did not manually execute wrapper/N3/N4/N5, did not execute rollback, did not write business data, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/position/trade.

## Stop Proof

Target:

- label: `com.ashare-v3.v3-realtime-engine`
- plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.v3-realtime-engine.plist`

Pre-stop:

- launchctl loaded: `true`
- state: `not running`
- run interval: `3` seconds
- runs: `659`
- last exit code: `0`
- wrapper/child process count: `0`
- plist lint: `PASS`

Executed command:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.v3-realtime-engine.plist
```

Command exit code: `0`

Post-stop:

- `launchctl print` exit code: `113`
- state: `not_loaded`
- wrapper/child process count: `0`
- plist still installed: `true`

## Current Partial State

Stale N5 action run:

`v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`

Current rows:

- `common_action_run=1`
- `common_action_quality_item=0`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- N5 outbox `43`, pending `43`, delivered/delivering `0`
- original scoped consumer `n5_action_consumer_v1` inbox/checkpoint: `0/0`
- production wrapper consumer `v3_realtime_engine_n5_consumer_20260612` inbox/checkpoint: `49/43`

The production wrapper consumer refs were observed at:

`2026-06-13 09:59:11.293845+08`

## N4 Preservation Proof

N4 remains preserved:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_event_outbox_n4=4454`
- N4 outbox delivered/delivering: `0`

## Decision

Scheduler is now stopped. Do not restart it before stale N5 cleanup is repaired and completed.

Next step is to repair the N5 rollback scope so it includes or supersedes the production wrapper consumer `v3_realtime_engine_n5_consumer_20260612`, while preserving N4 and N3.

## Forbidden Scope Proof

- Wrapper manually executed: `false`
- N3/N4/N5 manually executed: `false`
- Rollback executed: `false`
- Business database written: `false`
- Outbox consumed or updated: `false`
- Inbox/checkpoint consumed or updated: `false`
- N6 entered: `false`
- Voice/mobile/sim/position/trade touched: `false`
- Old system modified: `false`

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_ACTION_MARK_ROLLBACK_SCOPE_REPAIR_INCLUDE_REALTIME_ENGINE_CONSUMER_GATE。

目标：在 V3 realtime engine scheduler 已 stop/not_loaded 后，修复 stale N5 action_mark rollback scope，将 production wrapper consumer v3_realtime_engine_n5_consumer_20260612 对 source N4 run 的 49 条 inbox refs / 43 条 checkpoint refs 纳入 stale rollback 或明确 supersede；保留 N4 run 和 N3 projection run。只改 rollback SQL/tests/report，不执行 rollback、不写 DB、不消费/update outbox/inbox/checkpoint、不进入 N4/N5/N6/voice/mobile/sim/position/trade。要求 rollback SQL 仍 hard-fail before first DELETE，继续阻断 N5 outbox delivered/delivering、N5 downstream refs、N6/user/sim/voice/mobile refs；删除范围仅 stale N5 run、N5 outbox/action facts/events/run，以及 stale N5 consumers 对 scoped N4 source 的 inbox/checkpoint。
```
