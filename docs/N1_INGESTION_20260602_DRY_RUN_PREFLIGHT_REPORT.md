# N1 Ingestion 20260602 Dry-Run / Preflight Report

```json
{
  "stage": "N1 official daily 20260602 ingestion dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_BLOCKED",
  "trade_date": "20260602",
  "for_trade_date": "20260603",
  "source_batch_id": "official_daily_ingest_20260602_v1",
  "source_versions": {
    "stock": "stock_daily_20260602_v1",
    "index": "index_daily_20260602_v1",
    "board": "board_daily_20260602_v1"
  },
  "read_only_baseline": {
    "calendar": {
      "trade_date": "20260602",
      "is_open": true,
      "prev_trade_date": "20260601",
      "next_trade_date": "20260603",
      "source_version": "trade_calendar_20260602_patch_v1",
      "row_count": 1
    },
    "next_calendar": {
      "trade_date": "20260603",
      "row_count": 0
    },
    "official_daily_rows": {
      "stock": 5507,
      "index": 83,
      "board": 428,
      "total": 6018
    },
    "batch_conflict": 1,
    "quality_conflict": 31,
    "active_conflict": 3
  },
  "expected_scope": {
    "stock_scope_basis": {
      "active_stock_identity": 5526,
      "daily_bar_rows": "TBD_after_Tushare_daily_adj_factor_source_probe"
    },
    "index_scope_basis": {
      "fixed_9_present": 9,
      "fixed_9_missing": [],
      "daily_bar_rows": "TBD_after_Mootdx_Tushare_BJ_source_probe"
    },
    "board_scope_basis": {
      "board_identity_total": 428,
      "industry_881": 127,
      "daily_bar_rows": "TBD_after_TDX_Mootdx_source_probe"
    }
  },
  "quality": {
    "p0_count": 1,
    "p1_count": 1,
    "p2_count": 0,
    "items": [
      {
        "gate_name": "calendar_ready",
        "severity": "P0",
        "status": "passed",
        "expected": "row=1,is_open=true,prev=20260601,next=20260603",
        "actual": {
          "trade_date": "20260602",
          "is_open": true,
          "prev_trade_date": "20260601",
          "next_trade_date": "20260603",
          "source_version": "trade_calendar_20260602_patch_v1",
          "row_count": 1
        }
      },
      {
        "gate_name": "official_daily_baseline_clean",
        "severity": "P0",
        "status": "failed",
        "expected": "daily/batch/quality/active conflicts=0",
        "actual": {
          "daily_rows": {
            "stock": 5507,
            "index": 83,
            "board": 428,
            "total": 6018
          },
          "batch": 1,
          "quality": 31,
          "active": 3
        }
      },
      {
        "gate_name": "tushare_source_ready",
        "severity": "P0",
        "status": "passed",
        "expected": "TUSHARE_TOKEN_PRESENT=true or approved fallback",
        "actual": {
          "TUSHARE_TOKEN_PRESENT": true,
          "fallback_approved": false
        }
      },
      {
        "gate_name": "tdx_mootdx_source_ready",
        "severity": "P0",
        "status": "passed",
        "expected": "TDX/Mootdx local source readable",
        "actual": {
          "tushare_token_present": true,
          "tushare_fallback_approved": false,
          "tdx_root": "/Volumes/MacRaid/tdxdata/tdx",
          "tdx_root_exists": true,
          "tdx_root_readable": true,
          "mootdx_import_present": true,
          "tdx_mootdx_local_source_available": true,
          "source_fetch_boundary": {
            "live_fetch_performed": false,
            "external_tushare_fetch_performed": false,
            "external_mootdx_fetch_performed": false
          },
          "p0_blockers": []
        }
      },
      {
        "gate_name": "next_calendar_detail_ready",
        "severity": "P1",
        "status": "warning",
        "expected": "common_trade_calendar(20260603)=1",
        "actual": {
          "trade_date": "20260603",
          "row_count": 0
        }
      }
    ]
  },
  "blockers": [
    "official_daily_baseline_clean"
  ],
  "rollback_sql_path": "sql/N1_official_daily_20260602_ingestion_rollback.sql",
  "side_effects": {
    "writes_database": false,
    "postgres_fact_written": false,
    "parquet_written": false,
    "condition_source_written": false,
    "executes_n1_n6": false,
    "enters_n2_n3_a1": false,
    "enters_n2_n3_n4_n5_n6": false,
    "consumes_outbox": false,
    "starts_worker": false,
    "delivery_or_notification": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "generated_at": "2026-06-03T04:20:10+08:00"
}
```
