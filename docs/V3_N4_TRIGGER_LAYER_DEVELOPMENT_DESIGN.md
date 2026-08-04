# V3 N4 Trigger Layer Development Design

> Status: historical/superseded for new runtime terminology.
>
> New N4/N5 runtime work must follow, in order:
> `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`,
> `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`,
> `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md`,
> and `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md`.
>
> Legacy terms in this document, including `TriggerCleared`,
> `B_BUY_30M_VOL`, `S_SELL_30M_SHRINK`, `BUY_HINT` as runtime
> `signal_type`, and `SELL_HINT` as runtime `signal_type`, are retained
> only as historical compatibility language. Historical run evidence must not be silently rewritten.

## 1. 定位

N4 是 v3 的触发层，负责把 N3 标准行情事件转换为标准触发事实和触发事件。

```text
N2 condition run
  -> N4 trigger_context_snapshot 本地化
N3 market event
  -> N4 trigger_state / trigger_event
  -> TriggerMatched / TriggerCleared / TriggerPendingMarketData outbox
```

N4 是实时层，但不是行情层、动作层或用户层。

N4 必须遵守：

```text
不拉行情
不读外接盘作为盘中高频路径
不写 action
不写 user projection
不播语音
不写 sim
不真实交易
```

## 2. 核心原则

### 2.1 N2 条件上下文本地化

N2/N1 产物位于较慢的权威事实层，N4 盘中不得每个事件都访问 N2 外接盘数据。

N4 启动或切换交易日前必须先执行一次上下文本地化：

```text
N2 active condition run
N3 market_data_subscription run
  -> stock/index/board_trigger_context_snapshot
```

盘中 N4 worker 只读本地 runtime PostgreSQL 和内存 cache。

### 2.2 Event consumer，不扫表乱跑

N4 worker 的输入是 N3 标准事件：

```text
MarketSnapshotUpdated
MinuteBarClosed
MinuteBarCorrected
MarketDataDelayed
MarketDataMissing
```

N4 输出是 N4 标准事件：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N4 consumer 必须幂等，有 checkpoint / ack / watermark。

### 2.3 事实和事件同事务

N4 写触发事实时，必须在同一事务写 outbox：

```text
BEGIN;
  INSERT/UPDATE trigger_state;
  INSERT trigger_event;
  INSERT common_event_outbox;
  UPDATE consumer_checkpoint;
COMMIT;
```

禁止先写事件再补事实，也禁止事实写入成功但 outbox 缺失。

## 3. 输入

### 3.1 N2 本地化输入

N4-preload 只读：

```text
stock_condition_basis / index_condition_basis / board_condition_basis
stock_condition_pool / index_condition_pool / board_condition_pool
stock_minute_target_scope / index_minute_target_scope / board_minute_target_scope
common_condition_run
```

N2-R4 后，N4 本地化还必须读取并复制 `period_trigger_baseline_json`。该字段来自 N2 冻结结果，包含上一周期实体上沿/下沿、上一周期金额基准、当前周期截至上一交易日 seed 等。N4 不得回查 N1 历史日 K 或自行重算该字段。

读取频率：

```text
交易日前或 N4 启动前一次性读取
盘中不再访问外接盘 N2 路径
```

### 3.2 N3 事件输入

N4 只消费 N3 标准事件，不直接调用外部行情接口。

普通 BUY/SELL/FULL：

```text
主要消费 MarketSnapshotUpdated / realtime_daily_snapshot
```

四类 projection / 30m 类信号：

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

允许消费或引用：

```text
N3 标准化、可追溯 realtime projection 指标
MinuteBarClosed
N3 closed 30m summary
```

