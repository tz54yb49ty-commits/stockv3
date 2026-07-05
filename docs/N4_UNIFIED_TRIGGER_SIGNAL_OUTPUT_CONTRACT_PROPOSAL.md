# N4 Unified Trigger Signal Output Contract Proposal

Status: `PROPOSAL_FOR_RUNTIME_CONTROL_REVIEW`

Layer role: `N4_trigger`

Generated at: `2026-06-09`

This proposal freezes the requested N4 output shape for runtime_control review. It does not execute N4, does not write database rows, does not consume outbox/inbox/checkpoint, does not enter N5/N6, and does not start workers.

## 1. Goal

N4 currently has one runtime `signal_type` field whose valid values are only:

```text
B_BUY
S_SELL
```

That is correct for runtime direction, but it is not enough for users, N5, N6, and audit to distinguish:

```text
BUY:Y,Q,M,W,D
SELL:Y,Q,M,W,D
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

The goal is to make these six condition families output a consistent field envelope while preserving canonical runtime direction:

```text
signal_type = B_BUY / S_SELL
condition_signal_type = BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT
condition_key = original N2 condition, such as BUY:Y,Q,M,W,D
original_condition_key = original N2 condition before any N4 normalization
```

## 2. Non-goals

This proposal does not change N4 trigger math.

This proposal does not let N4 pull market data, read raw K, read N1 daily, aggregate periods, recalculate N2, write N5 action, write N6 user projection, write voice/mobile/sim/position/real trade, or choose final `action_mark`.

This proposal does not make `BUY_HINT / SELL_HINT / BUY:FULL / SELL:FULL / BUY / SELL` valid runtime `signal_type` values.

This proposal does not make `TriggerPendingMarketData` or `TriggerStateChanged` N5 action confirmation entries.

## 3. Recommended Field Model

Use three separate layers:

```text
Layer 1: signal_type
  Runtime buy/sell direction.
  Allowed values: B_BUY / S_SELL.

Layer 2: condition_signal_type
  Condition family/type.
  Allowed values: BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT.

Layer 3: condition_key / original_condition_key / trace
  Original N2 condition detail, including requested formal periods.
  Examples: BUY:Y,Q,M,W,D, SELL:Y,Q,M,W,D, BUY:FULL, SELL_HINT.
```

Do not rename the existing physical `signal_type` field unless a later schema review approves it. If a UI/API needs a clearer alias, it may expose `runtime_signal_type = signal_type` as a read-only alias.

## 4. Required Unified Output Fields

Every N4 output payload for trigger plans, `TriggerMatched`, `TriggerPendingMarketData`, and `TriggerStateChanged` should carry the same semantic envelope where the field is applicable:

```text
signal_type
runtime_signal_type
direction
condition_signal_type
condition_key
original_condition_key
trigger_kind
trigger_mark_candidate

requested_periods
triggered_periods
all_trigger_periods
primary_trigger_period
trigger_period

trigger_price
trigger_time
event_time
price_source
match_basis
baseline_source

projection_30m_required
projection_30m_flag
projection_30m_type
projection_period
projection_30m_volume_up_flag
projection_30m_shrink_down_flag

trigger_live
current_status
n5_entry_allowed
data_quality_status
```

Notes:

- `signal_type` remains the canonical runtime field. `runtime_signal_type` is an optional alias equal to `signal_type` for readability.
- `trigger_price` is required for valid `TriggerMatched`. It may be null only for non-N5-entry pending/quality states where price evidence is genuinely unavailable.
- `condition_signal_type` is the proposed new discriminator that makes ordinary, FULL, and HINT outputs visibly different without polluting runtime `signal_type`.
- `requested_periods` is the period list requested by `condition_key`; `triggered_periods` is the list that actually fired in this event.
- `30m` may be `trigger_period` only for valid HINT matched output. `30m` must not appear in `triggered_periods`, `all_trigger_periods`, or `primary_trigger_period`.

## 5. 30m Marker Fields

Every signal family must explicitly carry 30m marker fields:

```text
projection_30m_required
projection_30m_flag
projection_30m_type
projection_period
projection_30m_volume_up_flag
projection_30m_shrink_down_flag
```

Recommended semantics:

```text
projection_30m_required:
  true only when the signal family requires N3 30m projection confirmation.

