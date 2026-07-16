# N4 Trigger Rule Spec, Fully Atomic Version

Status: canonical_registered

Frozen at: 2026-06-26

Effective at: 2026-06-26

Scope: N4 trigger-side rule definitions only.

Registration status:

```text
registered_by = docs/N4_TRIGGER_ATOMIC_CANONICAL_REGISTRATION_GATE.md
layer_role = N4_trigger
historical_runs_rewritten = false
historical_runs_superseded = false
```

This draft is documentation-only:

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

This document defines N4 rules for:

```text
BUY
SELL
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

This document does not define:

```text
N5 action confirmation
N6 user presentation
voice/mobile/sim/trade intent
real trade execution
```

## 1. Allowed N4 Outputs

N4 may emit only these standard outputs:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
```

Boundary rules:

```text
Only TriggerMatched may enter N5 action confirmation entry.
TriggerPendingMarketData must not create ActionEligible.
TriggerPendingMarketData must not create ActionExecuted.
TriggerStateChanged may be consumed by N5 as state-gate / active-ref-refresh input only.
TriggerStateChanged(trigger_live=true,current_status=matched) may refresh an executable active ref with action_eligible_entry_allowed=false.
TriggerStateChanged(trigger_live=false) may expire/remove a matching active ref.
TriggerStateChanged allowed uses = update_context / expire_window / live-state synchronization / active_ref_refresh.
TriggerStateChanged must not create ActionEligible.
TriggerStateChanged must not directly create ActionExecuted without matching N3T_C1_CLOSED proof.
TriggerStateChanged must not be treated as action confirmation entry.
```

## 2. Input Model

Every N4 candidate is evaluated using two input groups.

### 2.1 N2 Frozen Context

N2 frozen context provides static reference baselines. It must provide at least:

```text
condition_key
direction
previous_transition
trigger_previous_entity_high
trigger_previous_entity_low
previous_avg_amount
upper-period chain baseline inputs
```

### 2.2 N3 Realtime Inputs

N3 realtime inputs provide current numeric values. They must provide at least:

```text
current_price_or_close
current_period_avg_with_today[P]
trigger_amount_chain_pass[P]
current_30m_virtual_amount
reference_30m_amount
```

## 3. Atomic Field Definitions

Every field below has exactly one meaning in this document.

### 3.1 `condition_key`

Definition:

- The condition-type string for the current N4 candidate.

Allowed examples:

```text
BUY
SELL
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
BUY:M
BUY:W,D
SELL:M,W,D
```

Role:

- Selects the N4 rule path for the candidate.

### 3.2 `direction`

Definition:

- The trading direction of the current candidate.

Allowed values:

```text
buy
sell
```

Mapping:

```text
BUY / BUY:FULL / BUY_HINT -> buy
SELL / SELL:FULL / SELL_HINT -> sell
```

Role:

- Selects the price comparison direction.
- Selects the target transition direction.

### 3.3 `current_price_or_close`

Definition:

- The single scalar price used by N4 at the current evaluation time.

Properties:

```text
single numeric value
not a range
not an array
not a historical aggregate
```

Role:

- Compared against `trigger_previous_entity_high` or `trigger_previous_entity_low`.

### 3.4 `trigger_previous_entity_high`

Definition:

- The body-high of the previous complete reference period.

Formula:

```text
trigger_previous_entity_high = max(previous_open, previous_close)
```

Exclusions:

```text
does not use wick high
does not use trade-time max price
```

Role:

- Buy-side price break threshold.

### 3.5 `trigger_previous_entity_low`

Definition:

- The body-low of the previous complete reference period.

Formula:

```text
trigger_previous_entity_low = min(previous_open, previous_close)
```

Exclusions:

```text
does not use wick low
does not use trade-time min price
```

Role:

- Sell-side price break threshold.

### 3.6 `current_period_avg_with_today[P]`

Definition:

- The current same-period average virtual amount including today's current virtual amount.

Properties:

```text
period-indexed numeric value
same-period transition amount comparison input
```

Period mapping:

```text
D -> today_virt_amount
W -> weekly_avg_with_today
M -> monthly_avg_with_today
Q -> quarterly_avg_with_today
Y -> yearly_avg_with_today
```

Clarification:

```text
current_period_avg_with_today[P] must use the same period as P.
For P=M, it is monthly_avg_with_today.
For P=W, it is weekly_avg_with_today.
For P=Q, it is quarterly_avg_with_today.
For P=D, it is today_virt_amount.
```

Role:

- Used only by `BUY`, `SELL`, `BUY:FULL`, `SELL:FULL`.
- It is the current-side transition amount input for period `P`.
- It must not be collapsed into one unindexed `today_virt_amount` for all periods.

