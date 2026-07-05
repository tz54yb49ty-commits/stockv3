# v3 N3/N4/N5 Action Confirmation Rule Canonical Spec

Status: canonical

Supersession note for N4:

```text
effective_at = 2026-06-26
n4_trigger_side_rule_definitions = superseded_for_future_alignment
replacement_doc = docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
historical_run_interpretation_rewritten = false
```

Frozen at: 2026-06-02

Scope: N3 action-confirmation projection facts, N4 trigger consumption boundary, and N5 final action confirmation rules.

Current ownership clarification:

```text
N3 action-confirmation projection facts = authoritative here
N4 trigger-side rule definitions = authoritative in docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md
N5 final action confirmation rules = authoritative here
```

This freeze is documentation only:

```text
code_change = false
schema_migration = false
database_write = false
outbox_write = false
inbox_checkpoint_write = false
execute = false
worker_started = false
real_trade = false
```

Authoritative upstream specs:

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md
```

If older design docs, SQL drafts, code, tests, or reports conflict with this spec, this spec wins for future alignment work. Historical run evidence must remain auditable under the contract that produced it and must not be silently rewritten.

2026-06-12 realtime execution clarification:

```text
docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_EXECUTABLE_PLAN.md
```

N4 must not read raw unclosed minute rows or assemble raw 1m/5m/30m/120m
indicators. N4 may consume N3 standardized, traceable realtime virtual metrics
to emit TriggerMatched before the trigger-minute 1m fact is closed. N5
ActionExecuted still requires the trigger-time virtual 120m/30m/5m metric
snapshot plus the closed/settled trigger-minute 1m confirmation fact. This
clarification does not change the B_BUY/S_SELL rule set; it only freezes the
source and timing semantics.

## 1. Layer Ownership

Canonical ownership:

```text
N3 owns action-confirmation projection facts.
N4 consumes N3 standard metrics to decide trigger live state, TriggerMatched, TriggerPendingMarketData, TriggerStateChanged, and 30m trigger marker evidence.
N5 consumes N3T action-confirmation metrics plus N4 TriggerMatched to decide final ActionExecuted confirmation.
N6 owns user presentation, alert-only, push, voice, mobile, sim, position interpretation, and trade-intent presentation.
```

Forbidden shortcuts:

```text
N4 must not pull market data.
N4 must not read raw minute bars and assemble 1m/5m/30m/120m indicators itself.
N4 must not decide final action confirmation.
N5 must not pull market data.
N5 must not read raw minute bars and assemble 1m/5m/30m/120m indicators itself.
N5 must not trust opaque action_confirmation payloads as final confirmation proof.
N5 must not enter N6 policy, sim, position lock, push, voice, mobile, or real trade.
```

N3T contract registration for N5 final proof:

```text
N3T = N3_market_data independent C1-derived transform.
C1 = closed 1m K only.
source_basis = N3T_C1_CLOSED
metric_role = action_confirmation
proof_consumer = N5
not_n5_final_proof = false
run_id_prefix = n3t_action_confirmation_metric_YYYYMMDD_until_HHMM__
```

N3T must not reuse or mutate N3P/B1/B2 `target_run_id`, `source_run_id`, `proof_kind`, `metric_role`, outbox,
worker, launchd job, lineage config, rollback scope, or fact rows. N3P/B1/B2 remain trace or trigger proof only;
they are not final `ActionExecuted` proof.

The recommended N3T schema direction is Option A, new physical tables:

```text
stock_n3t_action_confirmation_metric
index_n3t_action_confirmation_metric
board_n3t_action_confirmation_metric
```

Option B may reuse an existing metric family only after a later explicit schema gate and only with
`metric_role=action_confirmation`, `proof_consumer=N5`, `source_basis=N3T_C1_CLOSED`, and
`not_n5_final_proof=false`.

## 2. N3 Action-Confirmation Projection Facts

N3 must produce standard, traceable action-confirmation projection facts before N4/N5 can rely on this rule set.

Minimum identity and lineage fields:

```text
action_confirmation_metric_id
projection_run_id
projection_schema_version
source_condition_run_id
source_subscription_run_id
source_snapshot_run_id
source_snapshot_id
source_snapshot_event_id
source_today_minute_run_id
source_previous_day_minute_run_id
asset_kind
identity_key
trade_date
metric_time
metric_minute_label
metric_quality_status
metric_ready
source_fact_ids
source_minute_refs
previous_day_minute_refs
raw_json
```

Canonical price fields:

```text
current_price
current_price_source
current_price_time

