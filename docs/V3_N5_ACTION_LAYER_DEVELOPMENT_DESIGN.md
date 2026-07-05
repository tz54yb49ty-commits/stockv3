# V3 N5 Action Layer Development Design

> Status: historical/superseded for new runtime terminology.
>
> New N4/N5 runtime work must follow, in order:
> `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`,
> `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`,
> `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md`,
> and `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md`.
>
> Legacy terms in this document, including `TriggerCleared`,
> `ActionEvent`, `HintEvent`, `RiskEvent`, `PositionEvent`,
> `B_BUY_30M_VOL`, and `S_SELL_30M_SHRINK`, are retained only as
> historical compatibility language. Historical run evidence must not be silently rewritten.

## 1. 定位

N5 是 v3 的动作层，负责把 N4 标准触发事件转换为动作、风险、持仓相关标准事件。

```text
N4 TriggerMatched / TriggerCleared / TriggerPendingMarketData
  -> N5 action fact / position fact
  -> ActionEvent / HintEvent / RiskEvent / PositionEvent
```

N5 是动作归一化层，不是用户投影层，不直接播报，不直接交易。

N5 不做：

```text
不拉行情
不重算条件
不重算触发
不写用户卡片
不播放语音
不写真实交易接口
不回写 N4 trigger_state
```

## 2. 核心原则

### 2.1 只消费 N4 标准事件

N5 输入只能是 N4 outbox / event ledger 投递后的标准事件：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N5 不直接扫 N4 内部裸表替代事件消费。

### 2.2 只读 N3 分钟 K

N5 可以读取 N3 本地 runtime 行情事实：

```text
today minute_bar_1m
previous_day_minute_bar_1m
realtime_daily_snapshot 摘要
```

用途是动作上下文、价格解释、风险解释、买入失败止损参考等。

N5 不得调用外部行情接口，不得补拉行情。

### 2.3 事实和事件同事务

N5 写动作事实时，必须同事务写 outbox：

```text
BEGIN;
  INSERT action_event;
  UPDATE position_state if needed;
  INSERT position_event if needed;
  INSERT common_event_outbox;
  UPDATE consumer_checkpoint;
COMMIT;
```

## 3. 输入

N5 只消费 N4 标准事件：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N5 可只读：

```text
N4 trigger payload
N4 trigger_context_snapshot 摘要
N3 minute_bar_1m
N3 previous_day_minute_bar_1m
N2 条件摘要字段的本地副本
```

N5 不应回读外接盘 N2 作为盘中高频路径。若需要 N2 静态字段，应由 N4 payload 或本地 action context snapshot 继承。
N2-R4 后，动作层如需触发阈值、目标价或参考周期，只能读取 N4 payload / N4 context / N5 action context 中继承的 `period_trigger_baseline_json`、`up_sell_reference_period`、`down_buy_reference_period`、`clear_sell_ref_period`，不得直接回查 N2/N1 重算。

### 3.1 Canonical action confirmation input

N3/N4/N5 action confirmation rule is frozen in:

```text
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
```

For new canonical runtime work, N5 final action confirmation must consume:

```text
N4 TriggerMatched
N3T action-confirmation metric facts
```

N3T is the N3_market_data C1-derived action-confirmation transform. It must use closed 1m K only
(`source_basis=N3T_C1_CLOSED`) and must not accept N3P/B1/B2/realtime_action_confirmation_metric lineage as final
`ActionExecuted` proof.

For live tracking v2, when `source_metric_run_id` starts with `n3t_action_confirmation_metric_`,
N5 reads the N3T Option A table family:

```text
stock_n3t_action_confirmation_metric
index_n3t_action_confirmation_metric
board_n3t_action_confirmation_metric
```

`n3t_action_confirmation_metric_id` is mapped to the N5 compatibility field
`action_confirmation_metric_id`. `source_basis=N3T_C1_CLOSED`,
`metric_role=action_confirmation`, and `proof_consumer=N5` are the valid
ActionExecuted policy lineage for this path; legacy realtime virtual metric
lineage remains trace-only and fails closed for `ActionExecuted`.

