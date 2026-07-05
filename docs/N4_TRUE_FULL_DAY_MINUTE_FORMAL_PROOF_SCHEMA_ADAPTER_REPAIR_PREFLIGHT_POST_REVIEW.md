# N4 True Full-Day Minute Formal Proof Schema Adapter Repair Preflight

Result: `N4_FORMAL_PROOF_SCHEMA_ADAPTER_PREFLIGHT_PASS`

This gate repaired only the N4 formal amount proof adapter for `n3.action_confirmation_metric.true_full_day_minute_series.v1`. No N4 replay execute was run, and N5/N6 were not entered.

## Repair

- Accepted true-minute `formal_period_amount_proof` from `raw_json/trace_json`.
- Accepted true-minute `formal_amount_chain_metrics` field names:
  - `today_virt_amount <- current_d_virtual_amount`
  - `weekly_avg_with_today <- current_w_virtual_amount`
  - `prev_weekly_avg <- previous_w_amount`
  - `monthly_avg_with_today <- current_m_virtual_amount`
  - `prev_monthly_avg <- previous_m_amount`
  - `quarterly_avg_with_today <- current_q_virtual_amount`
  - `prev_quarterly_avg <- previous_q_amount`
  - `yearly_avg_with_today <- current_y_virtual_amount`
  - `prev_yearly_avg <- previous_y_amount`
- Added guard that true-minute proof must still provide `N3_standard_period_metric`, `yuan`, and the matching `current_amount_field`.

## Dry-Run / Preflight

- Dry-run: `DRY_RUN_PASS`
- Preflight: `PREFLIGHT_PASS`
- Replay mode: `full_day_metric_time_series`
- Candidate count: `1037284`
- `TriggerMatched=124105`
- `TriggerPendingMarketData=913179`
- `TriggerStateChanged=1037284`
- P0/P1/P2: `0/1/0`

Ordinary formal recovered:

- `ordinary_formal_count=983524`
- `ordinary_formal_matched_count=113087`
- `ordinary_formal_proof_missing_count=7449`
- Previous blocked gate had `ordinary_formal_matched_count=0`.

Sample proof:

- `stock:SH:600008`, `BUY:Q,M,W,D`, triggered `M`
- Amount chain sources:
  - `monthly_avg_with_today=formal_amount_chain_metrics.current_m_virtual_amount`
  - `quarterly_avg_with_today=formal_amount_chain_metrics.current_q_virtual_amount`
  - `prev_quarterly_avg=formal_amount_chain_metrics.previous_q_amount`

## Artifacts

- `docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_DRY_RUN.json`
- `docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_DRY_RUN.md`
- `docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_PREFLIGHT.json`
- `docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_PREFLIGHT.md`
- `docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_PREFLIGHT_POST_REVIEW.json`

## Forbidden Scope

Confirmed: no N4 replay execute, no N5/N6, no outbox/inbox/checkpoint consumption or update, no market pull, no N2/N3 fact mutation, no worker/scheduler, no voice/mobile/sim/position/order/real trade, and no old-system access.

Allowed next prompt:

```text
layer_role=N4_trigger. Enter N4_TRUE_FULL_DAY_MINUTE_TRIGGER_REPLAY_EXECUTE_AFTER_FORMAL_PROOF_SCHEMA_ADAPTER_PREFLIGHT_PASS. Use trigger_context_run_id=trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and source_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and preflight_post_review=docs/N4_TRUE_FULL_DAY_MINUTE_FORMAL_PROOF_SCHEMA_ADAPTER_REPAIR_PREFLIGHT_POST_REVIEW.json. Execute bounded N4 true full-day minute replay only; do not enter N5/N6.
```