projection_30m_flag:
  true when the required 30m projection evidence is present and accepted.

projection_30m_type:
  none / volume_up / shrink_down.

projection_period:
  null / 30m.

projection_30m_volume_up_flag:
  true only for accepted 30m volume-up evidence.

projection_30m_shrink_down_flag:
  true only for accepted 30m shrink-down evidence.
```

This keeps the user's requested "whether 30m volume-up exists" marker while also handling the sell-side shrink-down case cleanly.

## 6. Six Signal Families

### 6.1 BUY:Y,Q,M,W,D

```text
signal_type=B_BUY
runtime_signal_type=B_BUY
direction=buy
condition_signal_type=BUY
condition_key=BUY:Y,Q,M,W,D or narrower BUY period set
trigger_kind=trigger
trigger_mark_candidate=normal
requested_periods=periods parsed from condition_key
triggered_periods=actual Y/Q/M/W/D periods that fired
all_trigger_periods=trade-date cumulative formal periods
primary_trigger_period=highest period in all_trigger_periods
trigger_period=primary_trigger_period or event primary period
projection_30m_required=false
projection_30m_flag=false
projection_30m_type=none
projection_period=null
projection_30m_volume_up_flag=false
projection_30m_shrink_down_flag=false
```

BUY formal trigger still requires:

```text
previous_transition[P] != volume_up
current_transition[P] == volume_up
transition_amount_pass[P] = true
trigger_amount_chain_pass[P] = true
```

### 6.2 SELL:Y,Q,M,W,D

```text
signal_type=S_SELL
runtime_signal_type=S_SELL
direction=sell
condition_signal_type=SELL
condition_key=SELL:Y,Q,M,W,D or narrower SELL period set
trigger_kind=trigger
trigger_mark_candidate=normal
requested_periods=periods parsed from condition_key
triggered_periods=actual Y/Q/M/W/D periods that fired
all_trigger_periods=trade-date cumulative formal periods
primary_trigger_period=highest period in all_trigger_periods
trigger_period=primary_trigger_period or event primary period
projection_30m_required=false
projection_30m_flag=false
projection_30m_type=none
projection_period=null
projection_30m_volume_up_flag=false
projection_30m_shrink_down_flag=false
```

SELL formal trigger still requires:

```text
previous_transition[P] != low_volume_down
current_transition[P] == low_volume_down
transition_amount_pass[P] = true
trigger_amount_chain_pass[P] = true
```

### 6.3 BUY:FULL

```text
signal_type=B_BUY
runtime_signal_type=B_BUY
direction=buy
condition_signal_type=BUY:FULL
condition_key=BUY:FULL
original_condition_key=BUY:FULL
trigger_kind=trigger
trigger_mark_candidate=normal
requested_periods=["D"]
triggered_periods=["D"] when matched
all_trigger_periods=["D"] when matched
primary_trigger_period=D when matched
trigger_period=D
projection_30m_required=false
projection_30m_flag=false
projection_30m_type=none
projection_period=null
projection_30m_volume_up_flag=false
projection_30m_shrink_down_flag=false
```

BUY:FULL requires N2 localized FULL context proof and D confirmation:

```text
condition_key=BUY:FULL
original_condition_key=BUY:FULL
direction=buy
D current_transition=volume_up
D transition_amount_pass=true
D trigger_amount_chain_pass=true
trigger_price non-null
```

### 6.4 SELL:FULL

```text
signal_type=S_SELL
runtime_signal_type=S_SELL
direction=sell
condition_signal_type=SELL:FULL
condition_key=SELL:FULL
original_condition_key=SELL:FULL
trigger_kind=trigger
trigger_mark_candidate=normal
requested_periods=["D"]
triggered_periods=["D"] when matched
all_trigger_periods=["D"] when matched
primary_trigger_period=D when matched
trigger_period=D
projection_30m_required=false
projection_30m_flag=false
projection_30m_type=none
projection_period=null
projection_30m_volume_up_flag=false
projection_30m_shrink_down_flag=false
```

SELL:FULL requires N2 localized FULL context proof and D confirmation:

```text
condition_key=SELL:FULL
original_condition_key=SELL:FULL
direction=sell
D current_transition=low_volume_down
D transition_amount_pass=true
D trigger_amount_chain_pass=true
trigger_price non-null
```

### 6.5 BUY_HINT

```text
signal_type=B_BUY
runtime_signal_type=B_BUY
direction=buy
condition_signal_type=BUY_HINT
condition_key=BUY_HINT
original_condition_key=BUY_HINT
trigger_kind=hint
trigger_mark_candidate=30m_volume
requested_periods=[]
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
trigger_period=30m when matched
projection_30m_required=true
projection_30m_flag=true when matched
projection_30m_type=volume_up
projection_period=30m
projection_30m_volume_up_flag=true when matched
projection_30m_shrink_down_flag=false
```

BUY_HINT requires:

```text
N2 oversold structure proof
N3 approved 30m volume-up projection proof
trigger_price non-null
n5_entry_allowed=true
```

### 6.6 SELL_HINT

```text
signal_type=S_SELL
runtime_signal_type=S_SELL
direction=sell
condition_signal_type=SELL_HINT
condition_key=SELL_HINT
original_condition_key=SELL_HINT
trigger_kind=hint
trigger_mark_candidate=30m_shrink
requested_periods=[]
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
trigger_period=30m when matched
projection_30m_required=true
projection_30m_flag=true when matched
projection_30m_type=shrink_down
projection_period=30m
projection_30m_volume_up_flag=false
projection_30m_shrink_down_flag=true when matched
```

SELL_HINT requires:

```text
N2 overbought structure proof
N3 approved 30m shrink-down projection proof
trigger_price non-null
n5_entry_allowed=true
```

## 7. Required Period Detail Output

When `condition_key` requests multiple formal periods, N4 must output both the requested periods and the actually fired periods.

Example:

```text
condition_key=BUY:Y,Q,M,W,D
requested_periods=["Y","Q","M","W","D"]
triggered_periods=["W","D"]
all_trigger_periods=["W","D"]
primary_trigger_period="W"
```

The payload must include `triggered_period_details`:

```json
{
  "W": {
    "trigger_price": "12.34",
    "current_transition": "volume_up",
    "transition_amount_pass": true,
    "trigger_amount_chain_pass": true,
    "baseline_source": "trigger_baseline"
  },
  "D": {
    "trigger_price": "12.34",
    "current_transition": "volume_up",
    "transition_amount_pass": true,
    "trigger_amount_chain_pass": true,
    "baseline_source": "trigger_baseline"
  }
}
```

If only `D` fires, N4 must not imply `Y/Q/M/W` fired merely because they appeared in `condition_key`.

## 8. N5 Entry Rule

N5 action confirmation entry remains strict:

```text
event_type=TriggerMatched
signal_type in (B_BUY, S_SELL)
current_status=matched
trigger_live=true
n5_entry_allowed=true
trigger_price non-null
```

`condition_signal_type` must be trace/dispatch context, not a replacement for the above N5 entry guard.

`TriggerPendingMarketData` and `TriggerStateChanged` may carry the unified field envelope for state/quality/visibility, but they must not create N5 action confirmation.

## 9. Schema And Persistence Policy To Review

Runtime_control should decide whether the new fields are:

```text
Option A: payload-only canonical fields
  Store in common_event_outbox.payload_json and common_trigger_match.raw_json/common_trigger_state.raw_json where available.
  Lowest schema risk.

