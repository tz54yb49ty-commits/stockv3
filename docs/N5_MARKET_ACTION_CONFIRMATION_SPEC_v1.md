# N5 Market Action Confirmation Spec v1

Status: frozen_for_runtime_control_review

Frozen at: 2026-06-04

Layer role: N5_action

Scope: N5 market action confirmation responsibility, N4 input event classification, N3 action-confirmation metric consumption, B_BUY / S_SELL confirmation rules, HINT provenance handling, final `action_mark`, canonical output event semantics, blocked reason boundary, idempotency, remediation priorities, and implementation route.

This freeze is documentation only:

```text
code_change=false
schema_migration=false
database_write=false
outbox_consumption=false
outbox_write=false
inbox_checkpoint_write=false
execute=false
worker_started=false
rollback=false
historical_run_rewrite=false
N6_entered=false
real_trade=false
```

Authoritative upstream and sibling specs:

```text
AGENTS.md
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md
```

If older N5 design documents, SQL drafts, code, tests, UI wording, reports, or historical run artifacts conflict with this document, this document wins for future N5 alignment work. Historical run evidence must remain auditable under the contract that produced it and must not be silently rewritten. Any correction to historical runs must go through explicit rollback, replay, or compatibility gates.

## 1. Frozen Remediation Conclusion

N5 must be aligned to the following target:

```text
N5 = market action confirmation layer
```

N5 only confirms whether a market action fact is established. N5 does not confirm whether any user can or should trade.

N5 answers exactly one runtime question:

```text
Given a live N4 TriggerMatched event with runtime signal_type=B_BUY or S_SELL,
do the N3 action-confirmation metrics confirm the market action?
```

N5 must not answer any user or account question:

```text
Does the user hold this stock?
Does the user have enough cash?
Is the position T+1 locked?
Has the user already sold?
Is the stock blacklisted for this user?
Is the user's position size allowed?
Should a card be displayed?
Should voice/TTS be spoken?
Should mobile push be sent?
Should a sim trade be written?
Should a real order be submitted?
```

All of those questions belong to N6/user policy or later explicitly authorized trade-intent layers.

## 2. N5 Boundary

N5 may:

```text
consume N4 standard trigger events
read N3 standard action-confirmation metric facts
read immutable N4 trigger context and trace fields
write N5 action confirmation facts when execute is explicitly authorized
emit canonical N5 action events when execute is explicitly authorized
write N5 consumer inbox/checkpoint for consumed N4 events when execute is explicitly authorized
write N5 quality items for market/system data quality when execute is explicitly authorized
```

N5 must not:

```text
pull realtime quotes
call external market data adapters
read raw minute K and assemble 1m/5m/30m/120m indicators
compute current_5m_virtual_amount from raw rows
compute previous period body high/low from raw rows
query N1 daily K
recompute N2 condition_basis / condition_pool / minute_target_scope
recompute N4 trigger decisions
write N4 trigger facts or N4 outbox status
read user holdings, account, cash, blacklist, T+1, position size, or preferences
write N6 user projection
write notification, voice, mobile, sim, position, or real trade objects
start a worker without separate authorization
```

N5 may preserve upstream trace fields, including condition provenance, projection trace, metric lineage, target-price candidates, and trigger context. Preserving trace is not permission to reinterpret upstream responsibilities.

## 3. Input Event Classification

N5 input events are split into action entry and observer/gate classes.

Action entry:

```text
TriggerMatched
```

Observer / gate:

```text
TriggerPendingMarketData
TriggerStateChanged
```

### 3.1 TriggerMatched

`TriggerMatched` is the only N5 action confirmation entry.

N5 may create an action confirmation grain only when the input event is:

```text
event_type=TriggerMatched
current_status=matched
trigger_live=true
action_eligible=true
signal_type in (B_BUY, S_SELL)
source_run_id explicitly allowlisted
source_action_confirmation_metric_id present and resolvable to N3 metric facts
```

