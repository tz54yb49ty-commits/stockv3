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
  - `n6_strategy_center_display_only_scheduled_evaluator_f464_v1`
  - `n6_user_web_immutable_release_bounded_rebind_v1`
  - `n6_strategy_center_schema_migration_maintenance_window_v1`
  - `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`
  - `n6_strategy_center_post_081_v2_catalog_migration_window_v1`
  - `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`
  - `n6_strategy_center_pre_canary_web_write_quiesce_v1`
  - `n6_strategy_center_reviewed_view_date_authority_084_v1`
  - `n6_strategy_center_post_canary_web_write_restore_v1`
  - `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`
  - `n6_strategy_center_shadow_activation_grant_v1`
  - `n6_btrack_delivery_l1_web_readonly_v1`
  - `n6_btrack_delivery_l2_n6_business_v1`
  - `n6_btrack_delivery_l3_virtual_runtime_v1`
  - `n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1`
  - `n5_n6_trigger_status_scheduled_convergence_30s_v1`
  - `n5_trigger_status_scheduler_timeout_recovery_20260804_v1`
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
TriggerMatched 是 N5 动作确认入口；TriggerPendingMarketData 只能作为 no-op / quality-only / state-gate，不允许 N5 开始动作确认；TriggerStateChanged 只做状态广播和 live/state gate，不写 common_trigger_match，也不作为动作入口。
pending_market_data 的 trigger_live=false；matched 的 trigger_live=true；inactive 的 trigger_live=false。
TriggerCleared / TriggerLiveChanged 仅作为旧 run 证据或兼容项，新 runtime 清除统一用 TriggerStateChanged(trigger_live=false, current_status=inactive)。
N5 只负责动作确认事实和动作事件，不负责用户展示策略。
TriggerMatched 是 N5 唯一动作确认入口；TriggerPendingMarketData 和 TriggerStateChanged 不得创建动作确认。
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
  `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` 的单个 V2 Web Release rebind；
  082/083 仅允许独立 `N6_user` 请求按
  `n6_strategy_center_post_081_v2_catalog_migration_window_v1` 严格分两次执行
- N6 execute；仅可在独立 `N6_user` 会话中精确满足
  `n6_strategy_center_display_only_bounded_run_once_v1` 或
  `n6_strategy_center_display_only_scheduled_evaluator_f464_v1`；另仅允许在 post-081
  维护窗口中精确满足 `n6_strategy_center_post_081_v2_catalog_migration_window_v1`
  的单阶段 082 或 083 schema/catalog migration；083 已提交后另仅允许独立
  `N6_user` 请求精确满足
  `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`，在 strategy
  write=0、evaluator quiesced 下创建一个单用户 pending V2 revision
  ；其余用户仅可在独立 `N6_user` 会话中精确满足
  `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`，按
  单 principal/user/predecessor CAS 创建一个 pending V2 revision；该策略不
  允许 all-users、Web PUT、手工 DML 或复用首个用户的冻结 scope；另仅允许后续
  独立 `N6_user` 请求精确满足 L2
  `trigger_status_projection_20260731_backfill` machine phase，执行一次冻结历史
  trigger-status bounded consumer；另仅允许当前请求已明确授权且分层精确满足
  `n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1` 时，由独立
  `N5_action` gate 先执行一次 status-forward-only，再由独立
  `N6_user` gate 执行一次当日 trigger-status bounded consumer；一般 L2
  consumer/runtime execute 仍禁止；另仅允许当日恢复与登录态只读验收均 PASS 后，
  按 `n5_n6_trigger_status_scheduled_convergence_30s_v1` 分别在独立
  `N5_action` / `N6_user` gate 安装两个 exact-label、30 秒、非 resident 的
  run-once LaunchAgent，必须先 N5 后 N6
- 语音播报
- mobile projection
- 未按 `N6_B_TRACK_DELIVERY_GOVERNANCE_V1` L3 合同授权的虚拟账户资金、
  proposal、position 或自动执行变更
- 未按 `N6_B_TRACK_DELIVERY_GOVERNANCE_V1` L1/L2 合同分类、验证和发布的
  N6 前端页面变更
