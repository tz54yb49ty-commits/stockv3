# A股监控系统 v3 整体分层架构

版本：V0.1
日期：2026-05-27
阶段：总体架构边界

## 1. 总目标

v3 的目标是把交易监控系统拆成可追溯、可回滚、低耦合的分层链路。

核心链路：

```text
入库层 -> 条件层 -> 行情范围层 -> 实时行情层 -> 触发层 -> 动作层 -> 用户层
```

总控控制面：

```text
runtime_control -> pipeline state / manual gate / dashboard / command registry / rollback registry / timeline
```

`runtime_control` 不属于业务数据链路，不生产 N1-N6 事实，不执行 N1-N6 命令，不修改 N1-N6 execute contract。

核心边界：

```text
条件层数据允许用户层在交易时段查询。
触发层和动作层数据与用户层隔离。
用户层只能被动接收动作层投递的标准事件，不能主动查询触发/动作裸表。
```

## 2. 分层职责

### 2.0 Runtime Control

职责：登记 runtime pipeline run/stage、`WAIT_MANUAL_CONFIRM` manual gate、execute command registry、rollback registry、pipeline timeline 和 dashboard v0。

输出：

```text
runtime_pipeline_run
runtime_pipeline_stage
runtime_execute_command_registry
runtime_rollback_registry
runtime_pipeline_timeline
dashboard v0
```

硬边界：

```text
只登记和展示。
不执行 nightly run。
不执行 registry command。
不执行 rollback SQL。
不连接数据库写 N1-N6 事实。
不修改 N1-N6 execute contract。
不消费 outbox。
不启动 worker。
不写用户层、语音、mobile、sim、position、真实交易。
```

### 2.1 入库层

职责：接收、清洗、定稿官方事实数据。

输入：

```text
stock / index / board 日线
stock 财务和市值
index / board 成分
交易日历
```

输出：

```text
common_active_source_version
stock_* fact
index_* fact
board_* fact
```

硬边界：

```text
只负责事实入库和 source_version 激活。
不计算条件。
不生成触发。
不生成动作。
不写用户层投影。
```

### 2.2 条件层

职责：基于已激活的入库事实，计算“哪些对象具备后续观察资格”。

输出：

```text
condition_basis
condition_pool
minute_target_scope
condition_display_basis
```

语义补充：

```text
condition_basis：全量条件审计根，必须包含 N4 真实触发所需的周期阈值 period_trigger_baseline_json。
condition_pool：默认/手动 policy 筛选后的条件资格池，继承必要静态结构和 baseline trace。
minute_target_scope：现有正式表名，canonical 语义等价 trigger_target_scope，是交易链路范围表。
condition_display_basis：N2 生成的 N6 展示输入，一对象一行优先，只读给用户层展示，不进入 N3/N4/N5。
```

对称性目标价 canonical spec：

```text
docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md
```

N2 只拥有对称性目标价候选与静态 trace：

```text
symmetry_anchor
amplitude_source_period
A 段识别
base_price_policy
reference_target_price
secondary_target_price
up_sell_reference_period
down_buy_reference_period
```

`locked_target_price` / `target_lock_status` 属于 N6/position，不属于 N2。

用户层权限：

```text
优先只读查询 condition_display_basis；必要时可只读 condition_basis / condition_pool 的摘要和解释字段。
可以展示目标价、上涨卖出参考周期/下跌买入参考周期、推荐、指数/行业上下文。
不得修改条件层数据。
```

硬边界：

```text
条件层不拉一分钟 K。
条件层不判断实时触发。
条件层不生成动作。
条件层不写语音、mobile、sim、position。
```

### 2.3 行情范围层

职责：根据条件层输出决定后续需要哪些实时行情对象。

输出：

