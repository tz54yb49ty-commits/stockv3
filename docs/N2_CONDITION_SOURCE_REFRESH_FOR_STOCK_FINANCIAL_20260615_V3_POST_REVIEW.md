# N2 Condition Source Refresh for Stock Financial 20260615 v3 Post Review

Result: `POST_REVIEW_PASS`

```text
source_trade_date = 20260615
for_trade_date = 20260616
execute_run_id = condition_layer_20260615_source_20260615_for_20260616_v4
previous_active_run_id = condition_layer_20260615_source_20260615_for_20260616_v3
command_exit_code = 0
writes_performed = true
will_execute_sql = true
migration_performed = false
minute_kline_pulled = false
downstream_layers_touched = false
n3_lineage_auto_switch = false
```

## Active Supersede Proof

```text
v4.status = passed_active
v3.status = superseded
active_run_count = 1
```

## Row Count Proof

```text
condition_basis stock/index/board = 5504/83/427
condition_pool stock/index/board = 4215/183/307
minute_target_scope stock/index/board = 4194/183/307
condition_display_basis stock/index/board = 1822/83/127
monitor_target stock/index/board = 5504/83/427
common_condition_quality_item = 103
common_condition_run = 1
```

## Quality Proof

```text
P0 failed = 0
P0 passed = 91
P1 passed = 4
P1 warning = 4
P2 warning = 4
```

## 002831 Propagation Proof

```text
financial_source_version = stock_financial_20260615_v3
source_type = tdx_financial_package
interest_expense_used = 19744658
score = 87.0
pe_core = 20.2506996374
report_core_profit = 341586050.0
core_profit_ttm = 1940382164.0
pool_rows = 2
scope_rows = 2
display_rows = 1
```

Pool samples:

```json
[
  {
    "condition_key": "BUY:M,D",
    "direction": "buy",
    "allowed_signal_types": [
      "BUY"
    ],
    "score": 87.0
  },
  {
    "condition_key": "SELL:Y,Q,M,W,D",
    "direction": "sell",
    "allowed_signal_types": [
      "SELL"
    ],
    "score": 87.0
  }
]
```

## Boundary Proof

```text
outbox/inbox/checkpoint delta = 0/0/0
N3/N4/N5/N6 refs = 0/0/0/0
market_or_minute_pull = false
worker_started = false
rollback_executed = false
```

## Rollback Proof

```text
rollback_sql = sql/N2_condition_source_refresh_for_stock_financial_20260615_v3_rollback.sql
exists = true
restores_v3_passed_active = true
hard_fail_before_delete_or_update = true
guards_event_infra = true
guards_downstream_refs = true
no_drop_truncate_cascade = true
```

## Decision

```text
can_mark_N2_condition_source_refresh_complete = true
recommended_next_gate = N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_READINESS_GATE
N3 lineage refresh must use a separate N3 gate.
```
