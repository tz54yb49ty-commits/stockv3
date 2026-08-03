# N5 Canonical Action Flow v0.1

Status: finalized_by_user

Frozen at: 2026-05-28

Scope: N5 action input boundary, action confirmation state model, final `action_mark`, canonical N5 output events, idempotency, rollback, replay, and N6 boundary.

This is a documentation-only freeze:

```text
code_change=false
schema_migration=false
database_write=false
outbox_write=false
inbox_checkpoint_write=false
execute=false
worker_started=false
real_trade=false
```

Authoritative upstream specs:

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
```

If older N5 design docs, reports, SQL, tests, or code conflict with this document, this document wins for future N5 alignment work. Historical runs remain auditable under the contracts that produced them and must not be silently rewritten.

## 1. N5 Responsibility

N5 owns action confirmation facts and action events. N5 is downstream of N4 trigger state and upstream of N6 user policy.

N5 may:

```text
consume N4 standard trigger events
read allowed N3 minute/action context
write N5 action confirmation facts
emit N5 canonical action events
```

N5 must not:

```text
modify N4 trigger state, facts, or events
recompute N4 trigger decisions
pull market data
assemble 1m/5m/30m/120m action-confirmation indicators from raw minute facts
trust opaque action_confirmation payloads as final proof
read unclosed or future minute bars for action confirmation
write N6 user projection
decide alert-only, display, voice, mobile, sim, or trade-intent policy
perform real trading
start a worker without separate authorization
```

### 1.1 N5 C1 / N3T Permission Boundary

For N3-side market context, N5 has permission only for C1 and N3T:

```text
N5_MARKET_CONTEXT_PERMISSION:
- N5 may use only explicit N3-C1 scoped closed 1m K context / metric_context_rows passed by runtime_control.
- N5 may use only N3T action-confirmation metric rows as final ActionExecuted market proof.
- Valid N3T rows must have source_basis=N3T_C1_CLOSED, metric_role=action_confirmation, proof_consumer=N5, and not_n5_final_proof=false.
- N5 must not use A1 previous-day cumulative, N3P, B1, B2, realtime_action_confirmation_metric, N4 trigger proof, or N4 projection candidate fields as ActionExecuted final proof.
- N5 must not trigger C1/N3T runtime, pull market data, scan full-market C1, or write N3/N4 facts/outbox.
- Missing C1/N3T context blocks ActionExecuted only; ActionEligible from a valid N4 TriggerMatched remains allowed.
```

`trigger_mark_candidate`, `projection_30m_flag`, and `projection_30m_type` are N4 trace fields in N5. They are not final `action_mark` authority.

## 2. N5 Input Event Handling

N5 consumes only canonical N4 events for new runtime work:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
```

| N4 event | N5 handling | Starts action confirmation | Result |
|---|---|---:|---|
| `TriggerMatched` | Validate source allowlist, idempotency, canonical payload, live context, and minute-boundary rules | yes | Only positive action confirmation entry |
| `TriggerPendingMarketData` | no-op / quality-only / state-gate context | no | Must not write final action fact or final `action_mark` |
| `TriggerStateChanged(trigger_live=true)` | refresh the current episode's live/state context and current active source | no | May advance existing tracking only if its immutable `TriggerMatched` entry exists |
| `TriggerStateChanged(trigger_live=false)` | stop further confirmation for the current trigger state | no | May mark pending/tracking action as `expired`; never deletes history |

`TriggerMatched` is the only N5 action-confirmation `episode_entry` and the
only event that creates `ActionEligible`. `TriggerPendingMarketData` and
`TriggerStateChanged` cannot independently create an episode. A later
`TriggerStateChanged(trigger_live=true)` may refresh the same episode's
`current_active_source` and become the top-level source of `ActionExecuted`,
but only while the original `TriggerMatched` remains frozen in
`action_entry_trigger_matched_ref`.

When `trigger_live=false`, N5 must stop continuing 120m / 30m / 5m / 1m confirmation for that trigger state. It must not delete historical action facts, action events, user projection, TTS, sim, or audit evidence.

