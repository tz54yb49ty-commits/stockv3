# N5-0 Action Layer Schema / Event Contract

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

## Scope

本文件冻结 N5-0 第一版动作层合同，只覆盖 schema 草案、N4 outbox preflight、action candidate dry-run 和静态边界检查。

本轮不执行 migration，不写 action fact，不消费 N4 outbox，不更新 `common_event_inbox` / `common_event_consumer_checkpoint`，不进入 N6。

## Input Contract

N5 只接受 N4 标准事件：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N5-0 preflight 的输入表是 `common_event_outbox` 中：

```text
source_layer = 'N4_trigger'
source_run_id = <N4 run_id>
```

当前 N4-5 outbox 是 synthetic/sample run-once 结果，只用于 N5 开发验证，不代表真实盘中 N3 event 消费结果。

## Output Contract

N5 正式输出事件只允许：

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

N5 输出 payload 必填：

```text
run_id
source_trigger_event_id
trigger_match_id
identity_key
asset_kind
direction
signal_type
condition_key
trigger_period
action_type
lane
data_quality_status
```

## BUY_HINT / SELL_HINT

`BUY_HINT` / `SELL_HINT` 是标准买卖动作候选，不在 N5 丢弃，也不硬编码为只能提示。

N5-0 dry-run 中：

```text
BUY_HINT  -> direction=buy  -> action candidate
SELL_HINT -> direction=sell -> action candidate
```

是否真实买卖、是否只提示、是否进入 sim 或真实交易，后续只能由 `lane / user_policy / position_state` 决定。N5-0 不做这些执行决策。

## Minute K Boundary

N5 不拉行情，只能读取 N3 已闭合：

```text
minute_bar_1m
previous_day_minute_bar_1m
```

对以下 30 分钟确认信号：

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

N5 只接受 N4 基于 `MinuteBarClosed` 或闭合 30 分钟确认摘要产生的触发结果。若 source trigger payload 指向未闭合分钟上下文，N5 dry-run 标记 `blocked_quality`，不得生成可确认动作。

## Schema Draft

Schema 草案路径：

```text
sql/011_action_layer_schema.sql
```

核心表：

```text
common_action_run
common_action_quality_item
stock_action_decision
index_action_decision
board_action_decision
common_action_event
common_position_state
common_position_event
```

`stock/index/board_action_decision` 继续物理分表，`identity_key` 只作为追溯和去重键，不替代物理隔离。

## N5-0 Preflight / Dry-Run

CLI：

```bash
PYTHONPATH=src python3 scripts/plan_action_preflight_dry_run.py \
  --trigger-run-id trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
```

输出：

```text
docs/N5_0_action_preflight_dry_run_report.json
docs/N5_0_ACTION_PREFLIGHT_DRY_RUN_REPORT.md
```

只读统计：

```text
event_type distribution
signal_type distribution
asset_kind distribution
direction distribution
BUY_HINT / SELL_HINT matched + pending
TriggerPendingMarketData count
```

Dry-run 转换：

```text
TriggerMatched -> action_candidate
TriggerPendingMarketData -> quality_plan / pending_market_data
TriggerCleared -> clear_candidate / PositionEvent candidate
```

## Static Contract Check

CLI：

```bash
PYTHONPATH=src python3 scripts/check_n5_contract.py
```

检查：

```text
禁止 N5 输出 User* / Voice* / Sim*
禁止 N5 写 user / voice / sim 表
禁止 N5 写真实交易接口
禁止正式表名使用 *_runtime
禁止 N5 直接引用 mootdx / Tushare
禁止 N5-0 preflight 更新 common_event_inbox / common_event_consumer_checkpoint
```
