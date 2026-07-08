# 20260609 Fast Lane N2 Bundle Execute Report

Result: `PASS`

Gate: `RUNTIME_CONTROL_20260609_N2_CONDITION_POST_REVIEW_REGISTRATION_GATE`

This artifact registers the completed N2 condition layer execute/post-review for the 20260609 Fast Lane pilot. It does not represent a new execute in this runtime_control gate.

## Lineage

- bundle_run_id: `n2_fastlane_bundle_20260609_manual_layer_sequence`
- layer_role: `N2_condition`
- run_id: `condition_layer_20260608_source_20260608_for_20260609_v1`
- source_trade_date: `20260608`
- for_trade_date: `20260609`
- status: `passed_active`
- active_passed_count: `1`

## Row Counts

| Table family | Stock | Index | Board |
|---|---:|---:|---:|
| condition_basis | 5514 | 83 | 428 |
| condition_pool | 4063 | 216 | 265 |
| minute_target_scope | 4043 | 216 | 265 |
| condition_display_basis | 1880 | 83 | 127 |
| monitor_target | 5514 | 83 | 428 |

- common_condition_run: `1`
- common_condition_quality_item: `106`
- row_counts_match_expected: `true`

## Quality

- underlying P0/P1/P2: `0/6/3`
- persisted quality:
  - P0 passed: `91`
  - P1 passed: `4`
  - P1 warning: `7`
  - P2 warning: `4`
- P0 failed: `0`
- aggregate warning rows are bookkeeping (`aggregate_p1_confirmation` / `aggregate_p2_recorded`), not new business blockers.

## Source And Skip Proof

N1 active source versions all match `20260608` v1:

- stock_daily: `stock_daily_20260608_v1`
- index_daily: `index_daily_20260608_v1`
- board_daily: `board_daily_20260608_v1`
- stock_daily_basic: `stock_daily_basic_20260608_v1`
- stock_financial: `stock_financial_20260608_v1`
- index_membership: `index_membership_20260608_v1`
- board_membership: `board_membership_20260608_v1`

`920206.BJ / stock:BJ:920206` skip proof:

- N1 active fact rows daily/basic/financial: `0/0/0`
- N2 basis/pool/scope/display rows: `0/0/0/0`
- severity: `P1`
- status: non-blocking skip propagated correctly.

## Boundary

- outbox/inbox/checkpoint refs: `0/0/0`
- N3/N4/N5/N6 refs: `0/0/0/0`
- market_data_pulled: `false`
- worker_started: `false`
- old_system_touched: `false`
- proposal/order/trade/sim/position/PnL/real_trade touched: `false`

## Rollback

- rollback SQL: `sql/N2_condition_layer_20260609_rollback.sql`
- rollback_safe: `true`
- hard-fail before DELETE: `true`
- guards event infra and downstream refs: `true`
- no DROP/TRUNCATE/CASCADE
- does not touch N1 facts.

## Sub Reports

- `docs/N2_20260609_condition_layer_execute_report.json`
- `docs/N2_20260609_CONDITION_LAYER_EXECUTE_REPORT.md`
- `docs/N2_20260609_CONDITION_LAYER_POST_REVIEW.md`
- `docs/N2_20260609_CONDITION_LAYER_POST_REVIEW.json`

## Next Gate

`N3_MARKET_DATA_A1_20260609_READINESS_GATE`
