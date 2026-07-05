# N4/N5 Attachment Rule Canonical Freeze And Drift Review

Result: `RULE_FREEZE_PASS`

Layer role: `runtime_control`

This gate is read-only. It freezes the user-confirmed attachment rule and registers current implementation drift. No N3/N4/N5 runner was executed, no database was written, no rollback was executed, no outbox/inbox/checkpoint was consumed or updated, no scheduler/worker was started, and no N6/voice/mobile/sim/position/order/real-trade path was entered.

## Canonical Frozen Rule

### Ordinary Formal Price

For ordinary `BUY/SELL` formal conditions, all D/W/M/Q/Y periods use current price/current close against the previous period real-body boundary:

```text
BUY:  current_price/current_close > previous_period_entity_high
SELL: current_price/current_close < previous_period_entity_low
```

Current period `body_high/body_low` must not be used as trigger price proof.

### Ordinary Formal Amount

Ordinary formal amount proof no longer uses:

```text
current_period_amount > trigger_previous_amount_baseline
current_period_amount < trigger_previous_amount_baseline
```

Canonical BUY amount chain:

```text
D: today_virt_amount >= weekly_avg_with_today >= prev_weekly_avg
W: weekly_avg_with_today >= monthly_avg_with_today >= prev_monthly_avg
M: monthly_avg_with_today >= quarterly_avg_with_today >= prev_quarterly_avg
Q: quarterly_avg_with_today >= yearly_avg_with_today >= prev_yearly_avg
Y: always pass
```

Canonical SELL amount chain is the reverse `<=` chain.

### FULL

```text
BUY:FULL  -> fixed D period, today D volume-up trigger
SELL:FULL -> fixed D period, today D shrink-down trigger
```

### HINT

`BUY_HINT / SELL_HINT` are fixed 30m projection triggers. N4 does not require 30m price breakthrough.

```text
BUY_HINT:  current_30m_virtual_amount > previous_day_same_30m_full_amount
SELL_HINT: current_30m_virtual_amount < previous_day_same_30m_full_amount
```

### Virtual Amount

Canonical virtual amount policy:

```text
today_virt_amount =
  today_cumulative_amount / previous_day_same_progress_cumulative_amount * previous_day_full_amount

current_5m_virtual_amount =
  today_current_5m_elapsed_amount / previous_day_same_5m_elapsed_amount * previous_day_same_5m_full_amount

current_30m_virtual_amount =
  today_current_30m_elapsed_amount / previous_day_same_30m_elapsed_amount * previous_day_same_30m_full_amount
```

Policy: `previous_day_same_window_elapsed_ratio_v1`.

Missing or zero previous-day same-progress denominator is a quality blocker. No linear fallback is allowed.

### N5 Boundary

N5 consumes only N4 `TriggerMatched` plus N3 calibrated standard metrics. N5 does not recompute N4 trigger, does not recompute N3 indicators, and does not trust opaque `payload.action_confirmation` as final proof. Final `action_mark` remains N5-owned and is derived after confirmation from calibrated N3 30m metric evidence.

## Current Implementation Drift

### P0: N4 Formal Price Drift

`src/ashare_v3/trigger/action_confirmation_metric_matcher.py` currently evaluates ordinary formal proof with `current_{period}_body_high/body_low`.

Required: use `current_price/current_close`.

### P0: N4 Formal Amount Drift

`src/ashare_v3/trigger/action_confirmation_metric_matcher.py` currently compares `current_{period}_virtual_amount` to `trigger_previous_amount_baseline`.

Required: use the canonical D/W/M/Q/Y avg-amount chain.

### P0: N4 rule_v4 Partial Drift

`src/ashare_v3/trigger/rule_v4_matcher.py` already uses `current_price_or_close` and `trigger_amount_chain_pass`, but it still requires `current_amount_metric` versus `trigger_previous_amount_baseline`.

Required: remove old amount-baseline transition proof from ordinary formal current trigger.

### P0: HINT Price Drift

`src/ashare_v3/trigger/action_confirmation_metric_matcher.py` still requires `buy_30m_price_pass/sell_30m_price_pass` for `BUY_HINT/SELL_HINT`.

Required: HINT should use strict 30m amount comparison only.

### P0: N3 Virtual Amount Drift

`src/ashare_v3/market/realtime_virtual_metric.py` and `src/ashare_v3/market/v3_full_day_replay_plan.py` still contain linear extrapolation:

```text
current_amount / elapsed_minutes * window_minutes
```

Required: previous-day same-window same-progress calibration.

### P0: N3 Projection Plan Drift

`src/ashare_v3/market/action_confirmation_projection_plan.py` documents/produces current partial sums for 5m/30m virtual amount.

Required: calibrated virtual amount fields plus policy/source proof.

### P1: N5 Policy Guard Gap

N5 uses the expected fields but does not yet hard-require `current_5m_virtual_amount_policy/current_30m_virtual_amount_policy = previous_day_same_window_elapsed_ratio_v1`.

Required: block action confirmation when calibrated metric policy/source proof is missing or non-canonical.

## Required N3 Changes

- Add `today_virt_amount` with proof.
- Add W/M/Q/Y avg fields and previous avg fields.
- Add ordinary formal amount-chain proof by D/W/M/Q/Y.
- Add 5m/30m same-progress elapsed/full-window fields.
- Add `current_5m_virtual_amount_policy` and `current_30m_virtual_amount_policy`.
- Fail closed on missing/zero previous-day same-progress denominator.
- Preserve identity-key scoped previous-day refs.

## Required N4 Changes

- Use current price/current close for formal price proof.
- Use chain avg-amount proof for ordinary formal amount.
- Keep ordinary formal periods only in D/W/M/Q/Y.
- Keep `BUY:FULL/SELL:FULL` fixed D.
- Make `BUY_HINT/SELL_HINT` 30m amount-only at N4.
- Carry formal proof trace in N4 outbox.

## Required N5 Changes

- Require calibrated N3 metric policy for 5m/30m amount confirmation.
- Continue to consume only `TriggerMatched`.
- Continue to pass through N4 periods only.
- Continue to derive final `action_mark` from calibrated N3 30m metric after confirmation.
- Emit `ActionBlocked` when calibrated metric proof is missing.

## Test Plan

- N3 calibrated 5m/30m virtual amount formulas.
- N3 missing/zero denominator blocks.
- N3 D/W/M/Q/Y amount-chain fields.
- N4 current-price price proof.
- N4 chain amount proof.
- N4 HINT amount-only proof.
- N5 calibrated policy guard.
- N5 no period inference from condition_key.
- Replay under new run IDs after contract/preflight/rollback.

## Next Gate

```text
layer_role=runtime_control。

进入 N4_N5_ATTACHMENT_RULE_CANONICAL_SPEC_UPDATE_GATE。

目标：
把已确认的附件 N4/N5 规则写入 canonical spec / freeze artifact，并标注旧文档冲突为 superseded。
不执行 N3/N4/N5、不写数据库、不消费 outbox。
```
