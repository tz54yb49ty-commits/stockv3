# N4 HINT 30m Projection Basis Alignment Report

Result: ALIGNMENT_PASS

Date: 2026-06-13

## Scope

This implementation aligns the N4 `BUY_HINT` / `SELL_HINT` 30m projection trigger basis with the N5 final `action_mark` amount basis.

No N4 execute, worker run, database write, outbox/inbox/checkpoint consumption, N5/N6 execution, delivery, voice, mobile, sim, position, order, trade, or real-trade path was run.

## Root Cause

The N4 action-confirmation metric matcher still treated side-specific 30m HINT evidence as:

- BUY side: `buy_30m_price_pass=true` and `buy_5m_amount_pass=true`
- SELL side: `sell_30m_price_pass=true` and `sell_5m_amount_pass=true`

That was inconsistent with the current N5 final `action_mark` basis, which uses N3 metric fields:

- `current_30m_virtual_amount`
- `previous_day_same_window_amount`

The old N4 SELL path could therefore emit `trigger_mark_candidate=30m_shrink` while N5 correctly derived `action_mark=normal` because the current 30m amount was not below the previous trading day's same-window amount.

## Code Repair Summary

Updated `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`:

- N4 `BUY_HINT` / legacy `B_BUY_30M_VOL` projection evidence now requires:
  - `buy_30m_price_pass=true`
  - `current_30m_virtual_amount > previous_day_same_window_amount`
  - `previous_day_same_window_amount > 0`
- N4 `SELL_HINT` / legacy `S_SELL_30M_SHRINK` projection evidence now requires:
  - `sell_30m_price_pass=true`
  - `current_30m_virtual_amount < previous_day_same_window_amount`
  - `previous_day_same_window_amount > 0`
- Missing or invalid same-window amount keeps the HINT candidate out of `TriggerMatched`.
- N4 metric trace now carries:
  - `current_30m_virtual_amount`
  - `previous_day_same_window_amount`
  - `previous_30m_full_amount`
  - `projection_30m_amount_basis=previous_day_same_window_amount`

N5 final `action_mark` derivation remains owned by N5 and is not changed by this gate.

## Regression Proof

Updated `tests/test_trigger_action_confirmation_metric_matcher.py` to cover:

- BUY_HINT amount not exceeding previous-day same window does not emit `TriggerMatched`.
- BUY_HINT same-window volume can emit `TriggerMatched` even when the old 5m amount flag is false.
- SELL_HINT amount not shrinking versus previous-day same window does not emit `TriggerMatched`.
- SELL_HINT same-window shrink can emit `TriggerMatched` even when the old 5m amount flag is false.
- Missing `previous_day_same_window_amount` does not emit HINT `TriggerMatched`.
- Existing readiness, preflight, contract, and rollback tests for this matcher still pass.
- N5 final action-mark dry-run tests still pass, proving N5 ownership was not changed.

Validation commands:

```text
PYTHONPATH=src python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher
PYTHONPATH=src python3 -m unittest tests.test_action_dry_run
PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'
python3 -m compileall src/ashare_v3/trigger tests/test_trigger_action_confirmation_metric_matcher.py
python3 -m json.tool docs/N4_HINT_30M_PROJECTION_BASIS_ALIGNMENT_REPORT.json >/dev/null
PYTHONPATH=src python3 scripts/check_n4_contract.py
git diff --check
```

All validation commands passed.

## Forbidden Scope Proof

- N4 execute was not run.
- No worker was started.
- No database write was performed.
- No N3 outbox/inbox/checkpoint was consumed or updated.
- N5/N6 were not entered.
- No delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, or real-trade path was touched.
- Old system was not touched.

## Next Gate

Allowed next review gate:

`N4_HINT_30M_PROJECTION_BASIS_ALIGNMENT_POST_REVIEW_GATE`
