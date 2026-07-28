# A股监控系统 v3 Roadmap

更新日期：2026-07-22
范围：总控阶段路线图。本文档只描述状态和 gate，不授权任何 execute、数据库写入、worker 或真实交易。

## 状态总览

### 2026-07-28 N6 B轨治理瘦身路线

状态：三通道治理 implementation ready；R3 已形成单一离线候选，当前生产服务
血缘仍为 `FRAGMENTED`，`database_state=NOT_READ`、
`deployment_authorized=false`，本阶段不部署。

```text
R0 冻结当前 Web / quote writer / executor / stop-loss 基线
-> R1 建立 codex/n6-btrack-integration 唯一候选发布主线
-> R2 登记 L1 n6_btrack_delivery_l1_web_readonly_v1
      / L2 n6_btrack_delivery_l2_n6_business_v1
      / L3 n6_btrack_delivery_l3_virtual_runtime_v1
-> R3 独立完成 n6_btrack_service_lineage_convergence_v1
-> R4 从新需求开始停止新增一次性 policy 和孤立发布血缘
-> R5 逐个审计并归档已完成工作树
-> R6 以 L1/L2 分类实施筛选中心改造
-> R7 完成 n6_btrack_preserved_capability_blob_lock_forward_scope_closeout_v1
-> R8 n6_btrack_canonical_integration_fast_forward_v1（ff-only）
```

R0-R2 只产生 Git/文档/静态测试，不连接数据库或操作服务。R3 使用
`N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1` 解决两个不同 `087`
migration 文件的完整身份冲突，并精确导入 stop-loss 087/088 八文件；不得仅按
migration 数字静默覆盖。R3 当前只生成统一候选 commit/tree 和离线测试证据，
不生成或部署 Release。R5 不允许按目录名或年龄批量删除，必须逐
工作树证明无 tracked、untracked、ignored 残留。L1 普通页面需求目标最多两个
mutating gate；L2/L3 继续保留 migration、rollback、权限、资金和 runtime
审计。

R7 已把历史 preserved-capability 锁限定为冻结 commit `2eeb05a5…`，旧
`N6_B_TRACK_MIGRATION_IDENTITY_RECONCILIATION_V1` 保持 byte-for-byte 不变；
L1/GET-only 功能候选
`75470cc4ee06e94c79fb925b74e28bb7e2f5a617` 的原四文件 path/blob/SHA256 已由
append-only artifact 登记，分类为 `POST_REVIEW_PASS`。该 closeout 未部署、
未访问数据库、未执行 migration 或服务操作。下一 gate 仅允许从 canonical
baseline `09718870086ff2611b7e19ab741b636bae542d97` 对本 closeout 单一提交链
执行 `n6_btrack_canonical_integration_fast_forward_v1` ff-only。
Focused/定向回归为 21/21 与 303/303；完整 `test_n6*.py` baseline/candidate
为 1743（22 failures / 41 errors / 22 skipped）和 1756（24 / 41 / 22）。
`FUNCTIONAL_NEW_FAIL=0`、历史/环境 baseline 签名漂移=0；额外两项是冻结 N6
AI knowledge bundle 的历史 artifact hash 失败，未扩展 allowlist 改写 manifest。

### 2026-07-22 N6 B 轨 virtual-executor 前向路线

本节只登记 `N6_B_TRACK_VIRTUAL_EXECUTOR_GOVERNANCE_V1` 的后续 gate 顺序，不授权本文件所在会话执行任何 runtime：

```text
G1 runtime_control 治理规则单一提交
-> G2 N6_user migration + immutable release deployment
-> G3 N6_user bounded explicit proposal smoke
-> G4 confirmed 队列精确治理 + bootout 停用方案冻结
-> G5 N6_user persistent virtual-executor enablement
-> G6 自然周期审计与异常停用验证
```

每一阶段均要求用户显式授权、版本化合同、preflight、精确 rollback 和精确影响范围。G3 必须 PASS，G4 必须完成，才允许进入 G5。持续 executor 只消费两阶段人工确认的 N6 虚拟申请，并在 claim/apply 两层 fail-closed 校验开放交易日、交易时段、两分钟报价、本人主体/账户/范围、现金、100 股取整和 T+1。真实券商、真实订单、自动申请、跨层写入和 AI autonomous real trading 不在路线内。

此前路线图中的“不授权 N6 execute/worker”均是对应历史 gate 的边界证据，继续保留；本节仅前向 supersede 生效后的 N6 B 轨虚拟执行器权限，不扩大到其他层或其他 worker。

