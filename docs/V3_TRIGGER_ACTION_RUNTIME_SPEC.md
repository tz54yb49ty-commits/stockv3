# v3 Trigger / Action Runtime Canonical Spec

Status: canonical

Frozen at: 2026-05-28

Confirmed scheme version:

```text
N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1
N5_CANONICAL_ACTION_FLOW_v0.1
```

Scheme status:

```text
finalized_by_user
documentation_only
implementation_not_started_by_this_freeze
schema_migration_not_started_by_this_freeze
execute_not_authorized_by_this_freeze
```

Authoritative scope: N1-N5 signal semantics, N4 trigger runtime, N5 action runtime, N6 user projection/display policy boundary.

This document is the authoritative runtime spec for N4/N5/N6 trigger and action semantics. If older design docs, reports, SQL drafts, tests, or code conflict with this document, this document wins for future alignment work. Existing historical runs are not silently reinterpreted; they remain auditable under the contract that produced them.

The N5-specific action confirmation flow is frozen in:

```text
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
```

The N4 trigger-side atomic rule definition is frozen in:

```text
docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
```

The N3/N4/N5 action-confirmation projection and final confirmation rule is frozen in:

```text
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
```

Realtime signal/action engine execution boundary is frozen in:

```text
docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_EXECUTABLE_PLAN.md
```

This plan supersedes the older blanket wording that could be read as forbidding
all unclosed-minute-derived N4 matches. New runtime work must use this
replacement boundary: N4 must not directly read raw unclosed minute bars or
assemble raw indicators, but it may consume N3 standardized, traceable realtime
virtual metrics to emit `TriggerMatched`. This does not change N4/N5 current
business rules, canonical event names, or runtime `signal_type`.

中文冻结：不改 N4/N5 当前业务规则。

The symmetric target-price and holding-target ownership boundary is frozen in:

```text
docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md
```

This spec freeze is documentation only:

```text
execute=false
database_write=false
outbox_write=false
inbox_checkpoint_write=false
worker_started=false
real_trade=false
```

## 1. One-Way Runtime Flow

The runtime flow is strictly one-way:

```text
N1 -> N2 -> N3 -> N4 -> N5 -> N6
```

Downstream layers must not write upstream state. Cross-layer communication must use formal contracts: immutable upstream facts, approved read-only summaries, or standard events.

Layer responsibility is frozen at the layer boundary:

```text
N1 owns source facts and source versions.
N2 owns condition semantics, condition_key, condition_pool, frozen trigger baselines, and symmetric target-price candidates.
N3 owns market data facts, projections, minute facts, closed summaries, and market events.
N3 owns market facts and proof facts. `N3P` is an N4 ordinary trigger proof, not an N5 final action-confirmation proof.
N4 owns trigger state, trigger outcome facts, and trigger state/outcome events.
N5 owns action confirmation facts and action events.
N6 owns user policy, display, notification, voice, mobile, sim display, holding-target interpretation, position target lock, and trade-intent presentation.
```

No downstream layer may recompute or reinterpret an upstream layer's responsibility:

```text
N4 must not recompute N2 conditions or condition_pool.
N4 must not assemble action-confirmation projection metrics from raw minute facts.
N5 must not recompute N4 trigger decisions.
N5 must not assemble 1m/5m/30m/120m action-confirmation indicators from raw minute facts.
N6 must not directly rewrite or reinterpret N4/N5 facts to replace standard events.
```

Current N3P/N5 boundary:

```text
N3P = N4 ordinary trigger proof for D/W/M/Q/Y formal amount-chain.
N3P may be carried through N4/N5 payloads only as lineage / compatibility trace.
N3P must not be used as N5 ActionExecuted final proof.
N5 ActionExecuted requires an N3T action-confirmation metric contract derived from closed C1 1m K.
TriggerMatched may create ActionEligible, but N3P-backed ActionExecuted must fail closed with BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF or BLOCKED_N3T_METRIC_REQUIRED.
```

No upstream layer may carry downstream user policy:

```text
N2/N3/N4/N5 must not carry alert-only, display priority, watchlist, voice, mobile, sim, or trade-intent policy.
N6/user policy is the first layer allowed to decide user-facing interpretation.
```

