# N1 Official Daily 20260601 Ingestion Dry-Run Report

```json
{
  "stage": "N1 official daily 20260601 ingestion dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_PASS_WITH_DEFERRED_FINAL_SOURCE_PROBE",
  "blocked": false,
  "trade_date": "20260601",
  "source_batch_id": "official_daily_ingest_20260601_v1",
  "source_versions": {
    "stock": "stock_daily_20260601_v1",
    "index": "index_daily_20260601_v1",
    "board": "board_daily_20260601_v1"
  },
  "calendar": {
    "trade_date": "20260601",
    "is_open": true,
    "prev_trade_date": "20260529",
    "next_trade_date": "20260602",
    "source_version": "trade_calendar_20260601_patch_v1",
    "row_count": 1
  },
  "baseline": {
    "current_daily_fact_rows": {
      "stock": 0,
      "index": 0,
      "board": 0,
      "total": 0
    },
    "batch_conflict": 0,
    "quality_conflict": 0,
    "active_conflict": 0
  },
  "source_probe_summary": {
    "stock": {
      "probe_result": "STOCK_PROBE_PASS",
      "tushare_daily_count": 5508,
      "adj_factor_count": 5525,
      "matched_identity_count": 5508,
      "unmapped_count": 0,
      "official_no_trade_manifest_count": 17,
      "duplicate_daily_ts_code_count": 0
    },
    "index": {
      "expected_rows": 83,
      "probe_result": "DEFERRED_TO_FINAL_GATE"
    },
    "board": {
      "expected_rows": 428,
      "probe_result": "DEFERRED_TO_FINAL_GATE"
    }
  },
  "expected_rows": {
    "stock_daily_bar_fact": 5508,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6019
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 1,
    "p2_count": 0,
    "items": [
      {
        "gate_name": "calendar_ready",
        "severity": "P0",
        "status": "passed",
        "expected": "row=1,is_open=true,prev=20260529,next=20260602",
        "actual": "row=1,is_open=True,prev=20260529,next=20260602"
      },
      {
        "gate_name": "daily_fact_absent_before_execute",
        "severity": "P0",
        "status": "passed",
        "expected": 0,
        "actual": 0
      },
      {
        "gate_name": "metadata_conflicts_absent",
        "severity": "P0",
        "status": "passed",
        "expected": 0,
        "actual": 0
      },
      {
        "gate_name": "stock_source_identity_coverage",
        "severity": "P0",
        "status": "passed",
        "expected": "unmapped=0",
        "actual": "unmapped=0"
      },
      {
        "gate_name": "index_board_source_probe_deferred_to_final_gate",
        "severity": "P1",
        "status": "warning",
        "expected": "full source coverage before production commit",
        "actual": "deferred"
      }
    ]
  },
  "side_effects": {
    "read_only_database_checks": true,
    "external_stock_source_probe": true,
    "will_execute_sql": false,
    "writes_performed": false,
    "postgres_fact_written": false,
    "parquet_written": false,
    "updates_active_source_version": false,
    "writes_outbox": false,
    "enters_n2_n3_n4_n5_n6": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "generated_at": "2026-06-02T08:32:38+08:00"
}
```