- 真实交易
- 长期 worker 启动；唯一调度例外是独立 `N6_user` 请求完整满足
  `n6_strategy_center_display_only_scheduled_evaluator_f464_v1` 的 exact-label、5 秒
  run-once LaunchAgent，且其前置 bounded canary 必须已通过
  ；另一例外仅为 `n5_n6_trigger_status_scheduled_convergence_30s_v1` 的两个
  exact-label 30 秒 run-once；它们不得复用或修改现有 N5/N6 poller

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
| `runtime_control` | runtime pipeline run/stage/command registry/rollback registry/timeline/dashboard 的文档、schema 草案、测试、只读 dashboard 输出；用户当前请求明确授权时，可修改控制面 Kernel/Compiler 合同及其静态测试，但不得在同一会话使用新增例外执行 N1-N6；可按 `N6_B_TRACK_DELIVERY_GOVERNANCE_V1` 只读分类 L1/L2/L3、维护 canonical integration baseline 和 service compatibility registry；后续独立请求精确满足 `n6_btrack_delivery_l1_web_readonly_v1`、`n6_btrack_delivery_l2_n6_business_v1` 或 `n6_btrack_delivery_l3_virtual_runtime_v1` 的 runtime-control 阶段时，才可执行该阶段列明的 exact immutable Release/service 操作；既有具名 policy 仅保留为历史兼容，不得作为普通新需求继续复制；精确满足 `n6_user_web_immutable_release_bounded_rebind_v1` 时，可对单个 `com.ashare-v3.n6.user-web` 执行一次 immutable Release rebind 和失败时的一次原 Release 恢复；精确满足 `n6_strategy_center_schema_migration_maintenance_window_v1` 时，可关闭 Strategy Center selection 写入口、有界重启该 Web、仅 quiesce exact evaluator，并写一个只读水位绑定的 immutable maintenance token；081 已提交后精确满足 `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` 时，可保持 strategy write=0、evaluator quiesced、virtual executor 不被操作，仅对该 Web 执行一次 V2 immutable Release rebind | N1-N6 合同、报告、rollback SQL 路径、run_id lineage、quality gate 摘要 | 执行 registry command、执行 nightly run、执行 rollback SQL、连接数据库写 runtime 表、消费 outbox、启动业务 worker、写 N1-N6 事实；除命名策略或 N6 delivery lane exact phase 外修改 LaunchAgent 或重启服务 |
| `N1_ingestion` | raw ingest、source_version、quality gate、active source_version、PostgreSQL/Parquet fact、N3 sealed runtime 的归档执行、入库回滚与入库文档 | N2 readiness 缺口报告、N3 archive_request / sealed runtime 分区 | 运行 condition_basis/condition_pool execute、写 `condition_*`、盘中拉分钟 K、触发/动作/用户层、worker |
| `N2_condition` | `condition_basis`、`condition_pool`、`minute_target_scope`、`condition_display_basis`、条件层质量项、条件层回滚 SQL、条件层文档 | N1 active source_version、N1 ready check、入库 fact | 外拉 Tushare/mootdx/实时行情、修 N1 fact、写 ingest 表、拉 1 分钟 K、进入 N3/N4/N5/N6 |
| `N3_market_data` | market_data_subscription、market_data_pull_plan、`previous_day_minute_bar_1m`、今日分钟 K、实时日 K/快照、行情质量项、N3 标准行情事件、低频行情展示事件、盘后封账与 archive_request 元数据 | N2 active condition run 和 `minute_target_scope` | 改条件层、重新计算条件、写 trigger/action/user、写用户卡片、播放语音、直接写 Parquet 归档或外接盘、启动交易 worker |
| `N4_trigger` | trigger event/state、trigger quality item、trigger dry-run/execute 合同 | N2 condition_pool、N3 行情快照/分钟 K | 拉行情、改条件、写 action、写 mobile/voice/sim |
| `N5_action` | action event、hint/risk/action 归一化事件、position event、动作质量项 | N4 trigger、N3 分钟 K、必要的 N2 条件摘要 | 改 N1/N2/N3/N4、写用户投影、播放语音、写真实交易 |
| `N6_user` | user projection、voice policy、mobile/card projection、sim shadow、用户偏好表；普通 B轨新需求必须先由 `N6_B_TRACK_DELIVERY_GOVERNANCE_V1` 分类为 L1/L2/L3：L1 仅 Web/read-only，L2 仅 N6 schema/business 且不得自动影响资金，L3 才允许在完整 bounded smoke、queue governance、独立授权和 fail-closed 证据下处理虚拟资金/runtime；精确满足 `n6_strategy_center_display_only_bounded_run_once_v1` 时，可执行单 principal/user/revision/current reviewed-N6 trade-date 的策略中心 display-only bounded run-once；在 20260727 当前开放日自然 N6 input 的 exact F464 canary PASS 且精确满足 `n6_strategy_center_display_only_scheduled_evaluator_f464_v1` 时，可安装/启用唯一 exact-label、StartInterval=5、每 tick 单 scope 的 immutable-Release run-once 调度器；在 081 已提交、Web strategy write=0、evaluator quiesced 的维护窗口中，精确满足 `n6_strategy_center_post_081_v2_catalog_migration_window_v1` 时，可先单独执行一次 082，完成 postflight 后再由另一个独立请求单独执行一次 083；083 已提交后可按首用户及 remaining-user 命名 policy 每次创建一个 pending V2 revision；全部活动 scope 已为 V2 且 pending=0 后，可按命名 V1 retirement policy 单独退休 V1 catalog | N2 条件摘要、N5 输出事件 | 回写 N1-N5、直接改 trigger/action 事实、真实交易、未分类或跨 lane 扩权 |

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
runtime_control 只允许登记 pipeline_run / pipeline_stage / execute command registry / rollback registry / pipeline timeline / dashboard v0 的文档、schema 草案和只读输出。
runtime_control 不得执行 registry command，不得执行 rollback SQL，不得执行 nightly run，不得连接数据库写 runtime 表，除非用户另行明确授权 runtime_control schema migration 且已有 preflight / rollback。
runtime_control 默认不得修改 N1-N6 execute contract；只有用户在当前请求明确授权的控制合同治理 gate，才可修改 Kernel/Compiler 合同与静态测试。该治理 gate 不得在同一会话执行新增例外，不得消费 outbox，不得启动 worker，不得写 trigger/action/user/sim/voice/mobile/real trade。
runtime_control 默认不得修改 LaunchAgent 或重启服务。唯一例外是独立请求明确授权且完整满足 `n6_user_web_immutable_release_bounded_rebind_v1`；该例外仅允许对精确 label `com.ashare-v3.n6.user-web` 执行一次有界 immutable Release rebind，并在失败时恢复冻结的原 plist/Release。它不允许连接数据库、执行 migration/evaluator、启动长期 worker、操作其他 LaunchAgent 或触碰任何交易路径。
`n6_strategy_center_shadow_activation_grant_v1` 只允许后续独立 `runtime_control` 会话在 parent approval `N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION` 下续跑。四个用户可见阶段保持不变，但 `BOUNDED_REBIND` 内部分为 `BOUNDED_REBIND_WEB_TARGET` 与 `BOUNDED_REBIND_EVALUATOR_TARGET`。WEB_TARGET 只允许安装 immutable f464 Release 并把 exact Web 从 d85 rebind 到 f464，strategy-write 必须始终为 `0`，Evaluator job/runner 必须保持 absent/0；EVALUATOR_TARGET 在 WEB_TARGET passed 且后续 current-date bounded canary PASS 前必须保持 `blocked_pending_canary`，不得提前 planned、发 lease 或 bootstrap。执行前必须具备第二级不可变 supersession、完整 manifest SHA 链、最终治理提交的外部 attestation、failed checkpoint 的 resume evidence、内部 checkpoint 与匹配短 lease。禁止 kickstart、runner、同会话 canary、空状态恢复、Virtual Executor、数据库、N1-N5、业务、broker 与交易写入。
第二个且仅有的维护窗口例外是独立请求明确授权且完整满足 `n6_strategy_center_schema_migration_maintenance_window_v1`。它只允许把 Web 的 `ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED` 从 `1` 置为 `0` 并有界重启 exact Web、bootout exact Strategy Center evaluator 一次、只读冻结四张 strategy 表水位并写一个 immutable maintenance token。它不执行 081/082/083，不 bootstrap evaluator，不操作 virtual executor，不写数据库或业务/交易表。正常 5 秒 PID/runs 变化不构成配置漂移；label/plist/Release/runner/role/ACL/ownership/hash/object 变化才构成漂移。
第三个且仅用于 081 已提交维护阶段的 Web 例外是独立请求明确授权且完整满足 `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`。它要求 strategy write 在 rebind 前、目标 plist、rebind 后及回滚后始终为 `0`，要求 exact Strategy Center evaluator 的 job/PID 均不存在，并且只允许对 exact Web 执行一次 V2 immutable Release bootout/bootstrap。virtual executor 不得被停止、启动或修改；只冻结其 plist/Release/runner/role/ACL/object-boundary hashes，正常 StartInterval PID/runs 变化不构成配置漂移。该例外不连接数据库，不执行 migration/evaluator，不触碰 N1-N5、queue 或任何业务/交易路径，也不放宽普通 `n6_user_web_immutable_release_bounded_rebind_v1`。
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

