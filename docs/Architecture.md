# A股监控系统 v3 总控架构

更新日期：2026-07-22
范围：总控视角，只整理当前架构、数据流、事件流和权威 lineage。本文档不替代 `AGENTS.md`、各层设计文档、执行报告或 JSON 证据。

## 1. 一句话架构

```text
N1 入库层 -> N2 条件层 -> N3 实时行情层 -> N4 触发层 -> N5 动作层 -> N6 用户层
```

v3 的核心原则是：上游只产生可追溯事实，下游只消费正式合同；跨层要么走只读摘要接口，要么走标准事件，不允许下游直接扫上游内部裸表来替代事件消费。

`runtime_control` 是 N1-N6 之外的总控控制面，只登记 runtime pipeline state machine / dashboard / command registry / rollback registry / timeline，不执行 N1-N6 命令，不修改 N1-N6 execute contract。dashboard v0.2 已新增 20260602 action-confirmation timeline detector：保留 20260527 nightly v0 七阶段，同时在 `/runtime/20260602` 和 `/api/runtime/20260602/dashboard` 只读展示 9 阶段 all PASS、N5 pending outbox=ActionExecuted 4 / ActionBlocked 1、N6 shadow rows=1/5/5/5、N2-N6 rollback paths complete；routes 仍只有 GET/HEAD，无 form、无 execute button。

### 1.1 N6 B轨交付主线与三通道

N6 B轨的唯一候选发布主线为
`codex/n6-btrack-integration`，对应隔离工作树
`/Users/chuanfuchen/Documents/A股监控系统v3_n6_btrack_integration`。临时需求
从当前生产权威基线分出，验证后只能汇入该主线；脏主工作树继续
preserve-only。

普通需求必须复用以下三条交付通道：

| 通道 | policy_id | 边界 |
|---|---|---|
| L1 | `n6_btrack_delivery_l1_web_readonly_v1` | 页面、文案、只读查询、筛选展示；无数据库和交易 runtime |
| L2 | `n6_btrack_delivery_l2_n6_business_v1` | N6 schema、监控范围、策略配置、虚拟账户业务规则；migration 与 Release 分 gate |
| L3 | `n6_btrack_delivery_l3_virtual_runtime_v1` | executor、自动止损、申请或资金/持仓变化；bounded smoke、队列治理和持续运行授权分离 |

服务基线登记在 `docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json`。本次登记只确认
Web、quote writer/executor、stop-loss 仍为三条分叉 lineage，且同时存在两个
不同的 `087` migration 文件；它不授权部署或自动合并。正常目标是四个服务从
同一 commit 构建；确需不同 commit 时必须登记兼容原因和关键 blob 证明。

`n6_btrack_service_lineage_convergence_v1` 已在独立候选分支完成离线文件级
收敛：只从 `edfb66d2…` 导入 stop-loss 087 四文件、从 `17d30207…` 导入
088 四文件，没有 merge/cherry-pick 完整 quote/stop lineage。版本化身份清单
`N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1` 同时保留 Web archive 087
和 stop-loss 087 的原路径、Git blob 与 SHA256，migration 选择必须使用完整
文件身份，不得按数字 glob、静默改号、覆盖或改写历史。Registry 已纠正
quote→stop-loss merge-base 为 `658ebb39…`；生产状态仍为 `FRAGMENTED`、
`database_state=NOT_READ`、`deployment_authorized=false`。本候选不表示统一
生产 Release，也不授权数据库、migration 或服务操作。

受管活跃工作树目标不超过 5 个：生产集成、当前开发、当前治理、紧急修复和
验收。已有工作树只能在 commit、测试、rollback、tracked/untracked/ignored
均为零的证据冻结后归档，不得批量删除或改写用户文件。

## 2. 分层职责

| 层级 | layer_role | 职责 | 当前边界 |
|---|---|---|---|
| Runtime Control | `runtime_control` | runtime pipeline run/stage、WAIT_MANUAL_CONFIRM、dashboard v0/v0.2、execute command registry、rollback registry、pipeline timeline | 只登记和展示；不执行 nightly run，不连接数据库写业务事实，不改 N1-N6 execute contract |
| N1 | `N1_ingestion` | 外部原始数据、标准事实表、质量闸门、active source version、Parquet 归档、回滚审计 | 不计算条件，不拉盘中分钟 K，不写触发/动作/用户层 |
| N2 | `N2_condition` | 基于 N1 active fact 生成 `condition_basis`、`condition_pool`、`minute_target_scope`、`condition_display_basis`，并冻结对称性目标价候选 | 不拉行情，不生成触发，不写动作、锁价、语音、sim、用户投影 |
| N3 | `N3_market_data` | 从 N2 scope 去重生成行情订阅，拉取实时快照、今日分钟 K、前一日分钟 K，写 N3 标准事件，并生产 action-confirmation projection facts | 不改条件，不写 trigger/action/user，不直接写 Parquet 归档 |
| N4 | `N4_trigger` | 本地化 N2 context，消费 N3 标准事件，生成 `TriggerMatched` / `TriggerPendingMarketData` | 不拉行情，不写 action/user/sim，不重算目标价、不锁价 |
| N5 | `N5_action` | 消费 N4 标准事件，生成 action / hint / risk / position 标准事件 | 不改 N1-N4，不写用户投影，不播放语音，不真实交易，不重算目标价、不锁价、不决定清仓 |
| N6 | `N6_user` | 用户投影、语音策略、mobile/card projection、sim shadow、持仓目标价解释；受控 N6 B 轨虚拟账户与 virtual-executor | 不回写 N1-N5，不直接读 trigger/action 裸表；虚拟执行仅按 `N6_B_TRACK_VIRTUAL_EXECUTOR_GOVERNANCE_V1` 独立 gate 开放，永不连接真实券商 |

### 2.1 N6 B 轨虚拟执行器前向治理登记

自 2026-07-22 起，`N6_B_TRACK_VIRTUAL_EXECUTOR_GOVERNANCE_V1` supersede 过去对“所有 N6 runtime 一律拒绝”的现行治理表述，但不改写任何历史 gate 或历史 BLOCKED 证据。例外只覆盖 N6 自有虚拟账户：

```text
N6_user explicit gate
-> versioned contract + preflight + exact rollback
-> immutable release + exact impact scope
-> bounded virtual-executor smoke PASS
-> confirmed queue governance complete
-> immediate bootout plan frozen
-> persistent virtual-executor eligible
```

proposal 仍由真人在 Web 完成创建与确认两次显式操作；executor 只能消费已确认申请，不能创建或确认申请。claim/apply 两层都必须重新校验开放交易日、交易时段、两分钟内 `passed/ok` 报价、本人 principal/account/scope、现金、服务端预算、100 股取整和 T+1。executor 使用独立 service role，所有 proposal/order/trade/cash/position/lot 必须完整审计并可立即停用。

`runtime_control` 只登记权限和调度交接；migration、release/plist 切换、bounded smoke、队列处理和 executor 启停均只能在明确的 `N6_user` 独立 gate 执行。真实券商、真实订单、N6 回写 N1-N5、自动创建/确认 proposal、AI autonomous real trading 仍永久禁止。

## 3. 数据流

```text
外部数据源 / 本地 TDX txt
  -> N1 PostgreSQL fact + quality gate + active source_version
  -> N1 Parquet data_lake + manifest
  -> N2 condition_basis
  -> N2 condition_pool
  -> N2 minute_target_scope -> N3 market_data_subscription_candidate
  -> N2 condition_display_basis -> N6 display input
  -> N3 market_data_subscription
  -> N3 market_data_pull_plan
  -> N3 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m
  -> N4 trigger_context_snapshot
  -> N4 trigger_state / trigger_match
  -> N5 action_fact / action_event / position_state
  -> N6 user projection
```

`minute_target_scope` 是条件来源明细，不是最终行情拉取任务。N3 必须按 `asset_kind + identity_key + required_data_kind + for_trade_date` 去重生成 `market_data_subscription`，不能按 scope 明细逐行重复拉行情。

## 4. 事件流

N3 到 N6 使用标准事件作为跨层协议：

```text
N3 fact + common_event_outbox
  -> MarketSnapshotUpdated / MinuteBarClosed / MinuteBarCorrected
  -> MarketDataDelayed / MarketDataMissing / MarketDisplaySnapshotUpdated

N4 trigger state/outcome fact + common_event_outbox
  -> TriggerStateChanged / TriggerMatched / TriggerPendingMarketData

N5 action fact + common_event_outbox
  -> canonical action events
  -> historical current-real runs may still show ActionEvent / HintEvent / RiskEvent / PositionEvent

N6 event inbox + user projection
  -> user_card_projection / user_market_projection / user_voice_delivery / sim_projection
```

硬规则：

- 事实和事件必须同事务产生。
- `event_id`、`dedup_key`、`event_schema_version` 必填且稳定。
- consumer 必须幂等，并维护 inbox / checkpoint / watermark。
- N1 -> N6 消息只允许单向流动；下游不得回写、重算或重新解释上游职责。
- N4/N5 不承载 alert-only、voice、mobile、sim 或 trade-intent 用户策略；这些只属于 N6/user policy。
- 语音和手机只看 N6 用户投影，不直接读 N4/N5 裸表。

## 4.1 对称性目标价边界

对称性目标价 canonical spec：

```text
docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md
```

总控口径：

```text
N2 owns:
  symmetry_anchor
  amplitude_source_period
  A 段识别
  base_price_policy
  reference_target_price
  secondary_target_price
  up_sell_reference_period
  down_buy_reference_period

legacy alias:
  clear_sell_ref_period = up_sell_reference_period

N4/N5:
  may carry target fields as immutable context
  must not recompute target price
  must not lock target price
  must not decide clear-position policy

N6/position owns:
  locked_target_price
  target_lock_status
  holding target interpretation
  clear-position display/strategy policy
```

027 N2 symmetry target price canonical compatibility migration status:

```text
migration = sql/027_condition_symmetry_target_price_compatibility_migration.sql
status = passed
touched_tables = 12 N2 tables
new canonical fields exist = true
CHECK constraints validated = true
locked_target_price / target_lock_status absent = true
business row count delta = 0
outbox/inbox/checkpoint delta = 0/0/0
new fields non-null count = 0
rollback_safe = true
rollback_sql = sql/027_condition_symmetry_target_price_compatibility_rollback.sql
next gate = N2 canonical writer/readiness alignment
```

## 5. 核心表族

N1 入库层：

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
common_trade_calendar
stock_identity / index_identity / board_identity
stock_daily_bar_fact / stock_daily_basic / stock_financial_metrics_fact
index_daily_bar_fact / index_membership_fact
board_daily_bar_fact / board_membership_fact
```

N2 条件层：

```text
common_condition_run
common_condition_quality_item
stock/index/board_monitor_target
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
stock/index/board_condition_display_basis
```

N3 行情层：

```text
common_market_data_run
common_market_data_quality_item
common_market_data_subscription_candidate
common_market_data_subscription
common_market_data_pull_plan
stock/index/board_realtime_daily_snapshot
stock/index/board_minute_bar_1m
stock/index/board_previous_day_minute_preload_status
stock/index/board_realtime_projection_metric
stock/index/board_closed_30m_summary
stock/index/board_closed_30m_signal_enrichment
```

事件基础设施：

```text
common_event_ledger
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
```

Runtime control 控制面：

```text
runtime_pipeline_run
runtime_pipeline_stage
runtime_execute_command_registry
runtime_rollback_registry
runtime_pipeline_timeline
```

N4 / N5：

```text
common_trigger_run / common_trigger_quality_item
stock/index/board_trigger_context_snapshot
common_trigger_state / common_trigger_match

common_action_run / common_action_quality_item
stock/index/board_action_fact
common_action_event
common_position_state / common_position_event
```

## 6. 当前权威 active run lineage

截至本文件整理时，最新 N2 condition active run 已推进到 `20260602 -> 20260603`：`condition_layer_20260602_source_20260602_v1` 已 `passed_active`，采用 8782 console broad policy，post-review 已 `POST_REVIEW_PASS`。`20260529 -> 20260601` 的 `condition_layer_20260529_source_20260529_v6` 仍作为 preserved active baseline 证据保留；既有 `20260529` 盘中 N3/N4/N5/N6 运行链路仍保留在 `20260528 -> 20260529` 的旧 v1 lineage，不自动 rebuild，不自动消费或重放：

2026-06-02 post-chain handoff update：N1 `stock_financial_20260529_v2` canonical metrics 已 POST_REVIEW_PASS，并成为 active `stock_financial` source_version。N2 financial canonical v2 已消费该 source_version 并完成 pass-through；随后 N2 symmetry target price target-machine v3 已 active supersede v2，N2 anchor-segment alignment v4 已 active supersede v3，N2 secondary-anchor v5 已 active supersede v4，N2 level score v6 已 active supersede v5。后续 N3 必须基于 v6 单独走 subscription rebuild readiness / execute gate，不自动 rebuild。

```text
Latest N1 stock_financial active =
  stock_financial_20260529_v2
  source_batch_id = stock_financial_canonical_20260529_v1
  previous_source_version = stock_financial_20260529_v1
  financial_metric_version = financial_metric_v1
  rows = 5506
  P0/P1/P2 = 0/8/2
  consumed_by_N2_run = condition_layer_20260529_source_20260529_v2
  latest_N2_active_after_level_score_alignment = condition_layer_20260529_source_20260529_v6
  outbox/inbox/checkpoint_delta = 0/0/0
  rollback_safe = true
  rollback_sql = sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql

Latest N2 source_trade_date = 20260529
Latest N2 for_trade_date = 20260601
N2 active condition run =
  condition_layer_20260529_source_20260529_v6

N2 active status =
  passed_active
  previous_run = condition_layer_20260529_source_20260529_v5
  previous_run_status = superseded
  active_passed_active_count = 1
  P0/P1/P2 = 0/6/3
  common_condition_quality_item = 106
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428
  financial pass-through mismatch basis/pool/scope/display = 0/0/0/0
  canonical_financial_pass_through_mismatch = 0
  finance_sector_warning_rows = 120
  pre_revenue_warning_rows = 1
  000600 golden target price = 12.93
  000543 buy_target_price/reference_target_price = 10.82/10.82
  000543 main_up_anchor/up_reference_period = W/D
  000543 A segment = 20260506 -> 20260529
  000543 segment_low/high = 8.09/9.80
  000543 amplitude/base_price = 1.71/9.11
  000543 trend_break_date = 20260526
  000543 base_window = 20260527 -> 20260529
  000027 buy_target_price/reference_target_price = 8.45/8.45
  outbox/inbox/checkpoint_delta = 0/0/0
  downstream_refs N3/N4/N5 = 0/0/0
  rollback_safe = true
  rollback_sql = sql/N2_level_score_20260529_v6_rollback.sql
  financial_source_version_used_at_execute = stock_financial_20260529_v2

Previous source-date N2 active condition run =
  condition_layer_20260528_source_20260528_v5
  status = passed_active for source_trade_date 20260528 / for_trade_date 20260529

Historical 20260528 source superseded run =
  condition_layer_20260528_source_20260528_v4
  condition_layer_20260528_source_20260528_v3
  condition_layer_20260528_source_20260528_v2
  status = superseded

N2 earlier v1 downstream lineage =
  condition_layer_20260528_source_20260528_v1
  rows and downstream refs preserved = true

N2 v5 status =
  passed_active
  previous_active_run_id = condition_layer_20260528_source_20260528_v4
  previous_active_status = superseded
  passed_active_count = 1
  P0/P1/P2 = 0/3/3
  common_condition_quality_item = 103
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4271/169/875
  minute_target_scope stock/index/board = 4251/169/875
  condition_display_basis stock/index/board = 2011/83/428
  monitor_target stock/index/board = 5506/83/428
  000027 buy_target_price = 8.42
  000027 reference_target_price = 8.42
  000027 main_up_anchor = W
  000027 up_reference_period = D
  000027 up_amplitude = 1.17
  000027 up_base_price = 7.25
  deprecated_signal_rows = 0
  alias mismatch = 0
  invalid reference period = 0
  locked_target_price / target_lock_status absent = true
  outbox/inbox refs = 0/0
  downstream refs N3/N4/N5 = 0/0/0
  N3 not automatically rebuilt = true
  N4/N5/N6 not entered = true
  worker_started = false
  rollback_safe = true
  rollback_sql = sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql

Current downstream lineage remains old v1 until N3 rebuild:

N3 subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

N3 subscription status =
  common_market_data_run.status = passed
  P0/P1/P2 = 0/0/0
  candidate_rows = 5038
  subscription_rows = 2643
  pull_plan_rows = 7
  quality_rows = 34
  objects stock/index/board/total = 2021/9/127/2157
  required_data_kind realtime_daily_snapshot = 2157
  required_data_kind minute_bar_1m = 243
  required_data_kind previous_day_minute_bar_1m = 243
  market_data_pulled = false
  market_data_fact_written = false
  scoped outbox/inbox/checkpoint refs = 0/0/0

A1 previous_day_minute preload run =
  previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

A1 previous_day_minute preload status =
  common_market_data_run.status = passed
  P0/P1/P2 = 0/0/0
  quality_rows = 12
  actual rows stock/index/board/total = 56160/0/2160/58320
  object status stock passed/partial/missing = 234/0/0
  object status index expected_objects/rows = 0/0
  object status board passed/partial/missing = 9/0/0
  fake index pull / fake index rows = 0/0
  event_outbox_written = false
  downstream_layers_touched = false
  worker_started = false
  scoped outbox/inbox/checkpoint refs = 0/0/0

B1 pre-open realtime snapshot fact-only run =
  realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

B1 pre-open realtime snapshot fact-only status =
  common_market_data_run.status = passed
  pre_open_fact_only = true
  live_trading_snapshot_ready = false
  P0/P1/P2 = 0/1/0
  quality_rows = 11
  rows stock/index/board/total = 2021/9/127/2157
  missing/failed = 0/0
  writes_outbox = false
  generated_outbox_events = []
  source_time_missing_or_preopen total/stock/index = 2030/2021/9
  source_time_confirmed board = 127
  P1 warning = n3_b1_pre_open_source_time_not_confirmed
  P0 source date mismatch = 0
  scoped outbox/inbox/checkpoint refs = 0/0/0
  global outbox/inbox/checkpoint unchanged = 105122/20726/4345
  downstream_layers_touched = false
  worker_started = false
  N4/N5/N6 touched = false
  rollback_safe = true
  rollback_sql = sql/N3_B1_realtime_snapshot_20260529_rollback.sql

B1 live1 realtime snapshot fact-only run =
  realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

B1 live1 realtime snapshot fact-only status =
  common_market_data_run.status = passed
  live_trading_snapshot_ready = true
  pre_open_fact_only = false
  P0/P1/P2 = 0/0/0
  quality_rows = 11
  rows stock/index/board/total = 2021/9/127/2157
  missing/failed = 0/0
  writes_outbox = false
  generated_outbox_events = []
  stock source_time effective_quote_present/source_time_missing/partial_quality = 2021/2021/0
  index source_time effective_quote_present/source_time_missing/partial_quality = 9/9/0
  board source_time_confirmed/effective_quote_present = 127/127
  scoped outbox/inbox/checkpoint refs = 0/0/0
  global outbox/inbox/checkpoint = 105122/20726/4345
  downstream_layers_touched = false
  worker_started = false
  N4/N5/N6 untouched = true
  rollback_safe = true
  rollback_sql = sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql

B1 live2 standard outbox snapshot run =
  realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

B1 live2 standard outbox snapshot status =
  common_market_data_run.status = passed
  P0/P1/P2 = 0/0/0
  rows stock/index/board/total = 2021/9/127/2157
  writes_outbox = true
  MarketSnapshotUpdated outbox = 2157 pending
  MarketDataDelayed/MarketDataMissing/MarketDisplaySnapshotUpdated = 0/0/0
  delivered/delivering = 0/0
  scoped inbox/checkpoint refs = 0/0
  wrote only snapshot facts/common_market_data_run/common_market_data_quality_item/common_event_outbox
  no inbox/checkpoint writes = true
  downstream_layers_touched = false
  worker_started = false
  N4/N5/N6 entered = false
  scoped exception used for existing N6 web app / old system process; neither consumed v3 outbox
  rollback_safe = true
  rollback_sql = sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql

N4 live2 canonical trigger execute run =
  trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1

N4 live2 canonical trigger execute status =
  common_trigger_run.status = passed
  P0/P1/P2 = 0/1/0
  common_trigger_quality_item = 17
  common_trigger_state/common_trigger_match/common_event_outbox = 8861/8861/17722
  outbox TriggerMatched/TriggerPendingMarketData/TriggerStateChanged = 4309/4552/8861 pending
  outbox delivered/delivering = 0/0
  runtime signal B_BUY/S_SELL = 4467/4394
  deprecated runtime signal count = 0
  action_mark payload count = 0
  trigger_mark_candidate missing = 0
  matched trigger_live=true = 4309
  pending_market_data trigger_live=false = 4552
  common_trigger_match TriggerStateChanged = 0
  N3 live2 input MarketSnapshotUpdated pending = 2157
  N3 input inbox/checkpoint refs = 0/0
  N5 refs = 0
  downstream inbox/checkpoint refs = 0/0
  global outbox delta = +17722
  global inbox/checkpoint delta = 0/0
  outbox_consumed = false
  worker_started = false
  action/user/voice/mobile/sim/position/real_trade touched = false
  rollback_safe = true
  rollback_sql = sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql

N5 live2 canonical action execute run =
  action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1

