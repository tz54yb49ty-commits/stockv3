# N5 HINT Source Condition Agnostic Output Spec

Status: SPEC_PASS

Layer role: N5_action

Generated at: 2026-06-09T22:00:00+08:00

Scope: freeze N5 output semantics for `BUY_HINT` / `SELL_HINT` provenance.

This gate is documentation only:

```text
code_change=false
schema_migration=false
database_write=false
outbox_consumption=false
outbox_write=false
inbox_checkpoint_write=false
execute=false
rollback=false
N6_entered=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```

Authoritative inputs:

```text
AGENTS.md
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1.md
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_TRACEABILITY.md
```

If older N5 design documents, historical reports, UI wording, SQL drafts, or tests conflict with this spec, this spec wins for future N5 alignment. Historical run evidence remains auditable under the contracts that produced it and must not be silently rewritten.

## Result

SPEC_PASS

P0/P1/P2:

```text
P0=0
P1=3
P2=4
```

The P1/P2 items are divergence tracking items for follow-up gates. They do not block this documentation-only spec freeze.

## A. Core Rule

N5 action output is canonical and source-condition agnostic.

N5 MUST NOT vary any of the following because `condition_key` or `original_condition_key` is `BUY_HINT` or `SELL_HINT`:

```text
event_type
action_state
confirmation_status
action confirmation rule
output schema
```

N5 MUST treat `BUY_HINT` / `SELL_HINT` only as provenance trace. In N5, HINT provenance is not an action type, not a user hint type, not alert-only policy, and not a user strategy.

## B. Input Rule

N5 action confirmation entry is allowed only from:

```text
TriggerMatched
```

N5 MUST NOT create action fact/event from:

```text
TriggerPendingMarketData
TriggerStateChanged
```

`TriggerPendingMarketData` and `TriggerStateChanged` may be handled only as no-op / quality-only / state-gate / tracking context according to the run contract.

N5 runtime `signal_type` is allowed only:

```text
B_BUY
S_SELL
```

If N4 sends runtime `signal_type=BUY_HINT` or `signal_type=SELL_HINT`, N5 MUST treat it as a contract violation / P0 input error. It MUST NOT generate a HINT class action and MUST NOT silently reinterpret the runtime signal.

Valid HINT provenance entering N5 has the shape:

```text
BUY_HINT  -> signal_type=B_BUY, direction=buy
SELL_HINT -> signal_type=S_SELL, direction=sell
```

N4 remains responsible for deciding whether the object is allowed to enter N5. N5 must still validate the standard N4 `TriggerMatched` contract before creating any action candidate.

## C. Confirmation Rule

N5 applies one buy rule and one sell rule:

```text
B_BUY  -> unified buy 120m / 30m / 5m / 1m confirmation rule
S_SELL -> unified sell 120m / 30m / 5m / 1m confirmation rule
```

HINT provenance MUST NOT:

```text
change the four-period confirmation rule
bypass 120m / 30m / 5m / 1m confirmation
trust opaque payload.action_confirmation as final proof
auto-produce ActionEligible
auto-produce alert-only output
change blocked_reason semantics
```

Action confirmation must come from deterministic N3 action-confirmation metric facts plus a live N4 `TriggerMatched` event. If metrics are missing, low quality, or fail the price/amount rules, the output is a standard canonical result such as `ActionBlocked`; it is not a HINT-specific event.

## D. Output Rule

Canonical N5 output event types are only:

```text
ActionExecuted
ActionBlocked
ActionEligible
ActionSkipped
```

N5 MUST NOT output any of the following because source provenance is HINT:

```text
HintEvent
ActionEvent
RiskEvent
PositionEvent
User*
Voice*
Sim*
Trade*
```

`ActionExecuted` means only:

```text
N5 market action confirmation passed.
N5 emitted a canonical N5 action event.
```

`ActionExecuted` does not mean:

```text
order submitted
order filled
sim trade written
user card displayed
voice spoken
mobile push sent
trade intent approved
```

Those meanings belong to N6/user policy or later explicitly authorized trade-intent layers.

## E. Trace Fields

`BUY_HINT` / `SELL_HINT` may be preserved only as trace / audit / analytics provenance.

Allowed N5 trace locations include:

```text
condition_key
original_condition_key
trigger_kind
trigger_mark_candidate
source_condition_trace
period_trigger_baseline_trace
metric_trace
trace_json
source_payload_json
```

Trace preservation is not permission to change N5 action semantics.

## F. action_mark Rule

Final `action_mark` values are only:

```text
normal
30m_volume
30m_shrink
```

N5 final `action_mark` is derived from N3 action-confirmation metric evidence after N5 confirmation passes. N4 `trigger_mark_candidate` is trace-only and must not be used as the canonical source:

```text
B_BUY  + current_30m_virtual_amount > previous_day_same_window_amount + buy_30m_price_pass  -> action_mark=30m_volume
S_SELL + current_30m_virtual_amount < previous_day_same_window_amount + sell_30m_price_pass -> action_mark=30m_shrink
otherwise, including missing previous_day_same_window_amount -> action_mark=normal
```

N5 may write non-null final `action_mark` only when:

```text
confirmation_status=passed
action_state=executed
event_type=ActionExecuted
```

For blocked / eligible / skipped / expired / quality-only outputs:

```text
action_mark=null
trigger_mark_candidate remains trace/candidate evidence
```

HINT does not directly equal `action_mark`. HINT is provenance. Final `action_mark` still depends on N4 candidate mark plus N5 confirmation passed.

## G. N5 / N6 Boundary

N5 MUST NOT decide:

```text
display label
whether to show as hint
alert-only policy
voice / TTS
mobile push
sim inclusion
proposal / order / trade
real trade
user position / cash / blacklist / T+1 / holding state
watchlist / user preference filtering
```

Those decisions belong to N6/user policy or later explicit trade-intent layers.

N5 MUST NOT read user holdings, funds, blacklist, T+1, position size, or preferences. N5 blocked reasons must be market/system confirmation reasons only. User-layer reasons are forbidden in N5 `blocked_reason`.

## H. Divergence / Gap List

This gate only lists gaps; it does not repair code or rewrite historical artifacts.

### P1 Gaps

1. `src/ashare_v3/action/preflight.py` still reports `buy_hint_count` / `sell_hint_count` by checking `payload.signal_type == BUY_HINT/SELL_HINT`. The same module also reports trace counts correctly. Future N5 preflight wording should rename runtime-signal HINT counters to `deprecated_runtime_hint_signal_count` or remove them from normal summaries, so HINT is not presented as a runtime signal.

2. Several historical 09:52 artifacts use the wording `HINT_30M_ELIGIBILITY_ONLY` and `ActionEligible` for a metric-missing lineage. That lineage has already been annotated as non-final, but future closeout/dashboard wording must keep it clearly separate from metric-aware action confirmation and must not imply HINT-specific automatic eligibility.

3. `docs/N6_PROJECTION_CONTRACT.md` still describes `ActionEvent / HintEvent` as N6 input and maps `BUY_HINT / SELL_HINT` to `HintEvent` style notification source. This is an N6-facing historical contract gap and must be superseded before any N6 consumer relies on canonical N5 output.

### P2 Gaps

1. `docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md` still contains historical design language where `BUY_HINT` may become `HintEvent` or `ActionEvent` according to user policy. The file has a canonical note, but future doc cleanup should mark those sections as historical compatibility more visibly.

2. `docs/N5_current_real_action_execute_contract.json` still contains legacy mappings from `BUY_HINT` / `SELL_HINT` to `HintEvent`. This is historical current-real evidence, not future canonical behavior, and should be superseded or excluded from future runtime-control dashboards.

3. Tests intentionally keep historical compatibility samples such as `signal_type=BUY_HINT` to assert rejection. Future readers may misread these fixtures as supported input unless test names and comments keep saying they are negative tests.

4. Some N6/UI reports discuss hint display policy. That is valid only in N6. Future N6 specs must explicitly say any hint display is a user-policy presentation of canonical N5 `Action*` events, not an N5 `HintEvent`.

### No Active P0 Gap Found In This Spec Gate

The read-only scan found current canonical N5 event validation rejects `HintEvent` and rejects runtime `signal_type=BUY_HINT/SELL_HINT`. Current action tests also cover legal HINT provenance using canonical `B_BUY/S_SELL`, same-rule metric confirmation, final `action_mark` only on `ActionExecuted`, and null final `action_mark` for blocked/eligible paths.

## Required Follow-Up

Before the next N5 execute line uses this spec, runtime_control should run a review gate that confirms:

```text
source N4 output uses signal_type=B_BUY/S_SELL
BUY_HINT/SELL_HINT appear only in condition trace
N5 final gate binds N3 metric_run_id
planned event distribution is ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped only
planned action_mark is non-null only for ActionExecuted
N6/dashboard wording does not treat HINT as N5 user hint output
```

## Forbidden Scope Proof

```text
implementation_changed=false
database_write=false
execute=false
rollback=false
outbox_consumption=false
inbox_checkpoint_write=false
N6_entered=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```

## Next Gate

Allowed to return to runtime_control for:

```text
N5_HINT_SOURCE_CONDITION_AGNOSTIC_OUTPUT_SPEC_REVIEW_GATE
```