### 3.7 `previous_avg_amount`

Definition:

- The N2-frozen previous complete same-period average amount used by N4 as the transition amount baseline.

Value selection priority:

```text
1. previous_avg_amount
2. previous_amount
3. previous_amount_baseline
4. classification_previous_amount_baseline
```

Selection rule:

```text
Use the first existing value in the priority order above.
If none exist, previous_avg_amount is missing.
```

Role:

- Amount comparison baseline for `BUY`, `SELL`, `BUY:FULL`, `SELL:FULL`.
- This field is period-specific. For period `P`, read it as `previous_avg_amount[P]`.
- The transition amount comparison is therefore:

```text
current_period_avg_with_today[P]
vs
previous_avg_amount[P]
```

It is not:

```text
today_virt_amount reused for every period P
```

### 3.7.1 Period Baseline Freshness Guard

N4 must not recalculate N1 daily facts at runtime. Before using an N2-frozen
baseline for W/M/Q/Y, N4 must verify that the baseline belongs to the current
period containing `for_trade_date`.

Guard:

```text
D: no rollover guard
W/M/Q/Y:
  baseline.period_key_current must equal period_key(for_trade_date, P)
```

If `period_key_current` is missing, malformed, or not equal to the expected
period key, only that period is blocked:

```text
classification = quality_blocked
reason = stale_period_baseline_for_trade_date_rollover
output_event_type = none
TriggerPendingMarketData = false
N5 entry = false
```

Trace must retain:

```text
baseline_period_key_current
expected_period_key_current
baseline_period_key_previous
baseline_source_trade_date
for_trade_date
stale_period_baseline
stale_period_baseline_reason
```

Multi-period conditions evaluate independently. For example, stale W in
`BUY:W,D` does not block D; only actually triggered periods participate in
priority selection.

### 3.8 `previous_transition`

Definition:

- The N2-frozen previous state label for the evaluated period.

Allowed values include at least:

```text
volume_up
low_volume_up
low_volume_down
volume_down
other
```

Role:

- Determines whether current state is an upgrade to the target state.

### 3.9 `current_transition`

Definition:

- The current state label computed by N4 from current price and current amount relations.

Allowed values:

```text
volume_up
low_volume_up
low_volume_down
volume_down
other
```

### 3.10 `trigger_amount_chain_pass[P]`

Definition:

- The formal amount-chain gate result for period `P`.

Allowed values:

```text
true
false
not_applicable
```

Meaning:

- `true` means the formal upper-period amount chain is satisfied.
- `false` means the formal upper-period amount chain is not satisfied.
- `not_applicable` means there is no higher-period chain for the period.

It is not:

```text
not a single-step amount comparison
not the definition of current_transition
not a projection_30m_type input
```

### 3.11 `current_30m_virtual_amount`

Definition:

- The current 30-minute window virtual full amount at the current evaluation time.

Meaning:

- It is the amount obtained by calibrating the current partial 30-minute window into a full-window amount.

Role:

- Hint-path current amount input.

### 3.12 `reference_30m_amount`

Definition:

- The full amount of the previous trade date same-position 30-minute window.

Same-position definition:

```text
If the current minute belongs to the Nth 30m window of today,
reference_30m_amount is the full amount of the Nth 30m window of the previous trade date.
```

It is not:

```text
not today's previous 30m amount
not a partial previous-day amount
not an arbitrary average amount
```

Role:

- Hint-path amount comparison baseline.

### 3.13 `current_30m_price`

Definition:

- The single scalar price of the current 30-minute projection window at N4 evaluation time.

Properties:

```text
single numeric value
not a range
not a historical aggregate
not an amount field
```

Role:

- Hint-path price break input.

### 3.14 `reference_30m_entity_high`

Definition:

- The entity high of the immediately adjacent previous complete 30-minute K line.

Formula:

```text
reference_30m_entity_high = max(previous_30m_open, previous_30m_close)
```

It is not:

```text
not the wick high
not today's highest price
not a D/W/M/Q/Y period high
```

Role:

- BUY_HINT 30-minute price break threshold.

### 3.15 `reference_30m_entity_low`

Definition:

- The entity low of the immediately adjacent previous complete 30-minute K line.

Formula:

```text
reference_30m_entity_low = min(previous_30m_open, previous_30m_close)
```

It is not:

```text
not the wick low
not today's lowest price
not a D/W/M/Q/Y period low
```

Role:

- SELL_HINT 30-minute price break threshold.

### 3.16 `projection_30m_type`

Definition:

- The 30-minute projection direction classification.

Allowed values:

```text
volume_up
shrink_down
none
unknown
```

### 3.17 `projection_30m_flag`

