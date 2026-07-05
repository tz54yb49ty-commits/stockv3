# N3 20260617 D-Anchor B2 Formal Amount Proof Rebuild Preflight After N2 Q/Y Policy

Result: `BLOCKED`

## Scope

- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- trade_date: `20260617`
- subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- today_minute_run_id: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- planned_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- n2 policy: `n2_formal_amount_required_periods_only_qy_gap_policy_v1`

## Preflight Checks

- n3_b2_after_qy_policy_n2_policy_registered: `passed`
- n3_b2_after_qy_policy_subscription_passed: `passed`
- n3_b2_after_qy_policy_c1_run_passed: `passed`
- n3_b2_after_qy_policy_c1_full_day_coverage: `passed`
- n3_b2_after_qy_policy_bj_blockers_preserved: `passed`
- n3_b2_after_qy_policy_required_period_gap_zero: `passed`
- n3_b2_after_qy_policy_canonical_distribution_full_scope: `passed`
- n3_b2_after_qy_policy_b2_target_clean: `failed`
- n3_b2_after_qy_policy_previous_day_same_window_source_available: `failed`

## Canonical Distribution

- scope: included identities; BJ excluded identities remain quality-visible blockers
- BUY: `1939`
- SELL: `2021`
- BUY:FULL: `110`
- SELL:FULL: `28`
- BUY_HINT: `59`
- SELL_HINT: `165`
- not_hint_only: `True`

## Target Clean Proof

- common_market_data_run rows: `1`
- common_market_data_quality_item rows: `8`
- metric rows stock/index/board: `1841/81/127`
- outbox/inbox/checkpoint refs: `0/0/0`

## Previous-Day Same-Window Source

- stock rows: `0`, rows_1431_1500: `0`
- index rows: `0`, rows_1431_1500: `0`
- board rows: `0`, rows_1431_1500: `0`

## Rollback

- rollback_required_for_this_preflight: `false`
- rollback_sql_draft_or_path_if_needed: `/Users/chuanfuchen/Documents/A股监控系统v3/sql/N3_20260617_d_anchor_repair_full_day_action_confirmation_metric_rollback.sql`
- target_cleanup_required_before_execute: `True`

## Forbidden Scope Proof

- B2 metric executed: `false`
- N4/N5/N6 entered: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system read or modified: `false`

## Allowed B2 Execute Prompt

No B2 execute prompt is allowed because preflight is blocked.
