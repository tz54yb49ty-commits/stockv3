# A股监控系统 v3 当前任务看板

更新日期：2026-07-22
范围：最小可落地任务看板。本文档不授权数据库写入、行情 execute、worker、语音、sim、前端或真实交易。

## P0 当前优先级

### T0.GOV-N6-DELIVERY. N6 B轨三通道与唯一发布主线

状态：IMPLEMENTATION_READY；未部署、未清理工作树。

目标：用 `n6_btrack_delivery_lanes_v1` 取代普通新需求不断新增一次性 policy
的做法，并将所有后续 B轨发布收敛到
`codex/n6-btrack-integration`。

当前交付：

- L1 `n6_btrack_delivery_l1_web_readonly_v1`
- L2 `n6_btrack_delivery_l2_n6_business_v1`
- L3 `n6_btrack_delivery_l3_virtual_runtime_v1`
- `docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json`
- 无副作用的 `scripts/plan_n6_btrack_delivery.py`

下一 gate：

```text
n6_btrack_service_lineage_convergence_v1
```

该 gate 只允许在新的隔离集成分支中合并当前 Web、quote/executor 和
stop-loss 能力，解决两个 `087` 文件冲突并运行完整 N6 回归。它不得连接活动
数据库、切换 plist、启动 worker 或处理 proposal。血缘收敛完成前不得宣称
已有统一生产基线。

工作树归档是再下一独立 gate。任何删除都必须先证明对应工作树的 commit、
测试、rollback 和 tracked/untracked/ignored 均为零；主工作树始终
preserve-only。

### T0.GOV-N6. N6 B 轨 virtual-executor 权限治理 v1

状态：governance registration ready；runtime not executed。

目标：以前向规则 `N6_B_TRACK_VIRTUAL_EXECUTOR_GOVERNANCE_V1` 将 N6 虚拟账户 runtime 从 blanket reject 调整为严格条件下的独立 gate，同时保持真实交易和跨层写入永久禁止。

执行顺序：

```text
1. runtime_control 只提交治理文档
2. 切换 N6_user 部署版本化 migration 和不可变 release
3. 单条显式 proposal bounded smoke PASS
4. confirmed 队列精确治理完成
5. 冻结并验证立即 bootout 停用方案
6. 另行授权持续 virtual-executor
7. 自然周期验证全链审计和异常停用
```

验收硬条件：

- proposal 只能由真人两阶段显式创建、确认；executor 不得创建或确认。
- claim/apply 双层校验开放交易日、交易时段、两分钟内 `passed/ok` 报价、本人 principal/account/scope、现金、服务端预算、100 股取整和 T+1。
- 独立 service role；proposal/order/trade/cash/position/lot 全审计；可立即 bootout。
- 版本化合同、preflight、精确 rollback、不可变 release、精确影响范围全部通过。
- bounded smoke PASS、confirmed 队列治理完成、停用方案冻结后，才可启用持续 executor。

禁止事项：本治理任务不连接数据库、不执行 migration、不修改 release/plist、不启动 executor、不处理 proposal；真实券商、真实订单、N6 回写 N1-N5、未经授权的申请、自动创建交易申请、AI autonomous real trading 和无 preflight/rollback 的长期 worker 始终禁止。历史 gate 与历史 BLOCKED 证据不得改写。

### T0. Runtime pipeline state machine / dashboard v0/v0.2

状态：v0.2 dashboard smoke/post-smoke passed
目标：建立 runtime_control 控制面，用于登记 nightly runtime pipeline state、manual gate、execute command registry、rollback registry 和 timeline。

输入：

```text
docs/RUNTIME_PIPELINE_CONTROL_V0.md
docs/RUNTIME_NIGHTLY_SOP.md
sql/021_runtime_pipeline_control_schema.sql
scripts/plan_runtime_pipeline_dashboard.py
```

输出：

```text
runtime_pipeline_run
runtime_pipeline_stage
WAIT_MANUAL_CONFIRM
runtime_execute_command_registry
runtime_rollback_registry
runtime_pipeline_timeline
dashboard v0
dashboard v0.2 action-confirmation timeline detector
nightly runtime SOP
```

验收标准：

- `layer_role=runtime_control` 已登记。
- dashboard v0 可生成 stage timeline 和 registry 摘要。
- dashboard v0.2 已支持 `/runtime/20260602` 与 `/api/runtime/20260602/dashboard`：
  9 阶段 all PASS，N5 pending outbox=`ActionExecuted 4 / ActionBlocked 1`，
  N6 shadow rows=`user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/5/5/5`。
- command registry 只登记命令，不执行。
- rollback registry 只登记 SQL path，不执行。
- runtime dashboard routes 只有 GET/HEAD；无 form、无 execute button；boundary flags all false。
- 不修改 N1-N6 execute contract。
- 不执行 nightly run。
- 不启动 worker，不消费 outbox，不写 N6/voice/mobile/sim/real trade。

禁止事项：

- 不连接数据库执行 schema。
- 不运行 registry command。
- 不执行 rollback SQL。
- 不跨层推进 N1-N6 execute。

### T1. 确认权威 active run

状态：done for N2/N3 subscription/N3 preload/N3-B1/N3-C2/N3-EOD dry-run/preflight/N4 current context/N4 projection matcher execute/N5 current-real action execute/N4 20260528 canonical trigger execute/N5 20260528 canonical action execute/N1 20260528 ingestion passed/N2 20260528 condition execute passed/N3 subscription 20260529 execute passed/A1 previous_day_minute 20260529 preload passed/B1 pre-open realtime snapshot fact-only 20260529 passed/B1 live1 realtime snapshot fact-only 20260529 passed/B1 live2 standard outbox snapshot 20260529 passed/N4 live2 canonical trigger execute 20260529 passed/N5 live2 canonical action execute 20260529 passed/N4 20260529 canonical trigger execute passed/N5 20260529 canonical action execute passed/N6 20260529 canonical shadow projection passed/027 N2 symmetry target price schema migration passed/032 N3 action-confirmation projection metric schema migration passed/N3 action-confirmation projection writer execute passed/N4 action-confirmation metric business execute passed/N5 action-confirmation metric execute passed/N6 20260602 action-confirmation shadow projection execute passed/N2 canonical condition v2 active lineage supersede passed/N2 display scope alignment v3 preserved/superseded/N2 symmetry target price alignment v5 passed_active/N2 20260529 condition v1 preserved/superseded/N1 stock_financial 20260529 v2 passed/N2 financial canonical 20260529 v2 passed_active/N2 anchor-segment alignment 20260529 v4 preserved/superseded/N2 secondary-anchor 20260529 v5 preserved/superseded/N2 level score 20260529 v6 passed_active/N1 20260602 source baseline complete/N2 20260602 condition layer passed_active/N3 subscription 20260603 passed/A1 previous-day minute preload 20260603 passed/common_trade_calendar(20260603) repair passed/B1 realtime snapshot 20260603 fact-only passed/N4 trigger_context_snapshot 20260603 rebuild passed/N4 canonical trigger execute 20260603 passed after matcher fix/N5 canonical action execute 20260603 passed after status fix/N4 v4 execute 20260603 passed/N5 v1 market-action-confirmation execute 20260603 passed/20260605 N3 B1 live2 + C1 current/later-minute + B2 stock-index lineage expansion control-row + A1/C1 expansion + B2 realtime projection post-review passed/N4 20260605 matched-only execute post-review passed/N6 Phase 3 admin virtual account seed passed
目标：确认当前唯一权威 lineage，作为后续 N3/N4/N5 的输入锚点。

输入：

```text
docs/N2_DISPLAY_OVERWRITE_EXECUTE_REPORT.md
docs/N3_AFTER_N2_R4_MARKET_DATA_SUBSCRIPTION_REBUILD_REPORT.md
docs/N4_R4_TRIGGER_CONTEXT_REBUILD_REPORT.md
docs/N4_R4_SYNTHETIC_TRIGGER_EXECUTE_REPORT.md
docs/N5_R4_ACTION_CONSUMER_RUN_ONCE_DRY_RUN_REPORT.md
docs/N5_CURRENT_REAL_ACTION_EXECUTE_REPORT.md
docs/N5_current_real_action_execute_report.json
docs/N3_C2_closed_30m_replay_execute_report.json
docs/N3_C3_MINUTEBARCLOSED_EXECUTE_REPORT.md
docs/N3_C3_minute_bar_closed_execute_report.json
docs/N3_C2B_CLOSED_SIGNAL_ENRICHMENT_EXECUTE_REPORT.md
docs/N3_C2B_closed_signal_enrichment_execute_report.json
docs/N4_C3_REPLAY_DRY_RUN_REPORT.md
docs/N4_C3_replay_dry_run_report.json
docs/N4_C3_REPLAY_AUDIT_EXECUTE_PREFLIGHT.md
docs/N4_C3_replay_audit_execute_preflight.json
docs/N3_EOD_SNAPSHOT_REFRESH_DRY_RUN_REPORT.md
docs/N3_EOD_snapshot_refresh_dry_run_report.json
docs/N3_EOD_SNAPSHOT_REFRESH_EXECUTE_PREFLIGHT.md
docs/N3_EOD_snapshot_refresh_execute_preflight.json
docs/N4_20260528_V2_CANONICAL_TRIGGER_EXECUTE_REPORT.md
docs/N4_20260528_V2_canonical_trigger_execute_report.json
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_REPORT.md
docs/N5_20260528_canonical_action_execute_report.json
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_CONTRACT.md
docs/N5_20260528_canonical_action_execute_contract.json
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_PREFLIGHT.md
docs/N5_20260528_canonical_action_execute_preflight.json
sql/N5_20260528_canonical_action_execute_rollback.sql
docs/N1_official_daily_20260528_ingestion_execute_preflight.json
docs/N1_condition_source_20260528_activation_execute_preflight.json
docs/N2_condition_layer_20260528_execute_report.json
docs/N2_condition_layer_20260528_execute_post_review.json
docs/N2_CONDITION_LAYER_20260528_EXECUTE_POST_REVIEW.md
docs/N2_condition_layer_20260528_final_gate_preflight.json
docs/N2_condition_layer_20260528_final_gate_audit.json
docs/N3_subscription_20260529_execute_report.json
docs/N3_subscription_20260529_execute_preflight.json
docs/N3_subscription_20260529_execute_contract.json
docs/N3_subscription_20260529_dry_run_report.json
docs/N3_A1_previous_day_minute_preload_execute_report.json
docs/N3_B1_realtime_daily_snapshot_execute_report.json
docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_REPORT.md
docs/N3_B1_realtime_snapshot_20260529_live2_outbox_execute_contract.json
docs/N3_B1_realtime_snapshot_20260529_live2_outbox_execute_preflight.json
docs/N4_20260529_canonical_trigger_execute_contract.json
docs/N4_20260529_CANONICAL_TRIGGER_EXECUTE_CONTRACT.md
docs/N4_20260529_canonical_trigger_execute_preflight.json
docs/N4_20260529_CANONICAL_TRIGGER_EXECUTE_PREFLIGHT.md
docs/N5_20260529_canonical_action_execute_report.json
docs/N5_20260529_CANONICAL_ACTION_EXECUTE_REPORT.md
docs/N6_CANONICAL_PROJECTION_EXECUTE_CONTRACT.md
docs/N6_CANONICAL_PROJECTION_EXECUTE_PREFLIGHT.md
docs/N3_action_confirmation_projection_metric_032_migration_execute_report.json
docs/N3_ACTION_CONFIRMATION_PROJECTION_METRIC_032_MIGRATION_EXECUTE_REPORT.md
docs/N3_action_confirmation_projection_writer_execute_report.json
docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_REPORT.md
docs/N3_action_confirmation_projection_writer_execute_contract.json
docs/N3_action_confirmation_projection_writer_execute_preflight.json
sql/032_n3_action_confirmation_metric_schema.sql
sql/032_n3_action_confirmation_metric_schema_rollback.sql
sql/N3_action_confirmation_projection_metric_business_rollback.sql
sql/027_condition_symmetry_target_price_compatibility_migration.sql
sql/027_condition_symmetry_target_price_compatibility_rollback.sql
sql/N1_official_daily_20260528_ingestion_rollback.sql
sql/N1_condition_source_20260528_activation_rollback.sql
sql/N2_condition_layer_20260528_rollback.sql
sql/N3_subscription_20260529_rollback.sql
sql/N3_A1_previous_day_minute_20260529_rollback.sql
sql/N3_B1_realtime_snapshot_20260529_rollback.sql
sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql
sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql
sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql
sql/N4_20260529_canonical_trigger_execute_rollback.sql
sql/N5_20260529_live2_canonical_action_execute_rollback.sql
sql/N5_20260529_canonical_action_execute_rollback.sql
sql/N6_projection_business_rollback.sql
docs/N2_condition_layer_20260529_execute_report.json
docs/N2_condition_layer_20260529_execute_post_review.json
docs/N2_CONDITION_LAYER_20260529_EXECUTE_POST_REVIEW.md
sql/N2_condition_layer_20260529_rollback.sql
```

输出：

```text
N2 active condition run id
N3 subscription run id
N4 context run id
N4 synthetic denylist
N4 synthetic outbox run id
N5 current-real action run id
N5 current-real outbox pending counts
N3-C2 c2_run_id and closed_30m_summary counts
N3-C3 c3_run_id and MinuteBarClosed outbox counts
N3-C2B c2b_run_id and closed signal enrichment counts
N4-C3 replay audit replay_run_id and audit classification counts
N3-EOD eod_run_id, dry-run result, preflight blocker, and official daily missing counts
N4 20260528 canonical trigger execute_run_id and outbox pending counts
N5 20260528 canonical action_run_id and outbox pending counts
N1 20260528 official daily and condition source active source_version summary
N2 20260528 active condition run id, row counts, rollback safety, and N3 subscription 20260529 next gate
N3 subscription 20260529 market_data_run_id, row counts, required_data_kind distribution, rollback safety, and A1 next gate
A1 previous_day_minute 20260529 preload run id, actual rows, object status, rollback safety, and B1 next gate
B1 pre-open realtime snapshot fact-only 20260529 snapshot_run_id, row counts, source-time warning, outbox boundary, rollback safety, and 09:30 next gate
B1 live1 realtime snapshot fact-only 20260529 snapshot_run_id, row counts, live trading readiness, source-time summary, outbox boundary, rollback safety, and N4 trigger input proof
B1 live2 standard outbox snapshot 20260529 snapshot_run_id, row counts, MarketSnapshotUpdated pending counts, scoped exception proof, rollback safety, and N4 live2 execute proof
N4 live2 canonical trigger execute run id, outbox pending counts, canonical checks, N3 live2 input proof, rollback safety, and N5 live2 execute proof
N5 live2 canonical action execute run id, row counts, event distribution, outbox pending, N4 outbox unchanged proof, rollback safety, and N6 live2 / full-day projection next gate
N4 20260529 canonical trigger execute run id, outbox pending counts, canonical checks, N5 refs, rollback safety, and subsequent N5 execute proof
N5 20260529 canonical action execute run id, row counts, event distribution, outbox pending, rollback safety, and N6 contract/review next gate
N6 20260529 canonical shadow projection run id, row counts, projection policy, N5 outbox unchanged proof, rollback safety, and post-review next gate
027 N2 symmetry target price canonical compatibility migration status, boundary proof, rollback safety, and N2 writer/readiness alignment next gate
N2 canonical condition v2 active lineage supersede status, row counts, canonical target checks, boundary proof, rollback safety, and N3 subscription rebuild next gate
N2 display scope alignment v3 status, display scope row counts, alignment checks, boundary proof, rollback safety, and N3 subscription rebuild next gate
N2 20260529 -> 20260601 condition layer v1 preserved/superseded status, row counts, canonical checks, boundary proof, and rollback safety
N2 20260529 -> 20260601 financial canonical v2 preserved status, row counts, financial pass-through checks, boundary proof, and rollback safety
N2 20260529 -> 20260601 symmetry target price target-machine v3 active status, 000543/000027 golden proof, boundary proof, rollback safety, and N3 subscription 20260601 next gate
N2 20260529 -> 20260601 anchor-segment alignment v4 active status, 000600/000543/000027 golden proof, boundary proof, rollback safety, and N3 subscription 20260601 next gate
N2 20260529 -> 20260601 secondary-anchor v5 preserved status, boundary proof, rollback safety, and supersede proof
N2 20260529 -> 20260601 level score v6 active status, level score proof, boundary proof, rollback safety, and N3 subscription 20260601 next gate
```

验收标准：