| 阶段 | layer_role | 状态 | 当前判断 |
|---|---|---|---|
| Runtime Control | `runtime_control` | v0.2 dashboard smoke passed | pipeline state machine / dashboard v0 / command registry / rollback registry / timeline 已有 schema 草案和只读 CLI；dashboard v0.2 已新增 20260602 action-confirmation timeline detector，9 阶段 all PASS，N5 pending outbox=ActionExecuted 4 / ActionBlocked 1，N6 shadow rows=1/5/5/5；不授权 execute、rollback、worker 或 N1-N6 contract 修改 |
| N1 入库层 | `N1_ingestion` | done / 20260603-20260604 catch-up passed | schema、每日增量、quality gate、Parquet manifest、20260522 日增和 000001.SH 历史修复均已有报告；20260529 official daily 与 condition source activation 已 POST_REVIEW_PASS；`stock_financial_20260529_v2` canonical metrics 已 POST_REVIEW_PASS，并成为 active stock_financial；20260602 official daily 与 condition source activation 已 POST_REVIEW_PASS，并已被 N2 20260602 condition layer run 消费；`common_trade_calendar(20260603)` fix-forward repair 已 passed，B1 calendar blocker 已解除；20260604/20260605 calendar patch 均 POST_REVIEW_PASS；20260603/20260604 official daily + condition source catch-up 已 passed，单日 rows stock/index/board daily=5511/9/428，stock_daily_basic/financial=5511/5511，index/board membership=12841/56960，quality P0/P1/P2=0/0/0 |
| N2 条件层 | `N2_condition` | done / 20260603-20260604 catch-up passed | 20260602 -> 20260603 N2 condition layer 已 passed_active：active run `condition_layer_20260602_source_20260602_v1`，canonical policy=8782 console broad policy，P0/P1/P2=0/9/3，row_mismatches={}，rollback_safe=true；20260603 -> 20260604 run `condition_layer_20260603_source_20260603_v1` 已 passed_active，P0/P1/P2=0/6/3，scope stock/index/board=4201/20/892；20260604 -> 20260605 run `condition_layer_20260604_source_20260604_v1` 已 passed_active，P0/P1/P2=0/6/3，scope stock/index/board=4186/20/912；20260529 -> 20260601 N2 level score v6 与 20260528 -> 20260529 target v5 仍 preserved |
| N3 实时行情层 | `N3_market_data` | in progress / 20260605 B2 realtime projection post-review passed | 20260529 subscription、A1 previous_day_minute preload、B1 pre-open、B1 live1 fact-only、B1 live2 standard outbox snapshot 均已 passed；20260603 subscription control rows、A1 previous-day minute preload、calendar repair 与 B1 realtime snapshot fact-only retry 均已 passed，B1 snapshot_run_id=`realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`，rows stock/index/board/total=1963/83/428/2474，P0/P1/P2=0/1/0，writes_outbox=false，rollback_safe=true；新增 catch-up lineage 已完成 N3 subscription/A1：20260604 subscription `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` passed，candidate/subscription/pull_plan=5757/3041/9，A1 preload rows=77280；20260605 subscription `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed，candidate/subscription/pull_plan=5802/3073/9，A1 preload rows=82080；20260605 staged refresh 已完成 B1 live2 fact-only `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` rows=1952/9/428/2389，P0/P1/P2=0/0/0，writes_outbox=false，rollback_safe=true；C1 current-minute `today_minute_bar_1m_20260605_until_1037__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` rows=19028/134/3752/22914，latest_closed_minute=2026-06-05T10:37:00+08:00，P0/P1/P2=0/0/0，duplicate minute key groups=0/0/0，rollback_safe=true；C1 later-minute `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` rows=33228/234/6552/40014，latest_closed_minute=2026-06-05T11:27:00+08:00，objects processed/passed=342/342，P0/P1/P2=0/0/0，duplicate minute key groups=0/0/0，rollback_safe=true；B2 stock/index lineage expansion control-row run `market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，candidate/subscription/pull_plan=6696/3350/4，P0/P1/P2=0/2/0，market_data_pulled=false，market_data_fact_written=false，rollback_safe=true；A1 expansion `previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，minute/status totals=402000/1675，P0/P1/P2=0/1/0，rollback_safe=true；C1 expansion `today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1` passed，minute rows=195975，P0/P1/P2=0/0/0，rollback_safe=true；B2 realtime projection `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` passed，rows stock/index/board/total=1952/9/428/2389，ready/not_ready=969/1420，P0/P1/P2=0/4/0，fact-only trace compatible rows=2389，writes_outbox=false，outbox/inbox/checkpoint refs=0/0/0，N4/N5/N6 refs=0/0/0，rollback_safe=true；已由 20260605 N4 matched-only execute post-review 消费；下一步允许 N5 action readiness / dry-run gate，不允许直接 N5 execute 或消费 outbox |
| N4 触发层 | `N4_trigger` | in progress / 20260605 matched-only execute post-review passed | 20260525 real projection matcher execute、N4-C3 replay audit execute、20260528 canonical trigger execute、20260529 canonical trigger execute、20260529 live2 canonical trigger execute、20260602 action-confirmation metric business execute、20260603 matcher-fix canonical trigger execute 均已 preserved as historical evidence；20260603 N4 v4 run `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` 已 passed，state/match/outbox=863/863/863，TriggerMatched pending=863，rollback_safe=true；20260605 matched-only run `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` 已 POST_REVIEW_PASS，P0/P1/P2=0/0/0，state/match/outbox=1537/1537/1537，TriggerMatched pending=1537，TriggerPendingMarketData/TriggerStateChanged=0/0，B_BUY/S_SELL=1286/251，normal/30m_volume/30m_shrink=1262/87/188，invalid N5 entry=0，N5/N6 refs=0/0，rollback_safe=true |
| N5 动作层 | `N5_action` | in progress / 20260603 N5 v1 market-action-confirmation preserved | 20260525 current-real action run-once execute、20260528 canonical action run-once execute、20260529 canonical action execute、20260529 live2 canonical action execute、20260602 action-confirmation metric execute、20260603 canonical action execute after status fix 均已 preserved as historical evidence；当前 20260603 N5 v1 run `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` 已 passed 并 preserve-only，P0/P1/P2=0/0/0，ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped=863/0/0/0，blocked_reason price_confirmation_failed/amount_confirmation_failed/metric_missing=838/25/0，N5 outbox pending/delivered/delivering=863/0/0，N4 outbox unchanged TriggerMatched pending=863，fresh DB proof 显示 N6/user refs 已存在 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，position refs=0/0；N5 rollback 不再按 downstream=0 路线，若需 rollback 必须先进入 N6 rollback gate |
| N6 用户层 | `N6_user` | in progress / Phase 3 admin virtual account seed passed | 20260529 canonical shadow projection 已 passed；20260602 action-confirmation metric shadow projection 已 passed；20260603 N5 v1 market-action-confirmation downstream fresh DB refs 已存在且 `user_projection_run.status=passed`，source_action_run_id=`action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`，P0/P1/P2=0/5/2，input/output=863/863，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，queued_only path，N5 outbox remains pending ActionBlocked=863，未见 position refs；20260603 N6 existing-run post-review artifact 已 recovery passed；035 delivery notification queue schema alignment migration 已 passed；N6 delivery noop preview materialization 曾 passed，后续 rollback passed，target preview rows=0，source queued_only=863，N5 outbox ActionBlocked pending=863，真实 delivery/push/voice/mobile/sim/position/real trade 均未触发；20260603 final read-only lineage dashboard review 已 closeout，当前终点=N6 shadow projection / queued_only preserved；read-only dashboard artifact=`docs/dashboard/20260603_FINAL_READ_ONLY_LINEAGE_DASHBOARD.md` / `docs/dashboard/20260603_final_read_only_lineage_dashboard.json`；B 轨 Phase 3 admin virtual account seed 已 POST_REVIEW_PASS，seed_run_id=`n6_phase3_virtual_account_seed_20260605_v1`，n6_virtual_account/cash_ledger/cash_snapshot=1/1/1，virtual_account_id=1，principal=admin，initial_cash=1000000.0000 CNY，current_cash_snapshot_id=1，order/trade/position/position_event/pnl=0，user_sim_account 既有 3 行但非本次写入，user_sim_order/trade/position=0/0/0，outbox/inbox/checkpoint refs=0/0/0，worker/delivery/push/voice/mobile/sim/position/real_trade=false；下一步只允许 Phase 3 virtual account operation policy / order proposal design 或只读 dashboard/lineage review，真实 delivery/push/sim/position/real trade 必须另开 gate |

## Runtime Control

状态：v0.2 dashboard smoke passed。

已完成：

- `runtime_pipeline_run` / `runtime_pipeline_stage` schema 草案。
- `WAIT_MANUAL_CONFIRM` 状态定义。
- execute command registry 和 rollback registry 登记模型。
- pipeline timeline 和 dashboard v0 只读 CLI。
- nightly runtime SOP v0。
- dashboard v0.2 20260602 action-confirmation timeline detector / API / Web smoke passed：
  `action_confirmation_runtime_v0_2`，9 stages all PASS，N5 pending outbox=`ActionExecuted 4 / ActionBlocked 1`，
  N6 shadow rows=`1/5/5/5`，rollback registry N2-N6 complete，routes=`GET/HEAD` only。

Entry gate：

- 明确 `layer_role=runtime_control`。
- 本会话只做 orchestration / dashboard / registry / timeline。
- 不修改 N1-N6 execute contract。

Exit gate：

- dashboard 只读输出。
- command registry 只登记，不执行。
- rollback registry 只登记，不执行。
- side effects 全部为 false。

Rollback gate：

- schema 草案对应 `sql/021_runtime_pipeline_control_rollback.sql`。
- 未经单独 migration 授权，不执行 schema 或 rollback SQL。

Blocked / caution：

- runtime_control 不得执行 nightly run。
- runtime_control 不得消费 N3/N4/N5 outbox。
- runtime_control 不得启动 worker。
- 推进某个 stage execute 必须切换到对应 N1-N6 layer_role。

## N1 入库层

状态：done。

已完成：

- PostgreSQL schema 草案和执行基础表。
- `common_active_source_version`、quality gate、rollback 策略。
- 20260522 每日增量真实执行验收。
- `index:SH:000001` 历史窗口修复到 `index_daily_20260522_v4`。
- Parquet data lake / manifest 规则。
- 20260528 official daily ingestion passed：stock/index/board daily fact = 5506/83/428，total=6017，active source_version = `stock_daily_20260528_v1` / `index_daily_20260528_v1` / `board_daily_20260528_v1`，P0/P1/P2=0/19/0。
- 20260528 condition source activation passed：stock_daily_basic=5506，stock_financial_metrics_fact=5506，index_membership_fact=12841，board_membership_fact=56958，total=80811，active source_version = `stock_daily_basic_20260528_v1` / `stock_financial_20260528_v1` / `index_membership_20260528_v1` / `board_membership_20260528_v1`，P0/P1/P2=0/3/1。
- 20260528 N1 boundary passed：outbox/inbox/checkpoint delta=0/0/0，Parquet not written，N2-N6 not entered，worker_started=false，old_system_touched=false，real_trading=false。
- 20260529 stock_financial canonical metrics v2 passed：`source_batch_id=stock_financial_canonical_20260529_v1`，`source_version=stock_financial_20260529_v2`，previous_source_version=`stock_financial_20260529_v1`，financial_metric_version=`financial_metric_v1`，stock_financial_metrics_fact v2 rows=5506，common_quality_gate_result rows=13，P0/P1/P2=0/8/2，active stock_financial 20260529 -> `stock_financial_20260529_v2`。
- 20260529 stock_financial v2 boundary at N1 post-review time：outbox/inbox/checkpoint delta=0/0/0，condition base refs to v2=0，Parquet not written，N2-N6 not entered，worker_started=false，old_system_touched=false，real_trading=false，rollback_safe=true；rollback SQL=`sql/N1_stock_financial_canonical_metrics_20260529_rollback.sql`。后续该 source_version 已由 N2 `condition_layer_20260529_source_20260529_v2` 消费。
- 20260602 official daily ingestion passed：`source_batch_id=official_daily_ingest_20260602_v1`，stock/index/board daily fact = 5507/83/428，total=6018，metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/31/3，active source_version = `stock_daily_20260602_v1` / `index_daily_20260602_v1` / `board_daily_20260602_v1`，source validation P0/P1/P2=0/19/0，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true；rollback SQL=`sql/N1_official_daily_20260602_ingestion_rollback.sql`。
- 20260602 condition source activation passed：`source_batch_id=condition_source_activation_20260602_v1`，stock_daily_basic=5507，stock_financial_metrics_fact=5507，index_membership_fact=12841，board_membership_fact=56960，total=80815，metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/15/4，active source_version = `stock_daily_basic_20260602_v1` / `stock_financial_20260602_v1` / `index_membership_20260602_v1` / `board_membership_20260602_v1`，P0/P1/P2=0/2/1，P0 failed=0，outbox/inbox/checkpoint delta=0/0/0，official daily untouched=true，N2/N3/N4/N5/N6 refs=0/0/0/0/0，worker/parquet/delivery/notification/real_trade=false，rollback_safe=true；rollback SQL=`sql/N1_condition_source_20260602_activation_rollback.sql`。
- 20260603 trade calendar repair passed：`source_batch_id=trade_calendar_20260603_patch_v1`，`source_version=trade_calendar_20260603_patch_v1`，`common_trade_calendar(20260603)=1`，is_open=true，prev_trade_date=20260602，next_trade_date=20260604，active source_version `common / trade_calendar / SSE:20260603 -> trade_calendar_20260603_patch_v1`，metadata common_ingest_batch/common_quality_gate_result/common_active_source_version=1/11/1，persisted quality P0 passed=11，outbox/inbox/checkpoint delta=0/0/0，B1/N4/N5 refs=0/0/0，N2/N3/A1 refs remain=1/2/1，rollback SQL=`sql/N1_trade_calendar_20260603_patch_rollback.sql`。

Entry gate：

- 明确 `layer_role=N1_ingestion`。
- 只处理外部事实、source version、归档、回滚、审计。
- 真实执行必须有用户明确授权和环境确认。

Exit gate：

- stock/index/board 物理分表。
- identity_key coverage 100%。
- P0 quality gate = 0。
- source_batch_id / source_version 可追溯。
- Parquet manifest 可回滚。

Rollback gate：

- 按 `source_batch_id` 删除本批写入。
- 恢复 previous active source version。
- Parquet 通过 manifest 控制 active，不静默物理删除。

## N2 条件层

状态：done / 20260602 condition layer passed。

当前权威 run：

```text
condition_layer_20260602_source_20260602_v1
```

current source-date active run:

```text
condition_layer_20260602_source_20260602_v1 -> passed_active for source_trade_date 20260602 / for_trade_date 20260603
```

current source-date superseded run:

```text
condition_layer_20260529_source_20260529_v5 -> superseded after level score v6 active supersede
condition_layer_20260529_source_20260529_v4 -> superseded after secondary-anchor v5 active supersede
condition_layer_20260529_source_20260529_v3 -> superseded after anchor-segment v4 active supersede
condition_layer_20260529_source_20260529_v2 -> superseded after target-machine v3 active supersede
condition_layer_20260529_source_20260529_v1 -> superseded after financial canonical v2 active supersede
```

previous source-date active run:

```text
condition_layer_20260528_source_20260528_v5 -> active for source_trade_date 20260528 / for_trade_date 20260529
condition_layer_20260528_source_20260528_v4 -> superseded after target price v5 active supersede
condition_layer_20260528_source_20260528_v3 -> superseded / preserved for audit
condition_layer_20260528_source_20260528_v2 -> superseded
condition_layer_20260528_source_20260528_v1 -> downstream lineage preserved
```

历史 N2-Display active run：

```text
condition_layer_20260522_to_20260525_20260525102249_execute -> historical downstream lineage input
condition_layer_20260522_to_20260525_20260525003855_execute -> superseded
```

已完成：

- `condition_basis`、`condition_pool`、`minute_target_scope`。
- N2 四表输出方案已落地，`condition_display_basis` 已作为 N6 展示输入正式写入。
- 固定 9 指数 ready。
- `period_trigger_baseline_json` 贯通 basis / pool / scope。
- N2-Display overwrite 验收通过，active passed run count = 1。
- 20260528 -> 20260529 condition layer execute passed，run_id = `condition_layer_20260528_source_20260528_v1`。
- 20260528 active status：`passed_active`，passed_active_count=1，P0/P1/P2=0/6/3，quality_rows=106。
- 20260528 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，monitor_target=5506/83/428，condition_display_basis=5506/83/428。
- 20260528 canonical signal audit passed=true，deprecated_signal_rows=0，outbox/inbox/checkpoint delta=0/0/0。
- 20260528 boundary：market_data_pulled=false，N3/N4/N5/N6 entered=false，worker_started=false，rollback_safe=true。
- 027 N2 symmetry target price canonical compatibility migration passed：touched tables=12 N2 tables，new canonical fields exist=true，CHECK constraints validated=true，locked_target_price / target_lock_status absent=true。
- 027 boundary：business row count delta=0，outbox/inbox/checkpoint delta=0/0/0，new fields non-null count=0，N2 writer not executed，backfill not executed，N3/N4/N5/N6 not entered，worker_started=false。
- 027 rollback_safe=true；rollback SQL=`sql/027_condition_symmetry_target_price_compatibility_rollback.sql`。
- 20260528 -> 20260529 N2 canonical condition v2 active lineage supersede execute passed：run_id=`condition_layer_20260528_source_20260528_v2`，status=`passed_active`，previous active v1=`condition_layer_20260528_source_20260528_v1`，v1.status=`superseded`，v1 rows and downstream refs preserved=true。
- v2 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，condition_display_basis=5506/83/428，monitor_target=5506/83/428。
- v2 quality：quality_item=103，P0/P1/P2=0/3/3。
- v2 canonical target checks：alias mismatch=0，negative numeric fields=0，forbidden fields=0；first failed attempt rolled back due negative reference_target_price CHECK；writer fixed so negative canonical target numeric fields write NULL and raw negative value is preserved only in trace。
- v2 boundary：N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v2_canonical_target_rollback.sql`。
- 20260528 -> 20260529 N2 display scope alignment v3 preserved/superseded：run_id=`condition_layer_20260528_source_20260528_v3`，previous N2 run=`condition_layer_20260528_source_20260528_v2`，v2.status=`superseded`，后续已被 v5 active supersede。
- v3 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，condition_display_basis=2021/9/127，monitor_target=5506/83/428。
- v3 quality/checks：common_condition_quality_item=103，P0/P1/P2 failed=0/0/0，display duplicate groups=0/0/0，alias mismatch=0，negative numeric rows=0，locked_target_price / target_lock_status absent=true。
- v3 boundary：downstream refs=0，outbox/inbox v3 refs=0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql`。
- 20260528 -> 20260529 N2 symmetry target price alignment v5 passed_active：active N2 run=`condition_layer_20260528_source_20260528_v5`，previous active v4=`condition_layer_20260528_source_20260528_v4`，v4.status=`superseded`，passed_active_count=1。
- v5 000027 golden：main_up_anchor=W，up_reference_period=D，up_amplitude=1.17，up_base_price=7.25，buy_target_price=8.42，reference_target_price=8.42。
- v5 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4271/169/875，minute_target_scope=4251/169/875，condition_display_basis=2011/83/428，monitor_target=5506/83/428。
- v5 quality/checks：common_condition_quality_item=103，P0/P1/P2=0/3/3，deprecated signal rows=0，alias mismatch=0，invalid reference period=0，locked_target_price / target_lock_status absent=true。
- v5 boundary：outbox/inbox refs=0/0，N3/N4/N5 refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql`。
- 20260529 -> 20260601 N2 condition layer v1 historical passed_active：run_id=`condition_layer_20260529_source_20260529_v1`，source_trade_date=20260529，for_trade_date=20260601，prev_trade_date=20260529；该 run 执行时基于 N1 active stock_financial=`stock_financial_20260529_v1`，后续已被 financial canonical v2 active supersede 标记为 `superseded`。
- 20260529 v1 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4342/187/942，minute_target_scope=4323/187/942，condition_display_basis=1973/83/428，monitor_target=5506/83/428。
- 20260529 v1 quality/checks：common_condition_quality_item=109，P0/P1/P2=0/9/3，canonical signal audit passed，deprecated_signal_rows=0，noncanonical_signal_rows=0。
- 20260529 v1 boundary：outbox/inbox/checkpoint delta=0/0/0，N3/N4/N5 downstream refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260529_rollback.sql`。
- 20260529 -> 20260601 N2 financial canonical v2 active supersede passed：run_id=`condition_layer_20260529_source_20260529_v2`，曾为 `passed_active`，后续已被 target-machine v3 active supersede 标记为 `superseded`；source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529。
- 20260529 v2 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428。
- 20260529 v2 quality/checks：common_condition_quality_item=106，P0/P1/P2=0/6/3，basis/pool/scope/display financial mismatch=0/0/0/0，canonical_financial_pass_through_mismatch=0，finance_sector_warning_rows=120，pre_revenue_warning_rows=1。
- 20260529 v2 boundary：outbox/inbox/checkpoint delta=0/0/0，N3/N4/N5 refs for v2=0/0/0，market_data_pulled=false，downstream_layers_touched=false，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260529_financial_v2_rollback.sql`。
- 20260529 -> 20260601 N2 symmetry target price target-machine v3 active supersede passed/preserved：run_id=`condition_layer_20260529_source_20260529_v3`，v3.status=`superseded after condition_layer_20260529_source_20260529_v4`，v2.status=`superseded`，source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529。
- 20260529 v3 golden：000543 皖能电力 main_up_anchor=W，up_reference_period=D，A段=20260506->20260529，segment_low/high=8.09/9.80，amplitude=1.71，trend_break_date=20260526，base_window=20260527->20260529，base_price=9.11，buy_target_price/reference_target_price=10.82；000027 深圳能源 buy_target_price/reference_target_price=8.45。
- 20260529 v3 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428。
- 20260529 v3 quality/checks：common_condition_quality_item=106，P0/P1/P2=0/6/3，outbox/inbox/checkpoint delta=0/0/0，v3 downstream refs=0，market_data_pulled=false，downstream_layers_touched=false，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql`。
- 20260529 -> 20260601 N2 anchor-segment alignment v4 passed/preserved：run_id=`condition_layer_20260529_source_20260529_v4`，previous active v3=`superseded`，后续已被 v5 active supersede。
- 20260529 v4 row counts aligned：condition_basis stock/index/board=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428。
- 20260529 v4 golden：000600=12.93，000543=10.82，000027=8.45。
- 20260529 v4 boundary：P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql`。
- 20260529 -> 20260601 N2 secondary-anchor v5 passed/preserved：run_id=`condition_layer_20260529_source_20260529_v5`，previous active v4=`superseded`，后续已被 v6 active supersede，P0/P1/P2=0/6/3。
- 20260529 v5 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106。
- 20260529 v5 boundary：N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql`。
- 20260529 -> 20260601 N2 level score v6 passed_active：active N2 run=`condition_layer_20260529_source_20260529_v6`，previous active v5=`superseded`，P0/P1/P2=0/6/3。
- 20260529 v6 row counts：condition_basis stock/index/board=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106。
- 20260529 v6 level score checks：level_score_ok=true，row_match=true，golden 000543/000600/300327 level_score_up/down=3124/0、3124/0、2999/125，level score missing/invalid rows=0。
- 20260529 v6 boundary：N3/N4/N5 refs=0/0/0，outbox/inbox/checkpoint delta=0/0/0，N3 not automatically rebuilt，N4/N5/N6 not entered，market_data_pulled=false，worker_started=false，rollback_safe=true；rollback SQL=`sql/N2_level_score_20260529_v6_rollback.sql`。
- 20260602 -> 20260603 N2 condition layer passed_active：active N2 run=`condition_layer_20260602_source_20260602_v1`，canonical policy=`8782_console / n2_default_policy / v4`，policy_hash=`ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576`，P0/P1/P2=0/9/3，common_condition_quality_item=109。
- 20260602 row counts：condition_basis stock/index/board=5507/83/428，condition_pool=4182/168/890，minute_target_scope=4164/168/890，condition_display_basis=1963/83/428，monitor_target=5507/83/428。
- 20260602 artifact alignment：dry-run / contract / preflight / execute post-review 已与 execute runner policy loader 对齐，expected rows = actual rows，row_mismatches={}，post-review=`POST_REVIEW_PASS`。
- 20260602 boundary：outbox/inbox/checkpoint refs=0/0/0，N3/N4/N5/N6 refs=0/0/0/0，market_data_pulled=false，downstream_layers_touched=false，rollback_safe=true；rollback SQL=`sql/N2_condition_layer_20260602_rollback.sql`。

Entry gate：

- N1 active source version ready check passed。
- 不外拉 Tushare / Mootdx。
- 不修 N1 fact。

Exit gate：

- `condition_basis` 全量可审计。
- `condition_pool` 策略可解释。
- `minute_target_scope` 只从 pool 生成，作为 N3/N4/N5 交易链路 scope。
- `condition_display_basis` 只从同一 run 的 basis/pool/scope 派生，作为 N6 只读展示输入，不进入 N3/N4/N5。
- `required_period_not_ready_rows = 0`。

Rollback gate：

- 使用对应 overwrite rollback SQL 删除新 run。
- 恢复上一条 `common_condition_run` 为 passed。
- 不影响 N1 active source version。
- 20260528 rollback SQL：`sql/N2_condition_layer_20260528_rollback.sql`；N3/N4/N5 downstream refs 为 0 时 rollback_safe=true。

Next gate：

- N3 subscription 20260529 execute 已 passed on previous v1 lineage and remains preserved。
- 20260529 A1 previous_day_minute preload 已 passed。
- 20260529 B1 pre-open realtime snapshot fact-only 已 passed。
- 20260529 B1 live1 realtime snapshot fact-only 已 passed。
- 20260529 B1 live2 standard outbox snapshot 已 passed。
- 20260529 N4 canonical trigger execute 已 passed。
- 20260529 N4 live2 canonical trigger execute 已 passed。
- 20260529 N5 canonical action execute 已 passed。
- 20260529 N6 canonical shadow projection 已 passed。
- 027 N2 symmetry target schema migration 已 passed；N2 canonical condition v2 active lineage supersede execute 已 passed；N2 display scope alignment v3 已 superseded by v5；N2 symmetry target price alignment v5 已 passed_active；20260529 -> 20260601 N2 condition layer v1 已 preserved/superseded；20260529 -> 20260601 N2 financial canonical v2 已 preserved/superseded；20260529 -> 20260601 N2 symmetry target price target-machine v3 已 preserved/superseded；20260529 -> 20260601 N2 anchor-segment alignment v4 已 preserved/superseded；20260529 -> 20260601 N2 secondary-anchor v5 已 preserved/superseded；20260529 -> 20260601 N2 level score v6 已 passed_active。
- 当前 20260529 盘中 N3/N4/N5/N6 仍在旧 `condition_layer_20260528_source_20260528_v1` lineage，不自动 rebuild。
- 20260602 N2 condition layer 已 passed_active；20260603 N3 subscription control rows、A1 previous-day minute preload、`common_trade_calendar(20260603)` repair、B1 realtime snapshot fact-only retry、N4 trigger context rebuild、matcher fix 后 N4 canonical trigger execute、status persistence fix 后 N5 canonical action retry execute、N4 v4 execute、N5 v1 market-action-confirmation execute、N6 v1 shadow projection post-review recovery、035 N6 delivery schema alignment migration、N6 delivery noop preview rollback 与 20260603 read-only lineage closeout 均已 passed；当前 N5 v1 outbox pending ActionBlocked=863，N4 v4 outbox unchanged TriggerMatched pending=863，N6 delivery preview target rows=0，N6 shadow/source queue rows=1/863/863/863 preserved；20260603 read-only dashboard artifact 已生成在 `docs/dashboard/20260603_FINAL_READ_ONLY_LINEAGE_DASHBOARD.md` 与 `docs/dashboard/20260603_final_read_only_lineage_dashboard.json`。20260603/20260604 daily catch-up readiness artifact 已生成在 `docs/DAILY_PIPELINE_CATCHUP_20260603_20260604_READINESS_REPORT.md` 与 `.json`；20260604 calendar patch 已 POST_REVIEW_PASS；20260605 calendar patch preflight/final gate 已 PASS；20260605 N3 B1 live2 + C1 current/later-minute staged post-review 已 PASS，B1 rows=1952/9/428/2389，C1 current rows=19028/134/3752/22914，C1 later rows=33228/234/6552/40014；B2 stock/index lineage expansion control-row execute 已 PASS，candidate/subscription/pull_plan=6696/3350/4，P0/P1/P2=0/2/0，未写行情事实；A1/C1 expansion staged execute 已 PASS，A1 minute/status=402000/1675，C1 minute=195975，P0/P1/P2=0/1/0 and 0/0/0，duplicate minute key groups=0/0/0；B2 realtime projection execute 已 PASS，rows=1952/9/428/2389，ready/not_ready=969/1420，P0/P1/P2=0/4/0，fact-only trace compatible=2389，writes_outbox=false，outbox/inbox/checkpoint refs=0/0/0，N4/N5/N6 refs=0/0/0；允许 runtime_control read-only lineage/dashboard review、N5 action readiness / dry-run gate，或另开真实 delivery/push readiness gate。runtime_control 不直接执行 N1/N2/N3/N6，不消费 N4/N5 outbox，不启动 worker。
- 20260605 N4 matched-only execute 已 POST_REVIEW_PASS：execute_run_id=`trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`，state/match/outbox=1537/1537/1537，TriggerMatched pending=1537，delivered/delivering=0/0，B_BUY/S_SELL=1286/251，normal/30m_volume/30m_shrink=1262/87/188，TriggerPendingMarketData/TriggerStateChanged=0/0，invalid N5 entry=0，N5/N6 refs=0/0，rollback_safe=true；下一步只允许 N5 action readiness / dry-run gate，不允许 runtime_control 直接执行 N5 或消费 N4 outbox。
- 后续允许切换到 `layer_role=N3_market_data`，分别做基于 `condition_layer_20260529_source_20260529_v6` 的 20260601 subscription rebuild readiness / execute gate，或基于 `condition_layer_20260528_source_20260528_v5` 的 20260529 subscription rebuild readiness / execute gate；runtime_control 不直接执行 N3、不拉行情、不启动 worker。
- runtime_control read-only dashboard / lineage review 仍允许。
- runtime_control 不消费 N3/N4/N5 outbox，不更新 N5 outbox status，不启动 worker。

## N3 实时行情层

状态：in progress / 20260603 B1 fact-only passed。

当前 20260603 subscription / A1 / calendar / B1 baseline：

```text
N3 subscription run =
  market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
  status = passed

