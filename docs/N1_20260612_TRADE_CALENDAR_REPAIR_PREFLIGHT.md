# N1 20260612 Trade Calendar Repair Preflight

result: `PREFLIGHT_PASS`  
layer_role: `N1_ingestion`  
trade_date: `20260612`  
source_batch_id: `n1_trade_calendar_repair_20260612_v1`  
source_version: `n1_trade_calendar_repair_20260612_v1`  
scope_key: `SSE:20260612`  
rollback_sql: `sql/N1_20260612_trade_calendar_repair_rollback.sql`

## Calendar Proof

```text
20260611 calendar exists=true
20260611 is_open=true
20260611 next_trade_date=20260612
20260612 common_trade_calendar rows=0
Tushare source proof=PASS
fallback_used=false
20260612 is_open=true
20260612 prev_trade_date=20260611
20260612 next_trade_date=20260615
```

## Current Baseline

```text
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1/32:5432
transaction_read_only=on
batch_conflict=0
active_conflict=0
quality_conflict=0
scoped_outbox/inbox/checkpoint_refs=0/0/0
scoped_N2/N3/N4/N5/N6_refs=0/0/0/0/0
```

## Planned Write Scope

Business row:

```text
common_trade_calendar: 1 row for 20260612
```

Required N1 metadata:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
```

No existing calendar rows are updated or deleted.

## Quality

P0/P1/P2: `0/0/0`

## Rollback

Rollback is scoped to:

```text
trade_date=20260612
source_batch_id=n1_trade_calendar_repair_20260612_v1
source_version=n1_trade_calendar_repair_20260612_v1
scope_key=SSE:20260612
```

Rollback hard-fails before the first DELETE if any N1 source facts, outbox/inbox/checkpoint refs, or N2-N6 refs exist.

## Forbidden Scope

```text
stock/index/board daily facts
stock_daily_basic / stock_financial_metrics_fact
index_membership_fact / board_membership_fact
condition_* tables
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
Parquet
worker
old system
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
```

## Execute Gate

Allowed next gate:

```text
N1_20260612_TRADE_CALENDAR_REPAIR_EXECUTE_USER_CONFIRMATION_GATE
```