- N2 active run 确认为 `condition_layer_20260522_to_20260525_20260525102249_execute`。
- N3 subscription run 确认为 `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- N3 preload run 确认为 `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- N3-B1 snapshot run `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute` 首次 execute 曾 commit 且 status=failed，随后已安全 rollback；同一 run_id 重跑 execute 已 passed。
- N3-B1 rerun execute 已 passed。
- 当前该 snapshot_run_id 的 `stock/index/board_realtime_daily_snapshot` 写入为 stock=2052, index=9, board=127。
- 当前该 snapshot_run_id 的 `common_event_outbox` 为 `MarketSnapshotUpdated pending=2188`。
- `MarketDataMissing / MarketDataDelayed = 0`。
- delivered/delivering=0；N4 projection matcher 已通过 inbox/checkpoint 处理当前 N3-B1 event；N5 current-real action consumer 已通过 N5 inbox/checkpoint 处理当前 N4 real outbox；N6 尚未消费当前 N5 outbox。
- rollback_safe=true。
- 旧 N3 subscription run `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute` 标记为 stale_after_n2_display_overwrite。
- N4 current context run 确认为 `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- N4 current context rows 为 stock=4236, index=18, board=258, total=4512。
- N4 current context rebuild P0/P1/P2=0/0/0。
- N4 current context rebuild 未写 `common_event_inbox`、未写 `common_trigger_match`、未写 N4 outbox、未消费 N3 outbox。
- 旧 synthetic denylist 包含 `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute` 和 `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute`。
- 旧 N4 context run `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute` 标记为 stale_after_n2_display_overwrite / synthetic_denylist。
- N4 real projection matcher execute run 确认为 `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- N4 real projection matcher execute 已 passed，写入 `common_event_inbox=2188 processed`、`common_event_consumer_checkpoint=2188`、`common_trigger_state=764`、`common_trigger_match=764`、`common_trigger_quality_item=9`。
- N4 outbox 为 `TriggerMatched pending=488`、`TriggerPendingMarketData pending=276`，delivered/delivering=0。
- B1 outbox 仍为 `MarketSnapshotUpdated pending=2188`；N3 facts unchanged=true；old synthetic outbox untouched=53304；downstream N5 inbox for this N4 run=764 processed。
- N4 rollback_safe=true；rollback SQL=`sql/N4_projection_matcher_rollback.sql`。
- N5 current-real action execute run 确认为 `action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- N5 current-real action execute 已 passed，`common_action_run.status=passed`，P0/P1/P2=0/0/0。
- N5 写入 `stock_action_fact=488`、`index_action_fact=0`、`board_action_fact=0`、`common_action_event=488`、`common_action_quality_item=276`。
- N5 写入 `common_event_inbox=764 processed`、`common_event_consumer_checkpoint=615`。
- N5 outbox 为 `ActionEvent pending=479`、`HintEvent pending=9`、`RiskEvent=0`、`PositionEvent=0`。
- N4 current outbox remains pending=764；N2/N3/N4 authoritative runs unchanged。
- `common_position_state=0`、`common_position_event=0`；no real trade / no sim / no voice / no mobile / no N6。
- N5 rollback_safe=true；rollback SQL=`sql/N5_current_real_action_execute_rollback.sql`。
- N4 20260528 canonical trigger execute 已 passed，execute_run_id = `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- N4 20260528 canonical outbox pending：`TriggerMatched=4285`、`TriggerPendingMarketData=4602`、`TriggerStateChanged=8887`，delivered/delivering=0。
- N5 20260528 canonical action execute 已 passed，action_run_id = `action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- N5 20260528 canonical source_trigger_run_id = `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- N5 20260528 canonical `common_action_run.status=passed`，P0/P1/P2=0/0/0。
- N5 20260528 canonical 写入 `common_action_quality_item=4602`、`stock_action_fact=4013`、`index_action_fact=18`、`board_action_fact=254`、`common_action_event=4285`、`common_event_outbox=4285`。
- N5 20260528 canonical 写入 `common_event_inbox=17774`、`common_event_consumer_checkpoint=2146`。
- N5 20260528 canonical outbox：`ActionBlocked pending=4285`，`ActionEligible=0`，`ActionExecuted=0`，`ActionSkipped=0`，delivered/delivering=0。
- N5 20260528 canonical checks：legacy output events=0，`ActionEvent=0`，`HintEvent=0`，`RiskEvent=0`，`PositionEvent=0`，runtime signal `B_BUY=2145` / `S_SELL=2140`。
- N5 20260528 canonical `BUY_HINT / SELL_HINT` trace-only，`action_mark NULL=4285`，`action_state blocked=4285`，`confirmation_status failed=4285`。
- N5 20260528 canonical boundary：N4 outbox status unchanged，N6 refs=0，position refs=0，user projection rows=0，worker_started=false，no voice/mobile/sim/real trade。
- N5 20260528 canonical rollback_safe=true；rollback SQL=`sql/N5_20260528_canonical_action_execute_rollback.sql`。
- N1 20260528 official daily ingestion 已 passed，`source_batch_id=official_daily_ingest_20260528_v1`，stock/index/board daily fact = 5506/83/428，total=6017，active source_version = `stock_daily_20260528_v1` / `index_daily_20260528_v1` / `board_daily_20260528_v1`，P0/P1/P2=0/19/0，rollback SQL=`sql/N1_official_daily_20260528_ingestion_rollback.sql`。
- N1 20260528 condition source activation 已 passed，`source_batch_id=condition_source_activation_20260528_v1`，stock_daily_basic=5506，stock_financial_metrics_fact=5506，index_membership_fact=12841，board_membership_fact=56958，total=80811，active source_version = `stock_daily_basic_20260528_v1` / `stock_financial_20260528_v1` / `index_membership_20260528_v1` / `board_membership_20260528_v1`，P0/P1/P2=0/3/1，rollback SQL=`sql/N1_condition_source_20260528_activation_rollback.sql`。
- N1 20260528 boundary：outbox/inbox/checkpoint delta=0/0/0，Parquet not written，N2/N3/N4/N5/N6 not entered，worker_started=false，old_system_touched=false，real_trading=false。
- N1 20260529 stock_financial canonical metrics v2 已 passed，`source_batch_id=stock_financial_canonical_20260529_v1`，`source_version=stock_financial_20260529_v2`，previous_source_version=`stock_financial_20260529_v1`，financial_metric_version=`financial_metric_v1`，stock_financial_metrics_fact v2 rows=5506，common_ingest_batch row_count=5506，common_quality_gate_result=13，P0/P1/P2=0/8/2，active stock_financial 20260529 -> `stock_financial_20260529_v2`。
- N1 20260529 stock_financial v2 boundary at N1 post-review time：outbox/inbox/checkpoint delta=0/0/0，condition refs to v2=0，Parquet not written，N2/N3/N4/N5/N6 not entered，worker_started=false，old_system_touched=false，real_trading=false，rollback_safe=true；rollback SQL=`sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql`。后续该 source_version 已由 N2 `condition_layer_20260529_source_20260529_v2` 消费。
- N1 20260602 official daily 已 passed，`source_batch_id=official_daily_ingest_20260602_v1`，stock/index/board/total=5507/83/428/6018，metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/31/3，active source_version=`stock_daily_20260602_v1` / `index_daily_20260602_v1` / `board_daily_20260602_v1`，source validation P0/P1/P2=0/19/0，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0，rollback SQL=`sql/N1_official_daily_20260602_ingestion_rollback.sql`。
- N1 20260602 condition source 已 passed，`source_batch_id=condition_source_activation_20260602_v1`，stock_daily_basic/stock_financial_metrics_fact/index_membership_fact/board_membership_fact/total=5507/5507/12841/56960/80815，metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/15/4，active source_version=`stock_daily_basic_20260602_v1` / `stock_financial_20260602_v1` / `index_membership_20260602_v1` / `board_membership_20260602_v1`，P0/P1/P2=0/2/1，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0，official daily untouched=true，N2/N3/N4/N5/N6 refs=0/0/0/0/0，worker/parquet/delivery/notification/real_trade=false，rollback SQL=`sql/N1_condition_source_20260602_activation_rollback.sql`。
- N1 readiness：`check_condition_source_ready --source-trade-date 20260528` passed=true；该 readiness 已被 N2 20260528 -> 20260529 condition layer execute 消费。
- N2 20260528 -> 20260529 condition layer execute 已 passed，run_id=`condition_layer_20260528_source_20260528_v1`，status=`passed_active`，passed_active_count=1。
- N2 20260528 quality：P0/P1/P2=0/6/3，common_condition_quality_item=106。
- N2 20260528 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，monitor_target=5506/83/428，condition_display_basis=5506/83/428。
- N2 20260528 canonical signal audit passed=true，deprecated_signal_rows=0，noncanonical_signal_rows=0。
- N2 20260528 boundary：outbox/inbox/checkpoint delta=0/0/0，market_data_pulled=false，N3/N4/N5/N6 entered=false，worker_started=false。
- N2 20260528 rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_rollback.sql`。
- N3 subscription 20260529 execute 已 passed，market_data_run_id=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，source_condition_run_id=`condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=`passed`。
- N3 subscription 20260529 quality：P0/P1/P2=0/0/0，quality rows=34。
- N3 subscription 20260529 row counts：candidate=5038，subscription=2643，pull_plan=7，objects stock/index/board/total=2021/9/127/2157。
- N3 subscription 20260529 required_data_kind：realtime_daily_snapshot=2157，minute_bar_1m=243，previous_day_minute_bar_1m=243。
- N3 subscription 20260529 canonical signals=BUY, BUY:FULL, SELL, SELL:FULL, BUY_HINT, SELL_HINT；deprecated_signal_rows=0。
- N3 subscription 20260529 boundary：market_data_pulled=false，market_data_fact_written=false，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- N3 subscription 20260529 rollback_safe=true；rollback SQL=`sql/N3_subscription_20260529_rollback.sql`。
- 20260529 A1 previous_day_minute preload 已 passed，preload_run_id=`previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=`passed`。
- 20260529 A1 actual rows：stock=56160，index=0，board=2160，total=58320。
- 20260529 A1 object status：stock passed/partial/missing=234/0/0，index expected objects/rows=0/0，board passed/partial/missing=9/0/0，fake index pull / fake index rows=0/0。
- 20260529 A1 quality：P0/P1/P2=0/0/0，quality rows=12。
- 20260529 A1 boundary：scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，old_system_touched=false。
- 20260529 A1 rollback_safe=true；rollback SQL=`sql/N3_A1_previous_day_minute_20260529_rollback.sql`。
- 20260529 B1 pre-open realtime snapshot fact-only 已 passed，snapshot_run_id=`realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=`passed`。
- 20260529 B1 mode：pre_open_fact_only=true，live_trading_snapshot_ready=false。
- 20260529 B1 rows stock/index/board/total=2021/9/127/2157，missing/failed=0/0。
- 20260529 B1 quality：P0/P1/P2=0/1/0，quality rows=11，P1 warning=`n3_b1_pre_open_source_time_not_confirmed`，P0 source date mismatch=0。
- 20260529 B1 source time：source_time_missing_or_preopen stock/index/total=2021/9/2030，source_time_confirmed board=127。
- 20260529 B1 outbox boundary：writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- 20260529 B1 downstream boundary：downstream_layers_touched=false，worker_started=false，N4/N5/N6 touched=false。
- 20260529 B1 rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_rollback.sql`。
- 20260529 B1 live1 realtime snapshot fact-only 已 passed，snapshot_run_id=`realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=`passed`。
- 20260529 B1 live1 mode：live_trading_snapshot_ready=true，pre_open_fact_only=false。
- 20260529 B1 live1 rows stock/index/board/total=2021/9/127/2157，missing/failed=0/0。
- 20260529 B1 live1 quality：P0/P1/P2=0/0/0，quality rows=11。
- 20260529 B1 live1 source-time：stock effective_quote_present/source_time_missing/partial_quality=2021/2021/0，index effective_quote_present/source_time_missing/partial_quality=9/9/0，board source_time_confirmed/effective_quote_present=127/127。
- 20260529 B1 live1 outbox boundary：writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint=105122/20726/4345。
- 20260529 B1 live1 downstream boundary：downstream_layers_touched=false，worker_started=false，N4/N5/N6 untouched=true。
- 20260529 B1 live1 rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql`。
- 20260529 B1 live2 standard outbox snapshot 已 passed，snapshot_run_id=`realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=`passed`。
- 20260529 B1 live2 rows stock/index/board/total=2021/9/127/2157。
- 20260529 B1 live2 quality：P0/P1/P2=0/0/0。
- 20260529 B1 live2 outbox：writes_outbox=true，MarketSnapshotUpdated=2157 pending，MarketDataDelayed=0，MarketDataMissing=0，MarketDisplaySnapshotUpdated=0，delivered/delivering=0/0。
- 20260529 B1 live2 boundary：scoped inbox/checkpoint refs=0/0，no inbox/checkpoint writes，downstream_layers_touched=false，worker_started=false，N4/N5/N6 not entered=true，scoped exception used for existing N6 web app / old system process but they did not consume v3 outbox。
- 20260529 B1 live2 rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql`。
- 20260529 N4 live2 canonical trigger execute 已 passed，execute_run_id=`trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`，common_trigger_run.status=`passed`。
- 20260529 N4 live2 rows：common_trigger_quality_item=17，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722。
- 20260529 N4 live2 outbox：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0。
- 20260529 N4 live2 quality：P0/P1/P2=0/1/0。
- 20260529 N4 live2 canonical checks：runtime signal_type B_BUY=4467 / S_SELL=4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing=0，matched trigger_live=true=4309，pending_market_data trigger_live=false=4552，common_trigger_match TriggerStateChanged=0。
- 20260529 N4 live2 boundary：N3 live2 input MarketSnapshotUpdated pending=2157，N3 input inbox/checkpoint refs=0/0，N5 refs=0，downstream inbox/checkpoint refs=0/0，global outbox delta=+17722，inbox/checkpoint delta=0/0，worker_started=false，action/user/voice/mobile/sim/position/real_trade touched=false。
- 20260529 N4 live2 rollback_safe=true；rollback SQL=`sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql`。
- 20260529 N5 live2 canonical action execute 已 passed，action_run_id=`action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`，common_action_run.status=`passed`。
- 20260529 N5 live2 quality：P0/P1/P2=0/0/0。
- 20260529 N5 live2 actual rows：common_action_quality_item=4552，stock_action_fact=4037，index_action_fact=18，board_action_fact=254，common_action_event=4309，common_event_outbox=4309，common_event_inbox=17722，common_event_consumer_checkpoint=2157。
- 20260529 N5 live2 event distribution：ActionBlocked=4309 pending，ActionEligible=0，ActionExecuted=0，ActionSkipped=0，legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0，delivered/delivering=0/0。
- 20260529 N5 live2 boundary：N4 outbox status unchanged（TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending），N6 refs=0，position rows=0，worker_started=false，voice/mobile/sim/position/real_trade=false。
- 20260529 N5 live2 rollback_safe=true；rollback SQL=`sql/N5_20260529_live2_canonical_action_execute_rollback.sql`。
- 20260529 N4 canonical trigger execute 已 passed，execute_run_id=`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，common_trigger_run.status=`passed`。
- 20260529 N4 quality：P0/P1/P2=0/1/0。
- 20260529 N4 rows：common_trigger_run=1，common_trigger_quality_item=16，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722。
- 20260529 N4 outbox：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0。
- 20260529 N4 canonical checks：common_trigger_match TriggerStateChanged=0，pending_market_data trigger_live=false=4552，matched trigger_live=true=4309，runtime signal B_BUY=4467 / S_SELL=4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing count=0。
- 20260529 N4 boundary：scoped inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，outbox_consumed=false，N5/N6 touched=false，worker_started=false，user/voice/mobile/sim/position/real_trade=false，N2/N3 facts unchanged=true。
- 20260529 N4 rollback_safe=true；rollback SQL=`sql/N4_20260529_canonical_trigger_execute_rollback.sql`。
- 20260529 N5 canonical action execute 已 passed，action_run_id=`action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，source N4 run=`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，common_action_run.status=`passed`。
- 20260529 N5 quality：P0/P1/P2=0/0/0。
- 20260529 N5 actual rows：common_action_quality_item=4552，stock_action_fact=4037，index_action_fact=18，board_action_fact=254，common_action_event=4309，common_event_outbox=4309，common_event_inbox=17722，common_event_consumer_checkpoint=2157。
- 20260529 N5 event distribution：ActionBlocked=4309，ActionEligible=0，ActionExecuted=0，ActionSkipped=0，legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0。
- 20260529 N5 outbox：pending=4309，delivered=0，delivering=0。
- 20260529 N5 boundary：N4 outbox status unchanged（TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending），N6 refs=0，position rows for this run=0，worker_started=false，N6 not entered=true，voice/mobile/sim/real_trade=false，old_system_touched=false。
- 20260529 N5 rollback_safe=true；rollback SQL=`sql/N5_20260529_canonical_action_execute_rollback.sql`。
- 20260529 N6 canonical shadow projection 已 passed，projection_run_id=`user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，source_action_run_id=`action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，run status=`passed`。
- 20260529 N6 quality：P0/P1/P2=0/5/2。
- 20260529 N6 actual rows：user_projection_run=1，user_signal_projection=4309，user_signal_card=4309，user_notification_queue=4309。
- 20260529 N6 projection policy：notification_source=`n5_action_blocked`，queue_status=`queued_only`，notification queued_only=4309，card mapping blocked / blocked / ActionBlocked / blocked = 4309，projection_policy=`blocked_unconfirmed_no_push_no_decision_no_sim_no_trade`，trace_json_nonnull=4309，source_action_event_type=`ActionBlocked`，action_state=`blocked`。
- 20260529 N6 boundary：N5 outbox unchanged（ActionBlocked pending=4309，delivered/delivering=0/0），n5_outbox_consumed=false，updates_n5_outbox_status=false，user_signal_decision=0，user_watchlist=0，user_watchlist_item=0，user_sim_order/trade/position=0，linked decision/sim refs=0，worker_started=false，push/voice/mobile=false，position/real_trade=false，N1-N5 unchanged=true。
- 20260529 N6 rollback_safe=true；rollback SQL=`sql/N6_projection_business_rollback.sql`。
- 032 N3 action-confirmation projection metric schema migration 已 passed，migration=`sql/032_n3_action_confirmation_metric_schema.sql`，target_db=`ashare_v3`，target_user=`ashare_v3_user`，target_host=`127.0.0.1/32`，target_port=`5432`，old_system_db=false。
- 032 created tables：`stock_action_confirmation_projection_metric`、`index_action_confirmation_projection_metric`、`board_action_confirmation_projection_metric`。
- 032 schema proof：index_count=18，metric_ready trace CHECK constraints=3，row_count stock/index/board=0/0/0。
- 032 boundary：business row written=false，market_data_pulled=false，common_event_outbox/inbox/checkpoint delta=0/0/0，downstream N4/N5/N6 checked tables=32，downstream row_count_delta_zero=true，worker_started=false。
- 032 rollback_safe=true；schema rollback SQL=`sql/032_n3_action_confirmation_metric_schema_rollback.sql`，business rollback SQL=`sql/N3_action_confirmation_projection_metric_business_rollback.sql`，execute report=`docs/N3_action_confirmation_projection_metric_032_migration_execute_report.json`。
- N3 action-confirmation projection writer execute 已 passed，projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- N3 action-confirmation source lineage：source_condition_run_id=`condition_layer_20260601_source_20260601_v1`，source_subscription_run_id=`market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，source_snapshot_run_id=`realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，source_today_minute_run_id=`today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，source_previous_day_minute_run_id=`previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- N3 action-confirmation runtime status：common_market_data_run.status=`passed`，rows stock/index/board/total=765/54/150/969，metric_ready/not_ready=969/0，common_market_data_quality_item rows=6，P0/P1/P2=0/0/0。
- N3 action-confirmation boundary：market_data_pulled=false，market_data_fact_written=true，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint=0/0/0，global outbox/inbox/checkpoint delta=0/0/0，no outbox write/consume，no inbox/checkpoint write，no N4/N5/N6 refs。
- N3 action-confirmation rollback_safe=true；rollback SQL=`sql/N3_action_confirmation_projection_metric_business_rollback.sql`；execute report=`docs/N3_action_confirmation_projection_writer_execute_report.json`。
- N4 action-confirmation metric business execute 已 passed，execute_run_id=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- N4 action-confirmation source lineage：source_projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，trigger_context_run_id=`trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1`，source_condition_run_id=`condition_layer_20260601_source_20260601_v1`。
- N4 action-confirmation runtime status：common_trigger_run.status=`passed`，common_trigger_run=1，common_trigger_quality_item=10，common_trigger_state=5941，common_trigger_match=5941，common_event_outbox=5941。
- N4 action-confirmation outbox：TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，delivered/delivering=0/0。
- N4 action-confirmation quality：P0/P1/P2=0/1/0，quality item distribution P0 passed=9 / P1 warning=1，P1=`n4_action_confirmation_metric_pending_candidates_visible` non-blocking。
- N4 action-confirmation boundary：N3 metric facts unchanged stock/index/board=765/54/150，common_event_inbox refs=0，checkpoint refs=0，N5 refs=0，N3 outbox consumed=false，inbox/checkpoint written=false，N5/N6 entered=false，worker_started=false，market_data_pulled=false，voice/mobile/sim/position/real_trade=false。
- N4 action-confirmation rollback_safe=true；rollback SQL=`sql/N4_action_confirmation_metric_business_execute_rollback.sql`；execute report=`docs/N4_action_confirmation_metric_business_execute_report.json`。
- N5 action-confirmation metric execute 已 passed，action_run_id=`action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- N5 action-confirmation source N4 run=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- N5 action-confirmation runtime status：common_action_run.status=`passed`，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/5935/1/4/0/5/5/5941/2487。
- N5 action-confirmation outbox：ActionExecuted=4 pending，ActionBlocked=1 pending，ActionEligible=0，ActionSkipped=0，delivered/delivering=0/0。
- N5 action-confirmation boundary：N4 outbox unchanged TriggerMatched=6 pending、TriggerPendingMarketData=5935 pending、TriggerStateChanged=0、delivered/delivering=0/0；N6/user/downstream refs=0；position refs=0；voice/mobile/sim/real_trade refs=0；worker_started=false。
- N5 action-confirmation rollback_safe=true；rollback SQL=`sql/N5_20260602_action_confirmation_metric_execute_rollback.sql`；execute report=`docs/N5_20260602_action_confirmation_metric_execute_report.json`。
- N6 20260602 action-confirmation metric shadow projection execute 已 passed，projection_run_id=`user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- N6 20260602 source_action_run_id=`action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- N6 20260602 runtime status：preflight_result=`PREFLIGHT_PASS`，run status=`passed`，P0/P1/P2=0/5/2。
- N6 20260602 rows：user_projection_run=1，user_signal_projection=5，user_signal_card=5，user_notification_queue=5。
- N6 20260602 queue distribution：`n5_action_executed / queued_only = 4`，`n5_action_blocked / queued_only = 1`。
- N6 20260602 card distribution：ActionExecuted -> action_confirmed / executed / 30m_shrink = 4；ActionBlocked -> blocked / blocked = 1。
- N6 20260602 boundary：N5 outbox unchanged（ActionExecuted pending=4，ActionBlocked pending=1），N5 outbox consumed=false，N5 outbox status updated=false，user_signal_decision=0，linked user_sim_order/trade/position=0/0/0，user_watchlist=0，user_watchlist_item=0，worker_started=false，push/voice/mobile=false，sim/position/real_trade=false。
- N6 20260602 rollback_safe=true；rollback SQL=`sql/N6_projection_business_rollback.sql`。
- 027 N2 symmetry target price canonical compatibility migration 已 passed，migration=`027_condition_symmetry_target_price_compatibility_migration.sql`。
- 027 touched tables=12 N2 tables：stock/index/board condition_basis、condition_pool、minute_target_scope、condition_display_basis。
- 027 new canonical fields exist=true，CHECK constraints validated=true，locked_target_price / target_lock_status absent=true。
- 027 business row count delta=0，outbox/inbox/checkpoint delta=0/0/0，new fields non-null count=0。
- 027 boundary：N2 writer not executed，backfill not executed，N3/N4/N5/N6 not entered，worker_started=false，old_system_touched=false。
- 027 rollback_safe=true；rollback SQL=`sql/027_condition_symmetry_target_price_compatibility_rollback.sql`。
- N2 canonical condition v2 active lineage supersede execute 已 passed，new active run_id=`condition_layer_20260528_source_20260528_v2`，v2.status=`passed_active`，previous active v1=`condition_layer_20260528_source_20260528_v1`，v1.status=`superseded`。
- N2 v2 rows：condition_basis stock/index/board=5506/83/428，condition_pool stock/index/board=4271/18/263，minute_target_scope stock/index/board=4271/18/263，condition_display_basis stock/index/board=5506/83/428，monitor_target stock/index/board=5506/83/428。
- N2 v2 quality：quality_item=103，P0/P1/P2=0/3/3。
- N2 v2 canonical target checks：alias mismatch=0，negative numeric fields=0，forbidden fields=0；first failed attempt rolled back due negative reference_target_price CHECK；writer fixed negative canonical target numeric fields to NULL and preserved raw negative value only in trace。
- N2 v2 boundary：v1 rows and downstream refs preserved，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，outbox/inbox/checkpoint delta=0/0/0。
- N2 v2 rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql`。
- N2 display scope alignment v3 已 preserved/superseded，run_id=`condition_layer_20260528_source_20260528_v3`，previous N2 run=`condition_layer_20260528_source_20260528_v2`，v2.status=`superseded`，后续已被 v5 active supersede。
- N2 v3 rows：condition_basis stock/index/board=5506/83/428，condition_pool stock/index/board=4271/18/263，minute_target_scope stock/index/board=4271/18/263，condition_display_basis stock/index/board=2021/9/127，monitor_target stock/index/board=5506/83/428。
- N2 v3 quality/checks：common_condition_quality_item=103，P0/P1/P2 failed=0/0/0，display duplicate groups=0/0/0，alias mismatch=0，negative numeric rows=0，locked_target_price / target_lock_status absent=true。
- N2 v3 boundary：downstream refs=0，outbox/inbox v3 refs=0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false。
- N2 v3 rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql`。
- N2 symmetry target price alignment v5 已 passed_active，active N2 run=`condition_layer_20260528_source_20260528_v5`，previous active v4=`condition_layer_20260528_source_20260528_v4`，v4.status=`superseded`，passed_active_count=1。
- N2 v5 golden：000027 main_up_anchor=W，up_reference_period=D，up_amplitude=1.17，up_base_price=7.25，buy_target_price=8.42，reference_target_price=8.42。
- N2 v5 rows：condition_basis stock/index/board=5506/83/428，condition_pool=4271/169/875，minute_target_scope=4251/169/875，condition_display_basis=2011/83/428，monitor_target=5506/83/428。
- N2 v5 quality/checks：common_condition_quality_item=103，P0/P1/P2=0/3/3，deprecated signal rows=0，alias mismatch=0，invalid reference period=0，locked_target_price / target_lock_status absent=true。
- N2 v5 boundary：outbox/inbox refs=0/0，N3/N4/N5 refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql`。
- 20260529 -> 20260601 N2 condition layer v1 已 preserved/superseded，run_id=`condition_layer_20260529_source_20260529_v1`，source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529。
- N2 20260529 v1 rows：condition_basis stock/index/board=5506/83/428，condition_pool stock/index/board=4342/187/942，minute_target_scope stock/index/board=4323/187/942，condition_display_basis stock/index/board=1973/83/428，monitor_target stock/index/board=5506/83/428。
- N2 20260529 v1 quality/checks：common_condition_quality_item=109，P0/P1/P2=0/9/3，canonical signal audit passed，deprecated/noncanonical signal rows=0/0。
- N2 20260529 v1 boundary：outbox/inbox/checkpoint delta=0/0/0，N3/N4/N5 downstream refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260529_rollback.sql`。
- 20260529 -> 20260601 N2 financial canonical v2 已 passed/preserved，run_id=`condition_layer_20260529_source_20260529_v2`，v1.status=`superseded`，后续已被 v3 active supersede；condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，P0/P1/P2=0/6/3，financial pass-through mismatch=0。
- 20260529 -> 20260601 N2 symmetry target price target-machine v3 已 passed/preserved，run_id=`condition_layer_20260529_source_20260529_v3`，v2.status=`superseded`，后续已被 v4 active supersede，000543 buy_target_price/reference_target_price=10.82/10.82，000027 buy_target_price/reference_target_price=8.45/8.45，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，P0/P1/P2=0/6/3，rollback_safe=true。
- 20260529 -> 20260601 N2 anchor-segment alignment v4 已 passed/preserved，run_id=`condition_layer_20260529_source_20260529_v4`，后续已被 v5 active supersede，row counts aligned，golden 000600/000543/000027=12.93/10.82/8.45，P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true；rollback SQL=`sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql`。
- 20260529 -> 20260601 N2 secondary-anchor v5 已 passed/preserved，run_id=`condition_layer_20260529_source_20260529_v5`，后续已被 v6 active supersede，P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true；rollback SQL=`sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql`。
- 20260529 -> 20260601 N2 level score v6 已 passed_active，active N2 run=`condition_layer_20260529_source_20260529_v6`，previous active v5=`superseded`，P0/P1/P2=0/6/3，level_score_ok=true，row_match=true，golden 000543/000600/300327 level_score_up/down=3124/0、3124/0、2999/125，N3/N4/N5 refs=0/0/0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true；rollback SQL=`sql/N2_level_score_20260529_v6_rollback.sql`。
- 后续只允许 N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review、B1 realtime snapshot readiness/final gate、N3_market_data subscription rebuild gate for 20260529 based on `condition_layer_20260528_source_20260528_v5`，以及 subscription rebuild gate for 20260601 based on `condition_layer_20260529_source_20260529_v6`；runtime_control 不执行 B1/N4/N5/N6、不拉实时行情、不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。
- N3-C2 closed-minute / closed-30m replay execute 已 passed。
- C2 run id 确认为 `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- C2 minute_delta_rows：stock=100669，index=441，board=6223，total=107333。
- C2 closed_30m_summary rows：stock=16416，index=72，board=1016，total=17504。
- C2 summary_status：closed=17432，partial=0，missing=72，failed=0。
- C2 BJ 920xxx：9 objects，72 missing summaries，no fabricated minute rows。
- C2 quality P0/P1/P2=0/1/0。
- C2 outbox/inbox/checkpoint refs=0；B1 MarketSnapshotUpdated pending=2188。
- C2 保持 C1/B1/B2/N4/N5 runtime unchanged=true；worker_started=false；downstream_layers_touched=false。
- C2 rollback_safe=true；rollback SQL=`sql/N3_C2_closed_30m_business_rollback.sql`。
- N3-C3 MinuteBarClosed outbox execute 已 passed。
- C3 run id 确认为 `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- C3 `common_market_data_run.status=passed`；P0/P1/P2=0/1/0。
- C3 `market_data_pulled=false`；`market_data_fact_written=false`；source_trade_date/prev_trade_date=20260525/20260525。
- C3 `MinuteBarClosed` outbox rows=17432，stock/index/board=16344/72/1016。
- C3 outbox pending=17432，delivered/delivering=0，inbox=0，checkpoint refs=0。
- C3 boundary: closed_30m_summary C3 refs=0；minute_bar_1m C3 refs=0；realtime_projection_metric C3 refs=0；realtime_daily_snapshot C3 refs=0。
- C3 N4/N5/N6 touched=false；worker_started=false。
- C3 rollback_safe=true；rollback SQL=`sql/N3_C3_minute_bar_closed_outbox_rollback.sql`。
- N3-C2B closed_signal_enrichment execute 已 passed。
- C2B run id 确认为 `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- C2B `common_market_data_run.status=passed`；P0/P1/P2=0/3/0。
- C2B enrichment rows：stock=16416，index=72，board=1016，total=17504。
- C2B computable_rows=17432，unknown_rows=72，missing_rows=72。
- C2B signal distribution：up_volume_expanding=2800，up_volume_flat=2494，up_volume_shrinking=2260，down_volume_expanding=2806，down_volume_flat=2408，down_volume_shrinking=2011，flat=2653，unknown=72。
- C2B quality_rows=6；data_domain common=3 / stock=3；layer_scope=market_data_run；details.metric_scope=closed_signal_enrichment。
- C2B outbox=0；inbox=0；checkpoint refs=0。
- C2B 未消费 C3 outbox；C3 outbox pending=17432，delivered/delivering=0，inbox/checkpoint refs=0。
- C2B 未修改 closed_30m_summary / minute_bar_1m / realtime_projection_metric / realtime_daily_snapshot。
- C2B rollback_safe=true；rollback SQL=`sql/N3_C2B_closed_signal_enrichment_business_rollback.sql`。
- N4-C3 replay audit execute 已 passed。
- N4-C3 replay_run_id 确认为 `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`。
- N4-C3 replay audit `common_trigger_run.status=passed`。
- N4-C3 replay audit rows：stock=33762，index=144，board=2064，total=35970。
- N4-C3 replay audit classification：would_match=4734，would_clear=245，would_change=243，unchanged=30730，missing=18，not_ready=0。
- N4-C3 replay audit P0/P1/P2=0/1/0。
- N4-C3 replay audit boundary：`common_event_outbox=0`，`common_event_inbox=0`，checkpoint refs=0，`common_trigger_match=0`，`common_trigger_state=0`。
- C3 outbox remains pending=17432；C3 delivered/delivering=0。
- N4-C3 replay audit N5/N6 touched=false；worker_started=false。
- N4-C3 replay audit rollback_safe=true；rollback SQL=`sql/N4_C3_replay_audit_business_rollback.sql`。
- N3-EOD snapshot refresh dry-run 已 PASS。
- EOD run id 确认为 `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- EOD expected snapshot rows：stock=2052，index=9，board=127，total=2188。
- EOD execute preflight = PREFLIGHT_BLOCKED；blocker=`missing_official_daily_fact`；official_daily_missing=2188。
- C3 outbox remains pending=17432；C3 delivered/delivering=0。
- EOD P0/P1/P2=0/3/0。
- EOD business rows=0；common_market_data_run/quality scoped eod_run_id=0；outbox/inbox/checkpoint scoped eod_run_id=0。
- EOD execute 继续 blocked；下一步推荐 N1 official daily fact ingestion review。
- 禁止使用 C2/C2B 直接做正式 EOD settlement，除非另开 provisional settlement gate。
- 本总控登记任务本身不产生任何数据库写入。

禁止事项：

- 不切换 active run。
- 不回滚旧 run。
- 不消费 outbox。
- 不启动 worker。
- 不执行 B1，不拉行情，不写 snapshot/outbox/inbox/checkpoint，不进入 N4/N5/N6。

### T1C. 20260528 N1 ingestion passed

状态：done for N1 official daily + condition source activation passed。
目标：登记 20260528 N1 入库闭环，作为 N2_condition 20260528 -> 20260529 的上游 readiness。

输入：

```text
official_daily_ingest_20260528_v1
condition_source_activation_20260528_v1
sql/N1_official_daily_20260528_ingestion_rollback.sql
sql/N1_condition_source_20260528_activation_rollback.sql
check_condition_source_ready --source-trade-date 20260528
```

输出：

```text
20260528 official daily active source versions
20260528 condition source active source versions
N1 boundary proof
N2_condition next gate readiness
```

验收标准：

- Official daily rows：stock=5506，index=83，board=428，total=6017。
- Official daily active source_version：`stock_daily_20260528_v1`，`index_daily_20260528_v1`，`board_daily_20260528_v1`。
- Official daily P0/P1/P2=0/19/0。
- Condition source rows：stock_daily_basic=5506，stock_financial_metrics_fact=5506，index_membership_fact=12841，board_membership_fact=56958，total=80811。
- Condition source active source_version：`stock_daily_basic_20260528_v1`，`stock_financial_20260528_v1`，`index_membership_20260528_v1`，`board_membership_20260528_v1`。
- Condition source P0/P1/P2=0/3/1。
- outbox/inbox/checkpoint delta=0/0/0。
- Parquet not written；N2/N3/N4/N5/N6 not entered；worker_started=false；old_system_touched=false；real_trading=false。
- rollback_safe=true for both N1 runs。
- `check_condition_source_ready --source-trade-date 20260528` passed=true。

下一步：

- 20260528 -> 20260529 condition layer gate 已完成并登记为 T1D。
- N3 subscription 20260529 execute 已完成并登记为 T1E。
- 20260529 A1 previous_day_minute preload 已完成并登记为 T1F。
- 20260529 B1 pre-open realtime snapshot fact-only 已完成并登记为 T1G。
- 20260529 B1 live1 realtime snapshot fact-only 已完成并登记为 T1H。
- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- 不允许 runtime_control 消费 N3/N4/N5 outbox、更新 N5 outbox status 或启动 worker。

### T1C.2. 20260602 N1 source baseline complete

状态：done for N1 official daily + condition source activation passed。
目标：登记 20260602 N1 source baseline；该 baseline 曾作为 N2 condition layer 20260602 dry-run/preflight 的上游 readiness，当前已被 `condition_layer_20260602_source_20260602_v1` 消费。

输入：

```text
docs/N1_official_daily_20260602_ingestion_execute_report.json
docs/N1_OFFICIAL_DAILY_20260602_INGESTION_EXECUTE_REPORT.md
docs/N1_condition_source_20260602_activation_execute_report.json
docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_EXECUTE_REPORT.md
sql/N1_official_daily_20260602_ingestion_rollback.sql
sql/N1_condition_source_20260602_activation_rollback.sql
```

验收标准：

- Official daily rows：stock=5507，index=83，board=428，total=6018。
- Official daily active source_version：`stock_daily_20260602_v1`，`index_daily_20260602_v1`，`board_daily_20260602_v1`。
- Official daily source validation P0/P1/P2=0/19/0，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true。
- Condition source rows：stock_daily_basic=5507，stock_financial_metrics_fact=5507，index_membership_fact=12841，board_membership_fact=56960，total=80815。
- Condition source active source_version：`stock_daily_basic_20260602_v1`，`stock_financial_20260602_v1`，`index_membership_20260602_v1`，`board_membership_20260602_v1`。
- Condition source P0/P1/P2=0/2/1，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0。
- official daily untouched=true；N2/N3/N4/N5/N6 refs=0/0/0/0/0。
- worker/parquet/delivery/notification/real_trade=false。
- rollback_safe=true for both N1 runs。

下一步：

- 20260602 N2 condition layer 已完成并登记为 T1C.3。
- 20260603 N3 subscription 已完成并登记为 T1C.4。
- 20260603 A1 previous-day minute preload 已完成并登记为 T1C.5。
- 20260603 trade calendar repair 已完成并登记为 T1C.6。
- 20260603 B1 realtime snapshot fact-only retry 已完成并登记为 T1C.7。
- 20260603 N4 trigger_context_snapshot rebuild 已完成并登记为 T1C.8。
- 20260603 N4 canonical trigger execute matcher fix 后已完成并登记为 T1C.9。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 只允许进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- 不允许 runtime_control 执行 N6，不消费 N4/N5 outbox，不启动 worker，不触发 delivery / notification / real trade。

### T1C.3. 20260602 N2 condition layer passed

状态：done for N2 condition layer 20260602 passed_active。
目标：登记 20260602 N2 condition layer broad policy baseline；该 baseline 已被 20260603 N3 subscription 消费。

输入：

```text
docs/N2_condition_layer_20260602_execute_report.json
docs/N2_CONDITION_LAYER_20260602_EXECUTE_POST_REVIEW.md
docs/N2_condition_layer_20260602_execute_post_review.json
docs/N2_CONDITION_LAYER_20260602_DRY_RUN_REPORT.md
docs/N2_CONDITION_LAYER_20260602_EXECUTE_CONTRACT.md
docs/N2_CONDITION_LAYER_20260602_EXECUTE_PREFLIGHT.md
sql/N2_condition_layer_20260602_rollback.sql
```

验收标准：

- run_id=`condition_layer_20260602_source_20260602_v1`。
- status=`passed_active`，source_trade_date=20260602，for_trade_date=20260603。
- policy_source=`8782_console`，policy_id=`n2_default_policy`，policy_version=`v4`。
- policy_hash=`ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576`。
- P0/P1/P2=0/9/3，common_condition_quality_item=109。
- condition_basis stock/index/board=5507/83/428。
- condition_pool stock/index/board=4182/168/890。
- minute_target_scope stock/index/board=4164/168/890。
- condition_display_basis stock/index/board=1963/83/428。
- monitor_target stock/index/board=5507/83/428。
- row_mismatches={}，expected rows = actual rows = broad policy rows。
- outbox/inbox/checkpoint refs=0/0/0。
- N3/N4/N5/N6 refs=0/0/0/0。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260602_rollback.sql`。

