# v3 Execution Protocol (UNIFIED CONTROL SYSTEM)

Before ANY modification in A股监控系统 v3, Codex MUST follow this strict pipeline:

================================================
STEP 1 — TASK NORMALIZATION
================================================
Convert user request into structured intent:
- intent
- affected_files
- layer_role (N1-N6)
- risk_level

If cannot normalize → STOP

================================================
STEP 2 — EXECUTION COMPILER
================================================
Convert task into execution plan (DAG):

MUST include:
PLAN → VALIDATE → MODIFY → VERIFY → FINALIZE

Rules:
- MODIFY must always be preceded by VALIDATE
- No cycles allowed
- No cross-layer operations allowed

If DAG invalid → STOP

================================================
STEP 3 — KERNEL CHECK
================================================
Evaluate:
- Is operation allowed in layer_role?
- Does it violate N1-N6 boundaries?
- Is risk acceptable?

Output:
ACCEPT / REJECT / BLOCK / ESCALATE

If not ACCEPT → STOP

================================================
STEP 4 — RUNTIME GATE
================================================
Final safety enforcement:

- Cross-layer modification → REJECT
- Runtime execution request → REJECT，除非精确满足以下任一 fail-closed policy：
  - `n6_strategy_center_display_only_bounded_run_once_v1`
  - `n6_strategy_center_display_only_scheduled_evaluator_v1`
  - `n6_user_web_immutable_release_bounded_rebind_v1`
  - `n6_strategy_center_schema_migration_maintenance_window_v1`
  - `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`
  - `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`
  - `n6_strategy_center_post_081_v2_catalog_migration_window_v1`
  - `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`
  - `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`
  - `n6_strategy_center_pre_canary_web_write_quiesce_v1`
  - `n6_strategy_center_reviewed_view_date_authority_084_v1`
  - `n6_strategy_center_post_canary_web_write_restore_v1`
  - `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`
  - `n6_strategy_center_v1_retirement_after_all_users_v2_v1`
  - `n6_immutable_release_install_bounded_v1`
  - `n6_immutable_release_install_pre_rename_validator_recovery_v1`
  - `n6_immutable_release_install_preflight_git_violation_recovery_v1`
  - `n3_higher_period_amount_rollover_controlled_promotion_v1`
  - `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`
  - `n4_lifecycle_inactive_mark_recovery_v1`
  - `n4_lifecycle_inactive_projection_type_reset_v1`
  - `n6_immutable_release_install_eacces_retry_v1`
  - `n6_immutable_release_install_host_eacces_remediation_v1`
  - `n6_immutable_release_privileged_atomic_install_v1`
  - `n6_immutable_release_privileged_materialize_and_install_v1`
  - `n6_immutable_release_privileged_materialize_and_install_f67_v1`
  - `runtime_hot_cleanup_archive_gated_disk_governance_v1`
  - `n1_local_artifact_archive_daily_bounded_install_v1`
  - `windows_rebuild_w0_bounded_v1`
- Missing kernel decision → REJECT

If not ACCEPT → STOP

================================================
STEP 5 — SANDBOX SIMULATION
================================================
Simulate:

- file changes
- system impact
- DAG execution

If unsafe → STOP

================================================
STEP 6 — FINAL EXECUTION
================================================
Only if ALL steps passed:

→ Apply changes
→ Output diff
→ Log trace

================================================
HARD RULE
================================================

NO STEP CAN BE SKIPPED.

If any step is missing → TASK IS INVALID.

## Execution Mode System

### 1. Mode Classifier (MANDATORY)

Before execution, Codex MUST classify task into:

- LIGHT MODE
- FULL MODE

---

### 2. Classification Rules

LIGHT MODE if:

- single file change
- no N1–N5 structure change
- no trigger/action modification
- no schema change
- no DAG required

FULL MODE if:

- multi-file change
- N1–N5 logic modification
- trigger/action modification
- schema change
- risk_level >= medium

---

### 3. LIGHT MODE FLOW

- Kernel Check ONLY
- Direct modification allowed only after Evidence-Bound Modification Guard passes
- Minimal Trace
- NO Compiler
- NO Sandbox

---

### 4. FULL MODE FLOW

- Execution Compiler (DAG)
- Kernel Check
- Runtime Gate
- Sandbox Simulation
- Full Trace
- Execution

---

### 5. HARD RULE

Mode MUST be decided BEFORE execution.

If mode is not determined → STOP

# AGENTS.md

本文件是 A股监控系统 v3 的项目级 Codex 指令。任何 Codex/AI 助手进入本项目后，必须先阅读本文件，再继续任务。

## 1. 项目定位

本项目是 A股监控系统 v3。

项目路径：

- `/Users/chuanfuchen/Documents/A股监控系统v3`

v3 当前目标是重新设计并实现一个分层清晰、可追溯、可回滚的交易监控系统。

`AGENTS.md` 只保留执行硬规则、边界和流程要求，不再承载详细历史进度。当前权威状态、推荐路线和任务看板以以下三份总控文档为准：

```text
docs/Architecture.md
docs/Roadmap.md
docs/Tasks.md
```

当前状态约束：

```text
AGENTS.md 不维护具体 live run_id、行数、outbox 数量或当前阶段完成度。
当前权威状态、推荐路线和任务看板只以 docs/Architecture.md、docs/Roadmap.md、docs/Tasks.md 以及最新 gate artifact 为准。
历史报告、旧 run_id、旧 execute 摘要只能作为历史证据，不得被当作当前 active lineage 或 rollback/downstream proof。
如总控状态、lineage、rollback 安全性或 downstream refs 存在差异，必须通过专门 review / registration / supersession gate 登记，不得静默改写历史 run 证据。
```

RAG-first 状态问答规则：

```text
对于项目状态、lineage、gate result、rerun_required、rollback SQL、next gate / next step 类问题，
Codex 必须先查询本地只读 RAG helper 或 8786 RAG artifacts，再回答。
RAG 证据是 artifact-first、只读证据入口；不得执行命令、不得写数据库、不得启动 worker、
不得消费/update outbox/inbox/checkpoint，也不得替代 process / service / live DB runtime 问题的实时验证。
对于代码实现、页面报错、服务进程、live row count、launchd loaded 状态或 execute 请求，
RAG 只能作为辅助证据，仍必须按当前任务范围做 live/code/process/read-only verification。
```

当前允许做：

- 原始数据入库层维护
- 标准事实表维护
- 数据质量闸门
- 历史归档设计
- 入库回滚与审计
- 条件层维护、dry-run / diagnosis、回滚与审计
- N3 实时行情层开发文档
- N3 market_data_subscription dry-run / preflight 设计
- N3-C2 closed-minute / closed-30m incremental schema readiness 与 additive migration draft
- N3 / N4 / N5 当前 real lineage 的总控登记、复核、回滚与审计
- N4 触发层文档 / schema / event contract / current-real run-once 后续 gate 复核
- N5 动作层文档 / schema / event contract / current-real run-once 后续 gate 复核
- N6 user projection contract review
- runtime orchestration / dashboard / pipeline state machine 文档、schema 草案、只读 dashboard
- 总控架构、路线图、任务看板等文档维护

