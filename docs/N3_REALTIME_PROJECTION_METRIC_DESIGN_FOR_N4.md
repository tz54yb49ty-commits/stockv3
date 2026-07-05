# N3 Realtime Projection Metric Design For N4

## Summary

```text
layer_role=N3_market_data
stage=N3 projection design / contract
business_data_written=false
code_changed=false
migration_executed=false
market_data_pulled=false
n3_outbox_consumed=false
worker_started=false
downstream_layers_touched=false
```

本合同只定义 N3 如何向 N4 提供标准化、可追溯的 realtime projection 指标。它不授权 N3 拉行情、不授权 N4 execute、不修改总控状态。

当前 N4 execute blocker 固化为：

```text
缺 N3 标准化、可追溯 realtime projection 指标 + N4 projection matcher。
不是必须等待完整 30m 闭合。
```

在该指标和 N4 matcher 未落地前，N4 real execute 不得把以下信号写成正式 `TriggerMatched`：

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

## Scope

N3 只负责输出 market-only 指标，不负责条件判断和触发判断。

允许：

```text
读取 N3 自身的 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m。
生成 projection 指标的设计合同。
定义 future schema / event payload 候选。
定义 quality gate / trace / rollback 规则。
```

禁止：

```text
不读取 condition_display_basis。
不读取 N4 trigger_context_snapshot 作为 N3 输入。
不写 trigger/action/user/voice/sim/真实交易。
不消费 N3 outbox。
不写 common_event_inbox / checkpoint。
不启动 worker。
不触碰旧系统。
```

N4 后续负责把 N3 projection 指标与本地化后的 N2 context、`period_trigger_baseline_json` 和 condition_key 组合，决定是否输出 `TriggerMatched`。

## Design Choice

推荐 v1 使用 `MarketSnapshotUpdated` payload 扩展承载 projection 指标，同时允许未来落一个 N3 market fact JSONB 或独立物理分表。

选择理由：

```text
1. 不新增 N3->N4 事件类型，避免打破现有标准事件列表。
2. N4 当前真实输入已经是 MarketSnapshotUpdated。
3. projection 指标必须和 snapshot_id / source_run_id / subscription_id 同源可追溯。
4. 若未来需要高频独立 projection，可另开 MarketProjectionUpdated 合同审查；本轮不引入。
```

v1 事件仍是：

```text
event_type=MarketSnapshotUpdated
payload_json.realtime_projection_json=<projection contract>
```

如果某次 snapshot 无法生成 projection 指标，N3 必须显式给出：

```text
realtime_projection_json.projection_status=not_ready 或 quality_blocked
missing_reason / quality_reason
```

N4 遇到 projection 缺失、不可追溯或 quality 不通过时，只能生成 pending/quality 计划，不能写四类 projection / 30m 类信号的正式 `TriggerMatched`。

## Metric Grain

projection 指标粒度：

```text
asset_kind + identity_key + trade_date + projection_window_id + snapshot_id
```

`projection_window_id` 使用当前交易日内的 30m bucket。N4 不必等待 bucket 完整闭合；N3 可以在 bucket 内持续输出截至当前 snapshot_time 的 projection 指标。

窗口字段：

```text
projection_window_kind = active_30m_bucket_projection
projection_window_id
window_start
window_end
snapshot_time
elapsed_seconds
window_total_seconds
completion_ratio
is_window_closed
session_id
```

`is_window_closed=false` 不代表不能被 N4 使用。只要 projection 指标可追溯、quality passed，N4 可以使用它进行正式触发判断。

## Required Metrics

### Price Metrics

```text
window_open_price
latest_price
window_high_price
window_low_price
price_change_from_window_open
price_change_pct_from_window_open
price_direction_status
```

`price_direction_status` 枚举：

```text
up
down
flat
unknown
```

### Amount / Volume Metrics

金额优先于成交量作为跨 stock/index/board 的标准比较口径；volume 可以保留为辅助字段。

```text
elapsed_amount
elapsed_volume
projected_window_amount
projected_window_volume
previous_day_same_window_amount
previous_day_same_elapsed_amount
previous_day_same_window_volume
previous_day_same_elapsed_volume
amount_projection_ratio
elapsed_amount_ratio
volume_projection_ratio
elapsed_volume_ratio
amount_basis_kind
```

`amount_basis_kind` 枚举：

```text
previous_day_same_window
previous_day_same_elapsed
snapshot_delta_anchor
minute_bar_elapsed
adapter_projection
not_available
```

推荐 N3 同时输出 raw numeric 指标和中性 market shape：