下一步：

- 20260603 N3 subscription 已完成并登记为 T1C.4。
- 20260603 A1 previous-day minute preload 已完成并登记为 T1C.5。
- 20260603 trade calendar repair 已完成并登记为 T1C.6。
- 20260603 B1 realtime snapshot fact-only retry 已完成并登记为 T1C.7。
- 20260603 N4 trigger_context_snapshot rebuild 已完成并登记为 T1C.8。
- 20260603 N4 canonical trigger execute matcher fix 后已完成并登记为 T1C.9。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 只允许进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- 不允许 runtime_control 执行 N5/N6，不消费 N4/N5 outbox，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.4. 20260603 N3 subscription passed

状态：done for N3 subscription 20260603 passed。
目标：登记 20260603 N3 subscription control rows，作为 A1 previous-day minute preload gate 的上游锚点。

输入：

```text
docs/N3_subscription_20260603_execute_report.json
docs/N3_SUBSCRIPTION_20260603_EXECUTE_REPORT.md
docs/N3_subscription_20260603_execute_backup_before.json
docs/N3_subscription_20260603_execute_backup_after.json
docs/N3_subscription_20260603_execute_preflight.json
docs/N3_subscription_20260603_rollback_registry.json
sql/N3_subscription_20260603_rollback.sql
```

验收标准：

- market_data_run_id=`market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- source_condition_run_id=`condition_layer_20260602_source_20260602_v1`。
- common_market_data_run.status=`passed`。
- source_trade_date=20260602，for_trade_date=20260603，prev_trade_date=20260602。
- candidate rows=5776，subscription rows=3028，pull_plan rows=9，quality rows=34。
- objects stock/index/board/total=1963/83/428/2474。
- required_data_kind realtime_daily_snapshot=2474，minute_bar_1m=277，previous_day_minute_bar_1m=277。
- P0/P1/P2=0/1/0。
- P1=`common_trade_calendar(20260603)` missing；该 warning 不阻断 subscription control-row execute，且已由 T1C.6 calendar repair 解除 B1 前置 blocker。
- market_data_pulled=false，market_data_fact_written=false，event_outbox_written=false，downstream_layers_touched=false，worker_started=false。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- A1/B1/N4/N5/N6 touched=false。
- rollback_safe=true；rollback SQL=`sql/N3_subscription_20260603_rollback.sql`。
- rollback SQL hard-fails before DELETE and deletes only N3 subscription control rows.

下一步：

- 20260603 A1 previous-day minute preload 已完成并登记为 T1C.5。
- 20260603 trade calendar repair 已完成并登记为 T1C.6。
- 20260603 B1 realtime snapshot fact-only retry 已完成并登记为 T1C.7。
- 20260603 N4 trigger_context_snapshot rebuild 已完成并登记为 T1C.8。
- 20260603 N4 canonical trigger execute matcher fix 后已完成并登记为 T1C.9。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 只允许进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- 不允许 runtime_control 执行 N5/N6，不拉实时行情，不消费 N4/N5 outbox，不启动 worker。

### T1C.5. 20260603 A1 previous-day minute preload passed

状态：done for A1 previous-day minute preload 20260603 passed。
目标：登记 20260603 A1 previous-day minute facts/status，作为 B1 realtime snapshot gate 的前置 baseline。

输入：

```text
docs/N3_A1_previous_day_minute_20260603_execute_report.json
docs/N3_A1_PREVIOUS_DAY_MINUTE_20260603_EXECUTE_REPORT.md
docs/N3_A1_previous_day_minute_20260603_execute_backup_before.json
docs/N3_A1_previous_day_minute_20260603_execute_backup_after.json
docs/N3_A1_previous_day_minute_20260603_execute_preflight.json
sql/N3_A1_previous_day_minute_20260603_rollback.sql
```

验收标准：

- preload_run_id=`previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- source subscription run=`market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- common_market_data_run.status=`passed`。
- previous_day_minute_date=20260602，for_trade_date=20260603。
- actual rows stock/index/board/total=57840/480/8160/66480。
- object status stock/index/board/total=241/2/34/277 all passed。
- missing/partial/failed=0/0/0。
- quality rows=12。
- P0/P1/P2=0/1/0。
- P1=`n3_a1_contract_p1_carried`，rooted in historical `common_trade_calendar(20260603)` missing warning；该 calendar blocker 已由 T1C.6 repair 解除。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint unchanged=164214/68560/5163。
- realtime snapshot rows for this run=0/0/0。
- event_outbox_written=false，downstream_layers_touched=false，worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N3_A1_previous_day_minute_20260603_rollback.sql`。
- A1 market_data_pulled=true / market_data_fact_written=true is limited to previous-day minute facts/status, not B1 realtime snapshot/projection.

下一步：

- 20260603 trade calendar repair 已完成并登记为 T1C.6。
- 20260603 B1 realtime snapshot fact-only retry 已完成并登记为 T1C.7。
- 20260603 N4 trigger_context_snapshot rebuild 已完成并登记为 T1C.8。
- 20260603 N4 canonical trigger execute matcher fix 后已完成并登记为 T1C.9。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 只允许进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- 不允许 runtime_control 执行 N5/N6，不拉实时行情，不消费 N4/N5 outbox，不启动 worker。

### T1C.6. common_trade_calendar(20260603) repair passed

状态：done for trade calendar 20260603 fix-forward repair passed。
目标：登记 `common_trade_calendar(20260603)` fix-forward patch，解除 B1 realtime snapshot 前置 calendar blocker；该登记不授权 runtime_control 执行 B1。

输入：

```text
docs/N1_trade_calendar_20260603_patch_execute_report.json
docs/N1_TRADE_CALENDAR_20260603_PATCH_EXECUTE_REPORT.md
docs/N1_trade_calendar_20260603_patch_preflight.json
docs/N1_TRADE_CALENDAR_20260603_PATCH_PREFLIGHT.md
docs/N1_trade_calendar_20260603_patch_fix_forward_contract.json
docs/N1_TRADE_CALENDAR_20260603_PATCH_FIX_FORWARD_CONTRACT.md
sql/N1_trade_calendar_20260603_patch_rollback.sql
```

验收标准：

- `common_trade_calendar(20260603)=1`。
- `is_open=true`，prev_trade_date=20260602，next_trade_date=20260604。
- source=`tushare.trade_cal.patch`。
- source_batch_id/source_version=`trade_calendar_20260603_patch_v1`。
- active source_version：`common / trade_calendar / SSE:20260603 -> trade_calendar_20260603_patch_v1`。
- metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/11/1。
- persisted quality：P0 passed=11。
- outbox/inbox/checkpoint delta=0/0/0。
- B1 realtime snapshot refs=0，N4 refs=0，N5 refs=0。
- N2 refs remain=1，N3 refs remain=2，A1 refs remain=1。
- worker_started=false，realtime_market_data_pulled=false。
- delivery/notification/push/voice/mobile/sim/position/real_trade=false。
- rollback SQL=`sql/N1_trade_calendar_20260603_patch_rollback.sql`。
- rollback_safe_scope=true；hard_fail_before_delete=true。
- standalone calendar rollback currently expected to hard-fail because N2/N3/A1 refs exist；如需 rollback calendar，必须先 rollback A1、N3 subscription、N2，或进入专门 rollback plan。

下一步：

- B1 前置 calendar blocker 已解除，且 B1 realtime snapshot fact-only retry 已完成并登记为 T1C.7。
- 20260603 N4 trigger_context_snapshot rebuild 已完成并登记为 T1C.8。
- 20260603 N4 canonical trigger execute matcher fix 后已完成并登记为 T1C.9。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 只允许进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- 不允许 runtime_control 执行 N5/N6，不拉实时行情，不消费 N4/N5 outbox，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.7. 20260603 B1 realtime snapshot fact-only passed

状态：done for B1 realtime snapshot 20260603 fact-only retry passed。
目标：登记 20260603 B1 realtime snapshot facts，作为后续 N4 trigger_context_snapshot rebuild 与 local trigger dry-run 的 N3 fact-only baseline；该登记不授权 runtime_control 执行 N4。

输入：

```text
docs/N3_B1_realtime_snapshot_20260603_execute_report.json
docs/N3_B1_REALTIME_SNAPSHOT_20260603_EXECUTE_REPORT.md
docs/N3_B1_realtime_snapshot_20260603_execute_backup_before.json
docs/N3_B1_realtime_snapshot_20260603_execute_backup_after.json
docs/N3_B1_realtime_snapshot_20260603_execute_contract.json
docs/N3_B1_realtime_snapshot_20260603_execute_preflight.json
sql/N3_B1_realtime_snapshot_20260603_rollback.sql
```

验收标准：

- snapshot_run_id=`realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- source_subscription_run_id=`market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- source_condition_run_id=`condition_layer_20260602_source_20260602_v1`。
- common_market_data_run.status=`passed`。
- actual rows stock/index/board/total=1963/83/428/2474。
- expected rows stock/index/board/total=1963/83/428/2474。
- quality rows=11。
- P0/P1/P2=0/1/0。
- P1=`n3_b1_contract_p1_carried`，为非阻断 carried contract warning。
- BJ fallback rows written and passed：`index:BJ:899050`、`index:BJ:899601`。
- BJ fallback source_version=`tushare.index_daily.bj_snapshot_fallback.v1`。
- BJ fallback source_path=`tushare.index_daily.previous_trade_date_bootstrap`。
- writes_outbox=false，generated_outbox_events=[]。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint delta=0/0/0。
- N4/N5/N6 refs=0。
- downstream_layers_touched=false，worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260603_rollback.sql`。
- rollback SQL hard-fails before DELETE and guards event refs / N4-N6 downstream refs / worker flags.

下一步：

- 后续已完成 T1C.8 N4 trigger_context_snapshot 20260603 rebuild passed。
- 后续已完成 T1C.9 N4 canonical trigger execute 20260603 passed。
- 不允许 runtime_control 执行 N5/N6，不消费 N4 outbox，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.8. 20260603 N4 trigger_context_snapshot rebuild passed

状态：done for N4 trigger_context_snapshot 20260603 rebuild passed。
目标：登记 20260603 N4 context 本地化已从 N2 20260602 active run 与 N3 B1 fact-only baseline 生成；后续 local trigger dry-run 与 N4 canonical trigger execute 已完成并登记为 T1C.9。

输入：

```text
docs/N4_20260603_trigger_context_rebuild_execute_report.json
docs/N4_20260603_TRIGGER_CONTEXT_REBUILD_EXECUTE_REPORT.md
docs/N4_20260603_trigger_context_preflight.json
sql/N4_20260603_trigger_context_rebuild_rollback.sql
```

验收标准：

- trigger_context_run_id=`trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1`。
- source_condition_run_id=`condition_layer_20260602_source_20260602_v1`。
- source_market_data_run_id=`realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- market_subscription_run_id=`market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- common_trigger_run.status=`passed`。
- rows stock/index/board/total=4164/168/890/5222。
- object coverage stock/index/board=1963/83/428。
- BUY_HINT / SELL_HINT trace rows=216/61。
- period_trigger_baseline_json_missing=0。
- required_period_not_ready_rows=0。
- common_trigger_run/common_trigger_quality_item=1/62。
- P0/P1/P2=0/0/0。
- common_trigger_state=0；common_trigger_match=0；common_event_outbox=0。
- common_event_inbox refs=0；checkpoint refs=0。
- N5 refs=0；N6 refs=0。
- N3 B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0。
- market_data_pulled=false；n3_event_consumed=false；worker_started=false。
- N5/N6 not entered=true；old_system/real_trade=false。
- rollback_safe=true；rollback SQL=`sql/N4_20260603_trigger_context_rebuild_rollback.sql`。
- rollback SQL hard-fails before DELETE and guards event refs / trigger_state / trigger_match / N5 action refs / N6 projection-card-notification refs via to_regclass。

下一步：

- 后续已完成 T1C.9 N4 canonical trigger execute 20260603 passed after matcher fix。
- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 20260603 N4 v4 execute 与 N5 v1 market-action-confirmation execute 已完成并登记为 T1C.11。
- 当前只允许单独进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- runtime_control 不执行 N6，不消费 N4/N5 outbox，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.9. 20260603 N4 canonical trigger execute passed after matcher fix

状态：done for N4 canonical trigger execute 20260603 passed after matcher fix。
目标：登记 20260603 N4 canonical trigger run-once 已基于 N4 context 与 B1 snapshot 写入 trigger_state / trigger_match / N4 outbox；该登记不授权 runtime_control 消费 N4 outbox 或执行 N5/N6。

输入：

```text
docs/N4_20260603_CANONICAL_TRIGGER_EXECUTE_REPORT.md
docs/N4_20260603_canonical_trigger_execute_report.json
docs/N4_20260603_CANONICAL_TRIGGER_EXECUTE_CONTRACT.md
docs/N4_20260603_canonical_trigger_execute_contract.json
docs/N4_20260603_CANONICAL_TRIGGER_EXECUTE_PREFLIGHT.md
docs/N4_20260603_canonical_trigger_execute_preflight.json
sql/N4_20260603_canonical_trigger_execute_rollback.sql
```

验收标准：

- execute_run_id=`trigger_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- trigger_context_run_id=`trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1`。
- snapshot_run_id=`realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- market_subscription_run_id=`market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`。
- common_trigger_run.status=`passed`。
- P0/P1/P2=0/1/0。
- quality rows=17，P0 passed=16，P1 warning=1。
- common_trigger_state=10167。
- common_trigger_match=10167。
- common_event_outbox=20334。
- TriggerMatched=1252。
- TriggerPendingMarketData=8915。
- TriggerStateChanged=10167。
- outbox pending=20334，delivered=0，delivering=0。
- runtime signal B_BUY/S_SELL=5164/5003。
- deprecated runtime signal count=0。
- trigger_mark_candidate normal/30m_volume/30m_shrink=5222/2474/2471。
- pending_market_data trigger_live=false=8915。
- matched trigger_live=true=1252。
- TriggerStateChanged in common_trigger_match=0。
- final action_mark columns in trigger state/match=0。
- anomaly proof：B_BUY current_price/close <= open=0，S_SELL current_price/close >= open=0，B_BUY amount below localized baseline=0，S_SELL amount above localized baseline=0。
- inbox/checkpoint refs for this N4 run=0/0。
- N5 common_action_run/common_action_event refs=0/0。
- N6 projection/card/queue refs=0/0/0/0。
- source B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0。
- market_data_pulled=false，action_layer_touched=false，user_layer_touched=false。
- voice_touched=false，sim_touched=false，real_trade_touched=false，worker_started=false。
- rollback_safe=true before downstream consumption；rollback SQL=`sql/N4_20260603_canonical_trigger_execute_rollback.sql`。
- rollback SQL hard-fails before DELETE and guards delivered/delivering outbox, inbox/checkpoint, N5 action refs, and optional N6 projection/card/queue refs.

下一步：

- 20260603 N5 canonical action execute retry 已完成并登记为 T1C.10。
- 只允许单独进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- runtime_control 不消费 N4/N5 outbox，不执行 N6，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.10. 20260603 N5 canonical action execute passed after status fix

状态：done for N5 canonical action execute 20260603 passed after status persistence fix。
目标：登记 20260603 N5 canonical action consumer run-once retry 已基于 T1C.9 matcher fix 后 N4 canonical trigger run 执行并通过 post-review；该登记不授权 runtime_control 消费 N4/N5 outbox 或执行 N6。

输入：

```text
docs/N5_20260603_CANONICAL_ACTION_EXECUTE_REPORT.md
docs/N5_20260603_canonical_action_execute_report.json
docs/N5_20260603_CANONICAL_ACTION_EXECUTE_POST_REVIEW.md
docs/N5_20260603_canonical_action_execute_post_review.json
docs/N5_20260603_CANONICAL_ACTION_EXECUTE_CONTRACT.md
docs/N5_20260603_canonical_action_execute_contract.json
docs/N5_20260603_CANONICAL_ACTION_EXECUTE_PREFLIGHT.md
docs/N5_20260603_canonical_action_execute_preflight.json
docs/N5_20260603_FAILED_RUN_ROLLBACK_REPORT.md
docs/N5_20260603_failed_run_rollback_report.json
sql/N5_20260603_canonical_action_execute_rollback.sql
```

验收标准：

- action_run_id=`action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- source N4 run=`trigger_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- common_action_run.status=passed。
- run-level P0/P1/P2=0/0/0。
- common_action_run=1。
- common_action_quality_item=8915。
- stock/index/board_action_fact=1056/26/170。
- common_action_event=1252。
- N5 common_event_outbox=1252。
- N5 consumer inbox=20334。
- N5 consumer scoped checkpoint=2474。
- event distribution：ActionBlocked=1252，ActionEligible=0，ActionExecuted=0，ActionSkipped=0。
- N5 outbox pending/delivered/delivering=1252/0/0。
- N4 outbox remains pending：TriggerMatched=1252，TriggerPendingMarketData=8915，TriggerStateChanged=10167，total pending=20334，delivered/delivering=0/0。
- N6/user refs=0。
- common_position_state/event=0/0。
- market_data_pulled=false；trigger_layer_mutated=false；user_layer_touched=false。
- voice_touched=false；sim_touched=false；real_trade_touched=false；worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260603_canonical_action_execute_rollback.sql`。
- rollback SQL hard-fails before DELETE and guards N5 outbox delivered/delivering, downstream inbox/checkpoint, non-scoped consumer refs, and user/voice/mobile/sim/position refs.
- rollback does not touch N4/N3/N2/N6 facts.

下一步：

- 只允许单独进入 N6 readiness/shadow gate、delivery/notification gate 或 runtime_control read-only lineage review。
- runtime_control 不消费 N4/N5 outbox，不执行 N6，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.11. 20260603 N5 market-action-confirmation spec v1 execute passed

状态：done / preserve-only for N5_MARKET_ACTION_CONFIRMATION_SPEC_v1 20260603 execute passed。
目标：登记 20260603 N5 v1 market-action-confirmation 已基于 N4 v4 `TriggerMatched` 与 N3 deterministic action-confirmation metric join 执行并通过 post-review；existing-run decision 已选择 preserve-only。该登记不授权 runtime_control 消费 N5 outbox、rollback N5、启动 worker 或写用户层/position/voice/mobile/sim/real trade。

输入：

```text
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_EXECUTE_REPORT.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_execute_report.json
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_POST_REVIEW.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_post_review.json
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_EXECUTE_CONTRACT.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_execute_contract.json
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_EXECUTE_PREFLIGHT.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_execute_preflight.json
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_METRIC_AWARE_DRY_RUN_PREFLIGHT_REPORT.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_metric_aware_dry_run_preflight_report.json
sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql
```

验收标准：

