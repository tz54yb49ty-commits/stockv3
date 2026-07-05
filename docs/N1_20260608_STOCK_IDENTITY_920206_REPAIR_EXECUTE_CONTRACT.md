# N1 20260608 Stock Identity 920206 Repair Execute Contract

```json
{
  "stage": "N1 stock_identity refresh 20260608 execute contract",
  "layer_role": "N1_ingestion",
  "result": "DESIGN_PASS",
  "trade_date": "20260608",
  "runner_readiness": "ready_for_final_gate",
  "execute_authorized": false,
  "final_execute_gate_allowed": true,
  "source_batch_id": "stock_identity_refresh_20260608_920206_v1",
  "source_version": "stock_identity_20260608_v1",
  "previous_source_version": "stock_identity_20260605_v1",
  "active_scope_key": "A_STOCK:20260608",
  "expected_rows": {
    "stock_identity_insert_rows": 1,
    "common_ingest_batch_rows": 1,
    "common_active_source_version_rows": 1
  },
  "new_identity_rows": [
    {
      "stock_identity_key": "stock:BJ:920206",
      "ts_code": "920206.BJ",
      "code": "920206",
      "exchange": "BJ",
      "name": "彩客科技",
      "area": "河北",
      "industry": "染料涂料",
      "market": "北交所",
      "listed_date": "20260608",
      "delisted_date": null,
      "is_st": false,
      "status": "active"
    }
  ],
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
  "execute_flags": [
    "--execute",
    "--user-confirmed",
    "--source-fetch-enabled",
    "--postgres-commit-enabled"
  ],
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
    ],
    "single_transaction": true,
    "postgres_only": true,
    "writes_parquet": false
  },
  "idempotency": {
    "block_existing_batch_id": true,
    "block_existing_source_version": true,
    "block_existing_target_identity_key": true,
    "block_existing_target_ts_code": true,
    "block_existing_active_scope_key": true
  },
  "quality_gate": {
    "p0_must_equal_zero": true,
    "expected_p0_p1_p2": {
      "p0": 0,
      "p1": 0,
      "p2": 0
    }
  },
  "rollback": {
    "path": "sql/N1_20260608_stock_identity_920206_repair_rollback.sql",
    "strategy": "delete this batch's stock_identity row and quality/batch metadata, then restore active scope to previous_source_version when resolvable",
    "do_not_touch_historical_identity_rows": true,
    "do_not_touch_daily_fact": true,
    "do_not_touch_outbox_or_n2_n6": true
  },
  "implementation_status": {
    "execute_runner_implemented": true,
    "execute_authorized": false,
    "final_execute_gate_allowed": true,
    "next_gate": "final_execute_gate"
  }
}
```
