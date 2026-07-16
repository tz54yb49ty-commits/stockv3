# Runtime Pipeline Control v0

更新日期：2026-05-27
layer_role：`runtime_control`
范围：runtime orchestration / dashboard，只登记和展示 pipeline 状态，不执行 nightly run。

## 1. 定位

`runtime_control` 是 N1-N6 之外的总控控制面，用于登记 runtime pipeline run、stage、manual gate、execute command registry、rollback registry 和 pipeline timeline。

它不是新的业务层，不生产 N1-N6 事实，不消费 outbox，不写 trigger/action/user/sim/voice/mobile，也不修改任何 N1-N6 execute contract。

## 2. v0 Pipeline

当前 nightly runtime v0 的阶段顺序：

```text
calendar
-> N1 official daily
-> N1 condition source
-> N2 condition layer
-> N3 subscription
-> A1 previous_day preload
-> B1 realtime snapshot fact-only
```

对应 stage_id：

```text
calendar
n1_official_daily
n1_condition_source
n2_condition_layer
n3_subscription
a1_previous_day_preload
b1_realtime_snapshot_fact_only
```

## 3. State Machine

允许状态：

```text
PENDING
WAIT_MANUAL_CONFIRM
RUNNING
PASSED
FAILED
BLOCKED
ROLLBACK_READY
ROLLED_BACK
```

v0 关键规则：

```text
WAIT_MANUAL_CONFIRM 是所有 execute 前的人工确认态。
runtime_control 只能把命令登记到 registry，不得自行执行。
只有用户在对应 layer_role 会话内明确授权，才允许运行该阶段已有 execute command。
rollback registry 只登记 rollback SQL 路径，不执行 rollback。
dashboard 只读展示 pipeline/stage/timeline/registry。
```

## 3.1 Fast Gate Split

为降低 gate 延迟，runtime_control gate 必须拆成三类职责：

```text
FAST GATE
DEFERRED_ANALYSIS
REPAIR_FOLLOW_UP
```

FAST GATE 只能做内联允许/阻断判定，序列化输出必须只有：

```json
{"result":"PASS"}
```

允许值只包括：

```text
PASS
FAIL
BLOCK
```

FAST GATE 禁止输出或计算：

```text
lineage analysis
drift explanation
historical comparison
replay simulation
rollback strategy
supersession strategy
correction planning
```

上述内容必须进入 `DEFERRED_ANALYSIS` 报告；rollback、supersession、correction planning
必须进入 `REPAIR_FOLLOW_UP`，并由后续人工 gate 单独授权。

现有 full readiness report 保留为 deferred analysis：

```text
build_premarket_pipeline_readiness -> DEFERRED_ANALYSIS
build_intraday_pipeline_readiness  -> DEFERRED_ANALYSIS
```

新增 fast gate 入口：

```text
build_premarket_fast_gate
build_intraday_fast_gate
```

CLI 用法：

```bash
PYTHONPATH=src python3 scripts/plan_premarket_pipeline_readiness.py ...
PYTHONPATH=src python3 scripts/plan_intraday_pipeline_readiness.py ...
```

默认输出即 FAST GATE，只允许包含 `result`，不得携带 blockers、stages、lineage、
rollback plan 或 next prompt。

需要解释时必须显式运行 deferred analysis：

```bash
PYTHONPATH=src python3 scripts/plan_premarket_pipeline_readiness.py ... --analysis --json
PYTHONPATH=src python3 scripts/plan_intraday_pipeline_readiness.py ... --deferred-analysis --json
```

`--fast-gate` 作为兼容参数保留，但不再需要；fast gate 是默认模式。

## 4. Schema Draft

SQL 草案：

```text
sql/021_runtime_pipeline_control_schema.sql
sql/021_runtime_pipeline_control_rollback.sql
```

核心表：

```text
runtime_pipeline_run
runtime_pipeline_stage
runtime_execute_command_registry
runtime_rollback_registry
runtime_pipeline_timeline
```

该 schema 目前只是草案。本会话不执行 migration，不连接数据库，不创建真实表。

## 5. Dashboard v0

本地只读 CLI：

## 5.1 N6 archive-status keep-5 控制入口

`/n6/archive-status` 是 hot runtime keep-5 清理状态页，默认只读展示最近一次 cleanup 是否成功、保留/清理日期、blocker 和表级删除汇总。
页面不得提供 cleanup execute 按钮，不得嵌入 cleanup confirm token，也不得在 N6 web 进程内写数据库。

同一个 `com.ashare-v3.runtime-hot-cleanup-keep5-daily` 任务在完成既有 hot-row cleanup 后，直接清理最近 5 个有效交易日以外的 N3/N4/N5 每日本地文件；不做归档、不新增第二个 LaunchAgent。文件范围仅限 `docs/runtime/<YYYYMMDD>` 下的 N3/N4/N5 前缀项、固定 N3/N4 `tmp` 日报文件名，以及固定 N5 monitor/precheck/repair 日期目录。非法日期、未来日期、未知文件、symlink 和 active writer 均跳过。

本地文件结果写入现有：

```text
docs/runtime_archive/hot_keep5_cleanup/keep5_cleanup_status.json
```

字段位于 `local_file_cleanup`，包含执行时间、保留/清理交易日、删除文件/目录数量、释放字节、N3/N4/N5 分层汇总、errors 和 blockers。状态文件使用原子替换；`/n6/archive-status` 只读取该文件，不扫描 runtime roots、不调用 launchctl，也不提供 execute/delete/retry/reload 控件。

```text
GET /api/n6/ui/v1/archive-preview
```

只读生成 keep-5 归档计划：

```text
retention_trade_days=5
retention_policy=latest_trade_dates
archive_root=/Volumes/MacRaid/stock_db_archive/v3_runtime
```

该 preview 只能扫描本地 docs/artifact 目录和 MacRaid 存储状态，不得写 DB、不得写归档文件、不得清理本地热库、不得启动 worker。

```text
POST /api/n6/ui/v1/archive-execute
```

只在用户提交 `confirm_token=ARCHIVE_KEEP_5` 后登记 bounded one-shot archive job artifact。该接口不得在 N6 web 进程内直接执行 SQL cleanup、不得直接删除本地目录、不得 shell 拼接命令。真正归档和本地 hot cleanup 仍必须通过后续 runtime_control / N1 archive execute gate，且必须先验证 manifest、row_count、checksum 和 restore 证据。

keep-5 direct cleanup 硬规则：

