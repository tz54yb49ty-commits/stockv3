# N4 Trigger Rule Spec v4 Approved Changes

Status: APPROVED_CHANGES_FREEZE_PASS

Layer role: `runtime_control`

Date: 2026-06-03

Scope: Freeze the runtime_control `APPROVED_WITH_CHANGES` decision for `docs/N4_TRIGGER_RULE_SPEC_v4.md`, assign field ownership, and define the allowed next gates. This artifact does not authorize N4 matcher changes, database writes, execute, N5/N6 implementation, outbox consumption, worker startup, delivery, notification, voice, mobile, sim, position, or real trade.

## 1. Freeze Decision

`N4_TRIGGER_RULE_SPEC_v4` is approved only as a contract-alignment and dry-run implementation target.

```text
review_result = APPROVED_WITH_CHANGES
freeze_result = APPROVED_CHANGES_FREEZE_PASS
spec_version_required = N4_TRIGGER_RULE_SPEC_v4
policy_hash_required = true
independent_run_id_required = true
historical_run_reinterpretation = forbidden
execute_authorized = false
database_write_authorized = false
matcher_change_authorized_by_runtime_control = false
N5_N6_implementation_authorized = false
```

Required correction to the frozen draft:

```text
Original draft wording:
  N4 只输出 n5_entry_allowed

Approved wording:
  N4 outputs standard trigger events and carries n5_entry_allowed as an outcome payload/fact guard.
```

## 2. Required Changes

The following changes are mandatory before any v4 execute final gate:

- Add and require `trigger_rule_spec_version=N4_TRIGGER_RULE_SPEC_v4`.
- Add and require a deterministic `trigger_rule_policy_hash`.
- Use an independent v4 `run_id`; old runs must not be silently interpreted as v4.
- Refresh N4 v4 dry-run, execute contract, execute preflight, event payload contract, and rollback artifacts.
- Refresh N5 v4 entry contract and source allowlist guard.
- Add N6 v4 display compatibility note; N6 must not directly reinterpret N4 raw fields.
- Fix the draft wording around `n5_entry_allowed` so it is a guard on standard events, not an event replacement.
- Enforce N5 entry as `TriggerMatched + B_BUY/S_SELL + matched + trigger_live=true + n5_entry_allowed=true`.
- Ensure `TriggerPendingMarketData`, `TriggerStateChanged`, `no_op`, `quality_blocked`, and `inactive` never create N5 action confirmation.
- Freeze the outcome severity matrix for `matched`, `pending_market_data`, `no_op`, `quality_blocked`, and `inactive`.
- Confirm or block `BUY:FULL / SELL:FULL` semantics before any FULL matched execute.
- Prove v3-v4 backtest/diff before execute.
- Use rollback SQL with hard-fail guards before DELETE for every v4 execute artifact.

## 3. Recommended Changes

Recommended but not strictly required for the first v4 dry-run:

- Start with `payload_json` / `raw_json` compatibility before additive columns.
- Add `evidence_completeness_status`.
- Add `no_op_reason`.
- Add `pending_reason`.
- Add `quality_block_reason`.
- Add `compatibility_mode=false`.
- Add dashboard/report dimensions for `trigger_kind`, `primary_trigger_period`, `n5_entry_allowed`, `no_op`, and `quality_blocked`.

## 4. Field Owner Matrix

