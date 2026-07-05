{
  "stage": "N1 source facts 20260608 official daily execute contract",
  "layer_role": "N1_ingestion",
  "result": "DESIGN_PASS",
  "trade_date": "20260617",
  "source_batch_id": "official_daily_ingest_20260617_v1",
  "source_versions": {
    "stock": "stock_daily_20260617_v1",
    "index": "index_daily_20260617_v1",
    "board": "board_daily_20260617_v1"
  },
  "expected_rows": {
    "stock_daily_bar_fact": 5505,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 427,
    "total_daily_fact": 6015
  },
  "skip_policy": "skip_missing_stock_identity_when_count_lte_10"
}