- source N4 run=`trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- source N3 action metric run=`action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- action_run_id=`action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- common_action_run.status=passed。
- run-level P0/P1/P2=0/0/0。
- common_action_run=1。
- common_action_quality_item=0。
- stock/index/board_action_fact=680/34/149。
- common_action_event=863。
- N5 common_event_outbox=863。
- N5 consumer inbox=863。
- N5 consumer scoped checkpoint=822。
- event distribution：ActionBlocked=863，ActionExecuted=0，ActionEligible=0，ActionSkipped=0。
- blocked_reason distribution：price_confirmation_failed=838，amount_confirmation_failed=25，metric_missing=0。
- N5 outbox pending/delivered/delivering=863/0/0。
- N4 v4 outbox unchanged：TriggerMatched pending=863，delivered/delivering=0/0。
- fresh DB proof 显示 N6/user refs 已存在：user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863。
- common_position_state/event=0/0。
- BJ quality-blocked 与 BUY:FULL/SELL:FULL blocked 未写 TriggerMatched。
- action_mark final-only proof passed；blocked action_mark non-null=0。
- market_data_pulled=false；trigger_layer_mutated=false；user_layer_touched=false。
- voice_touched=false；sim_touched=false；real_trade_touched=false；worker_started=false。
- rollback SQL=`sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql` 仍 hard-fail before DELETE；由于 N6/user refs 已存在，N5 rollback 当前不再按 downstream=0 路线，若需 rollback 必须先进入 N6 rollback gate。
- rollback SQL hard-fails before DELETE and guards N5 outbox delivered/delivering, downstream inbox/checkpoint, non-scoped consumer refs, worker/downstream flags, and user/voice/mobile/sim/position refs.
- rollback does not touch N4/N3/N2/N6 facts and does not update N4 outbox status.

下一步：

- 只允许单独进入 N6 existing-run post-review registration、N6 rollback review、delivery/notification gate 或 runtime_control read-only lineage review。
- runtime_control 不消费 N4/N5 outbox，不执行新的 N6，不 rollback N5，不启动 worker，不触发 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1C.12. 20260603 N6 shadow/user projection post-review recovery passed

状态：done for N6 20260603 existing-run post-review recovery passed。
目标：登记当前 DB 中已存在的 20260603 N6 shadow/user projection downstream refs，并确认它们是 T1C.11 N5 preserved run 的合法 downstream；post-review artifact 已补齐，但该登记不授权 delivery / notification / push / voice / mobile / sim / position / real trade。

输入：

```text
docs/N6_20260603_v1_market_action_confirmation_projection_dry_run_report.json
docs/N6_20260603_v1_market_action_confirmation_projection_contract.json
docs/N6_20260603_v1_market_action_confirmation_projection_preflight.json
docs/N6_20260603_V1_MARKET_ACTION_CONFIRMATION_PROJECTION_POST_REVIEW.md
docs/N6_20260603_v1_market_action_confirmation_projection_post_review.json
sql/N6_projection_business_rollback.sql
fresh read-only DB proof on 2026-06-04
```

验收标准：

- source_action_run_id=`action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- expected projection_run_id=`user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`。
- N6 dry-run/contract/preflight 均覆盖同一 source_action_run_id 与 planned rows。
- fresh DB proof：user_projection_run.status=passed，P0/P1/P2=0/5/2，input/output=863/863。
- fresh DB rows：user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863。
- card_status=blocked count=863。
- notification_source=n5_action_blocked / queued_only count=863。
- position refs=0/0。
- N5 outbox remains pending ActionBlocked=863；delivered/delivering=0/0。
- shadow_projection=true；n5_outbox_consumed=false；n5_outbox_status_updated=false。
- N5 outbox consumption/status update 未登记；worker/delivery/notification/push/voice/mobile/sim/position/real_trade 仍未授权。
- rollback path=`sql/N6_projection_business_rollback.sql`；如需 N5 rollback，必须先进入 N6 rollback gate。

下一步：

- 只允许 N6 delivery noop preview execute final gate、N6 rollback review 或 runtime_control read-only lineage review。

### T1C.13. 20260603 N6 delivery schema alignment migration passed

状态：done for 035 N6 delivery notification queue schema alignment migration passed。
目标：登记 `user_notification_queue` 已允许 no-op preview materialization 所需枚举，但未写 delivery materialized rows、未消费 N5 outbox、未真实投递。

输入：

```text
sql/035_n6_delivery_notification_queue_schema_alignment.sql
sql/035_n6_delivery_notification_queue_schema_alignment_rollback.sql
docs/N6_DELIVERY_SCHEMA_ALIGNMENT_MIGRATION_DRAFT.md
docs/N6_delivery_schema_alignment_migration_draft.json
fresh read-only DB proof on 2026-06-04
```

验收标准：

- target DB=`ashare_v3 / ashare_v3_user / 127.0.0.1:5432`。
- `notification_source` CHECK 已包含 `n6_delivery_materialized_noop`，既有允许值保留。
- `channel` CHECK 已包含 `in_app_notification_preview`，既有允许值保留。
- exact delivery materialization run rows=0。
- source queue remains `n5_action_blocked / queued_only / broadcast_queue = 863`。
- N5 outbox remains `ActionBlocked:pending=863`，delivered/delivering=0/0。
- decision/position refs=0/0/0，optional delivery/voice/mobile tables absent or unused。
- migration 只改 CHECK 约束，不写业务行，不重跑 N6 delivery，不消费/update N5 outbox，不启动 worker，不触发 delivery/push/voice/mobile/sim/position/real trade。
- rollback path=`sql/035_n6_delivery_notification_queue_schema_alignment_rollback.sql`；若已有 `n6_delivery_materialized_noop` / `in_app_notification_preview` rows，schema rollback 会 hard-fail，必须先回滚 delivery materialization rows。

下一步：

- subsequent T1C.14 已登记 N6 delivery noop preview materialization passed，T1C.15 已登记该 preview rows rollback passed。
- runtime_control 不消费/update N5 outbox，不启动 worker，不触发真实 delivery / push / voice / mobile / sim / position / real trade。

### T1C.14. 20260603 N6 delivery noop preview materialization passed

状态：done for N6 delivery noop preview materialization passed。
目标：登记 N6 已将 863 条 `n5_action_blocked / queued_only` shadow queue append-only 物化为本地 no-op preview rows；该登记不代表真实 delivery、push、voice、mobile、sim、position 或 real trade。

输入：

```text
docs/N6_20260603_delivery_notification_contract.json
docs/N6_20260603_delivery_notification_preflight.json
docs/N6_20260603_DELIVERY_NOTIFICATION_CONTRACT.md
docs/N6_20260603_DELIVERY_NOTIFICATION_PREFLIGHT.md
sql/N6_20260603_delivery_notification_rollback.sql
fresh read-only DB proof on 2026-06-04
```

验收标准：

- delivery_materialization_run_id=`n6_delivery_notification_materialization_20260603_v1__user_projection_shadow_20260603_v1`。
- source queue remains `n5_action_blocked / queued_only / broadcast_queue = 863`。
- target materialized rows=863。
- target distribution=`n6_delivery_materialized_noop / ready_for_future_push / in_app_notification_preview = 863`。
- title/message missing=0/0。
- trace_json SQL NULL rows=863；trace_json JSONB null rows=0。
- notification_payload_json JSONB object rows=863。
- forbidden provider-visible payload rows=0。
- delivery_materialization_run_id rows=863。
- N5 outbox remains `ActionBlocked:pending=863`；N5 outbox consumed/status_updated=false。
- N5 inbox/checkpoint scoped refs=0/0。
- common_event_delivery_attempt total/ref rows=0/0。
- user_signal_decision=0；common_position_state/event refs=0/0；sim order/trade/position refs=0/0/0。
- voice/mobile/notification delivery optional tables absent or unused；worker=false；real delivery/push/voice/mobile/sim/position/real_trade=false。
- rollback path=`sql/N6_20260603_delivery_notification_rollback.sql`；rollback hard-fails before DELETE and deletes only this delivery materialization run's preview rows.

下一步：

- subsequent T1C.15 已登记 N6 delivery noop preview rollback passed，target preview rows=0。
- 允许 runtime_control read-only dashboard / lineage review。
- 真实 delivery / push / voice / mobile / sim / position / real trade 必须另开 readiness/final gate。
- runtime_control 不消费/update N5 outbox，不启动 worker，不触发真实 delivery / push / voice / mobile / sim / position / real trade。

### T1C.15. 20260603 N6 delivery noop preview rollback passed

状态：done for N6 delivery noop preview rollback passed。
目标：登记 N6 delivery noop preview materialization 的 863 条 append-only preview rows 已撤销；N6 shadow projection / source queued_only rows 与 N5 outbox 均保留。

输入：

```text
sql/N6_20260603_delivery_notification_rollback.sql
fresh read-only DB proof on 2026-06-04
```

验收标准：

- rollback SQL notice deleted preview rows=863。
- target preview rows=0。
- source queue remains `n5_action_blocked / queued_only / broadcast_queue = 863`。
- N6 shadow rows remain user_projection_run/user_signal_projection/user_signal_card/source_queue=1/863/863/863。
- N5 outbox remains `ActionBlocked:pending=863`；N5 outbox consumed/status_updated=false。
- N5 inbox/checkpoint scoped refs=0/0。
- common_event_delivery_attempt refs=0。
- user_signal_decision=0；common_position_state/event refs=0/0；sim order/trade/position refs=0/0/0。
- voice/mobile/notification delivery optional tables absent or unused；worker=false；real delivery/push/voice/mobile/sim/position/real_trade=false。
- original `n5_action_blocked / queued_only` rows preserved=true。
- rollback_safe=true；rollback path=`sql/N6_20260603_delivery_notification_rollback.sql`。

下一步：

- subsequent T1C.16 已登记 20260603 read-only lineage closed。
- 当前 20260603 N1->N6 lineage 终点恢复为 N6 shadow projection / queued_only preserved。
- 允许 runtime_control read-only dashboard / lineage review。
- 真实 delivery / push / voice / mobile / sim / position / real trade 必须另开 readiness/final gate。
- runtime_control 不重新执行 delivery，不消费/update N5 outbox，不启动 worker，不触发真实 delivery / push / voice / mobile / sim / position / real trade。

### T1C.16. 20260603 read-only lineage closed

状态：done for 20260603 final read-only lineage dashboard closeout passed。
目标：登记 20260603 N1->N6 当前最终只读状态，确认终点为 N6 shadow projection / queued_only preserved，而不是真实 delivery。

输入：

```text
docs/Architecture.md
docs/Roadmap.md
docs/Tasks.md
docs/N3_B1_realtime_snapshot_20260603_execute_report.json
docs/N4_TRIGGER_RULE_SPEC_v4_execute_report.json
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_post_review.json
docs/N6_20260603_v1_market_action_confirmation_projection_post_review.json
fresh read-only DB proof on 2026-06-04
```

验收标准：

- N1 calendar ready：`common_trade_calendar(20260603)` is_open=true，prev/next=20260602/20260604。
- N2 run=`condition_layer_20260602_source_20260602_v1`，status=passed_active，P0/P1/P2=0/9/3。
- N3 subscription/A1/B1 passed；B1 fact-only rows stock/index/board/total=1963/83/428/2474，writes_outbox=false。
- N4 v4 run=`trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，P0/P1/P2=0/0/0，state/match/outbox=863/863/863。
- N5 v1 run=`action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，P0/P1/P2=0/0/0，ActionBlocked=863。
- N6 shadow run=`user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，P0/P1/P2=0/5/2，projection/card/source_queue/preview=863/863/863/0。
- N4 outbox remains `TriggerMatched:pending=863`。
- N5 outbox remains `ActionBlocked:pending=863`；N5 outbox consumed/updated=false。
- N6 inbox/checkpoint refs=0/0。
- common_event_delivery_attempt=0；user_signal_decision=0；position refs=0/0；sim order/trade/position=0/0/0；voice/mobile delivery tables absent。
- no worker；no real delivery/push/voice/mobile/sim/position/real_trade。
- rollback dependency order：N6 shadow projection -> N5 v1 action -> N4 v4 trigger -> N4 context -> N3 B1/A1/subscription -> N2 condition -> N1 source/calendar。

下一步：

- 20260603 read-only lineage closed；当前终点=N6 shadow projection / queued_only preserved。
- 允许 runtime_control read-only dashboard / lineage review。
- 真实 delivery / push / voice / mobile / sim / position / real trade 必须另开 readiness/final gate。

### T1C.17. 20260603 final read-only dashboard artifact

状态：done for 20260603 final read-only dashboard artifact generated。
目标：生成可供 dashboard/card 只读展示使用的 Markdown/JSON artifact，固定当前 20260603 N1->N6 闭环终点为 N6 shadow projection / queued_only preserved，并避免被误读为真实 delivery 或可执行交易动作。

Artifacts:

```text
docs/dashboard/20260603_FINAL_READ_ONLY_LINEAGE_DASHBOARD.md
docs/dashboard/20260603_final_read_only_lineage_dashboard.json
```

验收标准：

- artifact result=`DASHBOARD_ARTIFACT_PASS`。
- fresh DB proof target=`ashare_v3 / ashare_v3_user / 127.0.0.1:5432`。
- N1 calendar ready：`common_trade_calendar(20260603)` is_open=true，prev/next=20260602/20260604。
- N2 run=`condition_layer_20260602_source_20260602_v1`，status=passed_active，P0/P1/P2=0/9/3。
- N3 subscription/A1/B1 passed；B1 fact-only rows stock/index/board/total=1963/83/428/2474，writes_outbox=false。
- N4 v4 run=`trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，state/match/outbox=863/863/863。
- N5 v1 run=`action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，ActionBlocked=863，blocked_reason price_confirmation_failed/amount_confirmation_failed/metric_missing=838/25/0。
- N6 shadow run=`user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，status=passed，projection/card/source_queue/preview=863/863/863/0。
- N4 outbox remains `TriggerMatched:pending=863`。
- N5 outbox remains `ActionBlocked:pending=863`；N5 outbox consumed/updated=false。
- delivery preview target rows=0；source `n5_action_blocked / queued_only / broadcast_queue=863` preserved。
- common_event_delivery_attempt=0；user_signal_decision=0；position refs=0/0；sim order/trade/position=0/0/0。
- no worker；no real delivery/push/voice/mobile/sim/position/real_trade。

下一步：

- 允许 runtime_control read-only dashboard / lineage review。
- N6 rollback review only if explicitly requested。
- 真实 delivery / push / voice / mobile / sim / position / real trade 必须另开 readiness/final gate。

### T1C.18. 20260603 / 20260604 daily pipeline catch-up through N3-A1

状态：done for DAILY_PIPELINE_CATCHUP_20260603_20260604_GATE through N3-A1。
目标：登记 20260603、20260604 两个已收盘 source_trade_date 已完成 N1 official daily / condition source、N2 condition、N3 subscription、N3-A1 previous-day minute preload catch-up。该登记不授权进入 N4/N5/N6、不消费 outbox、不启动 worker、不做 delivery / notification / push / voice / mobile / sim / position / real trade。

Artifacts:

```text
docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_READINESS_REPORT.md
docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_READINESS_REPORT.json
docs/N1_TRADE_CALENDAR_20260604_PATCH_PREFLIGHT.md
docs/N1_trade_calendar_20260604_patch_preflight.json
docs/N1_TRADE_CALENDAR_20260604_PATCH_FINAL_GATE.md
docs/N1_trade_calendar_20260604_patch_final_gate.json
docs/N1_TRADE_CALENDAR_20260604_PATCH_POST_REVIEW.md
docs/N1_trade_calendar_20260604_patch_post_review.json
sql/N1_trade_calendar_20260604_patch_rollback.sql
docs/N1_TRADE_CALENDAR_20260605_PATCH_PREFLIGHT.md
docs/N1_trade_calendar_20260605_patch_preflight.json
docs/N1_TRADE_CALENDAR_20260605_PATCH_FINAL_GATE.md
docs/N1_trade_calendar_20260605_patch_final_gate.json
docs/N1_TRADE_CALENDAR_20260605_PATCH_POST_REVIEW.md
docs/N1_trade_calendar_20260605_patch_post_review.json
docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_ORCHESTRATOR_REPORT.md
docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_ORCHESTRATOR_REPORT.json
sql/N1_trade_calendar_20260605_patch_rollback.sql
sql/N1_daily_catchup_20260603_rollback.sql
sql/N1_daily_catchup_20260604_rollback.sql
sql/N2_condition_layer_20260603_rollback.sql
sql/N2_condition_layer_20260604_rollback.sql
sql/N3_subscription_20260604_rollback.sql
sql/N3_subscription_20260605_rollback.sql
sql/N3_A1_previous_day_minute_20260604_rollback.sql
sql/N3_A1_previous_day_minute_20260605_rollback.sql
```

收口结论：

- 本次 catch-up 目标不是已 closeout 的 `20260602 -> 20260603` runtime lineage，而是新增：
  - `source_trade_date=20260603 -> for_trade_date=20260604`
  - `source_trade_date=20260604 -> for_trade_date=20260605`
- fresh DB proof：
  - `common_trade_calendar(20260603)` exists and is_open=true，prev/next=20260602/20260604。
  - `common_trade_calendar(20260604)` POST_REVIEW_PASS by user-provided DB proof：calendar/active/batch=1/1/1，quality=11，P0/P1/P2=0/0/0。
  - `common_trade_calendar(20260605)` POST_REVIEW_PASS：calendar/active/batch=1/1/1，quality=11，P0/P1/P2=0/0/0。
- N1 official daily / condition source：
  - 20260603 rows stock/index/board daily=5511/9/428，stock_daily_basic=5511，stock_financial=5511，index/board membership=12841/56960，batch_count=10，quality P0/P1/P2=0/0/0。
  - 20260604 rows stock/index/board daily=5511/9/428，stock_daily_basic=5511，stock_financial=5511，index/board membership=12841/56960，batch_count=10，quality P0/P1/P2=0/0/0。
- N2 condition:
  - 20260603 -> 20260604 run=`condition_layer_20260603_source_20260603_v1`，status=passed_active，P0/P1/P2=0/6/3，basis=5511/9/428，pool=4222/20/892，scope=4201/20/892，display=1960/9/428。
  - 20260604 -> 20260605 run=`condition_layer_20260604_source_20260604_v1`，status=passed_active，P0/P1/P2=0/6/3，basis=5511/9/428，pool=4207/20/912，scope=4186/20/912，display=1952/9/428。
- N3 subscription:
  - 20260604 run=`market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1`，status=passed，P0/P1/P2=0/0/0，source_scope/candidate/subscription/pull_plan=5113/5757/3041/9，market_data_pulled=false，market_data_fact_written=false，outbox=0。
  - 20260605 run=`market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，P0/P1/P2=0/0/0，source_scope/candidate/subscription/pull_plan=5118/5802/3073/9，market_data_pulled=false，market_data_fact_written=false，outbox=0。
- N3-A1 previous-day minute preload:
  - 20260604 preload=`previous_day_minute_preload_20260603_for_20260604__market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1`，status=passed，P0/P1/P2=0/0/0，minute/status stock=68160/284，index=480/2，board=8640/36，总计=77280/322，outbox=0。
  - 20260605 preload=`previous_day_minute_preload_20260604_for_20260605__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，P0/P1/P2=0/0/0，minute/status stock=68160/284，index=480/2，board=13440/56，总计=82080/342，outbox=0。
- N3 staged refresh for 20260605:
  - B1 live2=`realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，rows stock/index/board/total=1952/9/428/2389，quality rows=11，P0/P1/P2=0/0/0，writes_outbox=false，generated_outbox_events=[]，rollback_safe=true，rollback=`sql/N3_B1_realtime_snapshot_20260605_live2_rollback.sql`。
  - C1 current-minute=`today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，latest_closed_minute=2026-06-05T10:37:00+08:00，rows stock/index/board/total=19028/134/3752/22914，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups stock/index/board=0/0/0，rollback_safe=true，rollback=`sql/N3_C1_today_minute_bar_1m_20260605_until_1037_rollback.sql`。
  - C1 later-minute=`today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，latest_closed_minute=2026-06-05T11:27:00+08:00，rows stock/index/board/total=33228/234/6552/40014，objects processed/passed=342/342，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups stock/index/board=0/0/0，rollback_safe=true，rollback=`sql/N3_C1_today_minute_bar_1m_20260605_until_1127_rollback.sql`。
  - B2 stock/index lineage expansion control-row run=`market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，status=passed，candidate/subscription/pull_plan=6696/3350/4，quality rows=15，P0/P1/P2=0/2/0，P1 residuals=stock/index completion-only not_ready 136/2 与 board 14:59 quality-visible not_ready 428，market_data_pulled=false，market_data_fact_written=false，rollback_safe=true，rollback=`sql/N3_B2_stock_index_lineage_expansion_20260605_rollback.sql`。
  - A1 expansion=`previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，status=passed，minute rows stock/index/board/total=400320/1680/0/402000，preload status rows stock/index/board/total=1668/7/0/1675，quality rows=12，P0/P1/P2=0/1/0，P1=carried non-blocking warning，duplicate minute key groups=0/0/0，rollback_safe=true，rollback=`sql/N3_A1_previous_day_minute_20260605_b2_stock_index_lineage_expansion_rollback.sql`。
  - C1 expansion=`today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`，status=passed，latest_closed_minute=2026-06-05T11:27:00+08:00，minute rows stock/index/board/total=195156/819/0/195975，quality rows=8，P0/P1/P2=0/0/0，duplicate minute key groups=0/0/0，rollback_safe=true，rollback=`sql/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_rollback.sql`。
	  - B2 realtime projection=`realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，rows stock/index/board/total=1952/9/428/2389，ready/not_ready=969/1420，ready_by_asset=stock 969，not_ready_by_asset stock/index/board=983/9/428，quality rows=7，P0/P1/P2=0/4/0，fact-only trace compatible rows=2389，snapshot_event_id empty rows=2389，required fact trace complete rows=2389，writes_outbox=false，rollback_safe=true，rollback=`sql/N3_B2_realtime_projection_20260605_live2_compat_rollback.sql`。
	  - B1/C1 current/later/expansion/B2 scoped outbox/inbox/checkpoint refs=0/0/0，B2 enrichment refs=0，N4 trigger_state/match refs=0/0，N5/N6 refs=0/0，downstream_layers_touched=false，worker_started=false。
- N4 matched-only execute for 20260605:
  - execute_run_id=`trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`，status=passed，run row P0/P1/P2=0/0/0。
  - common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=4/1537/1537/1537；quality table 4 rows all P0 passed。
  - TriggerMatched=1537，TriggerPendingMarketData/TriggerStateChanged=0/0；signal_type B_BUY/S_SELL=1286/251；trigger_mark_candidate normal/30m_volume/30m_shrink=1262/87/188。
  - outbox pending/delivered/delivering=1537/0/0；invalid N5 entry=0，deprecated runtime signal count=0。
  - common_event_inbox/checkpoint refs=0/0，N5 action_run/action_event refs=0/0，N6 refs=0，worker_started=false，action/user/voice/sim/real_trade touched=false，rollback_safe=true，rollback=`sql/N4_20260605_execute_rollback.sql`。
- source readiness passed：Tushare token autoload present, token plaintext not printed, TDX txt present, `tushare`/`mootdx`/`psycopg` importable。
- boundary proof：scoped outbox/inbox refs=0/0，N4/N5/N6 refs=0/0/0，worker_started=false，delivery/notification/push/voice/mobile/sim/position/real_trade=false。
- N6 Phase 3 admin virtual account seed:
  - seed_run_id=`n6_phase3_virtual_account_seed_20260605_v1`，result=EXECUTED，post-review=passed。
  - n6_virtual_account/n6_virtual_cash_ledger/n6_virtual_cash_snapshot=1/1/1；n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0。
  - virtual_account_id=1，principal_id=1，principal_type=admin，login_name=admin，account_name=`Admin Virtual Account`，virtual_account_status=active，base_currency=CNY，initial_cash=1000000.0000，quality_status=passed。
  - initial cash ledger/snapshot linked：ledger_type=initial_deposit，amount=1000000.0000，available/frozen/total=1000000.0000/0.0000/1000000.0000，source_ledger_max_id=1，current_cash_snapshot_id=1，pointer_matches=true。
  - outbox/inbox/checkpoint/delivery_attempt refs=0/0/0/0，user_projection/signal/card/queue refs=0/0/0/0，user_sim_account 既有 3 行但无本次 seed linkage，user_sim_order/trade/position=0/0/0，worker/delivery/push/voice/mobile/sim/position/real_trade=false，rollback_safe=true，rollback=`sql/N6_phase3_virtual_account_seed_rollback.sql`。

下一步：

- 允许进入 20260605 N5 action readiness / dry-run gate；N5 execute、N5 outbox consumption、N5/N6 execute、worker 必须单独进入，本登记不自动授权。
- N6 侧允许进入 Phase 3 virtual account operation policy / virtual order proposal design gate；不得直接进入 sim/position/real trade。

禁止事项：

- 不从 runtime_control 直接进入 N5/N6 execute。
- 不消费/update N4/N5 outbox。
- 不启动 worker。
- 不 delivery / notification / push / voice / mobile / sim / position / real trade。

### T1D. 20260528 -> 20260529 N2 condition layer passed