N5 live2 canonical action execute status =
  source N4 run = trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
  common_action_run.status = passed
  P0/P1/P2 = 0/0/0
  common_action_quality_item = 4552
  stock_action_fact/index_action_fact/board_action_fact = 4037/18/254
  common_action_event = 4309
  common_event_outbox = 4309
  common_event_inbox = 17722
  common_event_consumer_checkpoint = 2157
  ActionBlocked = 4309 pending
  ActionEligible/ActionExecuted/ActionSkipped = 0/0/0
  legacy ActionEvent/HintEvent/RiskEvent/PositionEvent = 0
  delivered/delivering = 0/0
  N4 outbox status unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged = 4309/4552/8861 pending
  N6 refs = 0
  position rows = 0
  worker_started = false
  N6 entered = false
  voice/mobile/sim/position/real_trade = false
  rollback_safe = true
  rollback_sql = sql/N5_20260529_live2_canonical_action_execute_rollback.sql

N4 canonical trigger execute run (live1 branch) =
  trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

N4 canonical trigger execute status (live1 branch) =
  common_trigger_run.status = passed
  P0/P1/P2 = 0/1/0
  common_trigger_run/common_trigger_quality_item = 1/16
  common_trigger_state/common_trigger_match/common_event_outbox = 8861/8861/17722
  outbox TriggerMatched/TriggerPendingMarketData/TriggerStateChanged = 4309/4552/8861 pending
  outbox delivered/delivering = 0/0
  common_trigger_match TriggerStateChanged = 0
  pending_market_data trigger_live=false = 4552
  matched trigger_live=true = 4309
  runtime signal B_BUY/S_SELL = 4467/4394
  deprecated runtime signal count = 0
  action_mark payload count = 0
  trigger_mark_candidate missing count = 0
  scoped inbox/checkpoint refs = 0/0
  N5 refs common_action_run/common_action_event = 0/0
  global delta outbox/inbox/checkpoint = +17722/0/0
  outbox_consumed = false
  N5/N6 touched = false
  worker_started = false
  user/voice/mobile/sim/position/real_trade = false
  N2/N3 facts unchanged = true
  rollback_safe = true
  rollback_sql = sql/N4_20260529_canonical_trigger_execute_rollback.sql

N5 canonical action execute run (live1 branch) =
  action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

N5 canonical action execute status (live1 branch) =
  source N4 run = trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
  common_action_run.status = passed
  P0/P1/P2 = 0/0/0
  common_action_quality_item = 4552
  stock_action_fact/index_action_fact/board_action_fact = 4037/18/254
  common_action_event = 4309
  common_event_outbox = 4309
  common_event_inbox = 17722
  common_event_consumer_checkpoint = 2157
  ActionBlocked/ActionEligible/ActionExecuted/ActionSkipped = 4309/0/0/0
  legacy ActionEvent/HintEvent/RiskEvent/PositionEvent = 0
  N5 outbox pending/delivered/delivering = 4309/0/0
  N4 outbox status unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged = 4309/4552/8861 pending
  N6 refs = 0
  position rows for this run = 0
  worker_started = false
  N6 entered = false
  voice/mobile/sim/real_trade = false
  old_system_touched = false
  rollback_safe = true
  rollback_sql = sql/N5_20260529_canonical_action_execute_rollback.sql
  execute_report = docs/N5_20260529_canonical_action_execute_report.json

N6 canonical shadow projection run =
  user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

N6 canonical shadow projection status =
  source_action_run_id = action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
  run status = passed
  P0/P1/P2 = 0/5/2
  user_projection_run/user_signal_projection/user_signal_card/user_notification_queue = 1/4309/4309/4309
  notification_source = n5_action_blocked
  queue_status = queued_only
  notification queued_only = 4309
  card mapping blocked / blocked / ActionBlocked / blocked = 4309
  projection_policy = blocked_unconfirmed_no_push_no_decision_no_sim_no_trade
  trace_json_nonnull = 4309
  source_action_event_type = ActionBlocked
  action_state = blocked
  N5 outbox ActionBlocked pending/delivered/delivering = 4309/0/0
  n5_outbox_consumed = false
  updates_n5_outbox_status = false
  user_signal_decision/user_watchlist/user_watchlist_item = 0/0/0
  user_sim_order/user_sim_trade/user_sim_position = 0/0/0
  linked decision/sim refs = 0
  worker_started = false
  push/voice/mobile = false
  position/real_trade = false
  N1-N5 unchanged = true
  rollback_safe = true
  rollback_sql = sql/N6_projection_business_rollback.sql

Next allowed gate =
  20260529 N6 live2 / full-day user projection gate
```

20260525 N2-Display lineage 作为已执行下游历史证据保留：

```text
N1 source_trade_date = 20260522
N2 for_trade_date = 20260525
N2 active condition run =
  condition_layer_20260522_to_20260525_20260525102249_execute

N2 previous active condition run =
  condition_layer_20260522_to_20260525_20260525003855_execute -> superseded

N2 四表输出状态 =
  condition_basis / condition_pool / minute_target_scope / condition_display_basis 已正式写入

N3 subscription run aligned to N2-Display =
  market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

N3 previous-day minute preload aligned to N2-Display =
  previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

Previous N3 subscription run =
  market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute -> stale_after_n2_display_overwrite

N4 trigger context run aligned to current N2/N3 lineage =
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

Previous / synthetic N4 trigger context runs =
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute -> synthetic_denylist
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute -> synthetic_denylist / stale_after_n2_display_overwrite

N3-B1 snapshot run =
  realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

N3-B1 current status =
  execute passed
  P0/P1/P2 = 0/1/0
  stock_realtime_daily_snapshot rows = 2052
  index_realtime_daily_snapshot rows = 9
  board_realtime_daily_snapshot rows = 127
  common_event_outbox rows = 2188
  MarketSnapshotUpdated pending = 2188
  MarketDataMissing = 0
  MarketDataDelayed = 0
  delivered/delivering = 0
  N4 projection matcher processed via inbox/checkpoint = 2188
  N5 action consumer processed current N4 real outbox via N5 inbox/checkpoint = 764
  N6 consumed current N5 outbox = false
  rollback_safe = true
  minute_bar_written = false
  worker_started = false
  N2 active run unchanged
  N3 subscription run unchanged
  N3 preload run unchanged

N4 current context status =
  context rebuild passed
  P0/P1/P2 = 0/0/0
  stock_trigger_context_snapshot rows = 4236
  index_trigger_context_snapshot rows = 18
  board_trigger_context_snapshot rows = 258
  context_snapshot_total = 4512
  common_trigger_match written = 0
  common_event_outbox written = 0
  n3_event_consumed = false
  downstream_layers_touched = false
  worker_started = false

N4 real projection matcher execute status =
  execute passed
  execute_run_id = trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
  trigger_context_run_id = trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  projection_run_id = realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  source snapshot_run_id = realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  common_event_inbox = 2188 processed
  common_event_consumer_checkpoint = 2188
  common_trigger_run status = passed, P0/P1/P2 = 0/0/0
  common_trigger_state = 764
  common_trigger_match = 764
  common_trigger_quality_item = 9
  common_event_outbox = 764
  TriggerMatched pending = 488
  TriggerPendingMarketData pending = 276
  N4 outbox delivered/delivering = 0
  signal summary:
    B_BUY_30M_VOL matched = 305, pending = 136
    BUY_HINT matched = 6
    S_SELL_30M_SHRINK matched = 174, pending = 136
    SELL_HINT matched = 3, pending = 4
  B1 outbox still MarketSnapshotUpdated pending = 2188
  B1 delivered/delivering = 0
  N3 facts unchanged = true
  old synthetic outbox untouched = 53304
  downstream N5 inbox for this N4 run = 764 processed
  N5 action_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
  worker_started = false
  N5 action fact / action event / N5 outbox written = true
  N6/user/voice/sim/position written = false
  rollback_safe = true
  rollback_sql = sql/N4_projection_matcher_rollback.sql

N5 current-real action execute status =
  execute passed
  action_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
  source_trigger_run_id = trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
  common_action_run status = passed
  P0/P1/P2 = 0/0/0
  stock_action_fact = 488
  index_action_fact = 0
  board_action_fact = 0
  common_action_event = 488
  common_action_quality_item = 276
  common_event_inbox = 764 processed
  common_event_consumer_checkpoint = 615
  N5 outbox:
    ActionEvent pending = 479
    HintEvent pending = 9
    RiskEvent = 0
    PositionEvent = 0
  N4 current outbox remains pending = 764
  N4 outbox status updated = false
  N4 outbox consumed = false
  N2/N3/N4 authoritative runs unchanged = true
  common_position_state = 0
  common_position_event = 0
  no real trade / no sim / no voice / no mobile / no N6 = true
  worker_started = false
  rollback_safe = true
  rollback_sql = sql/N5_current_real_action_execute_rollback.sql
  next allowed gates = N6 user projection contract review; N1 official daily fact ingestion review

N3-C2 closed-minute / closed-30m replay execute status =
  execute passed
  c2_run_id = closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute
  minute_delta_rows: stock = 100669, index = 441, board = 6223, total = 107333
  closed_30m_summary rows: stock = 16416, index = 72, board = 1016, total = 17504
  summary_status: closed = 17432, partial = 0, missing = 72, failed = 0
  BJ 920xxx = 9 objects; missing summaries = 72; fabricated minute rows = 0
  P0/P1/P2 = 0/1/0
  outbox/inbox/checkpoint refs for c2_run_id = 0
  B1 MarketSnapshotUpdated pending = 2188
  C1/B1/B2/N4/N5 runtime unchanged = true
  worker_started = false
  downstream_layers_touched = false
  rollback_safe = true
  rollback_sql = sql/N3_C2_closed_30m_business_rollback.sql

N3-C3 MinuteBarClosed outbox execute status =
  execute passed
  c3_run_id = minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute
  common_market_data_run.status = passed
  P0/P1/P2 = 0/1/0
  market_data_pulled = false
  market_data_fact_written = false
  source_trade_date / prev_trade_date = 20260525 / 20260525
  MinuteBarClosed outbox rows = 17432
  stock / index / board = 16344 / 72 / 1016
  pending = 17432
  delivered / delivering = 0
  inbox = 0
  checkpoint refs = 0
  closed_30m_summary C3 refs = 0
  minute_bar_1m C3 refs = 0
  realtime_projection_metric C3 refs = 0
  realtime_daily_snapshot C3 refs = 0
  N4/N5/N6 touched = false
  worker_started = false
  rollback_safe = true
  rollback_sql = sql/N3_C3_minute_bar_closed_outbox_rollback.sql

N3-C2B closed_signal_enrichment execute status =
  execute passed
  c2b_run_id = closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute
  common_market_data_run.status = passed
  P0/P1/P2 = 0/3/0
  stock / index / board = 16416 / 72 / 1016
  total = 17504
  computable_rows = 17432
  unknown_rows = 72
  missing_rows = 72
  signal_distribution:
    up_volume_expanding = 2800
    up_volume_flat = 2494
    up_volume_shrinking = 2260
    down_volume_expanding = 2806
    down_volume_flat = 2408
    down_volume_shrinking = 2011
    flat = 2653
    unknown = 72
  quality_rows = 6
  quality data_domain = common 3 / stock 3
  quality layer_scope = market_data_run
  quality details.metric_scope = closed_signal_enrichment
  c2b outbox / inbox / checkpoint refs = 0 / 0 / 0
  C3 outbox pending = 17432
  C3 delivered / delivering = 0
  C3 inbox / checkpoint refs = 0 / 0
  closed_30m_summary modified = false
  minute_bar_1m modified = false
  realtime_projection_metric modified = false
  realtime_daily_snapshot modified = false
  rollback_safe = true
  rollback_sql = sql/N3_C2B_closed_signal_enrichment_business_rollback.sql

N4-C3 replay audit execute status =
  execute passed
  replay_run_id = trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b
  common_trigger_run.status = passed
  audit rows: stock = 33762, index = 144, board = 2064, total = 35970
  classification:
    would_match = 4734
    would_clear = 245
    would_change = 243
    unchanged = 30730
    missing = 18
    not_ready = 0
  P0/P1/P2 = 0/1/0
  common_event_outbox = 0
  common_event_inbox = 0
  checkpoint refs = 0
  common_trigger_match = 0
  common_trigger_state = 0
  C3 outbox pending = 17432
  C3 delivered / delivering = 0
  N5/N6 touched = false
  worker_started = false
  rollback_safe = true
  rollback_sql = sql/N4_C3_replay_audit_business_rollback.sql

N3-EOD snapshot refresh dry-run / preflight status =
  dry_run_result = DRY_RUN_PASS
  preflight_result = PREFLIGHT_BLOCKED
  blocker = missing_official_daily_fact
  eod_run_id = eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  expected_eod_snapshot_rows: stock = 2052, index = 9, board = 127, total = 2188
  official_daily_missing = 2188
  C3 outbox pending = 17432
  C3 delivered / delivering = 0
  P0/P1/P2 = 0/3/0
  EOD business rows = 0
  common_market_data_run / quality scoped eod_run_id = 0 / 0
  outbox / inbox / checkpoint scoped eod_run_id = 0 / 0 / 0
  EOD execute allowed = false
  next gate = N1 official daily fact ingestion review for 20260525
  provisional settlement = blocked unless a separate provisional settlement gate is opened

Prior N3-B1 failed attempt =
  first execute committed with status=failed because board snapshot missing=127 / board_realtime_daily_snapshot=0
  rollback completed safely before downstream delivery/consumption
  BoardMarketDataAdapter was implemented and probed before the passed rerun

Current N3 runtime gate =
  Do not newly consume or re-consume N3 outbox in this total-control session.
  Current N4 context has been rebuilt against active N2/N3 lineage.
  N4 real MarketSnapshotUpdated dry-run/preflight has identified the projection gate.
  N3 realtime projection metric schema is ready.
  N3-A1 current-lineage previous-day minute fill-facts execute passed.
  A1 previous-day minute rows: stock = 490320, index = 2160, board = 30480, total = 522960.
  A1 common_event_outbox rows = 0; projection tables written = false; worker_started = false.
  N3-C1 today_minute_bar_1m execute passed.
  today_minute_run_id = today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  C1 actual minute rows: stock = 390213, index = 1719, board = 24257, total = 416189.
  C1 expected total = 417908; missing rows = 1719; missing objects = 9, all BJ 920xxx stocks.
  C1 P0/P1/P2 = 0/1/0; P1 is the visible 9-object BJ missing-minute gap.
  C1 common_event_outbox rows = 0.
  C1 MinuteBarClosed generated = false.
  C1 projection tables written = false.
  C1 rollback_sql = sql/N3_C1_today_minute_bar_1m_rollback.sql.
  N3 action-confirmation projection metric schema migration 032 passed.
  032 migration = sql/032_n3_action_confirmation_metric_schema.sql.
  032 target_db = ashare_v3; target_user = ashare_v3_user; target_host = 127.0.0.1/32; target_port = 5432; old_system_db = false.
  032 created tables = stock_action_confirmation_projection_metric / index_action_confirmation_projection_metric / board_action_confirmation_projection_metric.
  032 index_count = 18; metric_ready trace CHECK constraints = 3.
  032 row counts stock/index/board = 0/0/0.
  032 business_row_written = false; market_data_pulled = false; worker_started = false.
  032 outbox/inbox/checkpoint delta = 0/0/0.
  032 downstream N4/N5/N6 checked tables = 32; downstream row_count_delta_zero = true.
  032 rollback_safe = true; schema_rollback_sql = sql/032_n3_action_confirmation_metric_schema_rollback.sql; business_rollback_sql = sql/N3_action_confirmation_projection_metric_business_rollback.sql.
  032 execute_report = docs/N3_action_confirmation_projection_metric_032_migration_execute_report.json.
  N3 action-confirmation projection writer execute passed.
  projection_run_id = action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
  source_condition_run_id = condition_layer_20260601_source_20260601_v1.
  source_subscription_run_id = market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1.
  source_snapshot_run_id = realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1.
  source_today_minute_run_id = today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1.
  source_previous_day_minute_run_id = previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1.
  common_market_data_run.status = passed.
  action-confirmation metric rows stock/index/board/total = 765/54/150/969.
  metric_ready/not_ready = 969/0.
  common_market_data_quality_item rows = 6; P0/P1/P2 = 0/0/0.
  market_data_pulled = false; market_data_fact_written = true; downstream_layers_touched = false; worker_started = false.
  scoped outbox/inbox/checkpoint = 0/0/0; global outbox/inbox/checkpoint delta = 0/0/0.
  no outbox write/consume; no inbox/checkpoint write; no N4/N5/N6 refs.
  rollback_safe = true; rollback_sql = sql/N3_action_confirmation_projection_metric_business_rollback.sql.
  execute_report = docs/N3_action_confirmation_projection_writer_execute_report.json.
  N4 action-confirmation metric business execute passed.
  execute_run_id = trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1.
  trigger_context_run_id = trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1.
  source_projection_run_id = action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1.
  common_trigger_run.status = passed.
  N4 action-confirmation rows: common_trigger_run = 1, common_trigger_quality_item = 10, common_trigger_state = 5941, common_trigger_match = 5941, common_event_outbox = 5941.
  N4 action-confirmation outbox: TriggerMatched = 6 pending, TriggerPendingMarketData = 5935 pending, TriggerStateChanged = 0, delivered/delivering = 0/0.
  N4 action-confirmation quality: P0/P1/P2 = 0/1/0; quality item distribution = P0 passed 9, P1 warning 1.
  N4 action-confirmation P1 = n4_action_confirmation_metric_pending_candidates_visible; non_blocking = true.
  N4 action-confirmation boundary: N3 metric facts unchanged stock/index/board = 765/54/150, common_event_inbox refs = 0, checkpoint refs = 0, N5 refs = 0.
  N4 action-confirmation side effects: N3 outbox consumed = false, inbox/checkpoint written = false, N5/N6 entered = false, worker_started = false, market_data_pulled = false, voice/mobile/sim/position/real_trade = false.
  N4 action-confirmation rollback_safe = true; rollback_sql = sql/N4_action_confirmation_metric_business_execute_rollback.sql.
  N4 action-confirmation execute_report = docs/N4_action_confirmation_metric_business_execute_report.json.
  N5 action-confirmation metric execute passed.
  action_run_id = action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1.
  source N4 run = trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1.
  common_action_run.status = passed; P0/P1/P2 = 0/0/0.
  N5 action-confirmation rows: common_action_run = 1, common_action_quality_item = 5935, stock_action_fact = 1, index_action_fact = 4, board_action_fact = 0, common_action_event = 5, common_event_outbox = 5, common_event_inbox = 5941, common_event_consumer_checkpoint = 2487.
  N5 action-confirmation event distribution: ActionExecuted = 4, ActionBlocked = 1, ActionEligible = 0, ActionSkipped = 0.
  N5 action-confirmation outbox: ActionExecuted = 4 pending, ActionBlocked = 1 pending, delivered/delivering = 0/0.
  N5 action-confirmation boundary: N4 outbox unchanged TriggerMatched = 6 pending, TriggerPendingMarketData = 5935 pending, TriggerStateChanged = 0, delivered/delivering = 0/0.
  N5 action-confirmation downstream refs: N6/user/downstream refs = 0, position refs = 0, voice/mobile/sim/real_trade refs = 0, worker_started = false.
  N5 action-confirmation rollback_safe = true; rollback_sql = sql/N5_20260602_action_confirmation_metric_execute_rollback.sql.
  N5 action-confirmation execute_report = docs/N5_20260602_action_confirmation_metric_execute_report.json.
  N6 20260602 action-confirmation metric shadow projection execute passed.
  N6 projection_run_id = user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1.
  N6 source_action_run_id = action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1.
  N6 shadow status = passed; preflight_result = PREFLIGHT_PASS; P0/P1/P2 = 0/5/2.
  N6 rows: user_projection_run = 1, user_signal_projection = 5, user_signal_card = 5, user_notification_queue = 5.
  N6 queue distribution: n5_action_executed / queued_only = 4; n5_action_blocked / queued_only = 1.
  N6 card distribution: ActionExecuted -> action_confirmed / executed / 30m_shrink = 4; ActionBlocked -> blocked / blocked = 1.
  N6 boundary: N5 outbox unchanged ActionExecuted = 4 pending, ActionBlocked = 1 pending; N5 outbox consumed = false; N5 outbox status updated = false; user_signal_decision = 0; linked user_sim_order/trade/position = 0/0/0; user_watchlist = 0; user_watchlist_item = 0; worker_started = false; push/voice/mobile = false; sim/position/real_trade = false.
  N6 rollback_safe = true; rollback_sql = sql/N6_projection_business_rollback.sql.
  N3-B2 realtime projection execute passed.
  projection_run_id = realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  B2 P0/P1/P2 = 0/3/0.
  B2 projection fact rows = stock 2052, index 9, board 127, total 2188.
  B2 ready projection rows = 2052: stock = 2043, index = 9.
  B2 not_ready projection rows = 136: BJ 920xxx stock = 9, board = 127.
  board not_ready reason = B1 board snapshot_time is 15:00, while C1 latest_closed_minute is 14:11; strict lineage must not mix these as ready.
  B2 projection_signal_status = down_volume_expanding 96, down_volume_flat 79, down_volume_shrinking 174, flat 577, unknown 136, up_volume_expanding 305, up_volume_flat 342, up_volume_shrinking 479.
  B2 quality rows = 6; quality data_domain = common/stock/board; layer_scope = market_data_run; details.metric_scope = realtime_projection_metric.
  B2 projection outbox rows = 0; projection inbox rows = 0.
  B1 MarketSnapshotUpdated remains pending = 2188.
  B2 rollback_safe = true; rollback_sql = sql/N3_B2_realtime_projection_rollback.sql.
  N4 projection matcher dry-run / preflight / run-once execute has passed for the current B1/B2/context lineage.
  N4 has recorded B1 event processing through common_event_inbox/checkpoint, but upstream B1 outbox status remains pending by design.
  Current N4 outbox remains real and pending by status: TriggerMatched = 488, TriggerPendingMarketData = 276.
  N5 current-real action execute has passed and recorded the current N4 outbox through N5 inbox/checkpoint.
  N5 outbox is pending: ActionEvent = 479, HintEvent = 9, RiskEvent = 0, PositionEvent = 0.
  Do not consume N5 outbox, enter N6 execute, write user/voice/sim/mobile/position/real-trade rows, or start worker.
  N3-C2 closed-minute / closed-30m replay execute passed as N3 replay/confirmation, not an N1->N3 full rerun.
  C2 c2_run_id = closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute
  C2 actual writes = common_market_data_run, common_market_data_quality_item, stock/index/board_minute_bar_1m delta rows, stock/index/board_closed_30m_summary.
  C2 minute_delta_rows = stock 100669, index 441, board 6223, total 107333.
  C2 closed_30m_summary rows = stock 16416, index 72, board 1016, total 17504.
  C2 summary_status = closed 17432, partial 0, missing 72, failed 0.
  C2 BJ 920xxx gap = 9 objects, 72 missing summaries, no fabricated minute rows.
  C2 P0/P1/P2 = 0/1/0.
  C2 outbox/inbox/checkpoint refs = 0.
  C2 writes_outbox = false; MinuteBarClosed outbox was handled by C3.
  C2 does not supersede B1/B2/N4/N5; replay diff writes quality/diff only and does not auto rollback or rerun downstream.
  Daily close is a separate gate.
  N3-C3 MinuteBarClosed outbox execute passed.
  C3 c3_run_id = minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  C3 wrote only common_market_data_run, common_market_data_quality_item, and common_event_outbox.
  C3 MinuteBarClosed outbox rows = 17432: stock = 16344, index = 72, board = 1016.
  C3 outbox status = pending 17432, delivered/delivering 0.
  C3 inbox/checkpoint refs = 0; closed_30m_summary/minute_bar_1m/realtime_projection_metric/realtime_daily_snapshot C3 refs = 0.
  C3 P0/P1/P2 = 0/1/0; market_data_pulled = false; market_data_fact_written = false.
  C3 source_trade_date / prev_trade_date = 20260525 / 20260525.
  C3 rollback_safe = true; rollback_sql = sql/N3_C3_minute_bar_closed_outbox_rollback.sql.
  C3 did not touch N4/N5/N6 and did not start worker.
  N3-C2B closed_signal_enrichment execute passed.
  C2B c2b_run_id = closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
  C2B wrote only common_market_data_run, common_market_data_quality_item, and stock/index/board_closed_30m_signal_enrichment.
  C2B enrichment rows = stock 16416, index 72, board 1016, total 17504.
  C2B computable_rows = 17432; unknown_rows = 72; missing_rows = 72.
  C2B signal_distribution = up_volume_expanding 2800, up_volume_flat 2494, up_volume_shrinking 2260, down_volume_expanding 2806, down_volume_flat 2408, down_volume_shrinking 2011, flat 2653, unknown 72.
  C2B quality rows = 6; data_domain = common 3 / stock 3; layer_scope = market_data_run; details.metric_scope = closed_signal_enrichment.
  C2B outbox/inbox/checkpoint refs = 0.
  C2B did not consume C3 outbox; C3 remains pending 17432, delivered/delivering 0, inbox/checkpoint refs 0.
  C2B did not modify closed_30m_summary, minute_bar_1m, realtime_projection_metric, or realtime_daily_snapshot.
  C2B rollback_safe = true; rollback_sql = sql/N3_C2B_closed_signal_enrichment_business_rollback.sql.
  N4-C3 replay audit execute passed after C2B; the branch still does not authorize N4/N5/N6 replay event execute, C3 outbox consumption, or worker.