Definition:

- The boolean field indicating whether the 30-minute projection is directly usable by N4 hint rules.

Allowed values:

```text
true
false
```

## 4. Formal Amount Chain Definition

### 4.1 General Rule

`trigger_amount_chain_pass[P]` is the formal upper-period amount-chain gate for period `P`.

It is separate from the transition amount comparison:

```text
transition amount comparison:
current_period_avg_with_today[P]
compared with previous_avg_amount[P]

amount-chain comparison:
period-specific average chain fields, for example
monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
```

Supported periods:

```text
D
W
M
Q
Y
```

### 4.2 BUY Direction Chain Rules

#### `trigger_amount_chain_pass[D]`

```text
trigger_amount_chain_pass[D] = true
iff
today_virt_amount >= weekly_avg_with_today
AND weekly_avg_with_today >= prev_weekly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[D] = false
```

#### `trigger_amount_chain_pass[W]`

```text
trigger_amount_chain_pass[W] = true
iff
weekly_avg_with_today >= monthly_avg_with_today
AND monthly_avg_with_today >= prev_monthly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[W] = false
```

#### `trigger_amount_chain_pass[M]`

```text
trigger_amount_chain_pass[M] = true
iff
monthly_avg_with_today >= quarterly_avg_with_today
AND quarterly_avg_with_today >= prev_quarterly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[M] = false
```

#### `trigger_amount_chain_pass[Q]`

```text
trigger_amount_chain_pass[Q] = true
iff
quarterly_avg_with_today >= yearly_avg_with_today
AND yearly_avg_with_today >= prev_yearly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[Q] = false
```

#### `trigger_amount_chain_pass[Y]`

```text
trigger_amount_chain_pass[Y] = not_applicable
```

Interpretation:

```text
Y has no higher formal period.
not_applicable is not true.
not_applicable is not false.
not_applicable means no upper-period amount-chain gate exists for Y.
```

### 4.3 SELL Direction Chain Rules

#### `trigger_amount_chain_pass[D]`

```text
trigger_amount_chain_pass[D] = true
iff
today_virt_amount <= weekly_avg_with_today
AND weekly_avg_with_today <= prev_weekly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[D] = false
```

#### `trigger_amount_chain_pass[W]`

```text
trigger_amount_chain_pass[W] = true
iff
weekly_avg_with_today <= monthly_avg_with_today
AND monthly_avg_with_today <= prev_monthly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[W] = false
```

#### `trigger_amount_chain_pass[M]`

```text
trigger_amount_chain_pass[M] = true
iff
monthly_avg_with_today <= quarterly_avg_with_today
AND quarterly_avg_with_today <= prev_quarterly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[M] = false
```

#### `trigger_amount_chain_pass[Q]`

```text
trigger_amount_chain_pass[Q] = true
iff
quarterly_avg_with_today <= yearly_avg_with_today
AND yearly_avg_with_today <= prev_yearly_avg
```

Otherwise:

```text
trigger_amount_chain_pass[Q] = false
```

#### `trigger_amount_chain_pass[Y]`

```text
trigger_amount_chain_pass[Y] = not_applicable
```

### 4.4 Role of `trigger_amount_chain_pass[P]`

Its only role is:

```text
formal second gate for BUY / SELL / BUY:FULL / SELL:FULL
```

It does not define:

```text
current_transition
projection_30m_type
projection_30m_flag
```

### 4.5 Ordinary period escalation prerequisite v2

N4 ordinary `BUY` / `SELL` uses the versioned N2 prerequisite context at:

```text
period_trigger_baseline_json.period_escalation_context
contract_version = N2-period-escalation-context-v1
generation_mode = N2-period-escalation-daily-incremental-v1  # new incremental evidence
```

The N4 policy trace is:

```text
ordinary_period_escalation_policy_version = N4-ordinary-period-escalation-v2
ordinary_period_escalation_policy_hash = stable hash of the N4 policy
```

This gate applies only to ordinary W/M/Q/Y periods:

```text
W <- D  directions[direction].W  window_kind=week
M <- W  directions[direction].M  window_kind=month
Q <- M  directions[direction].Q  window_kind=quarter
Y <- Q  directions[direction].Y  window_kind=year
```

`window_kind` is canonical. `window_type` is not an accepted alias.

N4 must validate the frozen N2 context without recomputing it. Validation includes:

```text
contract_version
source_layer = N2_condition
asset_kind
identity_key
for_trade_date
source_trade_date
direction
target_period
prerequisite_period
window_kind
window_key
window_start
observation_end
reset_for_trade_date
required_transition
status
coverage_status
seen
coverage counts and missing dates
entry_hash
context_hash
```

Direction transitions are fixed:

```text
buy  -> volume_up
sell -> low_volume_down
```

For P in W/M/Q/Y, N4 first computes the current same-direction formal-pass
period set from the current localized context plus the current N3 formal period
metrics. A condition key naming a period is not evidence that the period passed.

The same-day direct rules are:

```text
W = current W formal pass AND current D formal pass
M = current M formal pass AND current W formal pass
Q = current Q formal pass AND current M formal pass
Y = current Y formal pass AND current Q formal pass
```

This direct path does not use previous trigger state or historical N2 evidence.
It records:

```text
evidence_source = current_same_day_formal_pass
triggered_periods = [target period]
all_trigger_periods = [target period, prerequisite period]
primary_trigger_period = target period
prerequisite_periods = [prerequisite period]
```

Therefore `[D,W]`, `[W,M]`, `[M,Q]`, and `[Q,Y]` upgrade to W, M, Q,
and Y respectively. When several adjacent periods pass, a period used as the
same-day prerequisite of a higher target is not duplicated in
`triggered_periods`; it remains visible in `all_trigger_periods` and the audit
trace.

The production provisional ordinary adapter must preserve the matcher output
without recomputing or narrowing it. The matcher plan, lifecycle plan,
`common_trigger_match.raw_json`, and N4 outbox payload must carry the same:

```text
triggered_periods
all_trigger_periods
primary_trigger_period
prerequisite_periods
period_escalation_trace
ordinary_period_escalation_policy_version
ordinary_period_escalation_policy_hash
```

For v2 `current_same_day_formal_pass`, missing fields, reversed period order,
direction conflicts, policy/hash conflicts, or a target/prerequisite pair not
present in the current formal-pass evidence must fail closed. The adapter must
not replace missing `all_trigger_periods` with `triggered_periods`, infer the
direction from `condition_key`, or treat a condition-key period as formal-pass
evidence. This forwarding rule changes no event ID, dedup key, lifecycle state
identity, or N5 intake boundary.

When the same-day direct rule is not proven, N4 falls back to the frozen N2
context. For P in W/M/Q/Y:

```text
ordinary_formal_pass_v2[P] =
  existing_formal_pass[P]
  AND prerequisite_gate_pass[P]

prerequisite_gate_pass[P] =
  status = ready
  AND seen = true
  AND (
    coverage_status = passed with complete coverage
    OR generation_mode = N2-period-escalation-daily-incremental-v1
       AND coverage_status = incomplete with exact missing-date accounting
  )
  AND all contract and integrity checks pass
```

Status semantics:

```text
ready:
  prerequisite observed; exact complete or incomplete coverage proof is retained
  and the gate may pass

not_seen:
  complete coverage and prerequisite not observed; deterministic no-op

not_ready:
  incomplete coverage; quality-blocked and not equivalent to not_seen

missing / malformed / wrong version / wrong direction / wrong window / hash mismatch:
  quality-blocked for that high period
```

D does not use this prerequisite gate. `BUY:FULL`, `SELL:FULL`, `BUY_HINT`, and
`SELL_HINT` keep their separate rule branches and must not read this context.

Current formal periods and N2 prerequisites remain separate on the fallback
path:

```text
triggered_periods = periods that pass the current realtime formal rule and prerequisite gate
all_trigger_periods = triggered_periods, plus only same-day formal prerequisites
primary_trigger_period = highest current formal period
prerequisite_periods = prerequisite periods used by triggered high periods
period_escalation_trace = optional audit trace of every requested high-period gate
```

`all_trigger_periods` must not union `previous_all_trigger_periods` and must not
contain an N2 historical prerequisite unless that period also passes its own
current formal rule. The v4 plan exposes the aggregate trace directly. The provisional
ordinary event path preserves the same evidence under
`rule_proof.period_evaluation_details[*]` and
`rule_proof.triggered_period_details[*]` without changing event schema v1.

Lifecycle identity and dedup keys do not include the prerequisite audit trace:

```text
inactive -> matched: TriggerMatched only
matched -> matched unchanged: no-op
matched -> matched with current period-set change: TriggerStateChanged only
not_ready with no other ready formal evidence: preserve the existing live state
```

If same-day formal evidence is absent, new-policy runs require the v1 context.
`not_ready`, malformed context, a wrong direction/window/version, or a hash
mismatch blocks only that high-period rule. D, `BUY:FULL`, `SELL:FULL`,
`BUY_HINT`, and `SELL_HINT` do not use this gate and remain unchanged.

The only in-code legacy exception is the explicitly frozen historical replay
lineage:

```text
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

That lineage is marked `legacy_replay`, uses its frozen old period rule, and does
not create prerequisite facts. Its frozen output may retain the old previous-set
union; the v2 path must never do so. Other missing contexts fail closed unless
the current same-day formal pair is proven. Historical runs are never backfilled
or rewritten. This contract changes no lifecycle rule, event schema, event ID,
dedup key, N5 intake boundary, physical column, or DDL migration.

## 5. Ordinary BUY Rules

Applicable to:

```text
BUY:Y
BUY:Q
BUY:M
BUY:W
BUY:D
BUY:W,D
BUY combinations with one or more ordinary periods
```

### 5.1 `price_pass_buy`

```text
price_pass_buy = true
iff
current_price_or_close > trigger_previous_entity_high
```

Otherwise:

```text
price_pass_buy = false
```

### 5.2 `amount_up_pass_buy`

```text
amount_up_pass_buy = true
iff
current_period_avg_with_today[P] > previous_avg_amount[P]
```

Otherwise:

```text
amount_up_pass_buy = false
```

### 5.3 `amount_down_pass_buy`

```text
amount_down_pass_buy = true
iff
current_period_avg_with_today[P] < previous_avg_amount[P]
```

Otherwise:

```text
amount_down_pass_buy = false
```

### 5.4 `current_transition` for BUY

```text
If price_pass_buy = true
AND amount_up_pass_buy = true
=> current_transition = volume_up
```

```text
If price_pass_buy = true
AND amount_down_pass_buy = true
=> current_transition = low_volume_up
```

```text
All other cases
=> current_transition = other
```

### 5.5 `TriggerMatched(BUY:P)`

```text
TriggerMatched(BUY:P)
iff
previous_transition != volume_up
AND current_transition == volume_up
AND trigger_amount_chain_pass[P] = true
```

Expanded form:

```text
TriggerMatched(BUY:P) =
current_price_or_close > trigger_previous_entity_high
AND current_period_avg_with_today[P] > previous_avg_amount[P]
AND previous_transition != volume_up
AND trigger_amount_chain_pass[P] = true
```

## 6. Ordinary SELL Rules

Applicable to:

```text
SELL:Y
SELL:Q
SELL:M
SELL:W
SELL:D
SELL:M,W,D
SELL combinations with one or more ordinary periods
```

### 6.1 `price_pass_sell`

```text
price_pass_sell = true
iff
current_price_or_close < trigger_previous_entity_low
```

Otherwise:

```text
price_pass_sell = false
```

### 6.2 `amount_down_pass_sell`

```text
amount_down_pass_sell = true
iff
current_period_avg_with_today[P] < previous_avg_amount[P]
```

Otherwise:

```text
amount_down_pass_sell = false
```

### 6.3 `amount_up_pass_sell`

```text
amount_up_pass_sell = true
iff
current_period_avg_with_today[P] > previous_avg_amount[P]
```

Otherwise:

```text
amount_up_pass_sell = false
```

### 6.4 `current_transition` for SELL

```text
If price_pass_sell = true
AND amount_down_pass_sell = true
=> current_transition = low_volume_down
```

```text
If price_pass_sell = true
AND amount_up_pass_sell = true
=> current_transition = volume_down
```

```text
All other cases
=> current_transition = other
```

### 6.5 `TriggerMatched(SELL:P)`

```text
TriggerMatched(SELL:P)
iff
previous_transition != low_volume_down
AND current_transition == low_volume_down
AND trigger_amount_chain_pass[P] = true
```

Expanded form:

```text
TriggerMatched(SELL:P) =
current_price_or_close < trigger_previous_entity_low
AND current_period_avg_with_today[P] < previous_avg_amount[P]
AND previous_transition != low_volume_down
AND trigger_amount_chain_pass[P] = true
```

## 7. Full BUY Rules

Applicable to:

```text
BUY:FULL
```

### 7.1 `current_transition = volume_up`

```text
current_transition = volume_up
iff
current_price_or_close > trigger_previous_entity_high
AND current_period_avg_with_today[P] > previous_avg_amount[P]
```

### 7.2 `TriggerMatched(BUY:FULL)`

```text
TriggerMatched(BUY:FULL)
iff
current_transition == volume_up
AND trigger_amount_chain_pass[P] = true
```

Expanded form:

```text
TriggerMatched(BUY:FULL) =
current_price_or_close > trigger_previous_entity_high
AND current_period_avg_with_today[P] > previous_avg_amount[P]
AND trigger_amount_chain_pass[P] = true
```

Difference from ordinary BUY:

```text
BUY:FULL does not require previous_transition != volume_up
```

## 8. Full SELL Rules

Applicable to:

```text
SELL:FULL
```

### 8.1 `current_transition = low_volume_down`

```text
current_transition = low_volume_down
iff
current_price_or_close < trigger_previous_entity_low
AND current_period_avg_with_today[P] < previous_avg_amount[P]
```

### 8.2 `TriggerMatched(SELL:FULL)`

```text
TriggerMatched(SELL:FULL)
iff
current_transition == low_volume_down
AND trigger_amount_chain_pass[P] = true
```

Expanded form:

```text
TriggerMatched(SELL:FULL) =
current_price_or_close < trigger_previous_entity_low
AND current_period_avg_with_today[P] < previous_avg_amount[P]
AND trigger_amount_chain_pass[P] = true
```

Difference from ordinary SELL:

```text
SELL:FULL does not require previous_transition != low_volume_down
```

## 9. Hint Projection Type Rules

### 9.1 `projection_30m_type = unknown`

```text
projection_30m_type = unknown
iff
current_30m_virtual_amount is missing
OR reference_30m_amount is missing
OR current_30m_price is missing
OR reference_30m_entity_high / reference_30m_entity_low is missing for the required direction
```

### 9.2 `projection_30m_type = volume_up`

```text
projection_30m_type = volume_up
iff
current_30m_virtual_amount > reference_30m_amount
AND current_30m_price > reference_30m_entity_high
```

### 9.3 `projection_30m_type = shrink_down`

```text
projection_30m_type = shrink_down
iff
current_30m_virtual_amount < reference_30m_amount
AND current_30m_price < reference_30m_entity_low
```

### 9.4 `projection_30m_type = none`

```text
projection_30m_type = none
iff
required fields exist
AND projection_30m_type is not volume_up
AND projection_30m_type is not shrink_down
```

Precondition:

```text
All amount and price fields required by the candidate direction exist.
```

### 9.5 `projection_30m_flag`

```text
If projection_30m_type = volume_up
=> projection_30m_flag = true
```

```text
If projection_30m_type = shrink_down
=> projection_30m_flag = true
```

```text
If projection_30m_type = none
=> projection_30m_flag = false
```

```text
If projection_30m_type = unknown
=> projection_30m_flag = false
```

## 10. BUY_HINT Rules

Applicable to:

```text
BUY_HINT
```

Asset scope:

```text
asset_kind IN (index, board)
stock is not applicable
```

Definition:

```text
TriggerMatched(BUY_HINT)
iff
asset_kind IN (index, board)
AND
projection_30m_flag = true
AND projection_30m_type = volume_up
```

Expanded form:

```text
TriggerMatched(BUY_HINT) =
asset_kind IN (index, board)
AND current_30m_virtual_amount > reference_30m_amount
AND current_30m_price > reference_30m_entity_high
```

## 11. SELL_HINT Rules

Applicable to:

```text
SELL_HINT
```

Asset scope:

```text
asset_kind IN (index, board)
stock is not applicable
```

Definition:

```text
TriggerMatched(SELL_HINT)
iff
asset_kind IN (index, board)
AND
projection_30m_flag = true
AND projection_30m_type = shrink_down
```

Expanded form:

```text
TriggerMatched(SELL_HINT) =
asset_kind IN (index, board)
AND current_30m_virtual_amount < reference_30m_amount
AND current_30m_price < reference_30m_entity_low
```

### 11.1 HINT proof run_id suffix compatibility

N4 HINT/projection execute accepts only these exact N3 proof suffixes in
`realtime_hint_projection_metric` source run_id and corresponding
`trigger_provisional_b2` target run_id:

```text
index_board_1m_hint_projection_v1
index_board_1m_hint_projection_v1_midday_bridge_v1
```

`index_board_1m_hint_projection_v1_midday_bridge_v1` is a source-lineage
compatibility suffix for the N3 midday bridge supersession proof. It does not
change N4 HINT matcher semantics: `BUY_HINT` still requires
`projection_30m_type=volume_up`, and `SELL_HINT` still requires
`projection_30m_type=shrink_down`.

Unknown suffixes such as `midday_bridge_v2`, non-index/board asset scopes, and
missing `atomic_rule_v1` suffix must fail closed.

### 11.2 HINT previous baseline selection

N4 HINT/projection execute must use an explicit previous-baseline policy.

Allowed modes:

```text
no_previous_baseline=true
previous_trigger_run_id=<exact trigger_provisional_b2 HINT target>
```

`no_previous_baseline=true` means this HINT run is evaluated from an empty
previous state set. The runner must not query same-day ordinary trigger states.

`previous_trigger_run_id` must be an exact passed HINT/projection target:

```text
trigger_provisional_b2_*__realtime_hint_projection_metric_*__asset_index_board__...
```

Forbidden baseline behavior:

```text
implicit same-day previous state lookup for HINT
wildcard latest HINT target selection
ordinary target state as HINT baseline
cross-day HINT baseline unless explicitly reviewed by a separate gate
```

Ordinary and HINT state families are isolated. A HINT execute without
`no_previous_baseline=true` or an exact HINT `previous_trigger_run_id` must fail
closed with `BLOCKED_PREVIOUS_BASELINE_POLICY_UNSAFE`.

### 11.3 Intraday proof-discovery poller contract

N4 may use a bounded one-shot proof-discovery poller to discover already
persisted N3 proof targets and build exact child argv for N4 ordinary/HINT
run-once wrappers.

Poller scope:

```text
plan-only by default
no DB writes in patch/preflight gates
no child execution unless a later execute gate explicitly authorizes it
no outbox/inbox/checkpoint consumption or update
no N5/N6 entry
no worker/launchd start, stop, load, or unload
no rollback execution
```

Bounded execute behavior:

```text
plan-only remains the default and executes zero child commands
execute requires both --execute and --user-confirmed
--execute without --user-confirmed blocks
--user-confirmed without --execute blocks
execute first builds the same discovery plan used by plan-only mode
selected child wrappers run sequentially: ordinary first, then HINT
each child argv must be the audited exact argv from the discovery plan plus --execute --user-confirmed
first child failure blocks the poller and stops later children
all selected children returning 0 -> status=passed, exit code 0
no selected candidates -> status=noop, exit code 0
any child returning non-zero -> status=blocked, non-zero exit code
child stdout/stderr/returncode must be preserved in the poller report
```

Realtime source-selection policy:

```text
Default launchd/realtime selection mode is:
  selection_mode=realtime_latest_only

