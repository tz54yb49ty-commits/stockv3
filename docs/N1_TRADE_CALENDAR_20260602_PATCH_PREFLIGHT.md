# N1 Trade Calendar 20260602 Patch Preflight

result: `PREFLIGHT_PASS`
layer_role: `N1_ingestion`
trade_date: `20260602`
source_batch_id: `trade_calendar_20260602_patch_v1`
source_version: `trade_calendar_20260602_patch_v1`
rollback_sql_path: `sql/N1_trade_calendar_20260602_patch_rollback.sql`

## Calendar Row

```json
{
  "trade_date": "20260602",
  "exchange": "SSE",
  "is_open": true,
  "prev_trade_date": "20260601",
  "next_trade_date": "20260603",
  "source": "manual.calendar_patch",
  "source_batch_id": "trade_calendar_20260602_patch_v1",
  "source_version": "trade_calendar_20260602_patch_v1",
  "raw_payload": {
    "patch_source": "previous_calendar_next_trade_date",
    "evidence": {
      "trade_date": "20260601",
      "exchange": "SSE",
      "is_open": true,
      "prev_trade_date": "20260529",
      "next_trade_date": "20260602",
      "source": "tushare.trade_cal.patch",
      "source_batch_id": "trade_calendar_20260601_patch_v1",
      "source_version": "trade_calendar_20260601_patch_v1",
      "updated_at": "2026-06-02 06:49:19.928425+08:00"
    },
    "quality_risk": "manual fallback used because Tushare trade_cal was unavailable"
  }
}
```

## Source

Tushare available: `False`
fallback used: `True`

## Quality

P0/P1/P2: `0/0/1`

## Boundary

allowed write tables: `common_ingest_batch, common_trade_calendar, common_active_source_version, common_quality_gate_result`
daily fact writes: `false`
Parquet writes: `false`
outbox writes: `false`
downstream layers touched: `false`