`n6_strategy_center_display_only_scheduled_evaluator_f464_v1` 不扩展 runtime_control
业务执行权；本层只可在用户当前请求明确授权时治理其 Kernel/Compiler 合同。
安装/启用该调度器必须切换到独立 `N6_user` gate，且治理会话不得在同一会话
使用新例外。调度器固定 StartInterval=5，每 tick 只处理一个
principal/user/revision，pending 优先、active round-robin，并在激活后至少观察
12 tick，无重叠、deadline、backoff、重启循环或跨用户写入。canary 与 evaluator
均使用 reviewed-N6 `for_trade_date` 共识。20260727 F464 canary 的 exact scope
固定为 principal_id=12、principal_type=human_user、user_id=11、
selection_revision_id=22、revision_no=1、package_1=v2；`user`、`admin` 或未知
principal_type 均不得替代该 revision 22 scope。

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
严格为 `0`。若 flag 为 `1` 且 evaluator 已 quiesced，只能先由独立
`runtime_control` 请求完整满足
`n6_strategy_center_pre_canary_web_write_quiesce_v1`：保持同一 immutable
Release、WorkingDirectory、PYTHONPATH 和其他环境不变，仅对 exact Web 执行
一次 flag `1 -> 0` 的有界 bootout/bootstrap；失败最多恢复冻结 plist 一次。
该 policy 不操作 evaluator 或 virtual executor，不连接数据库，也不执行
canary、N1-N5 或交易。
runtime_control 需要推进某个 stage execute 时，必须停下并交接到对应 N1-N6 layer_role。
```

N6 reviewed-view 日期权威补充合同（20260724 起生效）：

```text
policy_id=n6_strategy_center_reviewed_view_date_authority_084_v1
仅允许 N6_user 独立会话执行一次 084 forward；日期只能来自三张 reviewed
display view 的最新完整批次 for_trade_date 共识。source_trade_date、
source_run_id、批次与 projection/card watermark 必须冻结。不得修改
selection/projection/change/catalog 或调用补偿函数；082/083、evaluator、Web、
交易与 N1-N5 均不在该 policy 范围内。