A1 previous-day minute preload run =
  previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
  status = passed

calendar repair =
  common_trade_calendar(20260603) = 1
  is_open = true
  prev_trade_date = 20260602
  next_trade_date = 20260604
  source_version = trade_calendar_20260603_patch_v1

B1 realtime snapshot fact-only run =
  realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
  status = passed
  rows stock/index/board/total = 1963/83/428/2474
  P0/P1/P2 = 0/1/0
  writes_outbox = false
  generated_outbox_events = []
  scoped outbox/inbox/checkpoint refs = 0/0/0
  N4/N5/N6 refs = 0
  rollback_safe = true
  rollback_sql = sql/N3_B1_realtime_snapshot_20260603_rollback.sql

next allowed gate =
  N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

当前 20260529 preserved subscription run：

```text
market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
```

当前 20260529 A1 preload run：

```text
previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
status = passed
```

当前 20260529 B1 pre-open realtime snapshot fact-only run：

```text
realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
status = passed
pre_open_fact_only = true
live_trading_snapshot_ready = false
subsequent live1 snapshot run = passed
```

当前 20260529 B1 live1 realtime snapshot fact-only run：

```text
realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
status = passed
pre_open_fact_only = false
live_trading_snapshot_ready = true
subsequent N4 canonical trigger execute = passed
```

当前 20260529 B1 live2 standard outbox snapshot run：

```text
realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
status = passed
writes_outbox = true
MarketSnapshotUpdated pending = 2157
subsequent N4 live2 canonical trigger execute = passed
```

历史 20260525 preload run：

