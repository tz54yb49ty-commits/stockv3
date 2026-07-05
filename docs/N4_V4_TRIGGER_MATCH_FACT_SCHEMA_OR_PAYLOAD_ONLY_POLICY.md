# N4 v4 Trigger Match Fact Schema Or Payload-Only Policy

Gate: `N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_GATE`

Layer role: `N4_trigger`

Result: `POLICY_PASS`

Finding: `N1N5-P1-001`

## Decision

Recommended policy: `dual_proof`

N4 v4 `TriggerMatched` keeps `common_event_outbox.payload_json` as the canonical cross-layer event protocol proof. N4 also mirrors the v4 required fields into `common_trigger_match.raw_json` at the top level for fact-layer audit, replay, and cross-layer consistency checks.

Payload-only proof is sufficient for N5 consumption semantics, but it is not sufficient as the only N4 fact persistence proof. `common_trigger_match.raw_json` must be able to prove the v4 match fields without requiring an auditor to infer them from a nested legacy `canonical_plan`.

## Required v4 Fact Proof Fields

Future `common_trigger_match.raw_json` rows for v4 `TriggerMatched` must include these top-level keys:

- `trigger_price`
- `trigger_kind`
- `triggered_periods`
- `all_trigger_periods`
- `primary_trigger_period`
- `trigger_live`
- `current_status`
- `n5_entry_allowed`
- `match_basis`

The outbox payload remains the canonical cross-layer input for N5. The match fact raw JSON is the N4-local audit mirror.

## Implementation Scope

No schema migration is required for the current fix because `common_trigger_match.raw_json` already exists.

Implemented future-write behavior:

- `insert_execute_match()` now builds raw JSON through a dedicated helper.
- `common_trigger_match.raw_json` now mirrors the v4 required fields at top level.
- The nested `canonical_plan` is preserved for backward traceability.
- The event outbox payload remains unchanged as the cross-layer canonical proof.

Historical live rows are not rewritten in this gate. The live 605 rows identified by `N1N5-P1-001` remain historical evidence until runtime_control explicitly authorizes a scoped repair or marks the finding closed by policy for future writes only.

## Cross-Layer Audit Interpretation

Audits must no longer treat payload-only proof and fact-schema proof as contradictory categories.

Correct interpretation:

- `common_event_outbox.payload_json`: canonical cross-layer event proof.
- `common_trigger_match.raw_json`: N4-local fact proof mirror for v4 required fields.
- `common_trigger_match` typed columns: legacy and high-use query columns; not the complete v4 proof surface.

For future writes, both payload and raw JSON must prove the v4 required fields. For existing historical rows, any remediation must use a separate scoped repair gate with readonly preflight and rollback.

## Modified Artifacts

- `src/ashare_v3/trigger/standard_trigger_execute.py`
- `tests/test_standard_trigger_execute.py`
- `docs/N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY.md`
- `docs/N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY.json`

## Required Implementation Gate

Future-write implementation: completed in this gate.

Historical live-row remediation, if runtime_control requires the 605 existing rows to be updated instead of accepted as historical evidence, must use a separate gate:

```text
N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```

That gate must not be skipped because it would write existing N4 facts.

## Forbidden Scope Proof

- N4 execute run: not performed
- database writes: not performed
- rollback SQL: not executed
- outbox/inbox/checkpoint consumption or update: not performed
- worker start: not performed
- N5/N6 execution: not entered
- delivery/push/voice/mobile/sim/position/order/trade/real trade: not touched
- old system: not touched

## Next Gate

Return to runtime_control for:

```text
N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_POST_REVIEW_GATE
```

If runtime_control requires live 605-row remediation, route to:

```text
N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```