In realtime_latest_only mode, each poll interval evaluates the newest valid N3
proof per family first. If that newest proof has no exact N4 target, the poller
may select it. If the newest proof already has a passed exact target, the family
returns noop/idempotent for that interval. Older unprocessed proofs must not be
auto-executed by the realtime worker; they must be reported as:
  backlog_requires_manual_catchup=true
  backlog_candidate_count=<count>
  backlog_candidate_run_ids=[...]
  skipped_candidates[].reason=backlog_requires_manual_catchup

Manual backlog processing must use an explicit non-launchd catch-up gate and an
explicit selection mode such as selection_mode=catchup_latest_unprocessed. The
launchd plan must not default to catch-up mode.
```

Python executable contract:

```text
launchd parent ProgramArguments[0] and poller --python-executable must both use:
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
N4 proof-discovery poller must build ordinary/HINT child argv with that same
absolute Python path. Child argv must not start with bare `python3`, because
launchd PATH can resolve it to an incompatible system Python. Reports may show
the Python executable path, but must continue to redact DSN passwords.
```

DSN and report contract:

```text
N4 proof-discovery poller accepts --dsn or ASHARE_V3_POSTGRES_DSN for DB
discovery. When it builds ordinary/HINT child argv, it must propagate an
explicit --dsn to each child wrapper so launchd smoke is deterministic.
Reports must redact any DSN password; runtime child execution may receive the
raw DSN, but child argv persisted in JSON/MD reports must only contain the
redacted DSN. If execute invokes child commands, both side_effects.child_executed
and forbidden_operation_proof.child_executed must be true; all forbidden
downstream flags must remain false.
```

Existing-target idempotency and baseline metadata compatibility:

```text
If an exact proposed N4 target already exists, the proof-discovery poller must
fail closed unless the target is passed, source_run_id matches the selected N3
proof exactly, outbox delivered/delivering count is zero, and persisted run
counts match actual state/match/outbox rows.

