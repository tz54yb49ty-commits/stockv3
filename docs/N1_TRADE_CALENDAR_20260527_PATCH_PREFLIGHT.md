# N1 Trade Calendar 20260527 Patch Preflight

result: `PREFLIGHT_PASS`
layer_role: `N1_ingestion`
trade_date: `20260527`
source_batch_id: `trade_calendar_20260527_patch_v1`
source_version: `trade_calendar_20260527_patch_v1`

## Calendar Row

```json
{
  "trade_date": "20260527",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260526",
  "next_trade_date": "20260528",
  "source": "tushare.trade_cal.patch",
  "source_batch_id": "trade_calendar_20260527_patch_v1",
  "source_version": "trade_calendar_20260527_patch_v1",
  "raw_payload": {
    "exchange": "SSE",
    "cal_date": "20260527",
    "is_open": 1,
    "pretrade_date": "20260526"
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