```text
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

语义：

```text
minute_target_scope 是条件来源明细表，不是最终行情拉取任务表，也不是触发层输入表。
它声明哪些对象需要实时日 K / 快照，哪些对象在动作层可能需要一分钟 K。
它也声明哪些对象需要预加载前一交易日一分钟 K。
它允许保留 asset_kind + identity_key + direction + condition_key 粒度，用于审计、展示和追溯。
它不承载用户展示冗余字段；用户展示由 N6 基于条件摘要和动作事件生成投影。
`minute_target_scope` 是 legacy 表名，交易链路语义上等价 `trigger_target_scope`。
条件层只写范围和验收要求，不拉行情，不判断触发。
```

硬边界：

```text
只声明范围。
真正行情拉取属于实时行情层。
实时行情层不得按 minute_target_scope 明细行逐行拉行情。
实时行情层必须先按 asset_kind + identity_key + required_data_kind + for_trade_date 去重生成 market_data_subscription。
触发层不得直接根据 minute_target_scope 自行拉取一分钟 K。
```

### 2.4 实时行情层

职责：统一拉取、缓存并定稿交易日内的行情事实，供触发层和动作层只读。

详细开发文档：`docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md`。

N3/N4/N5 action confirmation canonical rule：`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`。

输出：

```text
realtime_daily_snapshot
minute_bar_1m
previous_day_minute_bar_1m
previous_day_minute_preload_status
market_data_quality_item
action-confirmation projection facts
```

分工：

```text
触发层只读 realtime_daily_snapshot / 实时日 K 快照。
动作层只读 minute_bar_1m / previous_day_minute_bar_1m。
用户层只读用户投影和必要行情展示投影。
```

硬边界：

```text
实时行情层是唯一行情拉取者。
前一交易日一分钟 K 由实时行情层在盘前根据去重后的 market_data_subscription 预加载。
market_data_subscription 必须保留 source_scope_ids / source_condition_pool_ids 追溯。
触发层、动作层、用户层都不得直接调用外部行情接口。
行情缺失时写 missing_market_data / pending，不越层抓取。
N3 owns action-confirmation projection facts; N4/N5 must not assemble 1m/5m/30m/120m indicators from raw minute rows.
```

消费口径：

```text
condition_pool / minute_target_scope：object + direction + condition_key。
market_data_subscription：asset_kind + identity_key + required_data_kind + for_trade_date。
```

N3 子阶段：

```text
N3-0：market_data_subscription dry-run / preflight。
  从 active condition run 的 minute_target_scope 生成去重订阅计划。
  只输出 candidate / dedup / pull_plan，不拉行情，不写行情表。

N3-A：previous_day_minute_bar_1m preload。
  按 N3-0 去重订阅结果，预加载前一交易日一分钟 K。

N3-B：realtime_daily_snapshot。
  盘中维护实时日 K / 快照，供触发层只读。

N3-C：today minute_bar_1m。
  盘中维护今日一分钟 K，供动作层只读。
```

### 2.5 触发层

职责：读取条件池和实时日 K / 行情快照，判断是否触发。

输入：

```text
trigger_context_snapshot（由 N4 启动前从 N2 minute_target_scope -> condition_pool -> condition_basis 本地化）
realtime_daily_snapshot
MinuteBarClosed / N3 30分钟确认摘要（仅 30 分钟确认信号）
```

输出：

```text
trigger_event
trigger_state
```

用户层权限：

```text
用户层不能直接查询 trigger_event / trigger_state 裸表。
用户层只能看到动作层或用户投影层投递后的结果。
```

硬边界：

```text
触发层普通 BUY/SELL/FULL 不依赖实时一分钟 K；`B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 四类 30 分钟确认信号例外，N4 可以消费 N3 标准闭合分钟事件或 N3 30 分钟确认摘要完成正式触发。N4 不得直接拉行情，也不得使用未闭合或非 N3 标准分钟事实。
N4 只消费 N3 标准 action-confirmation projection facts 判断 live/trigger/30m marker；不得临时计算 1m/5m/30m/120m 指标。
触发层不得重算条件层静态结构字段。
触发层不得回查 N1 历史日 K 来计算上一周期实体上沿/下沿；这些阈值必须来自 N2 的 `period_trigger_baseline_json` 或 N4 本地化副本。
触发层不得写用户层 projection。
触发层不得生成 sim_trade。
```

### 2.6 动作层

职责：读取触发事件，结合分钟 K 和持仓策略生成标准动作事件。

输出：

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

用户层权限：

```text
用户层不能主动查询 action 裸表。
用户层只能被动接收动作层投递的事件或用户层投影。
```

硬边界：

```text
动作层不得回写 condition_basis / condition_pool。
动作层不得把内部候选、半成品动作直接暴露给用户层。
动作层只消费 N3 标准 action-confirmation projection facts + N4 TriggerMatched 做最终确认；不得信任 opaque action_confirmation payload，不得临时计算或拉取 raw minute 指标。
```

