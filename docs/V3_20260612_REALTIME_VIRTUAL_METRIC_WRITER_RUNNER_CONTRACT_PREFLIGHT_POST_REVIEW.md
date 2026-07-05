# V3 20260612 Realtime Virtual Metric Writer Runner Contract Preflight Post Review

Result: `POST_REVIEW_PASS`

This was a read-only runtime-control review. It did not write the database, did not execute wrapper/N3/N4/N5, did not modify scheduler, did not execute rollback, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## Contract Proof

- contract: `CONTRACT_PASS`
- dry-run: `DRY_RUN_PASS`
- preflight: `PREFLIGHT_PASS`
- `P0/P1/P2 = 0/1/0`
- P1 note: `execute_runner_implementation_required_before_execute_final_gate`
- `execute_ready=false`

Deterministic run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

Expected rows:

- total: `100`
- `B_BUY=76`
- `S_SELL=24`

## Scope Policy

Source facts retained:

- stock 1m: `705120`
- index 1m: `90144`
- board 1m: `56832`

Policies:

- auction: `09:31` label can be N3-owned auction virtual metric
- midday: `13:00` bridges missing `11:30`; no fabricated `11:30` row
- higher period context: N2 `period_trigger_baseline_json` or reviewed localized N4 context copy
- DB canonical fields: lowercase PostgreSQL identifiers
- display/payload aliases: `D/W/M/Q/Y` only as aliases

## Future Write Scope

Allowed only after a later execute final gate:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`

Forbidden:

- event outbox/inbox/checkpoint mutation
- N4/N5/N6 writes
- voice/mobile/sim/trade

## Rollback Proof

Rollback SQL:

`sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql`

Static proof:

- hard-fail before first `DELETE`
- scoped by target `projection_run_id`
- guards event infra
- guards N4/N5/N6/user refs
- no `DROP/TRUNCATE/CASCADE`
- rollback not executed

## Decision

Contract/preflight is registered, but execute is not allowed yet.

Reason: the runner implementation is still required. The preflight intentionally carries:

`execute_runner_implementation_required_before_execute_final_gate`

Allow entering:

`V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_IMPLEMENTATION_GATE`

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_IMPLEMENTATION_GATE。

目标：实现 20260612 新方案 N3 realtime virtual metric writer/runner，使其基于已保留 1m source facts 和 N2/N4 context 生成 100 条 B_BUY/S_SELL action-confirmation projection metric rows，写入 lowercase canonical realtime virtual metric 字段；默认 dry-run/plan-only，execute 必须 --execute --user-confirmed；不得执行本 gate 的业务写库，不启动 scheduler，不进入 N4/N5/N6，不消费/update outbox/inbox/checkpoint。

验证 TDD targeted tests、compileall、JSON parse、rollback static check、git diff --check，并输出 IMPLEMENTATION_PASS/BLOCKED。
```