previous_120m_body_high
previous_120m_body_low
previous_30m_body_high
previous_30m_body_low
previous_5m_body_high
previous_5m_body_low
previous_1m_body_high
previous_1m_body_low
```

Canonical amount fields:

```text
current_1m_amount
previous_1m_amount
current_5m_virtual_amount
previous_5m_full_amount
```

Canonical first-period boundary fields:

```text
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
boundary_policy_version
```

Allowed `previous_*_period_source` values:

```text
same_trade_date_previous_period
previous_trade_date_last_period
not_available
```

N3 may also expose deterministic pass flags for convenience, but those flags must be derived from the canonical numeric fields above and traceable through `source_fact_ids`:

```text
buy_120m_price_pass
buy_30m_price_pass
buy_5m_price_pass
buy_5m_amount_pass
buy_1m_price_pass
buy_1m_amount_pass

sell_120m_price_pass
sell_30m_price_pass
sell_5m_price_pass
sell_5m_amount_pass
sell_1m_price_pass
sell_1m_amount_pass
```

## 2.1 N4 Formal Trigger Rule Freeze

This 2026-06-15 freeze supersedes older ordinary formal amount wording that
used `current_period_amount > trigger_previous_amount_baseline`.

Ordinary `BUY` / `SELL` formal price proof:

```text
BUY period D/W/M/Q/Y:  current_price/current_close > previous_period_entity_high
SELL period D/W/M/Q/Y: current_price/current_close < previous_period_entity_low
```

N4 must not use current-period `body_high/body_low` as the formal breakthrough
price. Current-period body fields may remain trace only.

Ordinary `BUY` / `SELL` formal transition proof:

```text
BUY period D/W/M/Q/Y target_transition = volume_up:
  current_price/current_close > previous_period_entity_high
  AND current_period_avg_with_today > N2 previous complete same-period amount

SELL period D/W/M/Q/Y target_transition = low_volume_down:
  current_price/current_close < previous_period_entity_low
  AND current_period_avg_with_today < N2 previous complete same-period amount
```

`previous_transition` must come from the localized N2 context /
`period_trigger_baseline_json.periods[P].previous_transition`.  The transition
previous amount is also N2-owned and must come from the localized
`period_trigger_baseline_json.periods[P]` fields, in this priority order:

```text
previous_avg_amount
previous_amount
previous_amount_baseline
classification_previous_amount_baseline
```

N4 must standardize these N2 amount fields to yuan before comparison.  N4 must
not use `trigger_previous_amount_baseline`, `current_amount_seed`,
`current_avg_amount_seed`, or `current_amount_total_seed` as the transition
previous amount.  A formal D/W/M/Q period may trigger only when:

```text
previous_transition != target_transition
AND current_transition == target_transition
AND trigger_amount_chain_pass = true
```

`Y` is also an ordinary formal period.  It has no upper-period amount chain, so
the trigger amount-chain gate is `not_applicable` and must be treated as a
no-op gate, not as pass-by-default and not as failure.  A formal Y period may
trigger only when:

```text
previous_transition != target_transition
AND current_transition == target_transition
```

Therefore Y may enter `triggered_periods`, `all_trigger_periods`, and
`primary_trigger_period` when the Y transition upgrade proof passes.  N4 must
still forbid any `always_true_for_Y` implementation: absence of an upper amount
chain does not by itself make Y triggered.

Ordinary `BUY` trigger amount-chain proof, used as the second gate after the
transition proof:

```text
D: today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg
W: weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg
M: monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
Q: quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg
Y: no_upper_period_chain / trigger amount-chain not_applicable no-op; Y trigger decided by transition upgrade proof
```

Ordinary `SELL` trigger amount-chain proof, used as the second gate after the
transition proof:

```text
D: today_virt_amount <= weekly_avg_with_today <= prev_weekly_avg
W: weekly_avg_with_today <= monthly_avg_with_today <= prev_monthly_avg
M: monthly_avg_with_today <= quarterly_avg_with_today <= prev_quarterly_avg
Q: quarterly_avg_with_today <= yearly_avg_with_today <= prev_yearly_avg
Y: no_upper_period_chain / trigger amount-chain not_applicable no-op; Y trigger decided by transition upgrade proof
```

`BUY:FULL` and `SELL:FULL` are fixed to the D period and must reuse the same
D transition upgrade proof plus D trigger amount-chain proof.  FULL must output
`trigger_period=D` and `triggered_periods=["D"]` only when the D formal gate
passes; it must not bypass the transition gate.

N3 must publish the second-gate amount-chain fields and proof trace. N4 must
fail closed to `TriggerPendingMarketData` or quality-visible blocking when any
required price, N2 transition amount, N3 chain amount, source, or unit proof is
missing. N4 must not fallback to `trigger_previous_amount_baseline` or current
seed amount fields for ordinary formal transition proof.

5m/30m virtual amount policy:

```text
policy_version = previous_day_same_window_elapsed_ratio_v1
virtual_amount = today_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount
```

Missing previous-day same-window elapsed amount, missing previous-day same-window
full amount, or non-positive denominator is fail-closed. N3/N4/N5 must not use
linear elapsed extrapolation as a fallback.

`BUY_HINT` and `SELL_HINT` are fixed 30m projection conditions and do not run
ordinary formal Y/Q/M/W/D transition gates in N4:

```text
BUY_HINT: current_30m_virtual_amount > previous_day_same_30m_full_amount
SELL_HINT: current_30m_virtual_amount < previous_day_same_30m_full_amount
```

The current DB field `previous_day_same_window_amount` is the N3/N5 canonical
storage alias for `previous_day_same_30m_full_amount`.

HINT still requires N3 calibrated metric policy proof.  Runtime `signal_type`
must be `B_BUY` / `S_SELL`; `BUY_HINT` / `SELL_HINT` may remain only in
`condition_key`, `original_condition_key`, and trace fields.  HINT
`TriggerMatched` payloads must not populate ordinary Y/Q/M/W/D
`triggered_periods`.

N5 must consume only N3 calibrated metrics and N4 proven trigger fields. N5 must
not infer `triggered_periods`, `all_trigger_periods`, or
`primary_trigger_period` from `condition_key`, `original_condition_key`, or
`required_periods`. N5 must block non-calibrated metrics with
`metric_policy_invalid`.

## 3. First-Period Boundary Policy

The first-period boundary policy is canonical and must be produced by N3 as explicit facts.

1m:

```text
If this is the first 1m of the trade date:
  amount comparison defaults to pass.
  price compares current_price with the previous trading day's last 1m real-body high/low.