```

因此，N3-B1 已形成第一批真实 N3 snapshot fact + N3 outbox，N3-A1 current-lineage fill-facts 和 N3-C1 已补齐 B2 projection 所需的前一日与今日分钟输入，N4 当前 context 已对齐到同一 N2/N3 lineage。032 已新增 N3 action-confirmation projection metric 三张物理分表；随后 N3 action-confirmation projection writer execute 已 passed，写入 stock/index/board metric rows = 765/54/150，metric_ready = 969，P0/P1/P2 = 0/0/0，未写或消费 outbox/inbox/checkpoint。N4 action-confirmation metric business execute 已基于这批 N3 标准 metric facts 写入 N4 trigger fact/outbox：common_trigger_state/common_trigger_match/common_event_outbox = 5941/5941/5941，TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，P0/P1/P2=0/1/0，唯一 P1 为 pending candidates visible 且不阻断；该 run 未消费 N3 outbox、未写 inbox/checkpoint、未进入 N6、未启动 worker、未拉行情，rollback_safe=true。N5 action-confirmation metric execute 已基于 N4 TriggerMatched + N3 标准 metric facts 写入 N5 action fact/event/outbox/inbox/checkpoint：common_action_run=1，common_action_quality_item=5935，stock/index/board_action_fact=1/4/0，common_action_event=5，common_event_outbox=5，common_event_inbox=5941，checkpoint=2487，ActionExecuted=4 pending，ActionBlocked=1 pending，P0/P1/P2=0/0/0；N4 outbox status 保持 pending 且未改，N6/user/downstream refs=0，position refs=0，voice/mobile/sim/real_trade refs=0，worker_started=false，rollback_safe=true。N6 20260602 action-confirmation metric shadow projection 已基于 N5 标准 action outbox 写入 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/5/5/5，queue distribution 为 n5_action_executed/n5_action_blocked queued_only=4/1，card distribution 为 ActionExecuted -> action_confirmed/executed/30m_shrink=4 与 ActionBlocked -> blocked/blocked=1；N5 outbox 仍保持 ActionExecuted=4 pending、ActionBlocked=1 pending，未消费、未更新 status，未写 decision/sim/watchlist，未启动 worker，未 push/voice/mobile/sim/position/real trade，rollback_safe=true。旧 N4 synthetic outbox 仍只能作为历史验证材料，不得替代这批真实 N3 event。N3-B2 execute 已写入正式 realtime projection facts，stock/index 共 2052 行 ready projection 已被 N4 projection matcher run-once execute 消费为真实 N4 trigger fact / outbox；9 个 BJ 920xxx 和 127 个 board 仍显式 not_ready，并只生成 `TriggerPendingMarketData`。N5 current-real action execute 已基于当前真实 N4 outbox 写入 action fact / action event / N5 outbox，同时保持 N4 outbox status 为 pending 且不触碰 N2/N3/N4 权威 run。N3-C2 closed-minute / closed-30m replay execute 已 passed，补齐 C1 后半日 delta minute rows 并生成 closed 30m summary，但不 supersede B1/B2/N4/N5、不自动触发下游 replay。N3-C3 MinuteBarClosed outbox execute 已 passed，只写 N3 run/quality/outbox，生成 17432 条 pending `MinuteBarClosed`，未消费 outbox、未写 inbox/checkpoint、未触碰 N4/N5/N6。N3-C2B closed_signal_enrichment execute 已 passed，只写 N3 run/quality/enrichment facts，补齐 17504 条 closed signal enrichment，其中 17432 条 computable，72 条 BJ 920xxx 仍显式 unknown/missing。N4-C3 replay audit execute 已 passed，只把 C3 replay diff 固化到 audit facts，未消费 C3 outbox、未写标准 N4 outbox、未写 trigger_match/state、未触碰 N5/N6。N3-EOD snapshot refresh dry-run 已 PASS，但 execute preflight 因 `missing_official_daily_fact` BLOCKED，`official_daily_missing=2188`，EOD scoped business/run/quality/outbox/inbox/checkpoint rows 均为 0，且 C3 outbox 仍 pending=17432。当前下一步只允许 N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review，或 N1 official daily fact ingestion review。EOD execute、daily close、N5 outbox consumption、N5 outbox status update、additional N6 execute、N4/N5/N6 replay event execute、user/voice/sim/mobile/position/真实交易和 worker 均继续禁止。

## 6.1 N3-C2 closed-minute / closed-30m gate

C2 定位为 N3 replay / confirmation 子阶段。它不是 N1 到 N3 的全链路重跑，也不替代或 supersede 已 passed 的 B1 snapshot、B2 projection、N4 projection matcher 或 N5 action run。当前 C2 run-once execute 已 passed。

```text
c2_run_id =
  closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute

C2 executed strategy =
  pull_attempt = full-day 1m replay per subscribed object
  minute_write = only C1 missing rows or replay-diff delta rows, run_id=c2_run_id
  summary_write = closed 30m summary synthesized from C1 baseline + C2 delta
  outbox_write = false
  MinuteBarClosed event = emitted by C3
  daily_close = separate gate

C2 actual writes =
  common_market_data_run
  common_market_data_quality_item
  stock/index/board_minute_bar_1m delta rows
  stock/index/board_closed_30m_summary

C2 row summary =
  minute_delta_rows: stock = 100669, index = 441, board = 6223, total = 107333
  closed_30m_summary: stock = 16416, index = 72, board = 1016, total = 17504
  summary_status: closed = 17432, partial = 0, missing = 72, failed = 0
  BJ 920xxx: 9 objects, 72 missing summaries, no fabricated minute rows
  quality P0/P1/P2 = 0/1/0
  outbox/inbox/checkpoint refs c2 = 0
  C1/B1/B2/N4/N5 runtime unchanged = true
  worker_started = false
  downstream_layers_touched = false
  rollback_safe = true
  rollback_sql = sql/N3_C2_closed_30m_business_rollback.sql

C2 forbidden writes =
  common_event_outbox
  common_event_inbox / common_event_consumer_checkpoint
  stock/index/board_realtime_projection_metric
  stock/index/board_realtime_daily_snapshot
  existing B1/B2/N4/N5 runtime rows
  condition / trigger / action / user / voice / mobile / sim / position
  worker / long-running service
```

C2 replay diff 只能落质量项 / diff 证据，不得自动回滚或重跑 N4/N5。C3 `MinuteBarClosed` outbox execute、C2B `closed_signal_enrichment` execute 和 N4-C3 replay audit execute 均已单独完成。N3-EOD snapshot refresh dry-run 已 PASS，但 execute preflight 因缺 20260525 official daily fact BLOCKED；当前 C2/C3/C2B 分支不得用 C2/C2B 直接生成正式 EOD settlement，除非另开 provisional settlement gate。仍不授权下游 replay event execute、正式事件消费或 worker。

## 6.2 N3-C3 MinuteBarClosed outbox gate

C3 定位为 N3 closed summary 到标准事件 ledger 的单次发布阶段。它只把已闭合且 trace 完整的 C2 closed 30m summary 生成 `MinuteBarClosed` pending outbox，不修改分钟事实、closed summary、snapshot 或 projection，也不消费任何 outbox。

```text
c3_run_id =
  minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute

C3 execute status =
  common_market_data_run.status = passed
  P0/P1/P2 = 0/1/0
  market_data_pulled = false
  market_data_fact_written = false
  source_trade_date / prev_trade_date = 20260525 / 20260525

C3 event summary =
  MinuteBarClosed outbox rows = 17432
  stock / index / board = 16344 / 72 / 1016
  pending = 17432
  delivered / delivering = 0
  inbox = 0
  checkpoint refs = 0

C3 boundary =
  closed_30m_summary C3 refs = 0
  minute_bar_1m C3 refs = 0
  realtime_projection_metric C3 refs = 0
  realtime_daily_snapshot C3 refs = 0
  N4/N5/N6 touched = false
  worker_started = false

C3 rollback =
  rollback_safe = true
  rollback_sql = sql/N3_C3_minute_bar_closed_outbox_rollback.sql
```

C3 outbox 当前已具备 C2B closed signal enrichment 作为标准化信号补充，且 N4-C3 replay audit 已将 reviewed dry-run diff 固化为 audit facts。C3 outbox 仍不得被正式消费，N4/N5 若要 replay event execute 必须先有显式 C3 run_id allowlist、独立 contract/preflight/rollback 和用户授权。

## 6.3 N3-C2B closed_signal_enrichment gate

C2B 定位为 N3 closed summary 的标准信号补充事实。它不写事件，不消费 C3 outbox，不修改 C2 closed summary 或任何分钟 / snapshot / projection fact，只提供 N4 C3 replay dry-run 所需的标准化 closed signal 字段。

```text
c2b_run_id =
  closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

C2B execute status =
  common_market_data_run.status = passed
  P0/P1/P2 = 0/3/0
  stock / index / board / total = 16416 / 72 / 1016 / 17504
  computable_rows = 17432
  unknown_rows = 72
  missing_rows = 72

C2B signal_distribution =
  up_volume_expanding = 2800
  up_volume_flat = 2494
  up_volume_shrinking = 2260
  down_volume_expanding = 2806
  down_volume_flat = 2408
  down_volume_shrinking = 2011
  flat = 2653
  unknown = 72

C2B quality =
  quality_rows = 6
  data_domain common = 3
  data_domain stock = 3
  layer_scope = market_data_run
  details.metric_scope = closed_signal_enrichment

C2B boundary =
  c2b outbox = 0
  c2b inbox = 0
  c2b checkpoint refs = 0
  C3 outbox pending = 17432
  C3 delivered/delivering = 0
  C3 inbox/checkpoint refs = 0
  closed_30m_summary modified = false
  minute_bar_1m modified = false
  realtime_projection_metric modified = false
  realtime_daily_snapshot modified = false

C2B rollback =
  rollback_safe = true
  rollback_sql = sql/N3_C2B_closed_signal_enrichment_business_rollback.sql
```

C2B execute 后已完成 N4 C3 replay dry-run 与 replay audit execute 登记，并已完成 N3-EOD dry-run / preflight 登记。EOD dry-run PASS，但 execute preflight 因 `missing_official_daily_fact` BLOCKED。该登记不授权 N4/N5/N6 replay event execute，不授权消费 C3 outbox，不授权 worker；下一步推荐切回 N1 official daily fact ingestion review。

## 6.4 N4 C3 replay audit gate

N4-C3 replay audit 定位为审计固化：把已经 review 通过的 C3 replay diff 写入 replay audit facts，不消费 C3 outbox，不生成正式 N4 outbox，不改变当前 N4 projection matcher / N5 action runtime。

```text
replay_run_id =
  trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b

N4-C3 replay audit execute status =
  common_trigger_run.status = passed
  P0/P1/P2 = 0/1/0

audit rows =
  stock = 33762
  index = 144
  board = 2064
  total = 35970

classification =
  would_match = 4734
  would_clear = 245
  would_change = 243
  unchanged = 30730
  missing = 18
  not_ready = 0

boundary =
  common_event_outbox = 0
  common_event_inbox = 0
  checkpoint refs = 0
  common_trigger_match = 0
  common_trigger_state = 0
  C3 outbox pending = 17432
  C3 delivered / delivering = 0
  N5/N6 touched = false
  worker_started = false

rollback =
  rollback_safe = true
  rollback_sql = sql/N4_C3_replay_audit_business_rollback.sql
```

N4-C3 replay audit passed 不等于 N4 replay execute。`would_match / would_clear / would_change` 只是审计分类，不能被下游当作 `TriggerMatched` 或 canonical `TriggerStateChanged` 标准事件；`would_clear` 也不得被当作 legacy `TriggerCleared` 正式输出。N3-EOD dry-run 已 PASS，但 execute preflight BLOCKED；下一步推荐切回 N1 official daily fact ingestion review。

## 6.5 N4 触发语义 gate

N4 canonical 触发运行边界以 `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md` 为准；N4 trigger-side rule definitions 以 `docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md` 为准；N4/N5 状态流与跨层边界以 `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md` 为准。`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md` 对 N3 projection facts 与 N5 final confirmation 仍保留权威性，但对 N4 trigger-side rule definitions 已降级为 superseded/historical。`BUY_HINT / SELL_HINT` 是 N1-N5 内部买卖信号条件，不是用户提示类型；`B_BUY_30M_VOL / S_SELL_30M_SHRINK` 不再作为 future runtime `signal_type`，只能作为历史 trace / display / compatibility label。

```text
N4 不必等待完整 30m 闭合。
N4 不允许自己拉行情或拼原始分钟。
N4 可以基于 N3 标准化、可追溯 realtime projection 指标判断 30m projection 证据。
N4 只输出 projection_30m_flag / projection_30m_type / trigger_mark_candidate。
N5 在 120m / 30m / 5m / 1m 动作确认后决定最终 action_mark。
N4/N5 不得临时计算 1m/5m/30m/120m action confirmation 指标。
N5 只消费 N3 标准 action-confirmation projection facts + N4 TriggerMatched 做最终确认。
N5 不信任 opaque action_confirmation payload 作为 final proof。
MinuteBarClosed / closed 30m summary 是强确认或回放校验入口，不是唯一入口。
当前 execute blocker 不是“必须等 30m 闭合”。B2 execute 已写入 N3 标准化、可追溯 realtime projection 指标；N4 projection matcher dry-run、preflight、inbox/checkpoint/ack、rollback 和用户 run-once 授权 gate 已通过，并已完成一次真实 run-once execute。
N3-B2 projection 表结构与正式 facts 已就绪，ready projection 覆盖 stock=2043、index=9。当前历史 N4 run 已将符合条件的 projection / 30m 类输入写成正式 `TriggerMatched`，将 board/BJ not_ready 写成 `TriggerPendingMarketData`；后续新增 N4 execute 或 worker 仍必须另开 gate，并应按 canonical TriggerStateChanged + trigger_mark_candidate 语义对齐。
N3 action-confirmation projection metric schema migration 032 已 passed；writer execute 已 passed：projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，metric rows stock/index/board=765/54/150，metric_ready=969，P0/P1/P2=0/0/0，outbox/inbox/checkpoint=0/0/0。N4 action-confirmation metric business execute 已 passed：execute_run_id=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`，common_trigger_state/common_trigger_match/common_event_outbox=5941/5941/5941，TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，P0/P1/P2=0/1/0，未消费 N3 outbox，未写 inbox/checkpoint，未进入 N5/N6，rollback_safe=true。后续 N5 不得绕过 N3 标准 metric fact 或使用 opaque action_confirmation payload。
```

该 gate 不改变普通 BUY/SELL/FULL 的主输入：普通 BUY/SELL/FULL 仍主要由 `MarketSnapshotUpdated` 驱动，并必须用本地化后的 `period_trigger_baseline_json` 与 N3 标准行情事实/指标比较，不得回查 N1 日 K 或外拉行情。

## 6.6 20260528 canonical v2 N4 trigger execute gate

20260528 canonical v2 N4 trigger execute 已完成 run-once execute，并作为新 canonical runtime 分支登记。该分支不改写 20260525 历史 real lineage，也不授权 N5/N6 自动消费。

```text
N2 active canonical v2 =
  condition_layer_20260527_source_20260527_v2

N3 subscription =
  market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N3 previous-day minute preload =
  previous_day_minute_preload_20260527_for_20260528__market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N3 B1 fact-only snapshot =
  realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N4 context =
  trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2

N4 canonical execute =
  trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
```

N4 canonical execute status:

```text
common_trigger_run.status = passed
P0/P1/P2 = 0/1/0
common_trigger_quality_item = 16
common_trigger_state = 8887
common_trigger_match = 8887
common_event_outbox = 17774

N4 outbox pending =
  TriggerMatched = 4285
  TriggerPendingMarketData = 4602
  TriggerStateChanged = 8887
  delivered = 0
  delivering = 0

canonical checks =
  common_trigger_match TriggerStateChanged = 0
  pending_market_data trigger_live=false = 4602
  matched trigger_live=true = 4285
  state/match signal distribution: B_BUY = 4576, S_SELL = 4311
  deprecated runtime signal count: state = 0, match = 0, outbox_payload = 0
  action_mark payload count = 0
  trigger_mark_candidate missing: state = 0, match = 0, outbox = 0

boundary =
  N5 refs = 0
  N6 refs = 0
  scoped inbox/checkpoint refs = 0
  global delta: outbox +17774, inbox 0, checkpoint 0
  N5/N6 worker_started = false
  N2/N3 facts unchanged = true
  old_system_touched = false
  action/user/voice/mobile/sim/position/real trade written = false

rollback =
  rollback_safe = true
  rollback_sql = sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql
```

Next completed branch:

```text
N5 canonical action execute passed
```

Still forbidden:

```text
consume N4 outbox
N6 execute
worker
user/voice/mobile/sim/position/real trade
```

## 6.7 20260528 canonical N5 action execute gate

20260528 canonical N5 action execute 已完成 run-once execute，并作为当前 canonical runtime 分支登记。该分支消费 20260528 canonical N4 outbox 但不更新 N4 outbox status，不触碰 N2/N3/N4 facts，不进入 N6。

```text
N2 active canonical v2 =
  condition_layer_20260527_source_20260527_v2

N3 subscription =
  market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N3 previous-day minute preload =
  previous_day_minute_preload_20260527_for_20260528__market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N3 B1 fact-only snapshot =
  realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2

N4 context =
  trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2

N4 canonical execute =
  trigger_execute_20260528_condition_layer_20260527_source_20260527_v2

N5 canonical action execute =
  action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
```