Forbidden reverse mutations:

```text
N5 -> N4
N6 -> N5
N4 -> N3
N6 -> N4
N5 -> N3
any downstream write to upstream state
```

In particular:

```text
N5 must not write back N4 trigger state, facts, or events.
N6 must not write back N5 action state, facts, or events.
N6 must not write back N4 trigger state, facts, or events.
```

## 1.1 Symmetry Target Price Boundary

Target-price semantics are condition-layer static context until N6/position interprets them for a user or holding.

Canonical N2 target-price fields and concepts are defined by `docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md`:

```text
symmetry_anchor
amplitude_source_period
A segment recognition
base_price_policy
reference_target_price
secondary_target_price
up_sell_reference_period
down_buy_reference_period
```

Boundary rules:

```text
N2 computes target-price candidates and reference periods.
N4 may carry target fields as immutable trigger context only.
N5 may carry target fields as immutable action/audit context only.
N4/N5 must not recompute target candidates.
N4/N5 must not lock target prices.
N4/N5 must not decide clear-position policy.
N6/position owns locked_target_price and target_lock_status.
N6/position owns holding-target interpretation and clear-position policy.
```

`clear_sell_ref_period` is not canonical semantics. It is only a legacy alias:

```text
clear_sell_ref_period = up_sell_reference_period
```

## 2. Layer Responsibilities

### N4 Trigger

N4 owns trigger state and trigger outcome facts.

N4 may:

```text
read N2-localized trigger context
read N3 standard facts/events/projection metrics
write N4 trigger state
write N4 trigger outcome facts
emit N4 trigger events
```

N4 must not:

```text
pull market data
rebuild raw minute indicators
recompute condition_basis / condition_pool / minute_target_scope
write action facts
write sim state
write user display/projection
decide alert-only / voice / mobile / sim / trade-intent policy
modify N3 facts/events/projection
modify N5/N6 state
```

### N5 Action

N5 owns action confirmation facts. It consumes trigger signals and confirms action facts against its own minute-boundary rules.

N5 may:

```text
consume N4 standard trigger events
read allowed N3 minute/action context
write N5 action confirmation facts
emit N5 action events
```

N5 must not:

```text
modify N4 trigger state
rewrite N4 trigger facts
emit N4 events
trust opaque action_confirmation payload as final proof
assemble action-confirmation indicators from raw minute bars
write N6 user display/projection
write sim display
decide alert-only / voice / mobile / sim display policy
perform real trading without a later explicit contract
```

N5 must follow `docs/N5_CANONICAL_ACTION_FLOW_v0.1.md` for action input handling, `action_state`, internal confirmation fields, `action_mark`, canonical output events, idempotency, rollback, and replay.

N5 must follow `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md` for the 120m / 30m / 5m / 1m confirmation rule, first-period boundary policy, and the requirement to consume N3 standard action-confirmation metrics rather than opaque payload proof.

### N6 User

N6 owns user policy, user display, push, TTS, mobile, and sim display projection.

N6 may:

```text
consume N5 standard action events
write user display projection
decide alert-only / display label / notification channel
write push/TTS delivery state
write sim display projection
```

N6 must not:

```text
modify N4 trigger state
modify N5 action state
rewrite N5 action facts/events
write upstream business facts
```

### Three Runtime Channels

N4/N5/N6 must keep stock, index, and board channels independent:

```text
stock_trigger_channel
index_trigger_channel
board_trigger_channel
```

Every trigger/action/user event must carry:

```text
asset_kind or asset_channel
identity_key
code
name
direction
trade_date
source_run_id
```

Rules:

```text
Do not join cross-asset data by bare code.
Do not infer user policy from asset channel.
Do not hard-code index/board as alert-only in N4 or N5.
N4/N5 may preserve asset channel as fact context only.
N6/user policy decides whether stock/index/board is displayed, alerted, voiced, simulated, or trade-intent eligible.
```

## 3. Condition Key And Canonical Buy/Sell Signal Model

### 3.1 Condition Key Boundary

`condition_key != signal_type`.

`condition_key` is upstream condition provenance only. It may be used only for:

```text
trace
audit
analytics
```

Canonical runtime condition keys currently allowed into N4/N5 gates are:

```text
BUY:D
BUY:W,D
BUY:Y,Q,M,W,D
SELL:D
SELL:M,W,D
SELL:Y,Q,M,W,D
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

These names are condition semantics, not user display or action policy types.

N1-N5 must treat all `BUY*` condition keys as buy-side signal provenance and all `SELL*` condition keys as sell-side signal provenance:

```text
BUY:D / BUY:W,D / BUY:Y,Q,M,W,D / BUY:FULL / BUY_HINT -> buy-side
SELL:D / SELL:M,W,D / SELL:Y,Q,M,W,D / SELL:FULL / SELL_HINT -> sell-side
```

N1-N5 must not interpret `BUY_HINT` or `SELL_HINT` as user hint/display types, alert-only types, voice types, sim types, or trade-intent policy. They are buy/sell condition provenance only until N6/user policy decides presentation and downstream user behavior.

N4/N5/N6 must not derive runtime action semantics from raw `condition_key`. Runtime trigger/action semantics are expressed only by canonical buy/sell signal plus trigger/action mark fields:

```text
signal_type
N4: trigger_mark_candidate / projection_30m_flag / projection_30m_type
N5: action_mark
```

N2 no longer treats `B_BUY_30M_VOL` or `S_SELL_30M_SHRINK` as future action semantic values. If those names appear in N2 condition output or historical artifacts, they are lineage/audit labels only; they must be normalized downstream into canonical `signal_type` plus N4 trigger projection evidence or N5 final `action_mark`.

### 3.2 Signal Type Boundary

Canonical N4/N5 runtime `signal_type` values are only:

```text
B_BUY
S_SELL
```

Deprecated as `signal_type`:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

The deprecated 30m names and hint names must not be used as formal runtime `signal_type` in new N4/N5 work. They may appear only in `condition_key`, historical artifacts, migration compatibility code, trace/audit fields, or explicit alignment reports until removed from runtime payloads.

Canonical mapping from condition provenance to runtime signal:

```text
BUY:D / BUY:W,D / BUY:Y,Q,M,W,D / BUY:FULL / BUY_HINT -> signal_type=B_BUY
SELL:D / SELL:M,W,D / SELL:Y,Q,M,W,D / SELL:FULL / SELL_HINT -> signal_type=S_SELL
```

### 3.3 N4 Ordinary Formal Period Trigger Semantics

Ordinary formal periods are:

```text
Y / Q / M / W / D
```

For ordinary `BUY` / `SELL`, N4 must evaluate only the periods requested by the
N2 condition provenance, using localized N2 trigger context plus N3 standard
metric facts.  N4 must not infer periods from display text or downstream action
state.

Formal price proof:

```text
BUY:P  current_price/current_close > P.trigger_previous_entity_high
SELL:P current_price/current_close < P.trigger_previous_entity_low
```

Formal transition proof:

```text
BUY:P target_transition = volume_up
  current_price/current_close > P.trigger_previous_entity_high
  AND current_period_avg_with_today > N2 previous complete same-period amount

SELL:P target_transition = low_volume_down
  current_price/current_close < P.trigger_previous_entity_low
  AND current_period_avg_with_today < N2 previous complete same-period amount

transition_upgrade_pass =
  previous_transition != target_transition
  AND current_transition == target_transition
```

N2 owns the previous complete same-period amount.  N4 may read it only from
localized `period_trigger_baseline_json.periods[P]`, in this priority order:

```text
previous_avg_amount
previous_amount
previous_amount_baseline
classification_previous_amount_baseline
```

N4 must not use these fields as previous amount fallbacks:

```text
trigger_previous_amount_baseline
current_amount_seed
current_avg_amount_seed
current_amount_total_seed
```

For D/W/M/Q, transition upgrade is necessary but not sufficient.  These periods
also require the upper amount-chain gate:

```text
D BUY: today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg
W BUY: weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg
M BUY: monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
Q BUY: quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg

D SELL: today_virt_amount <= weekly_avg_with_today <= prev_weekly_avg
W SELL: weekly_avg_with_today <= monthly_avg_with_today <= prev_monthly_avg
M SELL: monthly_avg_with_today <= quarterly_avg_with_today <= prev_quarterly_avg
Q SELL: quarterly_avg_with_today <= yearly_avg_with_today <= prev_yearly_avg
```

Formal pass:

```text
D/W/M/Q formal_pass = price_pass && transition_upgrade_pass && trigger_amount_chain_pass
Y formal_pass       = price_pass && transition_upgrade_pass
```

Y is not a special display-only trace period.  Y may enter
`triggered_periods`, `all_trigger_periods`, and `primary_trigger_period` when
the Y formal pass holds.  The only difference is that Y has no upper amount
chain:

```text
Y trigger_amount_chain_status = not_applicable
Y trigger_amount_chain_gate = no_upper_period_chain_noop
```

This no-op gate must not be implemented as `always_true_for_Y`.  Y cannot
trigger from missing upper-chain proof alone; it still needs its own price proof
and transition upgrade proof.

`BUY:FULL` / `SELL:FULL` are fixed D-only current-state formal conditions.
They reuse the D price proof, D trigger amount-chain gate, and D amount
unit/source proof, but they do not require
`previous_transition != target_transition`.

## 4. Projection Mark And Action Mark

30m information is never represented by `signal_type` or `condition_key`.

N4 may carry only trigger-side 30m evidence:

```text
projection_30m_flag
projection_30m_type
trigger_mark_candidate
```

N5 owns the final action mark after minute-boundary action confirmation:

```text
action_mark
```

Canonical N5 `action_mark` values:

```text
normal
30m_volume
30m_shrink
```

Canonical final action mapping:

| Canonical signal_type | N5 action-confirmation metric basis | Canonical action_mark |
|---|---|---|
| `B_BUY` | all N5 confirmations pass, `current_30m_virtual_amount > previous_day_same_window_amount`, and buy-side 30m price confirmation passes | `30m_volume` |
| `S_SELL` | all N5 confirmations pass, `current_30m_virtual_amount < previous_day_same_window_amount`, and sell-side 30m price confirmation passes | `30m_shrink` |
| `B_BUY` / `S_SELL` | all N5 confirmations pass, but same-window 30m amount condition is false or missing | `normal` |

`BUY:Y,Q,M,W,D`, `SELL:Y,Q,M,W,D`, `BUY:FULL`, `SELL:FULL`, `BUY_HINT`, and `SELL_HINT` are condition provenance and trace. They do not directly decide `action_mark`. `previous_day_same_window_amount` is the previous trade date's same 30m time-window amount; it must not be substituted with same-trade-date `previous_30m_full_amount`.

N4 must not decide the final N5 action classification. It can only pass N3-standardized projection evidence and a non-final candidate mark:

```text
projection_30m_flag=true/false
projection_30m_type=volume_up / shrink_down / none
trigger_mark_candidate=normal / 30m_volume / 30m_shrink
```

N5 decides the final `action_mark` when action confirmation passes its 120m / 30m / 5m / 1m rules. The final mark is derived from N3 action-confirmation metric fields, not from N4 `trigger_mark_candidate`. Missing `previous_day_same_window_amount` downgrades the mark to `normal` without blocking `ActionExecuted`. Those rules and their N3 metric ownership are frozen in `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`. Existing N4 code or historical reports that expose an `action_mark` field must be treated as `trigger_mark_candidate` until explicitly aligned.

N4/N5 must not compute the 120m / 30m / 5m / 1m confirmation metrics by reading raw minute facts. For N5 `ActionExecuted`, N3T must publish standard action-confirmation metric facts from closed C1 1m K. The action-confirmation episode must have an immutable `episode_entry` created by a live N4 `TriggerMatched`; after that entry exists, a later `TriggerStateChanged(trigger_live=true)` may refresh the same episode's `current_active_source` and become the top-level `source_trigger_event_*` of `ActionExecuted`. The original `TriggerMatched` remains frozen in `action_entry_trigger_matched_ref`, and the `final_market_proof` must be the matching `N3T_C1_CLOSED` fact. Opaque `action_confirmation` payload fields are trace-only until a separate alignment contract replaces them.

`BUY_HINT` and `SELL_HINT` remain formal realtime buy/sell condition keys, but they are not formal N4/N5 runtime `signal_type` values. N4/N5 must not downgrade them to display-only semantics, and must not promote them into user hint policy either. Whether they are shown as a hint label, alert-only card, push, voice/TTS, sim display, or trade intent is decided only by N6/user policy.

N1-N5 forbidden interpretations:

```text
BUY_HINT != user hint type
SELL_HINT != user hint type
BUY_HINT != alert-only policy
SELL_HINT != alert-only policy
BUY_HINT / SELL_HINT do not imply voice
BUY_HINT / SELL_HINT do not imply sim inclusion/exclusion
BUY_HINT / SELL_HINT do not imply real trade intent
```

N6/user policy is the first layer allowed to decide:

```text
alert-only
display label
voice / TTS
sim display
trade intent presentation
```

## 5. 30m Projection Semantics

30m projection is not closed-bar confirmation.

30m projection means:

```text
intraday open bucket projection
```

Buy-side 30m volume projection:

```text
current 30m bucket intraday virtual amount > previous trading day's same 30m bucket full amount
```

Sell-side 30m shrink projection:

```text
current 30m bucket intraday virtual amount < previous trading day's same 30m bucket full amount
```

For `BUY_HINT` / `SELL_HINT`, N4 uses only the N3-standardized 30m same-window
amount projection above; N4 does not require a separate formal price
breakthrough. Ordinary formal `BUY` / `SELL` price proof remains governed by
`docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md` and uses
`current_price/current_close` against the previous formal period entity
high/low.

N4 is allowed to generate `TriggerMatched` from N3-standardized, traceable intraday projection metrics when:

```text
match_basis=intraday_projection
```

N4 must not compute this projection from raw minute data. N3 owns the standardized, traceable projection metric. N4 only consumes it.

Closed `MinuteBarClosed` / closed 30m summary remains useful for confirmation, replay, audit, and diff analysis, but it is not the only entry point and is not required before a valid intraday projection trigger can match.

`BUY_HINT` and `SELL_HINT` require two stages:

```text
N2 proves the oversold/overbought prerequisite structure and emits the condition provenance.
N4 confirms the relevant 30m projection evidence from N3 standardized metrics.
```

Without the N2 prerequisite structure, a 30m projection is not a hint condition. Without the N4 projection evidence, a `BUY_HINT` / `SELL_HINT` condition must not become a matched trigger.

## 6. N4 Trigger State

Canonical N4 trigger states:

```text
inactive
matched
```

Canonical `trigger_live` mapping:

```text
inactive -> trigger_live=false
matched -> trigger_live=true
```

`pending_market_data` is a legacy state label. New runtime candidate/no-match
inputs do not persist. If a previous state is live and current evidence is
missing or not ready, N4 keeps the last live state instead of closing it. N4
closes only when `metric_ready=true` and formal/current evidence proves the
trigger no longer holds.

Canonical lifecycle:

```text
inactive -> matched -> inactive
```

Allowed transitions:

```text
inactive -> matched
matched -> matched when material lifecycle content changes
matched -> inactive
inactive -> inactive drop/no-op
```

Forbidden in N4:

```text
action eligibility states
execution states
user display states
sim states
```

### TriggerStateChanged

N4 must broadcast material trigger state changes with `TriggerStateChanged`.

`TriggerStateChanged` is broader than live true/false. It is emitted when a downstream consumer needs to know that the current trigger state materially changed:

```text
trigger_live changed
current_status changed
primary_trigger_period upgraded
all_trigger_periods changed
projection_30m_flag or projection_30m_type changed
trigger_mark_candidate changed
data_quality_status changed
source trace changed to a materially stronger trigger basis
```

### Lifecycle-Only Runtime Events

New N4 runtime persists only trigger lifecycle changes.  Candidate/no-match
rows are evaluated in memory and summarized in artifacts; they are not written
as per-minute trigger facts.

```text
TriggerMatched = outcome event; positive input for N5 action confirmation
TriggerStateChanged = state event; current trigger-state broadcast; never written to common_trigger_match
```

For N5, `TriggerMatched` alone creates the action-confirmation episode and
`ActionEligible`. A later `TriggerStateChanged(trigger_live=true)` does not
create another episode or `ActionEligible`; it refreshes the current live
episode and may become its `current_active_source`. It can lead to
`ActionExecuted` only when the immutable `TriggerMatched` entry remains
available and a matching `N3T_C1_CLOSED` final proof passes.

`TriggerPendingMarketData` is legacy-only.  New runtime no-match, missing
market-data, and insufficient-proof candidates are dropped by default and must
not write `common_trigger_state`, `common_trigger_match`, or
`common_event_outbox`.

If the previous lifecycle state is live but the current metric/proof is missing
or not ready, N4 must not close the state.  N4 closes only when `metric_ready=true`
and the formal/current evidence proves the trigger is no longer satisfied.

Lifecycle state identity is:

```text
run_id
trade_date
asset_kind
identity_key
direction
signal_type
condition_key
```

`trigger_period`, `trigger_bucket`, `trigger_mark_candidate`, projection fields,
and period sets are state content, not state identity.  A material content change
on an already live lifecycle emits `TriggerStateChanged`; it does not write a new
`common_trigger_match`.

`trigger_price` is activation/audit payload.  A matched -> matched replay where
only `trigger_price` changed is not a material lifecycle change and must not emit
`TriggerStateChanged`.

Runtime transition rules:

```text
inactive -> matched:
  write/update common_trigger_state
  write common_trigger_match
  emit TriggerMatched only