`TriggerMatched` may produce:

```text
ActionExecuted
ActionBlocked
ActionEligible
ActionSkipped
```

In the current market-action-confirmation execute mode, the normal final outputs are:

```text
ActionExecuted when all confirmation rules pass
ActionBlocked when market/system confirmation fails or is unavailable
```

### 3.2 TriggerPendingMarketData

`TriggerPendingMarketData` is not an action entry.

N5 handling:

```text
quality observer
no-op for action confirmation
state/watermark gate
may write N5 quality item when execute is authorized
may write N5 inbox/checkpoint when execute is authorized
must not create action fact
must not emit ActionExecuted
must not emit ActionBlocked as an action confirmation result
must not write final action_mark
```

Pending market data means N5 does not yet have sufficient market facts to confirm an action. It is not a failed user action, not a no-position result, and not a trade rejection.

### 3.3 TriggerStateChanged

`TriggerStateChanged` is not an action entry.

N5 handling:

```text
state gate
tracking gate
live/inactive context
may update or wake existing tracking only when a separate TriggerMatched action grain already exists
may stop tracking when trigger_live=false
may write N5 inbox/checkpoint when execute is authorized
must not create action fact by itself
must not emit ActionExecuted by itself
must not emit ActionBlocked as a fresh action confirmation by itself
must not write final action_mark
```

When `trigger_live=false`, N5 must stop continuing confirmation for that trigger state. It must not delete existing facts, action events, user projections, notifications, or audit evidence.

## 4. Required N4 Input Semantics

For N5 action entry, N4 must pass a live matched trigger:

```text
event_type=TriggerMatched
current_status=matched
trigger_live=true
action_eligible=true
signal_type=B_BUY or S_SELL
direction=buy or sell
condition_key / original_condition_key as provenance
trigger_kind=trigger or hint
trigger_mark_candidate=normal / 30m_volume / 30m_shrink
source_action_confirmation_metric_id
source_projection_run_id
projection_schema_version
metric_quality_status
trigger_time
trade_date
asset_kind
identity_key
```

N5 must reject, block, or record P0/P1 according to the run contract when N4 provides deprecated runtime signal types:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
BUY_HINT
SELL_HINT
```

Those names may appear only as:

```text
condition_key
original_condition_key
trace_json
historical compatibility trace
audit / analytics provenance
```

## 5. Required N3 Metric Consumption

N5 must use only N3 standard action-confirmation metric facts for market confirmation.

Required metric families:

```text
action_confirmation_metric_120m
action_confirmation_metric_30m
action_confirmation_metric_5m
action_confirmation_metric_1m
```

Physical N3 tables may be split by channel:

```text
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
```

N5 must join the metric table according to:

```text
asset_kind
identity_key
trade_date
source_action_confirmation_metric_id
metric_minute_label / metric_time
projection_run_id / source lineage
```

N5 must not trust `payload.action_confirmation` as final proof. If `payload.action_confirmation` is present in N4 events or historical artifacts, N5 may keep it only as trace until a compatibility contract removes it.

Required N3 metric facts include at least:

```text
current_price
previous_120m_body_high
previous_120m_body_low
previous_30m_body_high
previous_30m_body_low
previous_5m_body_high
previous_5m_body_low
previous_1m_body_high
previous_1m_body_low
current_1m_amount
previous_1m_amount
current_5m_virtual_amount
previous_5m_full_amount
is_first_1m_of_day
is_first_5m_of_day
is_first_30m_of_day
is_first_120m_of_day
first_1m_amount_default_pass
first_5m_amount_default_pass
previous_1m_period_source
previous_5m_period_source
previous_30m_period_source
previous_120m_period_source
metric_ready
metric_quality_status
source_fact_ids
source_minute_refs
previous_day_minute_refs
```

N5 may evaluate using canonical numeric fields or deterministic N3 pass flags, but either path must remain traceable to N3 metric facts.

## 6. B_BUY Market Confirmation Rule

For runtime `signal_type=B_BUY`, N5 applies a four-period AND rule.

All of the following must pass:

```text
120m:
current_price > previous_120m_body_high