N5 canonical execute status:

```text
common_action_run.status = passed
P0/P1/P2 = 0/0/0
common_action_quality_item = 4602
stock_action_fact = 4013
index_action_fact = 18
board_action_fact = 254
common_action_event = 4285
common_event_outbox = 4285
common_event_inbox = 17774
common_event_consumer_checkpoint = 2146

N5 outbox pending =
  ActionBlocked = 4285
  ActionEligible = 0
  ActionExecuted = 0
  ActionSkipped = 0
  delivered = 0
  delivering = 0

canonical checks =
  legacy output events = 0
  ActionEvent = 0
  HintEvent = 0
  RiskEvent = 0
  PositionEvent = 0
  runtime signal B_BUY = 2145
  runtime signal S_SELL = 2140
  BUY_HINT / SELL_HINT = trace-only
  action_mark NULL = 4285
  action_state blocked = 4285
  confirmation_status failed = 4285

boundary =
  N4 outbox status unchanged = true
  N6 refs = 0
  position refs = 0
  user projection rows = 0
  worker_started = false
  voice/mobile/sim/real trade = false

rollback =
  rollback_safe = true
  rollback_sql = sql/N5_20260528_canonical_action_execute_rollback.sql
```

Subsequent branch:

```text
20260529 N6 canonical shadow projection has now passed; current follow-up gates are documented in 6.16.
```

Still forbidden:

```text
consume N5 outbox
N6 execute
worker
user/voice/mobile/sim/position/real trade
```

## 7. Synthetic 与真实链路

旧 N4-R4 trigger execute 是 synthetic/sample run-once，必须进入 denylist：

```text
denylist source_run_id =
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute

denylist N4 outbox rows =
  20260524014029: TriggerMatched 8884 + TriggerPendingMarketData 17768 = 26652
  20260525003855: TriggerMatched 8884 + TriggerPendingMarketData 17768 = 26652
  combined = 53304

source_condition_run_id =
  condition_layer_20260522_to_20260525_20260524014029_execute
  condition_layer_20260522_to_20260525_20260525003855_execute

real_n3_event_consumed = false for both synthetic lineages
```

这些 N4 outbox 可用于历史 N5 validation 证据材料，但不得被误认为新 N2-Display lineage 或真实 N3 行情事件触发链路。真实链路必须满足：

```text
N3 writes realtime_daily_snapshot or closed minute fact
N3 writes standard common_event_outbox in the same transaction
N4 consumes N3 standard event
N4 writes trigger fact and N4 outbox in the same transaction
N5 consumes N4 outbox and writes action fact / event
```

当前真实 N4 outbox 已由以下 run 产生：

```text
execute_run_id =
  trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249

event counts =
  TriggerMatched pending = 488
  TriggerPendingMarketData pending = 276

boundary =
  delivered/delivering = 0
  downstream N5 inbox for this N4 run = 764 processed
  old synthetic outbox untouched = 53304
```

20260528 canonical N4 outbox is a separate current canonical branch:

```text
execute_run_id =
  trigger_execute_20260528_condition_layer_20260527_source_20260527_v2

event counts =
  TriggerMatched pending = 4285
  TriggerPendingMarketData pending = 4602
  TriggerStateChanged pending = 8887

boundary =
  delivered/delivering = 0
  N5 refs = 0
  N6 refs = 0
  scoped inbox/checkpoint refs = 0
  N5/N6 worker_started = false
```

20260528 canonical N5 action execute has consumed the canonical N4 outbox through N5 inbox/checkpoint while leaving N4 outbox status unchanged:

```text
action_run_id =
  action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2

source_trigger_run_id =
  trigger_execute_20260528_condition_layer_20260527_source_20260527_v2

execute result =
  common_action_run.status = passed
  P0/P1/P2 = 0/0/0
  stock_action_fact = 4013
  index_action_fact = 18
  board_action_fact = 254
  common_action_event = 4285
  common_event_inbox = 17774
  common_event_consumer_checkpoint = 2146
  N5 outbox pending = ActionBlocked 4285
  ActionEligible = 0
  ActionExecuted = 0
  ActionSkipped = 0
  legacy output events = 0
  common_position_state = 0
  common_position_event = 0
  N6 refs = 0
  rollback_safe = true
  rollback_sql = sql/N5_20260528_canonical_action_execute_rollback.sql
```

## 6.8 20260528 N1 ingestion passed

20260528 N1 入库已完成 official daily 与 condition source activation 两段 run-once execute，并已通过 post-review。该登记只说明 N1 source facts 已 ready，不表示 N2/N3/N4/N5/N6 自动推进。

```text
official daily ingestion =
  source_batch_id = official_daily_ingest_20260528_v1
  stock_daily_bar_fact = 5506
  index_daily_bar_fact = 83
  board_daily_bar_fact = 428
  total = 6017
  P0/P1/P2 = 0/19/0
  rollback_safe = true
  rollback_sql = sql/N1_official_daily_20260528_ingestion_rollback.sql

official daily active source_version =
  stock_daily_20260528_v1
  index_daily_20260528_v1
  board_daily_20260528_v1

condition source activation =
  source_batch_id = condition_source_activation_20260528_v1
  stock_daily_basic = 5506
  stock_financial_metrics_fact = 5506
  index_membership_fact = 12841
  board_membership_fact = 56958
  total = 80811
  P0/P1/P2 = 0/3/1
  rollback_safe = true
  rollback_sql = sql/N1_condition_source_20260528_activation_rollback.sql
```

20260528 condition source active source_version:

```text
stock_daily_basic_20260528_v1
stock_financial_20260528_v1
index_membership_20260528_v1
board_membership_20260528_v1
```

Boundary:

```text
outbox/inbox/checkpoint delta = 0/0/0
Parquet written = false
N2/N3/N4/N5/N6 entered = false
worker_started = false
old_system_touched = false
real_trading = false
check_condition_source_ready --source-trade-date 20260528 passed = true
```

Next allowed gate:

```text
N2 condition layer, N3 subscription, A1 previous_day_minute preload, B1 pre-open, B1 live1, N4 canonical trigger execute, N5 canonical action execute, N6 canonical shadow projection, and B1 live2 standard outbox snapshot, N4 live2 canonical trigger execute, and N5 live2 canonical action execute passed; current next gate is 20260529 N6 live2 / full-day user projection gate
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not pull market data
do not write outbox/inbox/checkpoint
do not start worker
do not enter B1
do not enter N4/N5/N6
do not write user/voice/mobile/sim/position/real trade
```

## 6.8.1 20260602 N1 source baseline complete

20260602 N1 source baseline 已完成 official daily 与 condition source activation 两段 run-once execute，并已通过 post-review；该 source baseline 已被 `condition_layer_20260602_source_20260602_v1` 消费，并已进一步生成 20260603 N3 subscription control rows、A1 previous-day minute preload facts/status、`common_trade_calendar(20260603)` fix-forward patch、B1 realtime snapshot fact-only passed run、N4 trigger_context_snapshot rebuild passed run、matcher fix 后 N4 canonical trigger execute passed run、status fix 后 N5 canonical action execute passed run、N4 v4 execute passed run、N5 v1 market-action-confirmation execute passed run 与 N6 v1 shadow projection post-review recovery passed。035 N6 delivery notification queue schema alignment migration 已 passed；N6 delivery noop preview materialization 曾 append-only 写入 863 行，后续已按 `sql/N6_20260603_delivery_notification_rollback.sql` rollback passed，target preview rows=0。当前 source queued_only 仍为 863，N5 outbox ActionBlocked pending 仍为 863，N6 shadow rows 保留为 user_projection_run/user_signal_projection/user_signal_card/source_queue=1/863/863/863，真实 delivery/push/voice/mobile/sim/position/real trade 均未触发。20260603 final read-only lineage dashboard review 已 LINEAGE_DASHBOARD_PASS，并已 closeout 登记；read-only dashboard artifact 已生成：`docs/dashboard/20260603_FINAL_READ_ONLY_LINEAGE_DASHBOARD.md` 与 `docs/dashboard/20260603_final_read_only_lineage_dashboard.json`。20260603/20260604 daily pipeline catch-up 已 CATCHUP_PASS through N3-A1：报告=`docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_ORCHESTRATOR_REPORT.md` / `.json`。20260604/20260605 calendar patch 均 POST_REVIEW_PASS；20260603/20260604 official daily + condition source 均 passed；N2 runs `condition_layer_20260603_source_20260603_v1` 与 `condition_layer_20260604_source_20260604_v1` 均 passed_active；N3 subscription runs `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` / `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` 均 passed；A1 preload runs `previous_day_minute_preload_20260603_for_20260604__market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` / `previous_day_minute_preload_20260604_for_20260605__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` 均 passed，outbox refs=0，未进入 N4/N5/N6；20260605 N3 staged refresh 已 POST_REVIEW_PASS：B1 live2 fact-only run `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed，rows stock/index/board/total=1952/9/428/2389，P0/P1/P2=0/0/0，writes_outbox=false；C1 current-minute run `today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed，latest_closed_minute=2026-06-05T10:37:00+08:00，rows stock/index/board/total=19028/134/3752/22914，duplicate minute key groups=0/0/0，P0/P1/P2=0/0/0；C1 later-minute run `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed，latest_closed_minute=2026-06-05T11:27:00+08:00，rows stock/index/board/total=33228/234/6552/40014，objects processed/passed=342/342，quality rows=8，duplicate minute key groups=0/0/0，P0/P1/P2=0/0/0；B2 stock/index lineage expansion subscription control-row run `market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，candidate/subscription/pull_plan=6696/3350/4，quality rows=15，P0/P1/P2=0/2/0，P1 residuals=stock/index completion-only not_ready 136/2 与 board 14:59 quality-visible not_ready 428；market_data_pulled=false，market_data_fact_written=false。20260605 A1/C1 expansion staged execute 已 POST_REVIEW_PASS：A1 run `previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，minute rows stock/index/board/total=400320/1680/0/402000，preload status rows=1668/7/0/1675，P0/P1/P2=0/1/0，duplicate minute key groups=0/0/0，rollback_safe=true；C1 run `today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，latest_closed_minute=2026-06-05T11:27:00+08:00，minute rows stock/index/board/total=195156/819/0/195975，P0/P1/P2=0/0/0，duplicate minute key groups=0/0/0，rollback_safe=true；B2 realtime projection run `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` 已 POST_REVIEW_PASS，projection rows stock/index/board/total=1952/9/428/2389，ready/not_ready=969/1420，ready_by_asset=stock 969，not_ready_by_asset=stock/index/board 983/9/428，P0/P1/P2=0/4/0，quality rows=7，fact-only trace compatibility=true rows=2389，snapshot_event_id empty rows=2389，required fact trace complete=2389，writes_outbox=false，event outbox/inbox/checkpoint refs=0/0/0，N4/N5/N6 refs=0/0/0，rollback_safe=true。当前 N5 v1 run 已按 preserve-only 登记；fresh DB proof 显示 N6 shadow/user projection rows 已存在并引用该 N5 run，且 `user_projection_run.status=passed`。下一步只允许 runtime_control read-only dashboard/lineage review、N5 action readiness / dry-run gate、后续 N4/N5 planning gate，或另开真实 delivery/push readiness gate。

20260605 N4 local trigger dry-run / readiness gate 已由 matched-only combined execute 收口并 POST_REVIEW_PASS：execute_run_id=`trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`，common_trigger_run.status=passed，run row P0/P1/P2=0/0/0，common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=4/1537/1537/1537，quality table 4 rows all P0 passed；TriggerMatched=1537，TriggerPendingMarketData/TriggerStateChanged=0/0；signal_type B_BUY/S_SELL=1286/251；trigger_mark_candidate normal/30m_volume/30m_shrink=1262/87/188；outbox pending/delivered/delivering=1537/0/0；invalid N5 entry=0，deprecated runtime signal count=0；common_event_inbox/checkpoint refs=0/0，N5 action_run/action_event refs=0/0，N6 user_signal_projection/user_signal_card/user_notification_queue refs=0/0/0；market_data_pulled=false，action/user/voice/sim/real_trade touched=false，worker_started=false；rollback_safe=true，rollback_sql=`sql/N4_20260605_execute_rollback.sql`。当前下一步只允许 `N5_action` readiness / dry-run gate；runtime_control 不消费 N4 outbox、不执行 N5、不启动 worker、不进入 N6。

```text
official daily ingestion =
  source_batch_id = official_daily_ingest_20260602_v1
  stock_daily_bar_fact = 5507
  index_daily_bar_fact = 83
  board_daily_bar_fact = 428
  total = 6018
  common_ingest_batch = 1
  common_quality_gate_result = 31
  common_active_source_version = 3
  source validation P0/P1/P2 = 0/19/0
  P0 failed = 0
  outbox/inbox/checkpoint delta = 0/0/0
  rollback_safe = true
  rollback_sql = sql/N1_official_daily_20260602_ingestion_rollback.sql

official daily active source_version =
  stock_daily_20260602_v1
  index_daily_20260602_v1
  board_daily_20260602_v1

condition source activation =
  source_batch_id = condition_source_activation_20260602_v1
  stock_daily_basic = 5507
  stock_financial_metrics_fact = 5507
  index_membership_fact = 12841
  board_membership_fact = 56960
  total = 80815
  common_ingest_batch = 1
  common_quality_gate_result = 15
  common_active_source_version = 4
  P0/P1/P2 = 0/2/1
  P0 failed = 0
  outbox/inbox/checkpoint delta = 0/0/0
  official daily untouched = true
  N2/N3/N4/N5/N6 refs = 0/0/0/0/0
  worker/parquet/delivery/notification/real_trade = false
  rollback_safe = true
  rollback_sql = sql/N1_condition_source_20260602_activation_rollback.sql
```

20260602 condition source active source_version:

```text
stock_daily_basic_20260602_v1
stock_financial_20260602_v1
index_membership_20260602_v1
board_membership_20260602_v1
```

Rollback boundary:

```text
official daily rollback scope =
  official_daily_ingest_20260602_v1
  stock_daily_20260602_v1
  index_daily_20260602_v1
  board_daily_20260602_v1

condition source rollback scope =
  condition_source_activation_20260602_v1
  stock_daily_basic_20260602_v1
  stock_financial_20260602_v1
  index_membership_20260602_v1
  board_membership_20260602_v1

both rollback SQL files hard-fail before DELETE and guard outbox/inbox/checkpoint and downstream N2-N6 refs.
```

Next allowed gate:

```text
N2 condition layer 20260602, N3 subscription 20260603, A1 previous-day minute preload 20260603, common_trade_calendar(20260603) repair, B1 realtime snapshot 20260603 fact-only retry, N4 trigger_context_snapshot 20260603 rebuild, N4 canonical trigger execute after matcher fix, N5 canonical action execute after status fix, N4 v4 execute, N5 v1 market-action-confirmation execute, N6 v1 shadow projection post-review recovery, 035 N6 delivery schema alignment migration, N6 delivery noop preview rollback, and 20260603 read-only lineage closeout passed; current endpoint is N6 shadow projection / queued_only preserved, with target preview rows=0; next allowed gate is runtime_control read-only lineage/dashboard review or a separate real delivery/push readiness gate
```

Still forbidden from this runtime_control registration:

```text
do not execute additional N2/N3/A1
do not write database
do not consume outbox
do not start worker
do not trigger delivery / notification / real trade
```

## 6.8.2 20260602 N2 condition layer passed

20260602 N2 condition layer run-once execute 已完成，并经 artifact / policy alignment 后通过 post-review。该登记只说明 N2 `20260602 -> 20260603` 条件层 baseline 已 ready；后续 N3 subscription 与 A1 previous-day minute preload 已另行登记为 passed。runtime_control 本轮未执行 B1/N4/N5/N6，未消费 outbox，未启动 worker。

```text
run_id = condition_layer_20260602_source_20260602_v1
status = passed_active
source_trade_date = 20260602
for_trade_date = 20260603
active_passed_count = 1

policy_source = 8782_console
policy_id = n2_default_policy
policy_version = v4
policy_hash = ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576

P0/P1/P2 = 0/9/3
common_condition_quality_item = 109
row_mismatches = {}

condition_basis stock/index/board = 5507/83/428
condition_pool stock/index/board = 4182/168/890
minute_target_scope stock/index/board = 4164/168/890
condition_display_basis stock/index/board = 1963/83/428
monitor_target stock/index/board = 5507/83/428

outbox/inbox/checkpoint refs = 0/0/0
N3/N4/N5/N6 refs = 0/0/0/0
market_data_pulled = false
downstream_layers_touched = false
rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260602_rollback.sql
```

Policy / artifact alignment:

```text
canonical policy = broad policy from configs/n2_policy/default_policy_draft.json
execute runner and dry-run/contract/preflight artifact generator now use the same policy loader
expected rows = actual rows = current DB broad rows
post_review = POST_REVIEW_PASS
```

Next allowed gate:

```text
N4 v4 execute 20260603 and N5 v1 market-action-confirmation execute 20260603 have passed; next allowed gate is N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute B1/N4/N5/N6
do not write database
do not consume outbox
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.3 20260603 N3 subscription passed

20260603 N3 subscription control-row execute 已完成，并通过 post-review。该登记只说明 N3 subscription control baseline 已 ready；runtime_control 本轮未执行 A1/B1/N4/N5/N6，未拉行情，未写 market facts，未消费 outbox，未启动 worker。

```text
market_data_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
source_condition_run_id = condition_layer_20260602_source_20260602_v1
common_market_data_run.status = passed
source_trade_date = 20260602
for_trade_date = 20260603
prev_trade_date = 20260602

candidate rows = 5776
subscription rows = 3028
pull_plan rows = 9
quality rows = 34
P0/P1/P2 = 0/1/0

source scope stock/index/board/total = 4164/168/890/5222
objects stock/index/board/total = 1963/83/428/2474
required_data_kind realtime_daily_snapshot/minute_bar_1m/previous_day_minute_bar_1m = 2474/277/277

market_data_pulled = false
market_data_fact_written = false
event_outbox_written = false
downstream_layers_touched = false
worker_started = false
scoped outbox/inbox/checkpoint refs = 0/0/0
A1/B1/N4/N5/N6 touched = false
rollback_safe = true
rollback_sql = sql/N3_subscription_20260603_rollback.sql
```

P1 warning handling:

```text
P1 = historical common_trade_calendar(20260603) missing warning
blocks_subscription_execute = false
blocks_later_b1_realtime_snapshot_execute = false after calendar repair passed
calendar repair = trade_calendar_20260603_patch_v1
```

Rollback boundary:

```text
rollback SQL hard-fails before DELETE
guard covers outbox / inbox / checkpoint, downstream N3 facts, action-confirmation metric refs, and N4/N5/N6/user refs
DELETE scope is limited to N3 subscription control rows:
  common_market_data_pull_plan
  common_market_data_subscription
  common_market_data_subscription_candidate
  common_market_data_quality_item
  common_market_data_run
```

Next allowed gate:

```text
N4 v4 execute 20260603 and N5 v1 market-action-confirmation execute 20260603 have passed; next allowed gate is N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute B1/N4/N5/N6
do not pull realtime market data
do not write realtime snapshot/projection facts
do not consume outbox
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.4 20260603 A1 previous-day minute preload passed

20260603 A1 previous-day minute preload execute 已完成，并通过 post-review。该登记只说明 previous-day minute facts/status 已 ready；runtime_control 本轮未执行 B1/N4/N5/N6，未写 realtime snapshot/projection，未写 outbox/inbox/checkpoint，未启动 worker。

```text
preload_run_id = previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
source_subscription_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
common_market_data_run.status = passed
previous_day_minute_date = 20260602
for_trade_date = 20260603

actual rows stock/index/board/total = 57840/480/8160/66480
object status stock/index/board/total = 241/2/34/277 all passed
missing/partial/failed = 0/0/0
quality rows = 12
P0/P1/P2 = 0/1/0

P1 = n3_a1_contract_p1_carried
P1 root = historical common_trade_calendar(20260603) missing warning; repair passed after A1

scoped outbox/inbox/checkpoint refs = 0/0/0
global outbox/inbox/checkpoint unchanged = 164214/68560/5163
realtime snapshot rows for this run = 0/0/0
event_outbox_written = false
downstream_layers_touched = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N3_A1_previous_day_minute_20260603_rollback.sql
```

Boundary note:

```text
A1 market_data_pulled = true
A1 market_data_fact_written = true
This is limited to previous-day minute_bar_1m facts/status for 20260602.
It is not B1 realtime snapshot, not projection, not outbox delivery, and not worker execution.
```

Rollback boundary:

```text
rollback SQL hard-fails before DELETE
guard covers common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
rollback scope clears only A1 scoped minute/status/quality/run rows:
  stock/index/board_minute_bar_1m
  stock/index/board_previous_day_minute_preload_status
  common_market_data_quality_item
  common_market_data_run
```

Next required gate after A1:

```text
B1 realtime snapshot fact-only retry, N4 trigger_context_snapshot rebuild, N4 canonical trigger execute after matcher fix, N5 canonical action execute after status fix, N4 v4 execute, and N5 v1 market-action-confirmation execute have passed; next gate is N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute B1/N4/N5/N6
do not pull realtime market data
do not write realtime snapshot/projection facts
do not consume outbox
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.5 common_trade_calendar(20260603) repair passed

`common_trade_calendar(20260603)` fix-forward repair 已完成，并通过 N1 execute/post-review 证据登记。该修复只补齐 B1 前置 calendar readiness，不代表 B1/N4/N5/N6 自动推进；runtime_control 本轮未执行 B1、未拉实时行情、未消费 outbox、未启动 worker。

```text
common_trade_calendar(20260603) = 1
is_open = true
prev_trade_date = 20260602
next_trade_date = 20260604
source = tushare.trade_cal.patch
source_batch_id = trade_calendar_20260603_patch_v1
source_version = trade_calendar_20260603_patch_v1

