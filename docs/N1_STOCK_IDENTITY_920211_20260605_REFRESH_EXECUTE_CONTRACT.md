# N1 Stock Identity 920211 20260605 Refresh Execute Contract

```json
{
  "stage": "N1 stock_identity refresh 20260605 execute contract",
  "layer_role": "N1_ingestion",
  "result": "DESIGN_PASS",
  "trade_date": "20260605",
  "runner_readiness": "ready_for_final_gate",
  "execute_authorized": false,
  "final_execute_gate_allowed": true,
  "source_batch_id": "stock_identity_refresh_20260605_920211_v1",
  "source_version": "stock_identity_20260605_v1",
  "previous_source_version": "stock_identity_20260604_v1",
  "active_scope_key": "A_STOCK:20260605",
  "expected_rows": {
    "stock_identity_insert_rows": 1,
    "common_ingest_batch_rows": 1,
    "common_active_source_version_rows": 1
  },
  "new_identity_rows": [
    {
      "stock_identity_key": "stock:BJ:920211",
      "ts_code": "920211.BJ",
      "code": "920211",
      "exchange": "BJ",
      "name": "新睿电子",
      "area": "浙江",
      "industry": "专用机械",
      "market": "北交所",
      "listed_date": "20260605",
      "delisted_date": null,
      "is_st": false,
      "status": "active"
    }
  ],
  "source_evidence": {
    "ts_code": "920211.BJ",
    "trade_date": "20260605",
    "stock_basic": [
      {
        "ts_code": "920211.BJ",
        "symbol": "920211",
        "name": "新睿电子",
        "area": "浙江",
        "industry": "专用机械",
        "market": "北交所",
        "list_date": "20260605",
        "delist_date": null,
        "list_status": "L",
        "exchange": "BSE"
      }
    ],
    "daily": [
      {
        "ts_code": "920211.BJ",
        "trade_date": "20260605",
        "open": 278.87,
        "high": 280.0,
        "low": 226.68,
        "close": 226.88,
        "pre_close": 25.19,
        "change": 201.69,
        "pct_chg": 800.6749,
        "vol": 54564.27,
        "amount": 1382833.647
      }
    ],
    "adj_factor": [
      {
        "ts_code": "920211.BJ",
        "trade_date": "20260605",
        "adj_factor": 1.0
      }
    ],
    "suspend_d": [],
    "bak_daily": [
      {
        "ts_code": "920211.BJ",
        "trade_date": "20260605",
        "name": "N新睿",
        "close": 226.88,
        "open": 278.87,
        "high": 280.0,
        "low": 226.68,
        "pre_close": 25.19,
        "vol": 54564.0,
        "amount": 138283.37
      }
    ]
  },
  "execute_flags": [
    "--execute",
    "--user-confirmed"
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
    "path": "sql/N1_stock_identity_920211_20260605_refresh_rollback.sql",
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
