# N4 Trigger Atomic Canonical Registration Gate

Status: passed

Gate date: 2026-06-26

Layer role: `N4_trigger`

Mode: FULL MODE

Gate type: documentation-only registration and contract decision

Execution boundary:

```text
code_change = false
schema_migration = false
database_write = false
outbox_write = false
inbox_checkpoint_write = false
execute_n4 = false
execute_n5 = false
execute_n6 = false
worker_started = false
rollback_executed = false
historical_run_overwrite = false
```

Goal:

- Register `docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md` as the only canonical document for N4 trigger-side rule definitions.
- Downgrade old N4 rule-definition ownership in older specs without rewriting historical run meaning.
- Freeze implementation preconditions so the next gate only needs to code and verify.

## A. CANONICAL_DOC_REGISTRATION

Registered canonical document:

```text
path = docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
status = canonical_registered
effective_at = 2026-06-26
layer_role = N4_trigger
owned_scope = N4 trigger-side rule definitions only
```

Owned responsibilities:

```text
BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT atomic trigger rules
period transition definitions
formal amount-chain gate semantics
30m projection type definitions for hint path
TriggerMatched eligibility rules at N4
```

Not-owned responsibilities:

```text
N5 final action confirmation
N6 presentation and user policy
worker scheduling
run orchestration
rollback execution
database runtime authority
```

## B. SUPERSEDED_DOC_REGISTRATION

Superseded ownership decision:

```text
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
  n4_trigger_side_rule_definitions = superseded_for_future_alignment
  retained_scope = N3 projection facts and N5 final action confirmation

docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
  retained_scope = N4/N5 state flow and cross-layer boundary semantics
  n4_trigger_side_rule_definitions = not_authoritative
```

Registration rule:

```text
historical reports, tests, SQL drafts, and execute artifacts that cite old docs remain valid historical evidence
future N4 rule alignment must not use the superseded docs as primary rule-definition source
```

## C. TRIGGERSTATECHANGED_BOUNDARY_DECISION

Decision:

```text
TriggerStateChanged may be consumed by N5 active-monitor v2 as state-gate input
TriggerStateChanged(trigger_live=true,current_status=matched) may refresh an executable active ref
TriggerStateChanged(trigger_live=false) may expire/remove a matching active ref
TriggerStateChanged is not an action confirmation entry
```

Allowed N5 uses only:

```text
update_context
expire_window
live/state synchronization
active_ref_refresh with action_eligible_entry_allowed=false
```

Forbidden N5 uses:

```text
create ActionEligible
directly create ActionExecuted without matching N3T_C1_CLOSED proof
create action confirmation fact
act as substitute for TriggerMatched
```

Implementation consequence:

```text
N4 may continue to emit TriggerStateChanged
N5 consumers must gate it into state-only / active-ref-refresh logic
tests must prove TriggerStateChanged cannot create ActionEligible or directly create ActionExecuted
```

## D. Y_NOT_APPLICABLE_EXECUTION_DECISION

Decision:

```text
D/W/M/Q require trigger_amount_chain_pass[P] = true for formal trigger success
Y has no higher-period gate
trigger_amount_chain_pass[Y] = not_applicable
```

Required semantics:

```text
not_applicable is not true
not_applicable is not false
Y must not be serialized or normalized into true
payload/raw_json/proof must preserve not_applicable as execution meaning
```

Implementation consequence:

```text
ordinary BUY/SELL and FULL BUY:FULL/SELL:FULL must branch explicitly on Y
tests must assert Y is not booleanized
```

## E. HINT_UNKNOWN_OUTPUT_DECISION

Decision:

```text
if current_30m_virtual_amount is missing
or reference_30m_amount is missing
then projection_30m_type = unknown
and projection_30m_flag = false
```

Fixed output strategy:

```text
recommended strategy accepted = TriggerPendingMarketData
quality_block_only = false
no_op_later_decide = forbidden
```