状态：done for N2 condition v1 execute passed；subsequently superseded by T1P N2 canonical condition v2 active lineage。
目标：登记 20260528 -> 20260529 N2 条件层 v1 run；该 run 已被 v2 supersede，但 rows and downstream refs preserved，仍作为既有 N3/N4/N5/N6 旧 lineage 证据。

输入：

```text
docs/N2_condition_layer_20260528_execute_report.json
docs/N2_condition_layer_20260528_execute_post_review.json
docs/N2_CONDITION_LAYER_20260528_EXECUTE_POST_REVIEW.md
docs/N2_condition_layer_20260528_final_gate_preflight.json
docs/N2_condition_layer_20260528_final_gate_audit.json
sql/N2_condition_layer_20260528_rollback.sql
```

输出：

```text
N2 previous active condition run = condition_layer_20260528_source_20260528_v1
superseded by = condition_layer_20260528_source_20260528_v2
N2 execute status = passed_active
N2 row counts and quality summary
N2 canonical signal audit and side-effect boundary
N2 rollback safety
N3 subscription 20260529 next gate
```

验收标准：

- run_id=`condition_layer_20260528_source_20260528_v1`。
- status=`superseded` after v2 active lineage passed；v1 rows and downstream refs preserved。
- source_trade_date=20260528，for_trade_date=20260529，prev_trade_date=20260528。
- P0/P1/P2=0/6/3，common_condition_quality_item=106。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4271/18/263。
- minute_target_scope stock/index/board=4271/18/263。
- monitor_target stock/index/board=5506/83/428。
- condition_display_basis stock/index/board=5506/83/428。
- canonical_signal_audit_passed=true，deprecated_signal_rows=0，noncanonical_signal_rows=0。
- outbox/inbox/checkpoint delta=0/0/0。
- market_data_pulled=false，N3/N4/N5/N6 entered=false，worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_rollback.sql`。

禁止事项：

- 不进入 N3 execute。
- 不拉行情。
- 不写 outbox/inbox/checkpoint。
- 不启动 worker。
- 不进入 N4/N5/N6。

下一步：

- N3 subscription 20260529 execute 已完成并登记为 T1E on v1 lineage。
- 20260529 A1 previous_day_minute preload 已完成并登记为 T1F。
- 20260529 B1 pre-open realtime snapshot fact-only 已完成并登记为 T1G。
- 20260529 B1 live1 realtime snapshot fact-only 已完成并登记为 T1H。
- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续 v2 lineage 只允许 N3_market_data subscription rebuild gate；既有 v1 downstream lineage 不自动 rebuild。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1E. 20260529 N3 subscription passed

状态：done for N3 subscription execute passed；20260529 A1 previous_day_minute preload、B1 pre-open、B1 live1 realtime snapshot fact-only、N4 canonical trigger execute、N5 canonical action execute、N6 canonical shadow projection、B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute、N5 live2 canonical action execute 已完成，N6 live2 / full-day user projection gate allowed next。
目标：登记 20260529 N3 subscription control rows，作为 A1 previous_day_minute preload gate 的上游锚点。

输入：

```text
docs/N3_subscription_20260529_execute_report.json
docs/N3_subscription_20260529_execute_preflight.json
docs/N3_subscription_20260529_execute_contract.json
docs/N3_subscription_20260529_dry_run_report.json
sql/N3_subscription_20260529_rollback.sql
```

输出：

```text
N3 market_data_run_id = market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
source_condition_run_id = condition_layer_20260528_source_20260528_v1
N3 subscription row counts
required_data_kind distribution
canonical signal audit and side-effect boundary
N3 rollback safety
20260529 A1 previous_day_minute preload next gate
```

验收标准：

- market_data_run_id=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- source_condition_run_id=`condition_layer_20260528_source_20260528_v1`。
- common_market_data_run.status=`passed`。
- source_trade_date=20260528，for_trade_date=20260529，prev_trade_date=20260528。
- P0/P1/P2=0/0/0，quality rows=34。
- candidate rows=5038，subscription rows=2643，pull_plan rows=7。
- objects stock/index/board/total=2021/9/127/2157。
- required_data_kind realtime_daily_snapshot=2157，minute_bar_1m=243，previous_day_minute_bar_1m=243。
- canonical signals=BUY, BUY:FULL, SELL, SELL:FULL, BUY_HINT, SELL_HINT。
- deprecated_signal_rows=0。
- market_data_pulled=false，market_data_fact_written=false，downstream_layers_touched=false，worker_started=false。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- rollback_safe=true；rollback SQL=`sql/N3_subscription_20260529_rollback.sql`。

禁止事项：

- 不进入 B1 execute。
- 不拉行情。
- 不写 snapshot/outbox/inbox/checkpoint。
- 不进入 N4/N5/N6。
- 不消费 outbox。
- 不启动 worker。

下一步：

- 20260529 A1 previous_day_minute preload 已完成并登记为 T1F。
- 20260529 B1 pre-open realtime snapshot fact-only 已完成并登记为 T1G。
- 20260529 B1 live1 realtime snapshot fact-only 已完成并登记为 T1H。
- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1F. 20260529 A1 previous_day_minute preload passed

状态：done for A1 previous_day_minute preload passed；20260529 B1 pre-open、B1 live1 realtime snapshot fact-only、N4 canonical trigger execute、N5 canonical action execute、N6 canonical shadow projection、B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute、N5 live2 canonical action execute 已完成，N6 live2 / full-day user projection gate allowed next。
目标：登记 20260529 A1 previous_day_minute preload 结果，作为 B1 realtime snapshot fact-only gate 的上游锚点。

输入：

```text
docs/N3_A1_previous_day_minute_preload_execute_report.json
sql/N3_A1_previous_day_minute_20260529_rollback.sql
```

输出：

```text
A1 preload_run_id
source subscription run
actual previous-day minute rows
object status summary
event/outbox/inbox/checkpoint boundary
rollback safety
20260529 B1 pre-open realtime snapshot fact-only next gate
```

验收标准：

- preload_run_id=`previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- common_market_data_run.status=`passed`。
- actual rows stock/index/board/total=56160/0/2160/58320。
- stock object status passed/partial/missing=234/0/0。
- index expected objects=0，rows=0。
- board object status passed/partial/missing=9/0/0。
- fake index pull / fake index rows=0/0。
- P0/P1/P2=0/0/0，quality rows=12。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- event_outbox_written=false。
- downstream_layers_touched=false。
- worker_started=false。
- old_system_touched=false。
- rollback_safe=true；rollback SQL=`sql/N3_A1_previous_day_minute_20260529_rollback.sql`。

禁止事项：

- 不进入 B1 execute。
- 不拉行情。
- 不写 snapshot/outbox/inbox/checkpoint。
- 不进入 N4/N5/N6。
- 不启动 worker。

下一步：

- 20260529 B1 pre-open realtime snapshot fact-only 已完成并登记为 T1G。
- 20260529 B1 live1 realtime snapshot fact-only 已完成并登记为 T1H。
- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1G. 20260529 B1 pre-open realtime snapshot fact-only passed

状态：done for B1 pre-open realtime snapshot fact-only passed；subsequent live1 已登记为 T1H。
目标：登记 20260529 B1 pre-open realtime snapshot fact-only 结果；该上游锚点已被后续 T1H live1 记录接续。

输入：

```text
docs/N3_B1_realtime_daily_snapshot_execute_report.json
docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_REPORT.md
sql/N3_B1_realtime_snapshot_20260529_rollback.sql
```

输出：

```text
B1 snapshot_run_id
pre-open fact-only status
snapshot row counts
source time warning summary
outbox/inbox/checkpoint boundary
rollback safety
subsequent live1 registration
```

验收标准：

- snapshot_run_id=`realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- common_market_data_run.status=`passed`。
- pre_open_fact_only=true。
- live_trading_snapshot_ready=false。
- rows stock/index/board/total=2021/9/127/2157。
- missing/failed=0/0。
- P0/P1/P2=0/1/0，quality rows=11。
- writes_outbox=false，generated_outbox_events=[]。
- source_time_missing_or_preopen stock/index/total=2021/9/2030。
- source_time_confirmed board=127。
- P1 warning=`n3_b1_pre_open_source_time_not_confirmed`。
- P0 source date mismatch=0。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- downstream_layers_touched=false。
- worker_started=false。
- N4/N5/N6 touched=false。
- rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_rollback.sql`。

禁止事项：

- 不进入 N4/N5/N6。
- 不消费 outbox。
- 不启动 worker。
- 不写用户层、语音、mobile、sim、position 或真实交易。

下一步：

- 20260529 B1 live1 realtime snapshot fact-only 已完成并登记为 T1H。
- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1H. 20260529 B1 live1 realtime snapshot fact-only passed

状态：done for B1 live1 realtime snapshot fact-only passed；subsequent N4 canonical trigger execute 已登记为 T1I。
目标：登记 20260529 B1 live1 realtime snapshot fact-only 结果，作为 N4 trigger 输入锚点；同时保留 pre-open B1 记录。

输入：

```text
sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql
pre-open snapshot_run_id = realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

输出：

```text
B1 live1 snapshot_run_id
live trading snapshot readiness
pre-open B1 preservation proof
snapshot row counts
source-time summary
outbox/inbox/checkpoint boundary
rollback safety
subsequent N4 canonical trigger registration
```

验收标准：

- live1 snapshot_run_id=`realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- common_market_data_run.status=`passed`。
- live_trading_snapshot_ready=true。
- pre_open_fact_only=false。
- pre-open snapshot_run_id=`realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1` 保留，pre_open_fact_only=true，live_trading_snapshot_ready=false。
- rows stock/index/board/total=2021/9/127/2157。
- missing/failed=0/0。
- P0/P1/P2=0/0/0，quality rows=11。
- writes_outbox=false，generated_outbox_events=[]。
- stock source-time effective_quote_present/source_time_missing/partial_quality=2021/2021/0。
- index source-time effective_quote_present/source_time_missing/partial_quality=9/9/0。
- board source_time_confirmed/effective_quote_present=127/127。
- scoped outbox/inbox/checkpoint refs=0/0/0。
- global outbox/inbox/checkpoint=105122/20726/4345。
- downstream_layers_touched=false。
- worker_started=false。
- N4/N5/N6 untouched=true。
- rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql`。

禁止事项：

- 不进入 N4/N5/N6。
- 不消费 outbox。
- 不启动 worker。
- 不写用户层、语音、mobile、sim、position 或真实交易。

下一步：

- 20260529 N4 canonical trigger execute 已完成并登记为 T1I。
- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1I. 20260529 N4 canonical trigger execute passed

状态：done for N4 canonical trigger execute passed；subsequent N5 canonical action execute 已登记为 T1J。
目标：登记 20260529 N4 canonical trigger execute 结果，作为后续 N5 canonical action execute 的上游锚点。

输入：

```text
docs/N4_20260529_canonical_trigger_execute_contract.json
docs/N4_20260529_CANONICAL_TRIGGER_EXECUTE_CONTRACT.md
docs/N4_20260529_canonical_trigger_execute_preflight.json
docs/N4_20260529_CANONICAL_TRIGGER_EXECUTE_PREFLIGHT.md
sql/N4_20260529_canonical_trigger_execute_rollback.sql
```

输出：

```text
N4 execute_run_id
N4 trigger state/match/outbox row counts
N4 canonical runtime signal checks
N4 outbox pending counts
N5 refs proof
rollback safety
subsequent N5 canonical action execute proof
```

验收标准：

- execute_run_id=`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- common_trigger_run.status=`passed`。
- P0/P1/P2=0/1/0。
- common_trigger_run=1。
- common_trigger_quality_item=16。
- common_trigger_state=8861。
- common_trigger_match=8861。
- common_event_outbox=17722。
- TriggerMatched=4309 pending。
- TriggerPendingMarketData=4552 pending。
- TriggerStateChanged=8861 pending。
- delivered/delivering=0/0。
- common_trigger_match TriggerStateChanged=0。
- pending_market_data trigger_live=false=4552。
- matched trigger_live=true=4309。
- runtime signal B_BUY=4467，S_SELL=4394。
- deprecated runtime signal count=0。
- action_mark payload count=0。
- trigger_mark_candidate missing count=0。
- scoped inbox/checkpoint refs=0/0。
- N5 refs common_action_run/common_action_event=0/0。
- global delta outbox/inbox/checkpoint=+17722/0/0。
- outbox_consumed=false。
- N5/N6 touched=false。
- worker_started=false。
- user/voice/mobile/sim/position/real_trade=false。
- N2/N3 facts unchanged=true。
- rollback_safe=true；rollback SQL=`sql/N4_20260529_canonical_trigger_execute_rollback.sql`。

禁止事项：

- 不进入 N5/N6。
- 不消费 outbox。
- 不启动 worker。
- 不写用户层、语音、mobile、sim、position 或真实交易。

下一步：

- 20260529 N5 canonical action execute 已完成并登记为 T1J。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1J. 20260529 N5 canonical action execute passed

状态：done for N5 canonical action execute passed；subsequent N6 canonical shadow projection 已登记为 T1K。
目标：登记 20260529 N5 canonical action execute 结果，作为后续 N6 canonical shadow projection 的上游锚点。

输入：

```text
docs/N5_20260529_canonical_action_execute_report.json
docs/N5_20260529_CANONICAL_ACTION_EXECUTE_REPORT.md
sql/N5_20260529_canonical_action_execute_rollback.sql
```

输出：

```text
N5 action_run_id
source N4 run id
N5 action fact/event/outbox row counts
N5 canonical event distribution
N4 outbox unchanged proof
N6/position/worker/user boundary proof
rollback safety
subsequent N6 canonical shadow projection proof
```

验收标准：

- action_run_id=`action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- source N4 run=`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- common_action_run.status=`passed`。
- P0/P1/P2=0/0/0。
- execute_report=`docs/N5_20260529_canonical_action_execute_report.json`。
- common_action_quality_item=4552。
- stock_action_fact=4037。
- index_action_fact=18。
- board_action_fact=254。
- common_action_event=4309。
- common_event_outbox=4309。
- common_event_inbox=17722。
- common_event_consumer_checkpoint=2157。
- ActionBlocked=4309。
- ActionEligible=0。
- ActionExecuted=0。
- ActionSkipped=0。
- legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0。
- N5 outbox pending=4309。
- delivered/delivering=0/0。
- N4 outbox status unchanged：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending。
- N6 refs=0。
- position rows for this run=0。
- worker_started=false。
- N6 not entered=true。
- voice/mobile/sim/real_trade=false。
- old_system_touched=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260529_canonical_action_execute_rollback.sql`。

禁止事项：

- 不进入 N6 execute。
- 不消费 N5 outbox。
- 不启动 worker。
- 不写 voice/mobile/sim/position/real trade。
- 不触碰旧系统。

下一步：

- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- runtime_control 不消费 N3/N4/N5 outbox、不更新 N5 outbox status、不启动 worker。

### T1K. 20260529 N6 canonical shadow projection passed

状态：done for N6 canonical shadow projection passed；B1 live2 standard outbox snapshot、N4 live2 canonical trigger execute、N5 live2 canonical action execute 已完成，N6 live2 / full-day user projection gate allowed next。
目标：登记 20260529 N6 canonical shadow projection 结果，确认 20260529 run-once 链路已完成到 N6 shadow。

输入：

```text
docs/N6_CANONICAL_PROJECTION_EXECUTE_CONTRACT.md
docs/N6_CANONICAL_PROJECTION_EXECUTE_PREFLIGHT.md
sql/N6_projection_business_rollback.sql
```

输出：

```text
N6 projection_run_id
source_action_run_id
N6 projection/card/notification row counts
projection policy and queued-only proof
N5 outbox unchanged proof
decision/watchlist/sim/position/real-trade boundary proof
rollback safety
allowed follow-up gates
```

验收标准：

- projection_run_id=`user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- source_action_run_id=`action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- run status=`passed`。
- P0/P1/P2=0/5/2。
- user_projection_run=1。
- user_signal_projection=4309。
- user_signal_card=4309。
- user_notification_queue=4309。
- notification_source=`n5_action_blocked`。
- queue_status=`queued_only`。
- notification queued_only=4309。
- card mapping blocked / blocked / ActionBlocked / blocked = 4309。
- projection_policy=`blocked_unconfirmed_no_push_no_decision_no_sim_no_trade`。
- trace_json_nonnull=4309。
- source_action_event_type=`ActionBlocked`。
- action_state=`blocked`。
- N5 outbox unchanged：ActionBlocked pending=4309，delivered/delivering=0/0。
- n5_outbox_consumed=false。
- updates_n5_outbox_status=false。
- user_signal_decision=0。
- user_watchlist=0。
- user_watchlist_item=0。
- user_sim_order/trade/position=0。
- linked decision/sim refs=0。
- worker_started=false。
- push/voice/mobile=false。
- position/real_trade=false。
- N1-N5 unchanged=true。
- rollback_safe=true；rollback SQL=`sql/N6_projection_business_rollback.sql`。

禁止事项：

- 不启动 worker。
- 不 push/voice/mobile。
- 不写 sim/position/real trade。
- 不消费 N5 outbox。
- 不更新 N5 outbox status。

下一步：

- 允许进入 20260529 N6 live2 / full-day user projection gate。
- 允许进入 N6 shadow projection post-review。
- 仅在需要回滚时允许进入 N6 projection business rollback review。
- 允许 runtime_control read-only dashboard / lineage review。

### T1L. 20260529 B1 live2 standard outbox snapshot passed

状态：done for B1 live2 standard outbox snapshot passed；subsequent N4 live2 canonical trigger execute 已登记为 T1M。
目标：登记 20260529 B1 live2 standard outbox snapshot 结果，作为后续 N4 live2 canonical trigger execute 的 N3 standard `MarketSnapshotUpdated` 输入锚点。

输入：

```text
docs/N3_B1_realtime_snapshot_20260529_live2_outbox_execute_contract.json
docs/N3_B1_realtime_snapshot_20260529_live2_outbox_execute_preflight.json
sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql
```

输出：

```text
B1 live2 snapshot_run_id
snapshot row counts
MarketSnapshotUpdated pending counts
scoped exception proof
outbox/inbox/checkpoint boundary
rollback safety
N4 live2 execute proof
```

验收标准：

- snapshot_run_id=`realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- common_market_data_run.status=`passed`。
- rows stock/index/board/total=2021/9/127/2157。
- P0/P1/P2=0/0/0。
- writes_outbox=true。
- MarketSnapshotUpdated outbox=2157 pending。
- MarketDataDelayed=0。
- MarketDataMissing=0。
- MarketDisplaySnapshotUpdated=0。
- delivered/delivering=0/0。
- scoped inbox/checkpoint refs=0/0。
- wrote only snapshot facts/common_market_data_run/common_market_data_quality_item/common_event_outbox。
- no inbox/checkpoint writes=true。
- downstream_layers_touched=false。
- worker_started=false。
- N4/N5/N6 not entered=true。
- scoped exception was used for existing N6 web app / old system process, but they did not consume v3 outbox。
- rollback_safe=true；rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql`。

禁止事项：

- 不进入 N4/N5/N6 execute。
- 不消费 outbox。
- 不启动 worker。
- 不写 push/voice/mobile。
- 不写 sim/position/real trade。

下一步：

- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 允许进入 20260529 N6 live2 / full-day user projection gate。
- runtime_control 只允许继续 read-only dashboard / lineage review。

### T1M. 20260529 N4 live2 canonical trigger execute passed

状态：done for N4 live2 canonical trigger execute passed；subsequent N5 live2 canonical action execute 已登记为 T1N。
目标：登记 20260529 N4 live2 canonical trigger execute 结果，作为后续 N5 live2 canonical action execute 的上游锚点。

输入：

```text
N3 live2 source snapshot_run_id = realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql
```

输出：

```text
N4 live2 execute_run_id
N4 live2 trigger state/match/outbox row counts
N4 live2 canonical runtime signal checks
N4 live2 outbox pending counts
N3 live2 input proof
N5/downstream refs proof
rollback safety
subsequent N5 live2 canonical action execute proof
```

验收标准：

- execute_run_id=`trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- common_trigger_run.status=`passed`。
- P0/P1/P2=0/1/0。
- common_trigger_quality_item=17。
- common_trigger_state=8861。
- common_trigger_match=8861。
- common_event_outbox=17722。
- TriggerMatched=4309 pending。
- TriggerPendingMarketData=4552 pending。
- TriggerStateChanged=8861 pending。
- delivered/delivering=0/0。
- runtime signal_type B_BUY=4467，S_SELL=4394。
- deprecated runtime signal count=0。
- action_mark payload count=0。
- trigger_mark_candidate missing=0。
- matched trigger_live=true=4309。
- pending_market_data trigger_live=false=4552。
- common_trigger_match 中 TriggerStateChanged=0。
- N3 live2 input MarketSnapshotUpdated pending=2157。
- N3 input inbox/checkpoint refs=0/0。
- N5 refs=0。
- downstream inbox/checkpoint refs=0/0。
- global outbox delta=+17722，inbox/checkpoint delta=0/0。
- worker_started=false。
- action/user/voice/mobile/sim/position/real_trade touched=false。
- rollback_safe=true；rollback SQL=`sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql`。

禁止事项：

- 不消费 N4 outbox。
- 不进入 N5 execute。
- 不启动 worker。
- 不写 action/user/voice/mobile/sim/position/real trade。

下一步：

- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 允许进入 20260529 N6 live2 / full-day user projection gate。
- runtime_control 不消费 N4/N5 outbox、不进入 N6 execute、不启动 worker。

### T1N. 20260529 N5 live2 canonical action execute passed

状态：done for N5 live2 canonical action execute passed；20260529 N6 live2 / full-day user projection gate allowed next。
目标：登记 20260529 N5 live2 canonical action execute 结果，作为后续 N6 live2 / full-day user projection gate 的上游锚点。

输入：

```text
source N4 live2 run = trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
sql/N5_20260529_live2_canonical_action_execute_rollback.sql
```

输出：

```text
N5 live2 action_run_id
N5 live2 action fact/event/outbox row counts
N5 live2 canonical event distribution
N4 live2 outbox unchanged proof
N6/position/worker/user boundary proof
rollback safety
N6 live2 / full-day projection next gate
```

验收标准：

- action_run_id=`action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- common_action_run.status=`passed`。
- P0/P1/P2=0/0/0。
- common_action_quality_item=4552。
- stock_action_fact=4037。
- index_action_fact=18。
- board_action_fact=254。
- common_action_event=4309。
- common_event_outbox=4309。
- common_event_inbox=17722。
- common_event_consumer_checkpoint=2157。
- ActionBlocked=4309 pending。
- ActionEligible=0。
- ActionExecuted=0。
- ActionSkipped=0。
- legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0。
- delivered/delivering=0/0。
- N4 outbox status unchanged：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending。
- N6 refs=0。
- position rows=0。
- worker_started=false。
- voice/mobile/sim/position/real_trade=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260529_live2_canonical_action_execute_rollback.sql`。

禁止事项：

- 不消费 N5 outbox。
- 不进入 N6 execute。
- 不启动 worker。
- 不写 voice/mobile/sim/position/real trade。

下一步：

- 允许进入 20260529 N6 live2 / full-day user projection gate。
- runtime_control 不消费 N5 outbox、不进入 N6 execute、不启动 worker。

### T1O. 027 N2 symmetry target price canonical compatibility migration passed

状态：done for 027 N2 symmetry target price canonical compatibility migration passed；N2 canonical writer/readiness alignment gate allowed next。
目标：登记 027 schema migration 已完成，仅新增 N2 canonical compatibility nullable 字段与 CHECK 约束，不执行 N2 writer、不 backfill、不进入下游。

输入：

```text
sql/027_condition_symmetry_target_price_compatibility_migration.sql
sql/027_condition_symmetry_target_price_compatibility_rollback.sql
docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md
```

输出：

```text
027 migration passed status
12 N2 tables touched
new canonical fields existence proof
CHECK constraints validation proof
side-effect boundary proof
rollback safety
N2 canonical writer/readiness alignment next gate
```

验收标准：

- migration=`027_condition_symmetry_target_price_compatibility_migration.sql`。
- touched tables=12 N2 tables：stock/index/board condition_basis、condition_pool、minute_target_scope、condition_display_basis。
- new canonical fields exist=true。
- CHECK constraints validated=true。
- locked_target_price / target_lock_status absent=true。
- business row count delta=0。
- outbox/inbox/checkpoint delta=0/0/0。
- new fields non-null count=0。
- rollback_safe=true。
- rollback SQL=`sql/027_condition_symmetry_target_price_compatibility_rollback.sql`。

禁止事项：

- 不执行 N2 writer。
- 不 backfill。
- 不进入 N3/N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 允许进入 N2 canonical writer/readiness alignment gate。
- runtime_control 仅登记状态，不执行 writer、不写业务行、不消费 outbox。

### T1P. N2 canonical condition v2 active lineage supersede execute passed

状态：done for N2 canonical condition v2 active lineage supersede execute passed；后续已被 T1Q v3 active lineage supersede。
目标：登记 N2 v2 成为新的 active condition lineage，并明确 v1 rows/downstream refs preserved，N3/N4/N5/N6 不自动 rebuild。

输入：

```text
new active run_id = condition_layer_20260528_source_20260528_v2
previous active v1 = condition_layer_20260528_source_20260528_v1
sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql
```

输出：

```text
N2 v2 active lineage status
v1 supersede status and preserved downstream refs
row counts and quality summary
canonical target checks
side-effect boundary proof
rollback safety
N3 subscription rebuild next gate
```