active source_version =
  common / trade_calendar / SSE:20260603 -> trade_calendar_20260603_patch_v1

metadata =
  common_ingest_batch = 1
  common_quality_gate_result = 11
  common_active_source_version = 1
  persisted quality P0 passed = 11

boundary =
  outbox/inbox/checkpoint delta = 0/0/0
  B1 realtime snapshot refs = 0
  N4 refs = 0
  N5 refs = 0
  N2 refs remain = 1
  N3 refs remain = 2
  A1 refs remain = 1
  worker_started = false
  realtime_market_data_pulled = false
  delivery/notification/push/voice/mobile/sim/position/real_trade = false

rollback =
  rollback_sql = sql/N1_trade_calendar_20260603_patch_rollback.sql
  rollback_safe_scope = true
  hard_fail_before_delete = true
  standalone calendar rollback currently expected to hard-fail because N2/N3/A1 refs exist
  required before calendar rollback = rollback A1, N3 subscription, N2, or open a dedicated rollback plan
```

Next allowed gate:

```text
N4 v4 execute 20260603 and N5 v1 market-action-confirmation execute 20260603 have passed; next allowed gate is N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute B1/N4/N5/N6 from runtime_control
do not pull realtime market data from runtime_control
do not consume outbox
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.6 20260603 B1 realtime snapshot fact-only passed

20260603 B1 realtime snapshot fact-only retry 已完成并通过 post-review 登记。该登记只说明 N3 realtime snapshot fact baseline 已 ready；runtime_control 本轮未执行 N4/N5/N6，未写 outbox/inbox/checkpoint，未启动 worker，未触发 delivery / notification / push / voice / mobile / sim / position / real trade。

```text
snapshot_run_id = realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
source_subscription_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
source_condition_run_id = condition_layer_20260602_source_20260602_v1
common_market_data_run.status = passed
source_trade_date = 20260602
for_trade_date = 20260603
prev_trade_date = 20260602

actual rows stock/index/board/total = 1963/83/428/2474
expected rows stock/index/board/total = 1963/83/428/2474
quality rows = 11
P0/P1/P2 = 0/1/0

BJ fallback =
  index:BJ:899050 written, quality_status = passed
  index:BJ:899601 written, quality_status = passed
  source_version = tushare.index_daily.bj_snapshot_fallback.v1
  source_path = tushare.index_daily.previous_trade_date_bootstrap

boundary =
  writes_outbox = false
  generated_outbox_events = []
  scoped outbox/inbox/checkpoint refs = 0/0/0
  global outbox/inbox/checkpoint delta = 0/0/0
  N4/N5/N6 refs = 0
  downstream_layers_touched = false
  worker_started = false
```

P1 warning handling:

```text
P1 = n3_b1_contract_p1_carried
P1 is a carried non-blocking contract warning.
rows matched expected counts exactly and all snapshot objects passed.
```

Rollback boundary:

```text
rollback_safe = true
rollback_sql = sql/N3_B1_realtime_snapshot_20260603_rollback.sql
rollback SQL hard-fails before DELETE
guard covers common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
guard covers N4/N5/N6 downstream refs, downstream_layers_touched, and worker_started
DELETE scope is limited to B1 scoped snapshot rows / quality / run
does not touch N2, N3 subscription, A1 minute facts, outbox/inbox/checkpoint, or N4/N5/N6 facts
```

Next allowed gate:

```text
N6 readiness/shadow gate
delivery/notification gate
runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute N6 from runtime_control
do not consume outbox
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.7 20260603 N4 trigger_context_snapshot rebuild passed

20260603 N4 trigger context rebuild 已完成并通过 post-review 登记；随后 N4 local trigger dry-run 与 matcher fix 后 N4 canonical trigger execute 已单独完成并登记为 passed。该小节保留 context rebuild baseline；当前主线下一步以 6.8.8 的 N4 canonical trigger execute passed after matcher fix 为准。

```text
trigger_context_run_id = trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1
source_condition_run_id = condition_layer_20260602_source_20260602_v1
source_market_data_run_id = realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
market_subscription_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
for_trade_date = 20260603
source_trade_date = 20260602
prev_trade_date = 20260602

common_trigger_run.status = passed
rows stock/index/board/total = 4164/168/890/5222
object coverage stock/index/board = 1963/83/428
BUY_HINT / SELL_HINT trace rows = 216/61
period_trigger_baseline_json_missing = 0
required_period_not_ready_rows = 0
common_trigger_run/common_trigger_quality_item = 1/62
P0/P1/P2 = 0/0/0
```

Boundary:

```text
common_trigger_state = 0
common_trigger_match = 0
common_event_outbox = 0
common_event_inbox refs = 0
checkpoint refs = 0
N5 refs = 0
N6 refs = 0
N3 B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0
market_data_pulled = false
n3_event_consumed = false
downstream_layers_touched = false
worker_started = false
old_system_touched = false
real_trade = false
```

Rollback boundary:

```text
rollback_safe = true
rollback_sql = sql/N4_20260603_trigger_context_rebuild_rollback.sql
rollback SQL hard-fails before DELETE
guard covers common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
guard covers trigger_state / trigger_match
guard covers N5 action_run / action_event refs
guard covers N6 user_projection_run / user_signal_projection / user_signal_card / user_notification_queue via to_regclass
DELETE scope is limited to common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run
```

Next allowed gate:

```text
N4 v4 execute 20260603 and N5 v1 market-action-confirmation execute 20260603 have passed; next allowed gate is N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not execute N6 from runtime_control
do not consume N4 outbox
do not update N4 outbox status
do not consume outbox
do not start worker
do not enter N6
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.8 20260603 N4 canonical trigger execute passed after matcher fix

20260603 N4 canonical trigger run-once 已在 matcher fix 后重新执行并通过 post-review 登记，且 20260603 N5 canonical action retry 已在 status persistence fix 后通过 post-review。该小节登记当前有效 N4 trigger state/match/outbox baseline 证据。runtime_control 本轮不消费 N4/N5 outbox，不执行 N6，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

```text
execute_run_id = trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
trigger_context_run_id = trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1
snapshot_run_id = realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
market_subscription_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
for_trade_date = 20260603

common_trigger_run.status = passed
P0/P1/P2 = 0/1/0
quality rows = 17
quality distribution = P0 passed 16 / P1 warning 1

common_trigger_state = 10167
common_trigger_match = 10167
common_event_outbox = 20334
TriggerMatched = 1252
TriggerPendingMarketData = 8915
TriggerStateChanged = 10167
```

N4 outbox status:

```text
pending = 20334
delivered = 0
delivering = 0
```

Canonical checks:

```text
runtime signal_type B_BUY/S_SELL = 5164/5003
deprecated runtime signal count = 0
trigger_mark_candidate normal/30m_volume/30m_shrink = 5222/2474/2471
pending_market_data trigger_live=false = 8915
matched trigger_live=true = 1252
TriggerStateChanged rows in common_trigger_match = 0
final action_mark columns in trigger_state/match = 0
```

Anomaly proof after matcher fix:

```text
B_BUY current_price/close <= open = 0
S_SELL current_price/close >= open = 0
B_BUY amount below localized baseline = 0
S_SELL amount above localized baseline = 0
```

Boundary:

```text
common_event_inbox refs = 0
common_event_consumer_checkpoint refs = 0
source B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0
N5 common_action_run/common_action_event refs = 0/0
N6 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue refs = 0/0/0/0
market_data_pulled = false
action_layer_touched = false
user_layer_touched = false
voice_touched = false
sim_touched = false
real_trade_touched = false
worker_started = false
```

Rollback boundary:

```text
rollback_safe = true before downstream consumption
rollback_sql = sql/N4_20260603_canonical_trigger_execute_rollback.sql
rollback SQL hard-fails before DELETE
guard covers delivered/delivering outbox, common_event_inbox, common_event_consumer_checkpoint
guard covers N5 common_action_run / common_action_event refs
guard covers optional N6 user_projection_run / user_signal_projection / user_signal_card / user_notification_queue refs
DELETE scope is limited to common_event_outbox, common_trigger_match, common_trigger_state, common_trigger_quality_item, common_trigger_run
```

Next allowed gate:

```text
N6 readiness/shadow gate
delivery/notification gate
runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not consume N4 outbox from runtime_control
do not execute N6 from runtime_control
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.8.9 20260603 N5 canonical action execute passed after status fix

20260603 N5 canonical action consumer run-once retry 已基于 6.8.8 matcher fix 后 N4 run 执行，并在 status persistence fix 后通过 post-review。此前 failed run 已按 run_id rollback；当前有效 N5 run 为本小节登记的 retry passed run。runtime_control 本轮不消费 N4/N5 outbox，不执行 N6，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

```text
action_run_id = action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
source_trigger_run_id = trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
consumer_name = n5_action_consumer_v1

common_action_run.status = passed
run-level P0/P1/P2 = 0/0/0
common_action_run = 1
common_action_quality_item = 8915
stock/index/board_action_fact = 1056/26/170
common_action_event = 1252
N5 common_event_outbox = 1252
N5 consumer inbox = 20334
N5 consumer scoped checkpoint = 2474
```

Event distribution:

```text
ActionBlocked = 1252
ActionEligible = 0
ActionExecuted = 0
ActionSkipped = 0
N5 outbox pending/delivered/delivering = 1252/0/0
```

N4 source preservation:

```text
N4 execute_run_id = trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
N4 common_trigger_run.status = passed
TriggerMatched = 1252 pending
TriggerPendingMarketData = 8915 pending
TriggerStateChanged = 10167 pending
total pending = 20334
delivered / delivering = 0/0
```

Boundary:

```text
N6/user refs = 0
common_position_state/event = 0/0
N5 outbox consumed = false
N4 outbox status updated = false
market_data_pulled = false
trigger_layer_mutated = false
user_layer_touched = false
voice_touched = false
sim_touched = false
real_trade_touched = false
worker_started = false
```

Rollback boundary:

```text
rollback_safe = true before downstream consumption
rollback_sql = sql/N5_20260603_canonical_action_execute_rollback.sql
N5 outbox delivered/delivering = 0/0
N6/downstream refs = 0
rollback SQL hard-fails before DELETE
guard covers N5 outbox delivered/delivering, downstream inbox/checkpoint refs, non-scoped consumer refs, and user/voice/mobile/sim/position refs
DELETE scope is limited to N5 scoped action run outputs, N5 inbox/checkpoint rows, and N5 outbox rows
rollback does not touch N4/N3/N2/N6 facts
```

Next allowed gate:

```text
N6 readiness/shadow gate
delivery/notification gate
runtime_control read-only lineage review
```

Still forbidden from this runtime_control registration:

```text
do not consume N4 outbox from runtime_control
do not consume N5 outbox from runtime_control
do not execute N6 from runtime_control
do not start worker
do not trigger delivery / notification / push / voice / mobile / sim / position / real trade
```

## 6.9 20260528 -> 20260529 N2 condition layer v1 passed

20260528 -> 20260529 N2 condition layer v1 execute 已完成，曾作为 N2 active lineage 登记；后续已被 `condition_layer_20260528_source_20260528_v2` supersede。v1 rows and downstream refs preserved，并继续作为既有 N3/N4/N5/N6 旧 lineage 的来源证据。该登记只更新总控文档，不进入 N3 execute，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N4/N5/N6。

```text
N1 official daily active source_version =
  stock_daily_20260528_v1
  index_daily_20260528_v1
  board_daily_20260528_v1

N1 condition source active source_version =
  stock_daily_basic_20260528_v1
  stock_financial_20260528_v1
  index_membership_20260528_v1
  board_membership_20260528_v1

N2 previous active condition run =
  condition_layer_20260528_source_20260528_v1
status = superseded by condition_layer_20260528_source_20260528_v2
```

N2 execute summary:

```text
run_id = condition_layer_20260528_source_20260528_v1
status = passed_active
passed_active_count = 1
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
P0/P1/P2 = 0/6/3
common_condition_quality_item = 106

row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4271/18/263
  minute_target_scope stock/index/board = 4271/18/263
  monitor_target stock/index/board = 5506/83/428
  condition_display_basis stock/index/board = 5506/83/428

canonical_signal_audit_passed = true
deprecated_signal_rows = 0
noncanonical_signal_rows = 0
outbox/inbox/checkpoint_delta = 0/0/0
downstream_refs common_market_data_run/common_trigger_run/common_action_run = 0/0/0
market_data_pulled = false
N3/N4/N5/N6_entered = false
worker_started = false
old_system_touched = false
rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260528_rollback.sql
```

Supersede status:

```text
v1 rows and downstream refs preserved = true
N3/N4/N5/N6 remain on old v1 lineage until a separately authorized N3 rebuild
```

## 6.9.1 20260528 -> 20260529 N2 canonical condition v2 active lineage supersede passed

N2 canonical condition v2 active lineage supersede execute 已完成，并曾登记为新的 N2 active lineage；后续已被 6.9.2 的 v3 active lineage supersede。该登记只更新总控文档，不执行 N3 subscription rebuild，不拉行情，不进入 N4/N5/N6，不启动 worker，不触碰旧系统。

```text
new active run_id = condition_layer_20260528_source_20260528_v2
v2.status = passed_active
previous active v1 = condition_layer_20260528_source_20260528_v1
v1.status = superseded
v1 rows and downstream refs preserved = true

row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4271/18/263
  minute_target_scope stock/index/board = 4271/18/263
  condition_display_basis stock/index/board = 5506/83/428
  monitor_target stock/index/board = 5506/83/428

quality_item = 103
P0/P1/P2 = 0/3/3

canonical target checks =
  alias mismatch = 0
  negative numeric fields = 0
  forbidden fields = 0
  first failed attempt rolled back due negative reference_target_price CHECK
  writer fixed: negative canonical target numeric fields write NULL
  raw negative value preserved only in trace

boundary =
  N3 not automatically rebuilt = true
  N4/N5/N6 not entered = true
  worker_started = false
  outbox/inbox/checkpoint delta = 0/0/0

rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql
```

Next allowed gate:

```text
historical next gate was N3_market_data subscription rebuild gate for condition_layer_20260528_source_20260528_v2
current 20260528 source-date active run is now condition_layer_20260528_source_20260528_v5
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not pull market data
do not write outbox/inbox/checkpoint
do not start worker
do not enter B1
do not enter N4/N5/N6
do not write user/voice/mobile/sim/position/real trade
```

## 6.9.2 20260528 -> 20260529 N2 display scope alignment v3 preserved / superseded

N2 display scope alignment v3 曾登记为 active condition lineage；后续已被 v5 symmetry target price alignment active supersede 替代。该登记只保留审计证据，不执行 N3 subscription rebuild，不拉行情，不进入 N4/N5/N6，不启动 worker，不触碰旧系统。

```text
N2 run = condition_layer_20260528_source_20260528_v3
v3.status = superseded by condition_layer_20260528_source_20260528_v5
previous N2 run = condition_layer_20260528_source_20260528_v2
v2.status = superseded
v1 downstream lineage preserved = true

row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4271/18/263
  minute_target_scope stock/index/board = 4271/18/263
  condition_display_basis stock/index/board = 2021/9/127
  monitor_target stock/index/board = 5506/83/428

quality =
  common_condition_quality_item = 103
  P0/P1/P2 failed = 0/0/0

alignment checks =
  display duplicate groups = 0/0/0
  alias mismatch = 0
  negative numeric rows = 0
  locked_target_price / target_lock_status absent = true

boundary =
  downstream refs = 0
  outbox/inbox v3 refs = 0/0
  N3 not automatically rebuilt = true
  N4/N5/N6 not entered = true
  worker_started = false

rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql
```

Historical next gate:

```text
superseded by condition_layer_20260528_source_20260528_v5
```

Still forbidden from this runtime_control registration:

```text
do not execute N3 subscription from runtime_control
do not pull market data
do not write outbox/inbox/checkpoint
do not start worker
do not enter N4/N5/N6
do not touch old system
```

## 6.9.2a 20260528 -> 20260529 N2 symmetry target price alignment v5 passed_active

N2 symmetry target price alignment v5 已登记为 20260528 source-date 的 active condition lineage。该登记只更新总控文档，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N4/N5/N6，不触碰旧系统或真实交易。

```text
active N2 run = condition_layer_20260528_source_20260528_v5
v5.status = passed_active
previous_active_run_id = condition_layer_20260528_source_20260528_v4
v4.status = superseded
passed_active_count = 1

source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
```

N2 execute summary:

```text
row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4271/169/875
  minute_target_scope stock/index/board = 4251/169/875
  condition_display_basis stock/index/board = 2011/83/428
  monitor_target stock/index/board = 5506/83/428

common_condition_quality_item = 103
P0/P1/P2 = 0/3/3
```

000027 golden:

```text
stock_identity_key = stock:SZ:000027
main_up_anchor = W
up_reference_period = D
up_amplitude = 1.17
up_base_price = 7.25
buy_target_price = 8.42
reference_target_price = 8.42
amplitude_price_policy = OFFICIAL_QFQ_BODY_BOUNDARY
base_price_policy = MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN
```

Boundary:

```text
outbox refs = 0
inbox refs = 0
N3/N4/N5 refs = 0/0/0
deprecated signal rows = 0
alias mismatch = 0
invalid reference period = 0
locked_target_price / target_lock_status absent = true
market_data_pulled = false
downstream_layers_touched = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql
```

Next allowed gate:

```text
layer_role = N3_market_data
gate = 20260529 subscription rebuild readiness / execute gate
source_condition_run_id = condition_layer_20260528_source_20260528_v5
do not execute N3 from runtime_control
do not pull market data from runtime_control
```

## 6.9.3 20260529 -> 20260601 N2 condition layer v1 preserved / superseded

20260529 -> 20260601 N2 condition layer v1 execute 曾完成并登记为 source-date active condition lineage；后续已被 6.9.5 的 financial canonical v2 active supersede 替代，当前状态为 `superseded`。该历史登记只保留审计证据，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N4/N5/N6，不触碰旧系统或真实交易。

```text
N1 official daily active source_version =
  stock_daily_20260529_v1
  index_daily_20260529_v1
  board_daily_20260529_v1

N1 condition source active source_version =
  stock_daily_basic_20260529_v1
  stock_financial_20260529_v1
  index_membership_20260529_v1
  board_membership_20260529_v1

N1 financial source used by this N2 run =
  stock_financial_20260529_v1

Latest N1 active financial after post-chain handoff =
  stock_financial_20260529_v2
  not consumed by this N2 run

N2 active run =
  condition_layer_20260529_source_20260529_v1
status = superseded after condition_layer_20260529_source_20260529_v2
```

N2 execute summary:

```text
run_id = condition_layer_20260529_source_20260529_v1
status = passed_active
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
P0/P1/P2 = 0/9/3
common_condition_quality_item = 109

row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4342/187/942
  minute_target_scope stock/index/board = 4323/187/942
  condition_display_basis stock/index/board = 1973/83/428
  monitor_target stock/index/board = 5506/83/428

canonical_signal_audit = passed
deprecated_signal_rows = 0
noncanonical_signal_rows = 0
outbox/inbox/checkpoint_delta = 0/0/0
downstream_refs N3/N4/N5 = 0/0/0
market_data_pulled = false
N3/N4/N5/N6_entered = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260529_rollback.sql
```

Historical next gate status:

```text
financial canonical pass-through gate =
  completed by condition_layer_20260529_source_20260529_v2
symmetry target price target-machine active supersede gate =
  completed by condition_layer_20260529_source_20260529_v3
anchor-segment alignment active supersede gate =
  completed by condition_layer_20260529_source_20260529_v4
secondary-anchor active supersede gate =
  completed by condition_layer_20260529_source_20260529_v5
level score active supersede gate =
  completed by condition_layer_20260529_source_20260529_v6

N3_market_data subscription gate for for_trade_date=20260601 =
  should use source_condition_run_id = condition_layer_20260529_source_20260529_v6
  do not use v1/v2/v3/v4/v5 except for historical audit
```

Still forbidden from this runtime_control registration:

```text
do not execute N3 subscription from runtime_control
do not pull market data
do not write outbox/inbox/checkpoint
do not start worker
do not enter N4/N5/N6
do not touch old system
do not write user/voice/mobile/sim/position/real trade
```

## 6.9.4 20260529 stock_financial canonical metrics v2 passed

20260529 stock_financial canonical metrics v2 execute 已完成，并通过 N1 post-review。该登记只更新总控文档；不执行 N2 condition rebuild，不写 condition_* 表，不进入 N3/N4/N5/N6，不启动 worker，不触碰旧系统或真实交易。

```text
source_batch_id = stock_financial_canonical_20260529_v1
source_version = stock_financial_20260529_v2
previous_source_version = stock_financial_20260529_v1
financial_metric_version = financial_metric_v1

