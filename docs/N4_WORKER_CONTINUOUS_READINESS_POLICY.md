# N4 Worker Continuous Readiness Policy

Result: `POLICY_PASS`

This runtime-control policy gate was read-only. It did not execute N4, start a worker, write the database, consume or update outbox/inbox/checkpoint rows, execute rollback SQL, enter N5/N6, or touch trading/sim/position/voice/mobile paths.

## Current Evidence

The 20260611 N4 bounded smoke day-scope probe is closed out:

- Closeout: `CLOSEOUT_PASS`
- Smoke run id: `n4_worker_bounded_smoke_20260611_market_snapshot_updated_day_scope_probe`
- Consumer: `n4_trigger_worker_v1_bounded_smoke_20260611_day_scope_probe`
- Source run id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- Source event type: `MarketSnapshotUpdated`
- Source events selected: `2100`
- Asset distribution stock/index/board: `1890/83/127`
- N4 inbox/checkpoint: `2100/2100`
- N4 trigger state/match/outbox: `0/0/0`
- N3 source outbox remains pending: `2100`

Live read-only proof at `2026-06-11 16:24:03+08`:

```text
common_trigger_run.status=passed
P0/P1/P2=0/0/0
worker_started=false
N3 delivered/delivering=0/0
N4 runner process running=false
```

## Prerequisites

Completed:

- N4 state transition contract: `CONTRACT_PASS`
- N4 bounded smoke runner implementation post-review: `POST_REVIEW_PASS`
- N3 standard event source: `MarketSnapshotUpdated pending=2100`
- N4 context localization: `POST_REVIEW_PASS`
- N4 20260611 day-scope bounded consumption smoke: `CLOSEOUT_PASS`

Still required before scheduler or continuous activation:

- `n4_execute_report_metadata_alignment`: fix the report metadata caveat where generic `database_written=false` conflicts with N4 scoped write counts.
- `n4_20260611_current_real_trigger_semantic_smoke`: prove 20260611 real trigger semantics. The completed day-scope smoke was consumption-only and generated no `TriggerMatched`, `TriggerPendingMarketData`, or `TriggerStateChanged`.
- `n4_bounded_scheduler_contract`: define no-overlap, stop/unload, production consumer naming, status/report paths, rollback, and forbidden scope for bounded polling.
- Long-running worker remains deferred.

## Policy Decision

Continuous worker activation is not ready.

```text
continuous_worker_activation_ready=false
long_running_worker_allowed=false
bounded_scheduler_activation_ready=false
continue_with_bounded_run_once_expansion=true
```

Recommended route:

1. `N4_WORKER_BOUNDED_SMOKE_EXECUTE_REPORT_METADATA_ALIGNMENT_FIX_GATE`
2. `N4_20260611_TRIGGER_SEMANTIC_SMOKE_DRY_RUN_PREFLIGHT_GATE`
3. `N4_20260611_TRIGGER_SEMANTIC_SMOKE_EXECUTE_FINAL_GATE_REVIEW`
4. `N4_WORKER_BOUNDED_POLLING_SCHEDULER_CONTRACT_GATE`

Next recommended gate:

`N4_WORKER_BOUNDED_SMOKE_EXECUTE_REPORT_METADATA_ALIGNMENT_FIX_GATE`

## Forbidden Scope Proof

- N4 executed: `false`
- Worker started: `false`
- DB written by this gate: `false`
- Rollback SQL executed: `false`
- Outbox/inbox/checkpoint consumed or updated by this gate: `false`
- N5 entered: `false`
- N6 entered: `false`
- Delivery/push/voice/mobile touched: `false`
- Proposal/order/trade touched: `false`
- Sim/position/PnL/real trade touched: `false`
- Old system touched: `false`

## Next Prompt

```text
layer_role=N4_trigger

进入 N4_WORKER_BOUNDED_SMOKE_EXECUTE_REPORT_METADATA_ALIGNMENT_FIX_GATE。

目标：修复 N4 bounded smoke execute report 的 metadata caveat，使 execute report 的 database_written / side_effects / write_counts 对 scoped N4 run/quality/inbox/checkpoint 写入表达一致。不得执行 N4，不得启动 worker，不得写数据库，不得消费/update outbox/inbox/checkpoint，不得进入 N5/N6。

要求：更新 runner/report 逻辑和测试，确保 consumption-only bounded smoke 报告区分 scoped_n4_database_writes=true 与 worker_started=false / n3_outbox_updated=false / n5_n6_entered=false；验证 targeted tests、compileall、JSON parse、git diff。
```