Option B: additive physical columns
  Add physical columns for condition_signal_type, requested_periods, projection_30m_required, projection_30m_volume_up_flag, projection_30m_shrink_down_flag.
  Better query/display ergonomics but requires schema migration.

Recommended first step:
  Option A for contract compatibility, followed by schema review for selected physical columns.
```

At minimum, future writes must make these fields available in canonical payload evidence, even if some are not immediately physical columns.

## 10. P0 Guards

The following must be P0 before any future N4 execute:

```text
signal_type not in B_BUY/S_SELL
condition_signal_type missing or invalid
condition_key missing
original_condition_key missing
trigger_kind missing or invalid
trigger_price missing for TriggerMatched
triggered_periods missing for formal trigger matched rows
n5_entry_allowed missing/false for TriggerMatched
30m in triggered_periods/all_trigger_periods/primary_trigger_period
ordinary trigger_kind=trigger with trigger_period=30m
HINT matched without projection_30m_required=true
HINT matched without projection_30m_flag=true
HINT matched without projection_30m_type=volume_up/shrink_down
FULL matched without N2 FULL context proof
FULL matched with trigger_period other than D
payload contains final action_mark
```

## 11. Required Follow-up Gates

Recommended gate sequence:

```text
1. N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_REVIEW_GATE
   Runtime_control reviews and approves field names, payload-only vs schema strategy, and P0 guard scope.