If this is not the first 1m:
  amount compares current_1m_amount with previous_1m_amount.
  price compares current_price with the same trade date previous 1m real-body high/low.
```

5m:

```text
If this is the first 5m of the trade date:
  amount comparison defaults to pass.
  price compares current_price with the previous trading day's last 5m real-body high/low.
If this is not the first 5m:
  amount compares current_5m_virtual_amount with previous_5m_full_amount.
  price compares current_price with the same trade date previous 5m real-body high/low.
```

30m:

```text
If this is the first 30m of the trade date:
  price compares current_price with the previous trading day's last 30m real-body high/low.
If this is not the first 30m:
  price compares current_price with the same trade date previous 30m real-body high/low.
```

120m:

```text
If this is the first 120m of the trade date:
  price compares current_price with the previous trading day's last 120m real-body high/low.
If this is not the first 120m:
  price compares current_price with the same trade date previous 120m real-body high/low.
```

Boundary failures:

```text
Missing previous period body high/low = metric_ready=false.
Missing required amount field outside first 1m/5m = metric_ready=false.
Untraceable previous-period source = metric_ready=false.
N4/N5 must not repair missing N3 metrics by reading raw minute facts.
```

## 4. Final N5 Confirmation Rules

N5 final confirmation must evaluate `signal_type` using N3 standard action-confirmation metrics and a live N4 `TriggerMatched` event.

B_BUY passes only when all conditions pass:

```text
120m: current_price > previous_120m_body_high
30m:  current_price > previous_30m_body_high
5m:   current_price > previous_5m_body_high
      AND current_5m_virtual_amount > previous_5m_full_amount
1m:   current_price > previous_1m_body_high
      AND current_1m_amount > previous_1m_amount
```

S_SELL passes only when all conditions pass:

```text
120m: current_price < previous_120m_body_low
30m:  current_price < previous_30m_body_low
5m:   current_price < previous_5m_body_low
      AND current_5m_virtual_amount < previous_5m_full_amount
1m:   current_price < previous_1m_body_low
      AND current_1m_amount < previous_1m_amount