policy_id=n6_strategy_center_post_canary_web_write_restore_v1
仅允许在 display-only canary PASS、5 秒 evaluator 已观察至少 12 tick、pending=0、
目标 Release/ACL/ownership/hash 无漂移且 evaluator 稳定时，把精确 Web 的
ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED 从 0 改回 1；仅一次 bootout/bootstrap，
失败只恢复冻结 plist 且 flag=0。不得启动/恢复 evaluator、virtual executor、migration、
数据库业务 DML 或交易路径。
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
  `n6_strategy_center_display_only_scheduled_evaluator_f464_v1`，才可触发各自的唯一命名例外；
  另仅允许独立 `runtime_control` 请求完整满足
  `n6_strategy_center_schema_migration_maintenance_window_v1` 时准备一次
  081 quiesce window，但该例外不执行 migration
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
`REJECT`。仅 post-083 maintenance Gate2 的单 scope revision 20、当前交易日
20260723、pre-Gate2 dry-run/primary/replay attempts 均为 0 的 canary 可与既有
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
policy_id = n6_strategy_center_display_only_scheduled_evaluator_f464_v1
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

该例外必须在独立 `N6_user` 会话中由用户当前请求明确授权，
且 20260722 单用户 bounded dry-run + primary + same-input replay、projection
和 SSE 验收已全部 PASS。它只允许 exact label
`com.ashare-v3.n6.strategy-center-evaluator-v1` 从已验证 immutable Release 以
`StartInterval=5` 调用 `run_n6_strategy_center_auto_once.py`；数据库身份
只能是 `PGSERVICE=n6_strategy_worker`。唯一 plist planner 是
`plan_n6_strategy_center_launchd.py`，runner/planner blob、dependency lock、隔离
Python 3.11 runtime env 和 exact argv 必须同时验证。runner 必须自行绑定
`Asia/Shanghai` 当前交易日，并由 trade_date/source fingerprint/Release/
policy/pending revisions 生成稳定 attempt-scoped run_id，拒绝外部历史交易日/
scope 参数；非当前开放交易日必须 fail-closed/no-op。all-users
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
- L2 `trigger_status_projection_20260731_backfill` 仅允许后续独立、明确授权的
  `N6_user` gate 按完整 machine object 处理一次冻结历史 consumer；本治理 gate、
  任意日期、任意 run、重试或其他 consumer 均不获得 execute 权。
