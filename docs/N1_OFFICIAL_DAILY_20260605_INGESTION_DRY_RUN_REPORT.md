# N1 Official Daily 20260605 Ingestion Dry-Run Report

```json
{
  "stage": "N1 official daily 20260605 ingestion dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_PASS_WITH_DEFERRED_FINAL_SOURCE_PROBE",
  "blocked": false,
  "trade_date": "20260605",
  "source_batch_id": "official_daily_ingest_20260605_v1",
  "source_versions": {
    "stock": "stock_daily_20260605_v1",
    "index": "index_daily_20260605_v1",
    "board": "board_daily_20260605_v1"
  },
  "calendar": {
    "trade_date": "20260605",
    "is_open": true,
    "prev_trade_date": "20260604",
    "next_trade_date": "20260608",
    "source_version": "trade_calendar_20260605_patch_v1",
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
    "active_conflict": 0,
    "active_stock_identity_scope": {
      "scope_key": "A_STOCK:20260605",
      "source_version": "stock_identity_20260605_v1",
      "source_batch_id": "stock_identity_refresh_20260605_920211_v1",
      "previous_source_version": "stock_identity_20260604_v1",
      "row_count": 1
    }
  },
  "source_probe_summary": {
    "stock": {
      "probe_result": "STOCK_PROBE_PASS",
      "tushare_daily_count": 5514,
      "adj_factor_count": 5526,
      "matched_identity_count": 5514,
      "unmapped_count": 0,
      "official_no_trade_manifest_count": 12,
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
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
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
        "expected": "row=1,is_open=true,prev=20260604,next=20260608",
        "actual": "row=1,is_open=True,prev=20260604,next=20260608"
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
      },
      {
        "gate_name": "active_stock_identity_scope_ready",
        "severity": "P0",
        "status": "passed",
        "expected": {
          "scope_key": "A_STOCK:20260605",
          "source_version": "stock_identity_20260605_v1",
          "source_batch_id": "stock_identity_refresh_20260605_920211_v1"
        },
        "actual": {
          "scope_key": "A_STOCK:20260605",
          "source_version": "stock_identity_20260605_v1",
          "source_batch_id": "stock_identity_refresh_20260605_920211_v1",
          "previous_source_version": "stock_identity_20260604_v1",
          "row_count": 1
        },
        "details": {
          "blocking_execute": false,
          "lineage_guard": "official_daily_20260605_active_stock_identity"
        }
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
  "generated_at": "2026-06-07T22:02:49+08:00"
}
```