N4 不必等待完整 30m 闭合。N4 可以基于 N3 标准化、可追溯 realtime projection 指标判断 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT`，但这些指标必须由 N3 负责标准化和追溯。N4 不能自行拉行情、不能拼原始分钟、不能把非 N3 标准指标写成正式触发。

`MinuteBarClosed` / N3 closed 30m summary 是强确认或回放校验入口，不是唯一正式入口。

闭合分钟 K 触发规则：

```text
N4 可以用 MarketSnapshotUpdated 更新实时触发状态。
MarketSnapshotUpdated 可以携带或追溯到 N3 标准化 realtime projection 指标。
N4 不得用未闭合 1 分钟 K 生成 TriggerMatched。
1 分钟 K 标签 HH:MM 只有到 HH:MM+1 后才可作为闭合分钟事实。
普通 BUY/SELL/FULL 不把 MinuteBarClosed 作为主输入。
B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT 可使用 N3 标准化 realtime projection 指标正式触发；闭合 MinuteBarClosed 或 N3 closed 30m summary 作为强确认和回放校验。
在 N3 projection 指标和 N4 projection matcher 未落地前，N4 real execute 不得把这四类信号写成正式 TriggerMatched。
```

示例：

```text
14:26 K 在 14:27 闭合。
14:27 之后使用 14:26 K 进行强确认或回放校验是合法的。
14:26 分钟内部使用正在形成的 14:26 K 生成 TriggerMatched 是 P0。
14:26 分钟内部如果 N3 已输出标准化、可追溯 realtime projection 指标，N4 可以使用该指标；N4 自己拼接该指标是 P0。
```

### 3.3 N3 action-confirmation metric consumption

N3/N4/N5 action confirmation rule is frozen in:

```text
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
```

N4 may consume only N3 standard action-confirmation projection facts when judging live trigger state, `TriggerMatched`, `TriggerPendingMarketData`, `TriggerStateChanged`, and 30m marker evidence.

N4 may carry the following N5 trace fields:

```text
source_action_confirmation_metric_id
source_projection_run_id
projection_schema_version
source_snapshot_run_id
source_snapshot_event_id
projection_30m_type
trigger_mark_candidate
metric_quality_status
```

N4 must not:

```text
compute current_5m_virtual_amount
compute previous_5m_full_amount
compute previous_1m/5m/30m/120m body high/low
read raw minute bars for action confirmation
decide final action_mark
emit opaque action_confirmation as proof for N5
```

### 3.4 Ordinary lifecycle deactivation evidence

An existing ordinary `matched` state must emit exactly one
`TriggerStateChanged(trigger_live=false, current_status=inactive)` after every
previously active formal period no longer satisfies its persistent
price/amount/chain predicate. The event writes trigger state and outbox only;
it must not write `common_trigger_match` or create an N5 entry.

N2 period-escalation `not_ready` / `not_seen` evidence for W/M/Q/Y may block a
new activation or period upgrade, but it must not by itself keep an unrelated
already-live period active. This deactivation exception is allowed only when:

```text
selected N3 metric is ready and all declared quality/trace fields pass
pending reasons are empty
all blockers are exact period_escalation_prerequisite_not_ready/not_seen reasons
previous active-period formal proof remains canonical and uniquely identified
current formal detail is canonical no_op with unchanged baseline/source trace
the persistent target transition, amount predicate, or required chain is false
```

No fresh transition edge is not deactivation proof. If the persistent predicate
is still true, or if any detail, baseline, source, date, unit, hash, or quality
proof is missing or conflicting, N4 must retain the live state and fail closed.

The inactive state uses the canonical current marker
`trigger_mark_candidate=normal`; the previous active marker remains available as
`previous_trigger_mark_candidate`. Its projection fields are always
`projection_30m_flag=false` and `projection_30m_type=none`. This preserves an
earlier HINT marker (`30m_volume` / `30m_shrink`) without writing an invalid
current marker.

## 4. 本地 context snapshot

建议物理分表：

```text
stock_trigger_context_snapshot
index_trigger_context_snapshot
board_trigger_context_snapshot
```

N4-0 schema 草案采用以下逻辑表族：

```text
common_trigger_run
stock_trigger_context_snapshot
index_trigger_context_snapshot
board_trigger_context_snapshot
common_trigger_state
common_trigger_match
common_trigger_quality_item
```

说明：

```text
trigger_context_snapshot 逻辑上是 N4 本地化 context，物理上继续按 stock / index / board 分表。
trigger_state / trigger_match 是 N4 触发事实，不生成动作、不写用户投影、不播语音、不写 sim。
正式表名不得使用 *_runtime；runtime 只表示部署位置和生命周期，不进入表名。
```

最小字段：

```text
trigger_context_id
source_condition_run_id
source_condition_pool_id
source_condition_basis_id
source_minute_target_scope_id
source_market_subscription_id
asset_kind
identity_key
code
name
direction
condition_key
allowed_signal_types
prev_up_str
prev_dn_str
period_transition_y
period_transition_q
period_transition_m
period_transition_w
period_transition_d
amount_y
amount_q
amount_m
amount_w
amount_d
previous_amount_y
previous_amount_q
previous_amount_m
previous_amount_w
previous_amount_d
period_trigger_baseline_json
buy_target_price
sell_target_price
clear_sell_ref_period
previous_day_minute_date
policy_hash
context_hash
created_at
```

N4 worker 可以把这些表加载成内存字典：

```text
(identity_key, direction) -> context list
(identity_key, direction, condition_key) -> context
```

重启后从本地 runtime PostgreSQL 恢复，不回读外接盘。

## 5. 触发判定

### 5.1 普通买入

```text
condition_key = BUY:...
N3 event = MarketSnapshotUpdated
signal_type = B_BUY
```

N4 用 N2 本地 context 的周期、金额基准和 N3 realtime snapshot 判断是否满足当前日触发。

N4 判断周/月/季/年实时升级时，必须使用 `period_trigger_baseline_json` 中冻结的 previous_entity_high / previous_entity_low / previous_avg_amount 与 N3 标准行情事实比较，不得临时回查 N1 日 K。

普通 formal BUY/SELL 的 canonical 规则如下：

```text
BUY:P  price_pass = current_price/current_close > P.trigger_previous_entity_high
SELL:P price_pass = current_price/current_close < P.trigger_previous_entity_low