matched -> matched with same primary period / period set / projection / mark:
  no database write
  no event

matched -> matched with material lifecycle content change:
  write/update common_trigger_state
  emit TriggerStateChanged only
  do not write common_trigger_match

matched -> inactive:
  write/update common_trigger_state
  emit TriggerStateChanged only
  do not write common_trigger_match

inactive -> inactive:
  drop
```

`TriggerMatched` itself is the activation event, so activation must not emit an
extra `TriggerStateChanged` in the same transaction.  If the same input repeats
and lifecycle content did not materially change, N4 must not emit a duplicate.
If the state changes, such as D -> W period upgrade, all_trigger_periods
expansion, projection change, mark change, or matched -> inactive,
`TriggerStateChanged` must be emitted.

The period priority order is:

```text
Y > Q > M > W > D
```

For the same object, direction, and runtime signal, the primary trigger period may only upgrade during the same trade date. It must not downgrade.

Example:

```text
09:35 D triggers
  trigger_live=true
  primary_trigger_period=D
  all_trigger_periods=[D]
  state_change_reason=activated

10:20 W triggers
  trigger_live=true
  previous_primary_trigger_period=D
  primary_trigger_period=W
  all_trigger_periods=[D,W]
  state_change_reason=period_upgraded
```

Non-trigger state:

```text
N4 emits TriggerStateChanged with trigger_live=false when trigger conditions are no longer satisfied.
This tells N5 to stop further processing for the current trigger state and lets N6 update current display state through downstream forwarding.
It must not delete historical action, TTS, sim, or user projection facts.
```

`TriggerStateChanged` is a state transition event. It must not be written into `common_trigger_match`; it is emitted from the state transition and written only as an event outbox row.

N5 consumption rule:

```text
TriggerMatched -> may start N5 action confirmation
TriggerStateChanged -> live/state gate or downstream forwarding context only; action confirmation forbidden
TriggerPendingMarketData -> legacy-only; new runtime must not emit it
```

## 7. N5 Action State

Canonical N5 action states:

```text
eligible
blocked
executed
skipped
expired
```

N5 action state is downstream of N4 trigger state. N5 may decide that a matched trigger is eligible, blocked, executed, skipped, or expired. N5 must not update N4 trigger state to express that decision.

N5 final action confirmation rules are downstream of N4 trigger state:

| Sub-period | Buy pass | Sell pass |
|---|---|---|
| 120m | current price breaks reference real-body upper bound | current price breaks reference real-body lower bound |
| 30m | current price breaks current/previous 30m reference real-body upper bound | current price breaks current/previous 30m reference real-body lower bound |
| 5m | price breakout + current 5m average volume stronger than reference + current 5m virtual amount stronger than reference | price breakdown + current 5m average volume weaker than reference + current 5m virtual amount weaker than reference |
| 1m | current minute amount > previous minute amount and price breaks previous minute real-body upper bound | current minute amount < previous minute amount and price breaks previous minute real-body lower bound |

Minute label boundary:

```text
A 1m bar labeled HH:MM covers the HH:MM-HH:MM+1 interval and is complete only at HH:MM+1.
N5 must not use a future minute.
If the completed minute covers trigger_time, N5 may use it even when the bar label is earlier than trigger_time.
```

If N4 becomes live slightly after the relevant minute state was already true, N5 may synthesize one trigger-time action check to avoid missing the boundary. It must still pass trigger_live_now, time-boundary, channel, position/T+1 where applicable, and write-once guards.

N5 internal confirmation fields are not canonical action states:

```text
confirmation_status=pending/passed/failed/expired
tracking_until
last_checked_minute_label
```

`ActionExecuted` means only that the N5 action confirmation fact has been established and the canonical N5 action event has been emitted. It does not mean real order submission, sim trade write, N6 display, voice/TTS, mobile push, or trade-intent approval.

N5 must not introduce `ActionExpired`. Expiry is represented as:

```text
ActionSkipped(action_state=expired, reason=trigger_live_false)
ActionSkipped(action_state=expired, reason=window_expired)
```

## 8. Canonical Event Types

N4 may output only:

```text
TriggerStateChanged
TriggerMatched
```

`TriggerPendingMarketData` is legacy-only and must not be emitted by new
runtime replay/execute paths.

N5 may output only:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Deprecated for future N4/N5 canonical runtime work:

```text
TriggerLiveChanged
TriggerCleared
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