Older N4 targets may lack previous_trigger_run_id metadata even when they were
executed with the correct previous baseline. This is a metadata-only
compatibility gap. The poller may treat the exact target as idempotent only when
the source and counts above are verified, downstream refs are absent, and the
only mismatch is missing legacy baseline metadata. Reports must include:
  baseline_policy=baseline_metadata_compat_pass
  baseline_policy_compat_reason=missing_or_legacy_baseline_metadata_with_verified_exact_source_and_counts

Wrong source, count drift, dirty status, delivered/delivering outbox, downstream
refs, or non-empty conflicting baseline metadata remain hard blockers. The
poller must not rewrite, delete, or supersede the existing target in this
compatibility path.
```

Ordinary discovery accepts only passed N3P proof targets:

```text
realtime_action_confirmation_metric_<date>_until_<hhmm>
__asset_all
__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1
__market_data_subscription_<date>_condition_layer_<source_date>_source_<source_date>_for_<date>_v*
```

Persisted proof rows must carry:

```text
metric_role=trigger_proof
proof_owner=N3
proof_consumer=N4
not_n5_final_proof=true
row_count > 0
```

HINT discovery accepts only passed index/board HINT proof targets:

```text
realtime_hint_projection_metric_<date>_until_<hhmm>
__asset_index_board
__index_board_1m_hint_projection_v1_midday_bridge_v1
__market_data_subscription_<date>_condition_layer_<source_date>_source_<source_date>_for_<date>_v*
```

Persisted HINT proof rows must carry:

```text
metric_role=hint_trigger_proof
proof_owner=N3
proof_consumer=N4
not_n5_final_proof=true
stock rows absent
index/board rows valid
```

Baseline selection:

```text
ordinary first same-day target -> baseline_mode=no_previous_baseline
ordinary later same-day target -> previous_trigger_run_id=<latest exact prior ordinary target>
HINT first same-day target -> no_previous_baseline=true
HINT later same-day target -> previous_trigger_run_id=<latest exact prior HINT target>
ordinary never uses HINT baseline
HINT never uses ordinary baseline
```

Idempotency:

```text
exact passed N4 target with same source/baseline/counts -> idempotent skip
dirty or source-mismatched exact N4 target -> block
delivered/delivering outbox refs on exact target -> block overwrite/rollback path
```

## 12. Multi-Period Resolution

If `condition_key` contains multiple periods, for example:

```text
BUY:W,D
SELL:M,W,D
```

Then:

```text
Evaluate each period P independently.
Add every triggered period to triggered_periods.
Set trigger_period to the highest-priority triggered period.
```

Fixed priority order:

```text
Y > Q > M > W > D
```

## 13. Output Result Definitions

### 13.1 `TriggerMatched`

Definition:

- Emitted only when the rule path's formal trigger condition is satisfied.

Output requirements:

```text
current_status = matched
trigger_live = true
```

Required payload fields:

```text
triggered_periods
trigger_period
trigger_price
condition_key
signal_type
trigger_type
trigger_mark_candidate
```

### 13.2 `TriggerPendingMarketData`

Definition:

- Emitted only when required fields for formal evaluation are missing.

Output requirements:

```text
trigger_live = false
```

### 13.3 `TriggerStateChanged`

Definition:

- Emitted only when state content changes but formal `TriggerMatched` is not produced.

Output requirements:

```text
trigger_live = false
```

HINT lifecycle baseline rule:

- The explicit previous HINT target is the safe upper-bound anchor for baseline
  selection, not a complete live-state snapshot by itself.
- HINT execute must compare current rows against the latest carried-forward
  same-day HINT lifecycle state up to that previous target.
- If an object is already live matched and the current HINT row has the same
  bucket, projection type, mark, periods, direction, signal, and condition, N4
  must no-op instead of emitting another `TriggerMatched`.
- If that carried-forward state is absent, N4 may treat the row as a true
  inactive -> matched activation and emit `TriggerMatched`.

## 14. N5 Boundary

```text
TriggerMatched may enter N5.
TriggerPendingMarketData must not enter N5.
TriggerStateChanged may enter N5 only as state-gate / active-ref-refresh input.
TriggerStateChanged must not enter N5 as ActionEligible or action confirmation entry.
```

## 15. Final Compact Form

### `BUY:P`

```text
TriggerMatched(BUY:P) =
current_price_or_close > trigger_previous_entity_high
AND current_period_avg_with_today[P] > previous_avg_amount[P]
AND previous_transition != volume_up
AND trigger_amount_chain_pass[P] = true
```

### `SELL:P`

```text
TriggerMatched(SELL:P) =
current_price_or_close < trigger_previous_entity_low
AND current_period_avg_with_today[P] < previous_avg_amount[P]
AND previous_transition != low_volume_down
AND trigger_amount_chain_pass[P] = true
```

### `BUY:FULL`

```text
TriggerMatched(BUY:FULL) =
current_price_or_close > trigger_previous_entity_high
AND current_period_avg_with_today[P] > previous_avg_amount[P]
AND trigger_amount_chain_pass[P] = true
```

### `SELL:FULL`

```text
TriggerMatched(SELL:FULL) =
current_price_or_close < trigger_previous_entity_low
AND current_period_avg_with_today[P] < previous_avg_amount[P]
AND trigger_amount_chain_pass[P] = true
```

### `BUY_HINT`

```text
TriggerMatched(BUY_HINT) =
asset_kind IN (index, board)
AND current_30m_virtual_amount > reference_30m_amount
AND current_30m_price > reference_30m_entity_high
```

### `SELL_HINT`

```text
TriggerMatched(SELL_HINT) =
asset_kind IN (index, board)
AND current_30m_virtual_amount < reference_30m_amount
AND current_30m_price < reference_30m_entity_low
```
