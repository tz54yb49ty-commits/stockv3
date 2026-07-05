# N5 Unified Buy/Sell Action Rule Repair Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:systematic-debugging first, then superpowers:test-driven-development for code repairs. This plan is intended for a fresh one-shot repair session with explicit user authorization to work across N3/N4/N5/N6 for this single task.

**Goal:** Fix the 20260608 v13 index-all action chain so every buy/sell `TriggerMatched` uses one unified N5 action rule, with HINT treated as buy/sell condition provenance rather than a separate action class.

**Architecture:** N4 owns trigger evidence and `trigger_mark_candidate`; N3 owns action-confirmation metrics; N5 owns one unified action confirmation rule for all buy/sell `TriggerMatched`; N6 only projects the final N5 action event state. The repair must remove the current HINT-only / 30m-only shortcut behavior, fix metric time alignment, and rerun the scoped 20260608 chain with rollback safety.

**Tech Stack:** PostgreSQL runtime DB `ashare_v3`, Python scripts under `scripts/`, runtime code under `src/ashare_v3/{market,trigger,action,user}`, tests under `tests/`, artifacts under `docs/` and `sql/`.

---

## 1. Current Finding

The current 20260608 until 15:00 closeout is not an acceptable final action result.

Observed from read-only comparison against `/Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx`:

```text
Old export:
  normal B_BUY/S_SELL rows = 734
  is_hint = 0
  action rows marked actual = 734
  trigger_period distribution = D/W/M/Y
  detail.primary_trigger_period = D/W/M/Y
  detail.all_trigger_periods = [D/W/M/Y]

v3 current 15:00 lineage:
  N4 common_trigger_match = 122
  N4 matched condition_key = BUY_HINT 116 / SELL_HINT 6
  N5 common_action_event = ActionBlocked 122
  ActionExecuted = 0
  ordinary BUY/SELL common_trigger_state = 3770
  ordinary BUY/SELL common_trigger_match = 0
  ordinary BUY/SELL N5 action_event = 0
```

Object-level comparison:

```text
old unique identity+direction+condition = 164
old unique keys found in v3 state = 103
old unique keys found in v3 match = 0
old unique keys found in v3 N5 action = 0
```

The serious v3 symptom:

```text
ordinary BUY/SELL state rows:
  current_status = pending_market_data
  trigger_period = 30m
  primary_trigger_period = null
  all_trigger_periods = []
```

This is incompatible with the normal buy/sell action model, where ordinary triggers carry formal periods `Y/Q/M/W/D`.

## 2. Correct Semantic Rule

This repair must use the following rule:

```text
N2/N4:
  BUY_HINT / SELL_HINT are buy/sell signal conditions.
  HINT differs only in trigger evidence:
    BUY_HINT requires N4 30m volume-up projection confirmation.
    SELL_HINT requires N4 30m shrink-down projection confirmation.

N5:
  All buy/sell TriggerMatched rows use one unified action confirmation rule.
  N5 must not create a separate action rule for HINT.
  N5 must not downgrade HINT to eligibility-only or blocked-only because it is HINT.
  N5 must not treat trigger_period=30m as weak/invalid for legal HINT.
  N5 final action_mark is written only when the unified action rule passes.
  Candidate mark must be preserved:
    BUY_HINT -> trigger_mark_candidate=30m_volume
    SELL_HINT -> trigger_mark_candidate=30m_shrink
    ordinary BUY/SELL -> trigger_mark_candidate=normal unless the action rule proves otherwise.
```

If corrected rules still produce `ActionExecuted=0`, the run may only be accepted with per-row deterministic proof showing which unified action-rule field failed for every row. A bare closeout with `price_confirmation_failed=all rows` is not enough.

## 3. Root Causes To Prove Or Disprove

### RC1: N4 ordinary BUY/SELL formal trigger path is missing or bypassed

Current evidence points to `src/ashare_v3/trigger/projection_matcher.py` evaluating projection candidates only. Ordinary BUY/SELL rows that should preserve formal `Y/Q/M/W/D` periods are emitted as `TriggerPendingMarketData`.

The repair must decide and implement one of these paths:

```text
Preferred:
  Add/repair formal BUY/SELL matcher for ordinary condition rows.
  Ordinary TriggerMatched must retain:
    trigger_period in Y/Q/M/W/D
    primary_trigger_period in Y/Q/M/W/D
    all_trigger_periods containing formal periods
    trigger_mark_candidate=normal unless a valid 30m action mark is separately proven

Minimum if full ordinary matcher cannot be completed safely:
  Ordinary pending states must retain formal period metadata and explicit blocker reasons.
  They must not be persisted as trigger_period=30m with empty formal fields.
  Dashboard/closeout must explicitly state ordinary BUY/SELL not completed.
```

### RC2: N5 treats HINT differently from ordinary buy/sell actions

Search and verify:

```text
src/ashare_v3/action/dry_run.py
src/ashare_v3/action/execute.py
src/ashare_v3/action/event_factory.py
src/ashare_v3/events/models.py
tests/test_action_dry_run.py
tests/test_action_execute.py
tests/test_action_event_contract.py
```

The repair must ensure:

```text
TriggerMatched + n5_entry_allowed=true -> unified action confirmation path
TriggerPendingMarketData -> no-op / quality-only
TriggerStateChanged -> no action confirmation
condition_key=BUY_HINT/SELL_HINT does not force ActionEligible or ActionBlocked
legal HINT 30m does not fail merely because trigger_period=30m
```

### RC3: N3 metric joins are object-level rather than trigger-time aligned

Previous investigation found metric join coverage can be `122/122` while using a 15:00 metric for triggers that happened earlier. This is not enough.

The repair must make N3/N5 metric linkage deterministic by trigger evidence:

```text
required join dimensions:
  source_trigger_run_id
  source_trigger_match_id or source_trigger_event_id
  asset_kind
  identity_key
  direction
  condition_key
  trigger_time or closed minute label aligned to trigger_time
  metric_run_id

forbidden as sole join:
  asset_kind + identity_key + trade_date + metric_run_id
```

Acceptance:

```text
metric coverage means trigger-row coverage, not just object coverage.
metric_time must be compatible with trigger_time.
using 15:00 metric for early trigger rows must be blocked or explicitly classified as closeout-only replay, not live action proof.
```

## 4. Repair Scope

Allowed to modify:

```text
src/ashare_v3/trigger/projection_matcher.py
src/ashare_v3/trigger/projection_matcher_execute.py
src/ashare_v3/trigger/v4_enforcement.py
src/ashare_v3/market/action_confirmation_projection_plan.py
src/ashare_v3/market/projection_enrichment_v4_materialization_execute.py
src/ashare_v3/action/dry_run.py
src/ashare_v3/action/execute.py
src/ashare_v3/action/event_factory.py
src/ashare_v3/events/models.py
scripts/*n3*action*metric*.py
scripts/*trigger*projection*.py
scripts/*action_consumer*.py
scripts/*n6_projection*.py
tests/test_n3*.py
tests/test_trigger_projection_matcher*.py
tests/test_n4_v4_enforcement.py
tests/test_action*.py
tests/test_20260608*.py
docs/*.md
docs/*.json
sql/*20260608*.sql
```

Do not touch:

```text
/Users/chuanfuchen/stock_monitor_isolated
/Users/chenchuanfu/stock_monitor_isolated
old monitor.db
old LaunchAgent
old 8866/8868/8869/8871 services
real-trade integrations
long-running workers
delivery/push/voice/mobile execution
sim/order/trade/position/PnL execution
```

The old Excel file is allowed as a read-only reference:

```text
/Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx
```

## 5. Execution Sequence For Fresh Session

### Task 1: Read-only breach review

- Read `AGENTS.md`, `docs/Architecture.md`, `docs/Roadmap.md`, `docs/Tasks.md`, `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`, `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`, `docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md`, and `docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md`.
- Parse `/Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx`.
- Query live v3 lineage for 20260608 until 15:00:
  - N3 C1/B2/action-confirmation metric.
  - N4 `common_trigger_state`, `common_trigger_match`, N4 outbox.
  - N5 `common_action_run`, action facts/events/outbox.
  - N6 projection/card rows.
- Generate:

```text
docs/N5_UNIFIED_BUY_SELL_ACTION_RULE_PARITY_REVIEW.md
docs/N5_UNIFIED_BUY_SELL_ACTION_RULE_PARITY_REVIEW.json
```

Required classification:

```text
current_closeout_classification = NOT_ACCEPTED_AS_FINAL_ACTION_RESULT
blocker = unified_buy_sell_action_rule_and_metric_time_alignment_not_proven
```

### Task 2: Write failing tests

Add regression tests before code changes.

Required tests:

```text
N4 ordinary BUY:D / SELL:D matched plans preserve formal periods.
N4 ordinary pending states do not erase formal period metadata.
N4 HINT matched remains legal with trigger_period=30m and empty formal period arrays.
N5 legal BUY_HINT 30m and ordinary BUY:D both enter the same action confirmation path.
N5 does not force HINT into eligibility-only or blocked-only.
N5 metric join rejects object-only metric coverage when trigger_time does not align.
N5 metric join accepts trigger-row/time-aligned metric coverage.
N5 final action_mark is set to 30m_volume / 30m_shrink only after unified confirmation passes.
TriggerPendingMarketData remains no-op / quality-only.
```

Suggested files:

```text
tests/test_trigger_projection_matcher.py
tests/test_trigger_projection_matcher_execute.py
tests/test_n4_v4_enforcement.py
tests/test_action_dry_run.py
tests/test_action_execute.py
tests/test_action_event_contract.py
tests/test_20260608_unified_action_rule_parity.py
```

### Task 3: Repair N4 trigger semantics

Implement or repair the formal ordinary trigger path.

Hard requirements:

```text
ordinary BUY/SELL/FULL TriggerMatched:
  trigger_kind=trigger
  trigger_period in Y/Q/M/W/D
  primary_trigger_period in Y/Q/M/W/D
  all_trigger_periods contains formal periods
  n5_entry_allowed=true
  trigger_price not null
  trigger_mark_candidate=normal unless a valid action mark candidate is separately proven

HINT TriggerMatched:
  trigger_kind=hint
  trigger_period=30m
  primary_trigger_period=null
  all_trigger_periods=[]
  n5_entry_allowed=true
  trigger_price not null
  trigger_mark_candidate=30m_volume / 30m_shrink

ordinary pending:
  must not be persisted as trigger_period=30m with empty formal fields unless it is explicitly a projection-only blocker with preserved formal trace.
```

### Task 4: Repair N3 action-confirmation metric alignment

Metric materialization and N5 deterministic join must be trigger-row/time aligned.

Hard requirements:

```text
metric rows are linked to source TriggerMatched rows.
coverage target counts TriggerMatched rows, not objects only.
metric_time must align with trigger_time / latest closed minute relevant to the trigger.
15:00 metric cannot silently confirm or block 09:43 trigger rows unless the run is explicitly closeout-replay and documented.
```

Generate or update N3 artifacts and rollback SQL as needed.

### Task 5: Repair N5 unified action rule

Hard requirements:

```text
All TriggerMatched rows use the same N5 action confirmation rule.
HINT is condition provenance only.
ordinary BUY/SELL/FULL and HINT share:
  metric-aware confirmation path
  ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped state machine
  rollback and event contract

ActionExecuted only when unified confirmation passes.
ActionBlocked only with deterministic failure reason.
ActionEligible only when confirmation is legitimately pending or intentionally deferred.
```

### Task 6: Scoped rollback of invalid downstream rows

Before rerun, roll back invalid scoped N6/N5 rows in reverse order.

Possible invalid scoped runs include:

```text
user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry
action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
```

If N4/N3 metric rows are invalid after repair, regenerate downstream-aware rollback SQL and roll back in reverse dependency order:

```text
N6 -> N5 -> N4 -> N3 metric
```

Rollback rules:

```text
hard-fail before first DELETE/UPDATE
guard delivered/delivering outbox rows
guard downstream refs
delete only scoped rows
preserve N1/N2 facts
preserve old system
no CASCADE/DROP/TRUNCATE
```

### Task 7: Regenerate and rerun scoped 20260608 chain

After repairs and rollback safety:

```text
N3 metric contract/dry-run/preflight/final gate
N3 metric execute
N3 metric post-review
N4 trigger contract/dry-run/preflight/final gate
N4 trigger execute
N4 trigger post-review
N5 unified action contract/dry-run/preflight/final gate
N5 execute
N5 post-review
N6 shadow projection contract/dry-run/preflight/final gate
N6 execute
N6 post-review
final closeout/dashboard registration
```

The new session is authorized to generate the gate artifacts and execute them, but must stop for true P0 safety blockers such as delivered outbox, downstream real-trade refs, missing rollback safety, or old system access.

### Task 8: Final validation

Must pass:

```text
JSON parse for all generated reports
live DB row count proof
old Excel parity comparison proof
N4 ordinary/HINT trigger semantic proof
N3 metric trigger-time alignment proof
N5 unified action semantic proof
N6 projection proof
rollback static checks
python3 -m compileall scripts src tests
targeted unittest for N3/N4/N5/N6 repairs
full unittest discover if feasible
git diff --check
```

## 6. Acceptance Criteria

The final result may be accepted only if all are true:

```text
N4 no longer treats all ordinary BUY/SELL as 30m pending_market_data.
N4 ordinary formal triggers preserve Y/Q/M/W/D fields.
N4 HINT triggers preserve legal 30m semantics and trigger_mark_candidate.
N5 uses one unified action rule for all buy/sell TriggerMatched.
N5 does not special-case HINT into non-executable behavior.
N5 metric join is trigger-row/time aligned.
N5 ActionExecuted / ActionBlocked / ActionEligible distribution is recomputed under corrected rules.
If ActionExecuted remains 0, every row has deterministic per-period proof and old-system parity exceptions are listed.
N6 projects only the corrected N5 result.
No outbox is consumed or updated unless explicitly part of scoped run-once contract.
No worker, delivery, push, voice, mobile, sim, position, proposal, order, trade, real trade, or old-system touch.
```

## 7. Fresh Session Prompt

Paste the following into a fresh Codex session.