30m:
current_price > previous_30m_body_high

5m:
current_price > previous_5m_body_high
AND current_5m_virtual_amount > previous_5m_full_amount

1m:
current_price > previous_1m_body_high
AND current_1m_amount > previous_1m_amount
```

If any required price condition fails, the market action is not confirmed:

```text
event_type=ActionBlocked
action_state=blocked
confirmation_status=failed
blocked_reason=price_confirmation_failed
action_mark=null
```

If any required amount condition fails, the market action is not confirmed:

```text
event_type=ActionBlocked
action_state=blocked
confirmation_status=failed
blocked_reason=amount_confirmation_failed
action_mark=null
```

If all required B_BUY rules pass:

```text
event_type=ActionExecuted
action_state=executed
confirmation_status=passed
direction=buy
signal_type=B_BUY
action_mark=normal / 30m_volume / 30m_shrink according to trigger_mark_candidate
```

## 7. S_SELL Market Confirmation Rule

For runtime `signal_type=S_SELL`, N5 applies a four-period AND rule.

All of the following must pass:

```text
120m:
current_price < previous_120m_body_low

30m:
current_price < previous_30m_body_low

5m:
current_price < previous_5m_body_low
AND current_5m_virtual_amount < previous_5m_full_amount

1m:
current_price < previous_1m_body_low
AND current_1m_amount < previous_1m_amount
```

If any required price condition fails, the market action is not confirmed:

```text
event_type=ActionBlocked
action_state=blocked
confirmation_status=failed
blocked_reason=price_confirmation_failed
action_mark=null
```

If any required amount condition fails, the market action is not confirmed:

```text
event_type=ActionBlocked
action_state=blocked
confirmation_status=failed
blocked_reason=amount_confirmation_failed
action_mark=null
```

If all required S_SELL rules pass:

```text
event_type=ActionExecuted
action_state=executed
confirmation_status=passed
direction=sell
signal_type=S_SELL
action_mark=normal / 30m_volume / 30m_shrink according to trigger_mark_candidate
```

## 8. First-Period Boundary Rule

First-period exceptions are market metric rules, not user policy rules.

For the first 1m of the trade date:

```text
amount comparison defaults to pass
price must still compare against the previous trading day's last 1m real-body high/low
```

For the first 5m of the trade date:

```text
amount comparison defaults to pass
price must still compare against the previous trading day's last 5m real-body high/low
```

For the first 30m of the trade date:

```text
price compares against the previous trading day's last 30m real-body high/low
```

For the first 120m of the trade date:

```text
price compares against the previous trading day's last 120m real-body high/low
```

There is no first-period default pass for price comparisons.

If a required previous trading day reference entity is missing, untraceable, or marked `not_available`, N5 must not default pass:

```text
event_type=ActionBlocked
action_state=blocked
confirmation_status=failed
blocked_reason=missing_previous_session_reference
action_mark=null
```

## 9. HINT Handling

`BUY_HINT` and `SELL_HINT` enter N5 as condition provenance, not as independent action types.

N4-to-N5 canonical form for BUY_HINT:

```text
signal_type=B_BUY
direction=buy
trigger_kind=hint
original_condition_key=BUY_HINT
condition_key=BUY_HINT or upstream condition provenance bundle
trigger_mark_candidate=30m_volume
action_eligible=true
```

N4-to-N5 canonical form for SELL_HINT:

```text
signal_type=S_SELL
direction=sell
trigger_kind=hint
original_condition_key=SELL_HINT
condition_key=SELL_HINT or upstream condition provenance bundle
trigger_mark_candidate=30m_shrink
action_eligible=true
```

N5 handling:

```text
BUY_HINT uses the same B_BUY 120m/30m/5m/1m confirmation rule.
SELL_HINT uses the same S_SELL 120m/30m/5m/1m confirmation rule.
N5 must not emit HintEvent for BUY_HINT / SELL_HINT in canonical runtime.
N5 must not treat hint provenance as alert-only, display-only, voice-only, sim-only, or trade-intent policy.
```

The only N5 difference is trace:

```text
trigger_kind=hint
original_condition_key=BUY_HINT / SELL_HINT
trigger_mark_candidate=30m_volume / 30m_shrink
condition provenance in trace_json
```

N6 alone decides whether a HINT-provenance action is displayed as a hint, voice alert, card, sim item, mobile message, or trade-intent candidate.

## 10. action_mark Rule

N4 provides non-final mark evidence:

```text
trigger_mark_candidate
projection_30m_flag
projection_30m_type
```

N5 does not rejudge 30m volume or 30m shrink. N5 does not recompute:

```text
current_30m_virtual_amount
previous_day_same_30m_full_amount
30m volume_up
30m shrink_down
projection_30m_flag
projection_30m_type
```

N5 may write final `action_mark` only after market action confirmation passes.

Allowed final `action_mark` values:

```text
normal
30m_volume
30m_shrink
```

Mapping after `confirmation_status=passed`:

```text
B_BUY  + current_30m_virtual_amount > previous_day_same_window_amount + buy_30m_price_pass  -> final action_mark=30m_volume
S_SELL + current_30m_virtual_amount < previous_day_same_window_amount + sell_30m_price_pass -> final action_mark=30m_shrink
otherwise, including missing previous_day_same_window_amount -> final action_mark=normal
```

N4 `trigger_mark_candidate` is retained only as trace and is not the canonical final action_mark source.

If N5 confirmation is blocked, failed, pending, skipped, expired, or quality-only:

```text
final action_mark=null
trigger_mark_candidate retained in trace_json / query column
```

## 11. Canonical Output Events

Canonical N5 output events for new runtime work:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Current market action confirmation execute semantics:

```text
ActionExecuted:
  market action confirmation passed
  action_state=executed
  confirmation_status=passed
  action_mark is non-null