stock_financial_metrics_fact v2 rows = 5506
stock_financial_metrics_fact v1 rows = 5506
common_ingest_batch rows = 1
common_ingest_batch.row_count = 5506
common_ingest_batch.status = passed
common_quality_gate_result rows = 13
active stock_financial 20260529 = stock_financial_20260529_v2
```

Quality:

```text
P0/P1/P2 = 0/8/2
P0 passed = 2
P1 warnings = 8
P2 passed/warnings = 1/2
```

Boundary:

```text
outbox/inbox/checkpoint delta = 0/0/0
condition base table refs to v2 = 0
Parquet written = false
N2/N3/N4/N5/N6 entered = false
worker_started = false
old_system_touched = false
real_trading = false
rollback_safe = true
rollback_sql = sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql
rollback batch scope data_type = stock_financial_canonical_metrics
```

Follow-up status:

```text
N2_condition financial canonical pass-through / active supersede gate =
  completed by condition_layer_20260529_source_20260529_v2
N2_condition symmetry target price target-machine active supersede gate =
  completed by condition_layer_20260529_source_20260529_v3
N2_condition anchor-segment alignment active supersede gate =
  completed by condition_layer_20260529_source_20260529_v4
N2_condition secondary-anchor active supersede gate =
  completed by condition_layer_20260529_source_20260529_v5
N2_condition level score active supersede gate =
  completed by condition_layer_20260529_source_20260529_v6

Next N3 handoff =
  layer_role=N3_market_data
  subscription rebuild readiness / execute gate for for_trade_date=20260601
  source_condition_run_id=condition_layer_20260529_source_20260529_v6
```

## 6.9.5 20260529 N2 financial canonical v2 active supersede passed / preserved

20260529 -> 20260601 N2 financial canonical active supersede execute 已完成，并通过 post-review；后续已被 6.9.6 target-machine v3 active supersede 替代，v2 rows 保留用于审计。该登记只更新总控文档，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N4/N5/N6，不触碰旧系统或真实交易。

```text
new run_id = condition_layer_20260529_source_20260529_v2
v2.status = superseded after condition_layer_20260529_source_20260529_v3
previous run_id = condition_layer_20260529_source_20260529_v1
v1.status = superseded

source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
financial_source_version_used_at_execute = stock_financial_20260529_v2
```

N2 execute summary:

```text
row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428

common_condition_quality_item = 106
P0/P1/P2 = 0/6/3
```

Financial canonical pass-through:

```text
basis mismatch = 0
pool mismatch = 0
scope mismatch = 0
display mismatch = 0
canonical_financial_pass_through_mismatch = 0
finance_sector_warning_rows = 120
pre_revenue_warning_rows = 1
warning_preservation_missing = 0
```

Boundary:

```text
outbox/inbox/checkpoint delta = 0/0/0
N3/N4/N5 refs for v2 = 0/0/0
market_data_pulled = false
downstream_layers_touched = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_condition_layer_20260529_financial_v2_rollback.sql
```

Next allowed gate:

```text
completed by = condition_layer_20260529_source_20260529_v3
```

## 6.9.6 20260529 N2 symmetry target price target-machine v3 preserved / superseded

20260529 -> 20260601 N2 symmetry target price target-machine alignment v3 active supersede execute 已完成，并通过 N2 post-review；后续已被 6.9.7 的 anchor-segment alignment v4 active supersede。该登记只保留审计证据，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N4/N5/N6，不触碰旧系统或真实交易。

```text
new run_id = condition_layer_20260529_source_20260529_v3
v3.status = passed_active
previous run_id = condition_layer_20260529_source_20260529_v2
v2.status = superseded
active_passed_active_count = 1

source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
financial_source_version_used_at_execute = stock_financial_20260529_v2
policy_version = configs/n2_policy/default_policy_draft.json v4
```

N2 execute summary:

```text
row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428

common_condition_quality_item = 106
P0/P1/P2 = 0/6/3
```

Golden target proof:

```text
000543 皖能电力:
  main_up_anchor = W
  up_reference_period = D
  A段 = 20260506 -> 20260529
  segment_low/high = 8.09/9.80
  amplitude = 1.71
  trend_break_date = 20260526
  base_window = 20260527 -> 20260529
  base_price = 9.11
  buy_target_price/reference_target_price = 10.82/10.82

000027 深圳能源:
  buy_target_price/reference_target_price = 8.45/8.45
```

Boundary:

```text
common_event_outbox delta = 0
common_event_inbox delta = 0
common_event_consumer_checkpoint delta = 0
v3 downstream refs = 0
market_data_pulled = false
downstream_layers_touched = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql
```

Next allowed gate:

```text
layer_role = N3_market_data
gate = 20260601 subscription rebuild readiness / execute gate
historical source_condition_run_id = condition_layer_20260529_source_20260529_v3
historical v4 source_condition_run_id = condition_layer_20260529_source_20260529_v4
historical v5 source_condition_run_id = condition_layer_20260529_source_20260529_v5
current source_condition_run_id = condition_layer_20260529_source_20260529_v6
do not execute N3 from runtime_control
do not pull market data from runtime_control
```

## 6.9.7 20260529 N2 anchor-segment alignment v4 preserved / superseded

20260529 -> 20260601 N2 anchor-segment alignment v4 曾登记为 active condition lineage；后续已被 6.9.8 的 secondary-anchor v5 active supersede。该登记只保留审计证据，不执行 DB，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N3/N4/N5/N6。

```text
N2 run = condition_layer_20260529_source_20260529_v4
v4.status = superseded after condition_layer_20260529_source_20260529_v5
previous active v3 = condition_layer_20260529_source_20260529_v3
v3.status = superseded

source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
```

N2 execute summary:

```text
row counts aligned =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428

P0/P1/P2 = 0/6/3
```

Golden target proof:

```text
000600 = 12.93
000543 = 10.82
000027 = 8.45
```

Boundary:

```text
N3/N4/N5/N6 refs = 0/0/0/0
outbox/inbox/checkpoint refs = 0/0/0
N3 not automatically rebuilt = true
N4/N5/N6 not entered = true
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql
```

Next allowed gate:

```text
layer_role = N3_market_data
gate = 20260601 subscription rebuild readiness / execute gate
historical source_condition_run_id = condition_layer_20260529_source_20260529_v4
historical v5 source_condition_run_id = condition_layer_20260529_source_20260529_v5
current source_condition_run_id = condition_layer_20260529_source_20260529_v6
do not execute N3 from runtime_control
do not pull market data from runtime_control
```

## 6.9.8 20260529 N2 secondary-anchor v5 preserved / superseded

20260529 -> 20260601 N2 secondary-anchor v5 曾登记为 active condition lineage；后续已被 6.9.9 的 level score v6 active supersede。该登记只保留审计证据，不执行 DB，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N3/N4/N5/N6。

```text
N2 run = condition_layer_20260529_source_20260529_v5
v5.status = superseded after condition_layer_20260529_source_20260529_v6
previous active v4 = condition_layer_20260529_source_20260529_v4
v4.status = superseded

source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
```

N2 execute summary:

```text
row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428
  common_condition_quality_item = 106

P0/P1/P2 = 0/6/3
```

Boundary:

```text
N3/N4/N5/N6 refs = 0/0/0/0
outbox/inbox/checkpoint refs = 0/0/0
N3 not automatically rebuilt = true
N4/N5/N6 not entered = true
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql
```

Next allowed gate:

```text
layer_role = N3_market_data
gate = 20260601 subscription rebuild readiness / execute gate
historical source_condition_run_id = condition_layer_20260529_source_20260529_v5
current source_condition_run_id = condition_layer_20260529_source_20260529_v6
do not execute N3 from runtime_control
do not pull market data from runtime_control
```

## 6.9.9 20260529 N2 level score v6 passed_active

20260529 -> 20260601 N2 level score v6 已登记为最新 active condition lineage。该登记只更新总控文档，不执行 DB，不执行 N3 subscription rebuild，不拉行情，不写 outbox/inbox/checkpoint，不启动 worker，不进入 N3/N4/N5/N6。

```text
active N2 run = condition_layer_20260529_source_20260529_v6
v6.status = passed_active
previous active v5 = condition_layer_20260529_source_20260529_v5
v5.status = superseded

source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
```

N2 execute summary:

```text
row counts =
  condition_basis stock/index/board = 5506/83/428
  condition_pool stock/index/board = 4106/187/942
  minute_target_scope stock/index/board = 4087/187/942
  condition_display_basis stock/index/board = 1862/83/428
  monitor_target stock/index/board = 5506/83/428
  common_condition_quality_item = 106

P0/P1/P2 = 0/6/3
quality severity distribution P0/P1/P2 = 91/11/4
row_match = true
level_score_ok = true
```

Level score proof:

```text
000543 level_score_up/down = 3124/0
000600 level_score_up/down = 3124/0
300327 level_score_up/down = 2999/125

level score missing/invalid =
  condition_basis 0/0
  condition_pool 0/0
  minute_target_scope 0/0
  condition_display_basis 0/0
```

Boundary:

```text
N3/N4/N5 refs = 0/0/0
outbox/inbox/checkpoint delta = 0/0/0
N3 not automatically rebuilt = true
N4/N5/N6 not entered = true
market_data_pulled = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N2_level_score_20260529_v6_rollback.sql
```

Next allowed gate:

```text
layer_role = N3_market_data
gate = 20260601 subscription rebuild readiness / execute gate
source_condition_run_id = condition_layer_20260529_source_20260529_v6
do not execute N3 from runtime_control
do not pull market data from runtime_control
```

## 6.10 20260529 N3 subscription passed

20260529 N3 subscription execute 已完成，并作为当前 N3 control lineage 登记；后续 A1 previous_day_minute preload 已另行登记为 passed。该 subscription 登记本身只更新总控文档，不拉行情，不写 realtime snapshot/minute_bar，不进入 B1/N4/N5/N6，不消费 outbox，不启动 worker。

```text
N1 official daily active source_version =
  stock_daily_20260528_v1
  index_daily_20260528_v1
  board_daily_20260528_v1

N1 condition source active source_version =
  stock_daily_basic_20260528_v1
  stock_financial_20260528_v1
  index_membership_20260528_v1
  board_membership_20260528_v1

N2 active condition run =
  condition_layer_20260528_source_20260528_v1

N3 subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

N3 subscription execute summary:

```text
market_data_run_id = market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
source_condition_run_id = condition_layer_20260528_source_20260528_v1
common_market_data_run.status = passed
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
P0/P1/P2 = 0/0/0
candidate rows = 5038
subscription rows = 2643
pull_plan rows = 7
quality rows = 34
objects stock/index/board/total = 2021/9/127/2157

required_data_kind =
  realtime_daily_snapshot = 2157
  minute_bar_1m = 243
  previous_day_minute_bar_1m = 243

canonical signals = BUY, BUY:FULL, SELL, SELL:FULL, BUY_HINT, SELL_HINT
deprecated signal rows = 0
market_data_pulled = false
market_data_fact_written = false
downstream_layers_touched = false
worker_started = false
scoped outbox/inbox/checkpoint refs = 0/0/0
global outbox/inbox/checkpoint unchanged = 105122/20726/4345
rollback_safe = true
rollback_sql = sql/N3_subscription_20260529_rollback.sql
```

Next allowed gate:

```text
20260529 A1 previous_day_minute preload, B1 pre-open, B1 live1, N4 canonical trigger execute, N5 canonical action execute, N6 canonical shadow projection, and B1 live2 standard outbox snapshot, N4 live2 canonical trigger execute, and N5 live2 canonical action execute passed; current next gate is 20260529 N6 live2 / full-day user projection gate
```

Still forbidden from this runtime_control registration:

```text
do not pull market data
do not write realtime snapshot/minute_bar
do not enter N5/N6 execute from runtime_control
do not enter N4/N5/N6
do not consume outbox
do not start worker
do not write user/voice/mobile/sim/position/real trade
```

## 6.11 20260529 A1 previous_day_minute preload passed

20260529 A1 previous_day_minute preload execute 已完成，并作为当前 N3 previous-day minute lineage 登记。该登记只更新总控文档；runtime_control 本轮不进入 B1/N4/N5/N6，不拉行情，不写 snapshot/outbox/inbox/checkpoint，不启动 worker。

```text
preload_run_id =
  previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1
```

A1 execute summary:

```text
common_market_data_run.status = passed
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
P0/P1/P2 = 0/0/0
quality rows = 12

actual rows =
  stock = 56160
  index = 0
  board = 2160
  total = 58320

object status =
  stock passed/partial/missing = 234/0/0
  index expected objects/rows = 0/0
  board passed/partial/missing = 9/0/0
  fake index pull / fake index rows = 0/0

scoped outbox/inbox/checkpoint refs = 0/0/0
global outbox/inbox/checkpoint unchanged = 105122/20726/4345
event_outbox_written = false
downstream_layers_touched = false
worker_started = false
old_system_touched = false
rollback_safe = true
rollback_sql = sql/N3_A1_previous_day_minute_20260529_rollback.sql
execute_report = docs/N3_A1_previous_day_minute_preload_execute_report.json
```

Next allowed gate:

```text
20260529 B1 pre-open、live1 realtime snapshot fact-only、N4 canonical trigger execute、N5 canonical action execute 和 N6 canonical shadow projection 均已 passed。
20260529 B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute 和 N5 live2 canonical action execute 已 passed；当前 next gate 见 6.19。
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not pull market data in runtime_control
do not write snapshot/outbox/inbox/checkpoint
do not enter N4/N5/N6
do not consume outbox
do not start worker
do not write user/voice/mobile/sim/position/real trade
```

## 6.12 20260529 B1 pre-open realtime snapshot fact-only passed

20260529 B1 pre-open realtime snapshot fact-only execute 已完成，并作为当前 N3 realtime snapshot lineage 登记。该登记只更新总控文档；runtime_control 本轮不进入 N4/N5/N6，不消费 outbox，不启动 worker，不写用户层、语音、mobile、sim、position 或真实交易。

```text
snapshot_run_id =
  realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1
```

B1 execute summary:

```text
common_market_data_run.status = passed
pre_open_fact_only = true
live_trading_snapshot_ready = false
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
P0/P1/P2 = 0/1/0
quality rows = 11

rows =
  stock = 2021
  index = 9
  board = 127
  total = 2157

missing/failed = 0/0
writes_outbox = false
generated_outbox_events = []

source_time_missing_or_preopen =
  total = 2030
  stock = 2021
  index = 9

source_time_confirmed =
  board = 127

P1 warning = n3_b1_pre_open_source_time_not_confirmed
P0 source date mismatch = 0
scoped outbox/inbox/checkpoint refs = 0/0/0
global outbox/inbox/checkpoint unchanged = 105122/20726/4345
downstream_layers_touched = false
worker_started = false
N4/N5/N6 touched = false
rollback_safe = true
rollback_sql = sql/N3_B1_realtime_snapshot_20260529_rollback.sql
execute_report_json = docs/N3_B1_realtime_daily_snapshot_execute_report.json
execute_report_md = docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_REPORT.md
```

Subsequent gate:

```text
20260529 B1 live1 realtime snapshot fact-only、N4 canonical trigger execute、N5 canonical action execute 和 N6 canonical shadow projection 已 passed。
20260529 B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute 和 N5 live2 canonical action execute 已 passed；当前 next gate 见 6.19。
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not enter N5/N6 from runtime_control
do not consume outbox
do not start worker
do not write user/voice/mobile/sim/position/real trade
```

## 6.13 20260529 B1 live1 realtime snapshot fact-only passed

20260529 B1 live1 realtime snapshot fact-only execute 已完成，并作为当前 N3 live trading snapshot readiness 证据登记。该登记只更新总控文档；runtime_control 本轮不进入 N4/N5/N6，不消费 outbox，不启动 worker，不写用户层、语音、mobile、sim、position 或真实交易。

同时保留上一笔 pre-open B1 证据：

```text
pre-open snapshot_run_id =
  realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

pre_open_fact_only = true
live_trading_snapshot_ready = false
```

Live1 snapshot run:

```text
snapshot_run_id =
  realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1
```

B1 live1 execute summary:

```text
common_market_data_run.status = passed
live_trading_snapshot_ready = true
pre_open_fact_only = false
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
P0/P1/P2 = 0/0/0
quality rows = 11

rows =
  stock = 2021
  index = 9
  board = 127
  total = 2157

missing/failed = 0/0
writes_outbox = false
generated_outbox_events = []

source-time summary =
  stock effective_quote_present/source_time_missing/partial_quality = 2021/2021/0
  index effective_quote_present/source_time_missing/partial_quality = 9/9/0
  board source_time_confirmed/effective_quote_present = 127/127

scoped outbox/inbox/checkpoint refs = 0/0/0
global outbox/inbox/checkpoint = 105122/20726/4345
downstream_layers_touched = false
worker_started = false
N4/N5/N6 untouched = true
rollback_safe = true
rollback_sql = sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql
```

Next allowed gate:

```text
20260529 N4 canonical trigger execute、N5 canonical action execute 和 N6 canonical shadow projection 已 passed。
20260529 B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute 和 N5 live2 canonical action execute 已 passed；当前 next gate 见 6.19。
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not enter N4/N5/N6 execute from runtime_control
do not consume outbox
do not start worker
do not write user/voice/mobile/sim/position/real trade
```

## 6.14 20260529 N4 canonical trigger execute passed

20260529 N4 canonical trigger execute 已完成，并作为当前 N4 trigger lineage 登记；后续 N5 canonical action execute 已另行登记为 passed。该登记只更新总控文档；runtime_control 本轮不进入 N5/N6，不消费 N4/N5 outbox，不启动 worker，不写用户层、语音、mobile、sim、position 或真实交易。

```text
execute_run_id =
  trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source snapshot run =
  realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

N4 execute summary:

```text
common_trigger_run.status = passed
P0/P1/P2 = 0/1/0

rows =
  common_trigger_run = 1
  common_trigger_quality_item = 16
  common_trigger_state = 8861
  common_trigger_match = 8861
  common_event_outbox = 17722

outbox =
  TriggerMatched = 4309 pending
  TriggerPendingMarketData = 4552 pending
  TriggerStateChanged = 8861 pending
  delivered = 0
  delivering = 0

canonical checks =
  common_trigger_match TriggerStateChanged = 0
  pending_market_data trigger_live=false = 4552
  matched trigger_live=true = 4309
  runtime signal B_BUY = 4467
  runtime signal S_SELL = 4394
  deprecated runtime signal count = 0
  action_mark payload count = 0
  trigger_mark_candidate missing count = 0

scoped inbox/checkpoint refs = 0/0
N5 refs common_action_run/common_action_event = 0/0
global delta outbox/inbox/checkpoint = +17722/0/0

boundary =
  outbox_consumed = false
  N5/N6 touched = false
  worker_started = false
  user/voice/mobile/sim/position/real_trade = false
  N2/N3 facts unchanged = true

rollback_safe = true
rollback_sql = sql/N4_20260529_canonical_trigger_execute_rollback.sql
```

Next allowed gate:

```text
20260529 N5 canonical action execute 和 N6 canonical shadow projection 已 passed；live2 standard outbox snapshot 和 N4 live2 canonical trigger execute 已另行登记，当前 next gate 见 6.18。
```

Still forbidden from this runtime_control registration:

```text
do not enter N5/N6 execute from runtime_control
do not consume N4 outbox
do not consume N5 outbox
do not start worker
do not write user/voice/mobile/sim/position/real trade
```

## 6.15 20260529 N5 canonical action execute passed

20260529 N5 canonical action execute 已完成，并作为当前 N5 action lineage 登记。该登记只更新总控文档；runtime_control 本轮不进入 N6 execute，不消费 N5 outbox，不启动 worker，不写 voice、mobile、sim、position 或真实交易。

```text
action_run_id =
  action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source N4 run =
  trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source snapshot run =
  realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

N5 execute summary:

```text
common_action_run.status = passed
P0/P1/P2 = 0/0/0
execute_report = docs/N5_20260529_canonical_action_execute_report.json

actual rows =
  common_action_quality_item = 4552
  stock_action_fact = 4037
  index_action_fact = 18
  board_action_fact = 254
  common_action_event = 4309
  common_event_outbox = 4309
  common_event_inbox = 17722
  common_event_consumer_checkpoint = 2157

event distribution =
  ActionBlocked = 4309
  ActionEligible = 0
  ActionExecuted = 0
  ActionSkipped = 0
  legacy ActionEvent/HintEvent/RiskEvent/PositionEvent = 0

N5 outbox =
  pending = 4309
  delivered = 0
  delivering = 0

boundary =
  N4 outbox status unchanged:
    TriggerMatched = 4309 pending
    TriggerPendingMarketData = 4552 pending
    TriggerStateChanged = 8861 pending
  N6 refs = 0
  position rows for this run = 0
  worker_started = false
  N6 not entered = true
  voice/mobile/sim/real_trade = false
  old_system_touched = false

rollback_safe = true
rollback_sql = sql/N5_20260529_canonical_action_execute_rollback.sql
```

Next allowed gate:

```text
20260529 N6 canonical shadow projection passed；live2 standard outbox snapshot 和 N4 live2 canonical trigger execute 已另行登记，当前 next gate 见 6.18。
```

Still forbidden from this runtime_control registration:

```text
do not consume N5 outbox
do not start worker
do not write voice/mobile/sim/position/real trade
do not touch old system
```

## 6.16 20260529 N6 canonical shadow projection passed

20260529 N6 canonical shadow projection 已完成，并作为当前 N6 user shadow lineage 登记。该登记只更新总控文档；runtime_control 本轮不消费 N5 outbox，不启动 worker，不写 push、voice、mobile、sim、position 或真实交易。

```text
projection_run_id =
  user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source_action_run_id =
  action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source N4 run =
  trigger_execute_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1
```

N6 shadow projection summary:

