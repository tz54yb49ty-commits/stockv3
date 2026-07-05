# V3 20260612 B_BUY / S_SELL Replay Compare

- result: `REPLAY_COMPARE_PASS`
- mode: `offline_report_only`
- trade_date: `20260612`
- target_golden_counts: `{'B_BUY': 76, 'S_SELL': 24}`
- v3_replay_counts: `{'B_BUY': 76, 'S_SELL': 20}`
- metric_ready_counts: `{'ready': 100}`
- diff_summary: `{'matched': 96, 'missing_in_v3': 4, 'extra_in_v3': 0, 'missing_by_signal_type': {'S_SELL': 4}, 'extra_by_signal_type': {}}`
- diagnostics: `{'target_action_price_replay_counts': {'B_BUY': 76, 'S_SELL': 22}, 'target_legacy_board_amount_compat_replay_counts': {'B_BUY': 76, 'S_SELL': 24}, 'action_price_differs_from_minute_close': 15, 'current_price_source_primary': 'target_machine.minute_kline.1m.close', 'target_action_price_source': 'target_machine.action_fact_cache.price', 'target_action_price_replay_is_diagnostic_only': True, 'target_legacy_board_amount_compat_is_diagnostic_only': True}`

## Boundary

- target_machine_read_only: `True`
- database_written: `False`
- runtime_db_written: `False`
- scheduler_started: `False`
- worker_started: `False`
- n4_n5_business_rules_changed: `False`
- n6_entered: `False`
- voice_mobile_sim_trade_touched: `False`

## Blocked Reason Counts

- confirmation_rule_failed: `4`

## Failed Check Counts

- sell_1m_amount_pass: `2`
- sell_1m_price_pass: `2`
- sell_5m_amount_pass: `1`
- sell_5m_price_pass: `1`
