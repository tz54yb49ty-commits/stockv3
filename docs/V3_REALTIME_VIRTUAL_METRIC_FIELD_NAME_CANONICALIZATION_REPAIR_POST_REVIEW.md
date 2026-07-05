# V3 Realtime Virtual Metric Field Name Canonicalization Repair Post Review

Result: `POST_REVIEW_PASS`

This was a read-only runtime-control review. It did not write the database, did not execute schema migration or rollback, did not execute wrapper/N3/N4/N5, did not modify scheduler, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## Repair Proof

- repair result: `REPAIR_PASS`
- DB column canonical: PostgreSQL lowercase identifiers
- `D/W/M/Q/Y` remain display/payload aliases only
- builder outputs lowercase canonical fields
- `trace_json.display_alias_to_db_column` exposes alias mapping
- writer canonicalizes alias before insert
- legacy writer path is preserved

Examples:

- `current_D_body_high -> current_d_body_high`
- `current_Y_virtual_amount -> current_y_virtual_amount`
- `previous_Y_amount -> previous_y_amount`

## Live Schema Proof

| table | rows | canonical columns present | mixed-case period columns |
| --- | ---: | ---: | ---: |
| `stock_action_confirmation_projection_metric` | `2914` | `56/56` | `0` |
| `index_action_confirmation_projection_metric` | `214` | `56/56` | `0` |
| `board_action_confirmation_projection_metric` | `499` | `56/56` | `0` |

The prior field-name compatibility blocker is resolved.

## Validation

- repair report validation: PASS
- runtime-control targeted tests:
  - `PYTHONPATH=src:scripts python3 -m unittest tests.test_v3_realtime_virtual_metric_builder tests.test_v3_realtime_virtual_metric_schema_contract`
  - result: `12 tests OK`
- live schema probe: PASS
- scheduler state: `not_loaded`
- wrapper/child process count: `0`

## Decision

Allow entering:

`V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT_PREFLIGHT_GATE`

This does not authorize execute.

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT_PREFLIGHT_GATE。

目标：为 20260612 新方案生成 N3 realtime virtual metric writer/runner contract + preflight + rollback artifacts，基于已保留的 1m source facts 和 N2/N4 context，写入 stock/index/board_action_confirmation_projection_metric 的新 canonical realtime virtual metric 字段；本 gate 不 execute、不写业务数据、不执行 wrapper/N4/N5、不消费/update outbox/inbox/checkpoint、不进入 N6/voice/mobile/sim/trade。

请定义 deterministic run_id、source scope、expected rows、auction/midday policy、D/W/M/Q/Y context 输入、idempotency、rollback SQL，并验证 targeted tests、JSON parse、rollback static check、git diff --check。
```
