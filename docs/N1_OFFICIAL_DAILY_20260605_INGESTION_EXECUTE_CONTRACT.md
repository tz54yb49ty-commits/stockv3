# N1 Official Daily 20260605 Ingestion Execute Contract

```json
{
  "stage": "N1 official daily 20260605 ingestion execute contract",
  "layer_role": "N1_ingestion",
  "result": "DESIGN_PASS",
  "trade_date": "20260605",
  "source_batch_id": "official_daily_ingest_20260605_v1",
  "contract_batch_id": "official_daily_ingest_20260605_v1",
  "contract_source_version": "official_daily_ingest_20260605_v1",
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
  "execute_flags": [
    "--execute",
    "--user-confirmed",
    "--source-fetch-enabled",
    "--postgres-commit-enabled"
  ],
  "source_contract": {
    "stock": "Tushare daily + adj_factor proof",
    "index": "Mootdx primary plus Tushare BJ fallback",
    "board": "TDX/Mootdx board daily"
  },
  "source_probe_requirements": {
    "stock": "already probed read-only, unmapped=0",
    "index": "must complete full source coverage probe before production commit",
    "board": "must complete full source coverage probe before production commit",
    "active_stock_identity_scope": "A_STOCK:20260605 -> stock_identity_20260605_v1"
  },
  "future_write_scope": {
    "allowed_tables": [
      "common_ingest_batch",
      "common_quality_gate_result",
      "common_active_source_version",
      "stock_daily_bar_fact",
      "index_daily_bar_fact",
      "board_daily_bar_fact"
    ]
  },
  "implementation_status": {
    "guarded_nonproduction_runner_implemented": true,
    "production_commit_path_implemented": true,
    "source_fetch_adapter_routing": true,
    "source_bundle_validation": true,
    "postgres_commit_transaction": true,
    "cli_execute_pipeline_wired": true,
    "runner_readiness": "ready_for_final_gate",
    "execute_authorized": false,
    "next_required_step": "final_gate_user_confirmation_before_execute"
  },
  "rollback": {
    "path": "sql/N1_official_daily_20260605_ingestion_rollback.sql"
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
  "generated_at": "2026-06-07T22:02:49+08:00",
  "baseline": {
    "active_stock_identity_scope": {
      "scope_key": "A_STOCK:20260605",
      "source_version": "stock_identity_20260605_v1",
      "source_batch_id": "stock_identity_refresh_20260605_920211_v1",
      "previous_source_version": "stock_identity_20260604_v1",
      "row_count": 1
    }
  }
}
```
