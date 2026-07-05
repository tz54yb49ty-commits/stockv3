# N1 Official Daily 20260605 Ingestion Execute Blocked Report

```json
{
  "result": "BLOCKED",
  "blocker": "official_no_trade_manifest_mismatch",
  "commit_started": false,
  "writes_performed": false,
  "source_batch_id": "official_daily_ingest_20260605_v1",
  "source_versions": {
    "stock": "stock_daily_20260605_v1",
    "index": "index_daily_20260605_v1",
    "board": "board_daily_20260605_v1"
  },
  "expected_rows": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "actual_source_rows": {
    "stock": 5514,
    "index": 83,
    "board": 428,
    "total": 6025
  },
  "official_no_trade": {
    "expected_count": 12,
    "actual_count": 11,
    "expected_only": [
      "stock:SZ:000638"
    ],
    "actual_only": []
  },
  "db_post_check": {
    "stock_daily_bar_fact": 0,
    "index_daily_bar_fact": 0,
    "board_daily_bar_fact": 0,
    "common_ingest_batch": 0,
    "common_quality_gate_result": 0,
    "common_active_source_version": 0
  },
  "outbox_inbox_checkpoint_delta": {
    "outbox": 0,
    "inbox": 0,
    "checkpoint": 0
  },
  "rollback_needed": false,
  "rollback_sql": "sql/N1_official_daily_20260605_ingestion_rollback.sql",
  "next_required_gate": "N1 official daily 20260605 no-trade manifest correction for stock:SZ:000638"
}
```
