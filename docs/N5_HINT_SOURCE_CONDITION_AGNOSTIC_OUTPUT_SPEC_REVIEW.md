# N5 HINT Source Condition Agnostic Output Spec Review

Status: REVIEW_PASS

Layer role: runtime_control

Generated at: 2026-06-09T22:59:00.514681+08:00

Scope: read-only review of the N5 HINT source-condition agnostic output spec. No code, DB, N5 execute, outbox consumption, N6, worker, delivery, sim, position, order, trade, or old system action was performed.

## Result

REVIEW_PASS

Blockers:

- none

Allowed next gate:

```text
N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_READINESS_GATE
```

## Spec Artifact Proof

- MD exists: `True`
- JSON exists / parse: `True` / `PASS`
- result: `SPEC_PASS`
- source_docs_read: `PASS`
- code_report_gap_scan: `PASS`
- json_parse: `PASS`
- git_diff_check in source spec: `PASS`
- P0/P1/P2: `0/3/4`

Decision: the P1/P2 items are follow-up compatibility and wording gaps. They do not block this spec freeze because P0=0 and the canonical N5 semantics are explicit.

## Core Semantic Proof

- N5 action output is canonical and source-condition agnostic.
- N5 must not vary event_type, action_state, confirmation_status, action confirmation rule, or output schema because condition provenance is BUY_HINT / SELL_HINT.
- BUY_HINT / SELL_HINT are provenance trace only.
- BUY_HINT / SELL_HINT are not N5 independent action types, not N5 user hint/display types, and not alert-only policy types.

## Input / Confirmation / Output Proof

- Only action entry event: `TriggerMatched`
- No action fact/event from: `TriggerPendingMarketData, TriggerStateChanged`
- Runtime signal_type allowed: `B_BUY, S_SELL`
- Runtime BUY_HINT / SELL_HINT is a P0 contract violation, not a hint-class action.
- BUY_HINT maps to signal_type=B_BUY / direction=buy; SELL_HINT maps to signal_type=S_SELL / direction=sell.
- B_BUY uses the unified buy 120m/30m/5m/1m confirmation rule; S_SELL uses the unified sell rule.
- HINT does not change the confirmation rule, bypass N3 metric-aware confirmation, auto ActionEligible, or auto alert-only.
- Opaque payload.action_confirmation is not trusted as final proof.
- Allowed event types: `ActionExecuted, ActionBlocked, ActionEligible, ActionSkipped`
- HintEvent / ActionEvent / RiskEvent / PositionEvent / User* / Voice* / Sim* / Trade* are forbidden because of HINT provenance.

## action_mark Proof

- Allowed final action_mark values: `normal, 30m_volume, 30m_shrink`
- Non-null final action_mark is allowed only when event_type=ActionExecuted, action_state=executed, confirmation_status=passed.
- blocked / eligible / skipped / expired outputs must keep action_mark=null.
- HINT does not directly equal action_mark; HINT and N4 trigger_mark_candidate are trace, while final action_mark comes from N5-owned N3 action-confirmation metric comparison after N5 confirmation passes.

## Trace Proof

BUY_HINT / SELL_HINT may appear as provenance in:

- `condition_key`
- `original_condition_key`
- `trigger_kind`
- `trigger_mark_candidate`
- `source_condition_trace`
- `period_trigger_baseline_trace`
- `metric_trace`
- `trace_json`
- `source_payload_json`

Trace preservation does not change N5 action semantics.

## N5 / N6 Boundary Proof

- N5 does not decide display label, show-as-hint, alert-only, voice, mobile, sim, proposal/order/trade, real trade, or user policy.
- N5 does not read user holdings, cash, blacklist, T+1, preferences, or position state.
- N5 blocked_reason must not contain user-layer reasons.
- N6/user policy is the first layer allowed to interpret HINT for presentation.

## Divergence / Gap Review

- P0 gap count: `0`
- P1 gap count: `3`
- P2 gap count: `4`

P1 gaps:

- `P1-1` preflight runtime HINT counters are still named like normal signal counters: Rename to deprecated_runtime_hint_signal_count or keep only trace counters in normal reports.
- `P1-2` historical eligibility-only artifacts need clear non-final annotation: Keep annotated as non-final and not HINT-specific automatic eligibility.
- `P1-3` legacy N6 projection contract still names ActionEvent/HintEvent inputs: Supersede before N6 consumes canonical N5 output.

P2 gaps:

- `P2-1` historical N5 design doc still contains HintEvent mapping language: Mark sections as historical compatibility more visibly or supersede.
- `P2-2` legacy current-real execute contract contains BUY_HINT to HintEvent mapping: Exclude or supersede in future dashboards.
- `P2-3` negative tests include deprecated runtime signal fixtures: Keep test names/comments explicit that these are negative fixtures.
- `P2-4` N6/UI may display hint labels only under N6 policy: N6 specs must state hint display is user-policy presentation of canonical Action* events.

Review decision: no P0 gap blocks the spec freeze. Follow-up gates are required before legacy artifacts, dashboards, or N6 wording are relied on as canonical.

## N4 Readiness Tie-In

- N4 unified output retry post-review: `POST_REVIEW_PASS`
- target N4 run: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- runtime signal_type distribution: `{'B_BUY': 415, 'S_SELL': 141}`
- condition_signal_type distribution: `{'BUY': 299, 'BUY_HINT': 116, 'SELL': 135, 'SELL_HINT': 6}`
- action_mark emitted: `0`
- trigger_mark_candidate distribution: `{'30m_shrink': 6, '30m_volume': 116, 'normal': 434}`
- required unified fields missing: `0`
- BUY_HINT / SELL_HINT trace counts: `116/6`
- N5 refs total: `0`
- N6/user/sim refs total: `0`

Conclusion: N4 is ready for the next N5 readiness gate under this spec because it emits runtime signal_type only as B_BUY/S_SELL, keeps BUY_HINT/SELL_HINT as condition trace, emits no final action_mark, and carries trigger_mark_candidate as normal/30m_volume/30m_shrink.

## Forbidden Scope Proof

- code_change: `False`
- database_write: `False`
- sql_executed: `False`
- n5_execute: `False`
- outbox_consumption: `False`
- outbox_update: `False`
- inbox_checkpoint_update: `False`
- n6_entered: `False`
- worker_started: `False`
- delivery_push_voice_mobile: `False`
- sim_position_pnl_real_trade: `False`
- proposal_order_trade: `False`
- old_system_touched: `False`

## Validation

- JSON parse: `PASS`
- spec consistency scan: `PASS`
- source spec cross-check: `PASS`
- divergence list consistency: `PASS`
- N4 post-review tie-in proof: `PASS`
- git diff --check: `PASS`

## Next Gate

```text
N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_READINESS_GATE
```