```text
run status = passed
P0/P1/P2 = 0/5/2

actual rows =
  user_projection_run = 1
  user_signal_projection = 4309
  user_signal_card = 4309
  user_notification_queue = 4309

projection policy =
  notification_source = n5_action_blocked
  queue_status = queued_only
  notification queued_only = 4309
  card mapping blocked / blocked / ActionBlocked / blocked = 4309
  projection_policy = blocked_unconfirmed_no_push_no_decision_no_sim_no_trade
  trace_json_nonnull = 4309
  source_action_event_type = ActionBlocked
  action_state = blocked

boundary =
  N5 outbox unchanged:
    ActionBlocked pending = 4309
    delivered = 0
    delivering = 0
  n5_outbox_consumed = false
  updates_n5_outbox_status = false
  user_signal_decision = 0
  user_watchlist = 0
  user_watchlist_item = 0
  user_sim_order/trade/position = 0
  linked decision/sim refs = 0
  worker_started = false
  push/voice/mobile = false
  position/real_trade = false
  N1-N5 unchanged = true

rollback_safe = true
rollback_sql = sql/N6_projection_business_rollback.sql
```

Allowed follow-up gates:

```text
N6 live2 / full-day user projection gate
N6 shadow projection post-review
N6 projection business rollback review, only if rollback is requested
runtime_control read-only dashboard / lineage review
```

Still forbidden from this runtime_control registration:

```text
do not consume N5 outbox
do not update N5 outbox status
do not start worker
do not push/voice/mobile
do not write sim/position/real trade
do not touch old system
```

## 6.17 20260529 B1 live2 standard outbox snapshot passed

20260529 B1 live2 standard outbox snapshot 已完成，并作为当前 N3 standard `MarketSnapshotUpdated` outbox lineage 登记。该登记只更新总控文档；runtime_control 本轮不进入 N4/N5/N6，不消费 outbox，不启动 worker，不写 push、voice、mobile、sim、position 或真实交易。

```text
snapshot_run_id =
  realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1
```

B1 live2 execute summary:

```text
common_market_data_run.status = passed
P0/P1/P2 = 0/0/0

rows =
  stock = 2021
  index = 9
  board = 127
  total = 2157

writes_outbox = true

outbox =
  MarketSnapshotUpdated = 2157 pending
  MarketDataDelayed = 0
  MarketDataMissing = 0
  MarketDisplaySnapshotUpdated = 0
  delivered = 0
  delivering = 0

scoped inbox/checkpoint refs = 0/0

boundary =
  wrote only snapshot facts/common_market_data_run/common_market_data_quality_item/common_event_outbox
  no inbox/checkpoint writes = true
  downstream_layers_touched = false
  worker_started = false
  N4/N5/N6 not entered = true
  scoped exception was used for existing N6 web app / old system process
  scoped exception proof = existing N6 web app / old system process did not consume v3 outbox

rollback_safe = true
rollback_sql = sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql
```

Next allowed gate:

```text
20260529 N4 live2 canonical trigger execute 已 passed；当前 next gate 见 6.18。
```

Still forbidden from this runtime_control registration:

```text
do not enter N4/N5/N6 execute from runtime_control
do not consume outbox
do not start worker
do not push/voice/mobile
do not write sim/position/real trade
```

## 6.18 20260529 N4 live2 canonical trigger execute passed

20260529 N4 live2 canonical trigger execute 已完成，并作为当前 live2 标准 outbox 下游触发 lineage 登记。该登记只更新总控文档；runtime_control 本轮不消费 N4 outbox，不进入 N5 execute，不启动 worker，不写 action、user、voice、mobile、sim、position 或真实交易。

```text
execute_run_id =
  trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1

source_condition_run_id =
  condition_layer_20260528_source_20260528_v1

source subscription run =
  market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1

source snapshot run =
  realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

N4 live2 execute summary:

```text
common_trigger_run.status = passed
P0/P1/P2 = 0/1/0

rows =
  common_trigger_quality_item = 17
  common_trigger_state = 8861
  common_trigger_match = 8861
  common_event_outbox = 17722

outbox =
  TriggerMatched = 4309 pending
  TriggerPendingMarketData = 4552 pending
  TriggerStateChanged = 8861 pending
  delivered = 0
  delivering = 0

canonical checks =
  runtime signal_type B_BUY = 4467
  runtime signal_type S_SELL = 4394
  deprecated runtime signal count = 0
  action_mark payload count = 0
  trigger_mark_candidate missing = 0
  matched trigger_live=true = 4309
  pending_market_data trigger_live=false = 4552
  common_trigger_match TriggerStateChanged = 0

input/boundary =
  N3 live2 input MarketSnapshotUpdated pending = 2157
  N3 input inbox/checkpoint refs = 0/0
  N5 refs = 0
  downstream inbox/checkpoint refs = 0/0
  global outbox delta = +17722
  global inbox/checkpoint delta = 0/0
  worker_started = false
  action/user/voice/mobile/sim/position/real_trade touched = false

rollback_safe = true
rollback_sql = sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql
```

Next allowed gate:

```text
20260529 N5 live2 canonical action execute 已 passed；当前 next gate 见 6.19
```

Still forbidden from this runtime_control registration:

```text
do not consume N4 outbox
do not enter N5 execute
do not start worker
do not write action/user/voice/mobile/sim/position/real trade
```

## 6.19 20260529 N5 live2 canonical action execute passed

20260529 N5 live2 canonical action execute 已完成，并作为当前 live2 action lineage 登记。该登记只更新总控文档；runtime_control 本轮不消费 N5 outbox，不进入 N6 execute，不启动 worker，不写 voice、mobile、sim、position 或真实交易。

```text
action_run_id =
  action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1

source N4 live2 run =
  trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1

source N3 live2 snapshot run =
  realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

N5 live2 execute summary:

```text
common_action_run.status = passed
P0/P1/P2 = 0/0/0

rows =
  common_action_quality_item = 4552
  stock_action_fact = 4037
  index_action_fact = 18
  board_action_fact = 254
  common_action_event = 4309
  common_event_outbox = 4309
  common_event_inbox = 17722
  common_event_consumer_checkpoint = 2157

outbox =
  ActionBlocked = 4309 pending
  ActionEligible = 0
  ActionExecuted = 0
  ActionSkipped = 0
  delivered = 0
  delivering = 0

canonical checks =
  legacy ActionEvent/HintEvent/RiskEvent/PositionEvent = 0

boundary =
  N4 outbox status unchanged:
    TriggerMatched = 4309 pending
    TriggerPendingMarketData = 4552 pending
    TriggerStateChanged = 8861 pending
  N6 refs = 0
  position rows = 0
  worker_started = false
  voice/mobile/sim/position/real_trade = false

rollback_safe = true
rollback_sql = sql/N5_20260529_live2_canonical_action_execute_rollback.sql
```

Next allowed gate:

```text
20260529 N6 live2 / full-day user projection gate
```

Still forbidden from this runtime_control registration:

```text
do not consume N5 outbox
do not enter N6 execute from runtime_control
do not start worker
do not write voice/mobile/sim/position/real trade
```

N5 current-real action execute 已 passed。N5 新语义 gate 已满足并登记：

```text
current real source_run_id allowlist =
  trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249

old synthetic source_run_id denylist =
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
  trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute

valid projection trigger input =
  event_type = TriggerMatched
  source_event_type = MarketSnapshotUpdated
  payload_json.projection_trace present

historical current-real action mapping =
  BUY_HINT / SELL_HINT -> action fact + HintEvent
  B_BUY_30M_VOL / S_SELL_30M_SHRINK -> action fact + ActionEvent
  TriggerPendingMarketData -> quality / pending only, no action fact

future canonical action mapping =
  condition_key remains trace/audit only
  N4 runtime signal_type = B_BUY / S_SELL
  N4 carries projection_30m_flag / projection_30m_type / trigger_mark_candidate
  N5 decides final action_mark = normal / 30m_volume / 30m_shrink
  N6 decides display label / alert-only / voice / sim / trade-intent presentation

forbidden interpretation =
  projection_trace signal must not be downgraded to blocked_quality / RiskEvent merely because MinuteBarClosed is absent.

execute result =
  action_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
  common_action_run.status = passed
  P0/P1/P2 = 0/0/0
  stock_action_fact = 488
  common_action_event = 488
  common_action_quality_item = 276
  common_event_inbox = 764 processed
  common_event_consumer_checkpoint = 615
  N5 outbox pending = ActionEvent 479 + HintEvent 9
  RiskEvent = 0
  PositionEvent = 0
  common_position_state = 0
  common_position_event = 0
  rollback_safe = true
  rollback_sql = sql/N5_current_real_action_execute_rollback.sql
```

N5-R4 当前仍是 dry-run：

```text
planned_action_fact_count = 8884
planned_event_count = 8884
writes_performed = false
common_event_inbox_updated = false
consumer_checkpoint_updated = false
action_fact_written = false
n5_outbox_written = false
```

## 8. 当前推进原则

下一步不得直接跳到 N6 execute 或 worker，也不得追加 N5 execute。最小安全路径是：

