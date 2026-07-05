# N1 20260608 Stock Identity 920206 Repair Execute Preflight

```json
{
  "stage": "N1 stock_identity refresh 20260608 execute preflight",
  "layer_role": "N1_ingestion",
  "result": "PREFLIGHT_PASS",
  "blocked": false,
  "blockers": [],
  "trade_date": "20260608",
  "source_batch_id": "stock_identity_refresh_20260608_920206_v1",
  "source_version": "stock_identity_20260608_v1",
  "previous_source_version": "stock_identity_20260605_v1",
  "active_scope_key": "A_STOCK:20260608",
  "runner_readiness": "ready_for_final_gate",
  "final_execute_gate_allowed": true,
  "execute_authorized": false,
  "baseline": {
    "trade_date": "20260608",
    "target_stock_identity_rows": 0,
    "target_ts_code_rows": 0,
    "source_version_identity_rows": 0,
    "batch_conflict_count": 0,
    "quality_conflict_count": 0,
    "existing_active_scope_key_count": 0,
    "latest_previous_active_source_version": "stock_identity_20260605_v1",
    "latest_previous_active_source_batch_id": "stock_identity_refresh_20260605_920211_v1",
    "daily_fact_rows": {
      "stock": 0,
      "index": 0,
      "board": 0
    },
    "condition_source_rows": {
      "stock_daily_basic": 0,
      "stock_financial": 0,
      "index_membership": 0,
      "board_membership": 0
    },
    "event_counts": {
      "outbox": 198944,
      "inbox": 102484,
      "checkpoint": 9335
    },
    "read_only_database_checks": true
  },
  "expected_rows": {
    "stock_identity_insert_rows": 1,
    "common_ingest_batch_rows": 1,
    "common_active_source_version_rows": 1
  },
  "source_evidence": {
    "ts_code": "920206.BJ",
    "trade_date": "20260608",
    "stock_basic": [
      {
        "ts_code": "920206.BJ",
        "symbol": "920206",
        "name": "彩客科技",
        "area": "河北",
        "industry": "染料涂料",
        "market": "北交所",
        "list_date": "20260608",
        "delist_date": null,
        "list_status": "L",
        "exchange": "BSE"
      }
    ],
    "daily": [
      {
        "ts_code": "920206.BJ",
        "trade_date": "20260608",
        "open": 78.11,
        "high": 116.85,
        "low": 78.11,
        "close": 81.87,
        "pre_close": 30.28,
        "change": 51.59,
        "pct_chg": 170.3765,
        "vol": 101534.79,
        "amount": 914213.061
      }
    ],
    "adj_factor": [
      {
        "ts_code": "920206.BJ",
        "trade_date": "20260608",
        "adj_factor": 1.0
      }
    ],
    "suspend_d": [
      {
        "ts_code": "920206.BJ",
        "trade_date": "20260608",
        "suspend_type": "S",
        "suspend_timing": "9:31-9:41"
      }
    ],
    "bak_daily": [
      {
        "ts_code": "920206.BJ",
        "trade_date": "20260608",
        "name": "N彩客",
        "close": 81.87,
        "open": 78.11,
        "high": 116.85,
        "low": 78.11,
        "pre_close": 30.28,
        "vol": 101535.0,
        "amount": 91421.31
      }
    ]
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 0,
    "p2_count": 0,
    "source_evidence": {
      "stock_basic_present": true,
      "daily_present": true,
      "adj_factor_present": true,
      "suspend_d_present": true,
      "bak_daily_present": true
    }
  },
  "execute_runner": {
    "implemented": true,
    "runner_readiness": "ready_for_final_gate",
    "final_execute_gate_allowed": true,
    "execute_authorized": false
  },
  "future_write_scope": {
    "allowed_tables": [
      "stock_identity",
      "common_ingest_batch",
      "common_quality_gate_result",
      "common_active_source_version"
    ],
    "forbidden_tables": [
      "stock_daily_bar_fact",
      "index_daily_bar_fact",
      "board_daily_bar_fact",
      "stock_daily_basic",
      "stock_financial_metrics_fact",
      "index_membership_fact",
      "board_membership_fact",
      "condition source",
      "condition_* tables",
      "N2/N3/N4/N5/N6",
      "Parquet",
      "common_event_outbox",
      "common_event_inbox",
      "common_event_consumer_checkpoint",
      "worker",
      "old system",
      "real trading"
    ]
  },
  "rollback": {
    "path": "sql/N1_20260608_stock_identity_920206_repair_rollback.sql",
    "rollback_safe": true
  },
  "side_effects": {
    "writes_postgres": false,
    "updates_active_source_version": false,
    "writes_daily_fact": false,
    "writes_condition_source": false,
    "writes_parquet": false,
    "writes_outbox": false,
    "writes_inbox_or_checkpoint": false,
    "enters_n2_n3_n4_n5_n6": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "execute_command_candidate": "PYTHONPATH=src python3 scripts/run_n1_20260608_stock_identity_920206_repair_once.py --trade-date 20260608 --identity-key stock:BJ:920206 --ts-code 920206.BJ --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled",
  "execute_flags": [
    "--execute",
    "--user-confirmed",
    "--source-fetch-enabled",
    "--postgres-commit-enabled"
  ]
}
```
