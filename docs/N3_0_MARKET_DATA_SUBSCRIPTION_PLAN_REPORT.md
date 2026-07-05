# N3-0 Market Data Subscription Dry-Run Report

## Summary

N3-0 已按指定 active condition run 完成 `market_data_subscription` dry-run / preflight。

```text
layer_role=N3_market_data
source_condition_run_id=condition_layer_20260522_to_20260525_20260524014029_execute
source_trade_date=20260522
for_trade_date=20260525
prev_trade_date=20260522
```

输出 JSON：

```text
docs/N3_0_market_data_subscription_plan_20260525.json
```

## Scope Input

按 stock / index / board 物理分表读取 `minute_target_scope`：

| asset_kind | source_scope_row_count | source_scope_object_count |
|---|---:|---:|
| stock | 4236 | 2052 |
| index | 18 | 9 |
| board | 258 | 127 |
| total | 4512 | 2188 |

scope contract 检查：

```text
active condition run status=passed
active condition run P0=0
scope_source=condition_pool
source_condition_pool_id present
previous_day_minute_date=prev_trade_date
allowed_signal_types within v3 whitelist
```

## Candidate And Dedup

根据三类 required flag 展开 candidate：

```text
daily_snapshot_required=true -> realtime_daily_snapshot
minute_required=true -> minute_bar_1m
previous_day_minute_required=true -> previous_day_minute_bar_1m
```

本次 dry-run：

| metric | value |
|---|---:|
| source_scope_row_count | 4512 |
| subscription_candidate_count | 13536 |
| dedup_subscription_count | 6564 |
| subscription_object_count | 2188 |
| dedup_ratio | 0.484929 |
| dedup_reduction_ratio | 0.515071 |

`market_data_subscription_dedup` 按以下粒度去重：

```text
asset_kind + identity_key + required_data_kind + for_trade_date
```

每条 dedup subscription 保留：

```text
source_scope_ids
source_condition_pool_ids
condition_keys
directions
allowed_signal_types
```

## Required Data Kind

| required_data_kind | dedup_subscription_count |
|---|---:|
| realtime_daily_snapshot | 2188 |
| minute_bar_1m | 2188 |
| previous_day_minute_bar_1m | 2188 |

object_count by asset_kind：

| asset_kind | object_count |
|---|---:|
| stock | 2052 |
| index | 9 |
| board | 127 |

previous_day_minute_required：

| metric | value |
|---|---:|
| previous_day_minute_required_count | 4512 |
| previous_day_minute_required_object_count | 2188 |

previous_day_minute_date 分布：

| previous_day_minute_date | scope_row_count |
|---|---:|
| 20260522 | 4512 |

## Pull Plan

`market_data_pull_plan` 仅为 dry-run 分组计划，不执行行情拉取。

| asset_kind | required_data_kind | data_trade_date | subscription_count |
|---|---|---:|---:|
| stock | realtime_daily_snapshot | 20260525 | 2052 |
| stock | minute_bar_1m | 20260525 | 2052 |
| stock | previous_day_minute_bar_1m | 20260522 | 2052 |
| index | realtime_daily_snapshot | 20260525 | 9 |
| index | minute_bar_1m | 20260525 | 9 |
| index | previous_day_minute_bar_1m | 20260522 | 9 |
| board | realtime_daily_snapshot | 20260525 | 127 |
| board | minute_bar_1m | 20260525 | 127 |
| board | previous_day_minute_bar_1m | 20260522 | 127 |

## Calendar Detail Check

按要求只读检查 `20260525` 日历详情：

```text
common_trade_calendar table_exists=true
for_trade_date row_exists=false
severity=P1
```

说明：`20260525` 日历详情缺失属于上游日历明细缺口。本轮 N3-0 不修 N1 日历；由于 active run 与 scope 已明确 `prev_trade_date=20260522` 且 previous_day_minute_date 全部匹配，本项记录为 P1，不阻断订阅 dry-run。

## Quality

```text
P0=0
P1=1
P2=0
blocked=false
passed=true
```

P1：

```text
for_trade_calendar_row_exists: expected=20260525 actual=missing
```

## Boundary Confirmation

```text
old_system_touched=false
migration_executed=false
will_execute_sql=false
writes_performed=false
market_data_pulled=false
market_data_fact_written=false
downstream_layers_touched=false
trigger_action_mobile_voice_sim_entered=false
worker_started=false
```

N3-0 到此停止。未进入 N3 execute，未拉 mootdx / tushare / 实时行情，未写 minute_bar / snapshot / trigger / action / user 表。

## Rollback

N3-0 未写数据库、未写行情事实表、未执行 migration。回滚只需删除本次更新的 dry-run 代码和报告文件，或用版本控制恢复：

```text
src/ashare_v3/market/subscription_plan.py
scripts/plan_market_data_subscription.py
tests/test_market_data_subscription_plan.py
docs/N3_0_MARKET_DATA_SUBSCRIPTION_PLAN_REPORT.md
docs/N3_0_market_data_subscription_plan_20260525.json
```