Repeated delivery of the same `TriggerMatched` event is idempotent. After a
`TriggerStateChanged(trigger_live=false)` expires the current tracking episode,
a later distinct `TriggerMatched` event for the same action grain starts a new
episode and emits a new `ActionEligible` keyed by that source trigger event.
This episode boundary must be identical whether the events arrive in one
planner batch or in separate invocations.

### 2.1 Condition Projection Context And Price Percentages

New N5 live-tracking events use the additive contract marker:

```text
pct_contract_version=N5-trigger-action-pct-context-v1
```

`ActionEligible` freezes its price and N2 condition context from the verified
action-entry reference only:

```text
action_entry_trigger_matched_ref.source_n4_payload.trigger_price
action_entry_trigger_matched_ref.source_n4_payload.condition_projection_context
action_entry_trigger_matched_ref.source_n4_payload.condition_projection_context_status
action_entry_trigger_matched_ref.source_n4_payload.condition_projection_context_trace
```

The canonical calculation is:

```text
trigger_pct = (entry TriggerMatched trigger_price / entry N2 close - 1) * 100
```

`TriggerStateChanged(trigger_live=true)` may refresh the current
`source_n4_payload` and `latest_trigger_state_changed_ref`, but it must not
replace the frozen action-entry price, context, or `trigger_pct`. An
`ActionExecuted` event uses the latest event that created or refreshed A for
its top-level `source_trigger_event_*` / `source_n4_payload`, keeps the
original `TriggerMatched` entry snapshot in
`action_entry_trigger_matched_ref`, and additionally publishes:

```text
action_price = selected passing N3T_C1_CLOSED.current_price
action_pct = (action_price / the same entry N2 close - 1) * 100
```

`trigger_pct` and `action_pct` use `Decimal`, `ROUND_HALF_UP`, and exactly six
fraction digits. `action_price` preserves the selected N3T `current_price`
value without price recomputation or rounding; N5 must not query raw 1m facts
or recompute the N2 close.

The N2 context object and N4 validation trace pass through unchanged. Missing,
old, malformed, or `not_ready` context does not block the existing N5 action
lifecycle. In that case the applicable percentage is null, its status is
`not_ready`, and stable not-ready reasons are emitted. A valid selected N3T
price may still be exposed as `action_price` even when `action_pct` is not
available.

These fields are optional additive payload data under event schema `v2`. They
must not enter the action state key, event ID, dedup key, `action_state`, final
`action_mark`, or N3T final-proof decision. Historical events are not backfilled.

### 2.2 N5 -> N6 Projection Message Contract v1

New live-tracking `ActionEligible` and `ActionExecuted` events additionally
carry the additive N5-owned message contract:

```text
projection_message_contract_version=N5-n6-projection-message-v1
projection_message_contract_hash=572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025
projection_message_status=ready|not_ready
projection_message_not_ready_reasons=[]
```

The hash is the fixed SHA256 of the 2,653-byte canonical compact sorted-JSON
manifest; it is not a per-event data hash. N2 `condition_projection_context.context_hash`
continues to protect the frozen context object. The marker and flattened fields
are additive under event schema `v2`; they must not alter lifecycle, tracking
state, event ID, dedup key, final action mark, or N3T final-proof semantics.

N5 owns and emits:

```text
asset_code                 = validated identity_key third segment
asset_name                 = entry context fields.name
buy_expected_return_pct    = entry context fields.buy_expected_return_pct
sell_expected_return_pct   = entry context fields.sell_expected_return_pct
up_secondary_expected_return_pct
up_reference_period
down_reference_period
score / pe_core            = stock entry context only
```

All values are copied from the verified action-entry `TriggerMatched` context;
N5 must not recompute N2 targets, returns, close, score, or reference periods.
Index and board events must not emit stock-only `score` or `pe_core`. Optional
return/reference fields may be null without making the message contract
not-ready.

Before marking the message ready, N5 validates the action-entry context version,
hash, source layer, asset, identity, for-trade date, source status and exact
asset field shape. It also validates the N4 passthrough policy version/hash,
status, and `source_context_hash`. Invalid message evidence only sets
`projection_message_status=not_ready` with stable ordered reasons; existing
N5 `ActionEligible` / `ActionExecuted` lifecycle remains unchanged.