```text
最近 5 个交易日必须保留在 hot store。
daily cleanup 默认 direct-delete-no-archive，归档后置，不作为 cleanup 前置。
direct cleanup 只能删除 5 日以外 hot runtime rows。
存在 active archive/cleanup 进程、active N3/N4/N5/N6 runtime writer、retained-date overlap、
downstream/outbox/checkpoint blocker 时，wrapper 必须 BLOCK。
```

daily keep-5 direct cleanup 调度草案：

```text
01:00 com.ashare-v3.runtime-hot-cleanup-keep5-daily
  -> scripts/run_runtime_hot_keep5_cleanup_once.py
     --execute
     --direct-delete-no-archive
     --skip-row-count-plan
     --confirm-token RUNTIME_HOT_KEEP5_DIRECT_DELETE_NO_ARCHIVE_CONFIRMED
  -> 只清理不在最近 5 个交易日内的 hot runtime rows，不执行 archive。
```

上述 LaunchAgent 只能由显式 manual load gate 安装/加载。
patch / plan gate 只能生成 plist 草案，不得执行 `launchctl bootstrap/bootout/kickstart`。

archive-only execute wrapper 合同：

```text
如果目标 trade_date 已存在 result=ARCHIVED_VERIFIED、row_count_match=true、checksum_algorithm=sha256、cleanup_eligible=false，
且 manifest files 覆盖当前 archive query specs 的所有 `(layer, table)`，archive wrapper
必须返回 IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED，不重复全量导出，不重写 archive 文件。
如果旧 verified manifest 缺少当前必需 `(layer, table)`，必须视为 stale-scope manifest，
不得 idempotent skip，必须进入 archive refresh path。
未命中 verified manifest 时，archive wrapper 必须逐表、逐 chunk 读取，逐表写 parquet，逐表校验 row_count，并释放当前 frame/chunk 后再处理下一表。
archive wrapper 不得一次性把所有 runtime query frames 加载到内存。
N3 archive scope 必须包含实时 hot runtime 依赖表族，包括
`stock/index/board_eod_snapshot`、
`stock/index/board_eod_reconciliation_item`、
`stock/index/board_projection_enrichment_v4_metric`、
`index/board_realtime_hint_projection_metric`、
`stock/index/board_closed_30m_summary` 和
`stock/index/board_closed_30m_signal_enrichment`。这些表引用
`common_market_data_run(run_id)` 或依赖引用该 run 的 EOD snapshot，均不得在 archive/cleanup scope 中遗漏。
配置为 large table 的表允许写入分片 parquet 目录，而不是单个超大 parquet 文件。默认 large table 包含
`n3.stock_minute_bar_1m`、`n3.stock_action_confirmation_projection_metric` 和
`n4.common_trigger_state`。分片 manifest entry 必须使用
`format=parquet_partitioned`，`path` 指向分片目录，并记录 `part_files[]`、`chunk_count`、
总 `row_count`、总 `verified_row_count` 以及基于各 part sha256 checksum 组合出的 `sha256:<digest>`。
未生成 verified manifest 的旧 partial parquet 不能被视为已归档；只能在后续同 trade_date retry gate 中写入新的分片目录。
manifest/report 必须记录 table_timings[]，至少包含 layer、table、read/write started_at、read/write duration_ms、row_count、verified_row_count 和 status。
如果某表读取或写入失败，archive wrapper 必须返回 BLOCKED，并在 report 中记录 current_table 和 blocked_reason；该结果不得被视为 verified archive。
archive-only execute 仍不得写 runtime PostgreSQL、不得执行 hot cleanup、不得删除本地 docs/tmp/DB rows、不得消费 outbox/inbox/checkpoint。
```

keep-5 manifest-gated hot cleanup 合同：

```text
retention_trade_days=5
retention_policy=latest_hot_trade_dates
cleanup 前必须逐 cleanup_trade_date 验证 MacRaid manifest：
  result=ARCHIVED_VERIFIED
  row_count_match=true
  checksum_algorithm=sha256
  cleanup_eligible=false
wrapper 必须使用 single-flight lock；任一 keep-5 cleanup plan/execute 运行中，
第二个 wrapper 实例必须返回 BLOCKED_CLEANUP_ALREADY_RUNNING，且不得进入 count/delete。
cleanup scope 必须覆盖引用 `common_market_data_run(run_id)` 的 N3 runtime dependent 表族：
  stock_eod_reconciliation_item
  index_eod_reconciliation_item
  board_eod_reconciliation_item
  stock_projection_enrichment_v4_metric
  index_projection_enrichment_v4_metric
  board_projection_enrichment_v4_metric
  index_realtime_hint_projection_metric
  board_realtime_hint_projection_metric
  stock_eod_snapshot
  index_eod_snapshot
  board_eod_snapshot
  stock_closed_30m_signal_enrichment
  index_closed_30m_signal_enrichment
  board_closed_30m_signal_enrichment
  stock_closed_30m_summary
  index_closed_30m_summary
  board_closed_30m_summary
删除顺序必须保证 eod_reconciliation_item 先于 eod_snapshot，
projection_enrichment_v4_metric 先于 realtime_daily_snapshot，
eod_snapshot、signal_enrichment 先于 summary，summary 先于 common_market_data_run。
execute/recheck 必须按全局 spec/table 顺序跨所有 cleanup_trade_dates 处理，
不得按单个 trade_date 完整删完再进入下一日期；次日 action/projection metric
可能通过 previous-day run FK 引用前一交易日的 common_market_data_run。

任一 cleanup_trade_date 缺少 verified manifest、manifest corrupt、row_count_match=false、
checksum_algorithm 非 sha256、或 cleanup_eligible 非 false，必须 BLOCK，不得 count/delete。
execute 前必须重新验证 retained_trade_dates、verified manifest、row_count drift 和 retained overlap。
长事务执行环境受限时，keep-5 cleanup 可使用 resumable execute：
`--max-delete-units=N` 只提交前 N 个 delete unit。
delete unit 定义为一个普通表 delete，或一个已展开的 batch delete
（例如 event_id chunk、trigger_state_id chunk、run_id batch、intraday time window）。
`common_event_outbox` 大批量删除必须使用 `event_id` chunk；不得对单个
`trade_date + source_layer` 执行 full-day 单条 delete。
`common_trigger_state` 大批量删除必须使用 `trigger_state_id` chunk，当前
chunk size 为 1000，避免单个 trigger run 的大范围 state 删除超过 statement timeout。
partial closeout 必须返回 `DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PARTIAL_PASS`、
`cleanup_complete=false`、`resume_required=true`、`delete_units_total/executed/remaining`。
后续 gate 必须重新 plan/precheck 后继续执行；不得跳过 manifest、retained date 或 row_count drift 校验。
```