```text
previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

历史 subscription run：

```text
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute -> historical downstream lineage input
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute -> stale_after_n2_display_overwrite
```

当前 gate：

```text
N3 subscription 20260529 execute passed; market_data_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
N3 subscription 20260529 rows: candidate=5038, subscription=2643, pull_plan=7, quality=34
N3 subscription 20260529 objects stock/index/board/total=2021/9/127/2157
N3 subscription 20260529 required_data_kind: realtime_daily_snapshot=2157, minute_bar_1m=243, previous_day_minute_bar_1m=243
N3 subscription 20260529 boundary: market_data_pulled=false, market_data_fact_written=false, scoped outbox/inbox/checkpoint refs=0/0/0, global outbox/inbox/checkpoint unchanged=105122/20726/4345
N3 A1 20260529 preload passed; preload_run_id=previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
N3 A1 20260529 rows stock/index/board/total=56160/0/2160/58320; object status stock passed/partial/missing=234/0/0, index expected_objects/rows=0/0, board passed/partial/missing=9/0/0
N3 A1 20260529 boundary: event_outbox_written=false, downstream_layers_touched=false, worker_started=false, old_system_touched=false, scoped outbox/inbox/checkpoint refs=0/0/0, global outbox/inbox/checkpoint unchanged=105122/20726/4345
N3 B1 20260529 pre-open realtime snapshot fact-only passed; snapshot_run_id=realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
N3 B1 20260529 rows stock/index/board/total=2021/9/127/2157; missing/failed=0/0; quality_rows=11; P0/P1/P2=0/1/0
N3 B1 20260529 boundary: pre_open_fact_only=true, live_trading_snapshot_ready=false, writes_outbox=false, generated_outbox_events=[], scoped outbox/inbox/checkpoint refs=0/0/0, global outbox/inbox/checkpoint unchanged=105122/20726/4345, downstream_layers_touched=false, worker_started=false, N4/N5/N6 touched=false
N3 B1 20260529 source time: source_time_missing_or_preopen total/stock/index=2030/2021/9, source_time_confirmed board=127, P1 warning=n3_b1_pre_open_source_time_not_confirmed, P0 source date mismatch=0
N3 B1 20260529 live1 realtime snapshot fact-only passed; snapshot_run_id=realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
N3 B1 20260529 live1 rows stock/index/board/total=2021/9/127/2157; missing/failed=0/0; quality_rows=11; P0/P1/P2=0/0/0
N3 B1 20260529 live1 boundary: pre_open_fact_only=false, live_trading_snapshot_ready=true, writes_outbox=false, generated_outbox_events=[], scoped outbox/inbox/checkpoint refs=0/0/0, global outbox/inbox/checkpoint=105122/20726/4345, downstream_layers_touched=false, worker_started=false, N4/N5/N6 untouched=true
N3 B1 20260529 live1 source time: stock effective_quote_present/source_time_missing/partial_quality=2021/2021/0, index effective_quote_present/source_time_missing/partial_quality=9/9/0, board source_time_confirmed/effective_quote_present=127/127
N3 B1 20260529 live2 standard outbox snapshot passed; snapshot_run_id=realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1
N3 B1 20260529 live2 rows stock/index/board/total=2021/9/127/2157; P0/P1/P2=0/0/0; writes_outbox=true
N3 B1 20260529 live2 outbox: MarketSnapshotUpdated=2157 pending, MarketDataDelayed=0, MarketDataMissing=0, MarketDisplaySnapshotUpdated=0, delivered/delivering=0/0
N3 B1 20260529 live2 boundary: scoped inbox/checkpoint refs=0/0, no inbox/checkpoint writes, downstream_layers_touched=false, worker_started=false, N4/N5/N6 not entered=true, scoped exception used for existing N6 web app / old system process but they did not consume v3 outbox, rollback_safe=true
N4 20260529 live2 canonical trigger execute passed; execute_run_id=trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
N4 20260529 live2 rows common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=17/8861/8861/17722
N4 20260529 live2 outbox pending TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=4309/4552/8861; delivered/delivering=0/0
N4 20260529 live2 canonical checks: common_trigger_match TriggerStateChanged=0, pending_market_data trigger_live=false=4552, matched trigger_live=true=4309, runtime signal B_BUY/S_SELL=4467/4394, deprecated runtime signal count=0, action_mark payload count=0, trigger_mark_candidate missing=0
N4 20260529 live2 boundary: N3 live2 input MarketSnapshotUpdated pending=2157, N3 input inbox/checkpoint refs=0/0, N5 refs=0, downstream inbox/checkpoint refs=0/0, global delta outbox/inbox/checkpoint=+17722/0/0, worker_started=false, action/user/voice/mobile/sim/position/real_trade touched=false, rollback_safe=true
N5 20260529 live2 canonical action execute passed; action_run_id=action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1
N5 20260529 live2 rows common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=4552/4037/18/254/4309/4309/17722/2157
N5 20260529 live2 event distribution ActionBlocked/ActionEligible/ActionExecuted/ActionSkipped=4309/0/0/0; legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
N5 20260529 live2 outbox pending/delivered/delivering=4309/0/0
N5 20260529 live2 boundary: N4 outbox status unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=4309/4552/8861 pending, N6 refs=0, position rows=0, worker_started=false, voice/mobile/sim/position/real_trade=false, rollback_safe=true
N3 032 action-confirmation projection metric schema migration passed; migration=sql/032_n3_action_confirmation_metric_schema.sql
N3 032 target DB: database=ashare_v3, user=ashare_v3_user, host=127.0.0.1/32, port=5432, old_system_db=false
N3 032 created tables: stock_action_confirmation_projection_metric, index_action_confirmation_projection_metric, board_action_confirmation_projection_metric
N3 032 indexes/checks: index_count=18, metric_ready trace CHECK constraints=3
N3 032 row counts stock/index/board=0/0/0; business_rows_written=false; market_data_pulled=false; worker_started=false
N3 032 boundary: common_event_outbox/inbox/checkpoint delta=0/0/0, downstream N4/N5/N6 checked tables=32, downstream row_count_delta_zero=true
N3 032 rollback_safe=true; schema_rollback_sql=sql/032_n3_action_confirmation_metric_schema_rollback.sql; business_rollback_sql=sql/N3_action_confirmation_projection_metric_business_rollback.sql
N3 032 execute_report=docs/N3_action_confirmation_projection_metric_032_migration_execute_report.json
N3 action-confirmation projection writer execute passed; projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
N3 action-confirmation source lineage: condition=condition_layer_20260601_source_20260601_v1, subscription=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1, snapshot=realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1, today_minute=today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1, previous_day_minute=previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
N3 action-confirmation writer rows stock/index/board/total=765/54/150/969; metric_ready/not_ready=969/0; common_market_data_run.status=passed
N3 action-confirmation writer quality rows=6; P0/P1/P2=0/0/0
N3 action-confirmation writer boundary: market_data_pulled=false, market_data_fact_written=true, downstream_layers_touched=false, worker_started=false, scoped outbox/inbox/checkpoint=0/0/0, global outbox/inbox/checkpoint delta=0/0/0, no outbox write/consume, no inbox/checkpoint write, no N4/N5/N6 refs
N3 action-confirmation writer rollback_safe=true; rollback_sql=sql/N3_action_confirmation_projection_metric_business_rollback.sql; execute_report=docs/N3_action_confirmation_projection_writer_execute_report.json
N4 action-confirmation metric business execute passed; execute_run_id=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
N4 action-confirmation metric rows common_trigger_run/common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=1/10/5941/5941/5941
N4 action-confirmation metric outbox pending TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=6/5935/0; delivered/delivering=0/0
N4 action-confirmation metric quality P0/P1/P2=0/1/0; quality distribution P0 passed=9, P1 warning=1
N4 action-confirmation metric P1 warning=n4_action_confirmation_metric_pending_candidates_visible; non_blocking=true
N4 action-confirmation metric boundary: N3 metric facts unchanged stock/index/board=765/54/150, common_event_inbox refs=0, checkpoint refs=0, N5 refs=0, N3 outbox consumed=false, inbox/checkpoint written=false, N5/N6 entered=false, worker_started=false, market_data_pulled=false, voice/mobile/sim/position/real_trade=false, rollback_safe=true
N4 action-confirmation metric rollback_sql=sql/N4_action_confirmation_metric_business_execute_rollback.sql; execute_report=docs/N4_action_confirmation_metric_business_execute_report.json
N5 action-confirmation metric execute passed; action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
N5 action-confirmation metric source N4 run=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
N5 action-confirmation metric common_action_run.status=passed; P0/P1/P2=0/0/0
N5 action-confirmation metric rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/5935/1/4/0/5/5/5941/2487
N5 action-confirmation metric event distribution ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped=4/1/0/0
N5 action-confirmation metric outbox pending ActionExecuted/ActionBlocked=4/1; delivered/delivering=0/0
N5 action-confirmation metric boundary: N4 outbox unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=6/5935/0 pending, delivered/delivering=0/0; N6/user/downstream refs=0; position refs=0; voice/mobile/sim/real_trade refs=0; worker_started=false
N5 action-confirmation metric rollback_safe=true; rollback_sql=sql/N5_20260602_action_confirmation_metric_execute_rollback.sql; execute_report=docs/N5_20260602_action_confirmation_metric_execute_report.json
N6 20260602 action-confirmation metric shadow projection execute passed; projection_run_id=user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
N6 20260602 shadow projection status=passed; preflight_result=PREFLIGHT_PASS; P0/P1/P2=0/5/2
N6 20260602 rows user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/5/5/5
N6 20260602 queue distribution n5_action_executed:queued_only=4, n5_action_blocked:queued_only=1
N6 20260602 card distribution ActionExecuted -> action_confirmed/executed/30m_shrink=4, ActionBlocked -> blocked/blocked=1
N6 20260602 boundary: N5 outbox unchanged ActionExecuted=4 pending, ActionBlocked=1 pending; n5_outbox_consumed=false; updates_n5_outbox_status=false; user_signal_decision=0; user_watchlist/watchlist_item=0/0; linked user_sim_order/trade/position=0/0/0; worker_started=false; push/voice/mobile=false; sim/position/real_trade=false; rollback_safe=true
N6 20260602 rollback_sql=sql/N6_projection_business_rollback.sql
N4 20260529 canonical trigger execute passed; execute_run_id=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
N4 20260529 rows common_trigger_run/common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=1/16/8861/8861/17722
N4 20260529 outbox pending TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=4309/4552/8861; delivered/delivering=0/0
N4 20260529 canonical checks: common_trigger_match TriggerStateChanged=0, pending_market_data trigger_live=false=4552, matched trigger_live=true=4309, runtime signal B_BUY/S_SELL=4467/4394, deprecated runtime signal count=0, action_mark payload count=0, trigger_mark_candidate missing count=0
N4 20260529 boundary: scoped inbox/checkpoint refs=0/0, N5 refs common_action_run/common_action_event=0/0, global delta outbox/inbox/checkpoint=+17722/0/0, outbox_consumed=false, N5/N6 touched=false, worker_started=false, user/voice/mobile/sim/position/real_trade=false, N2/N3 facts unchanged=true, rollback_safe=true
N5 20260529 canonical action execute passed; action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
N5 20260529 rows common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=4552/4037/18/254/4309/4309/17722/2157
N5 20260529 event distribution ActionBlocked/ActionEligible/ActionExecuted/ActionSkipped=4309/0/0/0; legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
N5 20260529 outbox pending/delivered/delivering=4309/0/0
N5 20260529 boundary: N4 outbox status unchanged, N6 refs=0, position rows=0, worker_started=false, N6 not entered=true, voice/mobile/sim/real_trade=false, old_system_touched=false, rollback_safe=true
N6 20260529 canonical shadow projection passed; projection_run_id=user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
N6 20260529 rows user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/4309/4309/4309
N6 20260529 policy notification_source=n5_action_blocked, queue_status=queued_only, notification queued_only=4309, projection_policy=blocked_unconfirmed_no_push_no_decision_no_sim_no_trade
N6 20260529 boundary: N5 outbox unchanged ActionBlocked pending=4309 delivered/delivering=0/0, n5_outbox_consumed=false, updates_n5_outbox_status=false, user_signal_decision/watchlist/watchlist_item=0/0/0, user_sim_order/trade/position=0/0/0, worker_started=false, push/voice/mobile=false, position/real_trade=false, N1-N5 unchanged=true, rollback_safe=true
Next allowed gate: N6 shadow projection post-review, N6 projection business rollback review if needed, runtime_control read-only dashboard / lineage review, or 20260529 N6 live2 / full-day user projection gate as a separate reviewed branch
N3-B1 passed; upstream B1 outbox status remains pending by design after N4 inbox/checkpoint processing
N4 current context rebuild passed; B2 projection facts have been consumed by N4 projection matcher run-once execute
N3 projection metric schema is ready
N3-A1 current-lineage previous-day minute fill-facts execute passed; writes_outbox=false
N3-C1 today_minute_bar_1m execute passed; outbox = 0; MinuteBarClosed generated = false; projection tables written = false
N3-B2 realtime projection execute passed; projection rows=2188, ready=2052, not_ready=136
N3-B2 writes_outbox=false; projection outbox/inbox=0; B1 MarketSnapshotUpdated remains pending=2188
N4 projection matcher dry-run / preflight / run-once execute passed; N4 outbox pending=764
N4 did not update upstream B1 outbox status; B1 MarketSnapshotUpdated remains pending=2188 by design
N5 current-real action dry-run / contract / rollback / row-count guard passed
N5 current-real action run-once execute passed; N5 outbox pending=488
20260528 canonical N4 trigger execute passed; N4 canonical outbox pending=17774
20260528 canonical N5 action execute passed; N5 canonical outbox pending=4285 ActionBlocked
20260529 canonical N5 action execute passed; N5 canonical outbox pending=4309 ActionBlocked
N3-C2 closed-minute / closed-30m replay execute passed
N3-C3 MinuteBarClosed outbox execute passed; MinuteBarClosed pending=17432 and delivered/delivering=0
N3-C2B closed_signal_enrichment execute passed; enrichment rows=17504 and c2b outbox/inbox/checkpoint refs=0
N4-C3 replay audit execute passed; N3-EOD dry-run PASS but execute preflight is BLOCKED by missing_official_daily_fact; N5 action-confirmation metric execute passed; N6 20260602 action-confirmation metric shadow projection execute passed; current recommended branch is N6 shadow projection post-review, N6 projection business rollback review if needed, runtime_control read-only dashboard / lineage review, or N1 official daily fact ingestion review; N5 outbox consumption, N5 outbox status update, additional N6 execute, N4/N5/N6 replay event execute, EOD execute, daily close, and workers remain blocked
```

已完成：

- N3 schema / migration。
- N3 action-confirmation projection metric schema migration 032 已 passed：三张物理分表 `stock/index/board_action_confirmation_projection_metric` 已存在，index_count=18，metric_ready trace CHECK constraints=3。
- N3 action-confirmation projection writer execute 已 passed：projection_run_id=`action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`，rows stock/index/board/total=765/54/150/969，metric_ready/not_ready=969/0，quality rows=6，P0/P1/P2=0/0/0，no outbox/inbox/checkpoint writes or consumption，rollback_safe=true。
- N4 action-confirmation metric business execute 已 passed：execute_run_id=`trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1`，common_trigger_run/status=1/passed，common_trigger_quality_item=10，common_trigger_state=5941，common_trigger_match=5941，common_event_outbox=5941，TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，delivered/delivering=0/0，P0/P1/P2=0/1/0，唯一 P1 为 `n4_action_confirmation_metric_pending_candidates_visible` 且不阻断。
- market_data_subscription rebuild after N2-Display 已完成。
- 20260529 market_data_subscription execute 已 passed，source_condition_run_id=`condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=passed，P0/P1/P2=0/0/0。
- 20260529 subscription row counts：candidate=5038，subscription=2643，pull_plan=7，quality=34，objects stock/index/board/total=2021/9/127/2157。
- 20260529 required_data_kind distribution：realtime_daily_snapshot=2157，minute_bar_1m=243，previous_day_minute_bar_1m=243。
- 20260529 subscription canonical signals：BUY, BUY:FULL, SELL, SELL:FULL, BUY_HINT, SELL_HINT；deprecated_signal_rows=0。
- 20260529 subscription boundary：market_data_pulled=false，market_data_fact_written=false，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- 20260529 subscription rollback_safe=true，rollback SQL=`sql/N3_subscription_20260529_rollback.sql`。
- 032 rollback_safe=true，schema rollback SQL=`sql/032_n3_action_confirmation_metric_schema_rollback.sql`，business rollback SQL=`sql/N3_action_confirmation_projection_metric_business_rollback.sql`；schema rollback 仅允许三张 metric 表 row_count=0 时 DROP，business rollback 按 `projection_run_id` 并带 outbox/inbox/checkpoint hard guard。
- 20260529 A1 previous_day_minute preload 已 passed，preload_run_id=`previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，source subscription run=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=passed，P0/P1/P2=0/0/0，quality rows=12。
- 20260529 A1 actual rows：stock=56160，index=0，board=2160，total=58320。
- 20260529 A1 object status：stock passed/partial/missing=234/0/0，index expected objects/rows=0/0，board passed/partial/missing=9/0/0，fake index pull / fake index rows=0/0。
- 20260529 A1 boundary：event_outbox_written=false，downstream_layers_touched=false，worker_started=false，old_system_touched=false，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- 20260529 A1 rollback_safe=true，rollback SQL=`sql/N3_A1_previous_day_minute_20260529_rollback.sql`。
- 20260529 B1 pre-open realtime snapshot fact-only 已 passed，snapshot_run_id=`realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=passed，pre_open_fact_only=true，live_trading_snapshot_ready=false，P0/P1/P2=0/1/0，quality rows=11。
- 20260529 B1 rows：stock=2021，index=9，board=127，total=2157，missing/failed=0/0。
- 20260529 B1 outbox boundary：writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345。
- 20260529 B1 source time：source_time_missing_or_preopen total/stock/index=2030/2021/9，source_time_confirmed board=127，P1 warning=`n3_b1_pre_open_source_time_not_confirmed`，P0 source date mismatch=0。
- 20260529 B1 boundary：downstream_layers_touched=false，worker_started=false，N4/N5/N6 touched=false，rollback_safe=true，rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_rollback.sql`。
- 20260529 B1 reports：`docs/N3_B1_realtime_daily_snapshot_execute_report.json`，`docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_REPORT.md`。
- 20260529 B1 live1 realtime snapshot fact-only 已 passed，snapshot_run_id=`realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=passed，live_trading_snapshot_ready=true，pre_open_fact_only=false，P0/P1/P2=0/0/0，quality rows=11。
- 20260529 B1 live1 rows：stock=2021，index=9，board=127，total=2157，missing/failed=0/0。
- 20260529 B1 live1 source time：stock effective_quote_present/source_time_missing/partial_quality=2021/2021/0，index effective_quote_present/source_time_missing/partial_quality=9/9/0，board source_time_confirmed/effective_quote_present=127/127。
- 20260529 B1 live1 boundary：writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint=105122/20726/4345，downstream_layers_touched=false，worker_started=false，N4/N5/N6 untouched=true，rollback_safe=true，rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live1_rollback.sql`。
- 20260529 B1 live2 standard outbox snapshot 已 passed，snapshot_run_id=`realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，common_market_data_run.status=passed，P0/P1/P2=0/0/0。
- 20260529 B1 live2 rows：stock=2021，index=9，board=127，total=2157。
- 20260529 B1 live2 outbox：writes_outbox=true，MarketSnapshotUpdated=2157 pending，MarketDataDelayed=0，MarketDataMissing=0，MarketDisplaySnapshotUpdated=0，delivered/delivering=0/0。
- 20260529 B1 live2 boundary：scoped inbox/checkpoint refs=0/0，no inbox/checkpoint writes，downstream_layers_touched=false，worker_started=false，N4/N5/N6 not entered=true，scoped exception used for existing N6 web app / old system process but they did not consume v3 outbox，rollback_safe=true，rollback SQL=`sql/N3_B1_realtime_snapshot_20260529_live2_outbox_rollback.sql`。
- 20260529 N4 live2 canonical trigger execute 已 passed，execute_run_id=`trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`，common_trigger_run.status=passed，P0/P1/P2=0/1/0。
- 20260529 N4 live2 rows：common_trigger_quality_item=17，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722。
- 20260529 N4 live2 outbox：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0。
- 20260529 N4 live2 canonical checks：common_trigger_match TriggerStateChanged=0，pending_market_data trigger_live=false=4552，matched trigger_live=true=4309，runtime signal B_BUY=4467 / S_SELL=4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing=0。
- 20260529 N4 live2 boundary：N3 live2 input MarketSnapshotUpdated pending=2157，N3 input inbox/checkpoint refs=0/0，N5 refs=0，downstream inbox/checkpoint refs=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，worker_started=false，action/user/voice/mobile/sim/position/real_trade touched=false，rollback_safe=true，rollback SQL=`sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql`。
- 20260529 N4 canonical trigger execute 已 passed，execute_run_id=`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，common_trigger_run.status=passed，P0/P1/P2=0/1/0。
- 20260529 N4 rows：common_trigger_run=1，common_trigger_quality_item=16，common_trigger_state=8861，common_trigger_match=8861，common_event_outbox=17722。
- 20260529 N4 outbox：TriggerMatched=4309 pending，TriggerPendingMarketData=4552 pending，TriggerStateChanged=8861 pending，delivered/delivering=0/0。
- 20260529 N4 canonical checks：common_trigger_match TriggerStateChanged=0，pending_market_data trigger_live=false=4552，matched trigger_live=true=4309，runtime signal B_BUY=4467 / S_SELL=4394，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing count=0。
- 20260529 N4 boundary：scoped inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，outbox_consumed=false，N5/N6 touched=false，worker_started=false，user/voice/mobile/sim/position/real_trade=false，N2/N3 facts unchanged=true。
- 20260529 N4 rollback_safe=true，rollback SQL=`sql/N4_20260529_canonical_trigger_execute_rollback.sql`。
- N3-A1 previous-day minute preload 已与 N2-Display subscription lineage 对齐。
- N3-A1 current-lineage fill-facts execute 已 passed，previous-day minute rows: stock=490320, index=2160, board=30480, total=522960；`common_event_outbox` rows = 0。
- N3-B1 readiness 曾 PASS，允许进入用户确认点。
- N3-B1 first run-once execute 曾执行并 commit，但最终 status=failed；已安全 rollback。
- BoardMarketDataAdapter 已实现并 probe 通过。
- N3-B1 rerun execute 已 passed。
- current snapshot_run_id = `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- snapshot rows: stock=2052, index=9, board=127。
- outbox: `MarketSnapshotUpdated` pending=2188，delivered/delivering=0。
- `MarketDataMissing / MarketDataDelayed = 0`。
- rollback_safe = true。
- N4 projection matcher 已通过 `common_event_inbox` / checkpoint 记录当前 N3-B1 event 处理结果，但不更新 upstream B1 outbox status。
- N5 current-real action consumer 已通过 N5 inbox/checkpoint 处理当前 N4 real outbox；N4 outbox status 仍保持 pending=764。
- N6 当前仍未消费任何 N5 outbox。
- subscription candidate = 13536。
- dedup subscription = 6564。
- object count = 2188。
- pull plan = 9。
- condition_display_basis_input_to_n3 = false。
- N3 realtime projection metric schema / migration 已就绪。
- N3-B2 projection input diagnosis 已完成：诊断时因缺今日 1m minute_bar 输入只能生成 not_ready skeleton；该输入缺口已由 N3-C1 补齐，后续 B2 dry-run 已证明 stock/index 可生成 usable projection。
- N3-C1 today_minute_bar_1m execute 已 passed。
- C1 today_minute_run_id = `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- C1 actual rows: stock=390213, index=1719, board=24257, total=416189。
- C1 expected total=417908，missing rows=1719，missing objects=9，全部为 BJ 920xxx 股票。
- C1 common_event_outbox rows = 0；`MinuteBarClosed generated=false`；projection tables written=false。
- C1 rollback SQL: `sql/N3_C1_today_minute_bar_1m_rollback.sql`。
- N3-B2 realtime projection dry-run after A1 fill + C1 已 passed。
- B2 projection_run_id_candidate = `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- B2 ready projection rows = 2052，其中 stock=2043、index=9。
- B2 not_ready rows = 136，其中 BJ 920xxx stock=9、board=127。
- board not_ready 原因：B1 board snapshot_time=15:00，但 C1 latest_closed_minute=14:11，严格 lineage 下不得混用成 ready。
- B2 projection_signal_status: down_volume_expanding=96, down_volume_flat=79, down_volume_shrinking=174, flat=577, unknown=136, up_volume_expanding=305, up_volume_flat=342, up_volume_shrinking=479。
- N3-B2 realtime projection execute 已 passed。
- B2 projection_run_id = `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- B2 projection fact rows: stock=2052, index=9, board=127, total=2188。
- B2 quality P0/P1/P2 = 0/3/0；quality rows = 6；data_domain = common/stock/board；layer_scope = market_data_run；details.metric_scope = realtime_projection_metric。
- B2 projection outbox rows = 0；projection inbox rows = 0；B1 MarketSnapshotUpdated still pending=2188。
- B2 rollback_safe = true；rollback SQL = `sql/N3_B2_realtime_projection_rollback.sql`。
- N3-C2 closed-minute / closed-30m incremental design 已登记并完成 run-once execute，定位为 N3 replay / confirmation，不是 N1->N3 全链路重跑，不 supersede B1/B2/N4/N5。
- C2 run_id = `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- C2 strategy: 按对象尝试全日 1m replay；只写 C1 缺失或 replay diff 的 minute delta rows；closed 30m summary 从 C1 baseline + C2 delta 合成。
- C2 minute_delta_rows: stock=100669, index=441, board=6223, total=107333。
- C2 closed_30m_summary rows: stock=16416, index=72, board=1016, total=17504。
- C2 summary_status: closed=17432, partial=0, missing=72, failed=0。
- C2 BJ 920xxx: 9 objects, 72 missing summaries, no fabricated minute rows。
- C2 quality P0/P1/P2=0/1/0。
- C2 outbox/inbox/checkpoint refs=0；B1 MarketSnapshotUpdated pending=2188；C1/B1/B2/N4/N5 runtime unchanged=true。
- C2 rollback_safe=true；rollback SQL=`sql/N3_C2_closed_30m_business_rollback.sql`。
- C2 不写 `MinuteBarClosed` outbox；C3 event gate 已单独 execute passed；daily close 另设 gate。
- N3-C3 MinuteBarClosed outbox execute 已 passed。
- C3 run_id = `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- C3 `common_market_data_run.status=passed`；P0/P1/P2=0/1/0；`market_data_pulled=false`；`market_data_fact_written=false`；source_trade_date/prev_trade_date=20260525/20260525。
- C3 `MinuteBarClosed` outbox rows=17432，stock/index/board=16344/72/1016。
- C3 outbox status: pending=17432，delivered/delivering=0；inbox=0；checkpoint refs=0。
- C3 boundary: closed_30m_summary C3 refs=0；minute_bar_1m C3 refs=0；realtime_projection_metric C3 refs=0；realtime_daily_snapshot C3 refs=0。
- C3 touched: N4/N5/N6=false；worker_started=false。
- C3 rollback_safe=true；rollback SQL=`sql/N3_C3_minute_bar_closed_outbox_rollback.sql`。
- N3-C2B closed_signal_enrichment execute 已 passed。
- C2B run_id = `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`。
- C2B `common_market_data_run.status=passed`；P0/P1/P2=0/3/0。
- C2B enrichment rows: stock=16416, index=72, board=1016, total=17504。
- C2B computable_rows=17432，unknown_rows=72，missing_rows=72。
- C2B signal_distribution: up_volume_expanding=2800, up_volume_flat=2494, up_volume_shrinking=2260, down_volume_expanding=2806, down_volume_flat=2408, down_volume_shrinking=2011, flat=2653, unknown=72。
- C2B quality_rows=6；data_domain common=3 / stock=3；layer_scope=market_data_run；details.metric_scope=closed_signal_enrichment。
- C2B outbox=0，inbox=0，checkpoint refs=0。
- C2B did not consume C3 outbox；C3 outbox pending=17432，delivered/delivering=0，inbox/checkpoint refs=0。
- C2B did not modify closed_30m_summary / minute_bar_1m / realtime_projection_metric / realtime_daily_snapshot。
- C2B rollback_safe=true；rollback SQL=`sql/N3_C2B_closed_signal_enrichment_business_rollback.sql`。
- N4-C3 replay audit execute 已 passed；replay_run_id = `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`。
- N4-C3 replay audit rows: stock=33762, index=144, board=2064, total=35970。
- N4-C3 replay audit classification: would_match=4734, would_clear=245, would_change=243, unchanged=30730, missing=18, not_ready=0。
- N4-C3 replay audit P0/P1/P2=0/1/0；`common_event_outbox=0`，`common_event_inbox=0`，checkpoint refs=0，`common_trigger_match=0`，`common_trigger_state=0`。
- N4-C3 replay audit did not consume C3 outbox；C3 outbox pending=17432，delivered/delivering=0；N5/N6 touched=false；worker_started=false。
- N4-C3 replay audit rollback_safe=true；rollback SQL=`sql/N4_C3_replay_audit_business_rollback.sql`。
- N3-EOD snapshot refresh dry-run 已 PASS。
- EOD run id = `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute`。
- expected EOD snapshot rows: stock=2052, index=9, board=127, total=2188。
- EOD execute preflight = PREFLIGHT_BLOCKED；blocker=`missing_official_daily_fact`；official_daily_missing=2188。
- C3 outbox remains pending=17432，delivered/delivering=0；P0/P1/P2=0/3/0。
- EOD business rows=0；common_market_data_run/quality scoped eod_run_id=0；outbox/inbox/checkpoint scoped eod_run_id=0。
- EOD execute remains blocked；禁止使用 C2/C2B 直接做正式 EOD settlement，除非另开 provisional settlement gate。

待完成：

- N3-B1 outbox status 仍为 pending=2188；不得启动新的下游 consumer 静默重复消费。
- N4 projection matcher run-once execute 已完成；后续 N4 追加 execute / bounded worker 必须另开 gate。
- 旧 synthetic denylist 不得作为当前真实 N3 event 输入。
- N1 official daily fact ingestion review for 20260525。
- EOD snapshot refresh execute 继续 blocked，直到 20260525 official daily fact 补齐并重新通过 EOD final gate。
- N4/N5/N6 C3 replay event execute、daily close gate 均未授权。

Entry gate：

- N2 active condition run 已确认。
- `minute_target_scope` 可读且 P0=0。
- `market_data_subscription` 已按去重粒度生成。
- 对应 trade_date 是当天且交易日历 open；若 calendar row 缺失或非开市日，必须阻断 realtime snapshot execute。

Exit gate：

- realtime snapshot 和 minute fact 物理分表。
- 事实与 N3 outbox 同事务写入。
- N3 event payload trace 完整。
- 不写 trigger/action/user。

Rollback gate：

- N3 subscription 按 `run_id` 删除 control rows。
- N3-A1 按 `source_run_id + preload_run_id` 删除 fact/status/quality。
- N3-B1 按 snapshot run 删除 snapshot fact 和 outbox。
- N3-B2 按 projection_run_id 删除 projection fact、quality 和 run rows；B2 不应有 outbox rollback。
- N3-C2 按 c2_run_id 删除 closed_30m_summary、C2 delta minute rows、quality 和 run rows；rollback SQL 必须先确认 C2 outbox/inbox/checkpoint refs = 0。
- N3-C3 按 c3_run_id 删除 `common_event_outbox`、`common_market_data_quality_item`、`common_market_data_run`；rollback SQL 必须先确认 C3 outbox 无 delivered/delivering、inbox=0、checkpoint refs=0。
- N3-C2B 按 c2b_run_id 删除 `stock/index/board_closed_30m_signal_enrichment`、`common_market_data_quality_item`、`common_market_data_run`；rollback SQL 必须先确认 c2b outbox=0、inbox=0、checkpoint refs=0。
- N4-C3 replay audit 按 replay_run_id 删除 `stock/index/board_trigger_replay_audit`、`common_trigger_quality_item`、`common_trigger_run`；rollback SQL 必须先确认 replay_run_id 关联的 outbox/inbox/checkpoint refs=0，且不碰 C3/N3/N5/原 N4 projection matcher run。

Blocked / caution：

- N3-B1 outbox pending=2188 仍不是重复 N4 execute 授权；当前 N4 processed 事实以 `common_event_inbox` / checkpoint 和 `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249` 为准。
- 不得把旧 synthetic outbox 当作当前真实 N3 event。
- 不得直接进入追加 N5 execute、N6 execute 或启动 worker。
- N3-B2 execute 已写入 formal projection facts，并已被 N4 projection matcher run-once execute 使用；后续重跑 N4 必须重新通过 execute gate。
- board=127 当前为 not_ready，不应在严格 lineage 下静默修成 ready；是否补齐 board 需另开 N3 gate。
- N3-C 今日分钟 K 与 N4 event consumption 是两个不同 gate，不得混做。
- N3-C3 `MinuteBarClosed` outbox pending=17432 不是 N4/N5/N6 replay 授权；后续消费必须显式 allowlist C3 run_id 并另开所属层 contract / preflight / rollback。
- N4-C3 replay audit passed 只代表 audit facts 已固化；不得把 would_match/would_clear/would_change 当作正式 N4 标准事件，不得直接 N4/N5/N6 replay event execute 或启动 worker。
- N2 active condition run、N3 subscription run、N3 preload run 均未因首次 failed execute / rollback 或本次 B1 passed 登记改变。

## N4 触发层

状态：in progress / 20260603 canonical trigger execute passed。

当前 20260603 context rebuild run：

```text
trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1
```

20260603 context rebuild status：

```text
common_trigger_run.status = passed
source_condition_run_id = condition_layer_20260602_source_20260602_v1
source_market_data_run_id = realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
market_subscription_run_id = market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
for_trade_date/source_trade_date/prev_trade_date = 20260603/20260602/20260602
rows stock/index/board/total = 4164/168/890/5222
object coverage stock/index/board = 1963/83/428
BUY_HINT / SELL_HINT trace rows = 216/61
period_trigger_baseline_json_missing = 0
required_period_not_ready_rows = 0
common_trigger_run/common_trigger_quality_item = 1/62
common_trigger_state/common_trigger_match/common_event_outbox = 0/0/0
P0/P1/P2 = 0/0/0
N5/N6 refs = 0/0
market_data_pulled = false
n3_event_consumed = false
worker_started = false
rollback_safe = true
rollback_sql = sql/N4_20260603_trigger_context_rebuild_rollback.sql
canonical trigger execute run =
  trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
  status = passed
  P0/P1/P2 = 0/1/0
  quality_rows = 17
  common_trigger_state/common_trigger_match/common_event_outbox = 10167/10167/20334
  TriggerMatched/TriggerPendingMarketData/TriggerStateChanged = 1252/8915/10167
  outbox pending/delivered/delivering = 20334/0/0
  runtime signal B_BUY/S_SELL = 5164/5003
  deprecated runtime signal count = 0
  trigger_mark_candidate normal/30m_volume/30m_shrink = 5222/2474/2471
  anomaly = 0
  N5 refs common_action_run/common_action_event = 0/0
  N6 refs projection/card/queue = 0/0/0/0
  rollback_safe = true before downstream consumption
  rollback_sql = sql/N4_20260603_canonical_trigger_execute_rollback.sql