Event shape is fixed:

```text
ActionEligible:
  action_price/action_pct/action_pct_status are absent

ActionExecuted:
  action_price is the selected passing N3T_C1_CLOSED.current_price
  action_pct/action_pct_status are present and ready when the message is ready
```

Formal trigger periods remain separate from HINT's 30m projection evidence:

```text
ordinary / FULL:
  trigger_period = primary_trigger_period
  primary_trigger_period in Y/Q/M/W/D
  all_trigger_periods = current formal set

BUY_HINT / SELL_HINT:
  trigger_period = 30m
  primary_trigger_period = null
  all_trigger_periods = []
```

The bounded tracking persistence helper may retain internal
`triggered_periods=[30m]` solely to preserve its existing non-empty storage
requirement. It is not a formal period set and must not appear as
`all_trigger_periods` or `triggered_periods` in the N5 user message payload.

Historical events without this marker remain read-only compatibility evidence;
they are not backfilled and cannot be silently treated as v1 message-contract
events.

## 3. Canonical Action State

Canonical N5 `action_state` values are:

```text
eligible
blocked
executed
skipped
expired
```

State meanings:

| action_state | Meaning |
|---|---|
| `eligible` | N4 matched trigger entered N5 and passed eligibility checks, but no final action event has been emitted yet |
| `blocked` | N5 cannot confirm action because a hard quality, boundary, source, live, idempotency, or policy-independent gate failed |
| `executed` | N5 action confirmation fact is established and the canonical action event has been emitted |
| `skipped` | N5 intentionally did not proceed after evaluating the matched trigger |
| `expired` | N5 stopped tracking because the confirmation window expired or N4 became non-live before confirmation |

N5 action state is downstream of N4. N5 must not update N4 trigger state to express an action decision.

## 4. Internal Confirmation Fields

The following fields are internal N5 confirmation progress fields and are not canonical `action_state` values:

```text
confirmation_status = pending / passed / failed / expired
tracking_until
last_checked_minute_label
```

They may be stored in future N5 fact tables or trace JSON to make run-once and worker flows resumable. They must not be emitted as public action states and must not leak into N6 as user display policy.

## 5. ActionExecuted Semantics

`ActionExecuted` means:

```text
N5 action confirmation fact has been established.
N5 emitted a canonical action event.
```

`ActionExecuted` does not mean:

```text
real order submitted
sim trade written
N6 user card displayed
voice/TTS spoken
mobile push sent
trade intent approved
```

Real trading, sim, display, voice, mobile, and trade-intent presentation are outside N5 and belong to future explicit N6/user policy contracts.

Current proof boundary:

```text
N3P is not an N5 final action-confirmation metric.
N3P is N4 ordinary trigger proof only.
N3P lineage fields may remain in N5 payloads as trace, including selected_metric_id / selected_metric_time / source_metric_run_id compatibility fields.
Those fields are not final proof for ActionExecuted.
N5 must fail closed with BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF when a N3P / realtime_action_confirmation_metric payload is used as ActionExecuted final proof.
ActionEligible from TriggerMatched remains allowed.
ActionExecuted requires an episode originally entered by a live N4 TriggerMatched plus an N3T action-confirmation metric row derived from closed C1 1m K. A later same-episode TriggerStateChanged(trigger_live=true) may be the current active source, but it cannot replace the immutable TriggerMatched entry or execute without it.
N3P-backed proof remains fail-closed even after N3T exists.
```

## 6. Expired Expression

N5 must not introduce `ActionExpired`.

Expired action state is represented as:

```text
ActionSkipped(action_state=expired, reason=trigger_live_false)
ActionSkipped(action_state=expired, reason=window_expired)
```

`expired` can also appear in N5 facts as the final `action_state` when a pending/tracking confirmation stops without final action confirmation.

## 7. Action Mark Decision

N4 carries only trigger-side non-final mark evidence:

```text
trigger_mark_candidate
projection_30m_flag
projection_30m_type
```

N5 owns the final action classification:

```text
action_mark
```

Final `action_mark` values are only:

```text
normal
30m_volume
30m_shrink
```

N5 may write final `action_mark` only after all required action confirmation rules pass:

```text
120m confirmation
30m confirmation
5m confirmation
1m confirmation
```

The canonical numeric rule set, first-period boundary policy, and N3 metric ownership are frozen in `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`. N5 must consume N3T action-confirmation metrics plus N4 `TriggerMatched`; it must not use `payload.action_confirmation` as authoritative proof.

Decision rules:

| Runtime signal and N5 metric evidence | Required N5 result before final mark | final action_mark |
|---|---|---|
| `signal_type=B_BUY`, `current_30m_virtual_amount > previous_day_same_window_amount`, and buy-side 30m price confirmation passes | all N5 buy confirmations pass | `30m_volume` |
| `signal_type=S_SELL`, `current_30m_virtual_amount < previous_day_same_window_amount`, and sell-side 30m price confirmation passes | all N5 sell confirmations pass | `30m_shrink` |
| Any other passed confirmation, including missing `previous_day_same_window_amount` | all side-specific N5 confirmations pass | `normal` |

`previous_day_same_window_amount` means the previous trade date's same 30m time window amount. It is not the same-trade-date previous 30m segment (`previous_30m_full_amount`). Missing same-window amount does not block `ActionExecuted`; it downgrades the final mark to `normal` and records `action_mark_reason=previous_day_same_window_amount_missing`.

N5 must not use N4 `trigger_mark_candidate` / `projection_30m_type` as the canonical final `action_mark` source. N5 may retain those values only as trace, for example `n4_trigger_mark_candidate`.

If action confirmation is pending, blocked, skipped, or expired, N5 may retain candidate mark evidence in trace fields:

```text
trigger_mark_candidate
candidate_action_mark
trace_json
```

It must not write a final `action_mark`.

## 8. BUY_HINT / SELL_HINT

`BUY_HINT` and `SELL_HINT` are condition provenance only in N5 canonical runtime:

```text
condition_key
original_condition_key
trace_json
audit
analytics
```

Canonical runtime signal mapping:

```text
BUY_HINT -> signal_type=B_BUY
SELL_HINT -> signal_type=S_SELL
```

N5 must not interpret `BUY_HINT` or `SELL_HINT` as:

```text
user hint type
HintEvent
alert-only policy
voice policy
sim policy
trade-intent policy
```

Whether a `BUY_HINT` / `SELL_HINT` provenance should display as a hint, alert, card, voice, sim, or trade-intent presentation is decided only by N6/user policy.

## 9. Three Fact Channels

N5 must preserve three independent fact channels:

```text
stock
index
board
```

N5 must not hard-code:

```text
index = alert-only
board = alert-only
BUY_HINT = user hint display
SELL_HINT = user hint display
```

Asset channel is action fact context only. N6 decides display, notification, sim, and trade-intent behavior.

## 10. Canonical Output Events

N5 may output only these canonical event types for new runtime work:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Recommended event meaning:

| event_type | Required payload semantics |
|---|---|
| `ActionEligible` | `action_state=eligible`; matched trigger passed initial N5 entry gates |
| `ActionBlocked` | `action_state=blocked`; hard quality/source/live/minute/idempotency gate blocked confirmation |
| `ActionExecuted` | `action_state=executed`; final N5 action confirmation passed and event emitted |
| `ActionSkipped` | `action_state=skipped` or `action_state=expired`; N5 intentionally stopped without final action confirmation |

Deprecated N5 event names for future canonical runtime work:

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

These deprecated event names may remain in historical artifacts and current-real run evidence. Future alignment must use explicit dry-run, contract, schema, migration, preflight, rollback, and compatibility gates.

## 11. Minute Boundary And Confirmation Rules

N5 must use only N3 closed minute facts or approved N3 closed/projection context for action confirmation.

For new canonical runtime work, the approved context is the N3 action-confirmation metric set defined in `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`.

Minute label rule:

```text
A 1m bar labeled HH:MM covers HH:MM-HH:MM+1.
It is complete only at HH:MM+1.
N5 must not use future minute bars.
N5 must not use unclosed minute bars.
```

