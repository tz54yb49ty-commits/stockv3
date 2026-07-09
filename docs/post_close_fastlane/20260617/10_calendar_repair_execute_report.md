# N1 Trade Calendar 20260617 Patch Preflight

result: `PREFLIGHT_PASS`
layer_role: `N1_ingestion`
trade_date: `20260617`
source_batch_id: `n1_trade_calendar_repair_20260617_v1`
source_version: `n1_trade_calendar_repair_20260617_v1`
rollback_sql_path: `sql/N1_20260617_trade_calendar_repair_rollback.sql`

## Calendar Row

```json
{
  "trade_date": "20260617",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260616",
  "next_trade_date": "20260618",
  "source": "tushare.trade_cal.patch",
  "source_batch_id": "n1_trade_calendar_repair_20260617_v1",
  "source_version": "n1_trade_calendar_repair_20260617_v1",
  "raw_payload": {
    "exchange": "SSE",
    "cal_date": "20260617",
    "is_open": 1,
    "pretrade_date": "20260616"
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