- `n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1` 仅允许已授权的
  `20260803` 当日恢复：独立 `N5_action` gate 只向 `common_event_outbox`
  写两类状态消息，通过后独立 `N6_user` gate 只写
  `n6_trigger_status_current`、该 consumer 的 inbox/checkpoint。本 `runtime_control`
  gate 只登记合同，不得使用该例外执行任一子 gate。
- 仍禁止一般性 N6 长期 worker/LaunchAgent；
  `n6_strategy_center_display_only_scheduled_evaluator_f464_v1` 仅在当前
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
- 除上述唯一 N6 strategy-center 调度例外外，长期 worker 始终后置，
  必须先有 run-once 和 bounded worker smoke 的单独授权。

## N6 B轨交付通道硬规则

普通 N6 B轨新需求统一使用
`docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json`，不得再为相同类型需求创建
一次性 migration/rebind/runtime policy。三个可复用 policy 是：

```text
L1 = n6_btrack_delivery_l1_web_readonly_v1
L2 = n6_btrack_delivery_l2_n6_business_v1
L3 = n6_btrack_delivery_l3_virtual_runtime_v1
```

分类规则：

- L1：页面、文案、只读查询和筛选展示；不得 migration、数据库写入或操作
  quote/executor/stop-loss。
- L2：N6 schema、监控范围、策略配置和不自动影响资金的 N6 业务规则；必须有
  forward/rollback、PG16 和独立部署/只读验收。
- L3：任何 proposal、虚拟资金、position/lot、executor、stop-loss 或自动虚拟执行；
  必须保留 bounded smoke、confirmed queue 治理、独立持续运行授权和立即 bootout。

永久禁止真实券商、真实订单、自动创建/确认 proposal 和 N6 回写 N1-N5。
历史具名 policy 与 BLOCKED/PASS 证据保持 append-only；只有独立 retirement gate
可以停用，不得静默删除或改写。新需求无法可靠分类时必须 `BLOCK`，不得猜测。

L2 trigger-status 历史 consumer phase：

- `trigger_status_projection_20260731_backfill` 只属于既有
  `n6_btrack_delivery_l2_n6_business_v1`，不是新 policy。仅后续独立、明确授权的
  `N6_user` gate 可按 machine contract 对
  `n6_trigger_status_projection_v1`、`20260731`、固定 projection run、2296 条冻结
  输入执行一次 bounded run-once；本 `runtime_control` 治理会话不得使用该 phase。
- execute 前必须已有独立 N6_user 提供并通过静态/PG16 验证的 exact projection-run
  rollback artifact。它只能删除该 run 的 `n6_trigger_status_current`、该 consumer
  对应冻结 input event 的 inbox，并重算或恢复 exact checkpoint；不得使用会
  `DROP TABLE` 的 089 rollback，不得删除其他 consumer/旧投影，rollback 仍需独立授权。
- outbox 只读且 status update=0；ActionExecuted 为 no-op；trigger-status schema/API/UI/
  payload 不含 `trigger_pct`，现有 `ActionEligible` immutable payload 不得修改。任何
  migration、Release/Web/service/browser/LaunchAgent/scheduler、N1-N5、交易、virtual
  executor、Strategy Center、手工 SQL、重试或捎带下一阶段均 `REJECT`。

L2 trigger-status 20260803 当日恢复 phase：

- `policy_id=n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1`。执行前
  Web 当日、N4/N5 event trade date 与请求日期必须全部为 `20260803`；
  任一日期或 lineage 漂移必须 `BLOCKED_DATE_DRIFT`，不得自动换日。
- N5 子 gate 只允许 `status_forward_only_offline_bounded_v1`，必须绑定唯一
  `source_eligible_action_run_id`，只能幂等新增 `TriggerStatusUpdated` /
  `TriggerStatusInvalidated`；`common_action_event`、action fact/tracking、N4 inbox/
  checkpoint 和 N4 outbox status 变化必须为 0。
