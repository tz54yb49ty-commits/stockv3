# N1 Trade Calendar 20260609 Repair Preflight

result: `PREFLIGHT_PASS`
layer_role: `N1_ingestion`
trade_date: `20260609`
repair_mode: `missing_common_trade_calendar_row`
source_batch_id: `trade_calendar_20260609_repair_v1`
source_version: `trade_calendar_20260609_repair_v1`
rollback_sql_path: `sql/N1_20260609_trade_calendar_repair_rollback.sql`

## Current DB Baseline

```text
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1/32:5432
transaction_read_only=on
common_trade_calendar(20260609).total_count=0
common_trade_calendar(20260609).open_count=0
active_conflict_count=0
batch_conflict_count=0
quality_conflict_count=0
outbox/inbox/checkpoint=194930/96437/5188
```

## Calendar Row

```json
{
  "trade_date": "20260609",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260608",
  "next_trade_date": "20260610",
  "source": "tushare.trade_cal.patch",
  "source_batch_id": "trade_calendar_20260609_repair_v1",
  "source_version": "trade_calendar_20260609_repair_v1",
  "raw_payload": {
    "exchange": "SSE",
    "cal_date": "20260609",
    "is_open": 1,
    "pretrade_date": "20260608"
  }
}
```

## Source

Tushare available: `True`
fallback used: `False`

## Quality

P0/P1/P2: `0/0/0`

## Boundary

allowed write tables: `common_ingest_batch, common_trade_calendar, common_active_source_version, common_quality_gate_result`
daily fact writes: `false`
Parquet writes: `false`
outbox writes: `false`
downstream layers touched: `false`

Forbidden scope:

```text
stock/index/board daily facts
condition source / condition_* tables
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
worker
old system
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
```