## 5.2 Dirty hot keep-2 cleanup 控制入口

`keep2_dirty_hot_cleanup` 是临时调试数据清理链路，和 keep-5 archive-only 链路完全分离。它只用于清理 PostgreSQL hot runtime 中旧的脏调试数据，不要求先归档到 MacRaid。

保留规则：

```text
retention_trade_days=2
retention_policy=latest_hot_trade_dates
retained_trade_dates=hot runtime 中按 trade_date/for_trade_date 排序的最新 2 个交易日
cleanup_trade_dates=retained_trade_dates 以外的旧交易日
```

清理范围仅限 runtime hot 数据：

```text
N3 runtime market-data facts / runs / quality / subscription
N4 trigger context / run / state / match / replay audit / quality
N5 action runtime facts
N6 user runtime projection facts
cleanup_trade_dates 对应的 event outbox / ledger / inbox / delivery / checkpoint 记录
```

禁止清理：

```text
N1/N2 基础历史数据
condition basis / pool / scope
docs/runtime/current_intraday_worker_lineage.json
launchd plist
worker reports
代码、schema、rollback SQL
MacRaid archive 文件或 partial archive 文件
```

执行合同：

```text
Plan gate 只读扫描 hot runtime trade_dates，写 docs/runtime_archive/dirty_hot_cleanup/keep2_cleanup_status.json。
Plan gate 不删除、不写 DB、不消费 outbox/inbox/checkpoint、不操作 worker/launchd。
Execute gate 必须读取 plan artifact，并要求 confirm_token=DIRTY_HOT_KEEP_2_CLEANUP_CONFIRMED。
Execute gate 执行前必须重新发现 hot runtime trade_dates；如果 retained_trade_dates 变化，必须 BLOCK 并要求重新生成 plan。
Execute gate 必须复核表级 row_count；如果 plan 与 execute 前 count 不一致，必须 BLOCK。
Execute gate 可使用单事务或按 trade_date 分事务删除，但必须按 downstream/event refs -> runtime facts 的顺序执行。
N4 stock/index/board_trigger_replay_audit 必须按 for_trade_date/trade_date 纳入 cleanup scope，
并且删除顺序必须早于 common_trigger_run，避免 source_trigger_context_run_id /
source_n4_projection_run_id / replay_run_id 外键阻断。
N6 user_notification_queue / user_signal_card / user_signal_projection 必须按
user_projection_run_id 分批 count/delete；batch 来源只能是 source_action_run_id 属于 cleanup
trade_date 对应 common_action_run 的 user_projection_run。上述 dependent 表必须早于
user_projection_run 删除。
N3 common_market_data_subscription 必须按 common_market_data_run.run_id 分批
count/delete；batch 来源只能是 cleanup trade_date 对应 common_market_data_run.for_trade_date。
该 dependent 表必须早于 common_market_data_run 删除，避免单次 full-date delete 形成长事务。
Execute gate 必须写 closeout artifact，记录每个 trade_date/table 的 planned_row_count 与 deleted_row_count。
direct cleanup wrapper 必须同时写 compact status 字段：
cleanup_success、started_at、finished_at、duration_ms、deleted_table_summary、
current_hot_trade_dates_after、retained_trade_dates_after。
N6 `/n6/archive-status` 只展示 hot keep-5 cleanup 状态和表级汇总，不得直接执行 SQL delete。
```

planner 性能和阻断合同：