- N6 子 gate 仅允许 `consumer_name=n6_trigger_status_projection_v1`、
  `partition_key=trigger-status:20260803`、
  `projection_run_id=n6_trigger_status_projection_20260803_recovery_v1`。冻结输入不得
  超过 5000；只写新状态表和该 consumer inbox/checkpoint，不更新 N5 outbox
  status，不得触碰 Signals/Messages/Cards 或其 consumer checkpoint。
- 两个子 gate 均最多一次 execute。`systemError` 不是重试权；重试前必须
  先用 fresh read-only 证据证明零提交，再由独立 supersession gate 授权。
- 本 phase 不授权 migration、Release/Web/service/browser、LaunchAgent/scheduler、
  Strategy Center、virtual executor、语音、mobile、sim、持仓、资金或任何交易操作。

L2 trigger-status 30 秒隔离收敛 phase：

- `policy_id=n5_n6_trigger_status_scheduled_convergence_30s_v1` 仅在 20260803
  bounded recovery 与已登录 Safari GET/reload 只读验收均 PASS 后生效。
- 固定 label 为 `com.ashare-v3.n5.trigger-status-forward-v1` 与
  `com.ashare-v3.n6.trigger-status-projection-v1`；均为 `StartInterval=30`、
  `RunAtLoad=false`、`KeepAlive=false`，使用 singleton、immutable Release、独立
  report/history。不得 kickstart，不得改现有 poller/checkpoint。
- N5 runner 只从当前 stable intraday lineage 读取开放交易日，并要求唯一
  ActionEligible authority；只可幂等写两类状态消息到 N5 outbox。N6 runner 只消费
  独立 trigger-status consumer/checkpoint，写当前状态表。日期关闭返回 NOOP；当前
  开放日与 lineage 不一致或 authority 不唯一时 BLOCKED，均不得猜测换日。
- 激活必须分层且有序：先由独立 `N5_action` gate 安装/观察 N5 exact label，再由
  独立 `N6_user` gate 安装/观察 N6 exact label。治理会话不得安装或启动任一 label。
- 禁止 migration、Web rebind、SSE、现有 Signals/Messages/Cards、N1-N4、Strategy
  Center、virtual executor、语音、mobile、sim、持仓、资金与任何交易操作。

L2 trigger-status N5 调度超时恢复 phase：

- `policy_id=n5_trigger_status_scheduler_timeout_recovery_20260804_v1` 仅处理
  `com.ashare-v3.n5.trigger-status-forward-v1` 在 `20260803 15:06:15+08:00`
  的只读 plan 查询超时误分类，以及由此跨日阻断 `20260804` 的单次恢复。
- `runtime_control` 只登记合同并冻结首次日志、滚动报告、Release、label 与数据库
  只读水位，不得修改代码、数据库、Release、plist 或服务。实现与 exact N5 label
  rebind 必须在后续独立 `N5_action` gate 完成。
- N5 修复只能区分 plan/write 失败阶段：plan 失败必须
  `BLOCKED_CORE_PLAN_READ` 且 `requires_post_check=false`；只有 writer/commit
  歧义可为 `BLOCKED_COMMIT_UNKNOWN` 且必须写不可覆盖 incident。滚动报告不得
  覆盖该 incident。
- 代码 diff 仅允许两个 N5 runner 与聚焦测试；禁止 schema、index、migration。
  runtime 最多一次 exact N5 bootout/bootstrap，禁止 kickstart/retry，N6 label 与
  N6 consumer 不得操作。
- 第一个自然 tick 只可幂等新增 `TriggerStatusUpdated` /
  `TriggerStatusInvalidated`。禁止 Action*、action fact/tracking、N4、现有
  Signals/Messages/Cards、Web/SSE、Strategy Center、executor 与任何交易副作用。

Git 与 Release 规则：

- canonical branch/worktree 固定为
  `codex/n6-btrack-integration` /
  `/Users/chuanfuchen/Documents/A股监控系统v3_n6_btrack_integration`。
- 主检出 preserve-only；临时任务从 canonical baseline 创建隔离 worktree。
- 管理中的活动 N6 worktree 目标上限为 5；任何删除必须另行授权，并先证明
  tracked/untracked/ignored 全部为零且证据已冻结。
- Web、quote writer、virtual executor、stop-loss 默认从一个 commit 构建；
  分叉必须登记在 `docs/N6_B_TRACK_BASELINE_REGISTRY_V1.json`，不得在发布时临时猜测。
