# N4 HINT 30m Trigger Period Semantic Repair Proposal

## Result

PROPOSAL_READY_FOR_RUNTIME_CONTROL_REVIEW

Layer role: `N4_trigger`

Generated at: `2026-06-08`

This document is a proposal for runtime_control review. It does not execute N4, does not write business DB rows, does not consume outbox, and does not enter N5/N6.

## 1. Problem Statement

The latest N4 projection matcher v4 enforcement repair correctly blocked the 20260608 breach where ordinary projection matcher output wrote non-compliant `TriggerMatched` events with:

- missing `trigger_price`
- missing `trigger_kind`
- missing `n5_entry_allowed`
- `trigger_period=30m`
- `primary_trigger_period=30m`
- `all_trigger_periods=["30m"]`

However, the repair wording was too broad if interpreted as:

```text
TriggerMatched must never have trigger_period=30m.
```

That interpretation conflicts with the intended HINT business semantics:

```text
BUY_HINT / SELL_HINT are confirmed by N4 using N3 standardized 30m projection evidence.
```

Therefore the correct repair is not a global ban on `trigger_period=30m`. The correct repair is a type-specific rule:

```text
ordinary trigger:
  trigger_period must be Y/Q/M/W/D

hint trigger:
  trigger_period may be 30m

all formal period-set fields:
  triggered_periods / all_trigger_periods / primary_trigger_period must never contain 30m
```

## 2. Field Semantics

### 2.1 Formal Period Set Fields

These fields describe ordinary period-chain trigger state and upgrades:

```text
triggered_periods
all_trigger_periods
primary_trigger_period
```

Allowed values:

```text
Y / Q / M / W / D
```

Forbidden value:

```text
30m
```

For `BUY_HINT / SELL_HINT`, these fields must stay empty/null:

```text
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

Reason: HINT is not a Y/Q/M/W/D period upgrade. It is a 30m projection-confirmed entry after N2 has already proven oversold/overbought structure.

### 2.2 trigger_period

`trigger_period` should represent the period that confirmed the current matched trigger.

For ordinary `trigger_kind=trigger`:

```text
trigger_period in Y/Q/M/W/D
```

For HINT `trigger_kind=hint`:

```text
trigger_period=30m
```

This keeps user/audit wording honest: the HINT event was triggered by 30m confirmation, not by D/W/M/Q/Y.

### 2.3 Projection Evidence Fields

30m projection evidence must also be preserved in explicit projection fields:

```text
projection_period=30m
projection_30m_flag=true
projection_30m_type=volume_up / shrink_down
trigger_mark_candidate=30m_volume / 30m_shrink
```

These fields are evidence/marker fields, not ordinary period-chain fields.

## 3. Ordinary BUY / SELL Rules

Ordinary BUY / SELL means:

```text
trigger_kind=trigger
condition_key starts with BUY: or SELL:
condition_key != BUY:FULL / SELL:FULL
condition_key != BUY_HINT / SELL_HINT
```

For ordinary BUY/SELL `TriggerMatched`, the event is valid only if:

```text
signal_type in B_BUY / S_SELL
trigger_price is present
trigger_kind=trigger
n5_entry_allowed=true
trigger_live=true
current_status=matched
trigger_period in Y/Q/M/W/D
triggered_periods is non-empty and contains only Y/Q/M/W/D
all_trigger_periods is non-empty and contains only Y/Q/M/W/D
primary_trigger_period in Y/Q/M/W/D
triggered_periods / all_trigger_periods / primary_trigger_period do not contain 30m
```

If ordinary BUY/SELL only has 30m projection evidence but no formal Y/Q/M/W/D trigger evidence:

```text
do not write TriggerMatched
do not write common_trigger_match
write TriggerPendingMarketData or quality-visible/no-op according to evidence state
n5_entry_allowed=false
trigger_live=false
```

## 4. BUY_HINT Rules

`BUY_HINT` means:

```text
N2 has proven oversold prerequisite structure.
N4 only confirms N3 standardized 30m volume-up projection.
```

Valid `BUY_HINT` `TriggerMatched` must contain:

```text
event_type=TriggerMatched
signal_type=B_BUY
condition_key=BUY_HINT
original_condition_key=BUY_HINT
trigger_kind=hint
trigger_period=30m
trigger_price=<N3 approved projection/snapshot price>
trigger_live=true
current_status=matched
n5_entry_allowed=true
projection_period=30m
projection_30m_flag=true
projection_30m_type=volume_up
trigger_mark_candidate=30m_volume
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

`BUY_HINT` must not write:

```text
triggered_periods=["30m"]
all_trigger_periods=["30m"]
primary_trigger_period=30m
signal_type=BUY_HINT
action_mark
```

## 5. SELL_HINT Rules

`SELL_HINT` means:

```text
N2 has proven overbought prerequisite structure.
N4 only confirms N3 standardized 30m shrink-down projection.
```

Valid `SELL_HINT` `TriggerMatched` must contain:

```text
event_type=TriggerMatched
signal_type=S_SELL
condition_key=SELL_HINT
original_condition_key=SELL_HINT
trigger_kind=hint
trigger_period=30m
trigger_price=<N3 approved projection/snapshot price>
trigger_live=true
current_status=matched
n5_entry_allowed=true
projection_period=30m
projection_30m_flag=true
projection_30m_type=shrink_down
trigger_mark_candidate=30m_shrink
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

`SELL_HINT` must not write:

```text
triggered_periods=["30m"]
all_trigger_periods=["30m"]
primary_trigger_period=30m
signal_type=SELL_HINT
action_mark
```

## 6. Enforcement Matrix

| Case | trigger_kind | condition_key | trigger_period | triggered_periods | primary_trigger_period | N5 entry |
|---|---|---|---|---|---|---|
| Ordinary BUY/SELL valid | trigger | BUY:* / SELL:* | Y/Q/M/W/D | non-empty Y/Q/M/W/D | Y/Q/M/W/D | allowed |
| Ordinary BUY/SELL with only 30m projection | trigger | BUY:* / SELL:* | 30m or null | empty or 30m | 30m or null | blocked |
| BUY_HINT valid | hint | BUY_HINT | 30m | [] | null | allowed |
| SELL_HINT valid | hint | SELL_HINT | 30m | [] | null | allowed |
| Any HINT with missing trigger_price | hint | BUY_HINT / SELL_HINT | 30m | [] | null | blocked |
| Any HINT with 30m in period set | hint | BUY_HINT / SELL_HINT | 30m | ["30m"] | 30m | blocked |
| FULL before policy approval | trigger | BUY:FULL / SELL:FULL | any | any | any | blocked |

## 7. N5 Consumption Contract

N5 may consume only valid `TriggerMatched` events:

```text
event_type=TriggerMatched
signal_type in B_BUY / S_SELL
current_status=matched
trigger_live=true
n5_entry_allowed=true
trigger_price present
trigger_kind present
```

N5 must apply period validation by trigger kind:

```text
trigger_kind=trigger:
  trigger_period in Y/Q/M/W/D
  triggered_periods non-empty

trigger_kind=hint:
  trigger_period=30m
  condition_key in BUY_HINT / SELL_HINT
  triggered_periods=[]
  all_trigger_periods=[]
  primary_trigger_period=null
```

N5 must not treat `BUY_HINT / SELL_HINT` as user display hints, alert-only, voice, sim, position, or trade intent. N6 user policy decides presentation.

## 8. Required Code Repair

The previous N4 repair must be adjusted from:

```text
TriggerMatched always blocks trigger_period=30m
```

to:

```text
TriggerMatched blocks trigger_period=30m unless:
  trigger_kind=hint
  condition_key in BUY_HINT / SELL_HINT
  projection_period=30m
  projection_30m_type matches direction
  trigger_price present
  n5_entry_allowed=true
  triggered_periods=[]
  all_trigger_periods=[]
  primary_trigger_period=null
```

Implementation touch points expected:

- `src/ashare_v3/trigger/v4_enforcement.py`
- `src/ashare_v3/trigger/projection_matcher.py`
- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `tests/test_n4_v4_enforcement.py`
- `tests/test_trigger_projection_matcher.py`
- `tests/test_trigger_projection_matcher_execute.py`

Optional N5 follow-up:

- N5 input validator should allow `trigger_kind=hint + trigger_period=30m` and continue blocking ordinary `trigger_period=30m`.

## 9. Required Tests

Add or update tests:

```text
ordinary BUY/SELL TriggerMatched with trigger_period=30m => blocked
ordinary BUY/SELL TriggerMatched with triggered_periods=["30m"] => blocked
BUY_HINT TriggerMatched with trigger_period=30m and empty formal periods => allowed
SELL_HINT TriggerMatched with trigger_period=30m and empty formal periods => allowed
BUY_HINT missing trigger_price => blocked
SELL_HINT missing trigger_price => blocked
BUY_HINT with primary_trigger_period=30m => blocked
SELL_HINT with all_trigger_periods=["30m"] => blocked
N5 eligibility accepts HINT 30m only when trigger_kind=hint and condition_key is HINT
N5 eligibility rejects ordinary trigger_period=30m
```

## 10. Documentation Repair Required

The implementation report produced in the previous gate should be amended or superseded. Its broad wording:

```text
30m projection evidence is no longer allowed in formal trigger period fields.
Forbidden for TriggerMatched: trigger_period, triggered_periods, all_trigger_periods, primary_trigger_period.
```

should become:

```text
30m is forbidden in formal period-set fields:
  triggered_periods / all_trigger_periods / primary_trigger_period.

30m is forbidden in trigger_period for ordinary trigger_kind=trigger.

30m is allowed in trigger_period for trigger_kind=hint with condition_key BUY_HINT / SELL_HINT,
provided the event carries valid N3 projection evidence and trigger_price.
```

## 11. Recommended Runtime Route

1. runtime_control reviews this proposal.
2. If accepted, enter N4 repair contract gate.
3. Implement N4 enforcement adjustment.
4. Refresh N4 projection matcher dry-run for 20260608 v13 index-all until 0952.
5. Re-run preflight/final gate.
6. Only after final gate, execute N4 projection matcher.
7. N5/N6 remain blocked until N4 post-review passes.

## 12. Status

This proposal is ready for runtime_control review.

No business data was written.