```text
trade_date discovery 只能优先使用小型 driver 表：
  common_market_data_run
  common_trigger_run
  common_action_run
  common_event_outbox
不得对 stock_minute_bar_1m、stock_action_confirmation_projection_metric、common_trigger_state 等大事实表执行 distinct trade_date。
cleanup_trade_dates 确定后，大表只能按 where trade_date/for_trade_date = %s 做有界 count。
对单日行数很大的 runtime 表，planner/execute 可以使用显式分批策略；当前允许
`n3.stock_minute_bar_1m` 按 `trade_date + bar_time` 的 1m trading-session windows
分段 count/delete，`n3.board_minute_bar_1m` 按 5m trading-session windows 分段
count/delete，`n3.index_minute_bar_1m` 按 fine trading-session windows 分段 count/delete；
minute_bar batch 不覆盖 09:30 前 pre-open 空窗口。允许
`n3.stock/index/board_action_confirmation_projection_metric` 按
`trade_date + metric_minute_label` 的 5m intraday label windows 分段 count/delete。
`n4.common_trigger_match` 按 `common_trigger_run.run_id` 分段 count/delete；
`n4.common_trigger_state` 先按 cleanup date 对应 `common_trigger_run.run_id`
发现目标行，再在每个 run 内按 `trigger_state_id` 小范围 chunk count/delete，
避免旧 replay run 单批 state 行数过大导致 30s delete timeout。
`n3.stock_realtime_projection_metric` 按 `trade_date + snapshot_time` 的 fine
trading-session windows 分段 count/delete；不得使用 `window_start` 作为 cleanup
batch 字段，因为当前索引不支持该 count 路径。
N6 user projection dependent 表按 user_projection_run_id 分批 count/delete，避免单次
user_projection_run -> common_action_run nested count/delete 在 execute recheck 中超时。
N4 common_trigger_match 按 common_trigger_run.run_id 分批 count/delete，batch 来源只能是
cleanup trade_date 对应 common_trigger_run.for_trade_date；避免单次 full-date
common_trigger_match count/delete 在 planner 或 execute recheck 中超时，并且必须早于
common_trigger_run 删除。
N3 common_market_data_subscription 按 common_market_data_run.run_id 分批 count/delete，
batch 来源只能是 cleanup trade_date 对应 common_market_data_run.for_trade_date；避免单次
full-date common_market_data_subscription delete 在 execute 阶段形成无界长事务，并且必须早于
common_market_data_run 删除。
plan artifact 必须把每个 batch 的 label/start/end/row_count/duration 写入
count_timings[]；execute closeout 必须记录每个 batch 的 deleted_row_count。
plan artifact 必须记录 count_timings[]。
count timeout 使用 30s bounded statement timeout，并允许两次 bounded retry，用于处理 indexed old hot tables 的冷缓存/visibility
瞬时超时；retry 后仍超时或失败必须 BLOCK，不得进入 execute。
delete timeout 使用 30s bounded statement timeout；任一 delete batch 超时或失败必须写出
BLOCKED_DELETE_TIMEOUT / BLOCKED_DELETE_FAILED closeout，并依赖事务回滚，不得挂起长事务。
如果任一表 count 超时或失败，plan 必须返回 DIRTY_HOT_KEEP2_CLEANUP_PLAN_BLOCKED，
并记录 slow_or_blocked_table，不得挂起进程，也不得进入 execute。
event inbox cleanup count/delete 必须先按 cleanup trade_date + source_layer 从
common_event_outbox 取目标 event_id，再对 common_event_inbox 采用 bounded event_id
chunks 分批 count/delete；当前 chunk size 固定为 250 个 event_id；不得使用 correlated exists，也不得使用单次大 join 扫描拖慢
plan。
如 EXPLAIN 显示 event inbox/outbox cleanup count 因缺少索引而 seq scan，
只允许先生成 migration draft，不得在 cleanup plan gate 内直接建索引。当前最小索引草案：
  sql/runtime_dirty_hot_keep2_event_infra_indexes.sql
  sql/runtime_dirty_hot_keep2_event_infra_indexes_rollback.sql
包含：
  common_event_outbox(trade_date, source_layer, event_id)
  common_event_inbox(source_layer, event_id)
执行该 migration 必须另开显式 schema execute gate。
如 EXPLAIN 显示 `stock_minute_bar_1m` cleanup count 因缺少
`trade_date + bar_time` 顺序索引而不能高效使用 5m batch range，
只允许先生成 migration draft，不得在 cleanup plan gate 内直接建索引。当前最小索引草案：
  sql/runtime_dirty_hot_keep2_stock_minute_bar_indexes.sql
  sql/runtime_dirty_hot_keep2_stock_minute_bar_indexes_rollback.sql
包含：
  stock_minute_bar_1m(trade_date, bar_time)
执行该 migration 必须另开显式 schema execute gate。
如 cleanup execute 在删除 `common_market_data_subscription` 时触发 FK child
lookup / ON DELETE SET NULL 检查超时，只允许先生成 migration draft，不得在 cleanup
execute gate 内直接建索引。当前最小索引草案：
  sql/runtime_dirty_hot_keep2_market_subscription_fk_indexes.sql
  sql/runtime_dirty_hot_keep2_market_subscription_fk_indexes_rollback.sql
包含：
  stock_realtime_daily_snapshot(subscription_id)
  index_realtime_daily_snapshot(subscription_id)
  board_realtime_daily_snapshot(subscription_id)
  stock_minute_bar_1m(subscription_id)
  index_minute_bar_1m(subscription_id)
  board_minute_bar_1m(subscription_id)
  stock_previous_day_minute_preload_status(subscription_id)
  index_previous_day_minute_preload_status(subscription_id)
  board_previous_day_minute_preload_status(subscription_id)
  stock_realtime_projection_metric(subscription_id)
  index_realtime_projection_metric(subscription_id)
  board_realtime_projection_metric(subscription_id)
  stock_trigger_context_snapshot(source_market_subscription_id)
  index_trigger_context_snapshot(source_market_subscription_id)
  board_trigger_context_snapshot(source_market_subscription_id)
  common_trigger_match(source_market_subscription_id)
这些索引只用于加速 dirty hot keep2 cleanup 的 market subscription FK delete/check path。
执行该 migration 必须另开显式 schema execute gate。
如 cleanup execute 在删除 `common_market_data_run` 时触发 child FK lookup 检查超时，
只允许先生成 migration draft，不得在 cleanup execute gate 内直接建索引。当前最小索引草案：
  sql/runtime_hot_keep5_market_data_run_fk_indexes.sql
  sql/runtime_hot_keep5_market_data_run_fk_indexes_rollback.sql
包含所有当前缺少 child-side leading index 的 `common_market_data_run(run_id)` FK 列，
包括已观测 blocker：
  stock_action_confirmation_projection_metric(source_subscription_run_id)
以及 stock/index/board action confirmation、closed 30m、projection enrichment、hint projection、
action fact、eod snapshot、common action/position/trigger run 等 runtime 子表对应的 run_id trace 列。
这些索引只用于加速 keep-5 cleanup 删除 old `common_market_data_run` 时的 FK delete/check path。
执行该 migration 必须另开显式 schema execute gate。
如 cleanup execute/preflight 在 `stock/index/board_realtime_daily_snapshot`
按 `trade_date` count/delete 时触发 seq scan 或 statement timeout，只允许先生成
migration draft，不得在 cleanup execute gate 内直接建索引。当前最小索引草案：
  sql/runtime_hot_keep5_realtime_snapshot_trade_date_indexes.sql
  sql/runtime_hot_keep5_realtime_snapshot_trade_date_indexes_rollback.sql
包含：
  stock_realtime_daily_snapshot(trade_date)
  index_realtime_daily_snapshot(trade_date)
  board_realtime_daily_snapshot(trade_date)
这些索引只用于加速 keep-5 cleanup 的 realtime snapshot trade_date count/delete path。
执行该 migration 必须另开显式 schema execute gate。
```

安全硬规则：

```text
最新 2 个 hot trade_dates 永不删除。
如果 retained date 出现在 cleanup_trade_dates，必须 BLOCK。
如果 N3/N4/N5/N6 worker 正在写入待删日期，必须 BLOCK 或要求重新计划。
本链路不执行 archive、不验证 MacRaid manifest、不把 partial archive 当作 cleanup 前置条件。
```

```bash
PYTHONPATH=src python3 scripts/plan_runtime_pipeline_dashboard.py --trade-date 20260527
PYTHONPATH=src python3 scripts/plan_runtime_pipeline_dashboard.py --trade-date 20260527 --json
```

输出包含：

```text
pipeline_run_id
layer_role=runtime_control
stage timeline
WAIT_MANUAL_CONFIRM 状态
execute command registry
rollback SQL path
边界声明
```

Web 只读控制台：

```bash
PYTHONPATH=src python3 scripts/run_runtime_dashboard_web.py
```

默认地址：

```text
http://127.0.0.1:8788/runtime/
http://127.0.0.1:8788/runtime/20260527
http://127.0.0.1:8788/api/runtime/20260527/dashboard
```

Web v0 只展示：

