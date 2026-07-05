{
  "stage": "N1 source facts 20260608 official daily dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_PASS_WITH_SKIP_POLICY",
  "trade_date": "20260626",
  "source_batch_id": "official_daily_ingest_20260626_v1",
  "expected_rows": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "stock_probe": {
    "result": "STOCK_PROBE_PASS_WITH_SKIP_POLICY",
    "stock_source": {
      "tushare_daily_count": 0,
      "adj_factor_count": 0,
      "matched_identity_count": 0,
      "unmapped_count": 0,
      "unmapped_sample": [],
      "daily_basic_unmapped_count": 0,
      "daily_basic_unmapped_sample": [],
      "adj_minus_daily_active_identity_count": 0,
      "duplicate_daily_ts_code_count": 0,
      "skip_policy": "skip_missing_stock_identity_when_count_lte_10",
      "stock_identity_refresh_required": false
    }
  },
  "skip_policy": {
    "policy": "skip_missing_stock_identity_when_count_lte_10",
    "manifest": [
      {
        "ts_code": "920206.BJ",
        "canonical_identity_key": "stock:BJ:920206",
        "asset_kind": "stock",
        "reason": "stock_identity_missing_below_threshold",
        "policy_name": "skip_missing_stock_identity_when_count_lte_10",
        "source_presence": [
          "tushare.daily",
          "tushare.daily_basic"
        ],
        "severity": "P1",
        "writes_stock_daily_bar_fact": false,
        "writes_stock_daily_basic": false,
        "writes_stock_financial_metrics_fact": false,
        "action": "exclude_from_20260608_source_facts"
      }
    ]
  },
  "side_effects": {
    "writes_postgres": false,
    "writes_outbox": false,
    "enters_n2_n3_n4_n5_n6": false
  }
}