Live tracking v2 persistence into `common_action_tracking_state` must populate current schema-required tracking columns.
`monitor_window_id` is a stable N5-owned key derived from `action_run_id + state_key`; `triggered_periods` must come
from `all_trigger_periods` or `primary_trigger_period` and must not be empty.

N5 must not consume opaque `payload.action_confirmation` as final proof. It may preserve that field only as historical compatibility trace until a separate alignment gate removes or replaces it.

N5 must not:

```text
pull market data
read raw minute bars and assemble 1m/5m/30m/120m indicators
compute current_5m_virtual_amount from raw rows
compute previous period body high/low from raw rows
repair missing N3 projection facts by querying N3 raw minute facts
```

### 3.2 N5 C1 / N3T permission boundary

N5 对 N3 侧行情上下文的权限必须写死为 C1 / N3T only：

```text
N5_MARKET_CONTEXT_PERMISSION:
- N5 只允许使用 runtime_control 显式传入的 N3-C1 scoped closed 1m K context / metric_context_rows。
- N5 只允许使用 N3T action-confirmation metric 作为 ActionExecuted 的最终市场确认输入。
- N3T metric 必须满足 source_basis=N3T_C1_CLOSED、metric_role=action_confirmation、proof_consumer=N5、not_n5_final_proof=false。
- N4 TriggerMatched 只允许创建 ActionEligible / active tracking；N4 trigger_mark_candidate、projection_30m_flag、projection_30m_type 只能保留为 trace，不得决定 final action_mark。
- A1 previous-day cumulative、N3P、B1、B2、realtime_action_confirmation_metric 只能作为上游 trace / compatibility evidence；不得作为 ActionExecuted proof，不得作为 final action_mark authority。
- N5 不得触发 N3-C1 / N3T runtime，不得拉行情，不得全量扫描 C1，不得写 N3/N4 facts 或 outbox。
- C1 / N3T context 缺失时，N5 必须 fail closed for ActionExecuted；ActionEligible 仍可来自有效 N4 TriggerMatched。
```

任何后续 N5 patch / execute gate 如果需要 N3 侧行情确认，都必须先证明输入来自上述 C1 / N3T allowlist；否则按 `BLOCKED_N3T_METRIC_REQUIRED` 或 `BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF` 处理。

## 4. 建议 schema

```text
common_action_run
common_action_quality_item
common_action_event_inbox
common_action_consumer_checkpoint

stock_action_context_snapshot
index_action_context_snapshot
board_action_context_snapshot

stock_action_event
index_action_event
board_action_event

stock_position_state
stock_position_event
```

N5 action context 最小字段：

```text
source_trigger_event_id
source_trigger_state_id
source_condition_run_id
source_condition_pool_id
source_market_event_id
asset_kind
identity_key
code
name
direction
signal_type
condition_key
trigger_price
trigger_time
trigger_period
buy_target_price
sell_target_price
clear_sell_ref_period
allowed_signal_types
lane
context_hash
```

## 5. 信号到事件映射

Canonical note: this section contains historical design language. New canonical runtime work must follow `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`, `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md`, and `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`: runtime `signal_type` is only `B_BUY` / `S_SELL`, `BUY_HINT` / `SELL_HINT` are provenance, and final action output events are `ActionEligible` / `ActionBlocked` / `ActionExecuted` / `ActionSkipped`.

### 5.1 买入类

```text
B_BUY
B_BUY_30M_VOL
BUY_HINT
```

这些都是标准买入信号类型。

是否进入买入动作、只提示、进入 sim 或真实交易，不由 signal_type 单独决定，而由：

```text
asset_kind
lane
user_policy
position_state
risk_policy
trading_permission
```

共同决定。

### 5.2 卖出类

```text
S_SELL
S_SELL_30M_SHRINK
SELL_HINT
```

这些都是标准卖出信号类型。

是否形成卖出动作、只提示、风险事件或持仓事件，同样由 lane / user_policy / position_state 决定。

### 5.3 建议映射

```text
stock_trade + buy signal + policy allow
  -> ActionEvent

stock_trade + BUY_HINT + policy提示优先
  -> HintEvent 或 ActionEvent，按用户策略

stock_sell/open_position + sell signal + position exists
  -> ActionEvent / PositionEvent

market_alert / stock_alert
  -> HintEvent，除非用户策略显式允许升级

TriggerPendingMarketData
  -> quality item，不生成动作
```