Execution meaning:

```text
BUY_HINT / SELL_HINT with unknown 30m projection evidence must emit TriggerPendingMarketData
the pending reason must remain traceable to projection data incompleteness
N5 must not treat this as action entry
```

## F. HISTORICAL_LINEAGE_PROTECTION

Protected historical lineage:

```text
2026-06-25 N4 ordinary run = old-rule historical lineage
2026-06-25 N4 hint run = old-rule historical lineage
2026-06-25 N5 active-monitor v2 run = old-rule historical lineage
```

Non-overwrite rule:

```text
new rule must not overwrite old common_trigger_run
new rule must not overwrite old common_trigger_state
new rule must not overwrite old common_trigger_match
new rule must not overwrite old common_event_outbox
new rule must not overwrite old common_action_*
```

Supersession rule:

```text
historical runs remain auditable under the contract that produced them
new atomic rule lineage may supersede old business intent only through new run_id and explicit gate registration
silent reinterpretation is forbidden
```

## G. NEW_RUN_ID_STRATEGY

Required naming rule:

```text
new N4 run_id must carry atomic-rule version marker
for example = __atomic_rule_v1
or = __n4_atomic_canonical_20260626_v1
```

Required lineage rule:

```text
new N5 run_id must show that its upstream N4 lineage is atomic-rule lineage
2026-06-25 completed run_id values must not be reused
```

Implementation consequence:

```text
execute gates must fail preflight if a reused old-rule run_id is proposed
post-review must prove old lineage remains untouched
```

## H. AFFECTED_CODE_AND_TEST_SURFACE

Primary code surface:

```text
src/ashare_v3/trigger/rule_v4_matcher.py
src/ashare_v3/trigger/provisional_ordinary_matcher.py
src/ashare_v3/trigger/provisional_projection_matcher.py
src/ashare_v3/trigger/provisional_trigger_lifecycle.py
src/ashare_v3/trigger/worker_state_transition.py
```

Primary test surface:

```text
tests/test_rule_v4_matcher.py
tests/test_provisional_ordinary_matcher.py
tests/test_provisional_projection_matcher.py
tests/test_provisional_trigger_lifecycle.py
tests/test_worker_state_transition.py
tests/test_provisional_projection_execute.py
tests/test_provisional_ordinary_execute.py
```

Doc/control surface:

```text
AGENTS.md
docs/Architecture.md
docs/Roadmap.md
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
```

## I. REGRESSION_SCOPE

Mandatory replay/check samples:

```text
300666 / BUY:W,D / 2026-06-25 11:29
001309 / BUY:M / 2026-06-25
at least one BUY:FULL sample
at least one SELL:FULL sample
at least one BUY_HINT sample
at least one SELL_HINT sample
at least one Y-period sample
at least one projection_30m_type = unknown sample
```

Mandatory verification topics:

```text
ordinary BUY/SELL transition definition uses price break plus today_virt_amount vs previous_avg_amount
ordinary BUY/SELL formal amount chain stays separate from current_transition
FULL rules do not require previous_transition != target_transition
Y keeps not_applicable semantics
HINT unknown emits TriggerPendingMarketData
TriggerStateChanged may be consumed as N5 state-gate only
new run_id does not touch 2026-06-25 lineage
```

## J. IMPLEMENTATION_GATE_PRECONDITIONS

Implementation gate may start only if all items below are accepted:

```text
canonical doc registration completed
superseded ownership registration completed
TriggerStateChanged boundary fixed
Y not_applicable semantics fixed
HINT unknown output policy fixed
historical lineage non-overwrite rule fixed
new run_id naming rule fixed
affected code and test surface locked
regression sample set locked
```

Implementation gate must not re-decide any rule-level semantics above.

## K. FINAL_VERDICT

```text
FINAL_VERDICT = READY_FOR_N4_ATOMIC_RULE_IMPLEMENTATION_GATE
```
