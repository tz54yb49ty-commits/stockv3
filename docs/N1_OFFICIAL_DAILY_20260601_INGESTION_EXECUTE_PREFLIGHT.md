# N1 Official Daily 20260601 Ingestion Execute Preflight

```json
{
  "stage": "N1 official daily 20260601 ingestion execute preflight",
  "layer_role": "N1_ingestion",
  "result": "PREFLIGHT_PASS",
  "blocked": false,
  "production_execute_allowed": true,
  "production_execute_blockers": [],
  "trade_date": "20260601",
  "source_batch_id": "official_daily_ingest_20260601_v1",
  "source_versions": {
    "stock": "stock_daily_20260601_v1",
    "index": "index_daily_20260601_v1",
    "board": "board_daily_20260601_v1"
  },
  "execute_authorized": false,
  "final_gate_required": true,
  "final_execute_gate_allowed": true,
  "runner_readiness": "ready_for_final_gate",
  "execute_runner": {
    "implemented": true,
    "runner_readiness": "ready_for_final_gate",
    "final_execute_gate_allowed": true,
    "execute_authorized": false
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
    "active_conflict": 0
  },
  "expected_rows": {
    "stock_daily_bar_fact": 5508,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6019
  },
  "source_readiness": {
    "stock": {
      "probe_result": "STOCK_PROBE_PASS",
      "tushare_daily_count": 5508,
      "adj_factor_count": 5525,
      "matched_identity_count": 5508,
      "unmapped_count": 0,
      "official_no_trade_manifest_count": 17,
      "duplicate_daily_ts_code_count": 0
    },
    "index": "FULL_PROBE_PASS",
    "board": "FULL_PROBE_PASS"
  },
  "index_board_probe": {
    "stage": "N1 official daily 20260601 index/board source probe",
    "layer_role": "N1_ingestion",
    "mode": "full",
    "trade_date": "20260601",
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
    "full_probe_required_before_production_execute": false,
    "quality": {
      "p0_count": 0,
      "p1_count": 0,
      "p2_count": 0,
      "p0_items": [],
      "p1_items": []
    },
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
    "generated_at": "2026-06-02T08:22:29+08:00"
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
      }
    ]
  },
  "rollback": {
    "path": "sql/N1_official_daily_20260601_ingestion_rollback.sql",
    "rollback_safe_before_execute": true
  },
  "execute_command_template": "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260601_once.py --trade-date 20260601 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled",
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
  "generated_at": "2026-06-02T08:32:38+08:00"
}
```