## 6. BUY_HINT / SELL_HINT 定稿

BUY_HINT / SELL_HINT 是标准买卖动作候选，不是天然只能提示。

```text
BUY_HINT:
  N4 已确认 30分钟放量上涨
  N5 视为 buy direction 标准信号候选

SELL_HINT:
  N4 已确认 30分钟缩量下跌
  N5 视为 sell direction 标准信号候选
```

最终处理由用户策略层决定：

```text
是否展示
是否语音
是否强提醒
是否 sim
是否真实交易
是否只提示
```

## 7. 分钟 K 使用

N5 读取 N3 分钟 K 的用途：

```text
动作价格上下文
30分钟动作解释
买入失败止损参考
卖出动作确认
风险解释字段
回放与审计
```

如果分钟 K 缺失：

```text
写 ActionPendingMarketData 或 common_action_quality_item
不越界拉行情
不伪造动作上下文
```


闭合分钟 K 动作确认硬规则：

```text
N5 只能使用 N3 已闭合 minute_bar_1m / previous_day_minute_bar_1m 作为动作上下文。
1 分钟 K 标签 HH:MM 只有到 HH:MM+1 后才视为闭合。
N5 不得使用正在形成的当前分钟 K 生成 ActionEvent / HintEvent / RiskEvent / PositionEvent。
MarketSnapshotUpdated 可以让 N4 更新触发状态，但不能让 N5 越过闭合分钟 K 直接确认分钟动作。
```

对四类分钟确认信号：

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

N5 只能消费 N4 基于闭合 `MinuteBarClosed` 或 N3 闭合 30 分钟确认摘要产生的触发结果；如果分钟事实缺失或未闭合，应写 pending / quality，不得伪造动作。


## 8. 输出事件

N5 outbox 标准事件：

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

### 8.1 ActionEvent payload

```text
action_event_id
source_trigger_event_id
asset_kind
identity_key
direction
signal_type
condition_key
action_type
action_time
action_price
quantity_policy
minute_context_id
position_state_id optional
context_hash
```

### 8.2 HintEvent payload

用于用户策略决定只提示的标准信号或非交易范围对象。

```text
hint_event_id
source_trigger_event_id
asset_kind
identity_key
direction
signal_type
condition_key
hint_level
hint_reason
context_hash
```

### 8.3 RiskEvent payload

用于风险类提醒。

### 8.4 PositionEvent payload

用于持仓状态变化或持仓解释。

## 9. 幂等和去重

建议 dedup key：

```text
trade_date + identity_key + direction + signal_type + condition_key + action_bucket + policy_hash
```

对于同一触发事件重复投递，N5 必须幂等跳过。

## 10. 开发阶段

```text
N5-0：schema + action event contract
N5-1：N4 event consumption dry-run
N5-2：action mapping dry-run
N5-3：action execute run-once
N5-4：position state shadow
N5-5：bounded worker smoke
N5-6：长期 worker / 启动编排，后置
```

长期 worker 必须后置。

## 11. Worker 要求

bounded worker 必须具备：

```text
max_runtime_minutes
stop_file
heartbeat/status_json
consumer_checkpoint
recent_action_summary
error_count
lag metrics
```

## 12. P0 规则

```text
P0: N5 直接拉行情
P0: N5 重算 N4 触发
P0: N5 回写 N4 trigger_state
P0: N5 写用户 projection 或直接播放语音
P0: N5 直接写真实交易接口
P0: BUY_HINT / SELL_HINT 被硬编码成只能提示，绕过用户策略
P0: stock_trade 信号在没有策略许可时直接变成真实交易
P0: fact 写入后没有同事务 outbox
P0: consumer 非幂等或缺 checkpoint
```

## 13. 回滚

N5 execute 必须按 run_id 可回滚：

```text
删除 action_event
删除 position_event
回滚 position_state 到前一状态或删除 shadow 状态
删除 common_action_quality_item
删除 common_event_outbox 中 source_run_id 对应事件
删除 common_action_run
```

回滚不得触碰 N1/N2/N3/N4 事实。
