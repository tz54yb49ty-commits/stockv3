# V3 20260612 Pre-New-Plan Runtime Messages Cleanup Preflight

Result: `DRY_RUN_PREFLIGHT_PASS`

This gate is read-only with respect to the database. It generated cleanup/rollback artifacts and refreshed live counts, but did not execute cleanup, did not write DB rows, did not execute rollback, did not modify scheduler, and did not enter N6.

## Scheduler Proof

The required stop gate is complete:

- stop report: `docs/V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_SCHEDULER_STOP_OR_PAUSE_REPORT.json`
- target label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- expected state: `not_loaded`
- wrapper/child process count: `0`

## Live Target Counts

N6/user refs:

- `user_projection_run=0`
- `user_signal_projection=0`
- `user_signal_card=0`
- `user_notification_queue=0`

N5 scope:

- `common_action_run=3`
- `common_action_quality_item=0`
- `stock_action_fact=2436`
- `index_action_fact=0`
- `board_action_fact=1`
- `common_action_event=2437`
- `common_event_outbox=2437`
- `common_event_inbox=2437`
- `common_event_consumer_checkpoint=2402`

N4 scope:

- `common_trigger_run=4`
- `common_trigger_quality_item=36`
- `common_trigger_state=4865`
- `common_trigger_match=3249`
- `common_event_outbox=4865`
- `common_event_inbox=8328`
- `common_event_consumer_checkpoint=8328`
- downstream N5 action run refs before cleanup: `3`

N3 derived scope:

- standard B1 outbox runs: `11`
- trace-aligned B2 runs: `4`
- standard quality rows: `110`
- trace B2 quality rows: `28`
- standard stock/index/board snapshots: `20592/913/1397`
- `MarketSnapshotUpdated` outbox rows: `22902`
- trace B2 stock/index/board projection rows: `7488/332/508`
- downstream inbox/checkpoint refs from scoped N3 standard outbox: `8328/8328`

The downstream N3 refs are expected before N4 cleanup. The cleanup SQL removes N4 consumers first, then asserts these refs are zero before deleting N3 derived rows.

## Cleanup SQL Proof

Cleanup SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql`

Proof:

- default hard-fail before first executable mutation
- requires explicit session setting `ashare_v3.allow_v3_20260612_pre_new_plan_cleanup=true`
- backs up scoped rows to `common_runtime_cleanup_backup` before deletes
- deletes in reverse dependency order: N5 -> N4 -> N3 derived
- guards N6/user/sim/virtual refs
- guards N5 outbox downstream refs
- asserts N5 refs are zero before N4 cleanup proceeds
- asserts N3 downstream refs are zero before N3 derived cleanup proceeds
- no `DROP`, `TRUNCATE`, or `CASCADE`
- no minute-bar, preload, subscription, pull-plan, N1, or N2 delete scope

## Rollback SQL Proof

Rollback SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup_rollback.sql`

Proof:

- default hard-fail before first restore mutation
- requires explicit session setting `ashare_v3.allow_v3_20260612_pre_new_plan_cleanup_rollback=true`
- restores rows from `common_runtime_cleanup_backup`
- no `DROP`, `TRUNCATE`, or `CASCADE`

## Decision

`DRY_RUN_PREFLIGHT_PASS`

This gate allows runtime_control to do a cleanup execute final gate review. It does not authorize cleanup execution.

Next gate:

```text
layer_role=runtime_control。

进入 V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_EXECUTE_FINAL_GATE_REVIEW。

目标：
只读复核 20260612 新方案前 runtime derived messages cleanup contract/preflight/rollback 是否允许进入 cleanup 用户确认点。
本 gate 不执行 cleanup、不写数据库、不执行 rollback、不启动 scheduler、不手动执行 wrapper/N3/N4/N5、不消费/update outbox/inbox/checkpoint、不进入 N6/voice/mobile/sim/trade。

依据：
- docs/V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_CONTRACT.md/json
- docs/V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_PREFLIGHT.md/json
- docs/V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_SCHEDULER_STOP_OR_PAUSE_REPORT.md/json
- sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql
- sql/V3_20260612_pre_new_plan_runtime_messages_cleanup_rollback.sql

请复核 scheduler not_loaded、N6 refs=0、N5/N4/N3 scoped counts、reverse cleanup order、backup policy、cleanup SQL hard-fail、rollback SQL hard-fail、forbidden preserved scope，并输出 PASS/BLOCKED 与 allowed cleanup command draft。
```