### 2.7 用户层

职责：展示、播报、模拟账户、用户确认和筛选。

输入：

```text
条件层只读查询接口
动作层投递事件
用户层 projection
```

允许：

```text
查询条件层摘要。
接收动作事件。
展示 mobile projection。
执行前台语音。
维护用户侧已读、静音、筛选、模拟账户投影。
```

禁止：

```text
主动查询触发层裸表。
主动查询动作层裸表。
回写条件层字段。
影响触发判断和动作生成。
```

### 2.8 N3-N6 Event Contract / Outbox-Inbox

v3 从 N3 到 N6 采用标准事件流作为跨层协议。

核心原则：

```text
事实和事件同事务产生。
事件是跨层协议。
表是本层事实和投影。
```

明确禁止：

```text
禁止先发事件再落事实。
禁止下游直接扫上游内部事实表来替代标准事件消费。
禁止页面、语音、模拟账户直接拼 trigger/action 裸表。
```

标准写法：

```text
BEGIN;
  写本层事实表或投影表；
  写 common_event_outbox；
COMMIT;
```

N3-N6 事件链路：

```text
N3 行情层
  写 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m / quality/status
  同事务写 MarketSnapshotUpdated / MinuteBarClosed / MinuteBarCorrected / MarketDataDelayed / MarketDataMissing / MarketDisplaySnapshotUpdated

N4 触发层
  只消费 N3 标准事件
  写 trigger_event / trigger_state
  同事务写 TriggerMatched / TriggerCleared / TriggerPendingMarketData

N5 动作层
  只消费 N4 标准事件
  写 action / position / risk 事实
  同事务写 ActionEvent / HintEvent / RiskEvent / PositionEvent

N6 用户层
  消费 N5 标准动作事件
  写 user_card_projection / user_voice_delivery / user_device_ack / sim_projection
  消费 N3 MarketDisplaySnapshotUpdated
  写 user_market_projection
  手机、语音、模拟账户只看用户投影
  语音只来自 N5 ActionEvent / HintEvent / RiskEvent / PositionEvent
```

N3-N6 双速链路：

```text
高实时链路：
  N3 -> N4 -> N5 -> N6
  用于触发、动作、语音、卡片，目标 1-3 秒。

低频展示链路：
  N3 -> N6
  用于 user_market_projection 行情展示字段。
  默认完整 1 分钟 K 后发布；未来当前价展示可以 30 秒节流发布。
  不触发语音，不生成动作卡片，不反向影响 N3/N4/N5。
```

N3 事件边界：