| Field / concept | Owner | Decision |
|---|---|---|
| `condition_key` | N2 | N2 condition provenance. N4 reads local context only. |
| `original_condition_key` | N2 -> N4 payload | N2 owns provenance; N4 preserves it in payload. |
| `allowed_signal_types` / selected condition signal | N2 | N2 owns canonical condition semantics. |
| `period_trigger_baseline_json` | N2 | N2 computes and freezes. N4 localizes and consumes. |
| `previous_transition` | N2 context enrichment | Must be provided by N2-localized context for Y/Q/M/W/D. N4 does not infer from raw K. |
| `previous_entity_high` / `previous_entity_low` | N2 context enrichment | N2 context should provide or localize from frozen previous open/close trace. |
| `previous_amount_baseline` | N2 context enrichment | N2 context must provide per-period amount baseline trace. |
| `trigger_amount_chain_pass` | N2/N3 enrichment, not N4 | Must be provided as standardized context/projection/metric field. N4 must not补算. |
| `current_price_or_close` | N3 market fact | N3 owns snapshot/projection/closed metric current value. |
| `current_amount_metric` | N3 projection/enrichment | N3 owns current standardized amount metric if derived from live/projection/closed summary. |
| `transition_amount_pass` | N4 from standard fields | N4 may judge from N2 baseline and N3 current standard fields. If required source fields are absent, block/pending; do not raw-calculate. |
| `current_transition` | N4 from standard fields | N4 may judge using N2/N3 standard fields only. N3 may optionally provide trace, but N4 owns final trigger transition decision. |
| `trigger_kind` | N4 | N4 assigns `trigger` or `hint` from condition provenance. |
| `triggered_periods` | N4 | N4 derives from v4 trigger decision. |
| `all_trigger_periods` | N4 | N4 derives from same-day trigger state. |
| `primary_trigger_period` | N4 | N4 derives from `all_trigger_periods` with Y > Q > M > W > D. |
| `projection_period` / `projection_30m_type` | N3 evidence, N4 payload | N3 owns projection evidence. N4 carries it. |
| `trigger_mark_candidate` | N4 | N4 owns non-final mark candidate. |
| `n5_entry_allowed` | N4 | N4 owns N5 entry guard. |
| `action_state` | N5 | N5 owns action confirmation state. |
| final `action_mark` | N5 | N5 owns final mark after action confirmation. |
| user display / alert / voice / mobile / sim / trade intent | N6 | N6 owns user-facing interpretation. |

## 5. Owner Decisions For重点字段

### previous_transition

Decision: `previous_transition` is a required N2 context enrichment for Y/Q/M/W/D.

Rationale:

- It is a historical/static period-state baseline.
- N4 must not回查 N1 daily or aggregate raw K.
- N3 projection is not the owner of historical Y/Q/M/W/D transition state.

If missing:

```text
blocked_by_layer = N2_condition
required_gate = N2 context enrichment gate
```

### current_transition

Decision: N4 owns the final `current_transition` judgment, but it may only use N2/N3 standardized fields.

Allowed inputs:

```text
N2 previous entity/amount baseline
N3 current price/amount/projection/closed metric
N3 action-confirmation metric when applicable
```

N3 may provide a suggested trace field, but N4 remains the trigger decision owner.

### transition_amount_pass

Decision: N4 may judge `transition_amount_pass` from standard N2/N3 fields.

If the standardized source fields are absent, N4 must not补算 from raw K. It must emit `pending_market_data` or `quality_blocked` according to contract severity.

### trigger_amount_chain_pass

Decision: `trigger_amount_chain_pass` must be provided by N2/N3 enrichment. N4 must not calculate it.

If missing for a condition where v4 requires it:

```text
ordinary BUY/SELL = pending_market_data or quality_blocked by severity matrix
FULL = BLOCKED until FULL semantics and source ownership are finalized
```

### BUY:FULL / SELL:FULL

Decision: continue BLOCKED for v4 execute until FULL semantics are clarified.

Open choices:

```text
A. FULL means N2 proves full structure and N4 only checks D current transition.
B. FULL means all required Y/Q/M/W/D chain conditions must be satisfied.
C. FULL is a separate condition family with independent N2 context fields and N4 matcher.
```

Until the choice is finalized, v4 dry-run may report FULL candidates, but v4 execute must not write FULL `TriggerMatched`.

## 6. N2 Context Enrichment Needed

N2 context enrichment is required for:

- `previous_transition` per Y/Q/M/W/D.
- `previous_entity_high` / `previous_entity_low` per Y/Q/M/W/D.
- `previous_open` / `previous_close` trace if high/low are not materialized.
- `previous_amount_baseline` per Y/Q/M/W/D.
- `amount_metric` source policy.
- `trigger_amount_chain_pass` or the standardized source fields used to produce it.
- FULL prerequisite trace and `quality_status`.
- HINT prerequisite trace and `quality_status`.
- `baseline_ready` and source freshness indicators.

If these are absent, N4 must stop and hand off:

```text
blocked_by_layer = N2_condition
```

