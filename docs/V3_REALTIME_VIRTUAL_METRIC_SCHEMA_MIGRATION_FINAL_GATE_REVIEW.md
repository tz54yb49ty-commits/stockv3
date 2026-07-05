# V3 Realtime Virtual Metric Schema Migration Final Gate Review

Result: `PASS`

This was a read-only runtime-control review. It did not execute the migration, did not write the database, did not execute wrapper/N3/N4/N5, did not execute rollback, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## Findings

- schema contract: `CONTRACT_PASS`
- schema preflight: `PREFLIGHT_PASS`
- migration SQL: additive `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
- target tables:
  - `stock_action_confirmation_projection_metric`
  - `index_action_confirmation_projection_metric`
  - `board_action_confirmation_projection_metric`
- N4/N5 business rules changed: `false`

Decision: allow entering the N3 schema migration user confirmation point.

## Live Schema Proof

Target DB:

- database: `ashare_v3`
- user: `ashare_v3_user`
- host: `127.0.0.1`
- port: `5432`

Required new realtime virtual metric columns: `56`.

Current live table state:

| table | rows | required present | required missing |
| --- | ---: | ---: | ---: |
| `stock_action_confirmation_projection_metric` | `2914` | `0` | `56` |
| `index_action_confirmation_projection_metric` | `214` | `0` | `56` |
| `board_action_confirmation_projection_metric` | `499` | `0` | `56` |

Index dependency columns exist on all three tables:

- `trade_date`
- `metric_minute_label`
- `metric_ready`

Missing column examples:

- `realtime_metric_schema_version`
- `metric_time_label`
- `source_time`
- `observed_at`
- `snapshot_id`
- `event_id`
- `quality_status`
- `session_kind`
- `period_source`
- `is_closed_1m`
- `is_auction_virtual`
- `midday_bridge_policy`
- `deterministic_pass_flags`
- `current_30m_virtual_amount`
- `current_120m_virtual_amount`
- `trace_json`

## Migration Command Draft

For the later N3 migration execute gate only:

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
import psycopg

DSN = 'host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user'
sql = Path('sql/039_v3_realtime_virtual_metric_schema_draft.sql').read_text()

with psycopg.connect(DSN) as conn:
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout = '5s'")
        cur.execute("SET statement_timeout = '120s'")
        cur.execute(sql)
    conn.commit()
PY
```

This command is not authorized for runtime_control execution.

## Rollback Proof

Rollback draft:

`sql/039_v3_realtime_virtual_metric_schema_rollback_draft.sql`

Static proof:

- default hard-fail before first column removal: PASS
- downstream guard checks `common_trigger_state` for `v3.realtime_virtual_metric.v1`
- no `TRUNCATE`
- no `CASCADE`
- rollback contains `DROP COLUMN IF EXISTS` by design, but is blocked by default and requires a separate rollback final gate

## Write Risk

The migration is schema-only, not a business data write. It will still take schema/table locks for `ALTER TABLE` and `CREATE INDEX`. Current target row counts are small: stock `2914`, index `214`, board `499`.

Keep this migration separate from runtime wrapper/N3/N4/N5 execution.

## Forbidden Scope Proof

- migration executed: `false`
- database written by this gate: `false`
- business data written: `false`
- wrapper/child manually executed: `false`
- scheduler modified: `false`
- rollback executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N4/N5 executed: `false`
- N6/voice/mobile/sim/trade entered: `false`

Scheduler/process check:

- `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`: `not_loaded`
- wrapper/child process count: `0`

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_REALTIME_VIRTUAL_METRIC_SCHEMA_MIGRATION_EXECUTE_GATE。

目标：按 runtime_control final gate approved command 执行 V3 realtime virtual metric additive schema migration，仅对 stock/index/board_action_confirmation_projection_metric 添加 N3 标准 realtime virtual metric 字段和索引。

要求：不写业务数据、不执行 wrapper/N3/N4/N5、不消费/update outbox/inbox/checkpoint、不进入 N6/voice/mobile/sim/trade。

执行后复核三张表新增字段 present=56/56、索引存在、业务 row count 未变化，并生成 migration execute/post-review artifacts。
```