验收标准：

- new active run_id=`condition_layer_20260528_source_20260528_v2`。
- v2.status=`passed_active`。
- previous active v1=`condition_layer_20260528_source_20260528_v1`。
- v1.status=`superseded`。
- v1 rows and downstream refs preserved=true。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4271/18/263。
- minute_target_scope stock/index/board=4271/18/263。
- condition_display_basis stock/index/board=5506/83/428。
- monitor_target stock/index/board=5506/83/428。
- quality_item=103。
- P0/P1/P2=0/3/3。
- alias mismatch=0。
- negative numeric fields=0。
- forbidden fields=0。
- first failed attempt rolled back due negative reference_target_price CHECK。
- writer fixed：negative canonical target numeric fields write NULL，raw negative value preserved only in trace。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- outbox/inbox/checkpoint delta=0/0/0。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 历史 next gate 曾允许 N3_market_data subscription rebuild gate for `condition_layer_20260528_source_20260528_v2`。
- 当前 next gate 已由 T1Q2 改为 N3_market_data subscription rebuild gate for `condition_layer_20260528_source_20260528_v5`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1Q. N2 display scope alignment v3 preserved / superseded

状态：done for N2 display scope alignment v3 historical run；后续已被 N2 symmetry target price alignment v5 active supersede。
目标：保留 N2 v3 审计证据，并明确 v3 已不再是 20260528 source-date active condition lineage。

输入：

```text
active N2 run = condition_layer_20260528_source_20260528_v3
previous N2 run = condition_layer_20260528_source_20260528_v2
sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql
```

输出：

```text
N2 v3 active lineage status
v2 supersede status
display scope row counts
alignment checks
side-effect boundary proof
rollback safety
N3 subscription rebuild next gate
```

验收标准：

- active N2 run=`condition_layer_20260528_source_20260528_v3`。
- v3.status=`superseded by condition_layer_20260528_source_20260528_v5`。
- previous N2 run=`condition_layer_20260528_source_20260528_v2`。
- v2.status=`superseded`。
- v1 downstream lineage preserved=true。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4271/18/263。
- minute_target_scope stock/index/board=4271/18/263。
- condition_display_basis stock/index/board=2021/9/127。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=103。
- P0/P1/P2 failed=0/0/0。
- display duplicate groups=0/0/0。
- alias mismatch=0。
- negative numeric rows=0。
- locked_target_price / target_lock_status absent=true。
- downstream refs=0。
- outbox/inbox v3 refs=0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 当前 20260528 source-date active run 已由 T1Q2 改为 `condition_layer_20260528_source_20260528_v5`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1Q2. N2 symmetry target price alignment v5 passed_active

状态：done for N2 symmetry target price alignment v5 passed_active；N3 subscription rebuild for v5 allowed next。
目标：登记 `condition_layer_20260528_source_20260528_v5` 成为 20260528 source-date 的 active condition lineage，并明确 v4 superseded、旧 v1 downstream lineage preserved，N3/N4/N5/N6 不自动 rebuild。

输入：

```text
active N2 run = condition_layer_20260528_source_20260528_v5
previous active run = condition_layer_20260528_source_20260528_v4
sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql
```

验收标准：

- active N2 run=`condition_layer_20260528_source_20260528_v5`。
- v5.status=`passed_active`。
- previous active run=`condition_layer_20260528_source_20260528_v4`。
- v4.status=`superseded`。
- passed_active_count=1。
- source_trade_date / for_trade_date / prev_trade_date = 20260528 / 20260529 / 20260528。
- 000027 buy_target_price=`8.42`。
- 000027 reference_target_price=`8.42`。
- 000027 main_up_anchor=`W`。
- 000027 up_reference_period=`D`。
- 000027 up_amplitude=`1.17`。
- 000027 up_base_price=`7.25`。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4271/169/875。
- minute_target_scope stock/index/board=4251/169/875。
- condition_display_basis stock/index/board=2011/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=103。
- P0/P1/P2=0/3/3。
- deprecated signal rows=0。
- alias mismatch=0。
- invalid reference period=0。
- locked_target_price / target_lock_status absent=true。
- outbox/inbox refs=0/0。
- N3/N4/N5 refs=0/0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 允许进入 N3_market_data subscription rebuild gate for `condition_layer_20260528_source_20260528_v5`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1R. 20260529 -> 20260601 N2 condition layer v1 preserved / superseded

状态：done for 20260529 -> 20260601 N2 condition layer v1 historical run；后续已被 financial canonical v2 active supersede。
目标：保留 `condition_layer_20260529_source_20260529_v1` 的审计证据，并明确该 run 已不再是当前 active condition lineage。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v1
source_trade_date = 20260529
for_trade_date = 20260601
sql/N2_condition_layer_20260529_rollback.sql
```

输出：

```text
N2 20260529 active lineage status
row counts and quality summary
canonical signal and target checks
side-effect boundary proof
rollback safety
N3 subscription 20260601 next gate
```

验收标准：

- run_id=`condition_layer_20260529_source_20260529_v1`。
- status=`superseded after condition_layer_20260529_source_20260529_v2`。
- source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4342/187/942。
- minute_target_scope stock/index/board=4323/187/942。
- condition_display_basis stock/index/board=1973/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=109。
- P0/P1/P2=0/9/3。
- canonical signal audit passed=true。
- deprecated_signal_rows=0。
- noncanonical_signal_rows=0。
- outbox/inbox/checkpoint delta=0/0/0。
- N3/N4/N5 downstream refs=0/0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260529_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- financial canonical pass-through / active supersede 已由 `condition_layer_20260529_source_20260529_v2` 完成。
- symmetry target price target-machine active supersede 已由 `condition_layer_20260529_source_20260529_v3` 完成。
- anchor-segment alignment active supersede 已由 `condition_layer_20260529_source_20260529_v4` 完成。
- secondary-anchor active supersede 已由 `condition_layer_20260529_source_20260529_v5` 完成。
- level score active supersede 已由 `condition_layer_20260529_source_20260529_v6` 完成。
- N3_market_data subscription gate for 20260601 应基于 `condition_layer_20260529_source_20260529_v6`，不再基于 v1/v2/v3/v4/v5。
- 20260529 盘中旧 lineage 的 N6 live2 / full-day user projection gate 仍是独立可审查分支。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1S. 20260529 N1 stock_financial canonical metrics v2 passed

状态：done for N1 stock_financial canonical metrics v2 passed；已被 N2 `condition_layer_20260529_source_20260529_v2` 消费。
目标：登记 `stock_financial_20260529_v2` 成为 20260529 active stock_financial source_version，并明确后续已由 N2 financial canonical v2 active run 承接。

输入：

```text
source_batch_id = stock_financial_canonical_20260529_v1
source_version = stock_financial_20260529_v2
previous_source_version = stock_financial_20260529_v1
financial_metric_version = financial_metric_v1
rollback_sql = sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql
```

验收标准：

- stock_financial_metrics_fact v2 rows=5506。
- stock_financial_metrics_fact v1 rows=5506。
- common_ingest_batch rows=1，row_count=5506，status=passed。
- common_quality_gate_result rows=13。
- active stock_financial 20260529 -> `stock_financial_20260529_v2`。
- P0/P1/P2=0/8/2。
- outbox/inbox/checkpoint delta=0/0/0。
- condition refs to v2=0 at N1 post-review time；later consumed by N2 run `condition_layer_20260529_source_20260529_v2`。
- Parquet not written。
- N2/N3/N4/N5/N6 not entered。
- worker_started=false。
- old_system/real_trading not touched。
- rollback_safe=true；rollback batch scope uses `data_type=stock_financial_canonical_metrics`。

禁止事项：

- 不自动执行 N2。
- 不写 condition_* 表。
- 不进入 N3/N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- N2_condition financial canonical pass-through / active supersede 已完成：`condition_layer_20260529_source_20260529_v2`。
- N2_condition symmetry target price target-machine active supersede 已完成：`condition_layer_20260529_source_20260529_v3`。
- N2_condition anchor-segment alignment active supersede 已完成：`condition_layer_20260529_source_20260529_v4`。
- N2_condition secondary-anchor active supersede 已完成：`condition_layer_20260529_source_20260529_v5`。
- N2_condition level score active supersede 已完成：`condition_layer_20260529_source_20260529_v6`。
- 下一步允许切换到 `layer_role=N3_market_data`，做 20260601 subscription rebuild readiness / execute gate，source_condition_run_id=`condition_layer_20260529_source_20260529_v6`。
- 不允许 runtime_control 直接执行 N3。

### T1T. 20260529 -> 20260601 N2 financial canonical v2 passed / preserved

状态：done for N2 financial canonical active supersede；后续已被 T1U target-machine v3 active supersede。
目标：登记 `condition_layer_20260529_source_20260529_v2` 的 financial canonical pass-through 证据，并明确该 run 已被 v3 supersede，N3/N4/N5/N6 不自动 rebuild。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v2
source_trade_date = 20260529
for_trade_date = 20260601
financial_source_version = stock_financial_20260529_v2
rollback_sql = sql/N2_condition_layer_20260529_financial_v2_rollback.sql
```

验收标准：

- v2.status=`superseded after condition_layer_20260529_source_20260529_v3`。
- v1.status=`superseded`。
- source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4106/187/942。
- minute_target_scope stock/index/board=4087/187/942。
- condition_display_basis stock/index/board=1862/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=106。
- P0/P1/P2=0/6/3。
- basis/pool/scope/display financial mismatch=0/0/0/0。
- canonical_financial_pass_through_mismatch=0。
- finance_sector_warning_rows=120。
- pre_revenue_warning_rows=1。
- outbox/inbox/checkpoint delta=0/0/0。
- N3/N4/N5 refs for v2=0/0/0。
- market_data_pulled=false。
- downstream_layers_touched=false。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260529_financial_v2_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 已由 T1U `condition_layer_20260529_source_20260529_v3` active supersede，随后由 T1V `condition_layer_20260529_source_20260529_v4` active supersede。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1U. 20260529 -> 20260601 N2 symmetry target price target-machine v3 preserved / superseded

状态：done for N2 symmetry target price target-machine active supersede；后续已被 T1V v4 active lineage supersede。
目标：保留 `condition_layer_20260529_source_20260529_v3` 的审计证据，并明确该 run 已不再是 20260529 source-date active condition lineage。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v3
source_trade_date = 20260529
for_trade_date = 20260601
previous_run_id = condition_layer_20260529_source_20260529_v2
financial_source_version = stock_financial_20260529_v2
rollback_sql = sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql
```

验收标准：

- v3.status=`superseded after condition_layer_20260529_source_20260529_v4`。
- v2.status=`superseded`。
- active_passed_active_count=1。
- source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4106/187/942。
- minute_target_scope stock/index/board=4087/187/942。
- condition_display_basis stock/index/board=1862/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=106。
- P0/P1/P2=0/6/3。
- 000543 皖能电力：main_up_anchor=W，up_reference_period=D，A段=20260506->20260529，segment_low/high=8.09/9.80，amplitude=1.71，trend_break_date=20260526，base_window=20260527->20260529，base_price=9.11，buy_target_price/reference_target_price=10.82/10.82。
- 000027 深圳能源：buy_target_price/reference_target_price=8.45/8.45。
- outbox/inbox/checkpoint delta=0/0/0。
- v3 downstream refs=0。
- market_data_pulled=false。
- downstream_layers_touched=false。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql`。

禁止事项：

- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 历史 next gate 曾允许 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v3`。
- 后续又由 T1V 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v4`。
- 后续又由 T1W 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v5`。
- 当前 next gate 已由 T1X 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v6`。
- 20260529 盘中旧 lineage 的 N6 live2 / full-day user projection gate 仍是独立可审查分支。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1V. 20260529 -> 20260601 N2 anchor-segment alignment v4 preserved / superseded

状态：done for N2 anchor-segment alignment v4 historical run；后续已被 T1W v5 active lineage supersede。
目标：保留 `condition_layer_20260529_source_20260529_v4` 的审计证据，并明确该 run 已不再是 20260529 source-date active condition lineage。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v4
previous active v3 = superseded
rollback_sql = sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql
```

验收标准：

- active N2 run=`condition_layer_20260529_source_20260529_v4`。
- v4.status=`superseded after condition_layer_20260529_source_20260529_v5`。
- previous active v3=`condition_layer_20260529_source_20260529_v3`。
- v3.status=`superseded`。
- P0/P1/P2=0/6/3。
- row counts aligned。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4106/187/942。
- minute_target_scope stock/index/board=4087/187/942。
- condition_display_basis stock/index/board=1862/83/428。
- monitor_target stock/index/board=5506/83/428。
- golden 000600=12.93。
- golden 000543=10.82。
- golden 000027=8.45。
- N3/N4/N5/N6 refs=0/0/0/0。
- outbox/inbox/checkpoint refs=0/0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql`。

禁止事项：

- 不执行 DB。
- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 历史 next gate 曾允许 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v4`。
- 后续又由 T1W 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v5`。
- 当前 next gate 已由 T1X 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v6`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1W. 20260529 -> 20260601 N2 secondary-anchor v5 preserved / superseded

状态：done for N2 secondary-anchor v5 historical run；后续已被 T1X v6 active lineage supersede。
目标：保留 `condition_layer_20260529_source_20260529_v5` 的审计证据，并明确该 run 已不再是 20260529 source-date active condition lineage。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v5
previous active v4 = superseded
rollback_sql = sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql
```

验收标准：

- N2 run=`condition_layer_20260529_source_20260529_v5`。
- v5.status=`superseded after condition_layer_20260529_source_20260529_v6`。
- previous active v4=`condition_layer_20260529_source_20260529_v4`。
- v4.status=`superseded`。
- P0/P1/P2=0/6/3。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4106/187/942。
- minute_target_scope stock/index/board=4087/187/942。
- condition_display_basis stock/index/board=1862/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=106。
- N3/N4/N5/N6 refs=0/0/0/0。
- outbox/inbox/checkpoint refs=0/0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql`。

禁止事项：

- 不执行 DB。
- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 历史 next gate 曾允许 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v5`。
- 当前 next gate 已由 T1X 改为 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v6`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1X. 20260529 -> 20260601 N2 level score v6 passed_active

状态：done for N2 level score v6 passed_active；N3 subscription rebuild gate for 20260601 based on v6 allowed next。
目标：登记 `condition_layer_20260529_source_20260529_v6` 成为 20260529 source-date 的 active condition lineage，并明确 N3/N4/N5/N6 不自动 rebuild。

输入：

```text
run_id = condition_layer_20260529_source_20260529_v6
previous active v5 = superseded
rollback_sql = sql/N2_level_score_20260529_v6_rollback.sql
```

验收标准：

- active N2 run=`condition_layer_20260529_source_20260529_v6`。
- v6.status=`passed_active`。
- previous active v5=`condition_layer_20260529_source_20260529_v5`。
- v5.status=`superseded`。
- source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529。
- P0/P1/P2=0/6/3。
- condition_basis stock/index/board=5506/83/428。
- condition_pool stock/index/board=4106/187/942。
- minute_target_scope stock/index/board=4087/187/942。
- condition_display_basis stock/index/board=1862/83/428。
- monitor_target stock/index/board=5506/83/428。
- common_condition_quality_item=106。
- level_score_ok=true。
- row_match=true。
- golden 000543 level_score_up/down=3124/0。
- golden 000600 level_score_up/down=3124/0。
- golden 300327 level_score_up/down=2999/125。
- level score missing/invalid rows=0。
- N3/N4/N5 refs=0/0/0。
- outbox/inbox/checkpoint delta=0/0/0。
- N3 not automatically rebuilt。
- N4/N5/N6 not entered。
- market_data_pulled=false。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N2_level_score_20260529_v6_rollback.sql`。

禁止事项：

- 不执行 DB。
- 不执行 N3。
- 不拉行情。
- 不进入 N4/N5/N6。
- 不启动 worker。
- 不触碰旧系统。

下一步：

- 允许进入 N3_market_data subscription rebuild readiness / execute gate for 20260601 based on `condition_layer_20260529_source_20260529_v6`。
- runtime_control 仅登记状态，不执行 N3、不拉行情、不消费 outbox。

### T1A. runtime PostgreSQL data_directory gate

状态：done before N3-B1 passed rerun
目标：确认 N3/N4/N5 runtime PostgreSQL 使用本地硬盘，不把盘中 runtime 表写到 `/Volumes/MacRaid/database`。

输入：

```text
ASHARE_V3_POSTGRES_DSN
PostgreSQL SHOW data_directory 只读结果
N3 runtime database / cluster 约定
```

输出：

```text
runtime_storage_gate_report
data_directory path
local_disk=true/false
external_raid_database_path=false/true
rerun_allowed=true/false
```

验收标准：

- `data_directory` 已确认。
- `data_directory` 不在 `/Volumes/MacRaid/database`。
- 若无法确认或位于外接盘，必须阻断 N3-B1 rerun。
- 该 gate 只读，不改 PostgreSQL 配置，不迁移数据。

禁止事项：

- 不执行 N3-B1。
- 不写数据库。
- 不修改 PostgreSQL 配置。
- 不启动服务或 worker。

### T1B. board snapshot missing=127 root cause

状态：done before N3-B1 passed rerun
目标：解释上一次 N3-B1 failed execute 中 `board snapshot missing=127` 且 `board_realtime_daily_snapshot=0` 的原因。

输入：

```text
N3-B1 failed execute report
N3-B1 pre/post backup
source_adapter_plan
board market_data_subscription / pull_plan
board adapter evidence
```

输出：

```text
board_snapshot_missing_root_cause_report
root_cause
fix_or_rerun_condition
rollback_safety_confirmation
```

验收标准：

- 明确是 adapter、订阅、代码路径、表写入、数据源还是环境问题。
- 明确是否只影响 board，是否影响 stock/index。
- 明确重跑前需要修复还是只需更换执行窗口/数据源。
- 不用 synthetic 或 N4/N5 数据替代真实 N3 snapshot。

禁止事项：

- 不拉行情，除非用户另行授权专门的 N3 诊断 execute。
- 不写 `board_realtime_daily_snapshot`。
- 不写 outbox。
- 不进入 N4/N5/N6。

### T2. 标记 synthetic outbox

状态：done by total-control documentation registration；数据库未写标记
目标：把当前 N4 synthetic/sample outbox 与未来真实 N3 event-driven outbox 明确区分，避免 N5 或 N6 误当真实交易链路消费。

输入：

```text
docs/N4_R4_SYNTHETIC_TRIGGER_EXECUTE_REPORT.md
docs/N5_R4_ACTION_CONSUMER_RUN_ONCE_DRY_RUN_REPORT.md
common_event_outbox row count evidence from reports
```

输出：

```text
synthetic outbox inventory
source_run_id list
denylist source_run_id list
rollback SQL reference
consumer safety note
```

验收标准：

- 明确 synthetic denylist source_run_id 为：
  `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute`
  `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute`
- 明确 `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute` 基于 superseded N2 run `condition_layer_20260522_to_20260525_20260525003855_execute`。
- 明确每个 denylist source_run_id 的 synthetic outbox count = 26652，合计 denylist N4 outbox rows = 53304。
- 明确 `real_n3_event_consumed=false`。
- 明确 N5-R4 dry-run 只可作为 contract validation，不代表真实动作。
- 给出是否需要 rollback synthetic outbox 的决策点。

禁止事项：

- 不更新 `common_event_outbox`。
- 不消费 N4 outbox。
- 不写 N5 inbox / checkpoint。
- 不删除 synthetic 数据，除非用户单独授权 rollback。

### T3. 重跑 N3-B1 readiness

状态：done, latest readiness PASS and execute passed
目标：在 2026-05-25 当日重新执行只读 readiness，确认 realtime daily snapshot 是否可进入 execute 决策。

输入：

```text
N3-B1 execute contract
current date = 20260525
for_trade_date = 20260525
N3 subscription run aligned to N2-Display: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
trade calendar status
previous-day minute preload status
```

输出：

```text
docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_READINESS_20260525.md
docs/N3_B1_realtime_daily_snapshot_execute_readiness_20260525.json
```

验收标准：

- readiness 是 read-only。
- P0/P1/P2 明确。
- 若 P0=0，输出 `ready=true` 但不自动执行。
- 若 P0>0，输出 blocker 和 `blocked_by_layer` 交接建议。
- 明确使用 N2-Display / N3-Display lineage，不再引用旧 run `20260524014029` 或旧 N2-R4 subscription。

禁止事项：

- 不拉行情。
- 若 `20260525 common_trade_calendar` detail row 仍缺失，必须 blocked_by_layer=N1_ingestion。
- 不写 snapshot。
- 不写 outbox。
- 不启动 worker。
- 不进入 N4/N5。

### T4. 对齐 N3-A1 到 N2-Display lineage

状态：done, aligned to N2-Display subscription lineage
目标：解决 N3-A1 previous-day minute preload 当前报告引用旧 N3 run 的 lineage 缺口。

输入：

```text
docs/N3_A1_PREVIOUS_DAY_MINUTE_PRELOAD_EXECUTE_REPORT.md
docs/N3_AFTER_N2_DISPLAY_MARKET_DATA_SUBSCRIPTION_REBUILD_REPORT.md
N2-Display active run = condition_layer_20260522_to_20260525_20260525102249_execute
N3-Display subscription run = market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

输出：

```text
aligned preload run:
previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

验收标准：

- 当前 N3-Display subscription source_run_id 是 `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- 当前 preload run 使用同一 N3-Display subscription lineage。
- N2 active condition run、N3 subscription run、N3 preload run 在 B1 failed execute / rollback 后均未改变。

禁止事项：

- 不静默复用旧 preload。
- 不直接写新的分钟 K。
- 不删除旧 preload。
- 不影响 N4/N5 现有 synthetic 验证数据。

### T5. 决定是否执行 N3-B1

状态：done, N3-B1 execute passed。
目标：基于 readiness 和 lineage 对齐结果，决定是否执行 realtime daily snapshot。

输入：

```text
runtime PostgreSQL data_directory gate result
board snapshot missing=127 root cause result
latest T3 readiness result
T4 lineage alignment result
N3-B1 execute contract
operator approval
```

输出：

```text
execute decision completed
snapshot_run_id = realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
snapshot rows = stock 2052 / index 9 / board 127
outbox = MarketSnapshotUpdated pending 2188
missing/delayed events = 0
```

验收标准：

- 用户明确确认执行。
- P0=0。
- N3-A1 preload lineage 已对齐。
- 上一次 failed execute 已 rollback clean；重跑前该 snapshot_run_id / outbox 已为空，重跑后当前状态以本任务输出为准。
- runtime PostgreSQL `data_directory` 位于本地硬盘，且不在 `/Volumes/MacRaid/database`。
- `board snapshot missing=127 / board_realtime_daily_snapshot=0` 已解释并形成重跑条件。
- 明确写入目标是 `stock/index/board_realtime_daily_snapshot` 和 N3 outbox。
- 明确不会触碰 N4/N5/N6。
- execute report P0=0。
- `minute_bar_written=false`。
- `downstream_layers_touched=false`。
- `worker_started=false`。

禁止事项：

- 不消费当前 N3-B1 outbox。
- 不启动长期 worker。
- 不写 trigger/action/user。
- 不读或改旧系统。

### T5A. N4 current context rebuild and real-event contract registration

状态：done; current context ready for dry-run
目标：在不消费 outbox、不写 trigger fact 的前提下，登记 N4 current context rebuild 和真实 N3 `MarketSnapshotUpdated` dry-run 输入边界。

输入：

```text
current N3-B1 snapshot_run_id
MarketSnapshotUpdated pending=2188
N4 current trigger context lineage
old N4 synthetic outbox inventory
N4 event consumption contract
docs/N4_CURRENT_TRIGGER_CONTEXT_REBUILD_REPORT.md
docs/N4_CURRENT_TRIGGER_CONTEXT_REBUILD_REPORT.json
```

输出：

```text
N4 real-event contract review report
allowed source_run_id list
synthetic outbox exclusion rule
N4 rollback preconditions
dry-run command proposal
current context run:
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

验收标准：