BUY:P target_transition = volume_up
SELL:P target_transition = low_volume_down

transition_upgrade_pass =
  previous_transition != target_transition
  AND current_transition == target_transition
```

其中 `current_transition` 必须按 N2 分级语义重新判断：

```text
BUY:P current_transition=volume_up:
  price_pass
  AND current_period_avg_with_today > N2 previous complete same-period amount

SELL:P current_transition=low_volume_down:
  price_pass
  AND current_period_avg_with_today < N2 previous complete same-period amount
```

N2 previous complete same-period amount 只允许从本地化
`period_trigger_baseline_json.periods[P]` 读取，字段优先级为：

```text
previous_avg_amount
previous_amount
previous_amount_baseline
classification_previous_amount_baseline
```

不得使用 `trigger_previous_amount_baseline` 或任何 `current_*seed` 字段作为
上一完整周期金额。

D/W/M/Q 还必须通过第二道触发金额链：

```text
D BUY: today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg
W BUY: weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg
M BUY: monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
Q BUY: quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg

D SELL: today_virt_amount <= weekly_avg_with_today <= prev_weekly_avg
W SELL: weekly_avg_with_today <= monthly_avg_with_today <= prev_monthly_avg
M SELL: monthly_avg_with_today <= quarterly_avg_with_today <= prev_quarterly_avg
Q SELL: quarterly_avg_with_today <= yearly_avg_with_today <= prev_yearly_avg
```

Y 年周期没有上级触发金额链，因此第三道金额链门是
`not_applicable` / `no_upper_period_chain_noop`。这不是失败，也不是
`always_true_for_Y`。Y 是否进入 `triggered_periods` 只由自己的
`price_pass && transition_upgrade_pass` 决定。

最终 formal pass：

```text
D/W/M/Q formal_pass = price_pass && transition_upgrade_pass && trigger_amount_chain_pass
Y formal_pass       = price_pass && transition_upgrade_pass
```

### 5.2 30 分钟放量买入

```text
condition_key = BUY:... 或 BUY:FULL
N3 input = realtime projection metric / MinuteBarClosed / closed 30m summary
signal_type = B_BUY_30M_VOL
```

### 5.3 超跌买入

```text
condition_key = BUY_HINT
N3 input = realtime projection metric / MinuteBarClosed / closed 30m summary
确认条件 = projection 放量上涨或强确认放量上涨
signal_type = BUY_HINT
```

BUY_HINT 是正式买入触发信号类型。是否最终买入、只提示或进入 sim，不在 N4 决定。

### 5.4 普通卖出

```text
condition_key = SELL:...
N3 event = MarketSnapshotUpdated
signal_type = S_SELL
```

### 5.5 30 分钟缩量卖出

```text
condition_key = SELL:... 或 SELL:FULL
N3 input = realtime projection metric / MinuteBarClosed / closed 30m summary
signal_type = S_SELL_30M_SHRINK
```

### 5.6 超涨卖出

```text
condition_key = SELL_HINT
N3 input = realtime projection metric / MinuteBarClosed / closed 30m summary
确认条件 = projection 缩量下跌或强确认缩量下跌
signal_type = SELL_HINT
```

SELL_HINT 是正式卖出触发信号类型。是否最终卖出、只提示或进入 sim，不在 N4 决定。

### 5.7 FULL

```text
BUY:FULL -> B_BUY / B_BUY_30M_VOL
SELL:FULL -> S_SELL / S_SELL_30M_SHRINK
trigger_period = D
```

FULL 不混写为普通 BUY:D / SELL:D。FULL 固定 D-only，并且必须复用 D 的
price gate、transition upgrade gate 和 trigger amount-chain gate；不得绕过
普通 D formal 规则。

## 6. 输出事件

### 6.1 TriggerMatched payload

```text
run_id
trigger_event_id
trigger_state_id
source_event_id
source_condition_run_id
source_condition_pool_id
source_condition_basis_id
source_market_subscription_id
asset_kind
identity_key
direction
signal_type
condition_key
trigger_price
trigger_time
trigger_period
data_quality_status
context_hash
```

N4 标准输出事件 payload 必填公共字段：

```text
run_id
source_event_id
identity_key
asset_kind
direction
condition_key
trigger_period
data_quality_status
```

### 6.2 TriggerCleared

用于触发状态失效或撤销。

### 6.3 TriggerPendingMarketData

用于行情缺失、延迟或质量不足。

N4 不应越界补行情。

### 6.4 N4-0 event contract

输入事件只接受：

```text
MarketSnapshotUpdated
MinuteBarClosed
MarketDataDelayed
MarketDataMissing
```

输出事件只允许：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

边界：

```text
N4 不输出 ActionEvent / HintEvent / RiskEvent / PositionEvent。
N4 不输出 User* / Voice* / Sim* 事件。
BUY_HINT / SELL_HINT 是正式买卖触发候选，是否买卖、只提示、进 sim 或真实交易由 N5/N6 决定。
```

## 7. 幂等和去重

N4 去重建议：

```text
trade_date + identity_key + direction + signal_type + condition_key + trigger_bucket
```

普通日 K 触发：

```text
trigger_bucket = trading_day
```

projection / 30m 类触发：

```text
trigger_bucket = projection_window_id 或 30m_window_start / 30m_window_end
```

同一 dedup key 重复消费必须幂等跳过。

## 8. 开发阶段

```text
N4-0：schema + event contract
N4-1：trigger schema gap / migration review
  只读检查当前 DB 是否缺 N4 表，审查 010 migration 是否 additive-only，生成 backup / rollback 要求。
  不执行 migration，不写 trigger_context_snapshot，不消费 N3 event。