```text
market_shape_status
```

`market_shape_status` 枚举：

```text
up_volume_expanding
down_volume_shrinking
up_volume_flat
down_volume_flat
up_volume_shrinking
down_volume_expanding
flat
unknown
```

该 status 不是触发判断，不包含 N2 condition_key 语义。N4 必须仍按本地 context 的 `allowed_signal_types / condition_key / direction` 决定是否生成 `TriggerMatched`。

## Suggested N4 Mapping

N4 matcher 后续可使用以下映射：

```text
B_BUY_30M_VOL:
  allowed_signal_types contains B_BUY_30M_VOL
  direction=buy
  market_shape_status=up_volume_expanding
  projection_quality_status=passed

BUY_HINT:
  condition_key=BUY_HINT
  direction=buy
  market_shape_status=up_volume_expanding
  projection_quality_status=passed

S_SELL_30M_SHRINK:
  allowed_signal_types contains S_SELL_30M_SHRINK
  direction=sell
  market_shape_status=down_volume_shrinking
  projection_quality_status=passed

SELL_HINT:
  condition_key=SELL_HINT
  direction=sell
  market_shape_status=down_volume_shrinking
  projection_quality_status=passed
```

N4 还必须校验：

```text
source_run_id == current N3 snapshot/projection run
context source_condition_run_id == current active N2 run
synthetic denylist not used
period_trigger_baseline_json trace present when trigger_period requires it
```

## Trace Contract

projection 指标必须可追溯到 N3 market facts，不允许只有计算结果。

必填 trace 字段：

```text
projection_id
projection_schema_version
snapshot_run_id
snapshot_id
snapshot_event_id
subscription_id
pull_plan_id
source_adapter
asset_kind
identity_key
trade_date
snapshot_time
data_quality_status
source_fact_ids
source_fact_kind
calculation_method
calculation_config_hash
created_at
```

`source_fact_kind` 枚举：

```text
realtime_daily_snapshot
minute_bar_1m_elapsed
snapshot_delta_anchor
previous_day_minute_bar_1m
adapter_projection
mixed
```

`source_fact_ids` 至少包含：

```text
snapshot_id
minute_bar_ids_used
previous_day_minute_bar_ids_used
anchor_snapshot_id
quality_item_ids
```

没有对应来源时必须写空数组和 `missing_reason`，不能伪造 id。

## Quality Gate

N3 projection status：

```text
ready
not_ready
quality_blocked
```

N3 projection quality status 沿用 v3 质量枚举：

```text
passed
pending
warning
failed
blocked
```

N4 可写正式 `TriggerMatched` 的最低要求：

```text
projection_status=ready
projection_quality_status=passed
trace_status=passed
source_run_id is current authoritative N3 run
projection_schema_version is supported
market_shape_status in supported enum
```

P0：

```text
projection 指标缺少 snapshot_id / subscription_id / pull_plan_id / source_adapter。
projection 指标无法追溯 source_fact_ids。
projection 指标来自旧 synthetic outbox 或非当前 N3 source_run_id。
N3 使用 condition_display_basis、N4 context 或 action/user/sim 数据生成 projection。
N3 输出 TriggerMatched / ActionEvent / User* / Voice* / Sim*。
N4 在 projection_quality_status 非 passed 时写四类 signal 的 TriggerMatched。
N4 自己拉行情或拼原始分钟生成 projection 指标。
```

P1：

```text
completion_ratio 过低导致 projection_status=not_ready。
previous_day_same_window basis 缺失但有明确 quality_item。
adapter projection 可用但缺少 minute-level replay 校验，必须标记 warning。
```

P2：

```text
诊断样本不足。
ratio 小数精度展示不一致。
debug trace 未包含完整计算中间项。
```

## Payload Contract

`MarketSnapshotUpdated.payload_json` 必须继续包含既有 N3 trace 字段，并新增：

```text
realtime_projection_json
```

最小 payload 示例：

