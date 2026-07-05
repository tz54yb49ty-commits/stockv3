# V3 Realtime Signal Action Chain Dry Run

N3 -> N4 -> N5 report-only chain.

- result: `DRY_RUN_PASS`
- trade_date: `20260612`
- mode: `dry_run_report_only`
- child_invoked: `False`

## Summary

- n3_metric_ready: `100`
- n4_trigger_matched: `96`
- n5_action_eligible: `96`
- n5_action_executed: `96`
- target_missing_in_v3: `4`
- target_extra_in_v3: `0`

## Forbidden Scope

- target_machine_read_only: `True`
- database_written: `False`
- runtime_db_written: `False`
- scheduler_started: `False`
- worker_started: `False`
- child_invoked: `False`
- outbox_inbox_checkpoint_mutated: `False`
- n3_execute_run: `False`
- n4_executed: `False`
- n5_executed: `False`
- n6_entered: `False`
- voice_mobile_sim_trade_touched: `False`
- real_trade_touched: `False`

## Stages

### n3_metric_replay
- result: `REPLAY_COMPARE_PASS`

### n4_trigger_dry_run
- result: `DRY_RUN_PASS`
- input_source: `N3 realtime virtual metric replay`
- TriggerMatched: `96`
- TriggerPendingMarketData: `0`
- TriggerStateChanged: `0`
- raw_minute_rows_read: `False`
- market_adapter_called: `False`
- business_rules_changed: `False`

### n5_action_dry_run
- result: `DRY_RUN_PASS`
- entry_event: `TriggerMatched`
- ActionEligible: `96`
- ActionExecuted: `96`
- ActionBlocked: `0`
- ActionSkipped: `0`
- evidence: `trigger_time_virtual_120m_30m_5m_plus_closed_trigger_minute_1m`
- real_order_created: `False`
- sim_order_created: `False`
- n6_entered: `False`