- 明确 dry-run 只允许读取当前 N3-B1 `MarketSnapshotUpdated`；真实消费仍需单独 execute 授权。
- 明确 N4 current context run 为 `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- 明确 current context rows 为 stock=4236, index=18, board=258, total=4512。
- 明确 current context P0/P1/P2=0/0/0。
- 明确 context rebuild 未写 `common_event_inbox`、未写 `common_trigger_match`、未写 N4 outbox、未消费 N3 outbox。
- 明确旧 N4 synthetic outbox 不得作为当前真实链路输入。
- 明确 N4 dry-run 不写 trigger fact / outbox / inbox checkpoint。
- 明确四类 projection / 30m 类信号 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 不必等待完整 30m 闭合，但必须使用 N3 标准化、可追溯 realtime projection 指标；`MinuteBarClosed` / closed 30m summary 是强确认或回放校验入口。
- 当时明确 N4 real run-once execute 仍需用户单独授权；该授权链路已由 T7 登记为 passed，仅限当前 execute_run_id。

禁止事项：

- 不消费 outbox。
- 不写 `common_event_inbox`。
- 不写 trigger fact / trigger outbox。
- 不进入 N5/N6。

### T5B. N4 dry-run on current N3-B1 events

状态：done as read-only dry-run; superseded by T7 execute passed
目标：验证 N4 对当前 N3-B1 真实事件的消费口径和触发候选，不写正式事实；同时修正四类 projection / 30m 类信号的 gate，避免误认为必须等待完整 30m 闭合。

输入：T5A context registration、current N3-B1 `MarketSnapshotUpdated pending=2188`、N4 current context run。
输出：N4 real-event dry-run report。
验收标准：`real_n3_event_source_run_id` 等于当前 B1 snapshot_run_id，dry-run 使用 current N4 context run，不写 `common_event_inbox`、不写 trigger fact/outbox、不更新 checkpoint；四类 projection / 30m 类信号只能在 N3 标准化、可追溯 realtime projection 指标和 N4 projection matcher 落地后进入正式 TriggerMatched。
禁止事项：不消费或 ack outbox、不 execute、不写 action/user、不启动 worker。

### T5C. N3 realtime projection metric contract for N4

状态：done for design/schema/execute gate；B2 execute has written formal stock/index projection facts
目标：定义 N3 输出给 N4 的标准化、可追溯 realtime projection 指标，使 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 不必等待完整 30m 闭合即可被 N4 正式判断。

输入：N2 `period_trigger_baseline_json` trace、N3 realtime snapshot / minute facts、N4 current context gate、旧 synthetic denylist。
输出：N3 projection design / event payload contract / quality gate / rollback plan / projection fact schema。
验收标准：projection 指标具备来源 trace、窗口定义、amount/rise/shrink 口径、data_quality_status、dedup_key、replay 校验方式；N4 不需要也不得拉行情或拼原始分钟；projection fact 表结构已就绪。
禁止事项：不写 N4 trigger fact、不进入 N5/N6、不启动 worker。

### T5C.1 032 N3 action-confirmation projection metric schema migration

状态：done; schema migration passed, writer execute completed as T5C.2。
目标：登记 N3 action-confirmation projection metric 三张物理分表已落地，为 N4/N5 canonical action confirmation 输入事实提供 schema 前置条件。

输入：`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`、`sql/032_n3_action_confirmation_metric_schema.sql`、`sql/032_n3_action_confirmation_metric_schema_rollback.sql`、`sql/N3_action_confirmation_projection_metric_business_rollback.sql`、`docs/N3_action_confirmation_projection_metric_032_migration_execute_report.json`。
输出：032 migration passed 登记；schema 状态；rollback summary；下一步 N3 writer execute gate。

验收标准：

- migration=`sql/032_n3_action_confirmation_metric_schema.sql`，status=passed。
- target DB proof：database=`ashare_v3`，user=`ashare_v3_user`，host=`127.0.0.1/32`，port=`5432`，old_system_db=false。
- created tables：`stock_action_confirmation_projection_metric`、`index_action_confirmation_projection_metric`、`board_action_confirmation_projection_metric`。
- index_count=18；metric_ready trace CHECK constraints=3。
- row_count stock/index/board=0/0/0。
- business_rows_written=false；market_data_pulled=false；worker_started=false。
- common_event_outbox / common_event_inbox / common_event_consumer_checkpoint delta=0/0/0。
- downstream N4/N5/N6 checked_tables=32；downstream row_count_delta_zero=true。
- rollback_safe=true；schema rollback SQL=`sql/032_n3_action_confirmation_metric_schema_rollback.sql`；business rollback SQL=`sql/N3_action_confirmation_projection_metric_business_rollback.sql`。

下一步：

- 后续 N3 action-confirmation projection writer execute 已完成并登记为 T5C.2。
- 新增 N4/N5 对该 metric fact 的消费或确认仍必须另行通过 N4/N5 gate。

禁止事项：runtime_control 不执行 N3 writer、不写数据库、不拉行情、不消费 outbox、不进入 N4/N5/N6、不启动 worker、不触碰旧系统。

### T5C.2 N3 action-confirmation projection writer execute

状态：done; writer execute passed。
目标：登记 N3 action-confirmation projection metric facts 已正式写入，作为后续 N4 action-confirmation metric consumption contract alignment 的标准输入。后续 N4 business execute 已完成并登记为 T5C.3。

输入：`docs/N3_action_confirmation_projection_writer_execute_report.json`、`docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_REPORT.md`、`docs/N3_action_confirmation_projection_writer_execute_contract.json`、`docs/N3_action_confirmation_projection_writer_execute_preflight.json`、`sql/N3_action_confirmation_projection_metric_business_rollback.sql`、`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`。
输出：writer execute passed 登记；N3 schema/write 状态；rollback summary；后续 N4 consumption contract alignment 与 business execute 已完成并登记为 T5C.3。

验收标准：

- projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- source_condition_run_id=`condition_layer_20260601_source_20260601_v1`。
- source_subscription_run_id=`market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- source_snapshot_run_id=`realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- source_today_minute_run_id=`today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- source_previous_day_minute_run_id=`previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- common_market_data_run.status=`passed`。
- rows stock/index/board/total=765/54/150/969；metric_ready/not_ready=969/0。
- common_market_data_quality_item rows=6；P0/P1/P2=0/0/0。
- market_data_pulled=false；market_data_fact_written=true；downstream_layers_touched=false；worker_started=false。
- scoped outbox/inbox/checkpoint=0/0/0；global outbox/inbox/checkpoint delta=0/0/0。
- no outbox write/consume；no inbox/checkpoint write；no N4/N5/N6 refs。
- rollback_safe=true；rollback SQL=`sql/N3_action_confirmation_projection_metric_business_rollback.sql`。

下一步：

- 后续 N4 action-confirmation metric business execute 已完成并登记为 T5C.3。
- N4 只允许消费 N3 标准 metric facts 和 trace，不得从 raw minute 重算。

禁止事项：runtime_control 不执行 N4/N5/N6、不消费 outbox、不写 inbox/checkpoint、不启动 worker、不拉行情、不触碰旧系统、不做 voice/mobile/sim/position/real trade。

### T5C.3 N4 action-confirmation metric business execute

状态：done; business execute passed。
目标：登记 N4 已只消费 N3 标准 action-confirmation metric facts 和本地 trigger context，正式写入 N4 trigger fact/outbox；保持 N5/N6、inbox/checkpoint、worker、行情拉取和真实交易全部未触碰。

输入：`docs/N4_action_confirmation_metric_business_execute_report.json`、`docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_REPORT.md`、`docs/N4_action_confirmation_metric_business_execute_contract.json`、`docs/N4_action_confirmation_metric_business_execute_final_preflight.json`、`sql/N4_action_confirmation_metric_business_execute_rollback.sql`、`docs/N4_action_confirmation_metric_dry_run_report.json`、`docs/N4_action_confirmation_metric_execute_preflight.json`、`docs/N3_action_confirmation_projection_writer_execute_report.json`、`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`。
输出：N4 action-confirmation metric execute passed 登记；N4 outbox pending 摘要；rollback summary；下一步 N5 action-confirmation metric consumption contract/dry-run gate。

验收标准：

- execute_run_id=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- source_condition_run_id=`condition_layer_20260601_source_20260601_v1`。
- trigger_context_run_id=`trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1`。
- source_projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`。
- common_trigger_run.status=`passed`。
- common_trigger_run=1；common_trigger_quality_item=10；common_trigger_state=5941；common_trigger_match=5941；common_event_outbox=5941。
- outbox pending：TriggerMatched=6，TriggerPendingMarketData=5935，TriggerStateChanged=0，delivered/delivering=0/0。
- P0/P1/P2=0/1/0；quality item distribution：P0 passed=9，P1 warning=1。
- P1=`n4_action_confirmation_metric_pending_candidates_visible`，non-blocking=true。
- N3 metric facts unchanged：stock/index/board=765/54/150。
- common_event_inbox refs=0；checkpoint refs=0；N5 refs=0。
- N3 outbox consumed=false；inbox/checkpoint written=false；N5/N6 entered=false。
- worker_started=false；market_data_pulled=false；voice/mobile/sim/position/real_trade=false。
- rollback_safe=true；rollback SQL=`sql/N4_action_confirmation_metric_business_execute_rollback.sql`。
- execute report=`docs/N4_action_confirmation_metric_business_execute_report.json`。

下一步：

- 后续 N5 action-confirmation metric execute 已完成并登记为 T5C.4。
- 允许进入 `layer_role=N6_user` 的 user projection contract/dry-run gate。

禁止事项：runtime_control 不执行 N5/N6、不消费 N4 outbox、不写 inbox/checkpoint、不启动 worker、不拉行情、不触碰旧系统、不做 voice/mobile/sim/position/real trade。

### T5C.4 N5 action-confirmation metric execute

状态：done; business execute passed。
目标：登记 N5 已消费 N4 action-confirmation metric outbox 的 pending rows，基于 N4 `TriggerMatched` 和 N3 标准 action-confirmation metric facts 写入 N5 action fact/event/outbox，并保持 N6/user/voice/mobile/sim/position/real trade 全部未触碰。

输入：`docs/N5_20260602_ACTION_CONFIRMATION_METRIC_EXECUTE_REPORT.md`、`docs/N5_20260602_action_confirmation_metric_execute_report.json`、`docs/N5_20260602_ACTION_CONFIRMATION_METRIC_EXECUTE_PREFLIGHT.md`、`docs/N5_20260602_action_confirmation_metric_execute_preflight.json`、`docs/N5_20260602_ACTION_CONFIRMATION_METRIC_CONSUMPTION_DRY_RUN_REPORT.md`、`docs/N5_20260602_action_confirmation_metric_consumption_dry_run_report.json`、`docs/N5_20260602_ACTION_CONFIRMATION_METRIC_CONSUMPTION_CONTRACT.md`、`docs/N5_20260602_action_confirmation_metric_consumption_contract.json`、`sql/N5_20260602_action_confirmation_metric_execute_rollback.sql`、`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`。
输出：N5 action-confirmation metric execute passed 登记；N5 outbox pending 摘要；rollback summary；后续 N6 shadow projection execute 已完成并登记为 T5C.5。

验收标准：

- action_run_id=`action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- source N4 run=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- common_action_run.status=`passed`。
- P0/P1/P2=0/0/0。
- common_action_run=1；common_action_quality_item=5935；stock_action_fact=1；index_action_fact=4；board_action_fact=0；common_action_event=5；common_event_outbox=5；common_event_inbox=5941；common_event_consumer_checkpoint=2487。
- event distribution：ActionExecuted=4，ActionBlocked=1，ActionEligible=0，ActionSkipped=0。
- N5 outbox pending：ActionExecuted=4，ActionBlocked=1，delivered/delivering=0/0。
- N4 outbox unchanged：TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，delivered/delivering=0/0。
- N6/user/downstream refs=0；position refs=0；voice/mobile/sim/real_trade refs=0。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260602_action_confirmation_metric_execute_rollback.sql`。
- execute report=`docs/N5_20260602_action_confirmation_metric_execute_report.json`。

下一步：

- 后续 N6 20260602 action-confirmation metric shadow projection execute 已完成并登记为 T5C.5。
- N6 必须只消费 N5 标准 action outbox / user projection contract，不回写 N1-N5，不启动 worker，不做 push/voice/mobile/sim/position/real trade，除非另开 gate。

禁止事项：runtime_control 不执行 N6、不消费 N5 outbox、不写 user/voice/mobile/sim/position/real trade、不启动 worker、不触碰旧系统。

### T5C.5 N6 action-confirmation metric shadow projection execute

状态：done; shadow projection execute passed。
目标：登记 N6 已基于 N5 标准 action outbox 写入 shadow user projection/card/queue rows，并保持 N5 outbox pending、无 push/voice/mobile/sim/position/real trade、无 worker。

输入：`docs/N6_20260602_ACTION_CONFIRMATION_PROJECTION_CONTRACT.md`、`docs/N6_20260602_action_confirmation_projection_contract.json`、`docs/N6_20260602_ACTION_CONFIRMATION_PROJECTION_PREFLIGHT.md`、`docs/N6_20260602_action_confirmation_projection_preflight.json`、`docs/N6_20260602_ACTION_CONFIRMATION_PROJECTION_DRY_RUN_REPORT.md`、`docs/N6_20260602_action_confirmation_projection_dry_run_report.json`、`sql/N6_projection_business_rollback.sql`、`docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`。
输出：N6 shadow projection execute passed 登记；N6 projection/card/queue row 摘要；N5 outbox unchanged 摘要；rollback summary；20260602 N1-N6 run-once 链路完成到 N6 shadow。

验收标准：

- projection_run_id=`user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- source_action_run_id=`action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`。
- preflight_result=`PREFLIGHT_PASS`。
- run status=`passed`。
- P0/P1/P2=0/5/2。
- user_projection_run=1；user_signal_projection=5；user_signal_card=5；user_notification_queue=5。
- queue distribution：`n5_action_executed / queued_only = 4`，`n5_action_blocked / queued_only = 1`。
- card distribution：ActionExecuted -> action_confirmed / executed / 30m_shrink = 4；ActionBlocked -> blocked / blocked = 1。
- N5 outbox unchanged：ActionExecuted pending=4；ActionBlocked pending=1。
- N5 outbox consumed=false；N5 outbox status updated=false。
- user_signal_decision=0；linked user_sim_order/trade/position=0/0/0；user_watchlist=0；user_watchlist_item=0。
- worker_started=false；push/voice/mobile=false；sim/position/real_trade=false。
- rollback_safe=true；rollback SQL=`sql/N6_projection_business_rollback.sql`。

下一步：

- 20260602 run-once 链路已完成到 N6 shadow。
- 后续只允许 N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。

禁止事项：不再次执行 N6，不消费 N5 outbox，不更新 N5 outbox status，不启动 worker，不 push/voice/mobile/sim/position/real trade，不触碰旧系统。

### T5D. N3-B2 projection input diagnosis

状态：done; original input blocker resolved by N3-C1, follow-up B2 dry-run passed
目标：诊断 N3-B2 realtime projection 是否已有足够输入可生成 N4 可用 projection。

输入：N3 realtime snapshot、N3 projection fact schema、N3 projection contract、N3 previous-day minute preload、N3 today minute facts。
输出：N3-B2 projection input diagnosis。
验收标准：

- N3-B2 projection 表结构已就绪。
- 诊断时 projection 只能生成 `not_ready` skeleton。
- 原 blocker 是缺今日 1m `minute_bar` 输入。
- 该输入 blocker 已由 N3-C1 today_minute_bar_1m execute passed 解除。
- N3-B2 projection dry-run after A1 fill + C1 已 passed，证明 stock/index 可生成 usable projection。
- N3-B2 projection execute 已 passed，正式 ready projection facts 已写入。
- 原先不允许 N4 将 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT` 写成正式 `TriggerMatched`；该限制已由 T7 projection matcher dry-run / preflight / execute gate 解除，仅限当前已登记的 execute_run_id。
- 下一步改为 N5 action preflight / contract review。

禁止事项：不写 projection business data、不消费 outbox、不写 N4 trigger fact/outbox、不进入 N5/N6、不启动 worker。

## P1 后续任务

### T6. N3-C 今日闭合分钟 K 计划 / C1 execute

状态：done for C1 today_minute_bar_1m execute; MinuteBarClosed event path not started。
目标：规划今日 `minute_bar_1m` dry-run / contract，补齐 N3-B2 usable projection 所需今日 1m 输入，同时维护 `MinuteBarClosed` 合同边界。

输入：N3 subscription、N3-B1 结果、N3-B2 input diagnosis、闭合分钟 K 合同。
输出：N3-C dry-run / execute contract；N3-C1 execute report。
验收标准：

- C1 run status=passed。
- today_minute_run_id = `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- actual rows: stock=390213, index=1719, board=24257, total=416189。
- expected total=417908；missing rows=1719；missing objects=9，全部为 BJ 920xxx 股票。
- `common_event_outbox` rows for C1 = 0。
- `MinuteBarClosed generated=false`。
- projection tables written=false。
- rollback SQL = `sql/N3_C1_today_minute_bar_1m_rollback.sql`。
- 未闭合分钟 K 不得出 `MinuteBarClosed`；C1 不写 outbox，后续若要生成事件必须另开 gate。

禁止事项：不让 N4/N5 使用未闭合分钟 K；不直接进入 N4/N5/N6；不启动 worker。

### T6A. N3-B2 projection dry-run

状态：done; dry-run passed after A1 fill + C1, no downstream side effects。
目标：基于 N3-B1 snapshot、N3-A1 previous-day preload、N3-C1 today minute facts 生成 projection dry-run 评估，判断是否能从 not_ready skeleton 进入 usable projection。

输入：N3 projection schema / contract、N3-B1 snapshot run、N3-A1 preload run、N3-C1 today_minute_run_id、N2 period_trigger_baseline_json trace。
输出：N3-B2 projection dry-run report。
验收标准：

- dry-run result = passed，P0/P1/P2 = 0/3/0。
- projection_run_id_candidate = `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- expected projection rows total = 2188。
- ready projection rows = 2052，其中 stock=2043、index=9。
- not_ready rows = 136，其中 BJ 920xxx stock=9、board=127。
- board not_ready 原因：B1 board snapshot_time=15:00，但 C1 latest_closed_minute=14:11，严格 lineage 下不得混用。
- projection_signal_status: down_volume_expanding=96, down_volume_flat=79, down_volume_shrinking=174, flat=577, unknown=136, up_volume_expanding=305, up_volume_flat=342, up_volume_shrinking=479。
- future B2 execute only allowed to write `common_market_data_run`、`common_market_data_quality_item`、`stock/index/board_realtime_projection_metric`。
- 不写 projection fact、不写 quality、不写 outbox、不消费 N3-B1 outbox、不进入 N4/N5/N6。

禁止事项：不执行 projection business write、不把 dry-run 结果交给 N4 当正式 TriggerMatched 输入、不启动 worker。

### T6B. N3-B2 projection execute preflight

状态：done; B2 execute passed after preflight and user confirmation。
目标：在 B2 execute 前确认正式 projection fact 写入的幂等、回滚、质量项和边界，决定是否允许进入用户 execute 确认点。

输入：T6A dry-run report、B1 snapshot run、A1 current-lineage fill-facts run、C1 today_minute_run_id、015 projection schema、B2 rollback SQL 草案。
输出：N3-B2 execute preflight report / contract / rollback confirmation。
验收标准：

- P0=0。
- source runs 精确等于当前 B1/A1/C1/subscription lineage，且状态均为 passed。
- projection_run_id 当前不存在或已确认可幂等重跑。
- allowed write tables 仅限 `common_market_data_run`、`common_market_data_quality_item`、`stock/index/board_realtime_projection_metric`。
- writes_outbox=false，updates_market_snapshot_payload=false。
- board=127 与 BJ 920xxx=9 必须保持显式 not_ready / blocked，不得静默修成 ready。
- rollback 按 projection_run_id 删除 projection fact、quality 和 run rows；不涉及 outbox rollback。

禁止事项：不写 outbox、不消费 outbox、不写 N4/N5/N6、不启动 worker、不把 preflight 当 execute。

### T6C. N3-B2 realtime projection execute

状态：done; execute passed, no outbox/downstream side effects。
目标：登记 B2 formal realtime projection facts，作为 N4 projection matcher dry-run / execute 输入。

输入：B2 execute contract / preflight / dry-run、B1 snapshot run、A1 current-lineage fill-facts run、C1 today_minute_run_id。
输出：N3-B2 realtime projection execute report。
验收标准：

- projection_run_id = `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- projection rows: stock=2052, index=9, board=127, total=2188。
- ready=2052，not_ready=136。
- stock ready=2043 / not_ready=9；index ready=9；board not_ready=127。
- projection_signal_status: up_volume_expanding=305, up_volume_flat=342, up_volume_shrinking=479, down_volume_expanding=96, down_volume_flat=79, down_volume_shrinking=174, flat=577, unknown=136。
- quality P0/P1/P2 = 0/3/0；quality rows=6；data_domain=common/stock/board；layer_scope=market_data_run；details.metric_scope=realtime_projection_metric。
- projection outbox=0；projection inbox=0；B1 MarketSnapshotUpdated pending=2188。
- rollback_safe=true；rollback SQL=`sql/N3_B2_realtime_projection_rollback.sql`。

禁止事项：不消费 B1 outbox、不写 N4 trigger fact/outbox/inbox/checkpoint、不进入 N5/N6、不启动 worker。

### T6D. N3-C2 closed-minute / closed-30m replay execute

状态：done for run-once execute passed; superseded by T6E C3 MinuteBarClosed outbox execute passed; EOD dry-run passed but execute preflight blocked by official daily fact gap。
目标：把 C2 固化为 N3 replay / confirmation 子阶段，用全日 1m replay 校验 C1 baseline，只写缺失或不一致的 minute delta rows，并从 C1 baseline + C2 delta 合成 closed 30m summary。

输入：N3 subscription run、N3-C1 today_minute_bar_1m execute 结果、N3-B1 snapshot、N3-B2 projection 结果、当前 N4/N5 已 passed runtime 边界。
输出：C2 execute report；closed_30m_summary row counts；rollback SQL；下一步 review branch。
验收标准：

- C2 不是 N1->N3 全链路重跑。
- c2_run_id = `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- 拉取策略：按对象尝试全日 1m replay。
- 写入策略：只写 C1 缺失或与 replay 不一致的 `stock/index/board_minute_bar_1m` delta rows，`run_id=c2_run_id`。
- summary 策略：`stock/index/board_closed_30m_summary` 从 C1 baseline + C2 delta 合成。
- C2 execute 已 passed。
- minute_delta_rows：stock=100669，index=441，board=6223，total=107333。
- closed_30m_summary：stock=16416，index=72，board=1016，total=17504。
- summary_status：closed=17432，partial=0，missing=72，failed=0。
- BJ 920xxx：9 objects，72 missing summaries，no fabricated minute rows。
- quality P0/P1/P2=0/1/0。
- outbox/inbox/checkpoint refs c2=0。
- B1 MarketSnapshotUpdated pending=2188。
- C1/B1/B2/N4/N5 runtime unchanged=true。
- worker_started=false；downstream_layers_touched=false。
- rollback_safe=true；rollback SQL=`sql/N3_C2_closed_30m_business_rollback.sql`。
- C2 不写 `MinuteBarClosed` outbox；C3 单独设计 event gate 且已由 T6E 登记为 execute passed。
- C2 不 supersede B1/B2/N4/N5，不自动回滚或重跑 N4/N5；replay diff 只写 quality / diff 证据。
- daily close 另设 gate，不和 C2 混做。

禁止事项：不追加执行 C2、不消费 outbox、不写 realtime_projection_metric/realtime_daily_snapshot、不碰 B1/B2/N4/N5 既有 runtime、不进入 trigger/action/user/voice/mobile/sim/position、不启动 worker；C2B 与 N4 C3 replay audit 已完成，EOD execute 被 official daily fact gap 阻断，不得直接 execute。

### T6E. N3-C3 MinuteBarClosed outbox execute

状态：done for run-once execute passed; superseded by T6F C2B closed_signal_enrichment execute passed; EOD dry-run passed but execute preflight blocked by official daily fact gap。
目标：把 C2 closed 30m summary 中已闭合且 trace 完整的行发布为标准 `MinuteBarClosed` pending outbox，供后续显式 allowlist replay review 使用。

输入：N3-C3 execute report、N3-C3 execute contract、C3 rollback SQL、C2 closed 30m summary run。
输出：C3 execute passed 登记；MinuteBarClosed pending outbox counts；rollback SQL；下一步 review branch。
验收标准：

- c3_run_id = `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- `common_market_data_run.status=passed`。
- P0/P1/P2=0/1/0。
- `market_data_pulled=false`；`market_data_fact_written=false`。
- source_trade_date/prev_trade_date=20260525/20260525。
- `MinuteBarClosed` outbox rows=17432。
- stock/index/board=16344/72/1016。
- pending=17432；delivered/delivering=0。
- inbox=0；checkpoint refs=0。
- closed_30m_summary C3 refs=0。
- minute_bar_1m C3 refs=0。
- realtime_projection_metric C3 refs=0。
- realtime_daily_snapshot C3 refs=0。
- N4/N5/N6 touched=false。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N3_C3_minute_bar_closed_outbox_rollback.sql`。
- 下一步已通过 T6F/T7B 完成 N4 C3 replay dry-run 与 replay audit execute 登记；EOD dry-run 已 PASS 但 execute preflight blocked，不得直接 replay event execute 或 EOD execute。

禁止事项：不消费 C3 outbox、不进入 N4/N5/N6 replay event execute、不启动 worker、不写 trigger/action/user/voice/mobile/sim/position；不得修改 closed summary、minute_bar、projection 或 snapshot。

### T6F. N3-C2B closed_signal_enrichment execute

状态：done for run-once execute passed; superseded by N4-C3 replay audit execute passed; EOD dry-run passed but execute preflight blocked by official daily fact gap。
目标：基于 C2 closed 30m summary 与前一日同 bucket baseline，写入 N3 标准化 closed signal enrichment facts，解除 N4 C3 replay dry-run 中 `closed_signal_status_missing` 缺口。

输入：N3-C2B execute report、N3-C2B execute contract、C2B business rollback SQL、C2 closed summary、A1 previous-day minute facts、C3 outbox status。
输出：C2B execute passed 登记；closed signal enrichment row counts；signal distribution；rollback SQL；下一步 review branch。
验收标准：

