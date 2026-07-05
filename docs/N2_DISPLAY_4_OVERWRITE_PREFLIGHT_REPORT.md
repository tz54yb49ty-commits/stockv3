# N2-Display-4 Overwrite Preflight Report

layer_role = N2_condition
status = BLOCKED

## Boundary

```text
read_only = true
will_execute_sql = false
writes_performed = false
overwrite_performed = false
common_event_outbox_written = false
N3_N4_N5_written = false
service_started = false
worker_started = false
```

## Run Id Strategy

```text
current_active_run = condition_layer_20260522_to_20260525_20260525003855_execute
new_run_id_pattern = condition_layer_{source_trade_date}_to_{for_trade_date}_{YYYYMMDDHHMMSS}_execute
preview_only_run_id = condition_layer_20260522_to_20260525_20260525094107_execute
reuse_current_run_id_allowed = false
basis_pool_scope_display_share_same_run_id = true
```

## Planned Write Scope

| Table | Operation | Rows | Notes |
|---|---|---:|---|
| common_condition_run | insert | 1 |  |
| common_condition_quality_item | insert | 104 | basis/pool/scope/run=76; display=28; display layer_scope write=true |
| stock_monitor_target | insert | 5504 |  |
| index_monitor_target | insert | 81 |  |
| board_monitor_target | insert | 428 |  |
| stock_condition_basis | insert | 5504 |  |
| index_condition_basis | insert | 81 |  |
| board_condition_basis | insert | 428 |  |
| stock_condition_pool | insert | 4236 |  |
| index_condition_pool | insert | 18 |  |
| board_condition_pool | insert | 258 |  |
| stock_minute_target_scope | insert | 4236 |  |
| index_minute_target_scope | insert | 18 |  |
| board_minute_target_scope | insert | 258 |  |
| stock_condition_display_basis | insert | 5504 |  |
| index_condition_display_basis | insert | 81 |  |
| board_condition_display_basis | insert | 428 |  |

## 014b Gate

```text
will_write_common_condition_quality_item_layer_scope_condition_display_basis = true
display_quality_item_count = 28
current_schema_allows_condition_display_basis_layer_scope = false
overwrite_execute_requires_014b_first = true
```

BLOCKED: 计划写入 display quality item，但当前 `common_condition_quality_item.layer_scope` CHECK 尚未允许 `condition_display_basis`。必须先单独确认并执行 `sql/014b_condition_display_quality_check.sql`。

## Non-N2 Write Verification

| Target | Will write | Current count / evidence |
|---|---|---|
| common_event_outbox | false | 53304 |
| N3 tables | false | {'common_market_data_run': 4, 'common_market_data_subscription_candidate': 40608, 'common_market_data_subscription': 19692, 'common_market_data_pull_plan': 27} |
| N4 tables | false | {'common_trigger_run': 3, 'common_trigger_state': 17768, 'common_trigger_match': 53304} |
| N5 tables | false | {'common_action_run': 0, 'common_action_event': 0, 'common_position_state': 0} |

## Rollback Plan

```text
previous_active_run_id = condition_layer_20260522_to_20260525_20260525003855_execute
strategy = delete new run rows by run_id, then restore previous active run status=passed
must_not_touch = common_event_outbox, N1, N3, N4, N5, N6, old system
014b_rollback = separate schema rollback review if 014b is executed
```

Delete order:

1. `stock_condition_display_basis`
2. `index_condition_display_basis`
3. `board_condition_display_basis`
4. `stock_minute_target_scope`
5. `board_minute_target_scope`
6. `index_minute_target_scope`
7. `board_condition_pool`
8. `index_condition_pool`
9. `stock_condition_pool`
10. `board_condition_basis`
11. `index_condition_basis`
12. `stock_condition_basis`
13. `board_monitor_target`
14. `index_monitor_target`
15. `stock_monitor_target`
16. `common_condition_quality_item`
17. `common_condition_run`

## Decision

```text
blockers = ['014b_required_before_writing_condition_display_basis_quality_items']
allow_enter_overwrite_execute_confirmation_point = false
recommended_next_step = Execute sql/014b_condition_display_quality_check.sql in a separate confirmed N2 migration step, then rerun N2-Display-4 overwrite preflight.
```

## Artifacts

- json_report: `docs/N2_DISPLAY_4_overwrite_preflight_report.json`
- read_only_snapshot: `backups/N2_DISPLAY_4_overwrite_preflight_readonly_snapshot_20260525.json`
- source_full_dry_run_report: `docs/N2_FULL_DRY_RUN_basis_pool_scope_display_report.json`
