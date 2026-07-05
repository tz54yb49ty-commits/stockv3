# N4 Formal Price And Amount Chain Implementation Report

Result: IMPLEMENTATION_PASS

## Scope

This gate updates N4 action-confirmation metric matching only. It does not execute N4, write database rows, consume or update outbox/inbox/checkpoint, enter N5/N6, start a worker, or touch action/user/sim/voice/mobile/trade paths.

## Code Repair Summary

- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
  - Ordinary `B_BUY` / `S_SELL` matching now evaluates requested formal periods from N2 trigger baselines and N3 standard formal amount proof.
  - Formal price rule is explicit:
    - BUY: `current_price > trigger_previous_entity_high`
    - SELL: `current_price < trigger_previous_entity_low`
  - Formal amount chain rule is explicit:
    - BUY D: `today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg`
    - BUY W: `weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg`
    - BUY M: `monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg`
    - BUY Q: `quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg`
    - BUY Y: amount pass is always true once price and proof exist
    - SELL uses the symmetric `<=` chain.
  - Formal amount source guard requires `N3_standard_period_metric` with `yuan` unit proof.
  - Missing source/unit/chain proof returns `TriggerPendingMarketData` planning, not `TriggerMatched`.
  - Ordinary formal `TriggerMatched` is no longer gated by legacy 120m/5m/1m action-confirmation side flags; those flags are not N4 formal period proof.
  - HINT matching now requires calibrated 30m proof with `metric_policy=previous_day_same_window_elapsed_ratio_v1`.
  - HINT uses only `current_30m_virtual_amount` versus `previous_day_same_window_amount` plus side price pass; no 5m amount fallback.

## Test Summary

- Added/updated tests for BUY/SELL D chain pass/fail.
- Added/updated tests for W/M/Q chain pass/fail.
- Added/updated test for Y amount always pass.
- Added/updated tests for missing formal chain fields.
- Added/updated test proving ordinary formal price + amount-chain proof is sufficient even when legacy action-confirmation side flags are false.
- Added/updated tests for HINT calibrated metric policy pass/fail.
- Existing no raw minute and forbidden scope tests remain green.

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher`: PASS, 40 tests.
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher tests.test_trigger_projection_matcher tests.test_n4_trigger_rule_v4_matcher`: PASS, 74 tests.
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: PASS.
- `python3 -m compileall src/ashare_v3/trigger tests/test_trigger_action_confirmation_metric_matcher.py tests/test_trigger_projection_matcher.py tests/test_n4_trigger_rule_v4_matcher.py`: PASS.
- `python3 -m json.tool docs/N4_FORMAL_PRICE_AND_AMOUNT_CHAIN_IMPLEMENTATION_REPORT.json >/dev/null`: PASS.
- `git diff --check -- src/ashare_v3/trigger/action_confirmation_metric_matcher.py tests/test_trigger_action_confirmation_metric_matcher.py docs/N4_FORMAL_PRICE_AND_AMOUNT_CHAIN_IMPLEMENTATION_REPORT.md docs/N4_FORMAL_PRICE_AND_AMOUNT_CHAIN_IMPLEMENTATION_REPORT.json`: PASS.

## Forbidden Scope Proof

- No N4 execute was run.
- No database write was performed by this gate.
- No outbox/inbox/checkpoint consumption or update was performed.
- No N5/N6 code path was modified or executed.
- No action/user/sim/voice/mobile/trade path was modified or executed.
- Static forbidden-scope scan found only existing guard/test/report strings, not a new N5/N6 or trade execution path.

## Next Gate

Allowed next gate: N4_FORMAL_PRICE_AND_AMOUNT_CHAIN_IMPLEMENTATION_POST_REVIEW_GATE.
