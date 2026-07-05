# RUNTIME 20260608 N1/N2/N3-A1 One-Shot Premarket Readiness

result: `READINESS_BLOCKED`

layer_role: `runtime_control`

## Objective

Evaluate whether the requested one-shot path can proceed:

```text
N1_ingestion
-> N2_condition
-> N3_market_data subscription
-> N3-A1 previous-day minute preload
```

Requested lineage:

```text
current_date=20260607
source_trade_date=20260605
for_trade_date=20260608
previous_trade_date=20260605
```

## Decision

The one-shot path cannot execute to N3-A1 yet.

Stop at `N1_readiness`.

Reason: live DB proof shows the 20260608 trade-calendar row is absent and 20260605 N1 close/source facts are not loaded. N2 and N3-A1 do not yet have a valid upstream source lineage.

## Live Proof

Calendar:

| trade_date | exists | is_open | prev_trade_date | next_trade_date |
|---|---:|---:|---|---|
| 20260605 | true | true | 20260604 | 20260608 |
| 20260608 | false | n/a | n/a | n/a |

N1 20260605 facts:

| table | rows |
|---|---:|
| stock_daily_bar_fact | 0 |
| index_daily_bar_fact | 0 |
| board_daily_bar_fact | 0 |
| stock_daily_basic | 0 |

Latest active source versions are still anchored at `20260604` for stock/index/board daily, stock daily basic, financial, identity, and membership source families. The latest active calendar scope is `SSE:20260605`; no active `20260608` calendar row was observed.

Target lineage rows:

| object | rows |
|---|---:|
| common_condition_run where source_trade_date=20260605 or for_trade_date=20260608 | 0 |
| common_market_data_run where source_trade_date=20260605 or for_trade_date=20260608 | 0 |

## P0/P1/P2

P0:

- `calendar_20260608_missing`
- `stock_daily_bar_fact_20260605_missing`
- `index_daily_bar_fact_20260605_missing`
- `board_daily_bar_fact_20260605_missing`
- `stock_daily_basic_20260605_missing`
- `condition_source_20260605_not_active`

P1:

- `n2_condition_run_for_20260608_absent_due_to_missing_n1_source`
- `n3_market_data_run_for_20260608_absent_due_to_missing_n2_condition_run`
- `run_real_daily_incremental_py_is_a_real_write_runner_and_must_not_be_called_from_runtime_control`
- `date_specific_20260605_n1_final_gate_artifacts_not_confirmed_for_this_new_lineage`

P2:

- `one_shot_objective_crosses_N1_N2_N3_layer_roles_and_must_be_executed_as_explicit_layer_gated_sequence`

Summary: `P0/P1/P2 = 6/4/1`.

## Required Repair Sequence

1. `N1_20260605_CLOSE_AND_20260608_CALENDAR_REPAIR_CONTRACT_GATE`

   Generate N1 trade-calendar 20260608 patch and 20260605 close ingestion/condition-source contract, preflight, rollback, and final gate inputs. This remains runtime_control only and must not execute writes.

2. `N1_20260608_TRADE_CALENDAR_PATCH_EXECUTE_USER_CONFIRMATION_GATE`

   Switch to `layer_role=N1_ingestion`. Execute only after final gate and explicit user confirmation.

3. `N1_20260605_OFFICIAL_DAILY_INGESTION_EXECUTE_USER_CONFIRMATION_GATE`

   Switch to `layer_role=N1_ingestion`. Execute only after final gate and explicit user confirmation.

4. `N1_20260605_CONDITION_SOURCE_ACTIVATION_EXECUTE_USER_CONFIRMATION_GATE`

   Switch to `layer_role=N1_ingestion`. Execute only after final gate and explicit user confirmation.

5. `N2_CONDITION_LAYER_20260605_TO_20260608_EXECUTE_FINAL_GATE_REVIEW`

   Enter only after N1 post-review proves the 20260605 source bundle is active.

6. `N3_MARKET_DATA_SUBSCRIPTION_AND_A1_20260608_READINESS_GATE`

   Enter only after the N2 active condition run for 20260608 exists.

## Forbidden Scope Proof

This runtime_control review did not:

- execute N1/N2/N3 commands
- write database rows
- execute rollback SQL
- pull market data
- write minute or snapshot facts
- enter N4/N5/N6
- consume or update outbox/inbox/checkpoint
- start worker
- enter delivery/push/voice/mobile/sim/position/PnL/real trade
- generate proposal/order/trade
- touch the old system

## Next Gate

Recommended next gate:

```text
N1_20260605_CLOSE_AND_20260608_CALENDAR_REPAIR_CONTRACT_GATE
```