N4-2：执行 010 trigger schema migration
N4-3：trigger_context_snapshot execute
N4-4：run-once consume synthetic / sample N3 event dry-run
N4-5：run-once execute 写 TriggerMatched outbox
N4-6：bounded worker smoke
N4-7：长期 worker / 启动编排，后置
```

长期 worker 必须后置，先用 run-once 和 bounded worker 验证。

## 9. Worker 要求

bounded worker 必须具备：

```text
max_runtime_minutes
stop_file
heartbeat/status_json
consumer_checkpoint
recent_event_summary
error_count
lag metrics
```

N4 worker 不得无界运行到无法停机。

N4 proof-discovery launchd worker 必须通过
`--lineage-config docs/runtime/current_intraday_worker_lineage.json` 获取有效
for_trade_date/source_trade_date、N2 run 和 N4 context。config 只能由 post-close Fast Lane
`EXECUTE_PASS` 后更新；config 缺失、disabled、malformed 或 lineage mismatch 时必须
fail closed，不得静默回退到 installed plist 中的旧日期。实时 launchd 模式仍必须保持
`--selection-mode realtime_latest_only`，旧 backlog 只能进入显式 catch-up gate。

## 10. P0 规则

```text
P0: N4 盘中直接读取外接盘 N2 作为高频触发路径
P0: N4 直接调用 mootdx / Tushare / 外部行情接口
P0: N4 使用未闭合分钟 K 生成正式触发
P0: N4 自行拼原始分钟或自造 realtime projection 指标
P0: N4 写 action / user projection / voice / sim
P0: BUY_HINT / SELL_HINT 被当成非正式提示而不生成 TriggerMatched
P0: 普通 BUY/SELL/FULL 把 MinuteBarClosed 当主输入
P0: N3 标准化、可追溯 realtime projection 指标和 N4 projection matcher 未落地时，把 B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT 写成正式 TriggerMatched
P0: 触发事实写入后没有同事务 outbox
P0: consumer 非幂等或缺 checkpoint
```

## 11. 回滚

N4 execute 必须按 run_id 可回滚：

```text
删除 trigger_event
删除 trigger_state 或回滚到上一 active state
删除 common_trigger_quality_item
删除 common_event_outbox 中 source_run_id 对应事件
删除 common_trigger_run
```

回滚不得触碰 N1/N2/N3 事实。
