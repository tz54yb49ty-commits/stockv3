# N2 20260609 Condition Layer Post-Review

Result: `POST_REVIEW_PASS`

## Run Status

```text
run_id = condition_layer_20260608_source_20260608_for_20260609_v1
source_trade_date = 20260608
for_trade_date = 20260609
status = passed_active
active_passed_count = 1
```

## Row Counts

| table | expected | actual |
|---|---:|---:|
| common_condition_run | 1 | 1 |
| common_condition_quality_item | 106 | 106 |
| stock_monitor_target | 5514 | 5514 |
| index_monitor_target | 83 | 83 |
| board_monitor_target | 428 | 428 |
| stock_condition_basis | 5514 | 5514 |
| index_condition_basis | 83 | 83 |
| board_condition_basis | 428 | 428 |
| stock_condition_pool | 4063 | 4063 |
| index_condition_pool | 216 | 216 |
| board_condition_pool | 265 | 265 |
| stock_minute_target_scope | 4043 | 4043 |
| index_minute_target_scope | 216 | 216 |
| board_minute_target_scope | 265 | 265 |
| stock_condition_display_basis | 1880 | 1880 |
| index_condition_display_basis | 83 | 83 |
| board_condition_display_basis | 127 | 127 |

## Quality

Underlying dry-run quality:

```text
P0/P1/P2 = 0/6/3
```

Persisted quality item distribution includes aggregate bookkeeping rows:

```text
P0 passed = 91
P1 passed = 4
P1 warning = 7
P2 warning = 4
```

The extra warning rows are `aggregate_p1_confirmation` and `aggregate_p2_recorded`; they do not represent new business blockers.

## Source Proof

Active N1 source versions:

```text
stock_daily = stock_daily_20260608_v1
index_daily = index_daily_20260608_v1
board_daily = board_daily_20260608_v1
stock_daily_basic = stock_daily_basic_20260608_v1
stock_financial = stock_financial_20260608_v1
index_membership = index_membership_20260608_v1
board_membership = board_membership_20260608_v1
```

Skip policy proof:

```text
920206.BJ / stock:BJ:920206
N1 active fact rows daily/basic/financial = 0/0/0
N2 stock basis/pool/scope/display rows = 0/0/0/0
blocking = false
```

## Boundary Proof

```text
outbox/inbox/checkpoint refs = 0/0/0
N3/N4/N5/N6 refs = 0/0/0/0
market_data_pulled = false
worker_started = false
old_system_touched = false
trade/sim/position touched = false
```

## Rollback

Rollback SQL:

```text
sql/N2_condition_layer_20260609_rollback.sql
```

Rollback safety:

```text
hard_fail_before_delete = true
guards outbox/inbox/checkpoint = true
guards N3/N4/N5/N6 refs = true
scoped_to_run_id = true
no DROP/TRUNCATE/CASCADE = true
does_not_touch_n1_facts = true
```

## Recommendation

Allow runtime_control N2 post-review registration. Do not enter N3 automatically; switch explicitly to the next layer before N3-A1 readiness.
