# V3 Realtime Virtual Metric Schema Migration Runtime-Control Post-Review Recheck

Result: `BLOCKED`

This recheck did not write the database, did not execute wrapper/N3/N4/N5, did not execute rollback, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## What Passed

The physical migration was applied:

- execute result: `MIGRATION_PASS`
- reported post-review: `POST_REVIEW_PASS`
- target tables exist
- indexes exist:
  - `idx_stock_action_confirmation_metric_realtime_session`
  - `idx_index_action_confirmation_metric_realtime_session`
  - `idx_board_action_confirmation_metric_realtime_session`
- business row counts remained:
  - stock: `2914`
  - index: `214`
  - board: `499`

## Blocker

PostgreSQL lowercased the unquoted D/W/M/Q/Y identifiers.

The contract and builder tests still use mixed-case metric keys, for example:

- contract/builder key: `current_D_body_high`
- live DB column: `current_d_body_high`

Live schema proof:

| table | exact contract columns present | exact missing | lowercase-normalized present |
| --- | ---: | ---: | ---: |
| `stock_action_confirmation_projection_metric` | `26` | `30` | `56` |
| `index_action_confirmation_projection_metric` | `26` | `30` | `56` |
| `board_action_confirmation_projection_metric` | `26` | `30` | `56` |

This means the schema is physically present, but the contract is ambiguous for future writers. A writer that quotes metric dict keys as SQL identifiers would fail or miss the D/W/M/Q/Y fields. A writer that emits unquoted identifiers may work, but that is not a safe contract.

## Decision

- physical migration status: `APPLIED`
- clean schema closeout allowed: `false`
- realtime virtual metric business writer gate allowed: `false`

Next step is a field-name canonicalization repair, not another DB migration.

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_REALTIME_VIRTUAL_METRIC_FIELD_NAME_CANONICALIZATION_REPAIR_GATE。

目标：修复 realtime virtual metric schema/contract/builder/writer 字段命名兼容性，明确 DB column canonical 使用 PostgreSQL lowercase identifiers（current_d/current_w/current_m/current_q/current_y 等），并提供 metric payload/display alias 到 DB column 的映射；不得写业务数据，不执行 wrapper/N3/N4/N5，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。

验证 targeted tests、JSON parse、compileall、git diff --check。
```