- c2b_run_id = `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- `common_market_data_run.status=passed`。
- P0/P1/P2=0/3/0。
- enrichment rows: stock=16416，index=72，board=1016，total=17504。
- computable_rows=17432。
- unknown_rows=72。
- missing_rows=72。
- signal distribution: up_volume_expanding=2800，up_volume_flat=2494，up_volume_shrinking=2260，down_volume_expanding=2806，down_volume_flat=2408，down_volume_shrinking=2011，flat=2653，unknown=72。
- quality_rows=6；data_domain common=3 / stock=3；layer_scope=market_data_run；details.metric_scope=closed_signal_enrichment。
- c2b outbox=0；c2b inbox=0；c2b checkpoint refs=0。
- C3 outbox pending=17432；C3 delivered/delivering=0；C3 inbox/checkpoint refs=0。
- closed_30m_summary not modified=true。
- minute_bar_1m not modified=true。
- realtime_projection_metric not modified=true。
- realtime_daily_snapshot not modified=true。
- rollback_safe=true；rollback SQL=`sql/N3_C2B_closed_signal_enrichment_business_rollback.sql`。
- 下一步已完成 N4 C3 replay dry-run 与 replay audit execute 登记；后续不得直接 N4/N5/N6 replay event execute。

禁止事项：不消费 C3 outbox、不进入 N4/N5/N6 replay event execute、不启动 worker、不写 trigger/action/user/voice/mobile/sim/position；不得修改 closed summary、minute_bar、projection 或 snapshot。

### T7. N4 real projection matcher run-once

状态：done for current real projection matcher execute；additional N4 execute / worker blocked。
目标：从当前真实 N3 B1 `MarketSnapshotUpdated` 与 N3 B2 realtime projection facts 生成 N4 trigger fact / outbox。

输入：N3 `MarketSnapshotUpdated`、N3 realtime projection 指标、current N4 trigger context、N4 projection matcher execute contract / preflight / dry-run refresh。
输出：N4 real projection matcher execute registration。
验收标准：

- execute_run_id = `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- result = passed / executed，P0/P1/P2=0/0/0。
- `common_event_inbox=2188 processed`。
- `common_event_consumer_checkpoint=2188`。
- `common_trigger_state=764`。
- `common_trigger_match=764`。
- `common_trigger_quality_item=9`。
- N4 outbox: `TriggerMatched=488 pending`，`TriggerPendingMarketData=276 pending`，delivered/delivering=0。
- signal summary: `B_BUY_30M_VOL matched=305 pending=136`，`BUY_HINT matched=6`，`S_SELL_30M_SHRINK matched=174 pending=136`，`SELL_HINT matched=3 pending=4`。
- B1 outbox still `MarketSnapshotUpdated pending=2188`；N3 facts unchanged=true；old synthetic outbox untouched=53304。
- downstream N5 inbox for this N4 run=764 processed。
- rollback_safe=true；rollback SQL=`sql/N4_projection_matcher_rollback.sql`。

禁止事项：不拉行情，不用 synthetic 替代真实事件，不追加消费 N4 outbox，不追加 N4/N5 execute，不进入 N6 execute，不启动 worker，不写 user/voice/sim/position/真实交易。

### T7B. N4 C3 replay audit execute

状态：done for audit-only run-once execute passed; superseded by T7C EOD dry-run/preflight registration。
目标：把 N4 C3 replay dry-run 的 diff 结果固化为 replay audit facts，只做审计留痕，不消费 C3 outbox，不生成正式 N4 标准事件。

输入：N4 C3 replay dry-run report、N4 C3 replay audit execute preflight、C3 `MinuteBarClosed` pending outbox、C2B closed signal enrichment facts、当前 N4 projection matcher run。
输出：N4 replay audit execute passed 登记；classification counts；rollback SQL；下一步 EOD dry-run / preflight。
验收标准：

- replay_run_id = `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`。
- `common_trigger_run.status=passed`。
- audit rows：stock=33762，index=144，board=2064，total=35970。
- classification：would_match=4734，would_clear=245，would_change=243，unchanged=30730，missing=18，not_ready=0。
- P0/P1/P2=0/1/0。
- `common_event_outbox=0`。
- `common_event_inbox=0`。
- checkpoint refs=0。
- `common_trigger_match=0`。
- `common_trigger_state=0`。
- C3 outbox pending=17432。
- C3 delivered/delivering=0。
- N5/N6 touched=false。
- worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N4_C3_replay_audit_business_rollback.sql`。
- 下一步已进入 T7C EOD dry-run / preflight；EOD execute 当前 blocked。

禁止事项：不消费 C3 outbox，不把 `would_match / would_clear / would_change` 写成正式 `TriggerMatched / TriggerCleared`，不进入 N5/N6 replay event execute，不启动 worker，不写 user/voice/mobile/sim/position/真实交易。

### T7C. N3-EOD snapshot refresh dry-run / preflight

状态：done for dry-run PASS; execute preflight BLOCKED by missing_official_daily_fact。
目标：登记 EOD settlement refresh 的 dry-run 与 execute preflight 结果，明确 EOD execute 仍不得推进，并把下一步切回 N1 official daily fact ingestion review。

输入：N3-EOD snapshot refresh dry-run report、N3-EOD execute preflight report、B1 realtime snapshot、C2 closed_30m_summary、C2B closed_signal_enrichment、C3 outbox status、N4 replay audit status。
输出：EOD dry-run/preflight 登记；official daily fact 缺口；下一步 N1 review gate。
验收标准：

- eod_run_id = `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- dry-run result = DRY_RUN_PASS。
- preflight result = PREFLIGHT_BLOCKED。
- blocker = `missing_official_daily_fact`。
- expected EOD snapshot rows：stock=2052，index=9，board=127，total=2188。
- official_daily_missing=2188。
- C3 outbox remains pending=17432；delivered/delivering=0。
- P0/P1/P2=0/3/0。
- EOD business rows=0。
- common_market_data_run / quality scoped eod_run_id = 0 / 0。
- outbox / inbox / checkpoint scoped eod_run_id = 0 / 0 / 0。
- EOD execute 继续 blocked。
- 下一步推荐切回 N1 official daily fact ingestion review，补齐 20260525 official daily fact。
- 禁止使用 C2/C2B 直接做正式 EOD settlement，除非另开 provisional settlement gate。

禁止事项：不执行 EOD、不拉行情、不写数据库、不消费 C3 outbox、不进入 N4/N5/N6、不启动 worker、不写 user/voice/mobile/sim/position/真实交易。

### T7D. N4 20260528 canonical trigger execute

状态：done for canonical run-once execute passed；superseded by T8B N5 canonical action execute passed。
目标：登记 20260528 canonical v2 N4 trigger run-once execute，把 N2 canonical v2 + N3 B1 fact-only snapshot + N4 context 生成 canonical N4 trigger state/outcome facts 与 N4 outbox。

输入：

```text
docs/N4_20260528_V2_CANONICAL_TRIGGER_EXECUTE_CONTRACT.md
docs/N4_20260528_V2_canonical_trigger_execute_contract.json
docs/N4_20260528_V2_CANONICAL_TRIGGER_EXECUTE_PREFLIGHT.md
docs/N4_20260528_V2_canonical_trigger_execute_preflight.json
docs/N4_20260528_V2_CANONICAL_LOCAL_TRIGGER_DRY_RUN_REPORT.md
docs/N4_20260528_V2_canonical_local_trigger_dry_run_report.json
sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql
```

输出：

```text
execute_run_id = trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
N4 canonical outbox pending counts
rollback_safe registration
next completed gate = N5 canonical action execute
```

验收标准：

- `common_trigger_run.status=passed`。
- P0/P1/P2=0/1/0。
- `common_trigger_quality_item=16`。
- `common_trigger_state=8887`。
- `common_trigger_match=8887`。
- `common_event_outbox=17774`。
- N4 outbox pending：`TriggerMatched=4285`，`TriggerPendingMarketData=4602`，`TriggerStateChanged=8887`。
- delivered/delivering=0。
- `common_trigger_match` 中 `TriggerStateChanged=0`。
- `pending_market_data trigger_live=false=4602`。
- `matched trigger_live=true=4285`。
- state/match signal distribution：`B_BUY=4576`，`S_SELL=4311`。
- deprecated runtime signal count：state=0，match=0，outbox_payload=0。
- `action_mark` payload count=0。
- `trigger_mark_candidate` missing：state=0，match=0，outbox=0。
- N5 refs=0。
- N6 refs=0。
- scoped inbox/checkpoint refs=0。
- global delta：outbox=+17774，inbox=0，checkpoint=0。
- N5/N6 worker_started=false。
- N2/N3 facts unchanged=true。
- old_system_touched=false。
- no action/user/voice/mobile/sim/position/real trade。
- rollback_safe=true；rollback SQL=`sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql`。

禁止事项：

- T7D 本身不消费 N4 outbox。
- T7D 本身不进入 N5 execute；后续 T8B 已单独完成 N5 canonical action execute。
- 不启动 worker。
- T7D 本身不写 action/user/voice/mobile/sim/position/真实交易。
- 不改 N2/N3 facts。
- 不触碰旧系统。

下一步：

- N5 canonical action execute 已完成。
- 20260529 N6 canonical shadow projection 已完成并登记为 T1K。
- 20260529 B1 live2 standard outbox snapshot 已完成并登记为 T1L。
- 20260529 N4 live2 canonical trigger execute 已完成并登记为 T1M。
- 20260529 N5 live2 canonical action execute 已完成并登记为 T1N。
- 后续只允许 20260529 N6 live2 / full-day user projection gate、N6 shadow projection post-review、N6 projection business rollback review（仅在需要回滚时）、runtime_control read-only dashboard / lineage review。
- N5 outbox consumption、additional N6 execute、worker、voice/mobile/sim/position/real trade 仍需单独 gate。

### T8. N5 action run-once execute

状态：done for current-real run-once execute；additional N5 execute / worker blocked。
目标：基于当前真实 N4 projection outbox，完成一次 N5 action consumer run-once execute，写入 action fact、action event、N5 outbox、N5 inbox/checkpoint，并保持 position/sim/voice/mobile/N6/真实交易为 0。

输入：当前 N4 real outbox source_run_id `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`、N5 execute preflight、N5 event/action contract、rollback plan。
输出：N5 current-real action execute report；N5 outbox pending registration；N5 rollback SQL。
验收标准：

- N5 current-real action execute 已 passed。
- action_run_id = `action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- `common_action_run.status=passed`。
- P0/P1/P2=0/0/0。
- 旧 blocker 已解除：当前 `TriggerMatched + source_event_type=MarketSnapshotUpdated + projection_trace` 被视为合法 projection input，不再误判为 `blocked_quality -> RiskEvent`。
- 当前 real source_run_id 必须显式 allowlist：`trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- old synthetic source_run_id 必须 denylist：
  `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute`
  `trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute`
- 当前真实 N4 outbox：total=764 pending，`TriggerMatched=488`，`TriggerPendingMarketData=276`，delivered/delivering=0；N5 execute 后 N4 outbox status 仍保持 pending=764。
- matched distribution: `B_BUY_30M_VOL=305`，`BUY_HINT=6`，`S_SELL_30M_SHRINK=174`，`SELL_HINT=3`。
- `BUY_HINT / SELL_HINT` 应生成 action fact + `HintEvent`。
- `B_BUY_30M_VOL / S_SELL_30M_SHRINK` 应生成 action fact + `ActionEvent`。
- `TriggerPendingMarketData` 只生成 quality / pending，不生成 action fact。
- `stock_action_fact=488`，`index_action_fact=0`，`board_action_fact=0`。
- `common_action_event=488`，`common_action_quality_item=276`。
- `common_event_inbox=764 processed`，`common_event_consumer_checkpoint=615`。
- N5 outbox：`ActionEvent pending=479`，`HintEvent pending=9`，`RiskEvent=0`，`PositionEvent=0`。
- `common_position_state=0`，`common_position_event=0`。
- no real trade / no sim / no voice / no mobile / no N6。
- N2/N3/N4 authoritative runs unchanged。
- rollback_safe=true；rollback SQL=`sql/N5_current_real_action_execute_rollback.sql`。

禁止事项：不消费 N5 outbox、不进入 N6 execute、不启动 worker、不写 user/voice/sim/mobile/position/真实交易；不追加 N5 execute，除非另开 gate。

### T8A. N5 current-real dry-run / runner semantic implementation

状态：done；superseded by T8 execute passed。
目标：实现或修正 N5 current-real dry-run / runner，使其按当前 N4 real projection outbox 和新 N5 语义生成 dry-run 计划。

输入：T8 gate、当前 N4 real outbox、N5 action planner、N5 event contract、N5 rollback SQL 草案。
输出：N5 current-real dry-run report；N5 runner implementation；N5 rollback SQL；row-count guard evidence。
验收标准：dry-run 不消费 N4 outbox、不写 DB；只读取 allowlist source_run_id；denylist synthetic source_run_id；`TriggerMatched + projection_trace + MarketSnapshotUpdated` 生成正确 ActionEvent / HintEvent 计划；`TriggerPendingMarketData` 只生成 pending/quality；P0=0 后进入 N5 execute gate，并已由 T8 登记为 passed。
禁止事项：不追加执行 N5、不消费 N5 outbox、不写 position/sim/voice/mobile/N6、不启动 worker。

### T8B. N5 20260528 canonical action execute

状态：done for canonical run-once execute passed；superseded by 20260529 N6 canonical shadow projection passed。
目标：登记 20260528 canonical N5 action run-once execute，消费 20260528 canonical N4 outbox 并写入 canonical N5 action facts/events/outbox/inbox/checkpoint。

输入：

```text
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_REPORT.md
docs/N5_20260528_canonical_action_execute_report.json
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_CONTRACT.md
docs/N5_20260528_canonical_action_execute_contract.json
docs/N5_20260528_CANONICAL_ACTION_EXECUTE_PREFLIGHT.md
docs/N5_20260528_canonical_action_execute_preflight.json
sql/N5_20260528_canonical_action_execute_rollback.sql
```

输出：

```text
action_run_id = action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2
N5 canonical outbox pending counts
N5 inbox/checkpoint consumption proof
rollback_safe registration
subsequent gate = 20260529 N6 canonical shadow projection passed / T1K
```

验收标准：

- `common_action_run.status=passed`。
- P0/P1/P2=0/0/0。
- `common_action_quality_item=4602`。
- `stock_action_fact=4013`。
- `index_action_fact=18`。
- `board_action_fact=254`。
- `common_action_event=4285`。
- `common_event_outbox=4285`。
- `common_event_inbox=17774`。
- `common_event_consumer_checkpoint=2146`。
- N5 outbox：`ActionBlocked=4285 pending`，`ActionEligible=0`，`ActionExecuted=0`，`ActionSkipped=0`，delivered/delivering=0。
- canonical checks：legacy output events=0，`ActionEvent=0`，`HintEvent=0`，`RiskEvent=0`，`PositionEvent=0`。
- runtime signal：`B_BUY=2145`，`S_SELL=2140`。
- `BUY_HINT / SELL_HINT` trace-only。
- `action_mark NULL=4285`。
- `action_state blocked=4285`。
- `confirmation_status failed=4285`。
- N4 outbox status unchanged。
- N6 refs=0。
- position refs=0。
- user projection rows=0。
- worker_started=false。
- no voice/mobile/sim/real trade。
- rollback_safe=true；rollback SQL=`sql/N5_20260528_canonical_action_execute_rollback.sql`。

禁止事项：不消费 N5 outbox、不进入 N6 execute、不启动 worker、不写 user/voice/mobile/sim/position/真实交易；不追加 N5 execute，除非另开 gate。

### T9. N6 用户投影设计

状态：in progress；20260529 canonical shadow projection passed。
目标：维护 user projection contract / shadow projection lineage，明确 N6 只能投影 N5 canonical `ActionBlocked`，且继续禁止 voice/mobile/sim/真实交易。

输入：N5 标准事件合同、N5 20260529 canonical action execute report、N5 outbox pending=4309 ActionBlocked、N6 canonical projection execute contract/preflight、N6 shadow projection passed registration。
输出：N6 development design / schema / shadow projection registration。
验收标准：用户层只读投影，不读 trigger/action 裸表，不回写 N1-N5；shadow projection 不消费 N5 outbox、不更新 N5 outbox status、不启动 worker、不 push/voice/mobile。
禁止事项：不消费 N5 outbox，不追加 N6 execute，不播放语音，不启动前端，不写 mobile/sim/position/真实交易。

## 当前停止线

当前不应推进：

```text
N4/N5/N6 C3 MinuteBarClosed replay event execute beyond audit
EOD snapshot refresh execute / daily close execute
additional N4 real event execute / bounded worker
additional N5 action execute
N5 outbox consumption
additional N6 user projection execute beyond registered shadow
worker / long-running service
voice / mobile / sim / position / real trade
```

### T0. 固化 N2 condition_display_basis 架构决策

状态：done by documentation decision。
目标：采纳 N2 四表输出，明确 `condition_display_basis` 是 N2 生成的 N6 展示输入，不进入 N3/N4/N5。

输出：

```text
condition_basis          全量审计根
condition_pool           策略筛选后的条件行
minute_target_scope      N3/N4/N5 交易链路 scope
condition_display_basis  N6 展示输入
```

验收标准：

- N3/N4/N5 输入合同不变，仍只依赖 `minute_target_scope / market_data_subscription / 标准事件`。
- 正式写入 `condition_display_basis` 时必须生成新 N2 run_id。
- `condition_display_basis` 不命名为 `user_condition_basis`，不包含 user_id / device_id / voice / sim / action 执行字段。

禁止事项：

- 不在旧 active run 上补写 display_basis。
- 不让 N3/N4/N5 读取 display_basis。
- 不让 N6 直接 join trigger/action 裸表。

### T0.1 N2-Display schema / dry-run / overwrite 落地

状态：done。
结果：`stock/index/board_condition_display_basis` 已正式落到新 N2 active run `condition_layer_20260522_to_20260525_20260525102249_execute`。

最小步骤：

```text
N2-Display-1 schema review: done
N2-Display-2 migration: done
N2-Display-2b quality CHECK migration: done
N2-Display-3 dry-run: done
N2-Display-4 overwrite: done
N2-Web-3 8782 display basis 只读展示: todo
```

禁止事项：

- 未经确认不执行 migration。
- 未经确认不 overwrite。
- 不进入 N3/N4/N5/N6。

### T0.2 N3 subscription rebuild after N2-Display

状态：done。
目标：基于新的 N2 active run 重建 N3 `market_data_subscription` 控制层，不拉行情、不写行情事实、不进入 N4/N5。

输入：

```text
docs/N2_DISPLAY_OVERWRITE_EXECUTE_REPORT.md
new active N2 run = condition_layer_20260522_to_20260525_20260525102249_execute
old N2 run = condition_layer_20260522_to_20260525_20260525003855_execute -> superseded
```

输出：

```text
N3 subscription rebuild execute report
new market_data_subscription run aligned to condition_layer_20260522_to_20260525_20260525102249_execute: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
rollback SQL by N3 run_id
```

验收标准：

- 只读新 N2 `minute_target_scope`，不读取 `condition_display_basis` 作为 N3 输入。
- 写入范围仅限 N3 control 表：`common_market_data_run / quality_item / subscription_candidate / subscription / pull_plan`。
- 不拉行情，不写 realtime snapshot，不写 minute_bar，不写 common_event_outbox。
- 明确旧 N3 subscription `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute` 为 stale historical lineage。
- 历史 P1：`20260525 common_trade_calendar` detail row missing；该项已被后续 N3-B1 readiness PASS 取代，不再作为当前 blocker。

禁止事项：

- 不进入 N3-B1 execute。
- 不启动 worker。
- 不进入 N4/N5/N6。
- 不触碰旧系统。

### T0.3 N1 calendar detail gate for 20260525

状态：done/superseded by latest N3-B1 readiness PASS。
目标：补齐或确认 `common_trade_calendar` 中 `20260525` 的 detail row，让 N3-B1 readiness 可以判断交易日、开盘状态和 prev_trade_date。

输入：

```text
N3 rebuild report: docs/N3_AFTER_N2_DISPLAY_MARKET_DATA_SUBSCRIPTION_REBUILD_REPORT.md
P1: for_trade_calendar_row_exists actual=missing
for_trade_date = 20260525
expected prev_trade_date = 20260522
```

输出：

```text
N1 calendar detail fix / readiness report
20260525 common_trade_calendar detail row present
is_open / prev_trade_date / market session fields 可供 N3-B1 readiness 使用
latest readiness result: ready=true, calendar_row_count=1, is_trade_date=true
```

禁止事项：

- N3 不得自行修 N1 calendar。
- 不拉行情。
- 不写 N3 realtime snapshot。
- 不进入 N4/N5/N6。

### T0.4 N6 replay local canonical plan registration

状态：done / ready for manual use。
目标：登记 `/n6/replay` local-only replay 已支持 `fixture_v1` 与 `canonical_plan_v1`，并明确页面、API、artifact、Excel、安全边界和验收证据。该登记不授权任何 N3/N4/N5/N6 runtime execute、数据库写入、outbox/inbox/checkpoint 消费、worker、voice/mobile/sim/real trade。

输入：

```text
docs/N6_REPLAY_LOCAL_CANONICAL_PLAN.md
docs/replay/20260626/local_replay_20260626_154127_3a789ce6
docs/replay/20260626/local_replay_20260626_155558_035f00b6
tests.test_n6_local_replay
tests.test_n6_user_app
```

输出：

```text
/n6/replay route
replay jobs/timeline/N4/N5/Excel APIs
replay_engine_version whitelist:
  fixture_v1
  canonical_plan_v1
artifact path:
  docs/replay/<YYYYMMDD>/<job_id>/
timeline panel
N4/N5 debug columns
Excel lineage_and_safety sheet
local-only disclaimer and safety flags
```

验收标准：

- `/n6/replay` 可访问，默认 engine=`canonical_plan_v1`。
- 页面显示 `LOCAL REPLAY ONLY / No DB write / No outbox consumption / No checkpoint update`。
- timeline 面板存在，点击分钟后可过滤 N4/N5 表格。
- artifact 仅写 `docs/replay/<YYYYMMDD>/<job_id>/`，`job_id` 必须为 `local_replay_*`。
- `BUY_HINT / SELL_HINT` 可进入 `ActionEligible`。
- B2/Hint 不得成为 `ActionExecuted` final proof。
- `ActionExecuted` final proof 只来自 N3T_C1_CLOSED / N3T action-confirmation metric；N3P 只能作为 N4 trigger proof 或 replay trace。
- 20260626 smoke job=`local_replay_20260626_154127_3a789ce6` preserved as artifact proof。
- final acceptance job=`local_replay_20260626_155558_035f00b6` preserved as manual-use proof。
- DB no mutation proof：
  `common_market_data_* / common_trigger_* / common_action_* / common_event_*` unchanged。

禁止事项：

- 不得把 local replay artifact 当作 production lineage 或 production run_id。
- 不得写 `common_market_data_* / common_trigger_* / common_action_* / common_event_*`。
- 不得消费生产 outbox/inbox/checkpoint。
- 不得进入 N6 delivery / voice / mobile / sim / real trade。
- 若发现主链路问题，只能另开对应 N3/N4/N5 patch gate 修复。

下一步：

- 当前可人工使用 / 演示。
- 如需更真实历史全量源，另开 `N6_REPLAY_HISTORICAL_SOURCE_CONNECTOR_DESIGN_GATE`。
- 如需 shadow DB，另开独立隔离设计 gate；不得混入当前 local-only 模式。

## N3N6Q 专项任务

### T-N3N6Q-0. Cross-layer contract registration

状态：`ready_for_review`。

验收：

- authority matrix 明确 N3N6Q 只拥有外部股票报价与 source identity 校验。
- QuoteIdentity 输入仅 `identity_key / exchange / stock_code`。
- QuoteBatch v1 字段、质量枚举、批量上限与 fail-closed 规则已冻结。
- A1/B1/B2/C1/N3P/N3T 和全部现有 poller/worker/schema/event infrastructure 均为 denylist。
- N6 独占 scope、调度、trade_date/freshness、持久化和止损策略。
- A轨/admin/status、页面和浏览器不调用 N3N6Q。

### T-N3N6Q-1. Provider and fake-adapter gate

状态：`not_started`；`layer_role=N3_market_data`。

精确候选文件：

```text
src/ashare_v3/n3n6q/__init__.py
src/ashare_v3/n3n6q/contract.py
src/ashare_v3/n3n6q/provider.py
src/ashare_v3/n3n6q/mootdx_adapter.py
tests/test_n3n6q_quote_provider.py
```

禁止修改任何现有文件；provider gate 不拉行情、不写 DB、不生成事件。

### T-N3N6Q-2. Read-only live probe

状态：`blocked_until_T-N3N6Q-1_reviewed`；`layer_role=N3_market_data`。

只验证 Mootdx SH/SZ/BJ 身份映射、每批最多 80、响应 code/market、价格和 source time；不写 DB。BJ 映射未证明时必须 `not_ready`。

### T-N3N6Q-3. N6 quote persistence and stop-loss chain

状态：`blocked_until_T-N3N6Q-2_reviewed`；`layer_role=N6_user`。

按独立 gate 依次实现 N6 quote schema、one-shot、portfolio 估值、首日止损冻结、proposal evaluator、confirm transaction。任何 gate 不自动授权真实交易、券商、语音、N4/N5 修改或 runtime 发布。
