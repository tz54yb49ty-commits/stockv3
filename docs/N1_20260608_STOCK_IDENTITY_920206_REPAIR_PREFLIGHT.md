# N1 20260608 Stock Identity 920206 Repair Preflight

Result: `PREFLIGHT_PASS`

Execute authorized: `false`

Final execute gate allowed: `false`

Runner readiness: `contract_ready_execute_runner_not_implemented`

## Target

- `trade_date=20260608`
- `source_batch_id=stock_identity_refresh_20260608_920206_v1`
- `source_version=stock_identity_20260608_v1`
- `previous_source_version=stock_identity_20260605_v1`
- `active_scope_key=A_STOCK:20260608`
- `identity_key=stock:BJ:920206`
- `ts_code=920206.BJ`

## Source Proof

Tushare proof is present and consistent:

- stock_basic present: `true`
- list_date: `20260608`
- name: `彩客科技`
- market: `北交所`
- daily present: `true`
- daily_basic present: `true`
- adj_factor present: `true`
- bak_daily present: `true`
- canonical mapping: `920206.BJ -> stock:BJ:920206`

## Baseline

- target identity rows: `0`
- duplicate identity_key: `0`
- duplicate ts_code: `0`
- batch conflict: `0`
- quality conflict: `0`
- active scope conflict: `0`
- downstream refs: `0`

## Planned Write Scope

Allowed future write tables:

- `common_ingest_batch`
- `stock_identity`
- `common_active_source_version`
- `common_quality_gate_result`

Forbidden:

- daily facts
- condition source facts
- outbox/inbox/checkpoint
- N2/N3/N4/N5/N6
- Parquet
- old system
- proposal/order/trade/sim/position/PnL/real trade

## Planned Rows

- `stock_identity=1`
- `common_ingest_batch=1`
- `common_active_source_version=1`
- `common_quality_gate_result=8`

## Quality

`P0/P1/P2 = 0/0/0`

## Rollback

Rollback SQL:

`sql/N1_20260608_stock_identity_920206_repair_rollback.sql`

The rollback is hard-failed before DELETE, scoped to this identity repair only, and does not touch daily facts, condition source, N2-N6, or outbox/inbox/checkpoint.

## Execute Candidate

```bash
PYTHONPATH=src python3 scripts/run_stock_identity_920206_20260608_repair_once.py \
  --trade-date 20260608 \
  --execute \
  --user-confirmed
```

This command is only the required command shape for a future runner. The scoped `920206` execute runner is not implemented in this gate, so execute final gate is not allowed yet.

Next gate:

`N1_20260608_STOCK_IDENTITY_920206_REPAIR_RUNNER_IMPLEMENTATION_GATE`
