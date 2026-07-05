# N4 Formal Trigger Amount Unit Baseline Alignment Report

Result: `ALIGNMENT_PASS`

Generated at: `2026-06-15`

## Root Cause

N4 formal BUY/SELL/FULL matching could promote `realtime_daily_snapshot.amount` into `current_amount_metric` through the formal snapshot fallback path. That snapshot amount was then compared against N2 `trigger_previous_amount_baseline` without a required source-kind proof and unit proof, which allowed false `Y/Q/M/W/D` `TriggerMatched` rows.

Observed tainted sample:

- `trigger_match_id=266600`
- `identity_key=stock:SH:603226`
- `condition_key=BUY:M,D`
- `current_amount_metric=58,861,092`
- `D previous_amount_baseline=330,870.448`
- `triggered_periods=["M","D"]`
- N3 30m projection was `blocked/not_ready/unknown`

## Code Repair Summary

- `src/ashare_v3/trigger/rule_v4_matcher.py`
  - Formal period matching now requires `current_amount_metric_source_kind=N3_standard_period_metric`.
  - Formal period matching still requires declared matching amount units.
  - Missing or invalid source proof produces pending detail reason `formal_period_metric_source_not_allowed` or `formal_period_metric_source_not_proven`.

- `src/ashare_v3/trigger/projection_matcher.py`
  - Formal snapshot fallback no longer writes snapshot amount as triggerable `current_amount_metric`.
  - Snapshot amount is retained as `snapshot_amount_trace`.
  - Snapshot fallback amount-chain pass is no longer true for formal periods; it is trace-only until N3 provides standardized period metrics.

## Proof Counters

Expected after repaired dry-run / replay:

- `ordinary_formal_snapshot_amount_promoted_to_trigger_matched=0`
- `formal_amount_unit_not_proven_matched=0`
- `formal_period_metric_source_invalid_matched=0`
- `projection_quality_blocked_trigger_matched=0` for ordinary formal path

## Regression Proof

- Raw snapshot amount with no standard period metric source cannot produce `TriggerMatched`.
- Standardized period metric with matching unit proof can still produce formal `TriggerMatched`.
- `BUY_HINT` / `SELL_HINT` 30m projection semantics remain legal.
- 30m projection fields still do not enter formal `triggered_periods`, `all_trigger_periods`, or `primary_trigger_period`.

## Forbidden Scope Proof

- N4 was not executed.
- No database writes were performed by this gate.
- No rollback SQL was executed.
- No N3 outbox/inbox/checkpoint was consumed or updated.
- N5/N6 were not entered.
- No worker, scheduler, delivery, push, voice, mobile, sim, position, order, trade, or real-trade path was touched.

## Validation

- Targeted matcher tests: PASS
- Compile / broader validation: see final gate output for command results.

