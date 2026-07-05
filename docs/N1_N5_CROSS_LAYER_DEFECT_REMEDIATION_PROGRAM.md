# N1-N5 Cross-Layer Defect Remediation Program

- result: `PROGRAM_PASS`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T21:42:00+08:00`
- source audit:
  - [N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.md](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.md)
  - [N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.json)

## Program Scope

This gate converts the 7 audit findings into a layer-safe remediation queue. It does not execute N1-N5 commands, write the database, consume/update outbox, start workers, run rollback, enter N6 implementation, generate proposal/order/trade, update position/PnL, or submit real trade.

The target end state remains: rerun `N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT` and reach `P0/P1/P2=0/0/0`, or explicitly register remaining blockers with owner layer, gate, forbidden scope, rollback-safe proof, and no false PASS artifacts.

## Summary

- findings to remediate: `7`
- P0: `2`
- P1: `3`
- P2: `2`
- runtime_control docs-only closed: `3`
- N4_trigger required: `2`
- N5_action required: `2`

## Progress

Closed by `runtime_control`:

- `N1N5-P0-002`: [N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR.json), `REPAIR_PASS`
- `N1N5-P1-003`: [N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION.json), `SUPERSESSION_PASS`
- `N1N5-P2-001`: [AGENTS_STATUS_STUB_REFRESH.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/AGENTS_STATUS_STUB_REFRESH.json), `REFRESH_PASS`

Remaining findings:

- `N1N5-P0-001`
- `N1N5-P1-001`
- `N1N5-P1-002`
- `N1N5-P2-002`

Next required layer/gate:

```text
layer_role=N5_action
N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE
```

## Repair Sequence

### 1. N1N5-P0-001

- owner_layer: `N5_action`
- gate: `N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE`
- purpose: Resolve the contradiction where N5 execute report is `EXECUTED` while nested baseline quality has `P0 failed`.
- runtime_control can fix directly: `false`
- required layer_role: `N5_action`
- expected outputs:
  - reconciled N5 execute report or supersession artifact
  - readonly DB proof for action_run/action_event/inbox/checkpoint/outbox
  - quality `p0_count` aligned with final result semantics
  - rollback status confirmed without executing rollback

### 2. N1N5-P0-002

- owner_layer: `runtime_control`
- gate: `N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR_GATE`
- purpose: Register that N4 corrected post-review was a point-in-time proof and is now superseded by N5 downstream refs.
- runtime_control can fix directly: `true`
- expected outputs:
  - N4/N5 downstream ref registration artifact
  - stale N4 `N5_N6_refs=0` proof marked point-in-time / superseded
  - rollback decisions blocked from using stale downstream=0 proof
  - fresh readonly DB proof

### 3. N1N5-P1-001

- owner_layer: `N4_trigger`
- gate: `N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_GATE`
- purpose: Decide whether v4-required fields must live in `common_trigger_match` facts/raw_json or are event-payload-only.
- runtime_control can fix directly: `false`
- required layer_role: `N4_trigger`
- expected outputs:
  - explicit storage policy
  - contract/test/report alignment
  - if schema/raw_json persistence is required: separate N4 implementation gate
  - if payload-only is accepted: post-review wording repair

### 4. N1N5-P1-002

- owner_layer: `N5_action`
- gate: `N5_CHECKPOINT_ROWCOUNT_ALIGNMENT_GATE`
- purpose: Split N5 checkpoint accepted-event count from physical checkpoint row count.
- runtime_control can fix directly: `false`
- required layer_role: `N5_action`
- expected outputs:
  - contract/preflight/report terminology repair
  - physical checkpoint rows=`73` proof
  - accepted event count=`605` proof
  - rollback guard semantics unchanged

### 5. N1N5-P1-003

- owner_layer: `runtime_control`
- gate: `N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION_GATE`
- purpose: Mark the old `1537`-row `DRY_RUN_BLOCKED` artifact as historical/superseded by the corrected `605`-row chain.
- runtime_control can fix directly: `true`
- expected outputs:
  - supersession registry artifact
  - old blocker preserved as historical evidence
  - successor N4/N5 run ids recorded
  - next audit no longer treats the old blocker as current state

### 6. N1N5-P2-001

- owner_layer: `runtime_control`
- gate: `AGENTS_STATUS_STUB_REFRESH_GATE`
- purpose: Remove or refresh stale operational status in `AGENTS.md` while preserving hard rules.
- runtime_control can fix directly: `true`
- expected outputs:
  - `AGENTS.md` status stub points to `Architecture.md` / `Roadmap.md` / `Tasks.md`
  - no runtime rules weakened
  - project-rule refresh artifact

### 7. N1N5-P2-002

- owner_layer: `N4_trigger`
- gate: `N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_GATE`
- purpose: Fence the legacy `projection_matcher_execute` route so it cannot be selected for current v4 corrected flows.
- runtime_control can fix directly: `false`
- required layer_role: `N4_trigger`
- expected outputs:
  - legacy route marker/fence
  - tests proving current 20260605 v4 corrected gates do not select `projection_matcher_execute`
  - no historical evidence rewritten

## Owner Summary

- runtime_control docs-only closed:
  - `N1N5-P0-002`
  - `N1N5-P1-003`
  - `N1N5-P2-001`
- N4_trigger:
  - `N1N5-P1-001`
  - `N1N5-P2-002`
- N5_action:
  - `N1N5-P0-001`
  - `N1N5-P1-002`

## First Segment Prompt

```text
layer_role=N5_action。

进入 N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE。

目标：
修复 N1_N5 cross-layer audit finding N1N5-P0-001。

依据：
- docs/N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.md
- docs/N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT.json
- docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json
- docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json
- docs/N5_ACTION_PIPELINE_EXECUTE_PREFLIGHT.json
- sql/N5_repaired_context_action_pipeline_20260605_rollback.sql

目标 run：
- source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1

问题：
N5 execute report 最终 result=EXECUTED，且 live DB 有 action_run/action_event/inbox/checkpoint/outbox；
但 report 内部 baseline_comparison explainable=false，且 nested quality 中
n5_5_read_event_count_matches_n5_1_baseline 为 P0 failed。

要求：
- 只读优先
- 不 execute
- 不写数据库
- 不消费/update outbox
- 不启动 worker
- 不 rollback
- 不进入 N6
- 不 proposal/order/trade
- 不 position/PnL
- 不 real trade

请复核：
1. final result 与 nested quality P0 failed 是否矛盾。
2. baseline_read_event_count=0 / current_read_event_count=605 的来源。
3. 是否应修 contract/preflight/report artifact，还是登记 supersession。
4. live DB action_run/action_event/inbox/checkpoint/outbox proof。
5. rollback SQL 是否仍 safe before N6/downstream consumption。
6. 是否允许进入 artifact repair implementation gate。

输出：
- RECONCILIATION_PASS / BLOCKED
- root cause
- required artifact repairs
- live DB proof
- rollback proof
- forbidden scope proof
- next gate
```

## Final Acceptance

The remediation program is complete only when a fresh `N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT` can prove `P0/P1/P2=0/0/0`, or every remaining blocker is explicitly registered with owner layer, gate, forbidden scope, rollback-safe proof, and no false PASS artifacts.
