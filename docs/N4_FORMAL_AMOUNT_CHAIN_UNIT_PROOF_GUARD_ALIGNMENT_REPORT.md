# N4 Formal Amount Chain Unit Proof Guard Alignment Report

## Result

ALIGNMENT_PASS

## Scope

- layer_role: N4_trigger
- gate: N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_ALIGNMENT_GATE
- date: 2026-06-17
- execution: code/tests/report only
- database writes: none
- N5/N6 execution: none

## Root Decision

N4 ordinary formal BUY/SELL/FULL amount-chain evaluation now requires N3 formal amount proof to carry all three canonical fields:

- `unit_conversion_policy=formal_amount_chain_thousand_yuan_to_yuan_v1`
- `amount_unit=yuan`
- `amount_rule=attachment_dwmqy_avg_chain`

If any field is missing or mismatched, N4 returns `TriggerPendingMarketData` / quality-visible missing proof instead of `TriggerMatched`.

## Code Repair Summary

- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
  - Added `FORMAL_AMOUNT_UNIT_CONVERSION_POLICY`.
  - Added `formal_amount_chain_unit_proof_status`.
  - `evaluate_formal_amount_chain` now fail-closes before amount comparison when unit conversion proof is missing or invalid.
  - Successful formal amount details now expose `unit_conversion_policy`.
  - Price rules are unchanged.
  - BUY_HINT / SELL_HINT calibrated 30m logic is unchanged.

- `tests/test_trigger_action_confirmation_metric_matcher.py`
  - Added missing policy fail-closed coverage.
  - Added wrong policy fail-closed coverage.
  - Added `stock:SZ:002831` W amount-chain canonical unit proof coverage.
  - Updated test N3 proof fixture to include canonical unit conversion policy.

## N4 Proof Guard Implementation Proof

- Missing `unit_conversion_policy` produces:
  - `plan_status=would_pending`
  - `output_event_type=TriggerPendingMarketData`
  - `formal_trigger_period_proof_status=missing`
  - `reason=formal_amount_chain_unit_proof_missing_or_invalid`
  - `n5_entry_allowed=false`

- Mismatched `unit_conversion_policy` produces the same fail-closed pending behavior and does not write `TriggerMatched`.

## 002831 W Amount Chain Proof

Test fixture `stock:SZ:002831` with W period:

- `weekly_avg_with_today=1200000`
- `monthly_avg_with_today=1100000`
- `prev_monthly_avg=1000000`
- `amount_unit=yuan`
- `unit_conversion_policy=formal_amount_chain_thousand_yuan_to_yuan_v1`
- `amount_rule=attachment_dwmqy_avg_chain`

Expected result:

- `plan_status=would_trigger`
- `triggered_periods=["W"]`
- `amount_pass=true`

## HINT Unaffected Proof

The guard is only applied to ordinary formal `evaluate_formal_amount_chain`.

BUY_HINT / SELL_HINT still use calibrated 30m proof:

- `metric_policy=previous_day_same_window_elapsed_ratio_v1`
- `current_30m_virtual_amount`
- `previous_day_same_window_amount`
- side-specific 30m price pass flag

Existing HINT tests remain passing.

## Validation Summary

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher`: PASS, 45 tests OK
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_execute`: PASS, 6 tests OK
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_v4_enforcement`: PASS, 33 tests OK
- `python3 -m compileall src/ashare_v3/trigger tests/test_trigger_action_confirmation_metric_matcher.py tests/test_trigger_action_confirmation_metric_execute.py tests/test_n4_v4_enforcement.py`: PASS
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: PASS
- `python3 -m json.tool docs/N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_ALIGNMENT_REPORT.json >/dev/null`: PASS
- `git diff --check`: PASS

## Forbidden Scope Proof

- N4 was not executed.
- No database writes were performed.
- No outbox/inbox/checkpoint was consumed or updated.
- N5/N6 were not entered.
- No scheduler or worker was started.
- No voice/mobile/sim/position/order/real trade path was touched.

## Next Gate Prompt

`V3_20260616_N4_TRIGGER_REPLAY_AFTER_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_ROLLBACK_REGENERATION_GATE`

Purpose: scoped rollback of the stale 20260616 N4 trigger replay produced before this guard, then regenerate dry-run / contract / preflight / rollback artifacts using the guarded formal amount-chain proof.
