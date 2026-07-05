# N1 20260608 Stock Identity 920206 Repair Dry-Run

Result: `DRY_RUN_PASS`

Layer role: `N1_ingestion`

This gate only prepares a scoped identity repair for `920206.BJ`. It did not execute, write PostgreSQL, execute rollback SQL, enter N2-N6, consume/update outbox/inbox/checkpoint, start a worker, pull realtime quotes, touch old system, or touch trading/sim/position/PnL paths.

## Source Proof

- target ts_code: `920206.BJ`
- canonical identity_key: `stock:BJ:920206`
- stock_basic: `1` row
- name: `彩客科技`
- exchange: `BSE` -> canonical `BJ`
- market: `北交所`
- list_date: `20260608`
- daily 20260608: `1` row
- daily_basic 20260608: `1` row
- adj_factor 20260608: `1` row
- bak_daily 20260608: `1` row
- suspend_d 20260608: `1` intraday suspend source row, identity repair remains valid

## Baseline

- target identity rows: `0`
- duplicate identity_key: `0`
- duplicate ts_code: `0`
- batch conflict: `0`
- quality conflict: `0`
- active scope conflict: `0`
- daily fact refs: `0`
- condition refs: `0`
- outbox/inbox/checkpoint refs: `0/0/0`
- N2/N3/N4/N5/N6 refs: `0/0/0/0/0`

Previous active stock_identity:

- `A_STOCK:20260605 -> stock_identity_20260605_v1`

## Planned Repair

Planned rows:

- `stock_identity=1`
- `common_ingest_batch=1`
- `common_active_source_version=1`
- `common_quality_gate_result=8`

The repair is scoped to `stock:BJ:920206` only. It does not refresh the full stock identity universe, does not modify index/board identity, does not modify daily facts, and does not execute condition source.

Allowed future write tables:

- `common_ingest_batch`
- `stock_identity`
- `common_active_source_version`
- `common_quality_gate_result`

Forbidden:

- stock/index/board daily facts
- condition source facts
- outbox/inbox/checkpoint
- N2/N3/N4/N5/N6
- worker
- realtime quotes
- old system
- proposal/order/trade/sim/position/PnL/real trade

## Quality

`P0/P1/P2 = 0/0/0`

## Rollback

Rollback draft:

`sql/N1_20260608_stock_identity_920206_repair_rollback.sql`

The rollback is hard-failed before DELETE and scoped to:

- `source_batch_id=stock_identity_refresh_20260608_920206_v1`
- `source_version=stock_identity_20260608_v1`
- `identity_key=stock:BJ:920206`
- `ts_code=920206.BJ`
- `scope_key=A_STOCK:20260608`
