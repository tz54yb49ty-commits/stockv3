# N5 Spec Global Review Report

Status: BLOCKED

Review date: 2026-06-04

Layer role: runtime_control

Reviewed inputs:

```text
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_TRACEABILITY.md
docs/Architecture.md
docs/Roadmap.md
docs/Tasks.md
```

Boundary:

```text
execute=false
database_write=false
outbox_consumption=false
N6_entered=false
worker_started=false
delivery_notification_push_voice_mobile_sim_position_real_trade=false
historical_run_rewrite=false
```

## 1. Runtime Control Decision

N5_MARKET_ACTION_CONFIRMATION_SPEC_v1 is suitable as the frozen target contract for future N5 alignment work, but it is not yet sufficient to authorize an N5 v1 execute.

Decision:

```text
BLOCKED for direct N5 v1 execute.
APPROVED as frozen N5 market-action-confirmation target semantics, pending required implementation/test/contract alignment.
```

Reason:

```text
The spec is semantically coherent and aligned with the N1 -> N6 one-way boundary.
Traceability covers N5-001 through N5-064 with no missing or duplicate rule IDs.
However, several execution-critical rules remain planned/gap and must be enforced before any v1 execute final gate can pass.
```

Current 20260603 N5 passed run remains historical evidence under its own contract:

```text
action_run_id=action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
status=passed
P0/P1/P2=0/0/0
ActionBlocked=1252
```

That run must not be silently reinterpreted as v1-compliant. Future v1 execution needs explicit dry-run, contract, preflight, rollback, final gate, and post-review under a v1-specific source/action scope.

## 2. Core Findings

Positive findings:

```text
N5 is correctly scoped as market action confirmation only.
TriggerMatched is the only action entry.
TriggerPendingMarketData and TriggerStateChanged are observer/gate inputs, not action entries.
Runtime signal_type is restricted to B_BUY / S_SELL.
BUY_HINT / SELL_HINT are provenance/trace only in N5.
ActionBlocked is defined as market/system confirmation not passed, not a user trade failure.
N6 remains the first layer allowed to interpret holdings, cash, T+1, display, voice, sim, mobile, position, or trade intent.
Rollback scope excludes N4/N3/N2/N6 and requires hard-fail guards.
```

Blocking findings before v1 execute:

```text
N5-060 dedupe grain alignment is still a traceability gap.
B_BUY / S_SELL four-period price and amount clauses require explicit test coverage.
First-period boundary behavior requires tests for amount default pass and previous-session price references.
blocked_reason enum/validator must reject user-layer reasons.
ActionBlocked report/UI wording must be corrected to market action not confirmed.
final action_mark must be proven final-only and null for non-passed plans.
metric lineage must prove N5 consumes only N3 action-confirmation metrics and ignores opaque payload.action_confirmation.
```

## 3. Risk And Gap List

P0 before execute:

```text
1. Metric-only confirmation enforcement:
   N5 must join N3 action-confirmation metric facts by asset_kind, identity_key, trade_date, metric id, minute/time, and lineage.
   It must not trust payload.action_confirmation.

2. Four-period evaluator proof:
   B_BUY and S_SELL must prove all 120m / 30m / 5m / 1m price and amount clauses.
   Partial testing is not enough for execute final gate.

3. First-period boundary proof:
   First 1m and 5m amount may default pass, but price must still use previous trading day's last body reference.
   Missing previous references must block with missing_previous_session_reference.

4. blocked_reason validator:
   N5 must allow only metric/system confirmation reasons and reject user-layer reasons such as no_position, insufficient_cash, t_plus_one_locked, already_sold, position_limit, blacklist.

5. N5-060 dedupe grain alignment:
   The write-once grain must use trade_date, asset_kind, identity_key, direction, signal_type, trigger_kind, original_condition_key, primary_trigger_period, trigger_mark_candidate, and trigger_time.
```

P1 before execute:

```text
1. final action_mark only when confirmation_status=passed.
2. non-passed / quality-only / blocked plans keep final action_mark=null.
3. ActionBlocked wording in reports/UI must not imply user trade failure.
4. trace_json must preserve merged condition provenance for same-minute grains.
```