ActionBlocked:
  market action confirmation did not pass because of market/system facts
  action_state=blocked
  confirmation_status=failed or blocked_* according to contract
  action_mark=null

ActionEligible:
  matched trigger passed initial N5 entry gates, but final confirmation has not yet emitted
  action_state=eligible
  must not imply user trade eligibility

ActionSkipped:
  N5 intentionally stopped without final confirmation
  may express expired via action_state=expired and reason=trigger_live_false/window_expired
```

Deprecated historical event names:

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
```

Deprecated event names may appear in historical runs or compatibility artifacts only. New canonical market action confirmation output must not use them.

## 12. ActionExecuted Meaning

`ActionExecuted` means:

```text
N5 market action confirmation fact is established.
N5 emitted a canonical action event.
```

`ActionExecuted` does not mean:

```text
real order submitted
real order filled
sim trade written
N6 user card displayed
voice/TTS spoken
mobile push sent
notification delivered
trade intent approved
user has position
user has cash
T+1 check passed
```

N6/user policy or later trade-intent contracts must consume `ActionExecuted` and then decide user-facing or account-specific outcomes.

## 13. ActionBlocked Meaning

`ActionBlocked` means:

```text
N5 did not confirm the market action.
```

It is a market/system action-confirmation result. It is not a user trading failure.

Allowed `blocked_reason` values:

```text
metric_missing
metric_quality_failed
trigger_not_live
lineage_mismatch
missing_previous_session_reference
price_confirmation_failed
amount_confirmation_failed
duplicate_action_fact
unsupported_signal_type
```

Recommended interpretation:

```text
metric_missing:
  required N3 metric fact or source_action_confirmation_metric_id is absent

metric_quality_failed:
  N3 metric exists but metric_ready=false or metric_quality_status is not usable

trigger_not_live:
  N4 trigger is no longer live or current_status is not matched

lineage_mismatch:
  N4 event lineage and N3 metric lineage do not match the allowlisted source run / trade date / identity

missing_previous_session_reference:
  first-period boundary needs previous trading day reference, but N3 marks it missing or untraceable

price_confirmation_failed:
  at least one required side-specific price comparison failed

amount_confirmation_failed:
  at least one required side-specific amount comparison failed

duplicate_action_fact:
  the write-once market action grain already exists

unsupported_signal_type:
  runtime signal_type is not B_BUY or S_SELL
```

Forbidden `blocked_reason` values in N5:

```text
no_position
insufficient_cash
t_plus_one_locked
already_sold
position_limit
blacklist
user_disabled
watchlist_disabled
account_not_ready
order_rejected
```

Those reasons belong to N6/user policy, sim, position, or real trade layers.

## 14. Action State And Confirmation Status

Canonical `action_state` values:

```text
eligible
blocked
executed
skipped
expired
```

Internal confirmation status values may include:

```text
pending
passed
failed
expired
quality_only
state_gate
blocked_unclosed
confirmation_failed
pending_confirmation
```

`confirmation_status` is an internal N5 progress/status field. It is not a user trading state.

`expired` does not create a separate `ActionExpired` event. Expiry is represented as:

```text
ActionSkipped(action_state=expired, reason=trigger_live_false)
ActionSkipped(action_state=expired, reason=window_expired)
```

## 15. Deduplication And Write-Once Grain

N5 must avoid repeatedly writing the same market action confirmation.

Recommended action grain / dedupe key:

```text
trade_date
identity_key
signal_type
trigger_kind
original_condition_key
primary_trigger_period
trigger_mark_candidate
trigger_time
```

`action_mark` must not be used as the only dedupe mark because final `action_mark` is nullable until confirmation passes. The dedupe grain should use `trigger_mark_candidate` or an explicit `action_mark_or_candidate_mark` field.

When multiple `condition_key` rows occur in the same minute for the same asset, direction, runtime signal, trigger kind, trigger mark candidate, and trigger time, N5 should merge them into one action confirmation grain by default.

Condition provenance must be preserved in `trace_json`:

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
metric_trace
minute_boundary_trace
```

If the same grain already has `ActionExecuted`:

```text
do not write another ActionExecuted
record latest_seen / quality / duplicate_action_fact when useful
preserve source event evidence in trace or quality artifacts
```

## 16. Consumer, Inbox, Checkpoint, And Watermark

N5 may consume all three N4 event types for ordered consumer progress:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
```

N5 may write scoped inbox/checkpoint rows for those events when execute is explicitly authorized. This is a consumer/watermark responsibility only.

Consumer progress must not be confused with action entry:

```text
TriggerMatched -> may create action confirmation grain
TriggerPendingMarketData -> no action confirmation grain
TriggerStateChanged -> no action confirmation grain by itself
```

Checkpoint and inbox writes must be scoped by:

```text
consumer_name
source_run_id
action_run_id
partition_key
event_id
```

Global nonzero inbox/checkpoint rows from other runs must not block a scoped execute if the target scoped refs are zero.

## 17. Source Run Allowlist And Replay

N5 execute must use explicit source-run allowlists.

Allowed source runs must be declared in the execute contract or command:

```text
--source-run-id
--action-run-id
--allow-source-run-id
```

Synthetic, stale, or unrelated N4 source runs must be denied by guard:

```text
old synthetic outbox source_run_id
stale current-real source_run_id
unexpected N4 source_run_id
non-pending event status when pending-only execute is required
```

Replay must be explicit. N5 must not silently consume old N4 outbox rows because they are still present.

## 18. Rollback Boundary

N5 business rollback must be scoped by:

```text
action_run_id
source_trigger_run_id / source_run_id
consumer_name
```

Rollback may clean only N5-scoped outputs:

```text
common_event_outbox rows emitted by N5 for the action_run_id
common_action_event rows for the action_run_id
stock_action_fact rows for the action_run_id
index_action_fact rows for the action_run_id
board_action_fact rows for the action_run_id
common_action_quality_item rows for the action_run_id
common_event_inbox rows for the N5 consumer/action_run/source_run scope
common_event_consumer_checkpoint rows for the N5 consumer/action_run/source_run scope
common_action_run row for the action_run_id
```

Rollback must hard-fail before any delete when:

```text
N5 outbox delivered/delivering > 0
N5 outbox has downstream inbox/checkpoint refs
N6/user projection/notification/decision/sim/position/voice/mobile refs exist
non-scoped consumer refs exist
scope does not match action_run_id/source_run_id/consumer_name
```

Rollback must not touch:

```text
N4 outbox status
N4 trigger facts
N3 market/action-confirmation metrics
N2 condition facts
N1 ingestion facts
N6 user/downstream facts
025 canonical schema migration
```

## 19. Run Status And Quality Severity

`common_action_run.status` must reflect the execute gate and persisted quality results.

Rules:

```text
If execute gate P0/P1/P2=0/0/0 and no failed quality item exists, common_action_run.status must not be failed.
severity=P0 with status=passed must not cause common_action_run.status=failed.
Only failed/blocking quality items may fail the run.
Dry-run stale or baseline P0 findings must not override persisted execute run status unless the execute gate itself is blocked.
```

If the run is blocked before writes:

```text
do not write action facts
do not write N5 outbox
report BLOCKED with blockers
```

If the run writes successfully and post-review row counts match the final gate:

```text
common_action_run.status=passed
run-level P0/P1/P2 are recorded according to actual failed quality items
```

## 20. Current P0 / P1 / P2 Remediation Items

Current P0 items:

```text
P0-1:
Fix common_action_run.status persistence so severity=P0,status=passed quality items do not fail the run.

P0-2:
Enforce TriggerMatched as the only action confirmation entry.
TriggerPendingMarketData and TriggerStateChanged must not create action fact or ActionExecuted/ActionBlocked action result.

P0-3:
Enforce metric-only confirmation.
N5 must join N3 action-confirmation metric facts and must not trust opaque payload.action_confirmation as final proof.

P0-4:
Constrain blocked_reason to market/system facts and reject user-layer reasons.

P0-5:
For any run that already persisted a status mismatch, rollback or keep post-review blocked until a corrected execute is authorized.
```

Current P1 items:

```text
P1-1:
Write final action_mark only when confirmation_status=passed.

P1-2:
Keep BUY_HINT / SELL_HINT only in trigger_kind/original_condition_key/trace.

P1-3:
New canonical output events must be ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped only.

P1-4:
Reports and UI must label ActionBlocked as "market action not confirmed" or equivalent, not "trade failed".

P1-5:
Static legacy schema or older sql/011 drift may remain as historical compatibility only when live DB schema and current execute contract are canonical-ready.
```

Current P2 items:

```text
P2-1:
Synchronize schema notes, docs, tests, and report wording.

P2-2:
Display blocked_reason and confirmation trace in read-only pages.

P2-3:
Add runtime_control dashboard detector for N5 status mismatch.

P2-4:
Add traceability coverage checks for N5 market action confirmation rules.
```

## 21. Recommended Implementation Route N5-R0 To N5-R6

N5-R0: rollback current failed or mismatched run

```text
Goal:
  clear the current N5 run when status mismatch or wrong persisted action facts exist.

Allowed:
  execute scoped N5 rollback after runtime_control final gate.

Forbidden:
  do not rollback N4.
  do not consume N5 outbox.
  do not enter N6.
```

N5-R1: spec freeze

```text
Goal:
  freeze this N5 market action confirmation spec and traceability document.

Allowed:
  write docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1.md
  write docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_TRACEABILITY.md

Forbidden:
  no code change.
  no database write.
  no execute.
```

N5-R2: contract alignment implementation