next allowed gate = N6 readiness/shadow gate, delivery/notification gate, or runtime_control read-only lineage review
```

当前 context run：

```text
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

旧 synthetic denylist：

```text
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
```

已完成：

- N4 schema。
- 历史 N4-R4 context rebuild，context rows = 4512；旧 run 已标记为 synthetic/stale。
- current N4 context rebuild 已基于 N2 active run 和 N3 subscription 重建。
- current context rows: stock=4236, index=18, board=258, total=4512。
- current context P0/P1/P2 = 0/0/0。
- current context rebuild 写入 `common_trigger_run`、`common_trigger_quality_item`、`stock/index/board_trigger_context_snapshot`；未写 `common_trigger_match`，未写 N4 outbox，未消费 N3 event。
- `period_trigger_baseline_json` 本地化。
- synthetic trigger run-once execute 历史输出已保留为验证材料；denylist 两个 source_run_id 合计 N4 outbox rows = 53304。
- 旧 synthetic denylist 已登记，禁止作为当前真实 N3 event consumption 输入。
- N4 projection matcher dry-run refresh 已 passed：candidate=4512，matched=488，pending=276，not_matched=3748。
- N4 projection matcher execute preflight 已 passed，P0/P1/P2=0/0/0。
- N4 real projection matcher run-once execute 已 passed。
- execute_run_id = `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- execute 写入 `common_event_inbox=2188 processed`、`common_event_consumer_checkpoint=2188`、`common_trigger_state=764`、`common_trigger_match=764`、`common_trigger_quality_item=9`。
- N4 outbox pending: `TriggerMatched=488`、`TriggerPendingMarketData=276`，delivered/delivering=0。
- signal summary: `B_BUY_30M_VOL matched=305 pending=136`，`BUY_HINT matched=6`，`S_SELL_30M_SHRINK matched=174 pending=136`，`SELL_HINT matched=3 pending=4`。
- B1 outbox still `MarketSnapshotUpdated pending=2188`；N3 facts unchanged=true；old synthetic outbox untouched=53304；downstream N5 inbox for this N4 run=764 processed。
- rollback_safe=true；rollback SQL: `sql/N4_projection_matcher_rollback.sql`。
- N4-C3 replay dry-run 已 passed，candidate_count=35970，P0/P1/P2=0/1/0。
- N4-C3 replay audit run-once execute 已 passed，replay_run_id = `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`。
- N4-C3 replay audit rows: stock=33762, index=144, board=2064, total=35970。
- N4-C3 replay audit classification: would_match=4734, would_clear=245, would_change=243, unchanged=30730, missing=18, not_ready=0。
- N4-C3 replay audit boundary: `common_event_outbox=0`，`common_event_inbox=0`，checkpoint refs=0，`common_trigger_match=0`，`common_trigger_state=0`，C3 outbox remains pending=17432，delivered/delivering=0。
- N4-C3 replay audit did not touch N5/N6 and did not start worker。
- rollback_safe=true；rollback SQL: `sql/N4_C3_replay_audit_business_rollback.sql`。
- N4 canonical trigger/action runtime spec 已登记为分权冻结：`docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md` 负责 runtime boundary，`docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md` 负责 N4 trigger-side rule definitions，`docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md` 负责状态流与跨层边界；`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md` 对 N4 trigger-side rule definitions 已 superseded/historical。
- N4 024 canonical trigger state compatibility migration 已执行并 post-review PASS。
- 20260528 canonical v2 local trigger dry-run 已 PASS。
- 20260528 canonical v2 execute contract / preflight 已 PASS。
- 20260528 canonical v2 trigger run-once execute 已 passed。
- execute_run_id = `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- source lineage: N2=`condition_layer_20260527_source_20260527_v2`，N3 subscription=`market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2`，N3 snapshot=`realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2`，N4 context=`trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2`。
- 20260528 canonical N4 writes: `common_trigger_quality_item=16`，`common_trigger_state=8887`，`common_trigger_match=8887`，`common_event_outbox=17774`。
- 20260528 canonical N4 outbox pending: `TriggerMatched=4285`，`TriggerPendingMarketData=4602`，`TriggerStateChanged=8887`，delivered/delivering=0。
- canonical checks: `common_trigger_match TriggerStateChanged=0`，`pending_market_data trigger_live=false=4602`，`matched trigger_live=true=4285`，state/match signal distribution `B_BUY=4576`、`S_SELL=4311`，deprecated runtime signal count state/match/outbox_payload = 0/0/0，action_mark payload count=0，trigger_mark_candidate missing state/match/outbox = 0/0/0。
- boundary: N5 refs=0，N6 refs=0，scoped inbox/checkpoint refs=0，global delta outbox=+17774 / inbox=0 / checkpoint=0，N5/N6 worker_started=false，N2/N3 facts unchanged=true，old_system_touched=false，no action/user/voice/mobile/sim/position/real trade。
- rollback_safe=true；rollback SQL: `sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql`。
- 20260529 canonical trigger execute 已 passed。
- execute_run_id = `trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- source lineage: N2=`condition_layer_20260528_source_20260528_v1`，N3 subscription=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，N3 snapshot=`realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- 20260529 canonical N4 writes: `common_trigger_run=1`，`common_trigger_quality_item=16`，`common_trigger_state=8861`，`common_trigger_match=8861`，`common_event_outbox=17722`。
- 20260529 canonical N4 outbox pending: `TriggerMatched=4309`，`TriggerPendingMarketData=4552`，`TriggerStateChanged=8861`，delivered/delivering=0。
- 20260529 canonical checks: `common_trigger_match TriggerStateChanged=0`，`pending_market_data trigger_live=false=4552`，`matched trigger_live=true=4309`，runtime signal `B_BUY=4467` / `S_SELL=4394`，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing count=0。
- 20260529 boundary: scoped inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，outbox_consumed=false，N5/N6 touched=false，worker_started=false，user/voice/mobile/sim/position/real_trade=false，N2/N3 facts unchanged=true。
- rollback_safe=true；rollback SQL: `sql/N4_20260529_canonical_trigger_execute_rollback.sql`。
- 20260529 live2 canonical trigger execute 已 passed。
- live2 execute_run_id = `trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- live2 source lineage: N2=`condition_layer_20260528_source_20260528_v1`，N3 subscription=`market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`，N3 snapshot=`realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`。
- 20260529 live2 N4 writes: `common_trigger_quality_item=17`，`common_trigger_state=8861`，`common_trigger_match=8861`，`common_event_outbox=17722`。
- 20260529 live2 N4 outbox pending: `TriggerMatched=4309`，`TriggerPendingMarketData=4552`，`TriggerStateChanged=8861`，delivered/delivering=0。
- 20260529 live2 canonical checks: `common_trigger_match TriggerStateChanged=0`，`pending_market_data trigger_live=false=4552`，`matched trigger_live=true=4309`，runtime signal `B_BUY=4467` / `S_SELL=4394`，deprecated runtime signal count=0，action_mark payload count=0，trigger_mark_candidate missing=0。
- 20260529 live2 boundary: N3 live2 input MarketSnapshotUpdated pending=2157，N3 input inbox/checkpoint refs=0/0，N5 refs=0，downstream inbox/checkpoint refs=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，worker_started=false，action/user/voice/mobile/sim/position/real_trade touched=false。
- live2 rollback_safe=true；rollback SQL: `sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql`。

- 后续状态：

- 20260529 N5 canonical action execute 已 passed。
- 20260529 N5 action_run_id=`action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`，N5 outbox pending=4309 ActionBlocked，legacy output events=0。
- 20260529 N6 canonical shadow projection 已 passed；N5 outbox status unchanged。
- 20260529 B1 live2 standard outbox snapshot 已 passed；20260529 N4 live2 canonical trigger execute 已 passed。
- 20260529 N5 live2 canonical action execute 已 passed。
- 允许进入 20260529 N6 live2 / full-day user projection gate。
- N6 shadow projection post-review / rollback-readiness review 仍可只读复核；additional N6 execute、push/voice/mobile/sim/position/real trade 仍未授权。
- N5 canonical action execute 已完成于 20260528 branch，当前 20260528 N5 canonical outbox pending=4285。
- 20260528 canonical N4 outbox status 仍保持 pending；N5 通过 inbox/checkpoint 记录消费进度。
- 20260529 canonical N4 outbox status 保持 pending；20260529 N5 已通过 inbox/checkpoint 记录消费进度，不修改 N4 outbox status。
- 20260529 live2 canonical N4 outbox status 保持 pending；20260529 N5 live2 已通过 inbox/checkpoint 记录消费进度，不修改 N4 outbox status。
- N5 current-real action run-once execute 已完成；N4 outbox status 仍为 pending=764，N5 用 inbox/checkpoint 记录消费进度。
- 后续 N4 追加标准事件 run-once、replay event execute 或 bounded worker 仍需单独 gate；当前仅允许 N6 live2 / full-day user projection gate，不允许 runtime_control 进入 N6 execute。
- 若要回滚当前 N4 run，必须先处理已登记的 N5 action rollback。
- EOD execute 仍被 `missing_official_daily_fact` 阻断；其后续仍需单独 gate。

Entry gate：

- N3 realtime facts 和 N3 outbox 已准备。
- N4 context snapshot 与 N2/N3 lineage 对齐。
- 若执行 `B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT`，必须已具备 N3 标准化、可追溯、quality passed 的 realtime projection 指标和 N4 projection matcher；当前 run 已满足并 execute passed。
- 不访问外接盘 N2 runtime。

Exit gate：

- `TriggerMatched` / `TriggerPendingMarketData` 由标准 N3 event 触发。
- canonical 20260528 分支还允许 `TriggerStateChanged` 作为状态广播 outbox；`TriggerStateChanged` 不写入 `common_trigger_match`。
- trigger fact 与 N4 outbox 同事务。
- payload contract 0 violation。

Rollback gate：

- current context rebuild rollback SQL：`sql/N4_CURRENT_trigger_context_rebuild_rollback.sql`，只能在 N4 real dry-run/execute 消费该 context 前使用。
- N4 projection matcher execute rollback SQL：`sql/N4_projection_matcher_rollback.sql`；只按 execute run 删除 N4 outbox、trigger match/state/quality、N4 inbox/checkpoint 和 execute run row，不碰 N3。
- N4-C3 replay audit rollback SQL：`sql/N4_C3_replay_audit_business_rollback.sql`；只按 replay_run_id 删除 replay audit rows、quality 和 trigger_run，且必须先确认 outbox/inbox/checkpoint guard 为 0。
- synthetic 或 run-once 输出必须按 `run_id` 删除 `common_event_outbox`、`common_trigger_match`、`common_trigger_state` 和 quality rows。
- 若已被 N5 消费，必须先处理 N5 inbox/checkpoint/action rollback。
- 20260528 canonical execute rollback SQL：`sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql`；只按 execute_run_id 清理 N4 outbox/state/match/quality/run，并带 N5/N6 downstream guard，不碰 N2/N3。
- 20260529 canonical execute rollback SQL：`sql/N4_20260529_canonical_trigger_execute_rollback.sql`；只按 execute_run_id 清理 N4 outbox/state/match/quality/run，并带 N5/N6 downstream guard，不碰 N2/N3。
- 20260529 live2 canonical execute rollback SQL：`sql/N4_20260529_live2_canonical_trigger_execute_rollback.sql`；只按 execute_run_id 清理 N4 outbox/state/match/quality/run，并带 N5/N6 downstream guard，不碰 N2/N3。

## N5 动作层

状态：in progress / canonical run-once execute passed。

已完成：

- N5 schema migration。
- action event contract。
- N5-R4 consumer run-once dry-run。
- N5-R4 execute preflight 曾对 synthetic validation 输出 `allow_execute=True`，但未执行写入，且不得作为当前 real N4 outbox 的 execute 授权。
- N5 current-real action preflight / contract review 已登记。
- N5 current-real dry-run / runner semantic implementation 已完成：显式 allowlist 当前 real source_run_id，denylist 旧 synthetic source_run_id。
- N5 dry-run/action planner 已接受 `TriggerMatched + projection_trace + source_event_type=MarketSnapshotUpdated` 作为合法 projection input。
- `BUY_HINT / SELL_HINT` 已映射为 action fact + `HintEvent`。
- `B_BUY_30M_VOL / S_SELL_30M_SHRINK` 已映射为 action fact + `ActionEvent`。
- `TriggerPendingMarketData` 只生成 quality / pending，不生成 action fact。
- projection-trace signal 不再被误判为 unclosed minute risk / blocked_quality RiskEvent。
- N5 current-real action execute contract、rollback SQL 和 row-count guard 已通过。
- N5 current-real action run-once execute 已 passed。
- action_run_id = `action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- source_trigger_run_id = `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`。
- `common_action_run.status=passed`，P0/P1/P2=0/0/0。
- `stock_action_fact=488`，`index_action_fact=0`，`board_action_fact=0`。
- `common_action_event=488`，`common_action_quality_item=276`。
- `common_event_inbox=764 processed`，`common_event_consumer_checkpoint=615`。
- N5 outbox pending：`ActionEvent=479`，`HintEvent=9`，`RiskEvent=0`，`PositionEvent=0`。
- 当前真实 N4 outbox status 仍保持 pending=764；N4/N3/N2 authoritative runs unchanged。
- `common_position_state=0`，`common_position_event=0`。
- no real trade / no sim / no voice / no mobile / no N6。
- rollback_safe=true；rollback SQL=`sql/N5_current_real_action_execute_rollback.sql`。
- N5 canonical action execute contract / preflight / rollback SQL 已登记。
- N5 canonical action run-once execute 已 passed。
- action_run_id = `action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- source_trigger_run_id = `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`。
- `common_action_run.status=passed`，P0/P1/P2=0/0/0。
- `common_action_quality_item=4602`。
- `stock_action_fact=4013`，`index_action_fact=18`，`board_action_fact=254`。
- `common_action_event=4285`，`common_event_outbox=4285`。
- `common_event_inbox=17774`，`common_event_consumer_checkpoint=2146`。
- N5 canonical outbox pending：`ActionBlocked=4285`，`ActionEligible=0`，`ActionExecuted=0`，`ActionSkipped=0`，delivered/delivering=0。
- canonical checks：legacy output events=0，`ActionEvent=0`，`HintEvent=0`，`RiskEvent=0`，`PositionEvent=0`。
- runtime signal distribution for action facts：`B_BUY=2145`，`S_SELL=2140`。
- `BUY_HINT / SELL_HINT` trace-only；`action_mark NULL=4285`；`action_state blocked=4285`；`confirmation_status failed=4285`。
- N4 outbox status unchanged；N6 refs=0；position refs=0；user projection rows=0。
- no real trade / no sim / no voice / no mobile / no N6；worker_started=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260528_canonical_action_execute_rollback.sql`。
- 20260529 N5 canonical action execute 已 passed。
- action_run_id = `action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- source_trigger_run_id = `trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- `common_action_run.status=passed`，P0/P1/P2=0/0/0。
- `common_action_quality_item=4552`。
- `stock_action_fact=4037`，`index_action_fact=18`，`board_action_fact=254`。
- `common_action_event=4309`，`common_event_outbox=4309`。
- `common_event_inbox=17722`，`common_event_consumer_checkpoint=2157`。
- 20260529 N5 outbox pending：`ActionBlocked=4309`，`ActionEligible=0`，`ActionExecuted=0`，`ActionSkipped=0`，delivered/delivering=0。
- 20260529 canonical checks：legacy `ActionEvent/HintEvent/RiskEvent/PositionEvent=0`。
- N4 outbox status unchanged：`TriggerMatched=4309 pending`，`TriggerPendingMarketData=4552 pending`，`TriggerStateChanged=8861 pending`。
- N6 shadow projection rows已登记；position rows for this run=0；worker_started=false。
- no voice / no mobile / no sim / no real trade；old_system_touched=false。
- rollback_safe=true；rollback SQL=`sql/N5_20260529_canonical_action_execute_rollback.sql`；execute report=`docs/N5_20260529_canonical_action_execute_report.json`。
- 20260529 N5 live2 canonical action execute 已 passed。
- action_run_id = `action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- source_trigger_run_id = `trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- `common_action_run.status=passed`，P0/P1/P2=0/0/0。
- `common_action_quality_item=4552`。
- `stock_action_fact=4037`，`index_action_fact=18`，`board_action_fact=254`。
- `common_action_event=4309`，`common_event_outbox=4309`。
- `common_event_inbox=17722`，`common_event_consumer_checkpoint=2157`。
- 20260529 N5 live2 outbox pending：`ActionBlocked=4309`，`ActionEligible=0`，`ActionExecuted=0`，`ActionSkipped=0`，delivered/delivering=0。
- 20260529 live2 canonical checks：legacy `ActionEvent/HintEvent/RiskEvent/PositionEvent=0`。
- N4 live2 outbox status unchanged：`TriggerMatched=4309 pending`，`TriggerPendingMarketData=4552 pending`，`TriggerStateChanged=8861 pending`。
- N6 refs=0；position rows=0；worker_started=false。
- no voice / no mobile / no sim / no position / no real trade。
- rollback_safe=true；rollback SQL=`sql/N5_20260529_live2_canonical_action_execute_rollback.sql`。