If a completed minute covers `trigger_time`, N5 may use it even when the minute label is earlier than `trigger_time`.

If N4 becomes live slightly after the relevant minute state was already true, N5 may synthesize one trigger-time action check only when all of the following are true:

```text
current trigger_live=true
the minute fact is closed
the source run is explicitly allowlisted
the action grain has not already been written
the confirmation window has not expired
the event remains within the same trade date / channel / identity / direction / signal grain
```

When any condition fails, N5 must not compensate by confirming action.

Opaque compatibility payloads:

```text
payload.action_confirmation is not authoritative proof.
payload.action_confirmation may be retained only as trace or historical compatibility evidence.
ActionExecuted requires a live episode with an immutable TriggerMatched entry plus matching N3T action-confirmation metrics. Its current active source may be a later same-episode TriggerStateChanged(trigger_live=true).
N3T source_basis must be N3T_C1_CLOSED.
If the metric row is N3P/B1/B2/realtime_action_confirmation_metric lineage, N5 must fail closed with BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF or BLOCKED_N3T_METRIC_REQUIRED.
```

## 12. Idempotency And Write-Once Grain

N5 must be idempotent for repeated delivery and replay.

Default write-once action confirmation grain:

```text
trade_date
asset_kind
identity_key
direction
signal_type
action_mark_or_candidate_mark
action_minute_label
confirmation_window
source_trigger_state_id
```

Same-minute multiple `condition_key` rows for the same asset, direction, runtime signal, action mark, and confirmation window must default to one action confirmation. All condition provenance must be preserved in `trace_json`:

```text
condition_keys
original_condition_keys
source_trigger_event_ids
source_trigger_match_ids
source_condition_pool_ids
primary_trigger_period
all_trigger_periods
period_upgrade_trace
projection_trace
minute_fact_trace
```

This prevents duplicate action events while keeping full traceability.

## 13. Payload Requirements

Canonical N5 action event payloads must carry:

```text
run_id
source_trigger_event_id
source_trigger_run_id
source_trigger_state_id
source_trigger_match_id
identity_key
asset_kind
direction
condition_key
original_condition_key
signal_type
trigger_mark_candidate
action_mark
action_state
confirmation_status
action_policy
eligibility_reason
blocked_reason
skipped_reason
trace_json
event_schema_version
```

Rules:

```text
condition_key is trace/audit/analytics only
signal_type must be B_BUY or S_SELL
final action semantics are signal_type + action_mark
N5 payload must not encode alert-only, display label, voice, sim, mobile, real order, or trade-intent policy
```

For pending/blocked/skipped/expired rows, final `action_mark` must be null or absent; candidate mark evidence must stay in trace.

## 14. Rollback And Replay

N5 rollback must be scoped by action run:

```text
action_run_id
source_trigger_run_id
consumer_name
```

Rollback may clean only N5 and N5 consumer scope:

```text
N5 action facts
N5 action events
N5 outbox rows
N5 inbox rows
N5 checkpoint rows
N5 quality rows
N5 action_run row
```

Rollback must not touch:

```text
N4 trigger facts or outbox
N3 minute / projection / snapshot facts
N2 condition facts
N6 user projection
voice
mobile
sim
real trade / order state
old system
```

Replay may read only explicitly allowlisted `source_run_id` values. Old synthetic, stale, or superseded N4 runs must be denylisted unless a separate shadow-only replay contract explicitly allows them.

## 15. Compatibility And Divergence

Known current divergence items:

```text
Current N5 schema/code still uses ActionEvent / HintEvent / RiskEvent / PositionEvent.
Current N5 schema/code still allows B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT as runtime signal_type.
Current N5 schema/code still uses action_type / decision_status instead of canonical action_state / action_mark.
Current N5 tests and reports still assert HintEvent for BUY_HINT / SELL_HINT.
Current N5 SQL CHECK constraints would block ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped.
Current N5 input contract still contains TriggerCleared compatibility paths and does not yet canonicalize TriggerStateChanged.
```

These are alignment tasks, not defects in historical run evidence. Future N5 implementation must migrate them through explicit contract, schema, dry-run, preflight, rollback, and replay gates.
