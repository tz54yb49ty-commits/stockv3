# N1 Trade Calendar 20260612 Patch Preflight

result: `PREFLIGHT_BLOCKED`
layer_role: `N1_ingestion`
trade_date: `20260612`
source_batch_id: `n1_trade_calendar_repair_20260612_v1`
source_version: `n1_trade_calendar_repair_20260612_v1`
rollback_sql_path: `sql/N1_20260612_trade_calendar_repair_rollback.sql`

## Calendar Row

```json
{
  "trade_date": "20260612",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260611",
  "next_trade_date": "20260615",
  "source": "tushare.trade_cal.patch",
  "source_batch_id": "n1_trade_calendar_repair_20260612_v1",
  "source_version": "n1_trade_calendar_repair_20260612_v1",
  "raw_payload": {
    "exchange": "SSE",
    "cal_date": "20260612",
    "is_open": 1,
    "pretrade_date": "20260611"
  }
}
```

## Source

Tushare available: `True`
fallback used: `False`

## Quality

P0/P1/P2: `5/0/0`

## Boundary

allowed write tables: `common_ingest_batch, common_trade_calendar, common_active_source_version, common_quality_gate_result`
daily fact writes: `false`
Parquet writes: `false`
outbox writes: `false`
downstream layers touched: `false`