待完成：

- 20260529 N6 live2 / full-day user projection gate。
- N6 shadow projection post-review。
- N6 projection business rollback review，仅在需要回滚时进入。
- 后续如需消费 N5 outbox、追加 N6 execute、追加 N5 run-once 或 bounded worker，必须另开 gate。

Entry gate：

- N4 outbox source run 明确且非误用 synthetic 数据；历史 current-real source_run_id 为 `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`，canonical executed source_run_id 为 `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`、`trigger_execute_20260529_condition_layer_20260528_source_20260528_v1` 和 `trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1`。
- N5 current-real dry-run proves the new projection semantics above: done。
- N5 preflight P0=0 after semantic fix: done。
- idempotency、checkpoint、dedup 规则明确。
- rollback SQL and row-count guard present before execute: done。

Exit gate：

- action fact 物理分表。
- canonical 新合同应使用 `ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped`；历史 `ActionEvent / HintEvent / RiskEvent / PositionEvent` 仅作为 20260525 current-real run 证据或兼容项。
- 不写 N6 user projection，不播放语音，不写 sim，不写 position，不真实交易。

Rollback gate：

- 按 `action_run_id` 删除 action facts / events / quality。
- 按 consumer name + source run 回滚 inbox/checkpoint。
- 若 N6 已消费，先停止并交接 N6 rollback。

## N6 用户层

状态：in progress / 20260529 canonical shadow projection passed。

已完成：

