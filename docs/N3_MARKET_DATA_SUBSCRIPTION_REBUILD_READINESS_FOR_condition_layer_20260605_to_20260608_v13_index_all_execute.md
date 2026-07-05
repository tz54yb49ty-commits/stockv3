# N3 Market Data Subscription Rebuild Readiness - 20260608 v13 Index-All

Result: **READINESS_PASS**

Gate:
`N3_MARKET_DATA_SUBSCRIPTION_REBUILD_READINESS_GATE_FOR_condition_layer_20260605_to_20260608_v13_index_all_execute`

Layer role: `runtime_control`

This review is read-only. It does not execute N3 subscription, does not write N3 control rows, does not pull market data, and does not enter N4/N5/N6.

## N2 v13 Source Proof

Source condition run:
`condition_layer_20260605_to_20260608_v13_index_all_execute`

The N2 v13 overwrite post-review confirms:

| Item | Value |
|---|---:|
| status | `passed_active` |
| source_trade_date | `20260605` |
| for_trade_date | `20260608` |
| prev_trade_date | `20260605` |
| P0 / P1 / P2 | `0 / 3 / 3` |
| active passed run count | `1` |
| policy_version | `v13` |
| policy_hash | `5161cc7743480ccbbf2bf7b413417946870ccb8ffdd468f47f430385b1b6542c` |
| index policy | `selected_identity_key="__all__"` |

Index 83 proof:

| Table / Scope | Objects | Rows |
|---|---:|---:|
| index_monitor_target | 83 | 83 |
| index_condition_basis | 83 | 83 |
| index_condition_pool | 83 | 169 |
| index_minute_target_scope | 83 | 169 |
| index_condition_display_basis | 83 | 83 |

## Scope Consumption Proof

N3 subscription input is limited to:

- `stock_minute_target_scope`
- `index_minute_target_scope`
- `board_minute_target_scope`

`condition_display_basis` is explicitly forbidden as N3 input. The dedup grain remains:

```text
asset_kind + identity_key + required_data_kind + for_trade_date
```

Source scope:

| Asset | Scope Rows | Objects |
|---|---:|---:|
| stock | 4241 | 1945 |
| index | 169 | 83 |
| board | 267 | 127 |
| total | 4677 | 2155 |

## Planned Rebuild Summary

Planned registration run:
`market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

Dry-run artifact:
`docs/N3_market_data_subscription_rebuild_20260608_v13_index_all_readiness_dry_run.json`

| Item | Count |
|---|---:|
| subscription candidates | 5421 |
| deduped subscriptions | 2899 |
| subscription objects | 2155 |
| pull_plan rows | 9 |
| P0 / P1 / P2 | 0 / 0 / 0 |

Required data kind distribution:

| required_data_kind | stock | index | board | total |
|---|---:|---:|---:|---:|
| realtime_daily_snapshot | 1945 | 83 | 127 | 2155 |
| minute_bar_1m | 353 | 6 | 13 | 372 |
| previous_day_minute_bar_1m | 353 | 6 | 13 | 372 |

Calendar proof:

| Item | Value |
|---|---|
| for_trade_date | `20260608` |
| is_open | `true` |
| prev_trade_date | `20260605` |
| next_trade_date | `20260609` |
| calendar source_version | `trade_calendar_20260608_patch_v1` |

## Existing Baseline

No scoped N3 subscription rows currently exist for this v13 lineage:

| Table / Ref | Count |
|---|---:|
| common_market_data_run | 0 |
| common_market_data_subscription_candidate | 0 |
| common_market_data_subscription | 0 |
| common_market_data_pull_plan | 0 |
| common_market_data_quality_item | 0 |
| scoped realtime snapshot facts | 0 |
| scoped minute facts | 0 |
| scoped previous-day preload status | 0 |
| common_trigger_run | 0 |
| common_action_run | 0 |
| user_projection_run | 0 |
| common_event_outbox | 0 |
| common_event_inbox | 0 |

`common_event_consumer_checkpoint` has no supported scoped lineage column for this query, so it is recorded as not directly attributable in this readiness gate rather than treated as a failure.

## Future Contract Requirements

The next contract gate may prepare a registration-only execute command. That future execute must write only:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`

The future `pull_plan.execute_allowed` must remain `false`; this is not a market data pull gate.

Future rollback must:

- hard-fail before `DELETE` / `UPDATE`
- delete only scoped N3 subscription control rows for the new subscription run
- not delete N2 v13 rows
- not delete minute/snapshot facts unless separately authorized
- block if pull/market facts, projection refs, event refs, N4/N5/N6 refs, outbox/inbox/checkpoint refs, or worker refs exist
- contain no `CASCADE`, `DROP`, or `TRUNCATE`

## Forbidden Scope Proof

This readiness gate did not execute N3 subscription, did not write control rows, did not pull market data, did not write minute/snapshot facts, did not write outbox events, did not consume/update outbox/inbox/checkpoint, did not start a worker, did not enter N4/N5/N6, did not execute rollback SQL, and did not touch the old system or real trading.

## Next Gate

Allowed next gate:

```text
N3_MARKET_DATA_SUBSCRIPTION_REBUILD_CONTRACT_GATE_FOR_condition_layer_20260605_to_20260608_v13_index_all_execute
```