```text
Pipeline Summary
Stage Timeline
Quality Summary
Manual Gate
Command Registry
Rollback Registry
```

Web v0 不提供真实 execute 按钮。命令只作为可复制文本展示，不执行。

## 5.1 Dashboard v0.2 Action-Confirmation Timeline

`/runtime/20260602` 与 `/api/runtime/20260602/dashboard` 额外支持
20260602 action-confirmation run-once 链路只读 timeline：

```text
n2_condition_layer_active
n3_subscription
n3_a1_previous_day_preload
n3_b1_live3_snapshot
n3_c1_today_minute
n3_action_confirmation_projection
n4_action_confirmation_metric_execute
n5_action_confirmation_metric_execute
n6_shadow_projection
```

v0.2 detector 只读取 `docs/*.json` artifact 和 runtime_control closure artifact，
不连接数据库、不消费 outbox、不更新 outbox status、不启动 worker。20260527 nightly
七阶段 dashboard 保持不变。

## 5.2 Dashboard v0.2 Final Review

20260602 action-confirmation timeline 已完成 implementation / local smoke /
post-smoke review：

```text
pipeline = action_confirmation_runtime_v0_2
stage_count = 9
stage_status = all PASS
N5 pending outbox = ActionExecuted 4 / ActionBlocked 1
N6 shadow rows = user_projection_run/user_signal_projection/user_signal_card/user_notification_queue 1/5/5/5
rollback registry = N2/N3/N4/N5/N6 all present
routes = GET/HEAD only
form/button count = 0/0
boundary flags = all false
service stopped after smoke
```

Smoke artifacts are temporary and may be deleted:

```text
/tmp/runtime_dashboard_v0_2_20260602_smoke.png
/tmp/runtime_dashboard_20260602_api.json
/tmp/runtime_dashboard_20260602_page.html
```

## 6. 硬边界

`runtime_control` 本会话禁止：

```text
不执行 nightly run
不执行 registry command
不执行 rollback SQL
不连接 PostgreSQL
不改 N1-N6 execute contract
不消费 outbox
不启动 worker
不写 N6 / voice / mobile / sim / position / real trade
不触碰旧系统
```

## 7. N3/N4 intraday proof poller launchd plan

`runtime_control` 可以生成 N3/N4 intraday proof poller 的本地 launchd plan
artifact，但不得安装、bootstrap、kickstart、bootout、enable 或 disable 任何
LaunchAgent。

Plan artifact 合同：

```text
N3 label: com.ashare-v3.n3.intraday-proof-poller
N4 ordinary label: com.ashare-v3.n4.proof-discovery-poller
N4 HINT label: com.ashare-v3.n4.proof-discovery-poller.hint
N3 ProgramArguments 只能指向 scripts/run_n3_intraday_proof_poller_once.py
N4 ProgramArguments 只能指向 scripts/run_n4_intraday_proof_discovery_poll_once.py
RunAtLoad=false
KeepAlive=false
StartInterval: N3=15s, N4=10s
ProgramArguments 必须带 --execute --user-confirmed
ProgramArguments[0] 与 poller `--python-executable` 必须使用同一个已验证绝对 Python：
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
不得依赖 launchd PATH 中的裸 `python3`。父 poller 和所有 child wrapper argv 都必须继承该
Python executable；报告可以记录 Python 路径，但不得打印 DSN password。
N4 poller 必须显式传递 --dsn；N4 plist EnvironmentVariables 同时保留
ASHARE_V3_POSTGRES_DSN 占位符，由 manual load gate materialize 为真实 DSN。
N3 plist 不得安装 `ASHARE_V3_POSTGRES_DSN=__ASHARE_V3_POSTGRES_DSN__`；如果没有真实
DSN，N3 必须依赖自身只读 resolver 的安全 fallback 或 fail closed，不得把 placeholder 传给 psycopg。
N3/N4 ProgramArguments 必须传递：
  --lineage-config docs/runtime/current_intraday_worker_lineage.json
LaunchAgent plist 不得把某一天的 for_trade_date/source_trade_date 作为 active execution source
JSON/MD report 只能记录 redacted DSN，不得写入 DSN password
禁止 N5/N6、outbox consume、inbox/checkpoint update、rollback、schema/migration、
旧 N3->N4->N5 monolithic chain runner
```

N3 proof-poller 支持独立 branch launchd plan artifact，用于降低 N3P 普通 proof 被 HINT
串行路径拖慢的风险。该模式只改变 plan artifact，不授权安装或 load：

```text
N3P branch label: com.ashare-v3.n3.intraday-proof-poller.n3p
HINT branch label: com.ashare-v3.n3.intraday-proof-poller.hint
N3P ProgramArguments 必须包含 --branch n3p_only
HINT ProgramArguments 必须包含 --branch hint_only
N3P StartInterval=60s
HINT StartInterval=180s
N3P report path: tmp/N3_intraday_proof_poller_n3p_launchd_report.json
HINT report path: tmp/N3_intraday_proof_poller_hint_launchd_report.json
RunAtLoad=false
KeepAlive=false
N4 ordinary label 仍为 com.ashare-v3.n4.proof-discovery-poller
N4 ordinary ProgramArguments 必须包含 --mode ordinary
N4 HINT label 为 com.ashare-v3.n4.proof-discovery-poller.hint
N4 HINT ProgramArguments 必须包含 --mode hint
N4 HINT report path: tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json
N4 ProgramArguments 不得包含 N3 --branch 参数，且必须保持 --selection-mode realtime_latest_only
N4 ordinary/HINT split 只改变 plan artifact；真实安装、unload/reload 或 label 切换必须另开 manual load gate。
```

branch plan 仍必须使用 Python 3.11 绝对路径、`--lineage-config
docs/runtime/current_intraday_worker_lineage.json`、`--execute --user-confirmed`，并继续禁止 N5/N6、
outbox consume、inbox/checkpoint、rollback、schema/migration 和旧 chain runner。

真实安装和 load/start 必须另开 manual load gate，并在该 gate 内重新验证
LaunchAgent label、ProgramArguments、DSN 注入、process/launchctl 状态和边界。

## 7.1 Intraday Worker Lineage Config

N3/N4 intraday proof-poller 的有效交易日和 lineage 必须由 runtime config 提供：

```text
docs/runtime/current_intraday_worker_lineage.json
```

该文件由 post-close Fast Lane 在 durable `EXECUTE_PASS` 后原子更新。`PARTIAL_BLOCKED`、
`BLOCKED`、`FAILED`、status/report 缺失或 malformed 时不得更新。

