# N1 Official Daily 20260605 Ingestion Execute Report

```json
{
  "result": "EXECUTE_PASS",
  "source_batch_id": "official_daily_ingest_20260605_v1",
  "source_versions": {
    "stock": "stock_daily_20260605_v1",
    "index": "index_daily_20260605_v1",
    "board": "board_daily_20260605_v1"
  },
  "actual_rows": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "metadata_rows": {
    "common_ingest_batch": 1,
    "common_quality_gate_result": 31,
    "common_active_source_version": 3
  },
  "quality_summary": {
    "p0_failed": 0,
    "p0_passed": 28,
    "p1_warning": 3,
    "p2_warning": 0
  },
  "official_no_trade_correction_proof": {
    "manifest_count": 12,
    "includes_stock_SZ_000638": true,
    "stock_SZ_000638_writes_stock_daily_bar_fact": false,
    "all_manifest_fact_rows": 0
  },
  "stale_identity_proof": {
    "identity_key": "stock:SZ:300114",
    "writes_stock_daily_bar_fact": false
  },
  "forbidden_scope_proof": {
    "condition_source_rows": "0/0/0/0",
    "outbox_inbox_checkpoint_delta": "0/0/0",
    "parquet_written": false,
    "n2_n3_n4_n5_n6_touched": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "rollback": {
    "rollback_safe": true,
    "rollback_sql": "sql/N1_official_daily_20260605_ingestion_rollback.sql"
  },
  "next_gate": "runtime_control N1_OFFICIAL_DAILY_20260605_INGESTION_POST_REVIEW_GATE"
}
```
