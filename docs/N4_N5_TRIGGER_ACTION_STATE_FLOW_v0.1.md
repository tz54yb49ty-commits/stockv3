# N4/N5 Trigger Action State Flow v0.1

Status: finalized_by_user

Ownership clarification:

```text
effective_at = 2026-06-26
this_doc_owns = N4/N5 state flow and cross-layer boundary semantics
this_doc_does_not_own = N4 trigger-side rule definitions
replacement_for_n4_trigger_rules = docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
```

Frozen at: 2026-05-28

Scope: N4 trigger state/outcome events, N5 action entry boundary, N6 user policy boundary.

This is a documentation-only freeze:

```text
code_change=false
schema_migration=false
database_write=false
outbox_write=false
execute=false
worker_started=false
real_trade=false
```

## 1. Standard N4 Events

N4 new runtime persists exactly two canonical event types:

```text
TriggerMatched
TriggerStateChanged
```

Responsibilities:

```text
TriggerMatched = actionable N4 outcome; N5 may start minute-boundary action confirmation
TriggerStateChanged = current trigger-state broadcast; not written to common_trigger_match
```

N5 distinguishes three references:

```text
episode_entry = immutable TriggerMatched that creates ActionEligible
current_active_source = TriggerMatched or the latest same-episode TriggerStateChanged(trigger_live=true)
final_market_proof = matching N3T_C1_CLOSED
```

`TriggerStateChanged(trigger_live=true)` cannot independently create an
action-confirmation episode or `ActionEligible`. When an episode already has
its `TriggerMatched` entry, a material period/state upgrade refreshes the
current active source and may be the top-level source of a later
`ActionExecuted`. The original entry remains in
`action_entry_trigger_matched_ref`.

`TriggerPendingMarketData` is legacy-only. New runtime no-match / missing /
insufficient-proof candidates are dropped and must not write
`common_trigger_state`, `common_trigger_match`, or `common_event_outbox`.

Lifecycle state identity:

```text
run_id
trade_date
asset_kind
identity_key
direction
signal_type
condition_key
```

`trigger_period`, `trigger_bucket`, `trigger_mark_candidate`,
`projection_30m_*`, and period sets are state content, not identity.

Transition contract:

```text
inactive -> matched: TriggerMatched only
matched -> matched and content unchanged: no database write / no event
matched -> matched and period/mark/projection content changed: TriggerStateChanged only
matched -> inactive: TriggerStateChanged only
inactive -> inactive: drop
```

Activation does not also emit `TriggerStateChanged`; `TriggerMatched` is the
activation event. If the state has not materially changed, N4 must not repeat
`TriggerStateChanged`.

For an existing live episode, `matched -> matched` material changes such as a
period upgrade do not invalidate the episode. N5 continues confirmation from
the refreshed TSC(true) boundary. `matched -> inactive` with
`trigger_live=false` terminates further confirmation.

## 2. Trigger State

Canonical N4 states:

```text
inactive
matched
```

Canonical live mapping:

```text
inactive -> trigger_live=false
matched -> trigger_live=true
```

`pending_market_data` is a legacy state label. In new runtime, insufficient
evidence is no-op unless there is a previous live state and current
`metric_ready=true` evidence formally proves the trigger no longer holds.

`TriggerStateChanged` must cover material changes in:

```text
trigger_live
current_status
primary_trigger_period
all_trigger_periods
projection_30m_flag
projection_30m_type
trigger_mark_candidate
data_quality_status
source trace
```

Period priority:

```text
Y > Q > M > W > D
```

Y is a normal formal trigger period in this priority order.  Its upper
amount-chain gate is `not_applicable` because no higher formal period exists,
but that gate is a no-op, not a failure and not `always_true_for_Y`.  Y may be
included in `triggered_periods`, `all_trigger_periods`, and
`primary_trigger_period` only when its own price proof and transition upgrade
proof pass.

For the same object, direction, and runtime signal, `primary_trigger_period` may only upgrade during the same trade date. A D -> W/M/Q/Y upgrade is a state change and must be broadcast.

Ordinary `BUY/SELL`, `BUY:FULL/SELL:FULL`, and `BUY_HINT/SELL_HINT` have
independent lifecycle closures because `condition_key` is part of the state
identity. `BUY_HINT/SELL_HINT` can therefore coexist with ordinary `BUY/SELL`
for the same asset and direction.

When trigger conditions become inactive, N4 emits:

```text
TriggerStateChanged(trigger_live=false, current_status=inactive)
```

This does not delete historical action, user, sim, TTS, or projection facts.

## 3. Signal And Mark Boundary

Runtime `signal_type` is only:

```text
B_BUY
S_SELL
```

Forbidden as runtime `signal_type`:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

`BUY_HINT` / `SELL_HINT` remain only:

```text
condition_key
original_condition_key
trace
audit
analytics
```

They are not user hint types in N1-N5.

N4 outputs trigger-side projection evidence:

```text
projection_30m_flag
projection_30m_type
trigger_mark_candidate
```

N5 owns final action classification:

```text
action_mark
```

Canonical mark values:

```text
normal
30m_volume
30m_shrink
```

Legacy pending states may carry the expected `trigger_mark_candidate`, for example:

```text
signal_type=B_BUY
trigger_mark_candidate=30m_volume
current_status=pending_market_data
trigger_live=false
```

This is only legacy candidate context. New runtime drops this no-op input and
does not write a pending state or outbox event.

## 4. BUY_HINT / SELL_HINT

`BUY_HINT` and `SELL_HINT` are two-stage condition flows:

```text
N2 proves the oversold / overbought prerequisite structure.
N4 confirms the relevant N3 standardized 30m projection evidence.
```

Mapping:

```text
BUY_HINT -> signal_type=B_BUY
SELL_HINT -> signal_type=S_SELL
```

Without N2 prerequisite structure, a 30m projection is not a hint condition. Without N4 projection evidence, `BUY_HINT` / `SELL_HINT` must not become `TriggerMatched`.

Whether they are displayed as hints, alerts, voice, sim, or trade-intent presentation is decided only by N6 user policy.

## 5. Three Channels

N4/N5 must keep these channels independent:

```text
stock
index
board
```

N4/N5 must not hard-code:

```text
index = alert-only
board = alert-only
BUY_HINT = user hint display
SELL_HINT = user hint display
```

Asset channel is fact context only. User policy starts at N6.

## 6. N5 Consumption Boundary

N5 consumes N4 events as follows:

```text
TriggerMatched -> may start 120m / 30m / 5m / 1m action confirmation
TriggerStateChanged -> live/state gate or forwarding context only; action confirmation forbidden
TriggerPendingMarketData -> legacy-only; new runtime must not emit it
```

N5 must not write back to N4 state, recompute N4 trigger decisions, or reinterpret N4 conditions.

## 7. One-Way Flow

The runtime flow is strictly one-way:

```text
N1 -> N2 -> N3 -> N4 -> N5 -> N6
```

Forbidden:

```text
N5 -> N4 writeback
N6 -> N5 writeback
N4 -> N3 writeback
N5 recomputes N4
N4 recomputes N2
N6 directly interprets N4/N5 raw tables to replace standard events
```

## 8. Compatibility Notes

Historical runs and existing code may still contain:

```text
TriggerCleared
TriggerLiveChanged
ActionEvent
HintEvent
RiskEvent
PositionEvent
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT as signal_type
SELL_HINT as signal_type
```

They are compatibility or audit artifacts only. Future alignment must use explicit dry-run, contract, schema, migration, preflight, and rollback gates. Historical evidence must not be silently rewritten.