必填字段：

```text
enabled
for_trade_date
source_trade_date
n2_run_id
subscription_run_id
a1_preload_run_id
n4_context_run_id
updated_by
updated_at
source_status_path
source_oneshot_report_path
```

N3/N4 poller 如收到 `--lineage-config`，必须以 config 为准覆盖 CLI fallback 日期和
lineage ids。config 缺失、disabled、malformed 或日期/lineage 不匹配时必须 fail closed，
不得静默回退到 stale plist 参数。显式 CLI 日期/lineage 只保留给人工 repair/replay 模式，
launchd proof-poller plan 不使用它们作为 active execution source。

`docs/post_close_fastlane/latest` 是 latest attempted Fast Lane date，不是 active lineage。
当 latest attempted date 晚于 `current_intraday_worker_lineage.json.for_trade_date` 时，
N3/N4 proof-poller 必须读取 latest `00_status.json` 并 fail closed，除非 latest result
已经是 durable `EXECUTE_PASS` 且 active lineage 已由独立 materialization gate 对齐。该
fail-closed blocker 必须暴露 `BLOCKED_STALE_INTRADAY_WORKER_LINEAGE`、active date、
latest attempted date、latest result 和 failed step；不得自动 materialize 新 lineage，
不得改写 current lineage 文件，也不得隐式 unload launchd。N4 existing target downstream
refs 仍属于独立 supersession/selection gate，不能由 stale-lineage policy patch 静默修复。

N3 proof-poller execute 模式必须在生成或执行 N3P source-fetch child argv 前校验
effective `for_trade_date` 是否已进入当前本地/session 日期。若本地/session 日期仍早于
`for_trade_date`，必须写入 fresh noop report：

```text
status=noop
reason=noop_for_trade_date_not_current_session
executed_child_command_count=0
planned_child_steps=[]
market_data_pulled=false
database_written=false
writes_outbox=false
consumes_outbox=false
updates_inbox_or_checkpoint=false
touches_n4_n5_n6=false
starts_worker=false
```

该 no-op 不授权启动/停止 launchd，不拉行情，不注册 source payload，不执行 N3/N4/N5/N6 child。
目的是防止 post-close fastlane 提前 materialize 次日 lineage 后，launchd 在上一自然日尝试拉取
次日 source，导致上一日 index/board 1m rows 被 date mismatch 过滤并表现为
`missing_index_board_1m_rows_for_scope`。

N3 proof-poller 在 effective `for_trade_date` 等于当前本地日期时，还必须在 source-fetch child
生成前校验 source 可用窗口。当前策略为 `09:25-15:30`；早于 `09:25` 或晚于 `15:30`
必须写入 fresh noop report：

```text
status=noop
reason=non_trading_session_source_fetch_noop
executed_child_command_count=0
planned_child_steps=[]
market_data_pulled=false
database_written=false
writes_outbox=false
consumes_outbox=false
updates_inbox_or_checkpoint=false
touches_n4_n5_n6=false
starts_worker=false
```

该同日非交易时段 no-op 只阻止 N3P/HINT source-fetch child 过早执行；不得放宽 source payload
日期/对象合同，不得修复或覆盖 N4 downstream refs，也不得启动或停止 launchd/worker。

## 8. Intraday Proof-Poller Timing Report Contract

N3P / HINT branch proof-poller 和 N4 proof-discovery poller 的 launchd report 必须携带
report-only timing 字段，用于拆分 poller parent cadence、child execution 和 closeout 延迟。
该字段只用于观测，不参与 source selection、baseline selection、idempotency、trigger lifecycle、
matcher execute 或任何 side-effect 判定。

N3 proof-poller report:

```text
timing.started_at
timing.finished_at
timing.total_duration_ms
timing.branch_mode
timing.phases[]
  phase_name
  started_at
  finished_at
  duration_ms
  status
  child_step
```

N3 child result 同步记录：

```text
child_started_at
child_finished_at
child_duration_ms
```

N4 proof-discovery report:

```text
timing.started_at
timing.finished_at
timing.total_duration_ms
timing.phases[]
  discovery
  candidate_selection
  ordinary_child_execution
  hint_child_execution
  report_closeout
```

N4 `child_execution.children[]` 同步记录：

```text
child_started_at
child_finished_at
child_duration_ms
```

N4 proof-discovery poller 还必须追加轻量 pass history JSONL，用于诊断单一 latest report
覆盖后无法还原历史 selection/noop/skip 的问题。history 只作为本地证据，不改变 selection、
matcher 业务语义、DB 写入、exit code 或 launchd 配置。

```text
mode=hint:
  tmp/N4_intraday_proof_discovery_poller_hint_history.jsonl
mode=ordinary/both:
  tmp/N4_intraday_proof_discovery_poller_history.jsonl
```

每条 JSONL 至少记录：

```text
started_at
finished_at
duration_ms
mode
result/status/reason
selected_run_id / selected_source_market_data_run_id
selected_child_order_policy / selected_child_order
no_candidate_reason
existing_target_skip
executed_child_command_count
children[].family / source_run_id / target_run_id / returncode / duration_ms
report_path
```

history 文件必须有限保留，默认仅保留最近 500 条，避免 `tmp/` 证据无限增长。

N4 HINT-only proof-discovery poller 在 `mode=hint` 且
`selection_mode=realtime_latest_only` 时必须使用轻量 fast path：

```text
discovery_policy=hint_realtime_latest_fast_path_v1
只发现最新 HINT source common_market_data_run
只检查该 source 对应的 exact N4 HINT target 是否已存在
只读取上一条 HINT target 作为 previous_trigger_run_id baseline
不扫描 ordinary candidates
不扫描全日 existing_targets
不生成全量 skipped_candidates backlog
```

该 fast path 只优化 discovery/selection 范围，不改变 HINT matcher child argv、
trigger 业务语义、DB schema、outbox/inbox/checkpoint 行为或 launchd 配置。

N4 ordinary proof-discovery poller 在 `mode=ordinary` 且
`selection_mode=realtime_latest_only` 时同样必须使用轻量 fast path：

```text
discovery_policy=ordinary_realtime_latest_fast_path_v1
只发现最新 ordinary source common_market_data_run
只检查该 source 对应的 exact N4 ordinary target 是否已存在
只读取上一条 ordinary target 作为 previous_trigger_run_id baseline
不扫描 HINT candidates
不扫描全日 existing_targets
不生成全量 skipped_candidates backlog
```