The deprecated event names may remain in historical artifacts and old runtime evidence. New implementation work must plan explicit compatibility, migration, or dual-write/read gates before changing persisted contracts.

## 9. Payload Requirements

N4 trigger event payloads must carry enough trace to prove source and basis:

```text
run_id
source_event_id or source_fact_id
source_run_id
identity_key
asset_kind
direction
condition_key
signal_type
trigger_mark_candidate
trigger_period
match_basis
data_quality_status
trace_json
```

`TriggerStateChanged` payloads must also carry:

```text
trigger_live
previous_trigger_live
current_status
previous_status
primary_trigger_period
previous_primary_trigger_period
all_trigger_periods
previous_all_trigger_periods
projection_30m_flag
projection_30m_type
previous_projection_30m_flag
previous_projection_30m_type
trigger_mark_candidate
previous_trigger_mark_candidate
state_change_reason
source_outcome_event_type
source_outcome_event_id
```

For intraday projection matches:

```text
match_basis=intraday_projection
projection_run_id required
projection_metric_id or equivalent trace id required
```

N5 action event payloads must carry:

```text
run_id
source_trigger_event_id
source_trigger_run_id
identity_key
asset_kind
direction
condition_key
signal_type
action_mark
action_state
action_policy
eligibility_reason
trace_json
```