```text
MarketSnapshotUpdated：实时快照写入后立即 outbox，是 N4 买卖触发的主输入。
MinuteBarClosed：完整 1 分钟 K 闭合并写入后 outbox。普通 BUY/SELL/FULL 只用于解除 TriggerPendingMarketData、行情修正通知、触发状态行情可用性、辅助回放/对账，以及 N5 精确读取分钟上下文；`B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 四类 30 分钟确认信号可由 N4 使用闭合分钟事件或 N3 30 分钟确认摘要生成正式触发。
MinuteBarCorrected：已写分钟 K 被修正后 outbox，必须带原 dedup_key 和修正原因。
MarketDataDelayed / MarketDataMissing：quality/status fact 写入后 outbox。
MarketDisplaySnapshotUpdated：行情展示投影材料已更新，供 N6 生成 user_market_projection。
```

允许的基础事件表族：

```text
common_event_ledger
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
```

事件必填字段：

```text
event_id
event_type
asset_kind
identity_key
trade_date
event_time
source_layer
source_run_id
dedup_key
partition_key
event_schema_version
payload_json
created_at
```

N3 事件 payload 必须包含：

```text
subscription_id
pull_plan_id
run_id
source_adapter
data_quality_status
snapshot_id / minute_bar_id / quality_item_id，按事件类型至少提供一个
```

用户投影建议字段：

```text
user_projection_id
event_id
display_group
display_rank
first_seen_at
latest_seen_at
repeat_count
is_latest
voice_policy
voice_delivered
device_ack
```

幂等、顺序和投递规则：

```text
event_id 稳定。
dedup_key 稳定。
identity_key 用于分区，同一对象事件顺序必须稳定。
event_schema_version 必填。
consumer 必须按 event_id / dedup_key 幂等。
projection 必须可由 event ledger 重建。
ack / watermark 必须明确。
语音只播 watermark 后的新事件。
开启语音最多补播 1 条。
```

技术路线：

```text
当前 v3 默认：PostgreSQL event ledger + outbox / inbox + worker 轮询或批处理。
中期增强：Redis Streams 或 NATS JetStream。
大规模分布式：Kafka / Redpanda + Flink。
```

无论未来消息中间件如何替换，标准事件合同、投影合同和幂等规则不得推倒重来。

## 3. 接口边界

### 3.1 条件层 -> 用户层

允许只读查询：

```text
GET /api/conditions/basis?for_trade_date=YYYYMMDD
GET /api/conditions/pool?for_trade_date=YYYYMMDD
GET /api/conditions/coverage?for_trade_date=YYYYMMDD
GET /api/conditions/quality?run_id=...
```

用途：

```text
查看候选资格。
解释为什么进入条件池。
展示目标价、上涨卖出参考周期/下跌买入参考周期、财务评分、指数/板块上下文。
```

### 3.2 触发层 -> 动作层

内部接口，不对用户层开放：

```text
TriggerEvent
TriggerState
```

触发层只通过标准事件向动作层提供决策输入，不直接面向用户展示。

### 3.3 动作层 -> 用户层

单向事件投递：

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

事件进入用户层后再形成：

```text
common_event_inbox
user_card_projection
user_voice_delivery
user_device_ack
sim_projection
replay_projection
```

行情展示投影：

```text
user_market_projection
```

### 3.4 用户层 -> 系统

用户层只能提交用户操作，不参与交易决策：

```text
已读 / 静音 / 筛选 / 页面设置 / 手动模拟操作
```

这些操作不得回写触发层或动作层判断依据。

## 4. 数据库边界

运行事实库使用 PostgreSQL。

v3 按运行态与历史归档拆分存储位置：

```text
N1/N2 历史事实、Parquet 归档、manifest、盘后审计导出：
  /Volumes/MacRaid/database

N3 实时行情层运行态数据：
  本地 SSD PostgreSQL
  不写入 /Volumes/MacRaid/database
  不和 N1/N2 外接盘历史事实、归档、Parquet 混放
```

N3 本地 runtime database 建议：

```text
数据库：PostgreSQL
部署：独立本地 PostgreSQL cluster 或至少独立 database
建议 database 名：ashare_v3_runtime 或 ashare_v3_n3_runtime
数据目录：本机内置 SSD，不使用外接盘路径
适用数据：market_data_subscription、pull_plan、realtime_daily_snapshot、minute_bar_1m、previous_day_minute_bar_1m、quality、event ledger/outbox/inbox、consumer checkpoint
```

归档责任边界：

```text
N1/archive 是 N1_ingestion 内的归档职责名称，不是新的 layer_role。
N3_market_data 负责盘中本地 runtime、事件 outbox、质量项、run/trade_date 封账和 archive_request 元数据。
N3_market_data 不直接写 Parquet，不写 manifest，不写 /Volumes/MacRaid/database。
N1_ingestion/archive 负责读取已封账的 N3 runtime 分区，写入 Parquet、manifest、归档审计和 rollback 元数据。
N1_ingestion/archive 不参与 N3 盘中行情拉取、事件投递、触发/动作/用户投影。
N3 只能在 N1/archive manifest 校验通过后，按本地保留策略清理旧 runtime 分区。
```

技术取舍：

```text
PostgreSQL：N3/N4/N5/N6 默认运行事实库，支持事务、UPSERT、分区、索引、outbox/inbox、checkpoint。
DuckDB：只用于离线分析、回放、对账、报表，不作为 N3 运行态主库。
Parquet：用于历史归档，不承载 N3 盘中运行态写入。
Redis / NATS / Kafka：可作为未来消息投递增强，不替代 PostgreSQL 事实库。
SQLite / MongoDB / InfluxDB：不得作为 v3 主运行事实库，除非后续另行确认。
```

建议分层表族：

```text
common_ingest_*
stock_* / index_* / board_* fact
common_condition_*
stock_condition_* / index_condition_* / board_condition_*
stock_minute_target_scope / index_minute_target_scope / board_minute_target_scope
realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m / previous_day_minute_preload_status
common_event_ledger / common_event_outbox / common_event_inbox / common_event_consumer_checkpoint / common_event_delivery_attempt
*_trigger_event / *_trigger_state
*_action_event
user_card_projection / user_market_projection / user_voice_delivery / user_device_ack / sim_projection
```

隔离原则：

```text
stock / index / board 物理分表。
条件层允许用户只读。
触发层和动作层裸表不向用户层开放。
用户层只读投影，不读内部裸表。
N3-N6 跨层只能消费标准事件，不直接扫上游内部事实表。
N3 runtime 数据只落本地 SSD PostgreSQL，不落外接盘。
N3 只生成封账和 archive_request，不直接执行 Parquet 归档。
N3 行情事实表名不得使用 *_runtime；runtime 只表示部署和生命周期属性。
N3 事件不得使用 User* 命名；低频展示事件统一命名为 MarketDisplaySnapshotUpdated。
N4 不能把 `MinuteBarClosed` 作为普通 BUY/SELL/FULL 的主输入；四类 30 分钟确认信号 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 例外。
```


## 4.5 N4/N5 运行方案基准

N4/N5 采用本地 runtime PostgreSQL + event consumer 架构。

```text
N2 = 慢速权威条件源
N3 = 本地行情事实 + 标准事件源
N4 = 本地触发判定 consumer / worker
N5 = 本地动作生成 consumer / worker
N6 = 用户投影 / 语音 / sim / 策略解释
```

### 4.5.1 N4 触发层

N4 启动前必须把 N2 条件上下文本地化：

```text
N2 active condition run
N3 market_data_subscription run
  -> stock/index/board_trigger_context_snapshot