```text
1. 确认权威 active N2 run = condition_layer_20260522_to_20260525_20260525102249_execute。
2. 确认权威 N3 subscription run = market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute。
3. 确认权威 N3 preload run = previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute。
4. 登记 N3-B1 passed：stock/index/board snapshot rows = 2052/9/127，MarketSnapshotUpdated pending = 2188。
5. 登记 N4 current context rebuild：context rows = 4236/18/258，总计 4512，P0/P1/P2 = 0/0/0。
6. 登记旧 synthetic denylist：`20260524014029` 和 `20260525003855` 两条 trigger context source_run_id。
7. N4 real `MarketSnapshotUpdated` / realtime projection 语义 dry-run/preflight 已完成；B2 projection facts 与 N4 projection matcher gate 已 passed。
8. N3 projection schema 已就绪；N3-A1 current-lineage fill-facts passed；N3-C1 today_minute_bar_1m execute passed，实际写入 416189 行，C1 outbox = 0，未生成 MinuteBarClosed，未写 projection 表。
9. N3-B2 projection execute 已 passed：projection rows = 2188，ready=2052，not_ready=136，projection outbox/inbox = 0，B1 MarketSnapshotUpdated pending=2188。
10. N4 projection matcher dry-run / preflight / run-once execute 已 passed：N4 inbox/checkpoint = 2188，N4 outbox pending = 764。
11. N5 current-real dry-run、execute contract、rollback SQL 和 row-count guard 已通过；N5 run-once execute 已 passed。
12. N5 outbox 当前 pending：ActionEvent = 479，HintEvent = 9，RiskEvent = 0，PositionEvent = 0。
13. N3-C2 closed-minute / closed-30m replay execute 已 passed：minute_delta_rows = 107333，closed_30m_summary = 17504，summary_status = closed 17432 / missing 72，outbox/inbox/checkpoint refs = 0，rollback_safe=true。
14. N3-C3 MinuteBarClosed outbox execute 已 passed：MinuteBarClosed pending=17432，stock/index/board=16344/72/1016，delivered/delivering=0，inbox/checkpoint refs=0，rollback_safe=true。
15. N3-C2B closed_signal_enrichment execute 已 passed：enrichment rows = 17504，computable_rows=17432，unknown/missing=72，quality_rows=6，c2b outbox/inbox/checkpoint refs=0，C3 outbox pending=17432，rollback_safe=true。
16. N4-C3 replay audit execute 已 passed：audit rows = 35970，classification = would_match 4734 / would_clear 245 / would_change 243 / unchanged 30730 / missing 18 / not_ready 0，C3 outbox remains pending=17432，rollback_safe=true。
17. N3-EOD snapshot refresh dry-run 已 PASS；execute preflight BLOCKED，blocker = missing_official_daily_fact，expected EOD rows = stock 2052 / index 9 / board 127 / total 2188，official_daily_missing = 2188，C3 outbox pending = 17432，delivered/delivering = 0，P0/P1/P2 = 0/3/0，EOD scoped business/run/quality/outbox/inbox/checkpoint rows = 0。
18. 20260528 canonical v2 N4 trigger execute 已 passed：execute_run_id = trigger_execute_20260528_condition_layer_20260527_source_20260527_v2，N4 outbox pending = TriggerMatched 4285 / TriggerPendingMarketData 4602 / TriggerStateChanged 8887，rollback_safe=true。
19. 20260528 canonical N5 action execute 已 passed：action_run_id = action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2，N5 outbox pending = ActionBlocked 4285，N5 inbox/checkpoint = 17774/2146，legacy output events = 0，N6 refs = 0，position refs = 0，rollback_safe=true。
20. 20260528 N1 ingestion 已 passed：official daily fact rows = 6017，condition source rows = 80811，active daily/source versions 已写入，check_condition_source_ready --source-trade-date 20260528 passed=true，outbox/inbox/checkpoint delta=0/0/0。
21. 20260528 -> 20260529 N2 condition layer execute 已 passed：run_id = condition_layer_20260528_source_20260528_v1，status=passed_active，passed_active_count=1，P0/P1/P2=0/6/3，quality_rows=106，condition_basis=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，monitor_target=5506/83/428，condition_display_basis=5506/83/428，canonical_signal_audit_passed=true，deprecated_signal_rows=0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true。
22. 20260529 N3 subscription execute 已 passed：market_data_run_id = market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，source_condition_run_id = condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，P0/P1/P2=0/0/0，candidate/subscription/pull_plan/quality rows = 5038/2643/7/34，objects stock/index/board/total = 2021/9/127/2157，required_data_kind realtime_daily_snapshot/minute_bar_1m/previous_day_minute_bar_1m = 2157/243/243，deprecated_signal_rows=0，market_data_pulled=false，market_data_fact_written=false，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，rollback_safe=true。
23. 20260529 A1 previous_day_minute preload 已 passed：preload_run_id = previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，source subscription run = market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，actual rows stock/index/board/total = 56160/0/2160/58320，object status stock passed/partial/missing = 234/0/0，index expected objects/rows = 0/0，board passed/partial/missing = 9/0/0，fake index pull / fake index rows = 0/0，P0/P1/P2=0/0/0，quality_rows=12，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，old_system_touched=false，rollback_safe=true。
24. 20260529 B1 pre-open realtime snapshot fact-only 已 passed：snapshot_run_id = realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，pre_open_fact_only=true，live_trading_snapshot_ready=false，rows stock/index/board/total = 2021/9/127/2157，missing/failed=0/0，P0/P1/P2=0/1/0，quality_rows=11，writes_outbox=false，generated_outbox_events=[]，source_time_missing_or_preopen total/stock/index=2030/2021/9，source_time_confirmed board=127，P1 warning=n3_b1_pre_open_source_time_not_confirmed，P0 source date mismatch=0，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，downstream_layers_touched=false，worker_started=false，N4/N5/N6 touched=false，rollback_safe=true。
25. 20260529 B1 live1 realtime snapshot fact-only 已 passed：snapshot_run_id = realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，live_trading_snapshot_ready=true，pre_open_fact_only=false，rows stock/index/board/total = 2021/9/127/2157，missing/failed=0/0，P0/P1/P2=0/0/0，quality_rows=11，writes_outbox=false，generated_outbox_events=[]，stock effective_quote_present/source_time_missing/partial_quality=2021/2021/0，index effective_quote_present/source_time_missing/partial_quality=9/9/0，board source_time_confirmed/effective_quote_present=127/127，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint=105122/20726/4345，downstream_layers_touched=false，worker_started=false，N4/N5/N6 untouched=true，rollback_safe=true。
26. 20260529 B1 live2 standard outbox snapshot 已 passed：snapshot_run_id = realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，rows stock/index/board/total = 2021/9/127/2157，P0/P1/P2=0/0/0，writes_outbox=true，MarketSnapshotUpdated outbox=2157 pending，MarketDataDelayed/MarketDataMissing/MarketDisplaySnapshotUpdated=0/0/0，delivered/delivering=0/0，scoped inbox/checkpoint refs=0/0，wrote only snapshot facts/common_market_data_run/common_market_data_quality_item/common_event_outbox，no inbox/checkpoint writes，downstream_layers_touched=false，worker_started=false，N4/N5/N6 not entered=true，scoped exception used for existing N6 web app / old system process but they did not consume v3 outbox，rollback_safe=true。
27. 20260529 N4 live2 canonical trigger execute 已 passed：execute_run_id = trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，common_trigger_quality_item=17，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722，TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0，runtime signal_type B_BUY/S_SELL=4467/4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing=0，matched trigger_live=true=4309，pending_market_data trigger_live=false=4552，common_trigger_match TriggerStateChanged=0，N3 live2 input MarketSnapshotUpdated pending=2157，N3 input inbox/checkpoint refs=0/0，N5 refs=0，downstream inbox/checkpoint refs=0/0，global outbox delta=+17722，global inbox/checkpoint delta=0/0，worker_started=false，action/user/voice/mobile/sim/position/real_trade touched=false，rollback_safe=true。
28. 20260529 N5 live2 canonical action execute 已 passed：action_run_id=action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，source N4 run=trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，common_action_quality_item=4552，stock/index/board_action_fact=4037/18/254，common_action_event=4309，common_event_outbox/inbox/checkpoint=4309/17722/2157，ActionBlocked=4309 pending，ActionEligible/ActionExecuted/ActionSkipped=0/0/0，legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0，delivered/delivering=0/0，N4 outbox status unchanged，N6 refs=0，position rows=0，worker_started=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true。
29. 20260529 N4 canonical trigger execute 已 passed：execute_run_id = trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，common_trigger_run=1，common_trigger_quality_item=16，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722，TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0，common_trigger_match TriggerStateChanged=0，pending_market_data trigger_live=false=4552，matched trigger_live=true=4309，runtime signal B_BUY/S_SELL=4467/4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing count=0，scoped inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，outbox_consumed=false，N5/N6 touched=false，worker_started=false，user/voice/mobile/sim/position/real_trade=false，N2/N3 facts unchanged=true，rollback_safe=true。
30. 20260529 N5 canonical action execute 已 passed：action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，source N4 run=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，P0/P1/P2=0/0/0，common_action_quality_item=4552，stock/index/board_action_fact=4037/18/254，common_action_event=4309，N5 outbox pending=4309 ActionBlocked，legacy output events=0，N4 outbox status unchanged，N6 refs=0，position rows=0，rollback_safe=true。
31. 20260529 N6 canonical shadow projection 已 passed：projection_run_id=user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，source_action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，P0/P1/P2=0/5/2，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/4309/4309/4309，notification_source=n5_action_blocked，queue_status=queued_only，N5 outbox unchanged ActionBlocked pending=4309，n5_outbox_consumed=false，user_signal_decision/watchlist/sim/position/real_trade=0，push/voice/mobile=false，worker_started=false，N1-N5 unchanged=true，rollback_safe=true。
32. N2 display scope alignment v3 已 preserved/superseded：run_id=condition_layer_20260528_source_20260528_v3，曾为 passed_active，condition_display_basis stock/index/board=2021/9/127，common_condition_quality_item=103，P0/P1/P2 failed=0/0/0，rollback_safe=true。
33. N2 symmetry target price alignment v5 已 passed_active：active N2 run=condition_layer_20260528_source_20260528_v5，previous active v4=condition_layer_20260528_source_20260528_v4，v4.status=superseded，passed_active_count=1，000027 buy_target_price/reference_target_price=8.42/8.42，condition_pool=4271/169/875，minute_target_scope=4251/169/875，condition_display_basis=2011/83/428，common_condition_quality_item=103，P0/P1/P2=0/3/3，outbox/inbox refs=0/0，N3/N4/N5 refs=0/0/0，rollback_safe=true。
34. 20260529 -> 20260601 N2 condition layer v1 已 preserved/superseded：run_id=condition_layer_20260529_source_20260529_v1，曾为 passed_active，source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529，condition_basis=5506/83/428，condition_pool=4342/187/942，minute_target_scope=4323/187/942，condition_display_basis=1973/83/428，monitor_target=5506/83/428，common_condition_quality_item=109，P0/P1/P2=0/9/3，rollback_safe=true。
35. 20260529 -> 20260601 N2 financial canonical v2 active supersede 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v2，v1.status=superseded，后续已被 v3 active supersede，condition_basis=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106，P0/P1/P2=0/6/3，financial pass-through mismatch basis/pool/scope/display=0/0/0/0，canonical_financial_pass_through_mismatch=0，outbox/inbox/checkpoint delta=0/0/0，N3/N4/N5 refs=0/0/0，rollback_safe=true。
36. 20260529 -> 20260601 N2 symmetry target price target-machine v3 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v3，v2.status=superseded，后续已被 v4 active supersede，000543 buy_target_price/reference_target_price=10.82/10.82，000027 buy_target_price/reference_target_price=8.45/8.45，condition_basis=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106，P0/P1/P2=0/6/3，outbox/inbox/checkpoint delta=0/0/0，v3 downstream refs=0，rollback_safe=true。
37. 20260529 -> 20260601 N2 anchor-segment alignment v4 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v4，后续已被 v5 active supersede，P0/P1/P2=0/6/3，row counts aligned，golden 000600/000543/000027=12.93/10.82/8.45，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true。
38. 20260529 -> 20260601 N2 secondary-anchor v5 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v5，后续已被 v6 active supersede，P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true。
39. 20260529 -> 20260601 N2 level score v6 已 passed_active：active N2 run=condition_layer_20260529_source_20260529_v6，previous active v5=superseded，P0/P1/P2=0/6/3，level_score_ok=true，row_match=true，golden 000543/000600/300327 level_score_up/down=3124/0、3124/0、2999/125，N3/N4/N5 refs=0/0/0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true。
40. 032 N3 action-confirmation projection metric schema migration 已 passed：migration=sql/032_n3_action_confirmation_metric_schema.sql，target_db=ashare_v3，target_user=ashare_v3_user，target_host=127.0.0.1/32，target_port=5432，old_system_db=false，created tables=stock/index/board_action_confirmation_projection_metric，index_count=18，metric_ready trace CHECK constraints=3，business rows written=false，market_data_pulled=false，outbox/inbox/checkpoint delta=0/0/0，downstream N4/N5/N6 checked tables=32，downstream row_count_delta_zero=true，worker_started=false，rollback_safe=true。
41. N3 action-confirmation projection writer execute 已 passed：projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_condition_run_id=condition_layer_20260601_source_20260601_v1，source_subscription_run_id=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_snapshot_run_id=realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_today_minute_run_id=today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_previous_day_minute_run_id=previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，common_market_data_run.status=passed，rows stock/index/board/total=765/54/150/969，metric_ready/not_ready=969/0，common_market_data_quality_item=6，P0/P1/P2=0/0/0，market_data_pulled=false，market_data_fact_written=true，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint=0/0/0，global outbox/inbox/checkpoint delta=0/0/0，no outbox write/consume，no inbox/checkpoint write，rollback_safe=true，rollback_sql=sql/N3_action_confirmation_projection_metric_business_rollback.sql，execute_report=docs/N3_action_confirmation_projection_writer_execute_report.json。
42. N4 action-confirmation metric business execute 已 passed：execute_run_id=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，trigger_context_run_id=trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1，source_projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_condition_run_id=condition_layer_20260601_source_20260601_v1，common_trigger_run.status=passed，common_trigger_run=1，common_trigger_quality_item=10，common_trigger_state=5941，common_trigger_match=5941，common_event_outbox=5941，TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，delivered/delivering=0/0，P0/P1/P2=0/1/0，quality item distribution=P0 passed 9 / P1 warning 1，P1=n4_action_confirmation_metric_pending_candidates_visible non-blocking，N3 metric facts unchanged stock/index/board=765/54/150，common_event_inbox refs=0，checkpoint refs=0，N5 refs=0，N3 outbox consumed=false，inbox/checkpoint written=false，N5/N6 entered=false，worker_started=false，market_data_pulled=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true，rollback_sql=sql/N4_action_confirmation_metric_business_execute_rollback.sql，execute_report=docs/N4_action_confirmation_metric_business_execute_report.json。
43. N5 action-confirmation metric execute 已 passed：action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，source N4 run=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/5935/1/4/0/5/5/5941/2487，event distribution ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped=4/1/0/0，N5 outbox pending ActionExecuted=4、ActionBlocked=1，delivered/delivering=0/0，N4 outbox unchanged TriggerMatched=6 pending、TriggerPendingMarketData=5935 pending、TriggerStateChanged=0，N6/user/downstream refs=0，position refs=0，voice/mobile/sim/real_trade refs=0，worker_started=false，rollback_safe=true，rollback_sql=sql/N5_20260602_action_confirmation_metric_execute_rollback.sql，execute_report=docs/N5_20260602_action_confirmation_metric_execute_report.json。
44. N6 20260602 action-confirmation metric shadow projection execute 已 passed：projection_run_id=user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，source_action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，preflight_result=PREFLIGHT_PASS，run status=passed，P0/P1/P2=0/5/2，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/5/5/5，queue distribution n5_action_executed/n5_action_blocked queued_only=4/1，card distribution ActionExecuted -> action_confirmed/executed/30m_shrink=4、ActionBlocked -> blocked/blocked=1，N5 outbox unchanged ActionExecuted=4 pending、ActionBlocked=1 pending，N5 outbox consumed=false，N5 outbox status updated=false，user_signal_decision=0，linked user_sim_order/trade/position=0/0/0，user_watchlist/watchlist_item=0/0，worker_started=false，push/voice/mobile=false，sim/position/real_trade=false，rollback_safe=true，rollback_sql=sql/N6_projection_business_rollback.sql。
45. A1 previous-day minute preload 20260603 已 passed：preload_run_id=previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，source subscription run=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_market_data_run.status=passed，actual rows stock/index/board/total=57840/480/8160/66480，object status stock/index/board/total=241/2/34/277 all passed，missing/partial/failed=0/0/0，P0/P1/P2=0/1/0，P1=n3_a1_contract_p1_carried rooted in historical common_trade_calendar(20260603) missing warning，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=164214/68560/5163，realtime snapshot rows for this run=0/0/0，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=sql/N3_A1_previous_day_minute_20260603_rollback.sql。
46. common_trade_calendar(20260603) repair 已 passed：source_batch_id/source_version=trade_calendar_20260603_patch_v1，common_trade_calendar(20260603)=1，is_open=true，prev_trade_date=20260602，next_trade_date=20260604，active source_version common/trade_calendar/SSE:20260603 -> trade_calendar_20260603_patch_v1，common_ingest_batch/common_quality_gate_result/common_active_source_version=1/11/1，persisted quality P0 passed=11，outbox/inbox/checkpoint delta=0/0/0，B1 realtime snapshot refs=0，N4 refs=0，N5 refs=0，N2/N3/A1 refs remain=1/2/1，worker_started=false，realtime_market_data_pulled=false，delivery/notification/push/voice/mobile/sim/position/real_trade=false，rollback_safe_scope=true，hard_fail_before_delete=true，rollback_sql=sql/N1_trade_calendar_20260603_patch_rollback.sql，standalone calendar rollback currently expected to hard-fail because N2/N3/A1 refs exist。
47. B1 realtime snapshot 20260603 fact-only retry 已 passed：snapshot_run_id=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，actual/expected rows stock/index/board/total=1963/83/428/2474，P0/P1/P2=0/1/0，BJ fallback index:BJ:899050/index:BJ:899601 已写入且 passed，writes_outbox=false，generated_outbox_events=[]，outbox/inbox/checkpoint refs=0/0/0，N4/N5/N6 refs=0，rollback_safe=true。
48. N4 trigger_context_snapshot 20260603 rebuild 已 passed：trigger_context_run_id=trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1，source_condition_run_id=condition_layer_20260602_source_20260602_v1，source_market_data_run_id=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，market_subscription_run_id=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/0/0，rows stock/index/board/total=4164/168/890/5222，object coverage stock/index/board=1963/83/428，BUY_HINT/SELL_HINT trace rows=216/61，period_trigger_baseline_json_missing=0，required_period_not_ready_rows=0，common_trigger_run/common_trigger_quality_item=1/62，common_trigger_state/common_trigger_match/common_event_outbox=0/0/0，common_event_inbox refs=0，checkpoint refs=0，N5 refs=0，N6 refs=0，N3 B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0，market_data_pulled=false，n3_event_consumed=false，worker_started=false，N5/N6 not entered=true，old_system/real_trade=false，rollback_safe=true，rollback_sql=sql/N4_20260603_trigger_context_rebuild_rollback.sql。
49. N4 canonical trigger execute 20260603 matcher fix 后已 passed：execute_run_id=trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，quality_rows=17，common_trigger_state/common_trigger_match/common_event_outbox=10167/10167/20334，TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=1252/8915/10167，outbox pending/delivered/delivering=20334/0/0，runtime signal B_BUY/S_SELL=5164/5003，deprecated_runtime_signal_count=0，trigger_mark_candidate normal/30m_volume/30m_shrink=5222/2474/2471，pending_market_data trigger_live=false=8915，matched trigger_live=true=1252，TriggerStateChanged in common_trigger_match=0，final action_mark columns in trigger state/match=0，anomaly proof：B_BUY current_price/close <= open=0、S_SELL current_price/close >= open=0、B_BUY amount below localized baseline=0、S_SELL amount above localized baseline=0，inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，N6 refs projection/card/queue=0/0/0/0，source B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0，worker_started=false，delivery/notification/push/voice/mobile/sim/position/real_trade=false，rollback_safe=true before downstream consumption，rollback_sql=sql/N4_20260603_canonical_trigger_execute_rollback.sql。
50. N5 canonical action execute 20260603 retry after status persistence fix 已 passed：action_run_id=action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，source N4 run=trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/8915/1056/26/170/1252/1252/20334/2474，event distribution ActionBlocked/ActionEligible/ActionExecuted/ActionSkipped=1252/0/0/0，N5 outbox pending/delivered/delivering=1252/0/0，N4 outbox unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=1252/8915/10167 pending，N6/user refs=0，position rows=0/0，worker_started=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true，rollback_sql=sql/N5_20260603_canonical_action_execute_rollback.sql。
51. N4_TRIGGER_RULE_SPEC_v4 execute 20260603 已 passed：execute_run_id=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，source_condition_run_id=condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/0/0，common_trigger_run/common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=1/4/863/863/863，TriggerMatched pending=863，delivered/delivering=0/0，matched-only persistence 已生效，BJ quality-blocked 与 BUY:FULL/SELL:FULL blocked 均未写 TriggerMatched，invalid N5 entry=0，N5 refs at execute post-review=0，worker_started=false，rollback_safe=true，rollback_sql=sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql。
52. N5_MARKET_ACTION_CONFIRMATION_SPEC_v1 execute 20260603 已 passed 并 preserve-only：action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，source N4 run=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，N3 action_metric_run_id=action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/0/680/34/149/863/863/863/822，event distribution ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped=863/0/0/0，blocked_reason price_confirmation_failed/amount_confirmation_failed/metric_missing=838/25/0，N5 outbox pending/delivered/delivering=863/0/0，N4 outbox unchanged TriggerMatched pending=863，fresh DB proof 显示 N6/user refs 已存在 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，position rows=0/0，worker_started=false，voice/mobile/sim/position/real_trade=false，action_mark final-only proof passed；rollback SQL 仍 hard-fail before DELETE，但 N5 rollback 当前必须先处理 N6 refs，rollback_sql=sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql。
53. N6 20260603 v1 market-action-confirmation shadow projection post-review recovery 已 passed：source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，fresh DB proof 显示 user_projection_run.status=passed，P0/P1/P2=0/5/2，input/output=863/863，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，card_status=blocked 863，notification_source=n5_action_blocked / queued_only=863，position refs=0/0，shadow_projection=true，n5_outbox_consumed=false，n5_outbox_status_updated=false；post-review artifacts=docs/N6_20260603_V1_MARKET_ACTION_CONFIRMATION_PROJECTION_POST_REVIEW.md and docs/N6_20260603_v1_market_action_confirmation_projection_post_review.json。
54. 035 N6 delivery notification queue schema alignment migration 已 passed；N6 delivery noop preview materialization 曾 append-only 写入 863 rows，后续 rollback passed，target preview rows=0，source queued_only rows=863，N5 outbox ActionBlocked pending=863，真实 delivery/push/voice/mobile/sim/position/real_trade=false。
55. 20260603 N1->N6 final read-only lineage dashboard review 已 LINEAGE_DASHBOARD_PASS：N4 outbox TriggerMatched pending=863，N5 outbox ActionBlocked pending=863，N6 shadow projection/card/source_queue/preview=863/863/863/0，N5 outbox consumed/updated=false，decision/position/sim/voice/mobile/real_trade refs=0，当前终点=N6 shadow projection / queued_only preserved。
56. 20260603 final read-only dashboard artifact 已生成：Markdown=`docs/dashboard/20260603_FINAL_READ_ONLY_LINEAGE_DASHBOARD.md`，JSON=`docs/dashboard/20260603_final_read_only_lineage_dashboard.json`；artifact 明确当前终点为 N6 shadow projection / queued_only preserved，N4/N5 outbox pending，N6 delivery preview rows=0，且不得展示为买卖建议、可执行动作或真实通知。
57. 20260603/20260604 daily pipeline catch-up 已 CATCHUP_PASS through N3-A1：artifact=`docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_ORCHESTRATOR_REPORT.md` / `.json`；target lineages=`20260603 -> 20260604` 与 `20260604 -> 20260605`；20260604/20260605 calendar patch 均 POST_REVIEW_PASS；N1 official daily + condition source rows for each source date=stock/index/board daily 5511/9/428，stock_daily_basic/financial=5511/5511，index/board membership=12841/56960，N1 quality P0/P1/P2=0/0/0；N2 runs `condition_layer_20260603_source_20260603_v1` and `condition_layer_20260604_source_20260604_v1` passed_active with P0/P1/P2=0/6/3；N3 subscriptions `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` and `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed with P0/P1/P2=0/0/0；A1 preloads wrote minute/status totals 77280/322 and 82080/342，P0/P1/P2=0/0/0；scoped outbox/inbox refs=0/0，N4/N5/N6 refs=0/0/0，worker/delivery/push/voice/mobile/sim/position/real_trade=false。
58. 20260605 N3 staged refresh B1 live2 + C1 current/later-minute 已 POST_REVIEW_PASS：B1 snapshot_run_id=`realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，rows stock/index/board/total=1952/9/428/2389，quality rows=11，P0/P1/P2=0/0/0，writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=`sql/N3_B1_realtime_snapshot_20260605_live2_rollback.sql`；C1 current-minute run=`today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，latest_closed_minute=2026-06-05T10:37:00+08:00，rows stock/index/board/total=19028/134/3752/22914，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups stock/index/board=0/0/0，rollback_safe=true，rollback_sql=`sql/N3_C1_today_minute_bar_1m_20260605_until_1037_rollback.sql`；C1 later-minute run=`today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，latest_closed_minute=2026-06-05T11:27:00+08:00，rows stock/index/board/total=33228/234/6552/40014，objects processed/passed=342/342，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups stock/index/board=0/0/0，outbox/inbox/checkpoint refs=0/0/0，B2 projection refs=0，N4 trigger_state/match refs=0/0，N5/N6 refs=0/0，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=`sql/N3_C1_today_minute_bar_1m_20260605_until_1127_rollback.sql`；no delivery/push/voice/mobile/sim/position/real_trade。
59. 20260605 B2 stock/index lineage expansion subscription control-row execute 已 POST_REVIEW_PASS：run_id=`market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，candidate/subscription/pull_plan=6696/3350/4，quality rows=15，P0/P1/P2=0/2/0，P1 residuals=stock/index completion-only not_ready 136/2 与 board 14:59 quality-visible not_ready 428；market_data_pulled=false，market_data_fact_written=false，downstream_layers_touched=false，worker_started=false，subscription/pull_plan duplicate groups=0/0，outbox/inbox/checkpoint refs=0/0/0，minute/preload_status refs=0/0，B2 projection refs=0，N4 trigger_state/match refs=0/0，N5/N6 refs=0/0，rollback_safe=true，rollback_sql=`sql/N3_B2_stock_index_lineage_expansion_20260605_rollback.sql`。
60. 20260605 A1/C1 expansion staged execute 已 POST_REVIEW_PASS：A1 run=`previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，minute rows stock/index/board/total=400320/1680/0/402000，preload status rows stock/index/board/total=1668/7/0/1675，quality rows=12，P0/P1/P2=0/1/0，P1 为 carried non-blocking warning，duplicate minute key groups=0/0/0，rollback_safe=true，rollback_sql=`sql/N3_A1_previous_day_minute_20260605_b2_stock_index_lineage_expansion_rollback.sql`；C1 run=`today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，latest_closed_minute=2026-06-05T11:27:00+08:00，minute rows stock/index/board/total=195156/819/0/195975，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups=0/0/0，rollback_safe=true，rollback_sql=`sql/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_rollback.sql`；A1/C1 scoped outbox/inbox/checkpoint refs=0/0/0，B2 projection/enrichment refs=0，N4 trigger_state/match refs=0/0，N5/N6 refs=0/0，downstream_layers_touched=false，worker_started=false，no delivery/push/voice/mobile/sim/position/real_trade。
61. 20260605 B2 realtime projection execute 已 POST_REVIEW_PASS：projection_run_id=`realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，common_market_data_run.status=passed，projection rows stock/index/board/total=1952/9/428/2389，ready/not_ready=969/1420，ready_by_asset=stock 969，not_ready_by_asset=stock/index/board 983/9/428，quality rows=7，P0/P1/P2=0/4/0，P1 为 stock/index completion_ratio_below_min_ready、board 14:59 not_ready、BJ 920xxx visible 与 input P1 carried 的 quality-visible warning；fact-only trace compatibility=true rows=2389，snapshot_event_id empty rows=2389，required fact trace complete rows=2389，synthetic event id/outbox backfill rows=0/0；writes_outbox=false，outbox/inbox/checkpoint refs=0/0/0，N4 trigger_state/match refs=0/0，N5/N6 refs=0/0，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=`sql/N3_B2_realtime_projection_20260605_live2_compat_rollback.sql`。
62. 20260605 N4 matched-only execute 已 POST_REVIEW_PASS：execute_run_id=`trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`，common_trigger_run.status=passed，run row P0/P1/P2=0/0/0，common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=4/1537/1537/1537，TriggerMatched=1537，TriggerPendingMarketData/TriggerStateChanged=0/0，signal_type B_BUY/S_SELL=1286/251，trigger_mark_candidate normal/30m_volume/30m_shrink=1262/87/188，outbox pending/delivered/delivering=1537/0/0，common_event_inbox/checkpoint refs=0/0，N5 action_run/action_event refs=0/0，N6 user refs=0，worker/action/user/voice/sim/real_trade touched=false，rollback_safe=true，rollback_sql=`sql/N4_20260605_execute_rollback.sql`。
63. N6 Phase 3 admin virtual account seed 已 POST_REVIEW_PASS：seed_run_id=`n6_phase3_virtual_account_seed_20260605_v1`，n6_virtual_account/n6_virtual_cash_ledger/n6_virtual_cash_snapshot=1/1/1，n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0；virtual_account_id=1，principal_id=1，principal_type=admin，login_name=admin，account_name=`Admin Virtual Account`，status=active，base_currency=CNY，initial_cash=1000000.0000，quality_status=passed；cash ledger type=initial_deposit，amount=1000000.0000，snapshot available/frozen/total=1000000.0000/0.0000/1000000.0000，source_ledger_max_id=1，current_cash_snapshot_id=1，pointer_matches=true；scoped outbox/inbox/checkpoint/delivery_attempt refs=0/0/0/0，user_projection/signal/card/queue refs=0/0/0/0，user_sim_account 既有 3 行但无本次 seed linkage，user_sim_order/trade/position=0/0/0，worker/delivery/push/voice/mobile/sim/position/real_trade=false，rollback_safe=true，rollback_sql=`sql/N6_phase3_virtual_account_seed_rollback.sql`。
64. 后续只允许 runtime_control read-only dashboard / lineage review、N5 action readiness / dry-run gate、N4/N5 planning gate、N6 Phase 3 virtual account operation policy / virtual order proposal design gate、N3_market_data subscription rebuild gate for 20260529 based on condition_layer_20260528_source_20260528_v5、N3_market_data subscription rebuild gate for 20260601 based on condition_layer_20260529_source_20260529_v6、20260529 N6 live2 / full-day user projection gate，或另开真实 delivery/push/sim/position/real trade readiness gate；runtime_control 不消费 N4/N5 outbox，不启动 worker，N5 execute、N5 outbox consumption、N5 outbox status update、additional N6 execute、N4/N5/N6 replay event execute、EOD execute、daily close、worker、delivery、notification、push、voice、mobile、sim、position 和真实交易仍保持禁止，必须另行确认。
```

## 9. N2 四表输出决策

N2 采用四表输出，拆分交易链路和用户展示链路：

```text
condition_basis          全量审计根
condition_pool           策略筛选后的条件行
minute_target_scope      N3/N4/N5 交易链路 scope
condition_display_basis  N6 展示输入
```

`condition_display_basis` 是 N2 生成的 N6 展示输入，不进入 N3/N4/N5。N6 可以只读它来展示目标价、参考周期、分级、推荐、入池条件等解释字段，避免直接 join `condition_basis / condition_pool / minute_target_scope`。

N3/N4/N5 继续使用既有交易链路：

```text
minute_target_scope -> market_data_subscription -> N3 facts/events -> N4 trigger -> N5 action
```

因此，新增 `condition_display_basis` 不改变 N3/N4/N5 的正式输入合同。本次 N2-Display overwrite 已生成新的 active run；下游如要继续推进，必须按新 run lineage 重建 N3 subscription 和 N4 context。

## 10. N3N6Q for N6 virtual-account quotes

N3N6Q 已登记为 B轨 N6 虚拟账户的独立报价合同，当前状态为 `CONTRACT_REGISTERED_DESIGN_ONLY`，尚未实现 provider、live probe、数据库 schema、调度或止损执行。

```text
N6 position scope + cross-account identity dedup
  -> QuoteIdentity(identity_key, exchange, stock_code)
  -> N3N6Q stateless facade
  -> Mootdx batch quote (max 80 per provider batch)
  -> QuoteBatch v1
  -> N6 freshness/trade-date validation and N6-only persistence
```

该接口不属于 A1/B1/B2/C1/N3P/N3T，不复用其 lineage、schema、facts、events、poller、worker 或 rollback。N3N6Q 不写 DB、不生成 outbox；N6 不把 principal/account/position/stop-loss 传给 N3N6Q。A轨/admin/status、N4、N5 和浏览器均不调用该接口。

合同权威文件：

```text
docs/N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT.md
docs/N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT.json
```

后续必须依次通过：`N3_market_data provider/fake-adapter gate -> read-only live probe gate -> N6_user quote persistence gate -> N6_user valuation/stop-loss gates`。任何一步都不自动授权下一步。