2. N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT_GATE
   N4 reviews whether additive physical columns are required or payload-only is enough.

3. N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_DRY_RUN_ALIGNMENT_GATE
   N4 matcher/dry-run emits unified fields and triggered_period_details.

4. N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_EXECUTE_CONTRACT_GATE
   N4 execute contract/preflight/rollback encodes the new fields and guards.

5. N5_UNIFIED_TRIGGER_SIGNAL_INPUT_GUARD_GATE
   N5 validates condition_signal_type and 30m/HINT/FULL semantics without treating non-TriggerMatched events as action entries.

6. N6_DISPLAY_FIELD_MAPPING_GATE
   N6 maps condition_signal_type, requested_periods, triggered_periods, trigger_price, and 30m marker fields for user display.
```

## 12. Forbidden Scope

This proposal does not authorize:

```text
N4 execute
N5 execute
N6 execute
DB writes
outbox/inbox/checkpoint consumption or update
worker startup
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
old system access
```

## 13. Runtime Control Review Prompt

```text
layer_role=runtime_control

进入 N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_REVIEW_GATE。

目标：
审核 N4 unified trigger signal output proposal，确认 N4 六类条件输出是否统一采用：
- signal_type 仅表示 runtime 方向：B_BUY / S_SELL
- condition_signal_type 区分信号类型：BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT
- condition_key / original_condition_key 保留原始 N2 条件
- 每个 N4 输出均携带 projection_30m_required / projection_30m_flag / projection_30m_type / projection_period / projection_30m_volume_up_flag / projection_30m_shrink_down_flag
- 多周期条件必须输出 requested_periods、triggered_periods、all_trigger_periods、primary_trigger_period、triggered_period_details

依据：
- docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.md
- docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.json
- docs/N4_TRIGGER_RULE_SPEC_v4.md
- docs/N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md
- docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md
- docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
- AGENTS.md

本轮只读审核：
- 不执行 N4
- 不写数据库
- 不消费/update outbox/inbox/checkpoint
- 不进入 N5/N6
- 不启动 worker
- 不 delivery/push/voice/mobile/sim/position/order/trade/real trade

请确认：
1. 是否同意三层信号模型：
   - signal_type/runtime_signal_type = B_BUY / S_SELL
   - condition_signal_type = BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT
   - condition_key/original_condition_key = 原始 N2 条件与 trace
2. 是否同意六类信号输出一致字段 envelope。
3. 是否同意所有输出携带 30m marker fields。
4. 是否同意 HINT 允许 trigger_period=30m，但 30m 不得进入 triggered_periods/all_trigger_periods/primary_trigger_period。
5. 是否同意普通 BUY/SELL/FULL 的正式周期只能是 Y/Q/M/W/D。
6. 是否同意 TriggerMatched 必须带 trigger_price 与 triggered_period_details。
7. 是否同意先 payload-only 落地，再单独做 schema impact review。
8. 是否同意 P0 guard list。
9. 是否要求 N5/N6 同步增加 input/display guard。
10. 是否允许进入 N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT_GATE。

输出：
- REVIEW_PASS / BLOCKED
- approved field names
- required changes
- payload-only vs schema migration decision
- P0 guard list
- N5/N6 follow-up requirements
- 是否允许进入 N4 schema/code dry-run alignment gate
```
