# N2-F Scope Consumption Contract

## Summary

N2-F 明确 `minute_target_scope` 的消费口径，避免把条件来源明细行误解成行情层实际拉取任务。

```text
minute_target_scope = 条件来源明细表
market_data_subscription = 实时行情层去重后的实际拉取任务
```

本阶段只更新合同和文档：

```text
business_data_written=false
migration_executed=false
market_data_pulled=false
downstream_layers_touched=false
worker_started=false
```

## Why

N2-E10 后，`index_minute_target_scope=26` 是合理的条件来源口径：

```text
8 个指数对象
26 条 object + direction + condition_key 明细
```

它保留了：

```text
condition_key
allowed_signal_types
direction
source_condition_pool_id
previous_day_minute_date
scope_source
```

但实时行情层不能按 26 行重复拉取同一个指数行情。行情层必须先做去重订阅。

## Grain

### condition_pool / minute_target_scope grain

条件层允许保留以下粒度：

```text
asset_kind + identity_key + direction + condition_key
```

用途：

```text
1. 解释对象为什么进入行情范围。
2. 保留 BUY / SELL / BUY_HINT / SELL_HINT / FULL 差异；其中 `BUY_HINT / SELL_HINT` 是正式买卖触发信号类型，后续 N4 可基于 N3 标准化、可追溯 realtime projection 指标触发，`MinuteBarClosed` / closed 30m summary 只作为强确认或回放校验入口，不是仅用户层提示。
3. 追溯 source_condition_pool_id。
4. 支持 replay / audit / 用户展示。
```

### market_data_subscription grain

实时行情层必须生成去重后的订阅任务，建议粒度：

```text
asset_kind + identity_key + required_data_kind + for_trade_date
```

`required_data_kind` 建议先限定为：

```text
realtime_daily_snapshot
minute_bar_1m
previous_day_minute_bar_1m
```

说明：

```text
相同 identity_key 的多条 condition_key 明细，只能合并成对应 data_kind 的一次行情订阅。
```

## Required Dedup Rules

实时行情层消费 `minute_target_scope` 时必须：

```text
1. 按 stock / index / board 物理分表读取 scope。
2. 根据 daily_snapshot_required / minute_required / previous_day_minute_required 生成 required_data_kind。
3. 按 asset_kind + identity_key + required_data_kind + for_trade_date 去重。
4. 保留 source_scope_ids 或 source_condition_pool_ids 数组用于追溯。
5. 为 previous_day_minute_bar_1m 固定使用 previous_day_minute_date。
6. 输出 subscription_object_count 与 source_scope_row_count，禁止把二者混为一谈。
```

示例：

```text
index_minute_target_scope rows = 26
index subscription objects = 8
行情拉取次数按 subscription objects / required_data_kind 计算，不按 26 行 scope 明细计算。
```

## Forbidden

```text
P0: 实时行情层按 minute_target_scope 明细行逐行拉行情，导致同一 identity_key 重复拉取。
P0: 行情层绕过 condition_pool / minute_target_scope 自行扩大对象范围。
P0: 触发层、动作层、用户层直接调用外部行情接口。四类 projection / 30m 类信号也必须消费 N3 标准事实、标准事件、标准化 realtime projection 指标或 N3 closed summary；N4 不得自行拼原始分钟或自造 projection 指标。
P0: 条件层直接拉取 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m。
P0: market_data_subscription 缺少 source_scope_ids / source_condition_pool_ids 追溯信息。
```

## Output Contract For N3

N3 实时行情层应先设计只读计划：

```text
minute_target_scope
-> market_data_subscription_candidate
-> market_data_subscription_dedup
-> market_data_pull_plan
```

N3-A 不应直接拉行情。建议先输出 dry-run：

```text
source_scope_row_count
subscription_row_count
subscription_object_count
required_data_kind_counts
dedup_ratio
source_scope_ids_sample
P0/P1/P2
```

## Boundary Confirmation

- N2-F does not execute SQL.
- N2-F does not write condition-layer business rows.
- N2-F does not pull market data or minute K.
- N2-F does not enter N3 / trigger / action / mobile / voice / sim / worker.
- N2-F does not touch the old system.

## N2-Display 与 Scope 消费边界

N2 四表输出后，本合同继续只约束交易链路 scope 消费：

```text
minute_target_scope -> market_data_subscription -> N3/N4/N5
```

新增的 `condition_display_basis` 不属于 scope 消费合同，不得作为 N3/N4/N5 输入。它只作为 N6 展示输入，由 N2 在同一 active run 内从 basis/pool/scope 派生。

因此：

```text
N3 不读取 condition_display_basis。
N4 不读取 condition_display_basis。
N5 不读取 condition_display_basis。
N6 优先读取 condition_display_basis，而不是 join basis/pool/scope。
```

如果未来 N2 policy 改变并生成新 active run，下游交易链路仍按 `minute_target_scope` lineage 重建；N6 展示链路按同一 run_id 的 `condition_display_basis` 重建或刷新。
