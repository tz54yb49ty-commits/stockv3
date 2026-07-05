
# V3 20260616 Realtime Virtual Metric Writer Dry Run

- result: `DRY_RUN_PASS`
- target_run_id: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- planned rows stock/index/board/total: `564/17/53/634`
- signal counts: `{'S_SELL': 590, 'B_BUY': 44}`
- metric_ready/not_ready: `634/0`
- previous_day_same_window_amount coverage: `{'required_for_metric_ready_rows': True, 'metric_ready_rows': 634, 'non_null_rows': 634, 'missing_rows': 0}`
- virtual amount policy integrity: `{'checked_rows': 1268, 'missing_proof_rows': 0, 'required_trace_missing_rows': 0, 'mismatch_rows': 0, 'required_trace_missing_samples': [], 'mismatch_samples': [], 'policy': 'current_30m_virtual_amount must equal current_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount'}`
- side effects: plan-only, no DB write, no outbox/inbox/checkpoint, no N4/N5/N6