```

盘中 N4 不再访问外接盘 N2，不直接拉行情，只消费 N3 标准事件和本地 context。

N4 输出：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N4 的 30 分钟确认例外：

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

上述四类信号允许 N4 消费 N3 的 `MinuteBarClosed` 或 N3 30 分钟确认摘要完成正式触发。普通 BUY/SELL/FULL 仍以 `MarketSnapshotUpdated / realtime_daily_snapshot` 为主。

### 4.5.2 N5 动作层

N5 只消费 N4 标准事件：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

N5 可读取 N3 今日/前一日分钟 K 作为动作上下文，但不得外拉行情，不得重算 N4 触发。

N5 输出：

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

`BUY_HINT / SELL_HINT` 是标准买卖动作候选。是否最终买卖、只提示、进入 sim、强语音或真实交易，由 lane / user_policy / position_state 决定，不由 signal_type 名称单独决定。

### 4.5.3 Worker 策略

N4/N5 最终会使用 worker，但必须后置：

```text
run-once dry-run
run-once execute
bounded worker smoke
长期 worker / 启动编排
```

bounded worker 必须有：

```text
max_runtime_minutes
stop_file
heartbeat/status_json
consumer_checkpoint
recent summary
```


## 4.6 闭合分钟 K 动作确认规则

v3 统一采用闭合分钟 K 口径，避免目标机历史链路中“页面时间、信号时间、分钟标签时间”混淆。

```text
1 分钟 K 标签 HH:MM 只表示该分钟区间。
该 K 线只有到 HH:MM+1 后才视为闭合。
未闭合分钟 K 不得生成 MinuteBarClosed。
未闭合分钟 K 不得驱动 N4 TriggerMatched。
未闭合分钟 K 不得驱动 N5 ActionEvent / HintEvent / RiskEvent / PositionEvent。
```

分层含义：

```text
N3：只在完整 1 分钟 K 闭合并写入本地事实表后，才写 MinuteBarClosed outbox。
N4：MarketSnapshotUpdated 可用于实时触发状态；四类 30 分钟确认信号只可消费闭合 MinuteBarClosed 或 N3 闭合 30 分钟确认摘要。
N5：动作确认只读 N3 已闭合分钟 K / 前一日分钟 K；不能用当前未闭合分钟抢先生效。
N6：用户层可以 30 秒刷新行情展示投影，但展示刷新不等于动作确认。
```

允许的边界解释：

```text
14:26 标签的 1 分钟 K，在 14:27 才算闭合。
14:27 之后使用 14:26 K 生成分钟确认，是合法的闭合分钟动作。
14:26 分钟正在形成时使用它生成动作，是 P0。
```

## 5. 标准信号边界

v3 底层标准信号只保留 6 类：

```text
B_BUY_30M_VOL
B_BUY
S_SELL_30M_SHRINK
S_SELL
BUY_HINT
SELL_HINT
```

用户层解释类型不进入条件层和底层标准信号：

```text
POS_CLEAR
BUY_FAIL_CLEAR
ADD_BUY_FAIL_REDUCE
POS_REDUCE
```

这些由用户层/持仓策略层根据动作事件、持仓、清仓参考周期解释。

## 6. 质量闸门

P0：

```text
用户层直接查询 trigger/action 裸表。
用户层回写 condition_basis / condition_pool。
触发层或动作层重算条件层静态结构字段。
触发层或动作层把半成品候选暴露到用户层。
条件层输出 POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE。
N3-N6 下游直接扫上游内部事实表替代标准事件消费。
本层事实写入后未在同一事务写入对应 outbox event。
标准事件缺少 event_id / dedup_key / event_schema_version。
consumer 非幂等或缺少 checkpoint / ack / watermark。
语音绕过 user_voice_delivery 直接播 trigger/action 裸事件。
N3 实时行情、分钟 K、事件流或质量项写入 /Volumes/MacRaid/database 等外接盘路径。
N3 直接写 Parquet、manifest 或 N1/N2 历史归档目录。
N3 正式行情事实表使用 *_runtime 命名。
N3 事件使用 User* 命名。
N4 将 `MinuteBarClosed` 作为普通 BUY/SELL/FULL 的主输入，或绕过 N3 标准事实直接使用分钟 K。四类 30 分钟确认信号 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 可使用 N3 闭合分钟事件或 N3 30 分钟确认摘要。
N3 标准事件 payload 缺少 subscription_id / pull_plan_id / run_id / source_adapter / data_quality_status / snapshot_id / minute_bar_id / quality_item_id 中按事件类型要求的追溯字段。
```

P1：

```text
用户层 projection 缺少对应 ActionEvent 来源。
条件层 API 字段缺解释原因。
动作层事件没有进入用户投影但未造成交易决策错误。
```

## 7. 阶段推进

N1：入库层。

N2：条件层。

N3：行情范围层与实时行情层。

N3 详细开发文档：`docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md`。

N3-0：market_data_subscription dry-run / preflight，不拉行情、不写行情表。

N3-A：根据去重订阅结果预加载前一交易日一分钟 K。

N3-B：盘中维护实时日 K / 快照。

N3-C：盘中维护今日一分钟 K。

N4：触发层，仅读实时日 K / 快照。

N5：动作层。

N6：用户层 projection / 语音 / 模拟账户。

任何阶段不得越层写入后续层正式表。若为了测试需要模拟后续层，必须使用 dry-run / shadow / 临时表，并在报告中标明。


### N2 静态参考周期字段口径

N2 条件层 canonical 字段为：

```text
buy_target_price + up_sell_reference_period
sell_target_price + down_buy_reference_period
```

`clear_sell_ref_period` 是 N5 持仓迁移期兼容 alias，不再作为 N2 的主语义字段。

对称性目标价字段口径以 `docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md` 为准：

```text
symmetry_anchor / amplitude_source_period / base_price_policy 由 N2 冻结。
reference_target_price 是 N2 主目标价候选。
secondary_target_price 是 N2 可选次级目标价候选。
现有 buy_target_price / sell_target_price 是 reference_target_price 的兼容映射。
locked_target_price / target_lock_status 只属于 N6/position。
```

N2-R4 起，N2 还必须提供：

```text
period_trigger_baseline_json
```

该字段冻结 N4 判断实时周期升级所需的历史阈值，例如 previous_entity_high / previous_entity_low / previous_avg_amount / current_amount_seed。N4 只使用该冻结阈值与 N3 标准行情事实比较，不重算历史 K。

### 3.1.1 condition_display_basis

N2 四表输出后，用户层展示输入统一走 `condition_display_basis`：

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

`condition_display_basis` 由 N2 在同一个 run_id 内从 `condition_basis / condition_pool / minute_target_scope` 派生，保留展示所需的完整解释字段和追溯 id 数组。N6 只读该表生成用户展示和筛选，不直接读取 N3/N4/N5 裸表，也不要求 N6 自己 join N2 三张内部链路表。

`condition_display_basis` 不参与：

```text
N3 market_data_subscription
N4 trigger_context_snapshot
N5 action_fact / action_event
```
