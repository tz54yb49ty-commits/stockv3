# N4 Projection Matcher 20260608 Until 15:00 Unified Output Retry Final Gate Review

- gate: `N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_REGENERATION_GATE`
- result: `PASS`
- regeneration_result: `REGENERATION_PASS`
- target_run_id: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- consumer: `n4_projection_matcher_consumer_v1_until_1500_unified_output_retry`
- generated_at: `2026-06-09T21:25:11.170772+08:00`

## Baseline Proof

- target_new_run_all_zero: `True`
- n5_refs_total: `0`
- n6_user_refs_total: `0`
- N3 MarketSnapshotUpdated outbox status: `{"pending": 2155}`
- old FULL repair lineage preserved: `{"common_event_outbox": 556, "common_trigger_run": 1}`

## Dry-Run Summary

| item | value |
|---|---:|
| `candidate_count` | `4677` |
| `matched_count` | `556` |
| `pending_count` | `0` |
| `not_matched_signal_count` | `4121` |
| `matched_by_signal_type` | `{"B_BUY": 415, "S_SELL": 141}` |
| `matched_by_trigger_mark_candidate` | `{"30m_shrink": 6, "30m_volume": 116, "normal": 434}` |
| `buy_hint_matched_count` | `116` |
| `sell_hint_matched_count` | `6` |
| `P0/P1/P2` | `[0, 0, 0]` |

## Preflight / Planned Writes

| item | value |
|---|---:|
| `accepted_source_event_count` | `2155` |
| `matched_output_count` | `556` |
| `pending_output_count` | `0` |
| `inbox_write_plan_count` | `2155` |
| `checkpoint_write_plan_count` | `2155` |
| `planned_event_types` | `['TriggerMatched']` |
| `P0/P1/P2` | `[0, 0, 0]` |

## Unified Output Proof

- required_field_missing_total: `0`
- condition_signal_type_distribution: `{"BUY": 299, "BUY_HINT": 116, "SELL": 135, "SELL_HINT": 6}`
- signal_type_distribution: `{"B_BUY": 415, "S_SELL": 141}`
- trigger_mark_candidate_distribution: `{"30m_shrink": 6, "30m_volume": 116, "normal": 434}`

## HINT event_time Proof

- BUY_HINT event_time present/total/missing: `116/116/0`
- SELL_HINT event_time present/total/missing: `6/6/0`

## Six-Family Semantic Proof

- context_family_distribution: `{"BUY": 2106, "BUY:FULL": 47, "BUY_HINT": 218, "SELL": 2113, "SELL:FULL": 39, "SELL_HINT": 154}`
- planned_trigger_matched_by_condition_signal_type: `{"BUY": 299, "BUY_HINT": 116, "SELL": 135, "SELL_HINT": 6}`
- FULL TriggerMatched: `0`
- FULL interpretation: FULL rows are present in context and guarded; no FULL TriggerMatched planned because this retry has no D transition trigger for FULL.
- formal 30m pollution count: `0`
- action_mark emitted count: `0`

## P0 Guard Proof

| item | value |
|---|---:|
| `invalid_signal_type` | `0` |
| `runtime_signal_mismatch` | `0` |
| `invalid_condition_signal_type` | `0` |
| `condition_signal_type_family_mismatch` | `0` |
| `required_unified_fields_missing_total` | `0` |
| `event_time_missing` | `0` |
| `trigger_matched_trigger_price_null` | `0` |
| `trigger_matched_trigger_kind_missing` | `0` |
| `trigger_matched_n5_entry_allowed_not_true` | `0` |
| `action_mark_key_present` | `0` |
| `action_mark_non_null` | `0` |
| `ordinary_full_trigger_period_30m` | `0` |
| `formal_period_fields_contain_30m` | `0` |
| `formal_missing_requested_periods` | `0` |
| `formal_missing_triggered_periods` | `0` |
| `formal_missing_all_trigger_periods` | `0` |
| `formal_missing_primary_trigger_period` | `0` |
| `formal_missing_triggered_period_details` | `0` |
| `hint_trigger_period_not_30m` | `0` |
| `hint_formal_periods_non_empty` | `0` |
| `hint_primary_trigger_period_not_null` | `0` |
| `hint_triggered_period_details_non_empty` | `0` |
| `hint_projection_required_not_true` | `0` |
| `hint_projection_flag_not_true` | `0` |
| `hint_projection_period_not_30m` | `0` |
| `hint_projection_type_invalid` | `0` |
| `projection_marker_inconsistent` | `0` |
| `full_trigger_period_not_d_if_matched` | `0` |
| `full_formal_periods_invalid_if_matched` | `0` |

## Rollback Proof

| item | value |
|---|---:|
| `sql_path` | `sql/N4_projection_matcher_20260608_until_1500_unified_output_retry_rollback.sql` |
| `exists` | `True` |
| `hard_fail_before_first_delete_update` | `True` |
| `guards_delivered_delivering` | `True` |
| `guards_n5_refs` | `True` |
| `guards_n6_user_sim_refs` | `True` |
| `delete_scope_only_target_run` | `True` |
| `preserves_n3_n2_n1_and_old_lineage` | `True` |
| `no_drop_truncate_cascade` | `True` |
| `rollback_executed` | `False` |

## Forbidden Scope Proof

| item | value |
|---|---:|
| `n4_execute_performed` | `False` |
| `db_business_write_performed` | `False` |
| `outbox_consumed_or_updated` | `False` |
| `inbox_checkpoint_consumed_or_updated` | `False` |
| `n5_entered` | `False` |
| `n6_entered` | `False` |
| `worker_started` | `False` |
| `delivery_push_voice_mobile` | `False` |
| `sim_position_pnl_real_trade` | `False` |
| `proposal_order_trade` | `False` |
| `old_system_touched` | `False` |
| `rollback_executed` | `False` |

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_projection_matcher_once.py \
  --execute --user-confirmed \
  --execute-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --trigger-context-run-id trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --snapshot-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --projection-run-id realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --consumer-name n4_projection_matcher_consumer_v1_until_1500_unified_output_retry \
  --dry-run-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_DRY_RUN.json \
  --json-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_projection_matcher_20260608_until_1500_unified_output_retry_rollback.sql
```

## Next Gate

`N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_USER_CONFIRMATION_GATE`
