# N4 Trigger Rule Spec v4 Implementation Gate Report

Status: **BLOCKED**

Layer role: `N4_trigger`

This gate is read-only for runtime data: no N4 execute, no database business writes, no outbox consumption, no worker, no N5/N6 implementation.

## Source Integrity

- Spec rules parsed: `405` (`N4-001..N4-405` sequential = `True`).
- Traceability expanded coverage: `405` rules (`covers_all_rules=True`).
- Runtime-control `APPROVED_WITH_CHANGES` artifact: **not found** in repo or current attachments.

## Blockers

### missing_runtime_control_approved_with_changes_source

- severity: `P0`
- impacted rules: `N4-296, N4-297, N4-298, N4-300, N4-376, N4-377, N4-385, N4-401, N4-405`
- evidence: Repository and attachments search found no APPROVED_WITH_CHANGES artifact or required-change list for N4_TRIGGER_RULE_SPEC_v4.
- required action: runtime_control must provide the APPROVED_WITH_CHANGES review artifact or explicitly confirm the must-change list in a persisted doc before implementation can be called complete.

### context_missing_v4_transition_and_amount_chain_fields

- severity: `P0`
- impacted rules: `N4-043, N4-047, N4-048, N4-049, N4-050, N4-051, N4-053, N4-054, N4-055, N4-056, N4-057, N4-058 ...`
- evidence: 20260603 context raw_json has period_trigger_baseline_json with entity/amount seeds, but zero rows contain transition_amount_pass, trigger_amount_chain_pass, previous_transition, or current_transition fields.
- required action: Either N2/N4 context rebuild must localize these standardized fields, or N4 v4 Stage 2 must explicitly block before matcher implementation.

### current_dry_run_payload_missing_v4_fields

- severity: `P0`
- impacted rules: `N4-017, N4-018, N4-019, N4-025, N4-026, N4-035, N4-041, N4-245, N4-246, N4-247, N4-248, N4-249 ...`
- evidence: Current sample plans omit trigger_kind, n5_entry_allowed, triggered_periods, projection_period, triggered_period_details, transition_amount_pass, trigger_amount_chain_pass, current_transition, previous_transition, and outcome.
- required action: Implement v4 dry-run payload builder and tests before execute contract can pass.

### ordinary_matcher_not_v4_upgrade_downgrade

- severity: `P0`
- impacted rules: `N4-066, N4-067, N4-068, N4-069, N4-070, N4-071, N4-072, N4-087, N4-088, N4-089, N4-090, N4-091 ...`
- evidence: local_trigger_dry_run.evaluate_ordinary_snapshot_match uses current_price/close > open for BUY and < open for SELL, plus amount baseline; it does not test previous_transition != target state or per-period triggered_periods.
- required action: Replace ordinary matcher with per-period v4 transition matcher after context field readiness is resolved.

### full_semantics_not_safe_to_execute

- severity: `P0`
- impacted rules: `N4-108, N4-109, N4-110, N4-111, N4-112, N4-113, N4-114, N4-115, N4-116, N4-117, N4-118, N4-119 ...`
- evidence: Context has BUY:FULL/SELL:FULL rows, but v4-required D transition_amount_pass and trigger_amount_chain_pass are not localized as explicit facts; current matcher does not enforce N2 FULL precondition + D transition chain under v4.
- required action: Keep FULL execute blocked until Stage 2 context readiness and Stage 3 FULL matcher tests pass.

## Covered Rule Ranges
- N4-001..N4-004 partial: current N4 can read local context/snapshot and emit current event families, but v4 payload incomplete.
- N4-005..N4-016 partial: boundary/no raw market pull covered by existing dry-run side_effect flags and tests, but v4 standardized-field source proof incomplete.
- N4-017..N4-026 partial: signal_type B_BUY/S_SELL and trigger_mark_candidate exist; trigger_kind/n5_entry_allowed missing.
- N4-228..N4-232 partial: TriggerStateChanged dry-run plans exist; no-op/inactive semantics not stable.
- N4-296..N4-300 covered as docs/spec files; runtime_control APPROVED_WITH_CHANGES still missing.
- N4-401..N4-405 covered as principle text; runtime code/contract still incomplete.

## Gap Rule Ranges
- N4-027..N4-032 trigger_kind canonical payload gap
- N4-033..N4-042 triggered_periods/projection_period gap
- N4-043..N4-065 transition_amount_pass / trigger_amount_chain_pass context and matcher gap
- N4-066..N4-107 ordinary BUY/SELL v4 upgrade/downgrade matcher gap
- N4-108..N4-139 FULL matcher execute blocker
- N4-140..N4-191 HINT v4 payload/projection_period/n5_entry_allowed gap
- N4-192..N4-227 no_op/quality_blocked/inactive classification gap
- N4-233..N4-244 N5 entry contract not frozen against v4 fields
- N4-245..N4-295 required payload/state-change detail gap
- N4-301..N4-400 implementation/test/final-gate stages are still planned, not covered

## Schema / Context Impact

- `common_event_outbox` can carry v4 payload in `payload_json`; no N4 event-type blocker found.
- `common_trigger_state` has 024 canonical columns but lacks `trigger_kind`, `n5_entry_allowed`, `triggered_periods`, `triggered_period_details` physical columns.
- `common_trigger_match` has `trigger_mark_candidate` and intentionally does not support `TriggerStateChanged`; it lacks the same v4 semantic columns and would need raw_json or additive columns for outcome audit.
- 20260603 context has `period_trigger_baseline_json` for Y/Q/M/W/D and entity upper/lower fields, but has no explicit `transition_amount_pass`, `trigger_amount_chain_pass`, `previous_transition`, or `current_transition` fields.

## v3-v4 Diff / Backtest

- v3 source artifact: `docs/N4_20260603_local_trigger_dry_run_report.json`.
- v3 counts: `TriggerMatched=1252`, `TriggerPendingMarketData=8915`, `TriggerStateChanged=10167`.
- v4 backtest result: `BLOCKED_NOT_COMPARABLE` because required v4 fields and semantics are absent; computing a v4 count now would be speculative.

## FULL Semantics

`BUY:FULL / SELL:FULL` remain **BLOCKED** for execute. Context rows exist, but v4 requires D transition and amount-chain evidence that is not localized as explicit facts, and current matcher does not enforce FULL-specific N2 precondition + D chain under v4.

## Artifacts

- JSON report: `docs/N4_trigger_rule_spec_v4_implementation_gate_report.json`
- v3-v4 diff JSON: `docs/N4_TRIGGER_RULE_SPEC_v4_v3_v4_diff_backtest.json`
- execute contract draft: `docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json`
- execute preflight draft: `docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json`
- rollback SQL draft: `sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql`