该 fast path 只优化 ordinary discovery/selection 范围，不改变 ordinary matcher child argv、
trigger 业务语义、DB schema、outbox/inbox/checkpoint 行为或 launchd 配置。

N4 ordinary matcher execute report 必须携带轻量阶段耗时证据，用于区分 source/context 读取、
候选计划、baseline、lifecycle plan、事务写入和 artifact 写入耗时：

```text
phase_timing_ms.fetch_context_ms
phase_timing_ms.fetch_metric_ms
phase_timing_ms.build_matcher_plans_ms
phase_timing_ms.fetch_target_counts_ms
phase_timing_ms.fetch_previous_states_ms
phase_timing_ms.build_execute_plan_ms
phase_timing_ms.execute_transaction_ms
phase_timing_ms.write_artifacts_ms
phase_timing_ms.total_ms
```

该 timing 只作为本地 evidence，不改变 ordinary matcher 业务语义、DB schema、
outbox/inbox/checkpoint 行为或 launchd 配置。

N4 ordinary matcher 在收到 `previous_trigger_run_id` 时，previous-state baseline 必须使用
latest lifecycle state snapshot through previous target 的有界查询：

```text
include ordinary states with until_hhmm <= previous_trigger_run_id.until_hhmm
partition by lifecycle key:
  for_trade_date / asset_kind / identity_key / signal_type / condition_key / canonical_trigger_type
choose latest by until_hhmm desc, run_id desc
```

该查询不得把同一交易日全部 prior ordinary state rows 拉回 Python 后再过滤。若 bounded snapshot
无法解析或为空，才允许 fallback 到 exact `previous_trigger_run_id` rows，并继续保持缺失时
fail closed。

若 child blocked，report 必须保留原始 blocker reason/stderr/result，同时 timing 仍写入并将对应
phase 标记为 `blocked`。timing 不得把 side effects 从 false 改为 true，也不得隐藏 report
write 失败。

## 9. Post-Close Fast Lane Worker Guard Allowlist

18:00 post-close Fast Lane 的 `worker_launchd_guard` 默认仍然 fail-closed：
旧 N3 B1/C1/B2 auto-poll、旧 N4 bounded-polling、N5/N6/action worker、
outbox/inbox/checkpoint consumer 或未知 N3/N4/N5/N6 worker 一律阻断。

唯一允许与 post-close static Fast Lane 共存的 loaded worker 是以下新 proof-poller：

```text
com.ashare-v3.n3.intraday-proof-poller
com.ashare-v3.n3.intraday-proof-poller.n3p
com.ashare-v3.n3.intraday-proof-poller.hint
com.ashare-v3.n4.proof-discovery-poller
com.ashare-v3.n4.proof-discovery-poller.hint
```

guard 必须按实际 loaded label / running branch 读取当前 launchd plan 使用的无日期本地 report path：

```text
tmp/N3_intraday_proof_poller_launchd_report.json
tmp/N3_intraday_proof_poller_n3p_launchd_report.json
tmp/N3_intraday_proof_poller_hint_launchd_report.json
tmp/N4_intraday_proof_discovery_poller_launchd_report.json
tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json
```

不得继续依赖某个历史日期固化的 `*_20260701_launchd_report.json`，否则会在后续交易日误判
`report_stale`。

N3 branch 模式必须 branch-aware：`--branch n3p_only` 只能映射到
`tmp/N3_intraday_proof_poller_n3p_launchd_report.json`，`--branch hint_only` 只能映射到
`tmp/N3_intraday_proof_poller_hint_launchd_report.json`。base N3 report 不得替代 branch report
作为安全证据。

但它们只有在最新本地 report 同时证明以下条件时才可被 allowlist：

```text
status/result = noop 或 ready
executed_child_command_count = 0
database_written = false
market_data_pulled = false（N3 noop）
writes_outbox / consumes_outbox / outbox_consumed = false
inbox/checkpoint updated = false
n5_n6_entered / touches_n4_n5_n6 = false
rollback_executed = false
schema_changed = false
```

report 缺失、过旧、blocked、已执行 child、任何副作用字段不是 false、旧 label loaded、
或下游 worker/consumer 存在时，guard 必须继续阻断。该 allowlist 只改变只读 guard
判定和报告字段，不授权安装、加载、停止 launchd，也不授权执行 N1-N6 runtime。

## 10. Post-Close Fast Lane Latest Pointer Semantics

`docs/post_close_fastlane/latest` 表示 latest attempted Fast Lane date，而不是 latest
successful/effective lineage date。只要 one-shot attempt 已经 durable 写出
`00_status.json` 和 `01_oneshot_execute_report.json`，latest pointer 就可以刷新到该
`for_trade_date`，包括：

```text
EXECUTE_PASS
PARTIAL_BLOCKED
BLOCKED
```

刷新必须在 status/report artifact 写入后执行；若 `00_status.json` 或
`01_oneshot_execute_report.json` 缺失、JSON malformed、或 status 内
`for_trade_date` 与目录名不一致，则不得刷新 latest。

manual lineage overlay 仍是某个日期的 effective lineage evidence，但不得隐藏更晚日期的
latest attempted Fast Lane 状态。状态页需要区分：

```text
latest_attempted_for_trade_date
selected_for_trade_date
effective_manual_overlay
```

该规则只影响本地 artifact pointer 和只读 UI 展示，不授权 DB 写入、runtime execute、
launchd 操作、worker 操作或 outbox/inbox/checkpoint consumption。

## 11. N5 Active Scope to N3T/C1 Artifact-First Contract

本节登记 runtime_control 对 N5 active `trigger_live=true` scope 驱动 N3-C1 scoped
artifact 与 N3T scoped metric 的总控合同。该合同只定义层间交接顺序和硬边界，不授权
runtime_control 执行 N3/N4/N5 runtime，不授权拉行情，不授权写 DB，不授权消费 outbox。

### 10.1 N5 Active Scope Snapshot

N5 active scope snapshot 是 N5-owned 的 action-confirmation scope，不是 N3 表、
N4 表或 runtime_control 业务事实。runtime_control 只能传递显式 snapshot artifact 或
登记 snapshot artifact 路径，不得让 N3 直接扫描 N5 内部 tracking/inbox/checkpoint/outbox 表。

snapshot grain 必须至少包含：