Payload rule:

```text
condition_key is trace/audit/analytics only
N4 trigger buy/sell semantics must be read from signal_type plus trigger_mark_candidate/projection evidence
N5 final action semantics must be read from signal_type and action_mark
N4/N5 signal_type must be B_BUY or S_SELL only
alert-only / display label / voice / sim / trade intent are not N4/N5 payload semantics
```

## 10. Runtime Guards

Every N4/N5/N6 runtime runner must prove:

```text
layer_role is correct
input run_id allowlist is explicit
old synthetic/stale runs are excluded where applicable
idempotency key is stable
rollback scope is run_id scoped
downstream consumption guard exists before rollback
worker is not started unless separately authorized
real trading is not executed
```

## 11. Alignment Rule

Existing code and historical reports may still contain the previous names:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT as signal_type
SELL_HINT as signal_type
TriggerCleared
TriggerLiveChanged
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

Those are current divergence items, not canonical future runtime semantics. Future alignment work must migrate N4/N5/N6 contracts, schemas, tests, dry-run reports, and rollback plans deliberately. It must not silently rewrite past run evidence.

If `B_BUY_30M_VOL`, `S_SELL_30M_SHRINK`, `BUY_HINT`, or `SELL_HINT` remain visible as historical `condition_key`, legacy `allowed_signal_types`, report dimensions, or trace fields, they remain trace/audit/analytics only and must not be promoted back into runtime `signal_type`.
