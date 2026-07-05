# N3 Market Data Subscription Rebuild 20260608 v13 Index-All Execute Final Gate Review

Result: **PASS**

Layer role: `runtime_control`

This final review authorizes only entry to the N3 subscription execute user-confirmation gate. It does not execute N3 subscription and does not write the runtime database.

## Findings

```text
source_condition_run_id=condition_layer_20260605_to_20260608_v13_index_all_execute
market_data_run_id=market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_trade_date=20260605
for_trade_date=20260608
prev_trade_date=20260605
N2 status=passed_active
N2 P0/P1/P2=0/3/3
N3 dry-run P0/P1/P2=0/0/0
```

Expected registration rows:

| Item | Count |
|---|---:|
| common_market_data_run | 1 |
| common_market_data_quality_item | 34 |
| common_market_data_subscription_candidate | 5421 |
| common_market_data_subscription | 2899 |
| common_market_data_pull_plan | 9 |
| minute/snapshot fact rows | 0 |
| outbox events | 0 |

Scope summary:

| Asset | Scope Rows | Objects |
|---|---:|---:|
| stock | 4241 | 1945 |
| index | 169 | 83 |
| board | 267 | 127 |
| total | 4677 | 2155 |

Required data kind:

| Kind | Count |
|---|---:|
| realtime_daily_snapshot | 2155 |
| minute_bar_1m | 372 |
| previous_day_minute_bar_1m | 372 |

## Approved Scope

Allowed next action is a registration-only N3 subscription execute under `layer_role=N3_market_data`.

The only allowed write tables in that user-confirmed execute are:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`

`pull_plan.execute_allowed` must remain `false`.

## Blocked Scope

The following remain blocked in this runtime_control gate:

- runtime_control executing the command
- market data pull
- previous-day minute A1 preload
- today minute pull
- realtime snapshot pull
- minute/snapshot fact writes
- outbox event writes or consumption
- inbox/checkpoint mutation
- N4/N5/N6
- worker
- rollback execution
- old system touch
- real trading

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py \
  --source-condition-run-id condition_layer_20260605_to_20260608_v13_index_all_execute \
  --source-trade-date 20260605 \
  --for-trade-date 20260608 \
  --market-data-run-id market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_market_data_subscription_rebuild_20260608_v13_index_all_execute_backup_before.json \
  --post-backup-path docs/N3_market_data_subscription_rebuild_20260608_v13_index_all_execute_backup_after.json \
  --report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_REPORT.md
```

## Rollback Proof

Rollback SQL:
`sql/N3_market_data_subscription_rebuild_20260608_v13_index_all_rollback.sql`

Static proof:

- hard-fail before first `DELETE`
- deletes only N3 subscription control rows for this run
- does not delete N2 v13 rows
- does not delete market facts
- blocks if market facts, projection refs, event refs, or downstream refs exist
- no `CASCADE`, `DROP`, or `TRUNCATE`

## Validation

```text
JSON parse PASS
rollback static check PASS
runner guard tests PASS: 4 OK
subscription tests PASS: 168 OK
market data tests PASS: 168 OK
compileall PASS
git diff --check PASS
```

## Next Gate

```text
N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_USER_CONFIRMATION_GATE
```