## 7. N3 Projection Enrichment Needed

N3 projection / market-data enrichment is required for:

- `current_price_or_close`.
- `current_amount_metric`.
- Standardized 30m projection fields for HINT:
  - `projection_period=30m`
  - `projection_30m_type=volume_up/shrink_down/none`
  - current 30m bucket virtual amount
  - previous/reference 30m amount
  - current 30m price/reference entity boundary
  - projection quality / lineage trace
- N3 closed summary facts for replay or stronger confirmation.
- N3 action-confirmation metric facts if v4 matcher consumes them as standardized evidence.

If these are absent:

```text
blocked_by_layer = N3_market_data
```

## 8. N4 Standard-Field Judgments

N4 may judge only these fields from standard N2/N3 inputs:

- `current_transition`.
- `transition_amount_pass`.
- `matched / pending_market_data / no_op / quality_blocked / inactive`.
- `trigger_kind`.
- `triggered_periods`.
- `all_trigger_periods`.
- `primary_trigger_period`.
- `trigger_mark_candidate`.
- `n5_entry_allowed`.

N4 may not judge from raw K, N1 daily, external market calls, ad hoc period aggregation, qfq/hfq recomputation, or N2 condition recomputation.

## 9. N5 Entry Contract

N5 action confirmation may start only when all conditions are true:

```text
event_type = TriggerMatched
signal_type in (B_BUY, S_SELL)
current_status = matched
trigger_live = true
n5_entry_allowed = true
source_run_id allowlist passed
event_schema_version / trigger_rule_spec_version is v4-compatible
```

N5 must reject:

```text
TriggerPendingMarketData
TriggerStateChanged
no_op
quality_blocked
inactive
```

N5 must also reject any malformed event where `n5_entry_allowed=true` appears on a non-`TriggerMatched` event.

## 10. Outcome Severity Matrix

| Outcome | Writes outcome outbox | Writes state change | N5 entry | Default severity |
|---|---:|---:|---:|---|
| `matched` | yes: `TriggerMatched` | yes if material state changes | yes | P0=0 |
| `pending_market_data` | yes: `TriggerPendingMarketData` | yes if material state changes | no | P1 unless required evidence is contract-critical |
| `no_op` | no by default | yes only if previous state becomes inactive | no | metrics-only |
| `quality_blocked` | P0: no; P1/P2: contract decides pending or no outbox | optional by severity | no | by reason |
| `inactive` | state event only | yes | no | state transition |

Quality severity defaults:

| Reason | Severity |
|---|---|
| identity conflict | P0 |
| asset_kind channel mismatch | P0 |
| source_run_id not allowlisted | P0 |
| N2/N3 lineage mismatch | P0 |
| baseline missing for required signal | P0 |
| baseline_ready=false for required period | P0 or P1 by signal policy |
| amount source stale | P1 by default; P0 if threshold exceeded |
| projection lineage mismatch | P0 |
| projection quality failed | P1 or P0 by signal family |
| optional projection absent for non-HINT | P1/P2 or no_op by contract |

## 11. v3-v4 Compatibility And Backtest Plan

Compatibility rules:

- Old runs remain auditable under their original contract.
- No v4 field may be inferred onto an old run.
- v4 dry-run and execute must use separate run IDs.
- v4 reports must include spec version and policy hash.

Backtest / diff requirements:

```text
v3_trigger_matched_count
v4_trigger_matched_count
v3_pending_market_data_count
v4_pending_market_data_count
v4_no_op_count
v4_quality_blocked_count
trigger_kind_distribution
primary_trigger_period_distribution
n5_entry_allowed_count
invalid_n5_entry_count = 0
BUY matched direction anomaly = 0
SELL matched direction anomaly = 0
BUY amount anomaly = 0
SELL amount anomaly = 0
```

## 12. Allowed Next Gate

Allowed:

```text
N2/N3 context enrichment gate
```

The next gate may decide whether enrichment starts from N2, N3, or both.

Not allowed from this artifact:

```text
N4 matcher implementation
N4 execute
N5 implementation
N6 implementation
database write
outbox consumption
worker
delivery / notification / voice / mobile / sim / position / real trade
```
