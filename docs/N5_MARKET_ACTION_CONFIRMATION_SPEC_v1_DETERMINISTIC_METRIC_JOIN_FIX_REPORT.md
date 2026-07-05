# N5 Market Action Confirmation Spec v1 Deterministic Metric Join Fix Report

- result: `FIX_PASS`
- metric_join_coverage: `863/863`
- metric_rows: `822`
- missing_metric_rows: `0`
- duplicate_join_key_count: `0`
- ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped: `{'ActionEligible': 0, 'ActionBlocked': 863, 'ActionExecuted': 0, 'ActionSkipped': 0}`
- blocked_reason_distribution: `{'amount_confirmation_failed': 25, 'price_confirmation_failed': 838}`
- action_mark_final_non_null_count: `0`
- invalid_user_layer_blocked_reason_count: `0`
- rollback_sql: `sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql`
- rollback_hard_fail_before_delete: `True`

No execute was performed. No N4/N5 outbox was consumed. N6/user/voice/mobile/sim/position/real trade paths were not touched.
