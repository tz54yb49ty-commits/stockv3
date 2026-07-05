# N2 Full Dry-run Basis / Pool / Scope / Display Report

layer_role = N2_condition
status = FULL_DRY_RUN_PASS

## Run

```text
active_run_id = condition_layer_20260522_to_20260525_20260525003855_execute
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
writes_performed = false
overwrite_performed = false
new_active_run_generated = false
display_basis_written = false
downstream_layers_touched = false
service_started = false
worker_started = false
```

## Four Stage Counts

| Stage | Stock rows | Index rows | Board rows | P0/P1/P2 | Passed |
|---|---:|---:|---:|---|---|
| condition_basis | 5504 | 81 | 428 | 0/4/1 | true |
| condition_pool | 4236 | 18 | 258 | 0/1/1 | true |
| minute_target_scope | 4236 | 18 | 258 | 0/1/1 | true |
| condition_display_basis | 5504 | 81 | 428 | 0/0/0 | true |

## Active Run Comparison

| Stage | Domain | Dry-run rows | Current active rows | Match |
|---|---|---:|---:|---|
| condition_basis | stock | 5504 | 5504 | true |
| condition_basis | index | 81 | 81 | true |
| condition_basis | board | 428 | 428 | true |
| condition_pool | stock | 4236 | 4236 | true |
| condition_pool | index | 18 | 18 | true |
| condition_pool | board | 258 | 258 | true |
| minute_target_scope | stock | 4236 | 4236 | true |
| minute_target_scope | index | 18 | 18 | true |
| minute_target_scope | board | 258 | 258 | true |
| condition_display_basis | stock | 5504 | 0 | display_preview_only |
| condition_display_basis | index | 81 | 0 | display_preview_only |
| condition_display_basis | board | 428 | 0 | display_preview_only |

## Minute Target Scope Explanation

| Domain | Pool rows | Scope rows | Objects | Scope source | Prev-minute mismatch | Explanation |
|---|---:|---:|---:|---|---:|---|
| stock | 4236 | 4236 | 2052 | {'condition_pool': 4236} | 0 | scope rows equal pool rows, condition-key source granularity |
| index | 18 | 18 | 9 | {'condition_pool': 18} | 0 | scope rows equal pool rows, condition-key source granularity |
| board | 258 | 258 | 127 | {'condition_pool': 258} | 0 | scope rows equal pool rows, condition-key source granularity |

## Display Validation

| Domain | Rows | Objects | Duplicate | Empty scope rows | Empty scope explained | Invalid keys | Invalid signals | Invalid baseline | Ref mismatch | Forbidden fields |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| stock | 5504 | 5504 | 0 | 3452 | true | 0 | 0 | 0 | 0 | 0 |
| index | 81 | 81 | 0 | 72 | true | 0 | 0 | 0 | 0 | 0 |
| board | 428 | 428 | 0 | 301 | true | 0 | 0 | 0 | 0 | 0 |

## No-write Checks

| Check | Before | After | Result |
|---|---:|---:|---|
| common_condition_run total | 6 | 6 | unchanged |
| passed condition run count | 1 | 1 | unchanged |
| common_event_outbox | 53304 | 53304 | unchanged |
| stock_condition_display_basis | 0 | 0 | empty |
| index_condition_display_basis | 0 | 0 | empty |
| board_condition_display_basis | 0 | 0 | empty |

## Quality And Decision

```text
blockers = []
execute_readiness_P0/P1/P2 = 0/6/3
execute_preconditions_passed = true
requires_user_confirmation = true
will_execute_sql = false
can_enter_overwrite_preflight = true
```

## Future Overwrite Plan

```text
run_id_pattern = condition_layer_{source_trade_date}_to_{for_trade_date}_{YYYYMMDDHHMMSS}_execute
new_run_required = true
reuse_current_run_id = false
current_active_run_to_supersede_if_confirmed_later = condition_layer_20260522_to_20260525_20260525003855_execute
rollback_strategy = delete new run rows by run_id, then restore previous run status=passed
```

## 014b Decision

```text
needed_for_current_full_dry_run = false
needed_before_overwrite_preflight = false
needed_before_writing_display_quality_items = true
```

014b 不是本轮 dry-run 的前置条件；如果后续 overwrite 要把 `condition_display_basis` 质量项写入 `common_condition_quality_item`，应先单独确认并执行 014b。

## Artifacts

- basis: `docs/N2_FULL_DRY_RUN_condition_basis.json`
- pool: `docs/N2_FULL_DRY_RUN_condition_pool.json`
- scope: `docs/N2_FULL_DRY_RUN_minute_target_scope.json`
- display: `docs/N2_FULL_DRY_RUN_condition_display_basis.json`
- readiness: `docs/N2_FULL_DRY_RUN_execute_readiness_plan.json`
- before_snapshot: `backups/N2_FULL_DRY_RUN_before_snapshot_20260525.json`
- after_snapshot: `backups/N2_FULL_DRY_RUN_after_snapshot_20260525.json`
