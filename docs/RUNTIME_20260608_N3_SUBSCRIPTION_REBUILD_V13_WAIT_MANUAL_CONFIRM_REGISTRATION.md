# Runtime 20260608 N3 Subscription Rebuild v13 WAIT_MANUAL_CONFIRM Registration

Result: **WAIT_MANUAL_CONFIRM_REGISTERED**

Objective:
`RUNTIME_20260608_N1_N2_N3A1_ONE_SHOT_PREMARKET_CLOSEOUT`

This runtime_control registration does not execute the command, does not write the database, does not pull market data, and does not enter N4/N5/N6.

## Current State

The N3 subscription rebuild final gate is passed:

```text
source_condition_run_id=condition_layer_20260605_to_20260608_v13_index_all_execute
market_data_run_id=market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
source_trade_date=20260605
for_trade_date=20260608
prev_trade_date=20260605
```

Reviewed artifacts:

- `docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_READINESS_FOR_condition_layer_20260605_to_20260608_v13_index_all_execute.json`
- `docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_CONTRACT.json`
- `docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_PREFLIGHT.json`
- `docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_FINAL_GATE_REVIEW.json`
- `sql/N3_market_data_subscription_rebuild_20260608_v13_index_all_rollback.sql`

## Manual Confirmation Boundary

Next required layer role:
`N3_market_data`

Next gate:
`N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_EXECUTE_USER_CONFIRMATION_GATE`

Runtime control must stop here:

```text
blocked_by_layer=N3_market_data
```

## Allowed Execute Scope After User Confirmation

Allowed execute type: `registration_only`

Allowed write tables:

| Table | Rows |
|---|---:|
| common_market_data_run | 1 |
| common_market_data_quality_item | 34 |
| common_market_data_subscription_candidate | 5421 |
| common_market_data_subscription | 2899 |
| common_market_data_pull_plan | 9 |

`pull_plan.execute_allowed` must remain `false`.

No market data pull, no minute/snapshot facts, no outbox events, no N4/N5/N6.

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

## Rollback Registry

Rollback SQL:
`sql/N3_market_data_subscription_rebuild_20260608_v13_index_all_rollback.sql`

Proof:

- hard-fail before first `DELETE`
- deletes only scoped N3 subscription control rows
- does not delete N2 rows
- does not delete market facts
- guards event infra and downstream refs
- no `CASCADE`, `DROP`, or `TRUNCATE`

## Forbidden Scope Proof

This runtime_control registration did not execute the command, did not write DB rows, did not execute rollback SQL, did not pull market data, did not write minute/snapshot facts, did not consume/update outbox/inbox/checkpoint, did not start a worker, did not enter N4/N5/N6, did not touch the old system, and did not perform real trading.

## After Execute

After the N3 user-confirmed execute passes, return to runtime_control for:

```text
N3_MARKET_DATA_SUBSCRIPTION_REBUILD_20260608_V13_INDEX_ALL_POST_REVIEW_GATE
```

Then proceed toward:

```text
N3_A1_PREVIOUS_DAY_MINUTE_PRELOAD_READINESS_GATE_FOR_market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute
```