P2 before execute:

```text
1. Add traceability coverage checks for N5-001..N5-064.
2. Add runtime_control dashboard detector for N5 v1 status mismatch.
3. Keep older ActionEvent / HintEvent / RiskEvent / PositionEvent as historical compatibility only.
```

## 4. Contract And Traceability Requirements

Required contract additions or confirmations:

```text
spec_version=N5_MARKET_ACTION_CONFIRMATION_SPEC_v1
policy_hash=<hash of frozen spec + traceability + execution policy>
source_n4_run_id allowlist
action_run_id unique for v1 execute
consumer_name scoped to v1 run
N3 action-confirmation metric run_id / projection lineage allowlist
pending-only guard for source N4 outbox
forbidden source_run_id denylist for stale/synthetic runs
expected ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped distribution
expected common_event_inbox / checkpoint scope
rollback_sql path with hard-fail guard
```

Required traceability additions:

```text
N5-060 must move from gap to implemented/tested before execute.
N5-024 through N5-043 must have evaluator and boundary test evidence.
N5-055 through N5-057 must have report wording and blocked_reason validator evidence.
N5-050 through N5-051 must have action_mark final-only evidence.
N5-025 through N5-026 must have metric lineage and opaque payload rejection evidence.
```

## 5. Recommended Execution Order

Recommended order:

```text
Gate 0: runtime_control freezes this global review report.

Gate 1: N5_action contract alignment implementation.
  - dedupe grain N5-060
  - metric-only N3 action-confirmation join
  - B_BUY / S_SELL four-period evaluator
  - first-period boundary evaluator
  - blocked_reason enum/validator
  - action_mark final-only
  - report/UI ActionBlocked wording

Gate 2: N5_action tests and traceability refresh.
  - targeted unit tests for every P0/P1 gap
  - full action test suite
  - full unittest if implementation touches shared event/runner code
  - refresh traceability from gap/planned to implemented/tested only where evidence exists

Gate 3: N5 v1 dry-run.
  - no execute, no DB writes
  - explicit N4 source_run_id allowlist
  - explicit N3 metric lineage
  - planned rows/events/outbox/inbox/checkpoint
  - no N6/user/position refs

Gate 4: N5 v1 execute contract / preflight / rollback materialization.
  - contract JSON/MD
  - preflight JSON/MD
  - rollback SQL hard-fail before DELETE
  - source allowlist and stale denylist
  - scoped baseline proof

Gate 5: runtime_control N5 v1 execute final gate.
  - read-only final review
  - no execute in runtime_control

Gate 6: N5_action execute run-once only after explicit user confirmation.
  - --execute
  - --user-confirmed
  - no N5 outbox consumption
  - no N4 outbox status update
  - no N6
  - no worker

Gate 7: runtime_control post-review registration.
  - run status
  - P0/P1/P2
  - row counts
  - action event distribution
  - N5 outbox pending/delivered/delivering
  - N4 outbox unchanged
  - N6/user/position refs=0
  - rollback_safe
```

Rollback current run decision:

```text
If N5 v1 will reuse the current 20260603 N4 source/action scope, rollback current N5 run first through a separate final gate.
If N5 v1 will consume a new N4 v4 source_run_id with a new action_run_id, do not rollback the current passed run by default; preserve it as historical evidence.
If any current N5 outbox is delivered/consumed by N6 before rollback, rollback order must start at N6/downstream.
```

## 6. Required Runtime Control Position

Runtime control should approve the v1 spec as the target semantics, but block execution until the listed gaps are closed.

Current allowed next gate:

```text
layer_role=N5_action
N5_MARKET_ACTION_CONFIRMATION_SPEC_v1 implementation alignment gate
```

Current forbidden scope:

```text
do not execute N5
do not consume N4/N5 outbox
do not write inbox/checkpoint/action facts/action events/N5 outbox
do not enter N6
do not start worker
do not delivery / notification / push / voice / mobile / sim / position / real trade
do not reinterpret historical runs as v1-compliant
```

Final conclusion:

```text
BLOCKED
```
