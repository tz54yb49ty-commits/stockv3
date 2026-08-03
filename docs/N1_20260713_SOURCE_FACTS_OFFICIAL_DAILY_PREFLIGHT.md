{
  "stage": "N1 source facts 20260608 official daily execute preflight",
  "layer_role": "N1_ingestion",
  "result": "PREFLIGHT_PASS",
  "production_execute_blockers": [],
  "quality": {
    "p0_count": 0,
    "p1_count": 1,
    "p2_count": 0
  },
  "final_execute_gate_allowed": true,
  "expected_rows": {
    "stock_daily_bar_fact": 5514,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6025
  },
  "skip_policy": "skip_missing_stock_identity_when_count_lte_10"
}
