# N2 Condition Layer 20260602 Execute Post-review

status = POST_REVIEW_PASS

```text
run_id = condition_layer_20260602_source_20260602_v1
source_trade_date = 20260602
for_trade_date = 20260603
prev_trade_date = 20260602
common_condition_run.status = passed_active
active_passed_count = 1
policy = 8782_console / n2_default_policy / v4
policy_hash = ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
P0/P1/P2 = 0/9/3
common_condition_quality_item = 109
```

## Row Counts

| Table | Expected | Actual |
|---|---:|---:|
| board_condition_basis | 428 | 428 |
| board_condition_display_basis | 428 | 428 |
| board_condition_pool | 890 | 890 |
| board_minute_target_scope | 890 | 890 |
| board_monitor_target | 428 | 428 |
| common_condition_quality_item | 109 | 109 |
| common_condition_run | 1 | 1 |
| index_condition_basis | 83 | 83 |
| index_condition_display_basis | 83 | 83 |
| index_condition_pool | 168 | 168 |
| index_minute_target_scope | 168 | 168 |
| index_monitor_target | 83 | 83 |
| stock_condition_basis | 5507 | 5507 |
| stock_condition_display_basis | 1963 | 1963 |
| stock_condition_pool | 4182 | 4182 |
| stock_minute_target_scope | 4164 | 4164 |
| stock_monitor_target | 5507 | 5507 |

## Boundary Proof

```text
common_event_outbox_refs = 0
common_event_inbox_refs = 0
common_event_consumer_checkpoint_refs = 0
N3/N4/N5/N6 refs = 0/0/0/0
market_data_pulled = false
downstream_layers_touched = false
n3_lineage_auto_switch = false
```

## Alignment Note

- The canonical 20260602 N2 policy is the broad 8782 console draft policy.
- Refreshed dry-run / contract / preflight artifacts now match the executed broad-policy row counts.
- Preflight remains execute_allowed=false only because this already executed run now exists; that is not a post-review row mismatch.

## Rollback

rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260602_rollback.sql

## Next Step

Allow runtime_control to recheck this N2 post-review. Do not enter N3 automatically from N2.