```text
for_trade_date
asset_kind
identity_key
direction
signal_type
condition_key
source_trigger_event_id
source_trigger_run_id
scope_status=active
```

对象进入 scope 只能来自 N5 对 N4 pending `TriggerMatched` 的只读 intake plan。
对象退出 scope 只能来自：

```text
N5 ActionExecuted emitted for the same grain
N5 observed TriggerStateChanged(trigger_live=false) for the same grain
manual expiry policy in an explicit N5 gate
```

退出后，该对象不得继续进入后续 C1 scoped artifact 或 N3T scoped metric plan。

### 10.2 N4_OUTBOX_PROTECTION

早期 gates 中，N5 只能 read-only 读取 N4 pending outbox events：

```text
TriggerMatched
TriggerStateChanged(trigger_live=false)
```

禁止把 N4 outbox status 从 `pending` 更新为 `delivering`、`delivered`、`consumed`
或任何等价消费状态。禁止修改 N4 outbox payload、dedup key、partition key 或 delivery
metadata。N5 只能记录或计划 N5-owned shadow intake / inbox / checkpoint / active scope。

正式消费 N4 outbox 必须另开 explicit N5 execute consumption gate，并在该 gate 中重新验证
N4 outbox before/after counts、status transitions、rollback scope 和 downstream refs。

### 10.3 N3_C1_PROTECTION

N3-C1 scoped mode 在早期 gates 必须先走 plan-only / artifact-first：

```text
input scope = explicit N5 active scope snapshot artifact
output = scoped C1 artifact / scoped staging artifact
canonical stock/index/board_minute_bar_1m writes = forbidden
N3 outbox writes = forbidden
N3 proof-poller report/status mutation = forbidden
```

artifact-first C1 只能覆盖 active scope 中的 stock/index/board 对象和 `for_trade_date`
范围内已闭合的 1m bar。empty scope 必须 no-op。禁止在 empty scope、missing scope、
partial scope 或 validation failure 时 fallback 到 full-market pull / full-market processing。

canonical C1 writes to `stock_minute_bar_1m`、`index_minute_bar_1m` 或
`board_minute_bar_1m` 必须另开 `N3_C1_SCOPED_EXECUTE_GATE`，并在该 gate 中显式验证
去重策略、与现有 C1 path 的冲突策略、N3 outbox policy、rollback scope 和 N3/N4 主链路影响。

### 10.4 N3T Scoped Metric Input

N3T scoped metric 可以消费 scoped C1 artifact 或 explicit scoped metric input。N3T 不得
直接扫描 N5 内部表，不得使用 N3P/B1/B2/realtime_action_confirmation_metric 作为
N5 final action proof，不得写 N3->N4 outbox。

N3T scoped output 只能服务 N5 `ActionExecuted` guard。N3T failure 只阻断
`ActionExecuted`，不得阻断 N5 `ActionEligible`，不得影响 N3 worker status 或 N4 worker
status。

### 10.5 Bounded One-Shot Total-Control Order

总控顺序必须是 bounded one-shot，可重复调用，不得启动长期 worker：

```text
1. N5 plan-only reads N4 pending TriggerMatched / TriggerStateChanged(trigger_live=false)
2. N5 builds or refreshes N5-owned active scope snapshot artifact
3. runtime_control passes explicit active scope snapshot artifact path to N3-C1 scoped plan
4. N3-C1 scoped plan creates only scoped C1 artifact / staging plan for active objects
5. N3T scoped plan reads scoped C1 artifact / explicit scoped input and creates N3T metric plan
6. N5 plan-only evaluates N3T source_basis=N3T_C1_CLOSED metric for ActionExecuted plan
```

任一步 scope 为空、输入缺失、分钟未闭合或合同不匹配，都必须 fail closed 或 no-op；不得
扩大到全市场，不得消费 N4 outbox，不得写 canonical C1，不得进入 N6。

### 10.6 N6 B-Track Signal Projection Poller

N6 B-track signal projection poller 是独立 bounded one-shot poller，只在交易日
`09:25-15:00` 消费 N5 canonical action outbox event：

```text
ActionEligible
ActionExecuted
ActionBlocked
ActionSkipped
```

poller 默认从 `docs/runtime/current_intraday_worker_lineage.json` 读取 `for_trade_date`。
非交易日、非交易时间、无 N5 action event 时必须 safe noop。投影写入范围只允许：

```text
user_projection_run
user_signal_projection
user_signal_card
common_event_inbox
common_event_consumer_checkpoint
```

禁止更新 `common_event_outbox.status`，禁止消费/删除 N5 outbox，禁止语音、mobile、sim
或真实交易。幂等键为 `consumer_name + event_id`，重复运行不得重复生成用户投影。

`/n6/app/signals` 和 `/api/n6/app/v1/signals` 只读 N6 projection，不直接扫 N4/N5 fact。
不传 `trade_date` 时默认当前 lineage/filter batch 的交易日；传入历史 `trade_date` 时进入
historical projection mode，读取该日期已存在的 N6 投影历史，不受当前 monitor 过期状态隐藏。

历史 N5 action outbox 不由实时 poller 自动跨日期回填。若需要把旧
`ActionEligible / ActionExecuted / ActionBlocked / ActionSkipped` 投影到 N6，必须使用
显式 historical backfill mode，并要求独立确认 token：

```text
--historical-backfill
--backfill-trade-date YYYYMMDD
--confirm-token N6_B_TRACK_SIGNAL_HISTORICAL_BACKFILL_CONFIRMED
```

historical backfill 必须写独立 report/history artifact，不得覆盖 launchd 实时 poller
report；仍然禁止更新 N5 outbox status、语音、mobile、sim 或真实交易。

### 10.7 N6 Filter-Center Display-Basis Field Boundary

`/n6/app/filter-center` 的 stock/index/board 默认展示字段只能来自 N6 readonly view：

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
```

这些 view 的权威来源仍是 N2 `stock/index/board_condition_display_basis`，不得让 N6
为了补展示字段直接回查 `stock/index/board_condition_basis`。

`buy_expected_return_pct` 是 N2 condition_basis 已计算的目标价候选收益字段。若需要在
filter-center 展示，必须由 N2 display-basis 顶层透传到
`stock/index/board_condition_display_basis.buy_expected_return_pct`，再由
`v_n6_stock/index/board_condition_display_basis` 暴露给 N6。历史已有 display-basis
行需要显式 backfill，从 `primary_source_condition_basis_id` join 对应 condition_basis
回填，不由 N6 页面运行时拼接。