```text
Goal:
  align dry_run.py / execute.py / runner contracts to this spec.

Must fix:
  run status persistence.
  TriggerMatched-only action entry.
  metric-only N3 confirmation.
  blocked_reason boundary.
  action_mark finalization.
  deprecated runtime signal guard.
```

N5-R3: tests

```text
Required tests:
  TriggerPendingMarketData does not generate action fact.
  TriggerStateChanged does not generate action fact.
  severity=P0,status=passed quality item does not fail run.
  metric_missing -> ActionBlocked.
  metric_quality_failed -> ActionBlocked.
  price confirmation failed -> ActionBlocked.
  amount confirmation failed -> ActionBlocked.
  all four periods passed -> ActionExecuted.
  BUY_HINT / SELL_HINT use the same B_BUY / S_SELL rules.
  no user-layer blocked_reason in N5.
  no opaque payload.action_confirmation trust.
  final action_mark only when confirmation_status=passed.
  no ActionEvent / HintEvent / RiskEvent / PositionEvent in canonical mode.
```

N5-R4: dry-run / preflight after N4 matcher fix

```text
Goal:
  run read-only dry-run and preflight against the target N4 source_run_id.

Must confirm:
  source run allowlist.
  N4 outbox counts.
  target scoped N5 baseline=0.
  planned action grains.
  planned ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped distribution.
  rollback SQL exists and is hard-fail guarded.
```

N5-R5: execute final gate

```text
Goal:
  execute N5 run-once only after explicit user confirmation.

Required:
  --execute
  --user-confirmed
  source_run_id allowlist.
  action_run_id scoped baseline=0.
  rollback SQL ready.

Forbidden:
  do not consume N5 outbox.
  do not update N4 outbox status.
  do not enter N6.
  do not start worker.
```

N5-R6: post-review

```text
Must verify:
  common_action_run.status=passed.
  run-level P0/P1/P2 according to actual failed quality items.
  row counts match planned writes.
  ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped distribution matches contract.
  N5 outbox pending/delivered/delivering state.
  N4 outbox unchanged.
  N6/user/position refs=0.
  rollback_safe=true.
```

## 22. Runtime Control Decision Questions

Runtime control must explicitly decide:

```text
1. Freeze N5 as market-action-confirmation-only?
   Recommendation: yes.

2. Continue writing N5 inbox/checkpoint for TriggerPendingMarketData and TriggerStateChanged?
   Recommendation: yes, for consumer watermark only; never as action entry.

3. Restrict ActionBlocked reasons to market/system facts?
   Recommendation: yes.

4. Treat BUY_HINT / SELL_HINT as trace only in N5?
   Recommendation: yes.

5. Keep N6 as the first layer that can interpret user position, cash, T+1, display, voice, sim, and trade intent?
   Recommendation: yes.

6. Require N5 execute final gate for each source_run_id?
   Recommendation: yes.

7. Require rollback hard-fail guard before each N5 execute?
   Recommendation: yes.

8. Require reports/UI to label ActionBlocked as market action unconfirmed?
   Recommendation: yes.
```

## 23. Historical Compatibility And Divergence

Known divergence areas:

```text
Older N5 docs mention ActionEvent / HintEvent / RiskEvent / PositionEvent as standard outputs.
Canonical v1 treats those names as historical compatibility only.

Older N5 docs mention position state/event responsibilities.
Canonical v1 keeps position/user/account decisions out of N5.

Older flows may have used B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT as runtime signal_type.
Canonical v1 allows only B_BUY / S_SELL as runtime signal_type.

Older dry-run or execute paths may inspect payload.action_confirmation.
Canonical v1 forbids trusting that field as final proof.

Older report wording may make ActionBlocked look like a user trade failure.
Canonical v1 defines it as market/system action confirmation not passed.
```

Historical rows may remain as evidence. New work must use explicit alignment, migration, compatibility, dry-run, preflight, execute, rollback, and post-review gates.
