# N4/N5 Attachment Rule Canonical Alignment Implementation Report

Status: `IMPLEMENTATION_PASS`

Trade-date scope: rule implementation only. No replay execute, no DB write, no rollback, no outbox/inbox/checkpoint consumption, no scheduler/worker, no N6/user/voice/mobile/sim/position/order/real trade.

## Canonical Rule Freeze

Ordinary formal `BUY` / `SELL` now follows the attachment rule:

```text
BUY price:  current_price/current_close > previous_period_entity_high
SELL price: current_price/current_close < previous_period_entity_low
```

Ordinary formal amount is the D/W/M/Q/Y average-amount chain:

```text
BUY D: today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg
BUY W: weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg
BUY M: monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
BUY Q: quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg
BUY Y: amount_pass = true

SELL D: today_virt_amount <= weekly_avg_with_today <= prev_weekly_avg
SELL W: weekly_avg_with_today <= monthly_avg_with_today <= prev_monthly_avg
SELL M: monthly_avg_with_today <= quarterly_avg_with_today <= prev_quarterly_avg
SELL Q: quarterly_avg_with_today <= yearly_avg_with_today <= prev_yearly_avg
SELL Y: amount_pass = true
```

`BUY:FULL` / `SELL:FULL` remain fixed to D. `BUY_HINT` / `SELL_HINT` remain fixed to 30m and require only the same-window 30m amount comparison, not formal price breakthrough.

## Implementation Proof

- N3 realtime virtual metric uses `previous_day_same_window_elapsed_ratio_v1` for 5m/30m virtual amounts.
- N3 fails closed when previous-day same-window elapsed/full amount is missing or denominator is non-positive.
- N4 action-confirmation matcher evaluates formal periods from `current_price` and the attachment amount chain.
- N4 rule-v4 matcher uses `trigger_amount_chain_pass` as the formal amount condition and no longer uses old `trigger_previous_amount_baseline` comparison.
- N4 HINT 30m matcher no longer requires `buy_30m_price_pass` / `sell_30m_price_pass`.
- N5 blocks non-calibrated action-confirmation metrics with `metric_policy_invalid`.
- N5 still derives final `action_mark` from N5-owned calibrated 30m metric evidence.

## Files Changed

- `src/ashare_v3/market/realtime_virtual_metric.py`
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
- `src/ashare_v3/trigger/rule_v4_matcher.py`
- `src/ashare_v3/action/dry_run.py`
- `tests/test_v3_realtime_virtual_metric_builder.py`
- `tests/test_trigger_action_confirmation_metric_matcher.py`
- `tests/test_n4_trigger_rule_v4_matcher.py`
- `tests/test_action_dry_run.py`
- `docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md`
- `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`

## Validation

```text
targeted N3/N4/N5 tests: 96 OK
trigger test group: 150 OK
action/N4/N3 focused tests: 63 OK
test_n5*.py: 5 OK
scripts/check_n4_contract.py: PASS
compileall scoped modules/tests: PASS
report JSON parse: PASS
scoped git diff --check: PASS
```

## Forbidden Scope Proof

```text
database_write=false
runner_execute=false
rollback_execute=false
outbox_consumed=false
inbox_checkpoint_updated=false
scheduler_worker_started=false
n6_user_entered=false
voice_mobile_sim_position_order_real_trade_touched=false
old_system_touched=false
```

## Next Gate

`N4_N5_ATTACHMENT_RULE_CANONICAL_ALIGNMENT_POST_REVIEW_GATE`
