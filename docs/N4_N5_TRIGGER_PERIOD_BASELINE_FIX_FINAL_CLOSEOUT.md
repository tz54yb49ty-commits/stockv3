# N4/N5 Trigger Period 与 Trigger Baseline 口径修复最终收口

结论：`CLOSEOUT_PASS`。

本次收口完成了 N4/N5 Trigger Period 与 Trigger Baseline 修复后的剩余闭环：旧 N5 fabricated formal periods 污染事实已 scoped rollback；fixed N4 replay 已登记 row-count 口径差异并 POST_REVIEW_PASS；fixed N5 replay 已基于 fixed N4 重放；N6 用户投影已基于 fixed N5 重建；N6 UI/raw message 默认 active lineage 已切到 fixed run，旧污染 run 只在 `show_all=1` 审计模式可见。

## Stale Rollback

- rollback post-review: `ROLLBACK_POST_REVIEW_PASS`
- reviewed stale N5 runs:
  - `v3_n5_action_replay_20260612_after_n4_state_machine_v3`
  - `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`
- live zero proof:
  - `common_action_run=0`
  - `common_action_event=0`
  - `N5 common_event_outbox=0`
  - `stock/index/board_action_fact=0/0/0`
- N4/N3 facts preserved.

## Fixed N4

- run_id: `v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`
- status: `passed`
- post-review: `POST_REVIEW_PASS`
- row-count alignment: `POST_REVIEW_PASS`
- rows:
  - `common_trigger_match=1187`
  - `common_trigger_state=93072`
  - `TriggerMatched:pending=1187`
  - `TriggerPendingMarketData:pending=28206`
  - `TriggerStateChanged:pending=19720`
- decontamination:
  - ordinary formal 30m contamination = `0`
  - formal period arrays containing 30m = `0`
  - ordinary formal missing proof TriggerMatched = `0`
  - known polluted `stock:SZ:002056 BUY:M,W,D` TriggerMatched = `0`
  - HINT 30m TriggerMatched = `1187`

## Fixed N5

- run_id: `v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1`
- status: `passed`
- source N4 run: `v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`
- rows:
  - `common_action_event=1187`
  - `stock/index/board_action_fact=965/154/68`
  - `ActionExecuted=276`
  - `ActionBlocked=911`
  - N5 outbox delivered/delivering = `0/0`
- formal period proof:
  - fabricated formal periods = `0`
  - non-HINT formal period payload count = `0`
  - HINT payload count = `1187`

## Fixed N6

- projection_run_id: `v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1`
- status: `passed`
- source action run: `v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1`
- rows:
  - `user_signal_projection=276`
  - `user_signal_card=276`
  - `user_notification_queue=0`
- ordinary user-message projection only contains `ActionExecuted=276`; `ActionBlocked/ActionSkipped` are not projected as user messages.

## UI Active Lineage

Updated:

- `src/ashare_v3/web/n6_user_app.py`
  - `V3_20260612_ACTIVE_N4_SOURCE_RUN_ID = v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`
  - `V3_20260612_ACTIVE_N5_SOURCE_RUN_ID = v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1`
- `tests/test_n6_user_app.py`
  - default N4/N5 raw message pages hide superseded 20260612 runs
  - `show_all=1` remains available for audit

## Rollback Registry

- stale N5 rollback: `sql/V3_20260612_stale_n5_trigger_period_fabrication_rollback.sql`
- fixed N4 rollback: `sql/V3_20260612_n4_trigger_period_baseline_fixed_replay_rollback.sql`
- fixed N5 rollback: `sql/V3_20260612_n5_replay_after_n4_trigger_period_baseline_fix_rollback.sql`
- fixed N6 rollback: `sql/V3_20260612_N6_USER_PROJECTION_AFTER_TRIGGER_PERIOD_BASELINE_FIX_ROLLBACK.sql`

All rollback SQL files passed static hard-fail / forbidden keyword checks.

## Validation

- targeted unittest: `251 OK`
- compileall: `PASS`
- JSON parse: `PASS`
- rollback static check: `PASS`
- git diff check: `PASS`

## Forbidden Scope

- did not consume/update N4/N5 outbox status
- did not start scheduler/worker
- did not read or modify old system
- did not touch voice/mobile/sim/position/order/real trade

Completion marker: `N4_N5_TRIGGER_PERIOD_BASELINE_FIX_COMPLETE`.