N4/N5/N6 runtime 触发与动作语义的最新权威规范为：

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
```

上述文档是 trigger/action/user runtime canonical spec。`docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md` 仅拥有 N4 trigger-side rule definitions 主权；`docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md` 负责 runtime 边界；`docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md` 负责状态流与跨层边界；`docs/N5_CANONICAL_ACTION_FLOW_v0.1.md` 负责 N5 action flow。若旧设计文档、历史报告、SQL 草案、测试或代码与该规范冲突，后续对齐工作以该规范为准；历史 run 证据不得静默改写，只能通过明确 migration / compatibility / alignment gate 处理。

当前 canonical runtime 语义硬规则：

```text
N1 -> N2 -> N3 -> N4 -> N5 -> N6 只能单向流动。
下游不得回写、重算或重新解释上游职责；上游不得混入下游用户策略。
N2 -> N4 只传买卖信号条件语义和触发阈值，不传 alert-only / display / voice / sim / trade intent。
N4 只负责触发状态和触发结果，输出 TriggerStateChanged / TriggerMatched / TriggerPendingMarketData。
TriggerMatched 是 N5 新动作确认 episode 的唯一入口并负责生成 ActionEligible；TriggerPendingMarketData 只能作为 no-op / quality-only / state-gate，不允许 N5 开始动作确认；TriggerStateChanged 不写 common_trigger_match，也不得独立创建 episode 或 ActionEligible。
同一 episode 已冻结 TriggerMatched entry 后，TriggerStateChanged(trigger_live=true) 可作为状态升级刷新 A、cursor、当前 N4 payload 和 current_active_source，并可成为后续 ActionExecuted 顶层 source_trigger_event_*；ActionExecuted 仍必须保留 action_entry_trigger_matched_ref=TriggerMatched，并且 final_market_proof 只能是 matching N3T_C1_CLOSED。TriggerStateChanged(trigger_live=true) 没有对应 TriggerMatched entry 时不得生成 ActionExecuted。
pending_market_data 的 trigger_live=false；matched 的 trigger_live=true；inactive 的 trigger_live=false。
TriggerCleared / TriggerLiveChanged 仅作为旧 run 证据或兼容项，新 runtime 清除统一用 TriggerStateChanged(trigger_live=false, current_status=inactive)。
N5 只负责动作确认事实和动作事件，不负责用户展示策略。
TriggerMatched 是 N5 唯一 episode_entry；TriggerPendingMarketData 和 TriggerStateChanged 不得独立创建动作确认 episode。TriggerStateChanged(trigger_live=true) 只允许刷新已有 episode 的 current_active_source，trigger_live=false 则终止该 episode。
同一 TriggerMatched 重放必须幂等；TriggerStateChanged(trigger_live=false) 终止当前 tracking episode 后，同 action grain 的新 event_id TriggerMatched 必须开启新 episode，并生成以该 source trigger event 为幂等边界的新 ActionEligible；该语义在同一 planner batch 或跨 invocation 到达时必须一致。
N5 canonical action_state 只能为 eligible / blocked / executed / skipped / expired。
N5 internal confirmation_status=pending/passed/failed/expired、tracking_until、last_checked_minute_label 不是 canonical action_state。
ActionExecuted 只表示 N5 动作确认事实成立并发出动作事件，不表示真实下单、sim、N6 展示、语音或交易意图。
expired 不新增 ActionExpired；用 ActionSkipped(action_state=expired, reason=trigger_live_false/window_expired) 表达。
N5 final action_mark 只能为 normal / 30m_volume / 30m_shrink，且只有 120m / 30m / 5m / 1m 确认全部通过后才能写 final action_mark。
BUY_HINT / SELL_HINT 在 N5 只能作为 condition_key / original_condition_key / trace；runtime signal_type 必须是 B_BUY / S_SELL，N5 不输出 HintEvent。
N5 新 canonical 输出事件只能是 ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped；ActionEvent / HintEvent / RiskEvent / PositionEvent 仅作为历史兼容项。
N6 才负责 alert-only、展示、通知、语音、mobile、sim 和交易意图呈现。
stock / index / board 必须作为三个独立通道处理，N4/N5 不得把 index/board 写死为 alert-only。
```

当前阶段仍然不做：

- 在条件层输出 POS_CLEAR / BUY_FAIL_CLEAR / ADD_BUY_FAIL_REDUCE 等用户层解释类型
- 未经用户明确确认的行情拉取 execute
- 未经用户明确确认的追加触发层 execute / worker / 长期服务
- 未经用户明确确认的追加动作层 execute / worker / 长期服务
- 未经用户明确确认的 N5 outbox consumption
- 未经用户明确确认的 N3-C2 execute、closed summary 写入或 MinuteBarClosed outbox
- 未经用户明确切换到对应 N1-N6 layer_role 的 runtime registry command execute
- runtime_control 会话内执行 nightly run、rollback SQL、outbox consumption 或任何 worker
- runtime_control 修改 LaunchAgent 或重启服务；唯一例外是当前请求明确授权并精确满足
  `n6_user_web_immutable_release_bounded_rebind_v1` 的单个 N6 Web Release rebind，
  或精确满足 `n6_strategy_center_schema_migration_maintenance_window_v1` 的
  单次 081 prepare-only quiesce window，或在 081 已提交后精确满足
  `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` 的单个 V2 Web Release
  rebind，或在 081/082/083/084 已提交且 evaluator 已由独立 N6 gate 完全
  quiesce 后精确满足 `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`，
  将 exact Web 从唯一冻结 legacy 短名 source 有界切换到正式 40 位 immutable
  Release；或独立 `runtime_control` 执行请求精确满足
  `n3_higher_period_amount_rollover_controlled_promotion_v1`，且只对冻结的 N3P
  label 做一次 idle/bootout/absence wait/ff-only promotion/original-plist
  bootstrap；或独立 `runtime_control` 执行请求精确满足
  `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`，且只对两个冻结
  N4 proof-discovery label 做一次 bootout/absence wait/ff-only promotion/
  original-plist bootstrap；或独立 `runtime_control` 执行请求精确满足
  `n4_lifecycle_inactive_mark_recovery_v1`，且每个请求仅执行 rollback restore、
  corrected promotion 或 corrected code-only rollback 三个阶段之一；
  或独立 `runtime_control` 执行请求精确满足
  `n4_lifecycle_inactive_projection_type_reset_v1`，且只对两个冻结 N4
  proof-discovery label 做一次 idle/bootout/ff-only promotion/original-plist
  bootstrap；或独立 `runtime_control` 执行请求精确满足
  `runtime_hot_cleanup_archive_gated_disk_governance_v1`，且每个请求只执行
  cleanup scheduler quiesce、archive-verified local reclaim、Time Machine
  snapshot fallback、archive-gated scheduler restore 四个阶段之一；
  或独立 `runtime_control` 安装请求精确满足
  `n1_local_artifact_archive_daily_bounded_install_v1`，且只安装 exact N1
  archive-only daily label，不运行归档、不操作 cleanup label；
  082/083 仅允许独立 `N6_user` 请求按
  `n6_strategy_center_post_081_v2_catalog_migration_window_v1` 严格分两次执行
- N6 execute；仅可在独立 `N6_user` 会话中精确满足
  `n6_strategy_center_display_only_bounded_run_once_v1` 或
  `n6_strategy_center_display_only_scheduled_evaluator_v1`；另仅允许在 post-081
  维护窗口中精确满足 `n6_strategy_center_post_081_v2_catalog_migration_window_v1`
  的单阶段 082 或 083 schema/catalog migration；083 已提交后另仅允许独立
  `N6_user` 请求精确满足
  `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`，在 strategy
  write=0、evaluator quiesced 下创建一个单用户 pending V2 revision
  ；后续剩余用户只能按
  `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`
  每个请求/事务迁移一个 scope；全部活动 scope 已为 V2 且 pending=0 后，
  才可按 `n6_strategy_center_v1_retirement_after_all_users_v2_v1`
  单独退休 V1 catalog
- 语音播报
- mobile projection
- 模拟账户
- 前端页面
- 真实交易
- 长期 worker 启动；唯一调度例外是独立 `N6_user` 请求完整满足
  `n6_strategy_center_display_only_scheduled_evaluator_v1` 的 exact-label、5 秒
  run-once LaunchAgent，且其前置 bounded canary 必须已通过

## 2. 必读文档

开始任何任务前必须先读取：

- `AGENTS.md`
- `docs/V3_RAW_DATA_INGESTION_DESIGN.md`
- `docs/V3_EXISTING_RAW_TO_INGESTION_MAPPING.md`
- `docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md`
- `docs/Architecture.md`
- `docs/Roadmap.md`
- `docs/Tasks.md`

如果任务涉及条件层，也必须读取：

- `docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md`
- `docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md`

如果任务涉及 N3 实时行情层，也必须读取：

- `docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md`
- `docs/N2_FINAL_CONDITION_LAYER_CLOSURE.md`
- `docs/N2_F_SCOPE_CONSUMPTION_CONTRACT.md`

如果任务涉及 N4 触发层，也必须读取：

- `docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md`
- `docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md`
- `docs/N2_F_SCOPE_CONSUMPTION_CONTRACT.md`

如果任务涉及 N5 动作层，也必须读取：

- `docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md`
- `docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md`
- `docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md`

如果任务涉及项目规则更新，也必须同步更新：

- `AGENTS.md`
- 相关 `docs/*.md`

如果任务涉及 runtime orchestration / dashboard，也必须读取：

- `docs/RUNTIME_PIPELINE_CONTROL_V0.md`
- `docs/RUNTIME_NIGHTLY_SOP.md`

## 3. 与旧系统边界

v3 是新项目，不得默认触碰旧系统。

禁止默认读取、修改或写入：

- `/Users/chuanfuchen/stock_monitor_isolated`
- `/Users/chenchuanfu/stock_monitor_isolated`
- 任何旧系统 `monitor.db`
- 旧系统 LaunchAgent
- 旧系统 8866 / 8868 / 8869 / 8871 服务
- 旧系统 action / tts / sim / position 表

如确需只读参考旧系统，必须先说明目的、范围和命令，并获得用户确认。

## 3.1 分层会话边界硬规则

v3 必须按分层会话推进。每个会话在执行前必须确认本次 `layer_role`。如果用户没有明确指定，Codex 可以根据任务内容推断；无法确定时必须停下询问，不能跨层执行。

允许的 `layer_role` 只有：

```text
runtime_control
N1_ingestion
N2_condition
N3_market_data
N4_trigger
N5_action
N6_user
```

通用边界：

- 本层可以修改本层代码、schema 草案、脚本、测试、文档和本层数据。
- 本层只能只读上游正式产物，不得为了绕过问题去修改上游。
- 本层不得执行下游任务，不得顺手启动下一层。
- 一个会话不得连续推进多个层；完成本层任务后必须停下，等待用户明确切换层级。
- 发现问题属于其他层时，必须停止当前执行，输出 `blocked_by_layer=<layer_role>`、证据、建议交接提示词。
- 只有用户明确说“切换到 runtime_control/N1/N2/N3/N4/N5/N6”或给出等价确认后，才允许改变 `layer_role`。

分层权限如下。

| layer_role | 允许写入/执行 | 允许只读 | 禁止事项 |
|---|---|---|---|
| `runtime_control` | runtime pipeline run/stage/command registry/rollback registry/timeline/dashboard 的文档、schema 草案、测试、只读 dashboard 输出；用户当前请求明确授权时，可修改控制面 Kernel/Compiler 合同及其静态测试，但不得在同一会话使用新增例外执行 N1-N6；精确满足 `n6_user_web_immutable_release_bounded_rebind_v1` 时，可对单个 `com.ashare-v3.n6.user-web` 执行一次 immutable Release rebind 和失败时的一次原 Release 恢复；精确满足 `n6_strategy_center_schema_migration_maintenance_window_v1` 时，可关闭 Strategy Center selection 写入口、有界重启该 Web、仅 quiesce exact evaluator，并写一个只读水位绑定的 immutable maintenance token；081 已提交后精确满足 `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` 时，可保持 strategy write=0、evaluator quiesced、virtual executor 不被操作，仅对该 Web 执行一次 V2 immutable Release rebind；post-083 且 strategy write=1 时精确满足 `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`，可仅 bootout exact evaluator 一次并状态驱动等待 PID/job absence；081/082/083/084 已提交且 evaluator 由该独立 gate quiesce 后，精确满足 `n6_strategy_center_post_083_v2_web_bounded_rebind_v1` 时，可保持 strategy write=1、virtual executor 原 5 秒调度不被操作，仅将 exact Web 从唯一冻结 legacy 短名 rollback source 有界切换到一个正式 40 位 immutable Release | N1-N6 合同、报告、rollback SQL 路径、run_id lineage、quality gate 摘要 | 执行 registry command、执行 nightly run、执行 rollback SQL、连接数据库写 runtime 表、消费 outbox、启动业务 worker、写 N1-N6 事实；除命名策略外修改 LaunchAgent 或重启服务 |
| `N1_ingestion` | raw ingest、source_version、quality gate、active source_version、PostgreSQL/Parquet fact、N3 sealed runtime 的归档执行、入库回滚与入库文档 | N2 readiness 缺口报告、N3 archive_request / sealed runtime 分区 | 运行 condition_basis/condition_pool execute、写 `condition_*`、盘中拉分钟 K、触发/动作/用户层、worker |
| `N2_condition` | `condition_basis`、`condition_pool`、`minute_target_scope`、`condition_display_basis`、条件层质量项、条件层回滚 SQL、条件层文档 | N1 active source_version、N1 ready check、入库 fact | 外拉 Tushare/mootdx/实时行情、修 N1 fact、写 ingest 表、拉 1 分钟 K、进入 N3/N4/N5/N6 |
| `N3_market_data` | market_data_subscription、market_data_pull_plan、`previous_day_minute_bar_1m`、今日分钟 K、实时日 K/快照、行情质量项、N3 标准行情事件、低频行情展示事件、盘后封账与 archive_request 元数据 | N2 active condition run 和 `minute_target_scope` | 改条件层、重新计算条件、写 trigger/action/user、写用户卡片、播放语音、直接写 Parquet 归档或外接盘、启动交易 worker |
| `N4_trigger` | trigger event/state、trigger quality item、trigger dry-run/execute 合同 | N2 condition_pool、N3 行情快照/分钟 K | 拉行情、改条件、写 action、写 mobile/voice/sim |
| `N5_action` | action event、hint/risk/action 归一化事件、position event、动作质量项 | N4 trigger、N3 分钟 K、必要的 N2 条件摘要 | 改 N1/N2/N3/N4、写用户投影、播放语音、写真实交易 |
| `N6_user` | user projection、voice policy、mobile/card projection、sim shadow、用户偏好表；精确满足 `n6_strategy_center_display_only_bounded_run_once_v1` 时，可执行单 principal/user/revision/current reviewed-N6 trade-date 的策略中心 display-only bounded run-once；在当前日 canary PASS 且精确满足 `n6_strategy_center_display_only_scheduled_evaluator_v1` 时，可安装/启用唯一 exact-label、StartInterval=5、每 tick 单 scope 的 immutable-Release run-once 调度器；在 081 已提交、Web strategy write=0、evaluator quiesced 的维护窗口中，精确满足 `n6_strategy_center_post_081_v2_catalog_migration_window_v1` 时，可先单独执行一次 082，完成 postflight 后再由另一个独立请求单独执行一次 083；083 已提交后可按首用户及 remaining-user 命名 policy 每次创建一个 pending V2 revision；全部活动 scope 已为 V2 且 pending=0 后，可按命名 V1 retirement policy 单独退休 V1 catalog | N2 条件摘要、N5 输出事件 | 回写 N1-N5、直接改 trigger/action 事实、启动真实交易 |

上表 `runtime_control` 行的 LaunchAgent 禁止项另有一个磁盘治理命名例外：独立
请求完整满足 `runtime_hot_cleanup_archive_gated_disk_governance_v1` 时，只可对
exact cleanup label 执行该请求选择的单一阶段；不得借此操作任何业务服务或跨层
归档/数据库事实。

另有一个仅用于安装 N1 archive-only 日调度器的命名例外：独立
`runtime_control` 请求完整满足 `n1_local_artifact_archive_daily_bounded_install_v1`
时，只可安装和 bootstrap exact label
`com.ashare-v3.n1.local-artifact-archive-daily` 一次。该安装 gate 不执行归档，
不得操作 cleanup label；归档的自然运行及其 archive 写入仍属于 `N1_ingestion`。

trigger / action 写入硬规则：

```text
默认禁止跨层写 trigger/action。
只有本次会话已明确 layer_role=N4_trigger 或 layer_role=N5_action，
且用户明确授权 run-once，
且已有对应 preflight / contract / rollback，
才允许写入本层 trigger/action 事实或事件。
仍然禁止长期 worker、真实交易、N6 用户层写入、语音、mobile projection、sim。
N4 synthetic outbox 默认只允许用于 N5 dry-run / preflight / contract validation；
不得作为正式 N5 action fact / N5 outbox 写入来源，除非用户另行明确授权 shadow-only run，并提供独立标识、preflight 和 rollback。
```

runtime_control 写入硬规则：

```text
runtime_control 是总控控制面，不是 N1-N6 业务层。

`windows_rebuild_w0_bounded_v1` 是 Windows rebuild v2 的一次性、fail-closed
W0 主机治理例外。定义或修改该 policy 的治理会话不得使用它；只有后续独立、
明确授权的 `runtime_control` 请求可以选择一个 phase 执行一次。W0 完整 PASS
之前不得进入 `N1_ingestion`；Windows N1 必须从全新空 cluster 开始，Mac dump、
记录、source_version 和 evidence 的导入次数必须全部为 0。

<!-- policy:windows_rebuild_w0_bounded_v1:begin -->
```json
{
  "policy_id": "windows_rebuild_w0_bounded_v1",
  "policy_version": 7,
  "policy_state": "POLICY_READY_NOT_EXECUTED",
  "layer_role": "runtime_control",
  "scope_mode": "windows_w0_bounded_once",
  "default_runtime_execution_decision": "REJECT",
  "accept_decision": "ACCEPT",
  "governance_session_cannot_execute": true,
  "execution_session_must_be_independent": true,
  "explicit_current_request_authorization_required": true,
  "baseline": {
    "branch": "codex/windows-rebuild-v1",
    "commit": "027b03d3ca16c554491b7a21bc840acaec869571",
    "tree": "cdba2aafb8b1b87c6dc33b4af301398f8e42491d"
  },
  "phase_contract": {
    "allowed_phase_modes": [
      "w0_prepare_and_mutate",
      "w0_postgresql_virtual_identity_1639_recovery",
      "w0_postgresql_virtual_identity_22_recovery",
      "wsl_shutdown_native_control"
    ],
    "attempts_per_phase": 1,
    "automatic_retry_attempts": 0,
    "phase_combination_allowed": false,
    "phase_order": [
      "w0_prepare_and_mutate",
      "w0_postgresql_virtual_identity_1639_recovery",
      "w0_postgresql_virtual_identity_22_recovery",
      "wsl_shutdown_native_control"
    ],
    "shutdown_phase_requires_prior_result": "RESTART_REQUIRED",
    "shutdown_phase_requires_frozen_pre_shutdown_evidence": true
  },
  "exact_allowlist": {
    "scheduler_operations": [
      "export_exact_definition",
      "disable_exact_task"
    ],
    "scheduler_match_authority": [
      "TaskName",
      "TaskPath",
      "Actions"
    ],
    "scheduler_match_expression": "(?i)AshareV3|Ashare[-_ ]?V3",
    "scheduler_inventory_contract": {
      "dynamic_preflight_exact_inventory_required": true,
      "membership_authority": "current_TaskName_or_TaskPath_belongs_to_AshareV3",
      "fixed_task_count_as_execution_authority_forbidden": true,
      "historical_inventory_count_is_quality_evidence_only": true,
      "before_inventory_count_and_prior_evidence_delta_required": true,
      "export_every_frozen_definition_before_disable": true,
      "after_every_frozen_task_must_be_disabled": true
    },
    "legacy_service_name": "postgresql-x64-18",
    "legacy_service_operations": [
      "stop_once_if_running",
      "set_startup_disabled_once"
    ],
    "software_products": [
      "Git for Windows",
      "PostgreSQL 16 x64",
      "CPython 3.11 x64"
    ],
    "software_package_ids": [
      "Git.Git",
      "PostgreSQL.PostgreSQL.16",
      "Python.Python.3.11"
    ],
    "installer_version_hash_signature_must_be_frozen_before_install": true,
    "postgresql_minimum_version": "16.14",
    "postgresql_installer_package_id": "PostgreSQL.PostgreSQL.16",
    "postgresql_installer_version": "16.15-1",
    "postgresql_installer_filename": "postgresql-16.15-1-windows-x64-download-v1.exe",
    "postgresql_installer_path": "C:\\AshareV3\\staging\\installers\\postgresql-16.15-1-windows-x64-download-v1.exe",
    "postgresql_installer_url": "https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64.exe",
    "postgresql_installer_sha256": "DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2",
    "postgresql_installer_authenticode_status": "Valid",
    "postgresql_installer_signer": "EnterpriseDB Corporation",
    "postgresql_install_root": "D:\\PostgreSQL\\16",
    "postgresql_data_directory": "D:\\PostgreSQL\\16\\data",
    "postgresql_backup_staging": "D:\\PostgreSQL\\backup-staging",
    "postgresql_listen_addresses": "127.0.0.1",
    "postgresql_port": 5432,
    "postgresql_service_name": "postgresql-x64-16",
    "postgresql_transient_installer_identity": "NT AUTHORITY\\NetworkService",
    "postgresql_service_account": "NT SERVICE\\postgresql-x64-16",
    "c_directories": [
      "C:\\AshareV3\\app",
      "C:\\AshareV3\\config",
      "C:\\AshareV3\\runtime",
      "C:\\AshareV3\\logs",
      "C:\\AshareV3\\seed-inbox",
      "C:\\AshareV3\\evidence",
      "C:\\AshareV3\\staging"
    ],
    "wsl_visible_drive_after_restart": "C",
    "wsl_hidden_drive_after_restart": "D",
    "read_only_capability_checks": [
      "native_cpython_3_11_x64",
      "TdxW_process_present",
      "127.0.0.1:17709_listening"
    ]
  },
  "python311_contract": {
    "read_only_preflight_states": [
      "valid_native_3_11_x64",
      "missing_native_3_11",
      "damaged_native_3_11"
    ],
    "install_or_repair_allowed_only_for_states": [
      "missing_native_3_11",
      "damaged_native_3_11"
    ],
    "package_id": "Python.Python.3.11",
    "install_or_repair_attempts": 1,
    "automatic_retry_attempts": 0,
    "scope": "machine_wide_x64",
    "install_root": "C:\\Program Files\\Python311",
    "python_executable": "C:\\Program Files\\Python311\\python.exe",
    "version_constraint": "3.11.x",
    "secure_patch_selection": "highest_current_official_winget_3_11_x_at_preflight",
    "resolved_version_publisher_signer_sha256_frozen_before_install": true,
    "official_source_only": true,
    "verify_pe_x64": true,
    "verify_pip_available": true,
    "verify_venv_module_available": true,
    "microsoft_store_alias_forbidden": true,
    "python_3_12_or_3_14_substitution_forbidden": true,
    "source_build_forbidden": true,
    "third_party_distribution_forbidden": true,
    "business_venv_create_attempts": 0,
    "project_package_install_attempts": 0
  },
  "postgresql16_installer_contract": {
    "publisher_supported_defaults_required": true,
    "installation_mode": "interactive_gui_from_exact_staged_installer",
    "winget_unattended_execution_forbidden": true,
    "service_name": "postgresql-x64-16",
    "transient_installer_identity": "NT AUTHORITY\\NetworkService",
    "transient_identity_allowed_only_during_gui_install_and_empty_cluster_bootstrap": true,
    "final_service_account": "NT SERVICE\\postgresql-x64-16",
    "local_account_create_attempts": 0,
    "service_identity_transition_attempts": 1,
    "service_must_be_stopped_before_identity_or_acl_transition": true,
    "service_sid_type": "UNRESTRICTED",
    "scm_virtual_account_password": "none",
    "networkservice_acl_count_final": 0,
    "final_gate_requires_service_name_startname_sid_acl_loopback_empty_business_and_zero_imports": true,
    "networkservice_final_identity_forbidden": true,
    "service_logon_only": true,
    "interactive_local_rdp_network_batch_logon_forbidden": true,
    "account_group_membership_change_forbidden": true,
    "gui_secret_entry_required": true,
    "unattended_install_with_secret_forbidden": true,
    "gui_password_scope": "postgresql_database_superuser_only",
    "secret_forbidden_locations": [
      "command_line",
      "process_argv",
      "environment",
      "response_file",
      "shell_history",
      "transcript",
      "log",
      "evidence",
      "screenshot"
    ],
    "secret_value_or_hash_recording_forbidden": true,
    "evidence_records_only_redacted_gui_entry_and_redaction_audit": true,
    "automatic_retry_attempts": 0,
    "failed_install_preserved_as_evidence": true
  },
  "postgresql_virtual_identity_1639_recovery": {
    "prior_policy_commit": "3160c7bee824a5cadcd7f63c78235a8b5c24c038",
    "prior_policy_tree": "08959a4190ca4d2dafe67cf7062625541657f171",
    "prior_failed_program": "sc.exe config",
    "prior_exit_code": 1639,
    "prior_startname_unchanged": "NT AUTHORITY\\NetworkService",
    "phase_mode": "w0_postgresql_virtual_identity_1639_recovery",
    "attempts": 1,
    "required_pre_state": {
      "service_state": "Stopped",
      "start_name": "NT AUTHORITY\\NetworkService",
      "service_sid_type": "UNRESTRICTED",
      "virtual_account_acl_present": true,
      "networkservice_acl_count_full_tree": 0,
      "listen_addresses": "127.0.0.1",
      "port": 5432,
      "listener_5432_present": false
    },
    "only_mutation_method": "Invoke-CimMethod Win32_Service.Change",
    "change_arguments": {
      "StartName": "NT SERVICE\\postgresql-x64-16",
      "StartPassword": "empty_string"
    },
    "required_return_value": 0,
    "configuration_acl_install_mutation_attempts": 0,
    "service_start_attempts_after_verified_change": 1,
    "required_post_state": {
      "service_state": "Running",
      "start_name": "NT SERVICE\\postgresql-x64-16",
      "service_sid_type": "UNRESTRICTED",
      "listen_endpoint": "127.0.0.1:5432",
      "pg_isready": "accepting",
      "networkservice_acl_count_full_tree": 0
    },
    "failure_service_state": "Stopped",
    "automatic_retry_attempts": 0,
    "networkservice_restore_attempts": 0,
    "n1_handoff_allowed": false
  },
  "postgresql_virtual_identity_22_recovery": {
    "policy_id": "w0_postgresql_virtual_identity_22_recovery_v1",
    "prior_policy_commit": "0a64eb665433483a69e9134c222a1dabc03c1da2",
    "prior_policy_tree": "0f97f27c5a43d976e73f025e20d6b355f6ece494",
    "prior_phase": "w0_postgresql_virtual_identity_1639_recovery",
    "prior_mutation_method": "Invoke-CimMethod Win32_Service.Change",
    "prior_change_start_name": "NT SERVICE\\postgresql-x64-16",
    "prior_change_start_password": "empty_string",
    "prior_return_value": 22,
    "prior_service_start_attempts": 0,
    "prior_identity_change_proven": false,
    "phase_mode": "w0_postgresql_virtual_identity_22_recovery",
    "attempts": 1,
    "required_fresh_read_only_pre_state": {
      "service_state": "Stopped",
      "start_name": "NT AUTHORITY\\NetworkService",
      "service_sid_type": "UNRESTRICTED",
      "listener_5432_present": false
    },
    "only_mutation_program": "sc.exe",
    "exact_argument_vector": [
      "config",
      "postgresql-x64-16",
      "obj=",
      "NT SERVICE\\postgresql-x64-16"
    ],
    "password_argument": "OMITTED",
    "changeserviceconfig_lpPassword": "NULL",
    "required_exit_code": 0,
    "read_only_startname_check_before_start": true,
    "service_start_attempts_after_verified_change": 1,
    "required_post_state": {
      "service_state": "Running",
      "start_name": "NT SERVICE\\postgresql-x64-16",
      "service_sid_type": "UNRESTRICTED",
      "listen_endpoint": "127.0.0.1:5432",
      "pg_isready": "accepting",
      "networkservice_acl_count_full_tree": 0
    },
    "configuration_acl_install_or_logon_right_mutation_attempts": 0,
    "v6_rerun_attempts": 0,
    "automatic_retry_attempts": 0,
    "networkservice_restore_attempts": 0,
    "failure_service_state": "Stopped",
    "n1_handoff_allowed": false
  },
  "empty_cluster_contract": {
    "initdb_new_empty_cluster_only": true,
    "mac_dump_import_attempts": 0,
    "mac_record_import_attempts": 0,
    "mac_source_version_import_attempts": 0,
    "mac_evidence_import_attempts": 0,
    "ashare_v3_business_database_create_attempts": 0,
    "business_schema_create_or_migrate_attempts": 0,
    "n1_n6_data_write_attempts": 0
  },
  "identity_acl_contract": {
    "routine_codex_native_identity": {
      "account": "TDX-STOCK\\ashare-ops",
      "sid": "S-1-5-21-2072264739-3883739137-88032818-1006",
      "integrity": "Medium",
      "administrators_member": false,
      "required_group_memberships": [
        "Users",
        "Authenticated Users"
      ],
      "native_ssh_login_required": true
    },
    "elevated_operator_identity": {
      "account": "TDX-STOCK\\47894",
      "sid": "S-1-5-21-2072264739-3883739137-88032818-1002",
      "administrators_member": true,
      "allowed_phase_modes": [
        "w0_prepare_and_mutate",
        "w0_postgresql_virtual_identity_1639_recovery",
        "w0_postgresql_virtual_identity_22_recovery"
      ],
      "allowed_admin_operations": [
        "exact_frozen_installer_once",
        "disable_dynamically_frozen_scheduler_inventory",
        "stop_and_disable_postgresql_x64_18",
        "create_exact_d_postgresql_directories",
      "apply_exact_c_and_d_acl",
      "create_or_configure_exact_postgresql_16_service",
      "restrict_exact_postgres_service_account_logon",
      "stage_exact_wsl_configuration",
      "invoke_exact_postgresql_1639_cim_change_and_verified_start",
      "invoke_exact_postgresql_22_sc_config_null_password_and_verified_start"
      ]
    },
    "routine_and_elevated_identities_must_be_distinct": true,
    "elevated_operator_is_not_routine_codex_or_application": true,
    "operator_d_access_must_not_be_used_as_routine_acl_failure": true,
    "unknown_sid_rejected": true,
    "account_create_password_group_or_privilege_change_forbidden": true,
    "postgresql_identity_non_interactive": true,
    "postgresql_identity_access_scope": [
      "D:\\PostgreSQL\\16",
      "D:\\PostgreSQL\\backup-staging"
    ],
    "application_identity_must_be_non_admin": true,
    "codex_identity_must_be_non_admin": true,
    "operator_identity_must_be_distinct_from_application_and_codex": true,
    "application_and_codex_denied_rights": [
      "read",
      "list",
      "write",
      "create",
      "delete",
      "change_permissions",
      "take_ownership"
    ],
    "routine_d_denial_scope": "D:\\PostgreSQL\\16",
    "routine_normal_access_channels": [
      "loopback_database_connection",
      "C_drive_application_paths"
    ],
    "fail_if_identity_or_effective_access_is_unproven": true
  },
  "wsl_isolation_contract": {
    "after_restart_automount_d": false,
    "after_restart_mnt_d_exists": false,
    "after_restart_only_explicit_drive": "C",
    "wsl_conf_interop_enabled": false,
    "wsl_conf_append_windows_path": false,
    "linux_identity": "ashare-codex",
    "linux_identity_must_access_mnt_c_code": true,
    "native_operations_channel": "TDX-STOCK\\ashare-ops SSH",
    "uac_install_channel": "TDX-STOCK\\47894 independent native channel",
    "current_wsl_native_interop_operator_inheritance_forbidden": true
  },
  "required_pre_evidence": [
    "native_and_wsl_identity",
    "routine_and_elevated_account_sid_integrity_group_and_channel_evidence",
    "windows_build_and_architecture",
    "c_and_d_directory_inventory_without_recursive_delete",
    "c_and_d_owner_acl_sddl_and_effective_access",
    "dynamic_current_exact_asharev3_scheduler_inventory_definitions_and_states",
    "scheduler_current_count_and_prior_evidence_count_delta_as_quality_evidence",
    "legacy_postgresql_18_service_config_state_and_binary_data_paths",
    "installed_git_python_postgresql_versions_and_paths",
    "native_python311_registry_launcher_alias_executable_pe_version_pip_venv_state",
    "installer_package_ids_versions_sha256_and_signatures",
    "postgresql_16_15_1_exact_hash_authenticode_signer_and_official_authority",
    "local_postgres_account_presence_sid_groups_and_logon_rights",
    "postgresql_gui_secret_redaction_plan",
    "TdxW_process_and_127_0_0_1_17709_owner",
    "wsl_mounts_and_wsl_conf",
    "process_and_service_inventory",
    "baseline_commit_tree_and_policy_hash"
  ],
  "required_post_evidence": [
    "all_dynamically_frozen_exact_asharev3_scheduler_definitions_preserved_and_disabled",
    "scheduler_before_inventory_delta_quality_evidence",
    "legacy_postgresql_18_service_stopped_and_disabled_with_files_untouched",
    "git_for_windows_version",
    "native_python311_executable_pe_x64_version_3_11_x_pip_and_venv",
    "postgresql_16_version_at_least_16_14",
    "postgresql_16_install_and_data_paths_on_d",
    "postgresql_x64_16_service_runs_as_exact_local_postgres_account",
    "postgres_service_account_service_logon_only_and_exact_d_acl",
    "postgres_secret_absent_from_command_line_environment_logs_evidence_and_screenshots",
    "new_cluster_identity_and_zero_business_objects",
    "listen_addresses_exactly_127_0_0_1",
    "postgresql_port_exactly_5432",
    "c_and_d_owner_acl_sddl_and_effective_access",
    "application_and_codex_d_access_denials",
    "TdxW_process_and_127_0_0_1_17709_owner",
    "mac_import_attempt_counts_all_zero",
    "n1_n6_nas_and_business_write_attempt_counts_all_zero",
    "wsl_c_visible_and_d_absent_after_native_restart",
    "wsl_interop_disabled_append_windows_path_false_and_mnt_d_absent",
    "routine_ashare_ops_medium_non_admin_ssh_and_d_denials",
    "phase_attempt_counts_and_final_verdict"
  ],
  "required_zero_attempts": [
    "scheduler_delete_attempts",
    "scheduler_enable_attempts",
    "legacy_postgresql_18_uninstall_attempts",
    "legacy_postgresql_18_program_delete_attempts",
    "legacy_postgresql_18_data_delete_attempts",
    "recursive_delete_attempts",
    "overwrite_existing_path_attempts",
    "git_reset_hard_attempts",
    "git_clean_attempts",
    "tushare_install_import_call_attempts",
    "mootdx_install_import_call_attempts",
    "mac_worktree_write_attempts",
    "mac_data_import_attempts",
    "n1_n6_runtime_attempts",
    "nas_operation_attempts",
    "business_database_write_attempts",
    "wsl_shutdown_attempts_in_prepare_phase",
    "python311_install_or_repair_attempts_without_missing_or_damaged_preflight",
    "python311_second_install_or_repair_attempts",
    "python311_microsoft_store_alias_attempts",
    "python311_3_12_or_3_14_substitution_attempts",
    "python311_source_build_attempts",
    "python311_third_party_distribution_attempts",
    "business_venv_create_attempts",
    "project_package_install_attempts",
    "non_postgresql_identity_account_create_attempts",
    "postgres_local_account_create_attempts",
    "postgres_service_identity_second_transition_attempts",
    "postgres_service_start_before_final_identity_acl_attempts",
    "postgres_secret_command_line_or_process_argv_attempts",
    "postgres_secret_environment_or_response_file_attempts",
    "postgres_secret_log_history_transcript_evidence_or_screenshot_attempts",
    "postgres_interactive_logon_enable_attempts",
    "identity_password_change_attempts_outside_single_edb_gui_creation",
    "identity_group_membership_change_attempts",
    "identity_privilege_change_attempts",
    "elevated_operator_outside_prepare_attempts",
    "current_wsl_native_interop_attempts",
    "postgresql_1639_recovery_second_attempts",
    "postgresql_1639_recovery_sc_exe_attempts",
    "postgresql_1639_recovery_acl_or_config_attempts",
    "postgresql_1639_recovery_networkservice_restore_attempts",
    "postgresql_22_recovery_second_attempts",
    "postgresql_22_recovery_v6_rerun_attempts",
    "postgresql_22_recovery_cim_attempts",
    "postgresql_22_recovery_password_argument_attempts",
    "postgresql_22_recovery_acl_config_install_or_logon_right_attempts",
    "postgresql_22_recovery_networkservice_restore_attempts"
  ],
  "forbidden": [
    "Tushare",
    "Mootdx",
    "Mac dump restore",
    "Mac records or source_version import",
    "Mac evidence reuse",
    "N1-N6 runtime",
    "NAS operations",
    "Task Scheduler enable or creation",
    "fixed historical Scheduler task count as execution authority",
    "Microsoft Store Python alias",
    "Python 3.12 or 3.14 substitution",
    "Python source build or third-party distribution",
    "W0 business venv or project package install",
    "new Windows local account or account password/group/privilege mutation",
    "PostgreSQL secret in command line, argv, environment, response file, history, transcript, log, evidence or screenshot",
    "NT AUTHORITY\\NetworkService after bounded installer bootstrap",
    "final PostgreSQL 16 identity other than NT SERVICE\\postgresql-x64-16",
    "unknown or swapped routine/elevated SID",
    "routine identity in Administrators",
    "WSL interop enabled or appendWindowsPath true after restart",
    "business schema or business data",
    "recursive delete",
    "overwrite existing paths",
    "git reset --hard",
    "git clean"
  ],
  "rollback_and_recovery": {
    "automatic_rollback": false,
    "automatic_cleanup": false,
    "scheduler_tasks_must_never_be_deleted": true,
    "disabled_scheduler_tasks_remain_disabled_on_failure": true,
    "legacy_postgresql_18_files_and_data_remain_untouched": true,
    "new_postgresql_16_files_and_failed_cluster_are_preserved_as_evidence": true,
    "failed_python311_install_or_repair_is_preserved_as_evidence": true,
    "unknown_existing_python_must_not_be_uninstalled": true,
    "failed_python311_directory_must_not_be_automatically_cleaned": true,
    "no_existing_path_may_be_replaced": true,
    "restore_or_recovery_requires_new_independent_authorization": true,
    "failure_result": "BLOCKED_EVIDENCE_PRESERVED"
  },
  "n1_handoff": {
    "requires_w0_pass": true,
    "next_layer_role": "N1_ingestion",
    "allowed_sources": [
      "TQ",
      "eltdx_finance",
      "self_built_trade_calendar"
    ],
    "forbidden_sources": [
      "Tushare",
      "Mootdx",
      "Mac_dump",
      "Mac_records",
      "Mac_source_version",
      "Mac_evidence"
    ],
    "nas_deferred_until_after_n1": true
  }
}
```
<!-- policy:windows_rebuild_w0_bounded_v1:end -->

该 policy 的 `w0_prepare_and_mutate` phase 在写入 `/etc/wsl.conf` 并封存全部
pre-shutdown evidence 后必须输出 `RESTART_REQUIRED` 并停止；它对
`wsl --shutdown` 的 attempt 必须为 0。只有另一独立、明确授权且从原生 Windows
控制的 `wsl_shutdown_native_control` phase 才可执行一次 shutdown，并在重新连接后
证明 WSL 仅显式挂载 C、D 不可见。任何 identity/ACL effective-access 证明不完整、
已有目标路径冲突、版本不足、非空 cluster、Scheduler 漏项或 attempt 超界均必须
fail-closed，保留证据，不得自动 retry、cleanup 或 rollback。

Scheduler authority 必须来自当次只读 preflight：动态枚举当前所有 `TaskName` 或
`TaskPath` 属于 AshareV3 的任务，冻结 exact inventory，逐项导出后全部 Disable。
历史 10 个或现场 9 个等数量只能作为 quality evidence；数量漂移必须写入 before
差异，但任何固定数量都不得成为执行权威或遗漏当前成员。

同一 prepare phase 只有在只读 preflight 证明原生 CPython 3.11 x64 缺失或损坏时，
才可对 official winget `Python.Python.3.11` 执行一次 machine-wide install/repair，
精确 root 为 `C:\Program Files\Python311`。preflight 必须把当前最高可用安全
3.11.x 补丁版本、官方 publisher、signer 和 SHA-256 冻结后再安装；成功后必须证明
`python.exe` 存在、PE x64、版本为 3.11.x 且 pip/venv module 可用。Microsoft
Store alias、3.12/3.14 替代、源码构建、第三方分发、业务 venv 或项目包安装均为
`REJECT`。失败不得自动 retry、卸载未知旧 Python 或清理目录，只能保留证据。

W0 双身份固定为 routine `TDX-STOCK\ashare-ops`（SID
`S-1-5-21-2072264739-3883739137-88032818-1006`，Medium，非 Administrators）
和 elevated operator `TDX-STOCK\47894`（SID
`S-1-5-21-2072264739-3883739137-88032818-1002`，Administrators）。只有后者可在
独立 `w0_prepare_and_mutate` 任务中执行 policy 列出的管理员动作；它不是 routine
Codex/application，也不能用它的 D 访问能力判定 routine ACL 失败。不得创建本地
账号、改密码、改组或改变既有用户权限。routine 验收必须经 `ashare-ops` SSH，证明 Medium、
非管理员及对 `D:\PostgreSQL\16` 的全部拒绝；正常访问仅为 loopback DB 与 C 盘。

PostgreSQL 16 必须使用 EDB 官方 x64 16.15-1 安装器，服务名
`postgresql-x64-16`。GUI/空 cluster bootstrap 期间仅临时允许
`NT AUTHORITY\NetworkService`；最终服务账号必须为无密码、无需创建本地用户的
`NT SERVICE\postgresql-x64-16`。安装器 SHA-256 必须为
`DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2`，
Authenticode 必须为 `Valid` 且 signer 为 `EnterpriseDB Corporation`。安装结束后、
任何业务连接前必须停止服务，单次切换 SCM StartName，设置 service SID type
`UNRESTRICTED`，仅给虚拟账号 `D:\PostgreSQL\16` 与
`D:\PostgreSQL\backup-staging` 权限，并移除 NetworkService 在这些根的 ACE。
EDB GUI 密码只属于数据库 superuser，不是 Windows service-account 密码，必须只由
独立 elevated operator 在 GUI 密码控件中输入；不得进入命令行、process argv、环境、
response file、history、transcript、日志、evidence 或截图，且不得记录明文或 hash。
最终 gate 必须证明 StartName、service SID、ACL、空业务库及 loopback 全部闭合；
任一切换或启动失败必须 fail-closed，禁止重试、回退到 NetworkService 或卸载清理。

restart 后 WSL 必须仅显式挂载 C，`/mnt/d` 不存在，并在 `/etc/wsl.conf` 设置
`[interop] enabled=false`、`appendWindowsPath=false`。Linux `ashare-codex` 仍须能访问
`/mnt/c` 代码；native 运维只走 `ashare-ops` SSH，UAC 安装只走独立 `47894` 通道。
未知/对调/相同 SID、routine 成为管理员或不能以 Medium SSH 登录、interop 未关闭，
以及当前 WSL 借 native interop 继承 `47894` 均必须 `REJECT`。

新增 artifact-only 例外 `n6_immutable_release_install_bounded_v1` 仅允许在
用户明确授权的 runtime_control 请求中，将一个已完成 attestation 的 N6
immutable Release 从唯一 staging 目录原子安装为一个新的 0555 root 子目录。
当 Release root 初始为 0555 且无独立 privileged installer 时，只允许在冻结
owner/group/ACL/xattr 后执行一次 owner-write `0555 -> 0755`，并在成功或失败
路径中执行一次 `0755 -> 0555` 恢复；group/other write、第二次 mode 变更或
结束时 root 仍可写都必须 `REJECT`。
它不允许覆盖或删除既有 Release，不允许 LaunchAgent/service、数据库、
evaluator/executor、migration、业务或 N1-N6 写入；失败清理只能删除本次
创建的 staging/target 路径，否则必须 `REJECT`。

`n6_immutable_release_install_pre_rename_validator_recovery_v1` 是只适用于
`aa6d19c169df3837b3115d975587686cc726b87b` 一次冻结失败的 artifact-only
恢复例外。它必须绑定 SHA-256
`9594308305ff68a217d51f6071ded07e4c01892a3ed91227abea9f1586b2edf1`
的 BLOCKED install attestation，证明 failure type 精确为
`validation_tool_capability_missing`、atomic rename/fallback/retry/cleanup
attempts 均为 `0`、target 不存在且 Release root 已恢复 `0555`；同时必须绑定
exact source commit/tree/archive/manifest/filesystem/attestation hashes 和保留
staging-v1 的 path/device/inode/owner/mode/count/ACL/xattr 指纹。保留
staging-v1 永久 evidence-only，不得复用、修改、rename、删除或 cleanup。
后续唯一独立恢复请求必须先在 exact 新 artifact 目录生成并封存 macOS xattr
validator capability attestation 及 SHA sidecar，并冻结 attestation、
`/usr/bin/xattr` 和 validator protocol 的相互绑定；只有 capability PASS 后
才可创建唯一全新同父 staging-v2，重新 materialize 并完成
blob/path/mode/ACL/xattr value 全量验证。xattr path authority 固定为
`release-content-manifest.tsv` 的 6243 个 file path 加 45 个 derived
directory/root，共 6288 个 path；每个且仅一个 `com.apple.provenance`、raw value SHA-256
`29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487`
及 length-prefixed canonical fingerprint SHA-256
`92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee`；
全部匹配且 staging/target owner:group 均精确为 `501:20` 后，才可用同一
Release-root dirfd 和 direct-child basenames 执行一次
`renameatx_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH)`；
普通/覆盖 rename、flag 缺失、不支持或 fallback 均 `REJECT`。
capability 失败必须在 Release root chmod 或 staging-v2
创建前 fail-closed 停止；rename 前失败必须先把 staging-v2 已创建内容递归
封存为 `0444/0555` 并写 identity/metadata evidence，不得返回可写 staging；
rename 成功后的 postflight 失败则必须保留不可变 target 作为 evidence，不得
修改或删除。Release root 必须在 rename attempt 后立即恢复为 `0555`，早于
target postflight 或 attestation 写入。recovery validation/install attestation
及 SHA sidecar 只能写入 Kernel 冻结的 exact 新 artifact 目录；该 output
目录必须延后到 Release root 已恢复或确认保持 `0555` 且所选 recovery outcome
分支已完成封存/postflight 后，才可在 FINALIZE 创建；capability 失败分支也
必须在不 chmod root、不创建 staging-v2 的前提下写入并封存 recovery failure
artifacts 后再 STOP。路径预存、
覆盖、额外外部写入或未知请求字段全部 `REJECT`；任一目录/文件创建、写入或
final seal 失败，都必须在 STOP 前把已创建 output 递归封存为 `0444/0555`，
记录 partial identity/hash 并永久保留 evidence，不得返回可写残留。恢复只允许一次新的
Release root `0555 -> 0755 -> 0555` 窗口和一次 recovery attempt；第二次恢复、
policy fallback、自动 retry、旧 staging cleanup、LaunchAgent/service、数据库、
evaluator/executor、migration、业务、N1-N6 或交易操作全部 `REJECT`。定义本
policy 的治理会话不得使用它执行恢复。

`n6_immutable_release_install_preflight_git_violation_recovery_v1` 是只适用于
前述 validator recovery 在任何 mutation 前因误用只读 Git preflight 而
fail-closed 的一次性程序恢复合同。它必须绑定 prior policy、治理
commit/tree/patch、当时 `AGENTS.md` 原始字节 SHA、唯一 session JSONL 的冻结
turn 字节区间及 SHA、exact Git tool-call identity/参数/输出 SHA 和完整命令
时间线；摘要、转述或仍会追加的整份 JSONL 当前 hash 均不得替代原始区间证据。
历史证据必须证明仅出现一次 Git tool call，且只含 `rev-parse`、`diff`、
`show` 三个只读 subcommand；`apply_patch`、stage、commit、checkout、switch、
branch、push、工作树写入及 capability/recovery artifact、Release-root chmod、
staging-v2、target、cleanup/fallback/runtime/database/service mutation attempts
全部为 `0`。后续独立执行请求完全禁止 Git 和测试，治理权威只能由独立 review
冻结的当前 `AGENTS.md` 原始字节 SHA、Kernel policy block 原始字节 SHA、
session turn segment/prefix SHA 及直接文件系统证据验证。

该 policy 不得放宽或再次调用 prior policy。它仍须先生成并封存 SHA 绑定的
`/usr/bin/xattr` capability attestation；capability PASS 后才允许唯一 fresh
same-parent staging-v2、全量 blob/path/mode/owner/ACL/xattr raw-value 验证、
一次 Release-root `0555 -> 0755 -> 0555` owner-write 窗口及一次同-dirfd
`renameatx_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH)`。
preserved staging-v1 永久 evidence-only，不得复用、修改、rename、删除或
cleanup；fallback、自动 retry、第二次 procedural recovery、LaunchAgent/
rebind、DB、runtime、migration、evaluator/executor、N1-N6 与交易操作全部
`REJECT`。定义本 policy 的治理会话不得执行它。

`n3_higher_period_amount_rollover_controlled_promotion_v1` 是一次性 N3 高周期
成交额换期修复发布例外。它只把 source fix
`ce95072e553d7e0a96999e91b87c3a0f46067ac1` 和 source rollback
`d5e8183c0ec0be0085d0069e0bc18e3d2a424d21` 作为已验证内容证据，不得把它们
当作后续执行 commit。source fix 的 canonical full-index patch SHA-256 必须为
`e72e37670c31d736abbaf895e27aad6599bc6e021176fde28f7d9a3509fbf8d2`，source
rollback 的 canonical full-index patch SHA-256 必须为
`16fabe6c79d96ba928822400279db53840a1a274783cd4faad6014397818db41`。
本 policy 严格限定以下四个文件：
`src/ashare_v3/market/v3_realtime_virtual_metric_writer.py`、
`src/ashare_v3/market/v3_full_day_replay_plan.py`、
`tests/test_v3_realtime_virtual_metric_writer_runner.py`、
`tests/test_full_context_formal_action_confirmation_metric.py`。不得修改 N2、N4、
N5、schema、事件合同、HINT 链路、历史 target 或其他文件。

本 policy 提交后，必须由独立 `N3_market_data` 任务从该 policy commit 生成一个
四文件 final fix commit 和一个直接子级的四文件 code-only rollback commit；
final fix 的四个 blob 和 canonical patch 必须与 source fix 内容证据一致，
rollback 的四个文件必须逐一等于 policy commit，且 rollback 完整 tree 必须
精确等于 policy commit tree。后续独立 `runtime_control` 执行请求必须在任何
runtime 操作前冻结并验证 exact policy/final/rollback SHA、祖先链、patch、
四个文件 blob、Active tracked worktree/index clean、worker/child idle，以及
原 plist
`/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-proof-poller.n3p.plist`
的 SHA-256
`d850d39cf3814dd7255ebf7eeb7b643cc4377daec479b7a99fb786d07750b9fa`。

全部前置通过后，仅允许对
`com.ashare-v3.n3.intraday-proof-poller.n3p` bootout 一次，状态驱动等待
job/PID/child absence，仅执行一次 `git merge --ff-only <final-fix-commit>`，
重新核对原 plist SHA 后仅用该 plist bootstrap 一次。禁止操作 HINT、legacy
combined、N4、N5 或任何其他 LaunchAgent；kickstart、手工行情拉取或 execute、
retry、自动 rollback、push、checkout/rebase/cherry-pick、plist 改写、DB DML、
消息/队列、历史 target 重跑/补写/supersede 及其他层操作全部 `REJECT`。失败只
报告已冻结的 final rollback target，不得自动执行。定义本 policy 的治理会话
不得执行它。

`n4_lifecycle_deactivation_state_columns_controlled_promotion_v1` 是一次性
N4 lifecycle/state-column 发布例外。它只把 source endpoint
`6d1b7a24f2f6d6fa6ef5a4d675995c943703101e` 和 source rollback
`a1ff8b0e0dbda579dd2cece1c5b84a10879293bc` 作为已验证内容证据，不得
把它们当作后续执行 commit。它固定八个 N4 文件、combined/rollback
patch SHA-256、source endpoint 八个 blob、两个精确 label 及原 plist
path/SHA；这些范围不得动态放宽。本 policy 提交后，必须由独立
`N4_trigger` 准备任务从 policy commit 的新 HEAD 生成两段 final
promotion commit 和一个 tree-equal rollback；未生成的 final SHA 不得预写进
policy。

后续独立 `runtime_control` 执行 gate 必须在任何 bootout 前冻结并
验证 exact policy commit/final commit/rollback SHA：final 第一段的父提交
精确为 policy commit，final tip 是其直接子提交，roll back 是 final
tip 的直接子提交且其 tree 精确等于 policy commit tree。final
combined/rollback patch 和八个 blob 必须与冻结 source evidence 一致。
只有 Active tracked worktree/index clean、原 plist 无漂移、两个 worker
及 child idle 时，才允许对
`com.ashare-v3.n4.proof-discovery-poller` 和
`com.ashare-v3.n4.proof-discovery-poller.hint` 各 bootout 一次，状态驱动
等待 job/PID/child absence，仅执行一次 `git merge --ff-only <final-tip>`，
并仅用两份原 plist 各 bootstrap 一次。kickstart、手工 execute、retry、
push、checkout/rebase/cherry-pick、plist 改写、其他 LaunchAgent、自动 rollback、
N2/N3/N5/N6、DB DML、消息/队列、历史事件或交易操作全部 `REJECT`。
失败只报告已冻结的 final rollback target，不得自动执行。定义本 policy
的治理会话不得执行它。

`n4_lifecycle_inactive_mark_recovery_v1` 是只适用于 2026-08-04 首个自然
失活样本暴露 `trigger_mark_candidate=none` 约束失败的一次性恢复例外。它绑定
Active `49fd0a6576d3f3f04c28c0ce65da95d6472931d7`、稳定基线
`ae05d7f8c365d3d0ed807235ab124e0d4cdae28e`、冻结内容回滚
`cadbe91c1d400a803dd678710a2733ac0e0d9f92`、八个 N4 文件、两个精确
label 及原 plist path/SHA。冻结回滚只能作为内容证据，后续执行 commit 必须
在本 policy commit 之后由独立 `N4_trigger` 准备任务重新生成。

线性恢复链固定为 `policy -> rollback_restore -> fixed_lifecycle ->
typed_columns -> fixed_code_rollback`。`rollback_restore` 只恢复八个 N4 文件
到稳定内容；修复后的 inactive 当前值必须为 `trigger_mark_candidate=normal`，
原激活候选继续保存在 `previous_trigger_mark_candidate`，且
`projection_30m_flag=false`、`projection_30m_type=none`。不得修改数据库
约束、schema、事件结构或历史 09:34 target。

执行只能由三个彼此独立、逐次显式授权的 `runtime_control` 请求完成：先
`rollback_restore`，自然轮次恢复 `exit=0/P0=0` 后才可
`corrected_promotion`，严重失败时也只能由另一个请求执行
`corrected_code_only_rollback`。每一阶段只允许两个冻结 N4 label 各一次
bootout、状态驱动等待 job/PID/child absence、一次 `git merge --ff-only` 和
两份原 plist 各一次 bootstrap。禁止阶段合并、自动继续、自动回滚、retry、
kickstart、手工 execute、DB DML、消息/队列、历史 target、N2/N3/N5/N6 或
交易操作。定义本 policy 的治理会话不得执行它。

该 policy 的当前 revision 另精确绑定首次 `rollback_restore` 在任何 ref、
tree、index 或 tracked-file 变化前因 `.git/ORIG_HEAD.lock` 沙箱写权限失败的
证据。旧 `195ac3f3 -> 5bd53e75 -> 14786f73 -> 0f62f592` 链只作已验证内容
证据，不得执行或重试。必须先从本 revision policy commit 重新生成 patch SHA
完全相同的新四提交链；后续独立执行请求还必须在任何 bootout 前完成 Git
metadata 写权限授权与验证，禁止以非授权 `git merge` 作为能力探针。本 policy
revision 的定义会话同样不得执行 runtime。

`n4_lifecycle_inactive_projection_type_reset_v1` 是一次性 N4 inactive
projection type 最小修复发布例外。它绑定 Active 基线
`d237e0ba09e38eab1993e921943b0fcf66332899`，并严格限定以下三个文件：
`src/ashare_v3/trigger/provisional_trigger_lifecycle.py`、
`tests/test_provisional_trigger_lifecycle.py`、
`tests/test_provisional_projection_execute.py`。修复只能在合格
`matched -> inactive` 输出中设置
`projection_30m_type=none`；同时必须保持 `trigger_live=false`、
`current_status=inactive`、`trigger_mark_candidate=normal`、
`projection_30m_flag=false`、`n5_entry_allowed=false`，并保留
`previous_projection_30m_flag`、`previous_projection_30m_type` 和
`previous_trigger_mark_candidate`。不得修改 matcher、execute、schema、事件结构、
历史事件或 N2/N3/N5/N6。

本 policy 提交后，必须由独立 `N4_trigger` 任务从该 policy commit 生成一个
三文件修复 commit 和一个直接子级的三文件 code-only rollback commit；rollback
的三个文件必须逐一等于 policy commit。后续独立 `runtime_control` 执行请求必须
在任何 runtime 操作前冻结并验证 exact policy/fix/rollback SHA、祖先链、三个
文件 blob、Active target-path clean、index clean、worker/child idle，以及以下
两份原 plist：
`/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.plist`
的 SHA-256
`7c2f996985a5fb915f0dcd228c8cdd85e42cd79824af36eb0c2f8d6be13341c8`，以及
`/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.hint.plist`
的 SHA-256
`8b7a824c23639be8c39788b835da854746e94820de0f6aad23f9b58f75c081d7`。

全部前置通过后，仅允许对
`com.ashare-v3.n4.proof-discovery-poller` 和
`com.ashare-v3.n4.proof-discovery-poller.hint` 各 bootout 一次，状态驱动等待
job/PID/child absence，仅执行一次 `git merge --ff-only <fixed-code-commit>`，
再仅用两份原 plist 各 bootstrap 一次。若 Active HEAD 已前进，只允许其与三个
目标文件零交集且 fix commit 是当前 HEAD 的线性后继；否则必须停止并从新 HEAD
重建，不得 cherry-pick。kickstart、手工 execute、retry、自动 rollback、push、
DB DML、消息/队列、历史事件重跑/补写、其他 LaunchAgent 或 N2/N3/N5/N6 操作
全部 `REJECT`。定义本 policy 的治理会话不得执行它。

`n6_immutable_release_install_eacces_retry_v1` 是前述初始安装发生 rename
`EACCES` 时唯一的、单独授权的失败恢复例外：只在同一已 attest source 已有
一份完整、可证明的
`EACCES` rename 失败证据，且该失败没有 target、没有 attestation、并且
Release root 已恢复为 `0555` 时适用。它不得复用、修改或删除旧 staging；
只能创建一个新的同父 staging 和新 target。在验证新 staging 后，它只允许
将 *新 staging 顶层目录* 临时从 `0555` 改为 owner-only `0755`，执行一次
新的 atomic rename，并立即将 target root 固化为 `0555`。Release root 仍只
允许一次 `0555 -> 0755 -> 0555` 窗口。任何非 `EACCES` 失败、旧 staging
漂移、第二次 retry、现有 Release 改写，或服务、数据库、evaluator/executor、
migration、业务或 N1-N6 写入都必须 `REJECT`。

`n6_immutable_release_install_host_eacces_remediation_v1` 只处理已证明的
host-level rename `EACCES`：它绑定一份可重读、可哈希的 host trace（同一
Release root、`0555` staging、rename 到同父与 `/tmp` 都失败），同时要求
当前候选的 orphaned staging 未被改动且 target 仍不存在。它允许一个全新的
staging/target，且仅在内容验证后临时使新 staging 顶层 owner-writable 以完成
一次 rename。旧 staging、既有 Release 和所有 runtime/database/N1-N6 业务
对象均不可写；第二次 remediation 必须 `REJECT`。

`n6_immutable_release_privileged_atomic_install_v1` 仅在当前用户明确授权、
固定 SHA-256 的专用 helper 已完成签名 attestation 时，才允许独立执行会话调用
一次。helper 只能在固定 Release root 的 parent dirfd 内，用
`renameatx_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH)` 将一个
已验证 staging 变为一个不存在 target；不支持任一 flag 必须 fail-closed。不得
调用 shell、复制、删除、覆盖、修改 xattr/ACL/mode、连接数据库、操作服务或触碰
N1-N6 业务对象。本治理会话不得调用 helper。

`n6_immutable_release_privileged_materialize_and_install_v1` 仅适用于固定
`d85df6328bde223e912dabc3bd65e16df984aa45` archive/manifest 的独立 root-only
V2 helper。它在一次调用中只能创建一个
新的同父 staging、安全解包并按冻结 archive hash/entry 规则验证，然后用
`renameatx_np` 原子晋升为一个不存在 target。失败必须保留本次 staging，旧 staging
不可触碰；不得 shell、任意路径、覆盖/删除既有 Release、xattr/ACL、服务、数据库、
evaluator 或 N1-N6 业务操作。本治理会话不得使用新 policy 执行安装。

`n6_immutable_release_privileged_materialize_and_install_f67_v1` 是与前述
d85 helper 完全隔离的 final-f67 artifact-only 例外。它只接受固定
`f67be0f538f7fdc0fe413ac98bbdc5b32a29661a` commit/tree/archive/manifest、
git-ls-tree、filesystem validation 和 bundle hashes，以及独立签名 attestation
的 `/usr/local/libexec/ashare-v3/n6-immutable-release-materializer-f67`。
helper 只能在固定 Release root 内 `mkdirat` 一个全新 direct-child staging，
安全解包固定 PAX archive，验证 6240 files/45 directories、mode/link/path/PAX
合同，封存为 `0444/0555` 后用 parent-dirfd `renameatx_np` 的
EXCL/NOFOLLOW/BENEATH flags 原子晋升一次，并写不可变 f67 attestation。任何旧
staging 复用、其他 path/hash/count、retry、shell/delete/overwrite、xattr/ACL、
Release runtime、数据库、N1-N6 或交易操作都必须 `REJECT`。治理定义会话不得
安装、调用或执行该 helper。

`runtime_hot_cleanup_archive_gated_disk_governance_v1` 是磁盘治理的唯一
runtime-control 删除/cleanup LaunchAgent 例外。它严格绑定 exact label
`com.ashare-v3.runtime-hot-cleanup-keep5-daily`、exact plist、MacRaid 本地
artifact archive root、`common_trade_calendar` 权威的“当前交易日 + 前 5 个已
完成交易日”保留集合和 Data 卷 250 GiB 可用空间目标。每个独立请求只能选择
quiesce、archive-verified local reclaim、Time Machine snapshot fallback 或
archive-gated restore 一个阶段；定义或修改该 policy 的治理会话不得执行它。
归档执行仍属于独立 `N1_ingestion` gate；runtime_control 只能消费逐文件
`LocalArtifactArchiveManifest.v1`、全量 source/archive SHA equality 和每个存在
artifact family 的 `RESTORE_PROOF_PASS`。local reclaim 只能逐项重新核对普通
文件 path/device/inode/mode/mtime/size/SHA、retained-date exclusion、active
lineage exclusion 和 writer absence 后删除 exact manifest entry，并在每个日期
批次后测量 `df`，达到目标立即停止。禁止 glob/broad recursive delete、symlink、
未归档/活动 lineage、数据库删除、自动 retry、手工 cleanup replay、N3P/N4/N5/
N6 Web 等业务 LaunchAgent、old-dirty repo、Release 和 Codex session。snapshot
fallback 仅在完成本地回收后仍未达标时，删除执行时冻结且 purgeable 的 exact
`com.apple.TimeMachine.*.local` snapshot；`com.apple.os.update*` 永远禁止。
restore 前 plist 必须已移除 `direct-delete-no-archive` 及旧 confirm token 并证明
verified-archive-required；持久修复后的 restore 还必须只使用 exact regular-file
pointer
`/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts/current_verified_batch.json`
和 `--local-only`，不得保留固定一次性 batch 的四路径参数，不得计划或执行数据库
DELETE。只允许 bootstrap exact plist 一次，不 kickstart，后续验收只认自然
01:00。历史 direct-delete 报告保留为证据，但该模式自本 policy 生效起不再可用于
任何新执行或 scheduler restore。

`n1_local_artifact_archive_daily_bounded_install_v1` 是唯一允许安装 N1 本地 artifact
每日归档 LaunchAgent 的 runtime-control 例外。它严格绑定 exact label
`com.ashare-v3.n1.local-artifact-archive-daily`、exact plist
`/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n1.local-artifact-archive-daily.plist`、
`StartCalendarInterval=23:00`、`RunAtLoad=false`、`KeepAlive=false`、项目工作目录、
系统 Python 3.11、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONPATH=src:scripts:.` 以及
archive-only 入口 `scripts/run_local_artifact_archive_daily_once.py`。入口只能面向
次日 cleanup date，通过只读 `common_trade_calendar` 计算“次日 + 前 5 个已完成
交易日”，复制当前非保留四类 artifact 到
`/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts`，并且仅在 manifest、全量
source/archive SHA equality 和每个存在 family 的 restore proof 全部 PASS 后原子
发布 exact regular-file pointer `current_verified_batch.json`。

pointer schema 固定为 `LocalArtifactArchiveCurrentPointer.v1`，至少绑定
`for_cleanup_date`、`batch_id`、`retained_trade_dates`、`entry_count`、manifest、
summary、exact allowlist、restore proof 的 exact path 与 SHA-256，以及
`ARCHIVED_VERIFIED` / `RESTORE_PROOF_PASS`。空候选日也必须发布当前日期绑定的完整
verified empty batch；旧 pointer、部分归档或失败 batch 不得发布为 current。
archive job 遇到 writer、MacRaid、calendar、path、symlink、identity、hash、restore
proof 或 pointer publish 异常必须 fail-closed，pointer 保持不变，不等待、不 retry。

该 policy 的独立安装请求必须在 mutation 前冻结 policy/code/test/plist SHA、工作树
tracked/index 状态、exact label/path absence、MacRaid mount/root 和 cleanup label 未被
操作；只允许创建 exact plist 并 bootstrap exact label 各一次。禁止 kickstart、
RunAtLoad、KeepAlive、手工 archive execute、source delete/move、数据库写入、业务
worker、cleanup label、其他 LaunchAgent、自动 retry 或失败后自动 cleanup。定义或
修改本 policy 的治理会话不得安装、bootstrap 或运行它；N1 runner 实现、安装和
首次自然 23:00 验收必须分别由后续独立 gate 完成。
runtime_control 只允许登记 pipeline_run / pipeline_stage / execute command registry / rollback registry / pipeline timeline / dashboard v0 的文档、schema 草案和只读输出。
runtime_control 不得执行 registry command，不得执行 rollback SQL，不得执行 nightly run，不得连接数据库写 runtime 表，除非用户另行明确授权 runtime_control schema migration 且已有 preflight / rollback。
runtime_control 默认不得修改 N1-N6 execute contract；只有用户在当前请求明确授权的控制合同治理 gate，才可修改 Kernel/Compiler 合同与静态测试。该治理 gate 不得在同一会话执行新增例外，不得消费 outbox，不得启动 worker，不得写 trigger/action/user/sim/voice/mobile/real trade。
runtime_control 默认不得修改 LaunchAgent 或重启服务；仅限本文件逐项列明且由独立请求明确授权的命名 policy。`n6_user_web_immutable_release_bounded_rebind_v1` 仅允许对精确 label `com.ashare-v3.n6.user-web` 执行一次有界 immutable Release rebind，并在失败时恢复冻结的原 plist/Release。它不允许连接数据库、执行 migration/evaluator、启动长期 worker、操作其他 LaunchAgent 或触碰任何交易路径。
第二个且仅有的维护窗口例外是独立请求明确授权且完整满足 `n6_strategy_center_schema_migration_maintenance_window_v1`。它只允许把 Web 的 `ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED` 从 `1` 置为 `0` 并有界重启 exact Web、bootout exact Strategy Center evaluator 一次、只读冻结四张 strategy 表水位并写一个 immutable maintenance token。它不执行 081/082/083，不 bootstrap evaluator，不操作 virtual executor，不写数据库或业务/交易表。正常 5 秒 PID/runs 变化不构成配置漂移；label/plist/Release/runner/role/ACL/ownership/hash/object 变化才构成漂移。
第三个且仅用于 081 已提交维护阶段的 Web 例外是独立请求明确授权且完整满足 `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`。它要求 strategy write 在 rebind 前、目标 plist、rebind 后及回滚后始终为 `0`，要求 exact Strategy Center evaluator 的 job/PID 均不存在，并且只允许对 exact Web 执行一次 V2 immutable Release bootout/bootstrap。virtual executor 不得被停止、启动或修改；只冻结其 plist/Release/runner/role/ACL/object-boundary hashes，正常 StartInterval PID/runs 变化不构成配置漂移。该例外不连接数据库，不执行 migration/evaluator，不触碰 N1-N5、queue 或任何业务/交易路径，也不放宽普通 `n6_user_web_immutable_release_bounded_rebind_v1`。
post-083 且 strategy write 已为 `1` 时，Web rebind 前 quiesce evaluator 的唯一例外是独立请求明确授权且完整满足 `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`。它只允许对 exact label `com.ashare-v3.n6.strategy-center-evaluator-v1` 执行一次 bootout，并状态驱动等待 evaluator PID 和 job 均不存在；bootstrap、kickstart、kill/signal、重试和自动恢复均禁止。evaluator plist/path/runner/Release/role/ACL/state 必须冻结；Web 与 virtual executor 不得被操作，virtual executor 的正常 5 秒 PID/runs 变化不构成配置漂移。该例外不连接数据库、不执行 evaluator/migration、业务 DML、交易或 N1-N5 写入；失败只保留证据，后续恢复或 rebind 需要新的独立授权。
第四个且仅用于 post-083/084、strategy write 已恢复为 `1` 后的 Web 例外是独立请求明确授权且完整满足 `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`。它只接受当前 legacy 短名 source `20260724_042200__a1dc7350`，且必须将其关闭到 full commit `a1dc73503a07055f7bdb9cd29b378d1272642473`、tree/archive/git-ls-tree/manifest/filesystem/blob-mode-path attestation；该 source 只能作为本次冻结 rollback source，不能复用、修改或作为 target。target 必须是名称绑定 40 位 commit 的正式 immutable Release，并证明不回退 source 的有效 N6 增量。Web strategy write 在 before/target/after/rollback 始终为 `1`；exact evaluator 必须已由独立 N6 gate quiesce，本 policy 对 evaluator operation attempts=0。virtual executor 可保持 exact `StartInterval=5` 周期调度，但只能冻结 label/plist/Release/runner/role-ACL/object-boundary 并证明与 Web/Strategy Center 写对象无冲突；本 policy 对其 operation attempts=0，正常 PID/runs 周期变化不是配置漂移。它只允许 exact Web 一次 bootout/bootstrap、60 秒 readiness、30 秒稳定观察和一次条件 rollback，不连接数据库、不执行 migration/evaluator/executor、不触碰 N1-N5 或业务/交易路径。
082/083 的唯一迁移例外是独立 `N6_user` 请求明确授权且完整满足 `n6_strategy_center_post_081_v2_catalog_migration_window_v1`。082 和 083 必须是两个独立 gate、两个独立事务并严格按顺序执行；不得捎带、跳过、合并或重试。082 只安装 lifecycle constraint、唯一索引和 owner-only compensation functions，不得调用函数或写 revision/catalog/projection/change。083 只在 082 postflight 完成、开放交易日、pending=0、V2 selection item=0 且每个活动 principal 仍有唯一 active V1 时切换 catalog authority，不得修改已有 selection revision。两阶段均要求 strategy write=0、evaluator quiesced、virtual executor 未操作；rollback 需要独立授权。
083 后的首个 pending V2 selection 创建例外 `n6_strategy_center_post_083_single_user_pending_v2_revision_v1` 仅保留为已经完成的一次性历史恢复合同：其 principal/user、revision 15、revision 20 和交易日 20260723 固定值不得再次授权任何 Gate3+ 请求。后续用户迁移必须使用 `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`，由 reviewed N6 display-basis `for_trade_date` 共识和现场冻结的单一 predecessor CAS 动态确定 scope/date；禁止复用历史固定 revision/date。首个历史 gate 的恢复证据仍要求 `recovery_contract_version=pre_dml_guard_harness_recovery_v2`，并只承认两个按序且证据完整的历史 pre-DML harness transaction：第一次 SQLSTATE=42704，ACL guard 把 `PUBLIC` 当作 role；第二次 SQLSTATE=42601，psql `request_id` 变量位于 dollar-quoted `DO` 内未展开。两次都必须自动中止、正式 selection 函数调用=0、revision/item DML=0、commit=0、request_id 未落库、mutation_attempts=0 且全部冻结 before/after hash 相等。历史合同不得激活 revision，不得开放 Web strategy write，不得运行 evaluator，不得调用 082 compensation function，不得写 projection/change，不得操作 virtual executor、N1-N5 或任何交易对象。
Strategy Center 的当前业务日权威只能来自
`v_n6_stock_condition_display_basis`、`v_n6_index_condition_display_basis`、
`v_n6_board_condition_display_basis` 三张 reviewed N6 view 最新完整唯一批次的
`for_trade_date` 共识。`common_trade_calendar` 与 N1-N5 裸表不得用于
Strategy Center 日期选择；membership 只能按
`max(trade_date) <= source_trade_date` 作为 as-of 映射。bounded canary 必须
使用当前 reviewed-N6 日期的自然事件和动态正整数 principal/user/revision scope，
不得再绑定历史 `20260723` 或 revision 15/20。

`n6_strategy_center_display_only_scheduled_evaluator_v1` 不扩展 runtime_control
业务执行权；本层只可在用户当前请求明确授权时治理其 Kernel/Compiler 合同。
安装/启用该调度器必须切换到独立 `N6_user` gate，且治理会话不得在同一会话
使用新例外。调度器固定 StartInterval=5，每 tick 只处理一个
principal/user/revision，pending 优先、active round-robin，并在激活后至少观察
12 tick，无重叠、deadline、backoff、重启循环或跨用户写入。canary 与 evaluator
均使用 reviewed-N6 `for_trade_date` 共识。

canary 与 12 tick 稳定观察通过且 pending=0 后，
`n6_strategy_center_post_canary_web_write_restore_v1` 仅允许 exact Web
strategy-write flag `0 -> 1` 的一次有界 rebind。随后剩余七个用户只能按
`n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1` 每次一个
scope/事务/CAS 迁移。全部活动 scope 为 V2、pending=0、全用户确定性回放、
隔离、projection hash 与 SSE 验收通过后，才允许
`n6_strategy_center_v1_retirement_after_all_users_v2_v1` 独立执行一次
catalog-only V1 retirement。上述 gate 均默认 `REJECT`，禁止 N1-N5、交易、
virtual executor 操作及一般数据库/runtime execute。

Gate3 bounded canary 与 Gate4 scheduled evaluator 都要求 Web strategy-write
严格为 `0`。若当前 d85 Web flag 为 `1` 且 evaluator 已 quiesced，只能先由
独立 `runtime_control` 请求完整满足
`n6_strategy_center_pre_canary_web_write_quiesce_v1`：保持 d85 Release、
WorkingDirectory、PYTHONPATH 和其他环境不变，仅对 exact Web 执行一次
flag `1 -> 0` 的有界 bootout/bootstrap；失败最多恢复冻结 plist 和 flag `1`
一次。该 policy 不操作 evaluator 或 virtual executor，不连接数据库，也不执行
canary、N1-N5 或交易。
runtime_control 需要推进某个 stage execute 时，必须停下并交接到对应 N1-N6 layer_role。
```

跨层交接必须使用明确的交接文本，至少包含：

```text
blocked_by_layer=<目标层>
source_layer=<当前层>
证据：...
建议下一步：...
禁止本层继续做：...
```

典型例子：N2 条件层发现 `index_daily` 缺固定 9 指数历史，只能输出 `blocked_by_layer=N1_ingestion`，不得在 N2 内外拉行情或修入库表。

## 4. 当前阶段硬约束

v3 入库层和条件层都必须遵守：

```text
指数、板块、个股必须物理分表。
入库时就分开，不允许混表后再靠 asset_kind 过滤。
identity_key 必须保留，但不能替代物理隔离。
```

必须优先设计以下表族：

```text
stock_*
index_*
board_*
common_*
```

入库层核心表包括：

```text
common_ingest_batch
common_trade_calendar
stock_identity
index_identity
board_identity
stock_daily_bar_fact
stock_daily_basic
index_daily_bar_fact
board_daily_bar_fact
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
```

条件层表也必须继续物理隔离，优先使用以下表族：

```text
common_condition_*
stock_condition_*
index_condition_*
board_condition_*
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

N2 条件层输出的 `allowed_signal_types` / `selected_signal_types_json` 只表达 canonical 条件语义，只能使用以下 6 类：

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
```

`condition_key` 不等于 `signal_type`。普通 `BUY:* / SELL:*` 的 N2 condition signal_type 分别是 `BUY / SELL`；`BUY:FULL / SELL:FULL` 保留为独立 N2 condition signal_type；`BUY_HINT / SELL_HINT` 保留为 N2 正式 condition signal_type，但只对指数和板块生效，不包含个股。

N2 不再在 `allowed_signal_types` / `selected_signal_types_json` 输出 `B_BUY_30M_VOL` 或 `S_SELL_30M_SHRINK`。30m / projection 语义不由 N2 表达。`condition_key` 仅用于 trace / audit / analytics，不得被当作 action signal。N4/N5 runtime signal_type 只能收口为 `B_BUY / S_SELL`；N4 只输出 `projection_30m_flag / projection_30m_type / trigger_mark_candidate`，N5 才在分钟边界确认后给出最终 `action_mark`。

最新定稿：`BUY_HINT / SELL_HINT` 名称保留 Hint，但在 N1-N5 的语义是指数/板块买卖信号条件，不是用户层提示类型，且不得对个股生成正式 N4 HINT 触发。`BUY_HINT` 必须先由 N2 证明指数/板块超跌前置结构，再由 N4 基于 N3 标准行情事实或 N3 标准化、可追溯 realtime projection 指标确认 30m 放量上涨，才可生成正式 `TriggerMatched`；`SELL_HINT` 必须先由 N2 证明指数/板块超涨前置结构，再由 N4 确认 30m 缩量下跌，才可生成正式 `TriggerMatched`。动作层 N5 不因名称为 Hint 而改变边界，只按动作确认规则处理；是否显示为提示、alert-only、语音、sim 或交易意图呈现，只能由 N6 user_policy 决定。

方向字段只表达：

```text
buy
sell
```

其中：

```text
BUY_HINT -> direction=buy
SELL_HINT -> direction=sell
```

不得再把 hint 作为独立 direction。是否属于超跌/超涨条件族由 `condition_key`、`allowed_signal_types` 或兼容字段 `is_hint_scope` 表达；该字段不得被解释为“非正式触发”。

条件层必须定义并独立诊断三类必要条件：

```text
普通 BUY/SELL 条件
BUY:FULL / SELL:FULL 条件
BUY_HINT / SELL_HINT 条件
```

BUY:FULL/SELL:FULL 不得混写成 BUY:D/SELL:D；BUY_HINT/SELL_HINT 不得混入普通 BUY/SELL 周期集合。

条件层 schema 只保留条件层必要字段。禁止把触发/动作/语音/模拟账户执行字段放入条件层正式表：

```text
trigger_time / trigger_period / action_id / action_status / voice_status / tts_text / sim_trade_id / position_id
locked_target_price / target_lock_status / user_policy_hint
```

用户层边界：

```text
用户层可以只读查询条件层数据。
用户层不得直接查询 trigger/action 裸表。
用户层只能被动接收 N5 标准动作事件或经 N5 转发的触发状态投影；历史 ActionEvent / HintEvent / RiskEvent / PositionEvent 只能作为旧 run 证据或兼容输入。
用户层不得回写 condition_basis / condition_pool。
```

条件层静态结构字段必须只在条件层计算并定稿，触发层、动作层、用户层不得重算或回写：

```text
main_up_anchor / up_reference_period / up_amplitude / buy_target_price / up_sell_reference_period
main_down_anchor / down_reference_period / down_amplitude / sell_target_price / down_buy_reference_period
clear_sell_ref_period（仅 N5 兼容 alias，必须等于 up_sell_reference_period）
```

对称性目标价 canonical spec 以 `docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md` 为准。N2 只拥有目标价候选和静态 trace：

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

`locked_target_price / target_lock_status` 只属于 N6/position，不属于 N2。N4/N5 可以透传目标价候选作为不可变 context / audit trace，但不得重算目标价、不得锁价、不得决定清仓策略。N6/position 才能解释持仓目标价、锁定目标价和清仓策略，且不得回写 N2/N4/N5。

N2-R3 定稿后，`up_sell_reference_period / down_buy_reference_period / clear_sell_ref_period` 必须贯通：

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
```

`clear_sell_ref_period` 只作为 legacy alias，值必须等于 `up_sell_reference_period`。

N2-R4 起，条件层还必须冻结 N4 实时触发所需的周期阈值：

```text
period_trigger_baseline_json
```

该字段必须贯通：

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
```

`period_trigger_baseline_json` 至少包含 Y/Q/M/W/D 可计算周期的 current_open_seed、current_close_seed、current_amount_seed、current_trade_days_seed、previous_open、previous_close、previous_entity_high、previous_entity_low、previous_amount、previous_avg_amount、amount_metric、current_window_start/end、previous_window_start/end。

N4/N5/N6 不得回查 N1 历史 K 或自行重算这些周期阈值；只能读取 N2 冻结字段或 N4 本地化后的副本。

实时行情层边界：

```text
条件层只输出行情范围，不拉行情。
minute_target_scope 是条件来源明细表，不等于最终行情拉取任务表。
minute_target_scope 可以保留 asset_kind + identity_key + direction + condition_key 粒度，用于审计和追溯。
实时行情层消费 minute_target_scope 时，必须先按 asset_kind + identity_key + required_data_kind + for_trade_date 去重生成 market_data_subscription。
行情层不得按 minute_target_scope 明细行逐行重复拉取同一对象行情。
实时行情层统一拉取 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m。
realtime_daily_snapshot execute 只能在 for_trade_date 当天运行；当前日期不等于 for_trade_date，或 common_trade_calendar 缺少该交易日且 is_open=true 时，必须 P0 阻断，不拉行情、不写 snapshot、不写 outbox。
触发层主要消费 `MarketSnapshotUpdated / realtime_daily_snapshot`。N2 只输出 canonical `BUY / BUY:FULL / SELL / SELL:FULL / BUY_HINT / SELL_HINT`，不输出 30m action mark。N4 可基于 N2 condition signal 和 N3 标准化、可追溯 realtime projection 指标生成 `TriggerMatched`、`TriggerPendingMarketData` 以及 `TriggerStateChanged` 状态广播，并携带 `projection_30m_flag / projection_30m_type / trigger_mark_candidate`。最终 `action_mark=normal/30m_volume/30m_shrink` 由 N5 在动作确认阶段决定。`MinuteBarClosed` / N3 closed 30m summary 是强确认或回放校验入口，不是唯一入口。N4 仍不得直接拉行情，不得自行拼原始分钟，不得使用非 N3 标准指标生成正式触发。


闭合分钟 K 动作确认硬规则：

```text
1 分钟 K 的标签时间 HH:MM 表示该分钟区间，只有到 HH:MM+1 后才视为闭合。
N3 不得在分钟未闭合前写 MinuteBarClosed。
N4 不得直接读取 raw 未闭合分钟 K 生成 TriggerMatched，也不得自行拼 raw 1m/5m/30m/120m 指标；但允许消费 N3 标准化、可追溯 realtime virtual metric 生成 TriggerMatched。
N5 不得使用未闭合分钟 K 确认 ActionExecuted；ActionEligible 可在有效 TriggerMatched 后实时进入动作确认窗口。
MarketSnapshotUpdated 可以驱动实时触发状态，也可以携带或追溯到 N3 标准化 realtime projection 指标。
N2 canonical `BUY / SELL / BUY_HINT / SELL_HINT` 不要求 N4 等完整 30m 闭合；N4 可以基于 N3 标准化、可追溯 realtime projection 指标生成正式触发和 trigger_mark_candidate。MinuteBarClosed / closed 30m summary 仍是更强确认和回放校验入口。
在 N3 projection 指标和 N4 projection matcher 未落地前，N4 real execute 不得把这些 canonical signal_type 或其衍生 trigger_mark_candidate 写成正式 TriggerMatched。
```
动作层只读 minute_bar_1m / previous_day_minute_bar_1m，不直接调用外部行情接口。
用户层只读用户投影和必要行情展示投影。
```

N3-N6 事件流 / Outbox-Inbox 边界：

```text
事实和事件同事务产生。
事件是跨层协议。
表是本层事实和投影。
不是先发事件再落事实，也不是下游直接扫上游内部事实表。

N3 行情层：写本层行情事实、quality/status，并在同一事务写 MarketSnapshotUpdated / MinuteBarClosed / MinuteBarCorrected / MarketDataDelayed / MarketDataMissing / MarketDisplaySnapshotUpdated outbox event。
N4 触发层：只消费 N3 标准事件，写本层 trigger state / trigger outcome 事实，并在同一事务写 TriggerStateChanged / TriggerMatched / TriggerPendingMarketData outbox event。
N5 动作层：只消费 N4 标准事件，写本层 action confirmation 事实，并在同一事务写标准 action outbox event。历史 ActionEvent / HintEvent / RiskEvent / PositionEvent 只作为旧 run 证据或兼容路径。
N6 用户层：消费 N5 标准动作事件或经 N5 转发的触发状态投影写 user_card_projection / user_voice_delivery / user_device_ack / sim_projection；消费 N3 MarketDisplaySnapshotUpdated 写 user_market_projection。手机和语音只看用户投影。

禁止下游直接扫上游内部事实表来替代标准事件消费。
跨层只能消费 event ledger / outbox 投递后的标准事件，或使用文档明确允许的只读摘要接口。
```

N3-N6 双速链路：

```text
高实时链路：N3 -> N4 -> N5 -> N6，用于触发、动作、语音、卡片。
低频展示链路：N3 -> N6，用于 user_market_projection 行情展示字段。
N3 低频展示事件只能命名为 MarketDisplaySnapshotUpdated，不得使用 User* 事件名。
N3 事实表名沿用 stock/index/board_realtime_daily_snapshot 与 stock/index/board_minute_bar_1m，不得使用 *_runtime 表名。
```

N4/N5 最终架构边界：

```text
N4 触发层启动前必须把 N2 condition context 本地化到 runtime PostgreSQL；盘中不得每个事件访问外接盘 N2。
N4 只消费 N3 标准事件和本地 context，写 trigger state / trigger outcome fact，并同事务写 TriggerStateChanged / TriggerMatched / TriggerPendingMarketData。
N4 不拉行情，不写 action/user/sim。
普通 BUY/SELL/FULL 主要消费 MarketSnapshotUpdated；BUY_HINT / SELL_HINT 可消费 N3 标准化 realtime projection 指标，MinuteBarClosed 或 closed 30m summary 作为强确认和回放校验入口。N4 只输出 30m projection 证据和 trigger_mark_candidate，不定最终 action_mark。
N5 只消费 N4 标准事件，读取 N3 今日/前日分钟 K 作为动作上下文，写 action confirmation fact，并同事务写标准 action event。
N5 不拉行情，不重算触发，不写用户投影，不播放语音，不真实交易，不决定 alert-only / voice / mobile / sim / trade-intent policy。
BUY_HINT / SELL_HINT 是 N1-N5 内部买卖信号条件，不是用户提示类型；是否显示为提示、是否 alert-only、是否进入 sim/真实交易展示，由 N6 user_policy 决定。
N4/N5 worker 必须先 run-once 与 bounded worker smoke，长期 worker 后置。
```

标准事件必须包含：

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

N3 事件 payload 必须携带追溯字段：

```text
subscription_id
pull_plan_id
run_id
source_adapter
data_quality_status
snapshot_id / minute_bar_id / quality_item_id，按事件类型至少提供一个
```

事件消费规则：

```text
event_id 稳定。
dedup_key 稳定。
identity_key 用于分区和顺序约束。
event_schema_version 必填。
consumer 必须幂等。
projection 必须可重建。
ack / watermark 必须明确。
语音只播 watermark 后的新事件。
开启语音最多补播 1 条。
```

condition_basis / condition_pool / minute_target_scope 默认生成规则：

```text
condition_basis：保留 stock / index / board 全量条件基础，不在 basis 阶段按行情范围收窄。

index_condition_pool：默认只从固定 9 个指数中筛选合格条件：
000905、399303、000001、000852、399001、399006、000300、000016、000688。
固定 9 指数必须使用 exchange-qualified identity 筛选，不得只用裸 code：
index:SH:000905、index:SZ:399303、index:SH:000001、index:SH:000852、index:SZ:399001、index:SZ:399006、index:SH:000300、index:SH:000016、index:SH:000688。
任一固定指数缺少 condition_basis 来源必须作为 P0 阻断。
任一固定指数缺少完整周期金额基准，导致 amount_quality_status != passed，也必须作为 P0 阻断。

board_condition_pool：默认只从 `board_type=tdx_industry` 的行业板块中筛选合格条件；概念/地区扩展必须显式通过 policy 选择 `tdx_concept` / `tdx_region`。

stock_condition_pool：默认只包含已经具备普通 BUY/SELL、BUY:FULL/SELL:FULL 条件，
且通过默认选股策略的个股。默认策略至少要求 total_mv >= 100 亿、非 ST/风险票、official daily 证明存在、
财务快照基础字段可用、lane/monitor_type 合规。

minute_target_scope：只从对应 stock/index/board condition_pool 生成，可再由 policy 收窄。
```

说明：

```text
指数、板块、个股的行情范围都必须来自各自 condition_pool 或等价 dry-run 结果。
固定 9 个指数、`board_type=tdx_industry` 行业板块、个股 total_mv >= 100 亿是 condition_pool 的默认筛选策略，不是绕过 pool 的 scope 直写规则。
condition_pool 必须是可解释筛选池，保留 policy_name、policy_hash、selected_reason；被剔除候选必须在 dry-run/report/quality 中保留 excluded_reason 样本和原因分布。
未来界面可以编辑 condition_pool 筛选策略，但不得直接修改 condition_basis，也不得绕过 condition_pool 直接手写 minute_target_scope。
前一交易日一分钟 K 预加载由条件层声明 scope 和验收要求，由实时行情层实际拉取；条件层不得直接拉行情。
行情层实际拉取前必须生成去重订阅；例如 index_minute_target_scope 可以有多条 condition_key 来源明细，但指数行情按去重后的 identity_key / required_data_kind 拉取。
```

N2-D1 开始允许增加可审计筛选层：

```text
condition_basis
-> condition_pool_candidate
-> condition_pool_selection_policy
-> condition_pool
-> minute_scope_candidate
-> scope_selection_policy
-> minute_target_scope
```

要求：

```text
policy 必须按 index / board / stock 分段筛选。
默认 condition_pool policy 等价于当前自动范围。
scope policy 只能继续收窄 condition_pool 候选范围，不能绕过 condition_pool 扩张行情范围。
未来前端只操作 policy，不直接操作 condition_pool / minute_target_scope 行，也不得直接手写 condition_basis。
N2-D1 只做 dry-run，不写库、不拉行情、不进入触发/动作/用户层。
```

## 5. 数据库技术方向

默认技术方向：

```text
PostgreSQL：运行事实库
Parquet：历史归档
DuckDB：离线回放、对账、报表
```

未经用户确认，不得改成 SQLite / MongoDB / Redis / InfluxDB 作为主事实库。

Redis 只能作为未来缓存，不得作为事实库。

N3 实时行情层运行库必须使用本地硬盘：

```text
N3 runtime database：本地 SSD PostgreSQL。
N3 数据不得写入 /Volumes/MacRaid/database。
N3 数据不得和 N1/N2 外接盘历史事实、归档、Parquet 混放。
N3 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m / market_data_subscription / pull_plan / event ledger / outbox / inbox / quality / checkpoint 都属于本地运行态数据。
N4/N5/N6 若消费 N3 事件并需要低延迟运行态状态，默认也应使用同一套本地 runtime PostgreSQL 或同机本地 runtime database。
runtime 是部署和生命周期属性，不写入 N3 行情事实表名；禁止使用 stock_minute_bar_1m_runtime / index_minute_bar_1m_runtime / board_minute_bar_1m_runtime 作为正式表名。
```

N3 本地 PostgreSQL 建议：

```text
独立本地 PostgreSQL cluster 或至少独立 database。
建议 database 名：ashare_v3_runtime 或 ashare_v3_n3_runtime。
建议数据目录位于本机内置 SSD，不使用外接盘路径。
事实表按 stock/index/board 物理分表，并按 trade_date 分区或保留可滚动清理策略。
```

N3 与归档职责边界：

```text
N1/archive 是 N1_ingestion 内的归档职责名称，不是新的 layer_role。
N3 负责盘中本地 runtime 写入、同事务事件 outbox、质量项、run/trade_date 封账和 archive_request 元数据。
N3 不直接写 Parquet，不写 manifest，不写 /Volumes/MacRaid/database。
N1/archive 负责读取已封账的 N3 runtime 分区，写入 Parquet、manifest、归档审计和 rollback 元数据。
N1/archive 不参与 N3 盘中行情拉取、事件投递、触发/动作/用户投影。
只有 N1/archive manifest 校验通过后，N3 才能按本地保留策略清理旧 runtime 分区。
```

v3 入库层的数据文件根目录：

```text
/Volumes/MacRaid/database
```

说明：

- PostgreSQL 仍作为运行事实库，事实表由 PostgreSQL 管理。
- N1/N2 的 Parquet 归档、manifest、入库审计导出和可删除的数据文件默认写入该目录。
- N3 实时行情层的运行态 PostgreSQL 数据、事件流、分钟 K、实时快照和质量项不写入该目录。
- N3 盘后数据如需长期保留，必须先由 N3 封账并生成 archive_request，再由 N1/archive 归档到该目录。
- N1 阶段只生成 SQL schema 文件，不连接数据库，不创建真实数据库，不写入该数据目录。

## 6. 禁止事项

当前阶段禁止：

- 在条件层重新抓 raw data
- 在条件层直接拉一分钟 K
- 在触发层直接拉取外部行情，或绕过 N3 使用未闭合/非标准分钟 K；N4 所用 30m / projection 判断必须来自 N3 标准事实、标准事件、标准化 realtime projection 指标或 N3 明确输出的 closed summary
- 在动作层绕过实时行情层直接调用外部行情接口
- 跨层写 trigger/action，或未经明确 `layer_role`、用户 run-once 授权、preflight/contract/rollback 的 trigger/action 写入
- 写 voice
- 写 mobile projection
- 写 sim_trade
- 写真实交易接口
- 未经单独授权启动任何 worker
- 启动长期服务
- 修改旧系统数据库
- 修改旧系统服务
- 修改 LaunchAgent；只有独立 `runtime_control` 请求完整满足
  `n6_user_web_immutable_release_bounded_rebind_v1`，或独立 `N6_user` 请求在
  bounded canary PASS 后完整满足
  `n6_strategy_center_display_only_scheduled_evaluator_v1`，才可触发各自的唯一命名例外；
  另仅允许独立 `runtime_control` 请求完整满足
  `n6_strategy_center_schema_migration_maintenance_window_v1` 时准备一次
  081 quiesce window，但该例外不执行 migration；磁盘治理仅允许独立
  `runtime_control` 请求完整满足
  `runtime_hot_cleanup_archive_gated_disk_governance_v1`，并且一次只操作 exact
  cleanup label 的一个命名阶段；另仅允许独立 `runtime_control` 安装请求完整
  满足 `n1_local_artifact_archive_daily_bounded_install_v1` 时安装并 bootstrap exact
  N1 archive-only daily label 一次，该 gate 不运行归档、不操作 cleanup label
- 使用裸 code 作为跨资产 join key
- 把 stock / index / board 混入同一事实表
- 在 P0 质量问题下继续定稿

## 7. 数据质量规则

入库层必须设计 quality gate。

至少包含：

```text
identity_key coverage = 100%
同码污染 = 0
stock official daily 缺失 = 0
index official daily 缺失 = 0
board official daily 缺失 = 0
88xxxx stock violation = 0
财务指标与 stock universe 对齐
source_batch_id 可追溯
source_version 可激活/回滚
```

## N6 Strategy Center 30 天隔离退役治理

当前唯一 ACTIVE 的 Strategy Center 退役 runtime policies 为：

```text
n6_strategy_center_decommission_web_runtime_v1
n6_strategy_center_decommission_schema_archive_v1
```

所有既有 `n6_strategy_center_*` execute、scheduled evaluator、maintenance、
Web rebind/quiesce、migration、date-authority、write-toggle、remaining-user 和
V1-retirement policies 均已标记为 `RETIRED`。retirement lifecycle registry
拥有最高判定优先级；后续请求命中任一 retired policy 必须统一返回 `REJECT`，
不得读取历史 policy 块中的 `ACCEPT` 作为重新授权。历史文档、SQL、trace 和提交
必须保留审计，不得删除或静默改写。

`n6_strategy_center_decommission_web_runtime_v1` 只能由独立、明确授权的
`runtime_control` 请求执行：before/after/rollback 的 Strategy Center write flag
均必须为 `0`；exact evaluator job/PID 必须始终 absent 且不得恢复；只允许 exact
`com.ashare-v3.n6.user-web` 一次 bootout/bootstrap、readiness/stability 和主
rebind 失败时恢复冻结原 Release。Web 稳定后才可把 evaluator plist/state/log/
history 归档到新的只读退役目录。Virtual Executor、数据库和其他服务操作次数
必须为 0。

`n6_strategy_center_decommission_schema_archive_v1` 只能由后续独立、明确授权的
`N6_user` 单事务执行：将六张 Strategy Center 核心表及所属 sequence/index 移入
新的 owner-only archive schema，撤销冻结 Web runtime role、`n6_strategy_worker`
和 `PUBLIC` 对 archive schema 的 `USAGE`，并删除仅属于 Strategy Center 的
trigger/functions。必须逐表保留 before/after row count、content hash、DDL、ACL
和 dependency inventory，并提供绑定 hash、30 天内有效的专用 rollback。禁止
drop/truncate/数据 DML，禁止修改 `n6_strategy_worker` 角色本身、079 canonical
reviewed-view ACL、`n6_strategy`/`n6_ai_strategy_*`、Virtual Executor、N1-N5 或
任何交易对象。

30 天只定义最短隔离保留期，不创建自动删除任务。期满后的物理删除必须由新的、
独立、明确授权 gate 再决定；本治理线程不得执行。canary heartbeat 的暂停或删除
同样属于后续 runtime gate，本线程不执行。

## Evidence-Bound Modification Guard

Codex is a code executor, not an architecture designer. For every task, Codex MUST follow evidence-bound execution and MUST NOT infer authority, expand scope, or invent new responsibilities.

### 1. No inference rule

Codex MUST NOT use “probably”, “should”, “likely”, “seems”, or experience-based reasoning as the basis for code changes.

Every modification basis MUST come from at least one of:

- AGENTS.md
- docs/*.md canonical spec
- existing code evidence
- existing test evidence
- artifact / gate report
- live read-only query explicitly allowed by the task
- explicit user instruction

If authority cannot be proven from these sources, STOP and output BLOCKED.

### 2. Authority-first rule

Before any modification, Codex MUST identify and output:

- authority: the canonical source of the field / behavior / semantic rule
- forbidden: fields / tables / layers / paths that MUST NOT be used
- bug: the exact current code path that violates the authority rule
- patch: the smallest allowed modification point
- tests: positive test, negative pollution test, and missing-authority test
- blocked_if: conditions that require stopping instead of editing

If this summary is missing, modification is forbidden.

### 3. Scope freeze rule

Codex MUST only solve the user-named problem.

Codex MUST NOT:

- add new fields unless explicitly requested
- add new fallback paths
- add new runtime run / worker / queue / service path
- rename unrelated fields
- refactor unrelated code
- update snapshots to hide behavior changes
- modify upstream or downstream layers to make the local fix pass

If the fix appears to require another layer, STOP and output:

blocked_by_layer=<target_layer>
source_layer=<current_layer>
evidence:
handoff_prompt:
forbidden_to_continue:

### 4. File budget rule

If a task requires modifying more than 3 files, Codex MUST stop before editing and output BLOCKED.

The BLOCKED output must include:

- why more files appear necessary
- which layer owns the missing authority
- the minimal handoff prompt for the correct layer

### 5. Test proof rule

Every behavior fix MUST include tests that prove source authority.

Required tests:

1. positive test:
   - canonical authority source exists
   - code uses that source
   - expected behavior occurs

2. negative pollution test:
   - forbidden field/path contains a tempting but wrong value
   - canonical authority source contains the correct value
   - code MUST use the canonical source only

3. missing-authority test:
   - canonical authority source is missing
   - code MUST fail closed / skip / block
   - code MUST NOT fallback to forbidden sources

If any required test cannot be added, Codex MUST explain why and output BLOCKED unless the user explicitly authorizes proceeding without it.

### 6. Runtime prohibition reminder

Unless the user explicitly authorizes it in the current task, Codex MUST NOT execute:

- runtime execute
- rerun
- rollback
- worker
- queue consume
- outbox / inbox / checkpoint mutation
- DB write
- real trade
- sim
- voice
- mobile projection

Read-only verification is allowed only when the task explicitly permits it and it does not mutate DB, queues, checkpoints, workers, or runtime state.

N6 strategy-center 的有界单次 runtime/database-write 例外为：

```text
policy_id = n6_strategy_center_display_only_bounded_run_once_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外必须在独立 `N6_user` 会话中由用户当前请求明确授权，并完整满足
`docs/EXECUTION_KERNEL.md` 的 machine-readable policy。它只允许正式
`run_n6_strategy_center_once.py` 对单 principal、单 user、单 selection revision、
单当前交易日执行一次 display-only primary run 和最多一次相同 scope/input/run-id
的幂等验证；只写 N6 strategy selection/projection/change 表。任一条件缺失、
all-users、多 scope、非当前交易日、Release/ACL/watermark 漂移、长期 worker、
LaunchAgent、proposal/order/trade/position/cash、真实券商或 N1-N5 写入均返回
`REJECT`。仅 post-083 maintenance Gate2 的动态单 scope、当前 reviewed-N6
`for_trade_date` 共识、pre-Gate2 dry-run/primary/replay attempts 均为 0 的
canary 可与既有
`StartInterval=5` virtual executor 共存：必须冻结 exact label/plist/immutable
Release/runner/`PGSERVICE=n6_virtual_executor`/role ACL/object-boundary hashes，
证明该 role 对 Strategy Center selection/catalog/projection/observation/change
无写权限、对正式 Strategy Center functions 无 `EXECUTE`，且 executor 代码无
这些对象引用；本任务不得 bootout/bootstrap/修改或以其他方式操作 executor。
正常 PID/runs 变化不构成漂移；任一配置、身份、ACL、对象边界或代码引用漂移
均返回 `REJECT`。Gate2 顺序固定为同 scope dry-run -> primary -> same-input
replay。bounded evaluator 的写 allowlist 精确为 selection revision、match
projection、observation projection、match change 四表；observation 的
`SELECT FOR UPDATE/INSERT/UPDATE/DELETE` 必须全部绑定单 principal/type/user/
revision/current-open-trade-date scope 与 081 唯一 grain，且满足 input watermark、
plan hash、selection CAS、同 hash unchanged replay、qualified/observation 同
episode 互斥、`surface_kind=observation`、change dedup 和同 scope/input/run-id
replay。第五表、缺 predicate、跨 scope/date、同 episode 双 surface、重复 change、
Web/virtual executor observation 表写权或 executor observation 代码引用均
`REJECT`。Web 仍为 function-only；rollback 不删除 observation，存在 V2 依赖时
081 schema rollback 必须拒绝。一般性 N6 execute 和未明确授权的数据库写入继续
返回 `REJECT`。

唯一的 N6 strategy-center 持续调度例外为：

```text
policy_id = n6_strategy_center_display_only_scheduled_evaluator_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外必须在独立 `N6_user` 会话中由用户当前请求明确授权，
且当前 reviewed-N6 日期的单用户 bounded dry-run + primary + same-input
replay、projection 和 SSE 验收已全部 PASS。它只允许 exact label
`com.ashare-v3.n6.strategy-center-evaluator-v1` 从已验证 immutable Release 以
`StartInterval=5` 调用 `run_n6_strategy_center_auto_once.py`；数据库身份
只能是 `PGSERVICE=n6_strategy_worker`。唯一 plist planner 是
`plan_n6_strategy_center_launchd.py`，runner/planner blob、dependency lock、隔离
Python 3.11 runtime env 和 exact argv 必须同时验证。runner 必须自行绑定
`Asia/Shanghai` 当前交易日，并由 trade_date/source fingerprint/Release/
policy/pending revisions 生成稳定 attempt-scoped run_id，拒绝外部历史交易日/
scope 参数。planner 对 immutable Release 的 owner 只接受两种全树一致 authority：
当前 uid 或 `uid=0`；Release root、全部目录和全部文件必须使用同一 owner，
混合 owner、其他 uid、可写 mode、symlink、异常 hardlink 或 blob/mode/manifest
不闭合均 fail-closed。非当前开放交易日必须 fail-closed/no-op。all-users
仅表示逐 principal/user 隔离计算和 selection 激活，DML 仅可命中
`n6_user_strategy_selection_revision`、`n6_strategy_match_projection`、
`n6_strategy_observation_projection`、`n6_strategy_match_change`。observation
的 `SELECT FOR UPDATE/INSERT/UPDATE/DELETE` 必须全部绑定单
principal/type/user/revision/current-open-trade-date scope 与 081 唯一 grain，
并满足 input watermark、plan hash、selection CAS、同 hash unchanged replay、
qualified/observation 同 episode 互斥、`surface_kind=observation`、change dedup
和同 scope/input/run-id replay。launchd 单实例与 PostgreSQL advisory lock 必须同时
防重入。bounded canary 缺失，交易日/Release/ACL/runner/plist 漂移，
任何 N1-N5、outbox/inbox/checkpoint、account/cash/position 写入、
proposal/order/trade、真实券商、其他 LaunchAgent、可变代码、重入，
第五表、缺 predicate、跨 scope/date、同 episode 双 surface、重复 change、
Web/virtual executor observation 表写权、executor observation 代码引用，
或 virtual executor loaded 均返回 `REJECT`。非开放日的已安装 tick 仅可
no-op，不获得 DML 授权。Web 仍为 function-only；rollback 只允许 exact
调度器 label/plist 且不得删除 observation；存在 V2 依赖时 081 schema rollback
必须拒绝。治理该例外的会话不得在同一会话执行它。

唯一的 runtime_control Web Release rebind 例外为：

```text
policy_id = n6_user_web_immutable_release_bounded_rebind_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外必须由用户在当前独立 `runtime_control` 请求中明确授权，并完整满足
`docs/EXECUTION_KERNEL.md` 的 machine-readable policy。它只允许精确服务
`com.ashare-v3.n6.user-web` 在一个冻结的源 immutable Release 与一个验证过的目标
immutable Release 之间执行一次主 bootout/bootstrap；只有主 rebind 失败时，才允许
额外一次 rollback bootout/bootstrap 恢复冻结的源 plist/Release。ownership 不明、
多服务、多 Release、多次主尝试、lineage 降级、Release/环境漂移、不可变内容修改、
其他 LaunchAgent、数据库、migration、evaluator、virtual executor、业务 worker 或交易
路径均返回 `REJECT`。治理该例外的会话不得在同一会话执行它。

唯一的 Strategy Center 081 schema migration 维护窗口准备例外为：

```text
policy_id = n6_strategy_center_schema_migration_maintenance_window_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外必须由用户在当前独立 `runtime_control` 请求中明确授权，并完整满足
`docs/EXECUTION_KERNEL.md` 的 machine-readable policy。它只允许：

```text
Web strategy-write flag: 1 -> 0
exact Web: one state-driven bootout/bootstrap
exact Strategy Center evaluator: one bootout, zero bootstrap
read-only watermark snapshot:
  n6_user_strategy_selection_revision
  n6_strategy_match_projection
  n6_strategy_match_change
  n6_strategy_observation_projection
one immutable, expiring 081 maintenance token
```

它不授权执行 081/082/083，不写数据库、不获取数据库锁、不恢复旧 evaluator、
不操作 virtual executor、不触碰 N1-N5、queue、proposal/order/trade/position/cash
或真实券商。virtual executor 的正常 5 秒 PID/runs 变化不是配置漂移；其
label/plist/Release/runner/role/ACL/ownership 或目标对象发生变化才是漂移。
maintenance token 必须绑定 exact 081/Release/Web/evaluator hashes、quiesce 时间、
strategy 水位、expiry 和 token hashes。081 必须在后续独立 `N6_user` 会话验证
token 后执行；081 成功后必须保持 selection 写入和旧 evaluator quiesced，按
V2 Web → bounded canary → V2 evaluator 顺序推进。治理该例外的会话不得在同一
会话使用它。

唯一的 Strategy Center post-081 082/083 schema/catalog migration 例外为：

```text
policy_id = n6_strategy_center_post_081_v2_catalog_migration_window_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外只可由两个独立、明确授权的 `N6_user` 请求使用。第一个请求只执行一次
082 tooling transaction；082 postflight/ACL 通过后，第二个请求才可只执行一次
083 catalog activation transaction。两个 migration 不得合并、跳过、换序或重试。
082 只能安装 lifecycle constraints、唯一索引和 owner-only compensation functions，
不得调用函数或写 revision/catalog/projection/change。083 只能在开放交易日、
pending=0、V2 selection item=0、活动 principal 均有唯一 active V1 时执行四项
catalog authority transition，不得修改已有 selection revision。两阶段均要求
strategy write=0、evaluator job/PID 不存在、virtual executor 配置冻结且不被操作，
并使用单次 `ON_ERROR_STOP`、显式事务和 advisory transaction lock。rollback 必须
另行授权；治理该例外的会话不得在同一会话使用它。

唯一的 Strategy Center post-083 单用户 pending V2 revision 创建例外为：

```text
policy_id = n6_strategy_center_post_083_single_user_pending_v2_revision_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外只可由后续独立、明确授权的 `N6_user` 请求使用。当前 phase 的
`recovery_contract_version=pre_dml_guard_harness_recovery_v2` 只覆盖两个按序、
已证明无 mutation 的历史 pre-DML harness failure：第一次为 SQLSTATE `42704`，
ACL guard 使用 `has_function_privilege('PUBLIC', ...)` 导致
`role "PUBLIC" does not exist`；第二次为 SQLSTATE `42601`，因为 psql
`request_id` 变量位于 dollar-quoted `DO` 内而不展开。两次事务均必须自动中止，
正式 selection 函数调用、revision/item DML、commit、mutation attempts 均为 0，
request_id 未落库，所有冻结 before/after hash 完全相同。PUBLIC ACL guard 只能
改为 `pg_catalog.aclexplode(COALESCE(proacl,
pg_catalog.acldefault('f', proowner)))` 的 grantee OID `0` 检查，不得修改正式
selection 函数。新的独立请求必须先用独立 `READ ONLY` preflight transaction
完成所有复杂校验；正式 mutation transaction 禁止 `DO`、psql 变量插值和
dynamic SQL，只允许 BEGIN/SET/advisory-lock SELECT/单条正式 function SELECT/
只读 postflight SELECT/COMMIT。新 request_id 只能由 shell/driver 参数绑定层
传入；只允许审计其 hash，不得记录 token/secret。真正 mutation attempt 最多
一次，零重试。

首个 canary 精确冻结
principal_id=1、user_id=1、当前 active V1 revision_id=15/revision_no=5、
for_trade_date=20260723、目标 revision_no=6、previous_revision_id=15，以及
package key 不变但 package_1/v1 升级为 package_1/v2。它只创建 pending revision
和唯一 item，不激活，不通过 Web PUT，不把 strategy write 临时恢复为 1。
081/082/083 postflight hashes、V2 catalog、零 pending/零 V2 item、唯一 active V1、
evaluator absence、virtual executor 未操作、request_id 幂等、previous-revision CAS、
新 mutation 单事务一次 attempt 零重试、其他用户与 projection/change 不变及无交易
副作用必须全部现场复核。任意第三种 pre-DML 错误、第三次 harness transaction、
正式函数已调用、DML/commit 存在、hash 不一致、同 request_id、第二次 mutation attempt、all-users、多 scope、
非当前交易日、包 key 集合变化、predecessor 漂移、直接激活、082 compensation
function、Web/evaluator/virtual executor、N1-N5 或交易路径均返回 `REJECT`。
治理该例外的会话不得在同一会话使用它。

### 7. LIGHT MODE cannot bypass evidence

LIGHT MODE only reduces compiler/sandbox overhead.

LIGHT MODE does NOT bypass:

- authority proof
- forbidden path proof
- layer boundary checks
- runtime prohibition
- minimal diff requirement
- test proof requirement
- BLOCKED behavior

If LIGHT MODE conflicts with Evidence-Bound Modification Guard, this guard wins.

### 8. Required final output

After completion, Codex MUST output only:

- changed_files
- authority_used
- forbidden_sources_not_used
- tests_added_or_updated
- tests_run
- result
- blocked_items, if any

Do not include speculative next steps unless the task is BLOCKED.

## Execution Compiler + Kernel Enforcement Hook

Before executing ANY task, Codex MUST:

1. Convert natural language task into `execution_plan` DAG through Execution Compiler (`docs/EXECUTION_COMPILER.md`)
2. Validate DAG structure before creating `kernel_input`
3. Ensure DAG includes `PLAN -> VALIDATE -> MODIFY -> VERIFY -> FINALIZE`
4. Ensure every `MODIFY` is preceded by `VALIDATE`
5. Convert validated `execution_plan` into `kernel_input` schema
6. Send `kernel_input` to Execution Kernel (`docs/EXECUTION_KERNEL.md`)
7. Receive decision state (`ACCEPT / REJECT / BLOCK / ESCALATE`)
8. Proceed ONLY if `ACCEPT`
9. Otherwise STOP immediately

Required flow:

```text
User Task
   ↓
Execution Compiler
   ↓
Kernel Evaluation
   ↓
Runtime Gate
   ↓
Binding
   ↓
Execution
```

Hard rules:

```text
No execution without execution_plan.
Compiler is mandatory before kernel_input.
DAG must include PLAN -> VALIDATE -> MODIFY -> VERIFY -> FINALIZE.
MODIFY must always be preceded by VALIDATE.
If Compiler or Kernel is not evaluated -> task is INVALID.
```

## 8. 开发流程

每个阶段必须遵守：

1. 先读 `AGENTS.md`
2. 再读相关 `docs/*.md`
3. 先输出计划
4. 再修改文件
5. 每次只做一个阶段
6. 修改后运行必要的静态检查或测试
7. 输出修改文件、验证结果、回滚方式
8. 完成后停下，等待用户确认

## 9. 文件组织建议

建议目录：

```text
docs/
sql/
scripts/
src/ashare_v3/
tests/
configs/
data_lake/
```

说明：

- `docs/`：设计文档
- `sql/`：PostgreSQL schema / migration 草案
- `scripts/`：入库 CLI
- `src/ashare_v3/`：Python 包
- `tests/`：单元测试
- `configs/`：数据源配置
- `data_lake/`：项目内逻辑占位；真实 Parquet 归档大文件默认写入 `/Volumes/MacRaid/database/data_lake/`，不提交到代码库

## 10. 输出要求

每次完成任务后必须说明：

- 是否只在 v3 项目内修改
- 是否触碰旧系统
- 是否改数据库
- 是否启动服务
- 是否新增脚本
- 是否新增 schema
- 验证命令
- 验证结果
- 回滚方式

## 11. 回滚要求

任何代码或文档改动必须可回滚。

如果生成数据库 schema：

- 先生成 SQL 文件
- 不直接连接生产库
- 不直接执行 migration
- 不直接创建真实数据库，除非用户明确确认

如果生成数据文件：

- 必须说明路径
- 必须说明是否可删除
- 必须说明是否影响旧系统

## 12. 当前阶段总览

当前阶段总控状态以 `docs/Architecture.md`、`docs/Roadmap.md`、`docs/Tasks.md` 和最新 gate artifact 为准。

```text
AGENTS.md 不维护当前 active run_id、current-real lineage、outbox 数量、rollback_safe 或 downstream refs。
任何具体 run_id、行数、消费状态、rollback 安全性和 downstream refs 都必须来自最新 review / post-review / registration artifact 或 fresh readonly proof。
```

说明：

- `AGENTS.md` 不再记录详细历史进度，只保留执行硬规则。
- 历史 run 报告只作为历史证据；如果历史报告与当前 DB / gate 证据冲突，必须通过专门 supersession / registration gate 登记。
- N4/N5 outbox 与 inbox/checkpoint 的当前消费状态必须以 fresh readonly proof 或最新 post-review artifact 为准；不得据旧摘要重复执行或回滚。
- N5 outbox pending 不等于 N6 execute 授权。
- 下一步允许的只读 / 文档 review 分支只有：N6 user projection contract review，或 N3-C2 closed-minute / closed-30m schema readiness + additive migration draft。
- N3-C2 当前只允许登记设计与审查 schema，不允许 execute、拉行情、写 minute delta、写 closed summary、写 outbox 或启动 worker。
- 仍禁止一般性 N6 execute、worker、voice、mobile、sim、position 和真实交易；
  `n6_strategy_center_display_only_bounded_run_once_v1` 仅在独立、明确授权的
  `N6_user` gate 中按其完整 fail-closed 条件例外；post-083 Gate2 仅可按上述
  frozen/disjoint/zero-operation 合同与既有 virtual executor 共存，不获得任何
  executor 操作权或额外 evaluator DML 表权限。
- 仍禁止一般性 N6 长期 worker/LaunchAgent；
  `n6_strategy_center_display_only_scheduled_evaluator_v1` 仅在当前
  reviewed-N6 日期 bounded canary 完整 PASS 后，由独立、明确授权的
  `N6_user` gate 对唯一
  exact label 和 immutable scheduled run-once 例外。
- 仍禁止一般性 runtime_control 服务操作；`n6_user_web_immutable_release_bounded_rebind_v1`
  仅在独立、明确授权的 `runtime_control` gate 中对单个 N6 Web label 例外。
- 仍禁止一般性 runtime_control 维护窗口；`n6_strategy_center_schema_migration_maintenance_window_v1`
  仅在独立、明确授权的 `runtime_control` gate 中准备一次 exact 081 quiesce
  window，且不授权 migration 或 evaluator bootstrap。
- 081 提交后的 V2 Web 切换仅可由
  `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` 在独立、明确授权的
  `runtime_control` gate 中执行；strategy write 必须保持 0，evaluator 必须
  保持 quiesced，virtual executor 只能冻结配置证据而不得被操作。
- 083/084 提交且 strategy write 已恢复为 1 后，从唯一 legacy 短名 source
  切换到正式 40 位 immutable Release，仅可由
  `n6_strategy_center_post_083_v2_web_bounded_rebind_v1` 在独立、明确授权的
  `runtime_control` gate 中执行；legacy source 必须逐 blob 完整 attest 且只作
  一次 rollback source，evaluator 必须先由独立 N6 gate quiesce，virtual
  executor 可保持既有 5 秒周期但不得被本 policy 操作。
- 081 提交后的 082/083 仅可由
  `n6_strategy_center_post_081_v2_catalog_migration_window_v1` 在两个独立、
  明确授权的 `N6_user` gate 中严格按 082 后 083 执行；不得合并、跳过、
  调用 082 补偿函数或修改已有 selection revision。
- 083 提交后的首个 pending V2 selection 仅可由
  `n6_strategy_center_post_083_single_user_pending_v2_revision_v1` 在独立、
  明确授权的 `N6_user` gate 中对冻结的 1/1/15/20260723 scope 创建。当前
  recovery phase 采用 `pre_dml_guard_harness_recovery_v2`，必须精确绑定两个
  历史 pre-DML harness transaction：`42704/PUBLIC` 与 `42601/dollar-quoted DO
  内 psql 变量未展开`；二者正式函数/DML/commit/mutation attempts 全为 0、
  request_id 未落库且 before/after hashes 全同。新的独立 `READ ONLY` preflight
  完成全部复杂校验后，mutation transaction 禁止 `DO`、psql 插值和 dynamic SQL，
  新 request_id 仅由 shell/driver 参数绑定并只审计 hash，最多一次 mutation、
  零重试；第三种错误或第三次 harness transaction 必须拒绝。strategy write 保持
  0，Web PUT、激活、projection/change、evaluator 和 virtual executor 操作均禁止。
- post-083、strategy write=1 时，为后续独立 Web rebind quiesce evaluator 仅可由
  `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1` 在独立、明确授权的
  `runtime_control` gate 中执行；只允许 exact evaluator 一次 bootout 和状态驱动
  PID/job absence，零 bootstrap/kickstart/kill/retry/自动恢复。Web 与 virtual
  executor 均不得操作，数据库、migration、业务 DML、交易和 N1-N5 写入均禁止。
- 除上述唯一 N6 strategy-center 调度例外外，长期 worker 始终后置，
  必须先有 run-once 和 bounded worker smoke 的单独授权。


## N2-R2 静态参考周期硬规则

N2 条件层必须输出并保证非空：

```text
up_sell_reference_period
down_buy_reference_period
```

`clear_sell_ref_period` 仅作为兼容 alias，值必须等于 `up_sell_reference_period`。N2 不得再把 `clear_sell_ref_period` 当作 canonical 条件层字段；N5 持仓层后续可读取 `up_sell_reference_period` 初始化真实持仓清仓门槛。

N2 对称性目标价字段冻结：

```text
symmetry_anchor / amplitude_source_period / base_price_policy 由 N2 计算并冻结。
reference_target_price 是 N2 主目标价候选。
secondary_target_price 是 N2 可选次级目标价候选。
buy_target_price / sell_target_price 是 reference_target_price 的兼容映射。
locked_target_price / target_lock_status 不得进入 N2。
```

## N2-Display-0 四表输出硬规则

N2 条件层正式采用四表输出：

```text
condition_basis          全量审计根
condition_pool           策略筛选后的条件行
minute_target_scope      N3/N4/N5 交易链路 scope
condition_display_basis  N6 展示输入
```

`condition_display_basis` 必须由 N2 生成，物理分表命名为：

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

硬规则：

```text
condition_display_basis 只给 N6 用户层只读展示使用。
condition_display_basis 不进入 N3/N4/N5。
N3/N4/N5 仍只依赖 minute_target_scope / market_data_subscription / 标准事件链路。
condition_display_basis 不得命名为 user_condition_basis。
正式写入 condition_display_basis 时，必须生成新的 N2 run_id，并与同一 run_id 的 basis/pool/scope 生命周期一致。
不得在旧 active run 上补写 display_basis。
```

`condition_display_basis` 可以聚合 condition_pool / minute_target_scope 的多行条件来源，但输出粒度应面向 N6 展示，默认一对象一行，保留 source_condition_basis_id、source_condition_pool_ids_json、source_minute_target_scope_ids_json、selected_condition_keys_json、selected_signal_types_json 等追溯字段。