```text
layer_role=runtime_control

用户显式授权本会话作为一次性跨层修复会话：
- 允许在本会话内对 N3_market_data / N4_trigger / N5_action / N6_user 相关代码、测试、docs、sql artifacts 做必要修复。
- 允许按 scoped gate 执行必要的 N6->N5->N4->N3 rollback SQL、重新生成 contract/dry-run/preflight/final gate artifacts，并执行 scoped N3/N4/N5/N6 run-once。
- 允许中途遇到代码/SQL/contract/test blocker 时自行进入 repair gate、补测试、修代码、重跑验证，不要反复要求用户切换会话。
- 仍然禁止：旧系统 DB/服务、长期 worker、真实交易、delivery/push/voice/mobile、sim/order/trade/position/PnL、N5 outbox consumption、非 scoped 写入。
- 如遇 delivered/delivering outbox、真实下游交易/position refs、rollback 不安全、旧系统访问需求等 P0 安全问题，必须停止并报告 BLOCKED。

进入 N5_UNIFIED_BUY_SELL_ACTION_RULE_ONE_SHOT_REPAIR_GATE。

目标：
一次性修复 20260608 v13 index-all ActionExecuted=0 的动作层语义问题。当前结果不能被接受为 final action result，因为 v3 当前 15:00 closeout 只证明了 HINT 30m projection 链路被 N5 全部 ActionBlocked，没有证明所有买卖动作按统一 N5 动作规则处理。

必须读取：
- AGENTS.md
- docs/Architecture.md
- docs/Roadmap.md
- docs/Tasks.md
- docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
- docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
- docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md
- docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md
- docs/N5_UNIFIED_BUY_SELL_ACTION_RULE_REPAIR_PLAN.md
- /Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx

核心语义：
1. BUY_HINT / SELL_HINT 是买卖信号条件，不是用户提示动作类型。
2. HINT 的特殊性只在 N4 触发证据：
   - BUY_HINT 需要 30m 放量 projection 确认。
   - SELL_HINT 需要 30m 缩量 projection 确认。
3. 一旦 N4 输出 TriggerMatched 且 n5_entry_allowed=true，N5 必须按统一动作层规则处理。
4. 所有买卖动作共用一套 N5 action confirmation rule。
5. 30m_volume / 30m_shrink 是动作标记候选；final action_mark 只有统一动作确认通过后才能写。
6. N5 不得因为 condition_key=BUY_HINT/SELL_HINT 或 trigger_period=30m 就固定 ActionEligible/ActionBlocked/非执行。

先做只读 breach review：
- 解析 /Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx，只读，不读取旧系统 monitor.db。
- 复核老系统普通 B_BUY/S_SELL 动作口径：
  rows、unique objects、D/W/M/Y 周期、condition_key、trigger_time、action_time、是否实际动作、是否提示、detail 里的 trigger_period/primary/all periods。
- 复核 v3 20260608 until 15:00 live lineage：
  N3 C1/B2/action-confirmation metric
  N4 common_trigger_state/common_trigger_match/outbox
  N5 common_action_run/action_fact/action_event/outbox
  N6 projection/card
- 生成：
  docs/N5_UNIFIED_BUY_SELL_ACTION_RULE_PARITY_REVIEW.md
  docs/N5_UNIFIED_BUY_SELL_ACTION_RULE_PARITY_REVIEW.json

必须重点证明/修复：
1. N4 普通 BUY/SELL/FULL 是否被错误写成：
   trigger_period=30m
   primary_trigger_period=null
   all_trigger_periods=[]
   current_status=pending_market_data
   common_trigger_match=0
2. N4 HINT TriggerMatched 是否合法保留：
   trigger_period=30m
   trigger_mark_candidate=30m_volume / 30m_shrink
   trigger_price not null
   n5_entry_allowed=true
3. N5 是否对所有 TriggerMatched 使用同一 action confirmation rule。
4. N5 是否存在 HINT 特殊降级逻辑。
5. N3 metric / N5 deterministic join 是否只是 object-level coverage，而不是 trigger-row/time-aligned coverage。
6. 为什么当前 122 条全部 price_confirmation_failed，是否使用 15:00 metric 覆盖早盘 trigger_time。

修复要求：
- 使用 TDD，先写失败测试再改代码。
- 修 N4：
  ordinary BUY/SELL/FULL formal trigger path 必须保留 Y/Q/M/W/D 周期字段；不得全被写成 30m pending_market_data。
  HINT 30m 合法规则保持。
- 修 N3/N5 metric join：
  coverage 必须是 TriggerMatched row coverage，不只是 asset object coverage。
  metric_time 必须与 trigger_time / relevant closed minute 对齐。
  不允许只用 asset_kind+identity_key+trade_date+metric_run_id 作为最终动作确认 join。
- 修 N5：
  所有 TriggerMatched 进入统一动作规则。
  HINT 不得特殊降级。
  TriggerPendingMarketData 仍 no-op / quality-only。
  ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped 必须由统一动作规则产生。

执行路线：
1. 完成 parity review。
2. 写并跑失败测试。
3. 修 N4/N3/N5/N6 代码与 contracts。
4. 生成/修复 rollback SQL，必须 hard-fail before DELETE/UPDATE，guard delivered/delivering/downstream refs。
5. 对当前错误 scoped rows 按 N6 -> N5 -> N4 -> N3 metric 的依赖顺序评估并必要 rollback。
6. 重新生成 20260608 until 15:00 scoped N3 metric / N4 / N5 / N6 contract, dry-run, preflight, final gate review。
7. 执行 scoped N3/N4/N5/N6 run-once。
8. 生成 post-review 和 final closeout/dashboard。

验收：
- JSON parse PASS
- old Excel parity proof PASS
- live DB proof PASS
- N4 ordinary/HINT semantic proof PASS
- N3 metric trigger-time alignment proof PASS
- N5 unified action rule proof PASS
- N6 projection proof PASS
- rollback static checks PASS
- compileall PASS
- targeted unittest PASS
- git diff --check PASS

最终输出：
- REPAIR_COMPLETE / BLOCKED
- root cause
- files changed
- tests run
- rollback operations executed, if any
- final N4 TriggerMatched distribution
- final N5 ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped distribution
- explanation if ActionExecuted remains 0, with per-row deterministic failure summary
- forbidden scope proof
```

