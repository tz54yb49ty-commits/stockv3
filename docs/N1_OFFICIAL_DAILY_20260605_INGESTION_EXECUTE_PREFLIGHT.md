# N1 Official Daily 20260605 Ingestion Execute Preflight

```json
{
  "stage": "N1 official daily 20260605 ingestion execute preflight",
  "layer_role": "N1_ingestion",
  "result": "PREFLIGHT_PASS",
  "blocked": false,
  "production_execute_allowed": true,
  "production_execute_blockers": [],
  "trade_date": "20260605",
  "source_batch_id": "official_daily_ingest_20260605_v1",
  "source_versions": {
    "stock": "stock_daily_20260605_v1",
    "index": "index_daily_20260605_v1",
    "board": "board_daily_20260605_v1"
  },
  "execute_authorized": false,
  "final_gate_required": true,
  "final_execute_gate_allowed": true,
  "runner_readiness": "ready_for_final_gate",
  "execute_runner": {
    "implemented": true,
    "runner_readiness": "ready_for_final_gate",
    "final_execute_gate_allowed": true,
    "execute_authorized": false,
    "production_commit_path_implemented": true
  },
  "execute_runner_implemented": true,
  "source_fetch_implemented": true,
  "postgres_commit_implemented": true,
  "execute_flags_seen": {
    "execute": true,
    "user_confirmed": true,
    "source_fetch_enabled": true,
    "postgres_commit_enabled": true
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
  "expected_rows": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "source_readiness": {
    "stock": {
      "probe_result": "STOCK_PROBE_PASS",
      "tushare_daily_count": 5514,
      "adj_factor_count": 5526,
      "matched_identity_count": 5514,
      "unmapped_count": 0,
      "official_no_trade_manifest_count": 12,
      "duplicate_daily_ts_code_count": 0
    },
    "index": "FULL_PROBE_PASS",
    "board": "FULL_PROBE_PASS"
  },
  "index_board_probe": {
    "stage": "N1 official daily 20260605 index/board source probe",
    "layer_role": "N1_ingestion",
    "mode": "full",
    "trade_date": "20260605",
    "result": "FULL_PROBE_PASS",
    "selected_counts": {
      "index": 83,
      "board": 428
    },
    "source_counts": {
      "index": 83,
      "board": 428
    },
    "missing_counts": {
      "index": 0,
      "board": 0
    },
    "expected_full_counts": {
      "index": 83,
      "board": 428
    },
    "source_breakdown": {
      "index_mootdx": 81,
      "index_tushare_bj_fallback": 2,
      "board_mootdx": 428
    },
    "quality": {
      "p0_count": 0,
      "p1_count": 0,
      "p2_count": 0,
      "p0_items": [],
      "p1_items": [],
      "p2_items": []
    },
    "side_effects": {
      "read_only_database_checks": true,
      "writes_performed": false,
      "postgres_fact_written": false,
      "parquet_written": false,
      "condition_source_written": false,
      "enters_n2_n3_n4_n5_n6": false,
      "worker_started": false,
      "old_system_touched": false,
      "real_trading": false
    }
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 0,
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
  "rollback": {
    "path": "sql/N1_official_daily_20260605_ingestion_rollback.sql",
    "rollback_safe_before_execute": true
  },
  "execute_command_template": "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260605_once.py --trade-date 20260605 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled",
  "side_effects": {
    "read_only_database_checks": true,
    "external_stock_source_probe": false,
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
  "generated_at": "2026-06-07T22:02:49+08:00",
  "stock_source_probe": {
    "stage": "N1 official daily 20260605 stock source probe",
    "layer_role": "N1_ingestion",
    "trade_date": "20260605",
    "result": "STOCK_PROBE_PASS",
    "stock_source": {
      "tushare_daily_count": 5514,
      "adj_factor_count": 5526,
      "matched_identity_count": 5514,
      "unmapped_count": 0,
      "unmapped_sample": [],
      "unmapped_reason": null,
      "adj_minus_daily_active_identity_count": 12,
      "duplicate_daily_ts_code_count": 0,
      "stock_identity_refresh_required": false,
      "post_identity_refresh_expected_matched_identity_count": 5514,
      "post_identity_refresh_expected_unmapped_count": 0
    },
    "quality": {
      "p0_count": 0,
      "p1_count": 0,
      "p2_count": 0,
      "p0_items": [],
      "p1_items": [],
      "p2_items": []
    },
    "side_effects": {
      "read_only_database_checks": true,
      "external_stock_source_probe": true,
      "writes_performed": false,
      "postgres_fact_written": false,
      "parquet_written": false,
      "condition_source_written": false,
      "enters_n2_n3_n4_n5_n6": false,
      "worker_started": false,
      "old_system_touched": false,
      "real_trading": false
    }
  }
}
```