```json
{
  "run_id": "realtime_daily_snapshot_20260525__market_data_subscription_...",
  "subscription_id": "sub_...",
  "pull_plan_id": "pull_plan_...",
  "snapshot_id": "snapshot_...",
  "source_adapter": "mootdx",
  "data_quality_status": "passed",
  "realtime_projection_json": {
    "projection_schema_version": "n3.realtime_projection.v1",
    "projection_id": "projection_...",
    "projection_status": "ready",
    "projection_quality_status": "passed",
    "trace_status": "passed",
    "projection_window_kind": "active_30m_bucket_projection",
    "projection_window_id": "20260525-1400-1430",
    "window_start": "2026-05-25T14:00:00+08:00",
    "window_end": "2026-05-25T14:30:00+08:00",
    "snapshot_time": "2026-05-25T14:26:15+08:00",
    "elapsed_seconds": 1575,
    "window_total_seconds": 1800,
    "completion_ratio": "0.8750",
    "is_window_closed": false,
    "latest_price": "10.25",
    "window_open_price": "10.10",
    "price_change_pct_from_window_open": "0.014851",
    "price_direction_status": "up",
    "elapsed_amount": "120000000.00",
    "projected_window_amount": "137142857.14",
    "previous_day_same_window_amount": "90000000.00",
    "amount_projection_ratio": "1.523810",
    "amount_basis_kind": "previous_day_same_window",
    "market_shape_status": "up_volume_expanding",
    "calculation_method": "snapshot_delta_with_previous_day_window_basis",
    "calculation_config_hash": "sha256:...",
    "source_fact_kind": "mixed",
    "source_fact_ids": {
      "snapshot_id": "snapshot_...",
      "anchor_snapshot_id": "snapshot_anchor_...",
      "minute_bar_ids_used": [],
      "previous_day_minute_bar_ids_used": ["bar_prev_..."],
      "quality_item_ids": []
    }
  }
}
```

## Dedup Contract

projection 自身 dedup key：

```text
asset_kind + identity_key + trade_date + projection_window_id + snapshot_time + source_adapter + projection_schema_version
```

如果 future design 需要单独 `MarketProjectionUpdated` event，则必须另行审查，不得复用 `MarketSnapshotUpdated` dedup key。

## Replay / Strong Confirmation

`MinuteBarClosed` / closed 30m summary 的职责：

```text
1. 对 realtime projection 进行强确认。
2. 盘后或回放时验证 projection 是否偏离。
3. 修正 projection 质量状态或生成 replay discrepancy quality item。
```

它们不是四类 projection / 30m 类信号的唯一入口。

回放校验至少比较：

```text
projection_window_id
projected_window_amount vs closed_window_amount
price_direction_status vs closed price direction
market_shape_status vs closed shape
source_fact_ids completeness
```

如果强确认发现 projection 与 closed result 冲突，N3 应输出 quality item 或修正事件合同；N4/N5 是否撤销或补偿属于后续 N4/N5 合同，不在本设计执行。

## Storage Options For Later Implementation

本轮不做 migration。后续 N3 可选两种实现。

推荐 A：snapshot payload + optional JSONB column

```text
stock/index/board_realtime_daily_snapshot.realtime_projection_json
MarketSnapshotUpdated.payload_json.realtime_projection_json
```

优点：最小事件变更，适合当前 N4 real snapshot path。

备选 B：独立 market projection fact

```text
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
```

优点：适合高频 projection 独立更新；缺点是需要新增 schema、rollback、事件合同审查。

本设计建议先走 A。只有当 projection 更新频率独立于 snapshot、或需要多窗口并发 projection 时，再进入 B 的 schema review。

## Acceptance Gates

进入 N4 projection matcher 前，N3 必须提供：

```text
projection payload schema version 固定。
字段枚举固定。
trace 字段完整。
quality gate 明确。
缺 projection 时 N4 pending 行为明确。
synthetic denylist 与 real source_run_id 隔离明确。
rollback 方案明确。
```

进入 N4 real execute 前，必须另行完成：

```text
N3 projection implementation or dry-run evidence。
N4 projection matcher dry-run。
N4 inbox/checkpoint/ack preflight。
N4 rollback SQL。
用户明确 run-once execute 授权。
```

## Rollback

本轮仅新增文档，无数据库回滚。

若未来实现 projection 写入：

```text
未被 N4 消费：
  按 projection_run_id / snapshot_run_id 删除 projection fact 或回滚 payload 扩展。
  删除对应 N3 outbox rows 或恢复 payload 版本。

已被 N4 消费：
  先停止 N4/N5 下游消费。
  按 N4 run_id 回滚 trigger_match / trigger_state / N4 outbox / inbox / checkpoint。
  再回滚 N3 projection fact / payload / outbox。
```

N3 rollback 不得触碰 N2 condition 表、N4 trigger fact、N5 action fact 或 N6 用户投影，除非对应层另行授权。

## Boundary Confirmation

```text
only_v3_project=true
old_system_touched=false
code_changed=false
database_changed=false
market_data_pulled=false
outbox_consumed=false
worker_started=false
total_control_docs_updated=false
n4_execute_authorized=false
n5_n6_touched=false
```