- 20260529 canonical shadow projection passed。
- projection_run_id = `user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- source_action_run_id = `action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`。
- run status=passed，P0/P1/P2=0/5/2。
- actual rows：`user_projection_run=1`，`user_signal_projection=4309`，`user_signal_card=4309`，`user_notification_queue=4309`。
- projection policy：notification_source=`n5_action_blocked`，queue_status=`queued_only`，notification queued_only=4309，card mapping blocked/blocked/ActionBlocked/blocked=4309。
- `projection_policy=blocked_unconfirmed_no_push_no_decision_no_sim_no_trade`，trace_json_nonnull=4309，source_action_event_type=`ActionBlocked`，action_state=`blocked`。
- boundary：N5 outbox unchanged，ActionBlocked pending=4309，delivered/delivering=0/0，n5_outbox_consumed=false，updates_n5_outbox_status=false。
- no decision/watchlist/sim/position/real trade；worker_started=false；push/voice/mobile=false；N1-N5 unchanged=true。
- rollback_safe=true；rollback SQL=`sql/N6_projection_business_rollback.sql`。

待完成：

- 20260529 N6 live2 / full-day user projection gate。
- N6 shadow projection post-review。
- user_market_projection。
- user_voice_delivery policy gate。
- user_device_ack policy gate。
- sim_projection separate gate。

Entry gate：

- N5 标准事件已稳定。
- 用户层不得直接读 N4/N5 裸表。
- voice/mobile/sim 策略得到单独确认。

Exit gate：

- 投影可由 event ledger 重建。
- ack / watermark 明确。
- 语音只播 watermark 后的新事件，最多补播 1 条。

Rollback gate：

- 按 projection run 或 event watermark 重建/清理用户投影。
- 不回写 N1-N5。
- 不影响真实交易，因为真实交易尚未启用。
- 20260529 shadow rollback SQL：`sql/N6_projection_business_rollback.sql`；仅按 projection_run_id 清理 N6 projection rows，且必须先确认 linked decision/sim refs=0。

## 近期推荐路线

```text
R1: 确认权威 active N2 run = condition_layer_20260522_to_20260525_20260525102249_execute。
R2: 确认权威 N3 subscription run = market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute。
R3: 确认权威 N3 preload run = previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute。
R4: 登记 N3-B1 passed，当前 MarketSnapshotUpdated pending=2188。
R5: 登记 N4 current context rebuild，确认 context rows=4512、P0/P1/P2=0/0/0。
R6: N4 real MarketSnapshotUpdated / realtime projection semantics dry-run，验证只读取当前 N3-B1 outbox，不写 inbox/trigger fact/N4 outbox。
R7: 登记 N3 projection schema ready + N3-B2 input diagnosis：曾因缺今日 1m 只能 not_ready skeleton。
R8: 登记 N3-C1 今日 minute_bar_1m execute passed，补齐 projection dry-run 所需今日 1m 输入；C1 outbox=0，未生成 MinuteBarClosed。
R9: 登记 N3-B2 realtime projection execute passed；projection rows=2188，ready=2052，not_ready=136，outbox/inbox=0。
R10: N4 projection matcher dry-run / preflight / run-once execute 已 passed；N4 outbox pending=764，delivered/delivering=0。
R11: N5 current-real action run-once execute 已 passed；N5 outbox pending=488，N4 current outbox remains pending=764。
R12: N6 user projection contract review 可进入；N5 outbox consumption、N6 execute、worker、voice、mobile、sim、position、真实交易均后置。
R13: N3-C2 closed-minute / closed-30m replay execute 已 passed；closed_30m_summary rows=17504，C2 outbox/inbox/checkpoint refs=0。
R14: N3-C3 MinuteBarClosed outbox execute 已 passed；MinuteBarClosed pending=17432，delivered/delivering=0。
R15: N3-C2B closed_signal_enrichment execute 已 passed；enrichment rows=17504，computable=17432，unknown/missing=72，c2b outbox/inbox/checkpoint refs=0。
R16: N4-C3 replay audit execute 已 passed；audit rows=35970，classification=would_match 4734 / would_clear 245 / would_change 243 / unchanged 30730 / missing 18 / not_ready 0，C3 outbox remains pending=17432，rollback_safe=true。
R17: N3-EOD snapshot refresh dry-run 已 PASS；execute preflight BLOCKED，blocker=missing_official_daily_fact，expected EOD rows=2188，official_daily_missing=2188，C3 outbox pending=17432，P0/P1/P2=0/3/0，EOD scoped business/run/quality/outbox/inbox/checkpoint rows=0。
R18: 20260528 canonical v2 N4 trigger execute 已 passed；N4 outbox pending=17774，其中 TriggerMatched=4285、TriggerPendingMarketData=4602、TriggerStateChanged=8887；N5 refs=0，N6 refs=0，rollback_safe=true。
R19: 20260528 canonical N5 action execute 已 passed；action_run_id=action_consumer_canonical_20260528_trigger_execute_20260528_condition_layer_20260527_source_20260527_v2，N5 outbox pending=ActionBlocked 4285，N5 inbox/checkpoint=17774/2146，legacy output events=0，N6 refs=0，position refs=0，rollback_safe=true。
R20: 20260528 N1 ingestion 已 passed：official daily fact rows=6017，condition source rows=80811，active daily/source versions 已写入，check_condition_source_ready --source-trade-date 20260528 passed=true，outbox/inbox/checkpoint delta=0/0/0。
R21: 20260528 -> 20260529 N2 condition layer execute 已 passed：run_id=condition_layer_20260528_source_20260528_v1，status=passed_active，P0/P1/P2=0/6/3，quality_rows=106，condition_basis=5506/83/428，condition_pool=4271/18/263，minute_target_scope=4271/18/263，canonical_signal_audit_passed=true，deprecated_signal_rows=0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true。
R22: 20260529 N3 subscription execute 已 passed：market_data_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，source_condition_run_id=condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，P0/P1/P2=0/0/0，candidate/subscription/pull_plan/quality rows=5038/2643/7/34，objects stock/index/board/total=2021/9/127/2157，required_data_kind realtime_daily_snapshot/minute_bar_1m/previous_day_minute_bar_1m=2157/243/243，deprecated_signal_rows=0，market_data_pulled=false，market_data_fact_written=false，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，rollback_safe=true。
R23: 20260529 A1 previous_day_minute preload 已 passed：preload_run_id=previous_day_minute_preload_20260528_for_20260529__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，actual rows stock/index/board/total=56160/0/2160/58320，object status stock passed/partial/missing=234/0/0，index expected objects/rows=0/0，board passed/partial/missing=9/0/0，fake index pull / fake index rows=0/0，P0/P1/P2=0/0/0，quality_rows=12，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，old_system_touched=false，rollback_safe=true。
R24: 20260529 B1 pre-open realtime snapshot fact-only 已 passed：snapshot_run_id=realtime_snapshot_20260529_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，pre_open_fact_only=true，live_trading_snapshot_ready=false，rows stock/index/board/total=2021/9/127/2157，missing/failed=0/0，P0/P1/P2=0/1/0，quality_rows=11，writes_outbox=false，generated_outbox_events=[]，source_time_missing_or_preopen total/stock/index=2030/2021/9，source_time_confirmed board=127，P1 warning=n3_b1_pre_open_source_time_not_confirmed，P0 source date mismatch=0，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=105122/20726/4345，downstream_layers_touched=false，worker_started=false，N4/N5/N6 touched=false，rollback_safe=true。
R25: 20260529 B1 live1 realtime snapshot fact-only 已 passed：snapshot_run_id=realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，live_trading_snapshot_ready=true，pre_open_fact_only=false，rows stock/index/board/total=2021/9/127/2157，missing/failed=0/0，P0/P1/P2=0/0/0，quality_rows=11，writes_outbox=false，generated_outbox_events=[]，stock effective_quote_present/source_time_missing/partial_quality=2021/2021/0，index effective_quote_present/source_time_missing/partial_quality=9/9/0，board source_time_confirmed/effective_quote_present=127/127，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint=105122/20726/4345，downstream_layers_touched=false，worker_started=false，N4/N5/N6 untouched=true，rollback_safe=true。
R26: 20260529 B1 live2 standard outbox snapshot 已 passed：snapshot_run_id=realtime_snapshot_20260529_live2_outbox_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1，common_market_data_run.status=passed，rows stock/index/board/total=2021/9/127/2157，P0/P1/P2=0/0/0，writes_outbox=true，MarketSnapshotUpdated=2157 pending，MarketDataDelayed/MarketDataMissing/MarketDisplaySnapshotUpdated=0/0/0，delivered/delivering=0/0，scoped inbox/checkpoint refs=0/0，no inbox/checkpoint writes，downstream_layers_touched=false，worker_started=false，N4/N5/N6 not entered=true，scoped exception used for existing N6 web app / old system process but they did not consume v3 outbox，rollback_safe=true。
R27: 20260529 N4 live2 canonical trigger execute 已 passed：execute_run_id=trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，rows common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=17/8861/8861/17722，outbox pending TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=4309/4552/8861，delivered/delivering=0/0，canonical checks passed，N3 live2 input MarketSnapshotUpdated pending=2157，N3 input inbox/checkpoint refs=0/0，N5 refs=0，downstream inbox/checkpoint refs=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，worker_started=false，action/user/voice/mobile/sim/position/real_trade touched=false，rollback_safe=true。
R28: 20260529 N4 canonical trigger execute 已 passed：execute_run_id=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，rows common_trigger_run/common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=1/16/8861/8861/17722，outbox pending TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=4309/4552/8861，delivered/delivering=0/0，canonical checks passed，scoped inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，global delta outbox/inbox/checkpoint=+17722/0/0，outbox_consumed=false，N5/N6 touched=false，worker_started=false，N2/N3 facts unchanged=true，rollback_safe=true。
R29: 20260529 N5 live2 canonical action execute 已 passed：action_run_id=action_consumer_canonical_20260529_live2_trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，source N4 run=trigger_execute_20260529_live2_condition_layer_20260528_source_20260528_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=4552/4037/18/254/4309/4309/17722/2157，N5 outbox pending=4309 ActionBlocked，legacy output events=0，N4 outbox status unchanged，N6 refs=0，position rows=0，worker_started=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true。
R30: 20260529 N5 canonical action execute 已 passed：action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，source N4 run=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，P0/P1/P2=0/0/0，actual rows common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=4552/4037/18/254/4309/4309/17722/2157，N5 outbox pending=4309 ActionBlocked，legacy output events=0，N4 outbox status unchanged，N6 refs=0，position rows=0，rollback_safe=true。
R31: 20260529 N6 canonical shadow projection 已 passed：projection_run_id=user_projection_shadow_20260529__action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，source_action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1，run status=passed，P0/P1/P2=0/5/2，actual rows user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/4309/4309/4309，notification_source=n5_action_blocked，queue_status=queued_only，projection_policy=blocked_unconfirmed_no_push_no_decision_no_sim_no_trade，N5 outbox unchanged ActionBlocked pending=4309，n5_outbox_consumed=false，updates_n5_outbox_status=false，decision/watchlist/sim/position/real_trade refs=0，worker_started=false，push/voice/mobile=false，N1-N5 unchanged=true，rollback_safe=true。
R32: 027 N2 symmetry target price canonical compatibility migration 已 passed：12 N2 tables touched，new canonical fields exist=true，CHECK constraints validated=true，locked_target_price / target_lock_status absent=true，business row count delta=0，outbox/inbox/checkpoint delta=0/0/0，new fields non-null count=0，rollback_safe=true。
R33: N2 canonical condition v2 active lineage supersede execute 已 passed：new active run_id=condition_layer_20260528_source_20260528_v2，v2.status=passed_active，previous active v1=condition_layer_20260528_source_20260528_v1，v1.status=superseded，v1 rows and downstream refs preserved，N3 not automatically rebuilt，N4/N5/N6 not entered，worker_started=false，outbox/inbox/checkpoint delta=0/0/0，quality_item=103，P0/P1/P2=0/3/3，alias mismatch=0，negative numeric fields=0，forbidden fields=0，first failed attempt rolled back due negative reference_target_price CHECK，writer fixed negative canonical target numeric fields to NULL and preserved raw negative value only in trace，rollback_safe=true。
R34: N2 display scope alignment v3 已 preserved/superseded：run_id=condition_layer_20260528_source_20260528_v3，曾为 passed_active，condition_display_basis stock/index/board=2021/9/127，common_condition_quality_item=103，P0/P1/P2 failed=0/0/0，rollback_safe=true。
R35: N2 symmetry target price alignment v5 已 passed_active：active N2 run=condition_layer_20260528_source_20260528_v5，previous active v4=condition_layer_20260528_source_20260528_v4，v4.status=superseded，passed_active_count=1，000027 buy_target_price/reference_target_price=8.42/8.42，condition_pool=4271/169/875，minute_target_scope=4251/169/875，condition_display_basis=2011/83/428，common_condition_quality_item=103，P0/P1/P2=0/3/3，outbox/inbox refs=0/0，N3/N4/N5 refs=0/0/0，rollback_safe=true。
R36: 20260529 -> 20260601 N2 condition layer v1 已 preserved/superseded：run_id=condition_layer_20260529_source_20260529_v1，曾为 passed_active，source_trade_date/for_trade_date/prev_trade_date=20260529/20260601/20260529，condition_basis=5506/83/428，condition_pool=4342/187/942，minute_target_scope=4323/187/942，condition_display_basis=1973/83/428，monitor_target=5506/83/428，common_condition_quality_item=109，P0/P1/P2=0/9/3，rollback_safe=true。
R37: 20260529 -> 20260601 N2 financial canonical v2 active supersede 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v2，v1.status=superseded，后续已被 v3 active supersede；condition_basis=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106，P0/P1/P2=0/6/3，financial pass-through mismatch basis/pool/scope/display=0/0/0/0，canonical_financial_pass_through_mismatch=0，outbox/inbox/checkpoint delta=0/0/0，N3/N4/N5 refs=0/0/0，rollback_safe=true。
R38: 20260529 -> 20260601 N2 symmetry target price target-machine v3 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v3，v2.status=superseded，后续已被 v4 active supersede，000543 buy_target_price/reference_target_price=10.82/10.82，000027 buy_target_price/reference_target_price=8.45/8.45，condition_basis=5506/83/428，condition_pool=4106/187/942，minute_target_scope=4087/187/942，condition_display_basis=1862/83/428，monitor_target=5506/83/428，common_condition_quality_item=106，P0/P1/P2=0/6/3，outbox/inbox/checkpoint delta=0/0/0，v3 downstream refs=0，rollback_safe=true。
R39: 20260529 -> 20260601 N2 anchor-segment alignment v4 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v4，后续已被 v5 active supersede，row counts aligned，golden 000600/000543/000027=12.93/10.82/8.45，P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true。
R40: 20260529 -> 20260601 N2 secondary-anchor v5 已 passed/preserved：run_id=condition_layer_20260529_source_20260529_v5，后续已被 v6 active supersede，P0/P1/P2=0/6/3，N3/N4/N5/N6 refs=0/0/0/0，outbox/inbox/checkpoint refs=0/0/0，rollback_safe=true。
R41: 20260529 -> 20260601 N2 level score v6 已 passed_active：active N2 run=condition_layer_20260529_source_20260529_v6，previous active v5=superseded，P0/P1/P2=0/6/3，level_score_ok=true，row_match=true，golden 000543/000600/300327 level_score_up/down=3124/0、3124/0、2999/125，N3/N4/N5 refs=0/0/0，outbox/inbox/checkpoint delta=0/0/0，rollback_safe=true。
R42: N3 action-confirmation projection writer execute 已 passed：projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_condition_run_id=condition_layer_20260601_source_20260601_v1，source_subscription_run_id=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_snapshot_run_id=realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_today_minute_run_id=today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，source_previous_day_minute_run_id=previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，common_market_data_run.status=passed，rows stock/index/board/total=765/54/150/969，metric_ready/not_ready=969/0，common_market_data_quality_item=6，P0/P1/P2=0/0/0，market_data_pulled=false，market_data_fact_written=true，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint=0/0/0，global outbox/inbox/checkpoint delta=0/0/0，no outbox write/consume，no inbox/checkpoint write，rollback_safe=true。
R43: N4 action-confirmation metric business execute 已 passed：execute_run_id=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，source_condition_run_id=condition_layer_20260601_source_20260601_v1，source_projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1，trigger_context_run_id=trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1，common_trigger_run.status=passed，common_trigger_run=1，common_trigger_quality_item=10，common_trigger_state=5941，common_trigger_match=5941，common_event_outbox=5941，TriggerMatched=6 pending，TriggerPendingMarketData=5935 pending，TriggerStateChanged=0，delivered/delivering=0/0，P0/P1/P2=0/1/0，quality distribution P0 passed=9、P1 warning=1，P1=n4_action_confirmation_metric_pending_candidates_visible non-blocking，N3 metric facts unchanged stock/index/board=765/54/150，common_event_inbox refs=0，checkpoint refs=0，N5 refs=0，N3 outbox consumed=false，inbox/checkpoint written=false，N5/N6 entered=false，worker_started=false，market_data_pulled=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true。
R44: N5 action-confirmation metric execute 已 passed：action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，source N4 run=trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/5935/1/4/0/5/5/5941/2487，event distribution ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped=4/1/0/0，N5 outbox pending ActionExecuted=4、ActionBlocked=1，delivered/delivering=0/0，N4 outbox status unchanged，N6/user/downstream refs=0，position refs=0，voice/mobile/sim/real_trade refs=0，worker_started=false，rollback_safe=true。
R45: N6 20260602 action-confirmation metric shadow projection execute 已 passed：projection_run_id=user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，source_action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1，preflight_result=PREFLIGHT_PASS，run status=passed，P0/P1/P2=0/5/2，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/5/5/5，queue distribution n5_action_executed/n5_action_blocked queued_only=4/1，card distribution ActionExecuted -> action_confirmed/executed/30m_shrink=4、ActionBlocked -> blocked/blocked=1，N5 outbox unchanged ActionExecuted=4 pending、ActionBlocked=1 pending，N5 outbox consumed=false，N5 outbox status updated=false，user_signal_decision=0，linked user_sim_order/trade/position=0/0/0，user_watchlist/watchlist_item=0/0，worker_started=false，push/voice/mobile=false，sim/position/real_trade=false，rollback_safe=true。
R46: N1 20260602 source baseline complete：official daily `official_daily_ingest_20260602_v1` 已 passed，stock/index/board/total=5507/83/428/6018，active source_version=`stock_daily_20260602_v1`、`index_daily_20260602_v1`、`board_daily_20260602_v1`，source validation P0/P1/P2=0/19/0，rollback_safe=true；condition source `condition_source_activation_20260602_v1` 已 passed，stock_daily_basic/stock_financial/index_membership/board_membership/total=5507/5507/12841/56960/80815，active source_version=`stock_daily_basic_20260602_v1`、`stock_financial_20260602_v1`、`index_membership_20260602_v1`、`board_membership_20260602_v1`，P0/P1/P2=0/2/1，outbox/inbox/checkpoint delta=0/0/0，N2/N3/N4/N5/N6 refs=0/0/0/0/0，rollback_safe=true。
R47: N2 condition layer 20260602 已 passed_active：run_id=condition_layer_20260602_source_20260602_v1，source_trade_date/for_trade_date=20260602/20260603，policy_source=8782_console，policy_id=n2_default_policy，policy_version=v4，policy_hash=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576，P0/P1/P2=0/9/3，condition_basis=5507/83/428，condition_pool=4182/168/890，minute_target_scope=4164/168/890，condition_display_basis=1963/83/428，monitor_target=5507/83/428，common_condition_quality_item=109，row_mismatches={}，outbox/inbox/checkpoint refs=0/0/0，N3/N4/N5/N6 refs=0/0/0/0，rollback_safe=true。
R48: N3 subscription 20260603 已 passed：market_data_run_id=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，source_condition_run_id=condition_layer_20260602_source_20260602_v1，common_market_data_run.status=passed，source_trade_date/for_trade_date/prev_trade_date=20260602/20260603/20260602，candidate/subscription/pull_plan/quality rows=5776/3028/9/34，objects stock/index/board/total=1963/83/428/2474，required_data_kind realtime_daily_snapshot/minute_bar_1m/previous_day_minute_bar_1m=2474/277/277，P0/P1/P2=0/1/0，P1=historical common_trade_calendar(20260603) missing warning，market_data_pulled=false，market_data_fact_written=false，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，scoped outbox/inbox/checkpoint refs=0/0/0，A1/B1/N4/N5/N6 touched=false，rollback_safe=true，rollback_sql=sql/N3_subscription_20260603_rollback.sql。
R49: A1 previous-day minute preload 20260603 已 passed：preload_run_id=previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，source subscription run=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_market_data_run.status=passed，actual rows stock/index/board/total=57840/480/8160/66480，object status stock/index/board/total=241/2/34/277 all passed，missing/partial/failed=0/0/0，P0/P1/P2=0/1/0，P1=n3_a1_contract_p1_carried rooted in historical common_trade_calendar(20260603) missing warning，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint unchanged=164214/68560/5163，realtime snapshot rows for this run=0/0/0，event_outbox_written=false，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=sql/N3_A1_previous_day_minute_20260603_rollback.sql。
R50: common_trade_calendar(20260603) repair 已 passed：source_batch_id/source_version=trade_calendar_20260603_patch_v1，common_trade_calendar(20260603)=1，is_open=true，prev_trade_date=20260602，next_trade_date=20260604，active source_version common/trade_calendar/SSE:20260603 -> trade_calendar_20260603_patch_v1，common_ingest_batch/common_quality_gate_result/common_active_source_version=1/11/1，persisted quality P0 passed=11，outbox/inbox/checkpoint delta=0/0/0，B1 realtime snapshot refs=0，N4 refs=0，N5 refs=0，N2/N3/A1 refs remain=1/2/1，worker_started=false，realtime_market_data_pulled=false，delivery/notification/push/voice/mobile/sim/position/real_trade=false，rollback_safe_scope=true，hard_fail_before_delete=true，rollback_sql=sql/N1_trade_calendar_20260603_patch_rollback.sql，standalone calendar rollback currently expected to hard-fail because N2/N3/A1 refs exist。
R51: B1 realtime snapshot 20260603 fact-only retry 已 passed：snapshot_run_id=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，source subscription run=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_market_data_run.status=passed，actual/expected rows stock/index/board/total=1963/83/428/2474，quality_rows=11，P0/P1/P2=0/1/0，P1=n3_b1_contract_p1_carried 非阻断，BJ fallback index:BJ:899050/index:BJ:899601 均已写入且 quality_status=passed，source_version=tushare.index_daily.bj_snapshot_fallback.v1，source_path=tushare.index_daily.previous_trade_date_bootstrap，writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint delta=0/0/0，N4/N5/N6 refs=0，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=sql/N3_B1_realtime_snapshot_20260603_rollback.sql。
R52: B1 realtime snapshot 20260603 fact-only retry 已 passed：snapshot_run_id=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，source subscription run=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_market_data_run.status=passed，actual/expected rows stock/index/board/total=1963/83/428/2474，quality_rows=11，P0/P1/P2=0/1/0，P1=n3_b1_contract_p1_carried 非阻断，BJ fallback index:BJ:899050/index:BJ:899601 均已写入且 quality_status=passed，source_version=tushare.index_daily.bj_snapshot_fallback.v1，source_path=tushare.index_daily.previous_trade_date_bootstrap，writes_outbox=false，generated_outbox_events=[]，scoped outbox/inbox/checkpoint refs=0/0/0，global outbox/inbox/checkpoint delta=0/0/0，N4/N5/N6 refs=0，downstream_layers_touched=false，worker_started=false，rollback_safe=true，rollback_sql=sql/N3_B1_realtime_snapshot_20260603_rollback.sql。
R53: N4 trigger_context_snapshot 20260603 rebuild 已 passed：trigger_context_run_id=trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1，source_condition_run_id=condition_layer_20260602_source_20260602_v1，source_market_data_run_id=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，market_subscription_run_id=market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/0/0，rows stock/index/board/total=4164/168/890/5222，object coverage stock/index/board=1963/83/428，BUY_HINT/SELL_HINT trace rows=216/61，period_trigger_baseline_json_missing=0，required_period_not_ready_rows=0，common_trigger_run/common_trigger_quality_item=1/62，common_trigger_state/common_trigger_match/common_event_outbox=0/0/0，common_event_inbox refs=0，checkpoint refs=0，N5 refs=0，N6 refs=0，N3 B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0，market_data_pulled=false，n3_event_consumed=false，worker_started=false，N5/N6 not entered=true，old_system/real_trade=false，rollback_safe=true，rollback_sql=sql/N4_20260603_trigger_context_rebuild_rollback.sql。
R54: N4 canonical trigger execute 20260603 matcher fix 后已 passed：execute_run_id=trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/1/0，quality_rows=17，common_trigger_state/common_trigger_match/common_event_outbox=10167/10167/20334，TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=1252/8915/10167，outbox pending/delivered/delivering=20334/0/0，runtime signal B_BUY/S_SELL=5164/5003，deprecated_runtime_signal_count=0，trigger_mark_candidate normal/30m_volume/30m_shrink=5222/2474/2471，pending_market_data trigger_live=false=8915，matched trigger_live=true=1252，TriggerStateChanged in common_trigger_match=0，final action_mark columns in trigger state/match=0，anomaly proof：B_BUY current_price/close <= open=0、S_SELL current_price/close >= open=0、B_BUY amount below localized baseline=0、S_SELL amount above localized baseline=0，inbox/checkpoint refs=0/0，N5 refs common_action_run/common_action_event=0/0，N6 refs projection/card/queue=0/0/0/0，source B1 snapshot outbox/inbox/checkpoint refs remain 0/0/0，worker_started=false，delivery/notification/push/voice/mobile/sim/position/real_trade=false，rollback_safe=true before downstream consumption，rollback_sql=sql/N4_20260603_canonical_trigger_execute_rollback.sql。
R55: N5 canonical action execute 20260603 retry after status persistence fix 已 passed：action_run_id=action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，source N4 run=trigger_execute_20260603_condition_layer_20260602_source_20260602_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/8915/1056/26/170/1252/1252/20334/2474，event distribution ActionBlocked/ActionEligible/ActionExecuted/ActionSkipped=1252/0/0/0，N5 outbox pending/delivered/delivering=1252/0/0，N4 outbox unchanged TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=1252/8915/10167 pending，N6/user refs=0，position rows=0/0，worker_started=false，voice/mobile/sim/position/real_trade=false，rollback_safe=true，rollback_sql=sql/N5_20260603_canonical_action_execute_rollback.sql。
R56: N4_TRIGGER_RULE_SPEC_v4 execute 20260603 已 passed：execute_run_id=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，source_condition_run_id=condition_layer_20260602_source_20260602_v1，common_trigger_run.status=passed，P0/P1/P2=0/0/0，common_trigger_run/common_trigger_quality_item/common_trigger_state/common_trigger_match/common_event_outbox=1/4/863/863/863，TriggerMatched pending=863，delivered/delivering=0/0，matched-only persistence 已生效，BJ quality-blocked 与 BUY:FULL/SELL:FULL blocked 均未写 TriggerMatched，invalid N5 entry=0，N5 refs at execute post-review=0，worker_started=false，rollback_safe=true，rollback_sql=sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql。
R57: N5_MARKET_ACTION_CONFIRMATION_SPEC_v1 execute 20260603 已 passed 并 preserve-only：action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，source N4 run=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，N3 action_metric_run_id=action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，common_action_run.status=passed，P0/P1/P2=0/0/0，actual rows common_action_run/common_action_quality_item/stock_action_fact/index_action_fact/board_action_fact/common_action_event/common_event_outbox/common_event_inbox/common_event_consumer_checkpoint=1/0/680/34/149/863/863/863/822，event distribution ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped=863/0/0/0，blocked_reason price_confirmation_failed/amount_confirmation_failed/metric_missing=838/25/0，N5 outbox pending/delivered/delivering=863/0/0，N4 outbox unchanged TriggerMatched pending=863，fresh DB proof 显示 N6/user refs 已存在 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，position refs=0/0，worker_started=false，voice/mobile/sim/position/real_trade=false，action_mark final-only proof passed；rollback SQL 仍 hard-fail before DELETE，但 N5 rollback 当前必须先处理 N6 refs，rollback_sql=sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql。
R58: N6 20260603 v1 market-action-confirmation shadow projection post-review recovery 已 passed：source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1，fresh DB proof 显示 user_projection_run.status=passed，P0/P1/P2=0/5/2，input/output=863/863，user_projection_run/user_signal_projection/user_signal_card/user_notification_queue=1/863/863/863，card_status=blocked 863，notification_source=n5_action_blocked / queued_only=863，position refs=0/0，shadow_projection=true，n5_outbox_consumed=false，n5_outbox_status_updated=false；post-review artifacts=docs/N6_20260603_V1_MARKET_ACTION_CONFIRMATION_PROJECTION_POST_REVIEW.md and docs/N6_20260603_v1_market_action_confirmation_projection_post_review.json。
R59: 后续只允许 delivery/notification gate、N6 rollback review、runtime_control read-only dashboard / lineage review、N3_market_data subscription rebuild gate for 20260529 based on condition_layer_20260528_source_20260528_v5、N3_market_data subscription rebuild gate for 20260601 based on condition_layer_20260529_source_20260529_v6、20260529 N6 live2 / full-day user projection gate；runtime_control 不执行新的 N6，不消费 N4/N5 outbox，不启动 worker，N5 outbox consumption、N5 outbox status update、additional N6 execute、N4/N5/N6 replay event execute、EOD execute、daily close、worker、delivery、notification、push、voice、mobile、sim、position 和真实交易仍保持禁止，必须另行确认。
```

## N2-Display 扩展路线

状态：done。

结果：在不改变 N3/N4/N5 交易链路的前提下，N2 已额外生成 `stock/index/board_condition_display_basis`，作为 N6 展示输入。

落地 gate：

```text
N2-Display-1 schema review：done。
N2-Display-2 migration：done。
N2-Display-2b quality CHECK migration：done。
N2-Display-3 dry-run：done。
N2-Display-4 overwrite：done，新 active run 已生成。
N2-Web-3：todo，8782 增加 display_basis 只读展示。
```

回滚 gate：`condition_display_basis` 必须与同一 N2 run_id 的 basis/pool/scope 同生命周期回滚；不得单独补写到旧 active run。

## N3N6Q：N6 虚拟账户股票报价窄接口

状态：`contract_registered_design_only`。

边界已冻结：

```text
N3-A1 / N3-B1 / N3-B2 / N3-C1 / N3P / N3T unchanged
existing N3 poller / worker / schema / outbox / inbox / checkpoint unchanged
N3N6Q database writes = 0
N3N6Q events = 0
A-track calls = 0
```

推荐路线：

1. `N3_market_data` 在独立 worktree 仅新增 `src/ashare_v3/n3n6q/` 与 fake-adapter tests。
2. provider contract/test 通过后，另开 read-only Mootdx live probe；不得在 provider gate 拉行情。
3. `N6_user` 另开 quote schema/persistence gate，独占调度、trade_date/freshness、N6 snapshot。
4. portfolio 估值、首日止损冻结、stop proposal、confirm/虚拟卖出分别独立 gate。
5. runtime 发布与 LaunchAgent 必须最后由 `runtime_control` 另行授权；当前合同不安装、不启动。

仍禁止：修改或调用既有 N3 模块、写 N3/N6 DB、生成 N3 event、启动 poller/worker、真实交易、券商、跨层回写。
