# N1 20260612 Trade Calendar Repair Dry-Run

result: `DRY_RUN_PASS`  
layer_role: `N1_ingestion`  
trade_date: `20260612`  
repair_mode: `scoped_calendar_repair_only`  
source_batch_id: `n1_trade_calendar_repair_20260612_v1`  
source_version: `n1_trade_calendar_repair_20260612_v1`  
scope_key: `SSE:20260612`

## Source Proof

```text
source=read_only_tushare_calendar_proof
fallback_used=false
weekday_only_proof_used=false
TUSHARE_TOKEN_PRESENT=true
token_length=56
20260612 is_open=true
20260612 pretrade_date=20260611
next_open_date=20260615
```

## Current DB Baseline

```text
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1/32:5432
transaction_read_only=on
common_trade_calendar(20260611)=1, open=1, next_trade_date=20260612
common_trade_calendar(20260612)=0, open=0
batch_conflict_count=0
active_conflict_count=0
quality_conflict_count=0
scoped_outbox/inbox/checkpoint_refs=0/0/0
scoped_N2/N3/N4/N5/N6_refs=0/0/0/0/0
```

## Planned Repair

```json
{
  "trade_date": "20260612",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260611",
  "next_trade_date": "20260615",
  "source": "read_only_tushare_calendar_proof",
  "source_batch_id": "n1_trade_calendar_repair_20260612_v1",
  "source_version": "n1_trade_calendar_repair_20260612_v1",
  "scope_key": "SSE:20260612"
}
```

Business insert rows: `1` in `common_trade_calendar`. Existing calendar rows are not updated or deleted.

The existing N1 calendar repair runner also requires metadata registration in:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
```

## Quality

P0/P1/P2: `0/0/0`

## Boundary

Allowed future write scope:

```text
common_trade_calendar
common_ingest_batch
common_quality_gate_result
common_active_source_version
```

Forbidden scope:

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

## Rollback

rollback_sql: `sql/N1_20260612_trade_calendar_repair_rollback.sql`

The rollback is scoped to `trade_date=20260612`, `source_batch_id=n1_trade_calendar_repair_20260612_v1`, `source_version=n1_trade_calendar_repair_20260612_v1`, and `scope_key=SSE:20260612`. It hard-fails before the first DELETE if N1 source facts, outbox/inbox/checkpoint, or N2-N6 refs exist.

## Next Gate

`N1_20260612_TRADE_CALENDAR_REPAIR_EXECUTE_USER_CONFIRMATION_GATE`