```

First-period amount exception:

```text
For the first 1m of the trade date, current_1m_amount comparison is default pass.
For the first 5m of the trade date, current_5m_virtual_amount comparison is default pass.
first 1m amount comparison defaults to pass.
first 5m amount comparison defaults to pass.
There is no first-period default pass for price comparisons.
There is no amount condition for 30m or 120m in this rule set.
```

Final action result:

```text
If every required side-specific rule passes:
  confirmation_status = passed
  action_state = executed
  event_type = ActionExecuted
  action_mark = normal / 30m_volume / 30m_shrink according to N5-owned metric comparison:
    B_BUY: current_30m_virtual_amount > previous_day_same_window_amount and buy_30m_price_pass -> 30m_volume
    S_SELL: current_30m_virtual_amount < previous_day_same_window_amount and sell_30m_price_pass -> 30m_shrink
    otherwise -> normal
  If previous_day_same_window_amount is missing, ActionExecuted may still pass, but action_mark must downgrade to normal with action_mark_reason=previous_day_same_window_amount_missing.

If any required N3 metric is missing, unready, untraceable, or contradictory:
  confirmation_status = failed or pending, according to the explicit N5 contract for the run mode.
  action_state must not be executed.
  final action_mark must be NULL unless confirmation_status=passed.
```

## 5. N4 Contract Boundary

N4 may consume only N3 standard events and N3 standard projection facts.

N4 may decide:

```text
trigger_live
current_status
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
projection_30m_flag
projection_30m_type
trigger_mark_candidate
```

N4 must carry enough trace for N5:

```text
source_action_confirmation_metric_id
source_projection_run_id
projection_schema_version
source_snapshot_run_id
source_snapshot_event_id
projection_30m_type
trigger_mark_candidate
metric_quality_status
```

N3 action-confirmation metric must provide N5 action-mark basis:

```text
current_30m_virtual_amount
previous_day_same_window_amount
```

N4 must not:

```text
compute current_5m_virtual_amount
compute previous_5m_full_amount
compute previous_1m/5m/30m/120m body high/low
read raw minute bars for action confirmation
decide final action_mark
use N4 trigger_mark_candidate as final action_mark source
emit opaque action_confirmation as proof for N5
```

## 6. N5 Contract Boundary

N5 starts action confirmation only from `TriggerMatched`.

N5 must read or receive a traceable N3 action-confirmation metric set. The N4 payload may carry metric identifiers and trace, but N5 must not treat an opaque payload field as final proof.

Canonical N5 rule:

```text
N5 may evaluate final confirmation using N3 standard numeric fields or N3 deterministic pass flags.
N5 may not read raw minute facts to assemble missing 1m/5m/30m/120m indicators.
N5 may not call external market data adapters.
N5 may not use payload.action_confirmation as authoritative proof.
N5 must not use payload.action_confirmation as authoritative proof.
payload.action_confirmation, if present in historical or compatibility flows, is trace-only until a separate alignment contract replaces it.
```

If N3 metrics are not ready:

```text
TriggerMatched remains valid N4 evidence.
N5 must not emit ActionExecuted.
N5 may emit ActionBlocked, ActionEligible, or ActionSkipped only according to an explicit N5 run-mode contract.
```

## 7. Divergence List

Known divergence at freeze time:

```text
sql/015_market_realtime_projection_metric_schema.sql currently models active 30m projection only and lacks the canonical 120m/30m/5m/1m action-confirmation metric fields.
src/ashare_v3/market/realtime_projection_execute.py currently builds 30m projection status and amount ratios, not the full action-confirmation metric set.
src/ashare_v3/trigger/projection_matcher.py currently maps 30m projection status to trigger_mark_candidate; it does not carry a full source_action_confirmation_metric_id contract.
src/ashare_v3/action/dry_run.py currently accepts payload.action_confirmation as pass/fail input; future N5 alignment must replace that with N3 standard metric consumption.
docs/V3_N5_ACTION_LAYER_DEVELOPMENT_DESIGN.md still contains legacy ActionEvent / HintEvent / RiskEvent / PositionEvent and deprecated signal wording; canonical runtime work must follow this spec and docs/N5_CANONICAL_ACTION_FLOW_v0.1.md.
```

## 8. Required Handoff Order

Future alignment must use separate layer gates:

```text
1. runtime_control: freeze this documentation-only spec.
2. N3_market_data: draft schema/readiness/tests for action-confirmation projection facts.
3. N3_market_data: dry-run / contract / preflight, then separate execute gate if authorized.
4. N4_trigger: update N4 contract to consume N3 action-confirmation metric identifiers and 30m marker facts only.
5. N5_action: update N5 contract/code/tests to confirm using N3 metrics plus N4 TriggerMatched.
6. runtime_control: register lineage and readiness; do not execute N3/N4/N5 from runtime_control.
```

Forbidden in this freeze:

```text
Do not modify SQL.
Do not modify src/scripts/tests.
Do not run migrations.
Do not write database rows.
Do not execute N3/N4/N5.
Do not consume outbox.
Do not start workers.
Do not enter N6.
```
