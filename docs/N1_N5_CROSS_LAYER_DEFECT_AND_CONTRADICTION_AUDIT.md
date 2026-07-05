# N1-N5 Cross-Layer Defect And Contradiction Audit

- result: `BLOCKED`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T21:27:29+08:00`
- scope: N1-N5 code / contracts / tests / docs / SQL / readonly DB proof
- N6 scope: downstream refs proof only; N6 implementation completion was not audited

## Boundary

This audit was read-only. It did not modify code, write the database, execute any runner, consume/update outbox rows, start workers, run rollback SQL, enter N6 implementation, generate proposal/order/trade, update position/PnL, or submit real trade.

## Live Readonly Proof

- target DB: `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`
- DB time: `2026-06-08 21:27:29.207758+08`
- target N4 run: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- `common_trigger_run.status=passed`, generated_by=`trigger_rule_v4_execute`
- N4 rows: state/match/outbox=`605/605/605`
- N4 outbox: `TriggerMatched pending=605`, delivered/delivering=`0/0`
- N5 live refs for target N4 run: `common_action_run=1`, `common_action_event=605`, inbox=`605`, checkpoint refs=`73`
- N5 output distribution: `ActionBlocked=604`, `ActionExecuted=1`
- N5 outbox: pending=`605`
- N6 downstream refs checked against N6 virtual/account/order/trade/position/PnL tables: `0`

## Summary

- P0: `2`
- P1: `3`
- P2: `2`

## Findings

### N1N5-P0-001

- severity: `P0`
- layer: `N5_action`
- location: `docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:517`
- expected: N5 execute report must reconcile to a reviewed final-gate baseline before writing action facts/events.
- actual: The execute report records `writes_performed=true` and `result=EXECUTED`, but its own `baseline_comparison` says `baseline_read_event_count=0`, `current_read_event_count=605`, `same_event_distribution=false`, `explainable=false`; a later nested quality section has `p0_count=1` with `n5_5_read_event_count_matches_n5_1_baseline` failed.
- evidence:
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:517)
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:379)
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:553716)
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:554328)
  - readonly DB proof: `common_action_run=1`, `common_action_event=605` for the same `source_trigger_run_id`
- root_cause: The N5 execute artifact appears to combine a stale or mismatched baseline comparison with a successful execute path, so the final gate lineage cannot be proven from a single consistent contract/preflight/report chain.
- recommended_fix: Run an N5 action pipeline artifact reconciliation gate: regenerate or mark superseded the mismatched baseline fields, bind the execute report to the exact approved final gate, and re-run readonly proof against live rows.
- affected_gate: `N5_ACTION_PIPELINE_EXECUTE_POST_REVIEW_REGISTRATION_GATE`
- safe_next_step: `N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE`

### N1N5-P0-002

- severity: `P0`
- layer: `N4_trigger/N5_action`
- location: `docs/N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json:51`
- expected: Runtime control should not keep an unsuperseded N4 post-review artifact claiming `N5_N6_refs=0` after downstream N5 consumption has happened.
- actual: The N4 corrected execute report says `n5_refs=0`, `inbox_refs=0`, `checkpoint_refs=0`, and `n5_n6_entered=false`; live DB now has inbox=`605`, checkpoint refs=`73`, `common_action_run=1`, and `common_action_event=605` for the same trigger run.
- evidence:
  - [N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json:51)
  - readonly DB proof at `2026-06-08 21:27:29+08`
- root_cause: Post-review artifacts are point-in-time proofs, but the current control plane does not clearly supersede them after downstream stages advance.
- recommended_fix: Add a cross-layer state registration gate that marks N4 corrected post-review as superseded by the N5 action run, records the new downstream refs, and blocks rollback decisions from using stale `N5_N6_refs=0` proof.
- affected_gate: `N4_20260605_V4_CORRECTED_EXECUTE_POST_REVIEW_REGISTRATION_GATE`
- safe_next_step: `N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR_GATE`

### N1N5-P1-001

- severity: `P1`
- layer: `N4_trigger`
- location: `src/ashare_v3/trigger/v4_corrected_execute_contract.py:148`
- expected: N4 v4 TriggerMatched facts and/or their persisted trace should be able to prove `trigger_kind`, `triggered_periods`, `all_trigger_periods`, `primary_trigger_period`, `trigger_live`, `current_status`, `n5_entry_allowed`, and `match_basis`.
- actual: N4 outbox payload has these fields for `605/605` rows, but `common_trigger_match` live storage has none of these fields as columns or `raw_json` keys for `605/605` rows.
- evidence:
  - [v4_corrected_execute_contract.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/v4_corrected_execute_contract.py:148)
  - readonly DB proof: `trigger_kind_raw_present=0`, `triggered_periods_raw_present=0`, `n5_entry_allowed_raw_present=0`, `match_basis_raw_present=0`
- root_cause: The corrected runner persists v4 compliance primarily in event payload, while `common_trigger_match` remains a narrower legacy fact shape.
- recommended_fix: Decide whether v4-required fields must be stored on `common_trigger_match`, in `raw_json`, or explicitly documented as event-payload-only; then align schema/tests/post-review proof accordingly.
- affected_gate: `N4_TRIGGER_RULE_V4_FACT_SCHEMA_ALIGNMENT_GATE`
- safe_next_step: `N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_GATE`

### N1N5-P1-002

- severity: `P1`
- layer: `N5_action`
- location: `docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.md:11`
- expected: Planned write counts for `common_event_consumer_checkpoint` should use the physical row semantics of the checkpoint table, not the source event count.
- actual: Contract/preflight planned `common_event_consumer_checkpoint=605`, but live checkpoint refs for the N5 action run are `73`, matching partition-level upsert behavior.
- evidence:
  - [N5_ACTION_PIPELINE_EXECUTE_CONTRACT.md](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.md:11)
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:252)
  - readonly DB proof: checkpoint refs=`73`
- root_cause: The report uses accepted event count as checkpoint write count even though checkpoint storage is one row per `consumer_name + partition_key + source_layer`.
- recommended_fix: Split N5 checkpoint metrics into `accepted_event_count=605` and `physical_checkpoint_rows=73`; update contract/preflight/report and rollback static checks.
- affected_gate: `N5_ACTION_PIPELINE_CHECKPOINT_COUNT_SEMANTIC_REPAIR_GATE`
- safe_next_step: `N5_CHECKPOINT_ROWCOUNT_ALIGNMENT_GATE`

### N1N5-P1-003

- severity: `P1`
- layer: `N5_action`
- location: `docs/N5_20260605_ACTION_READINESS_DRY_RUN_GATE_REPORT.md:3`
- expected: Blocked dry-run artifacts that are superseded by later corrected runs should be explicitly marked superseded, with the successor run and gate path.
- actual: The dry-run report remains `DRY_RUN_BLOCKED` with `1537` TriggerMatched, FULL=`29`, and metric coverage `0/1537`, while current execute artifacts and live DB use the corrected `605`-row N4 run and N5 action pipeline.
- evidence:
  - [N5_20260605_ACTION_READINESS_DRY_RUN_GATE_REPORT.md](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_20260605_ACTION_READINESS_DRY_RUN_GATE_REPORT.md:3)
  - [N5_ACTION_PIPELINE_EXECUTE_REPORT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json:10)
- root_cause: Historical blocker artifacts are retained without a supersession registry, so runtime_control sees mutually incompatible gate states for the same `source_trigger_run_id`.
- recommended_fix: Create a supersession registry entry linking the blocked `1537`-row dry-run to the corrected `605`-row N4/N5 chain, preserving the old blocker as historical evidence only.
- affected_gate: `N5_20260605_DRY_RUN_BLOCKER_TRIAGE_GATE`
- safe_next_step: `N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION_GATE`

### N1N5-P2-001

- severity: `P2`
- layer: `runtime_control`
- location: `AGENTS.md:23`
- expected: Project-level instructions should avoid stale operational lineage or explicitly defer all live status to Architecture/Roadmap/Tasks.
- actual: `AGENTS.md` says N5 current-real action execute passed on 20260525 lineage and N6 not started, while the active thread and live DB contain 20260605/20260608 N3-N5/N6-related work.
- evidence:
  - [AGENTS.md](/Users/chuanfuchen/Documents/A股监控系统v3/AGENTS.md:23)
  - live target run: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- root_cause: `AGENTS.md` carries a historical status block even though it says `Architecture.md` / `Roadmap.md` / `Tasks.md` are authoritative.
- recommended_fix: Replace the historical status block with a short pointer to current total-control docs, or update it through a dedicated project-rule refresh gate.
- affected_gate: `PROJECT_RULE_STATUS_REFRESH_GATE`
- safe_next_step: `AGENTS_STATUS_STUB_REFRESH_GATE`

### N1N5-P2-002

- severity: `P2`
- layer: `N4_trigger`
- location: `src/ashare_v3/trigger/projection_matcher_execute.py:1364`
- expected: Deprecated N4 projection matcher routes should be fenced so they cannot be mistaken for the current v4 corrected matched-only runner.
- actual: The legacy projection matcher execute implementation still contains inbox writes, outbox upsert, and checkpoint writes, while current 20260605 v4 corrected flow uses a separate runner.
- evidence:
  - [projection_matcher_execute.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/projection_matcher_execute.py:1364)
  - [projection_matcher_execute.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/projection_matcher_execute.py:1702)
  - [projection_matcher_execute.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/projection_matcher_execute.py:1739)
- root_cause: Historical compatibility code remains callable/readable without a strong deprecation fence in the N4 runtime control surface.
- recommended_fix: Add a legacy-route fence/metadata marker and tests that current final gates never select `projection_matcher_execute` for 20260605 v4 corrected flows.
- affected_gate: `N4_LEGACY_PROJECTION_MATCHER_ROUTE_FENCE_GATE`
- safe_next_step: `N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_GATE`

## Positive Proofs

- N5 current execute code only enriches `TriggerMatched`; non-`TriggerMatched` events are continued without action confirmation enrichment: [execute.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/action/execute.py:665).
- Live N5 action run flags show no user/worker/voice/sim/real-trade touch.
- N6 virtual/account/order/trade/position/PnL tables have `0` refs to the target N4/N5 run ids checked in this audit.

## Recommended Remediation Gates

1. `N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE`
2. `N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR_GATE`
3. `N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_GATE`
4. `N5_CHECKPOINT_ROWCOUNT_ALIGNMENT_GATE`
5. `N5_20260605_BLOCKED_ARTIFACT_SUPERSESSION_REGISTRATION_GATE`
6. `N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_GATE`