- 当前 registry 的 `deployment_authorized=false`；本治理提交不得据此切换服务。

L1 post-decommission Web deployment phase：

- `post_decommission_web_readonly_rebind` 是既有
  `n6_btrack_delivery_l1_web_readonly_v1` 的可复用 `runtime_control` deployment
  phase，不是新 policy，也不得复活或复制历史 Strategy Center one-off policy。
- 仅适用于已由 L1 分类 `ACCEPT` 的 Web/read-only、UX-only、非 Strategy surface
  恢复、非回归 candidate；source/target/live/rollback 的 strategy-write 必须恒为
  `0`，退役页面必须精确 `307` 到
  `/n6/app/signals?notice=strategy_center_retired`，三个 Strategy API 必须精确
  `410` 且 `Cache-Control: no-store`，不得恢复任何 Strategy surface。
- exact Strategy evaluator 必须 job/PID absent 且操作次数 `0`。virtual executor
  可 loaded 并自然 StartInterval 轮转，正常 PID/runs 变化不算漂移，但其
  label/plist/Release/runner/role/ACL/ownership/object/hash 必须与 Web disjoint，
  且操作次数 `0`。
- target Release 必须使用 Release-specific immutable manifest，绑定 target
  commit/tree、exact archive/fileset、逐项 mode/owner/SHA、canonical retirement
  exclusion set 与 filesystem/object hash。pre-manifest legacy source 只能用只读
  重建证据冻结 source/rollback：exact source commit/tree、exact exclusion set、
  全部 present files 的 Git blob/mode 等价、无 extras、sealed owner/mode、无 write
  bits/symlink 及 deterministic object hash；禁止写回 source，且不得替代 target
  manifest。缺失、多义、extra 或 hash 漂移均 `REJECT`。
- Web plist 仅允许 WorkingDirectory/PYTHONPATH 的 Release binding 精确
  source→target；ProgramArguments 必须逐 token byte-identical、恰好两个 token，
  第二个固定为无 `..` 的相对 `scripts/run_n6_user_app.py`。interpreter 可以是
  literal `python3`，或冻结的 absolute immutable system Python；absolute
  interpreter token 可为冻结的 symlink chain，但 token、每个 hop/readlink text、
  resolved canonical regular target 及 `/Library` 至 trusted bin boundary 全路径链的
  owner/group/mode/flags/ACL/hash 必须 source/target 完全一致且无 escape/cycle/ambiguity。
  Web service principal 必须不是 owner、不得属于有写权限的 group，ACL/flags 也不得
  授予写权限，完整路径链必须 `effective_non_writable_by_service_principal`；该
  interpreter 不得当作 Release-bound runner、不得替换且 replacement count 必须为
  `0`。relative script 必须解析到 target Release 内并与 target manifest 的
  owner/mode/hash/entry 精确一致。mixed/extra argv、interpreter/script drift 或任一
  runner check 失败均 `REJECT`。
- primary 仅一次安全 plist replace/swap、一次 bootout、至少等待 1 秒并确认旧
  job/PID 消失、一次 bootstrap；禁止 kickstart、retry、第二次 primary、降级。
  仅 primary failure 可做一次 frozen-source rollback。DB、N1-N5、evaluator、
  executor、业务、proposal、资金、持仓、交易影响全部为 `0`；缺字段或 route/
  plist/side-effect/operation-count 漂移全部 `REJECT`。
- governance-only 合同修改会话不得使用本 phase 执行 Release、plist、launchctl
  或任何服务操作；deployment 必须是后续独立且明确授权的请求。


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
  - `n6_strategy_center_post_081_v2_catalog_migration_window_v1`
  - `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`
  - `n6_strategy_center_post_083_multi_user_pending_v2_revision_v1`
  - `n6_strategy_center_pre_canary_web_write_quiesce_v1`
  - `n6_strategy_center_reviewed_view_date_authority_084_v1`
  - `n6_strategy_center_post_canary_web_write_restore_v1`
  - `n6_strategy_center_shadow_activation_grant_v1`
  - `n6_btrack_delivery_l1_web_readonly_v1`
  - `n6_btrack_delivery_l2_n6_business_v1`
  - `n6_btrack_delivery_l3_virtual_runtime_v1`
  - `n5_n6_trigger_status_scheduled_convergence_30s_v1`
  - `n5_trigger_status_scheduler_timeout_recovery_20260804_v1`
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
