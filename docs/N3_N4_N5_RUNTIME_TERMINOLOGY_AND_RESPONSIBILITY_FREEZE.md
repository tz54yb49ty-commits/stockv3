# N3/N4/N5 Runtime Terminology And Responsibility Freeze

Gate: `RUNTIME_CONTROL_N3_N4_N5_RUNTIME_TERMINOLOGY_AND_RESPONSIBILITY_FREEZE_GATE`

Result: `FREEZE_PASS`

Layer role: `runtime_control`

This artifact freezes N3/N4/N5 runtime terminology and responsibility for future implementation work. It does not rewrite historical run evidence and does not execute N4/N5, write a database, consume outbox/inbox/checkpoint, start a worker, enter N6, or touch voice/mobile/sim/position/PnL/real trade.

## Canonical Authority

Future N3/N4/N5 runtime alignment must resolve conflicts in this order:

1. `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`
2. `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`
3. `docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md`
4. `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md`

Older design docs, reports, SQL drafts, tests, and code may still contain historical terms. Those terms are preserved for audit only and must not be used as new runtime semantics when they conflict with the canonical authority above.

## Frozen Runtime Terms

Runtime `signal_type` is only:

```text
B_BUY
S_SELL
```

The following are not allowed as runtime `signal_type`:

```text
BUY_HINT
SELL_HINT
B_BUY_30M_VOL
S_SELL_30M_SHRINK
```

`BUY_HINT`, `SELL_HINT`, `BUY:FULL`, and `SELL:FULL` may remain provenance in:

```text
condition_key
original_condition_key
trace
audit
analytics
```

`trigger_source_kind` is frozen as:

```text
normal
full
hint
```

`trigger_mark_candidate` is frozen as:

```text
normal
30m_volume
30m_shrink
```

N5 final `action_mark` is frozen as:

```text
normal
30m_volume
30m_shrink
```

N5 may write final `action_mark` only after final action confirmation passes.

`current_30m_virtual_amount` and `previous_same_30m_full_amount` are N3 projection / N4 trigger marker evidence. They are not default N5 final 30m amount confirmation fields.

## Event Model

N4 canonical events are only:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
```

`TriggerCleared` and `TriggerLiveChanged` are historical/superseded. New runtime clearing is expressed as:

```text
TriggerStateChanged(trigger_live=false, current_status=inactive)
```

N5 canonical events are only:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

`ActionEvent`, `HintEvent`, `RiskEvent`, and `PositionEvent` are historical/superseded for new canonical runtime work.

`ActionExecuted` means the N5 action confirmation fact is established and the canonical action event is emitted. It does not mean real order, sim, N6 display, voice, mobile push, or trade intent.

## HINT Semantics

`BUY_HINT` and `SELL_HINT` are not user-layer hint events in N1-N5.

Frozen flow:

```text
N2 proves BUY_HINT / SELL_HINT prerequisite structure.
N4 confirms N3 standardized 30m projection evidence.
N5 maps BUY_HINT / SELL_HINT to B_BUY / S_SELL action confirmation.
N6 owns user display / voice / sim / trade-intent policy.
```

## N3 Metric Ownership

N3 is the only owner of action-confirmation metrics.

N4 must not pull market data or assemble raw `1m/5m/30m/120m` indicators.

N5 must not pull market data, assemble raw `1m/5m/30m/120m` indicators, or treat opaque `action_confirmation` payloads as final proof.

N5 consumes:

```text
N4 TriggerMatched
N3 standard action-confirmation metrics
```

## Legacy Supersession

The following historical design docs are preserved for audit and compatibility only. Their conflicting terms are superseded by the canonical authority listed above:

```text
docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md
docs/N5_0_ACTION_EVENT_CONTRACT.md
```

Historical run evidence must not be silently rewritten.

## Forbidden Scope Proof

```text
n4_executed=false
n5_executed=false
database_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
n6_entered=false
voice_mobile_sim_position_pnl_real_trade_touched=false
historical_run_evidence_modified=false
```

Next recommended gate:

```text
N4_N5_CANONICAL_RUNTIME_CONTRACT_ALIGNMENT_READINESS_GATE
```
