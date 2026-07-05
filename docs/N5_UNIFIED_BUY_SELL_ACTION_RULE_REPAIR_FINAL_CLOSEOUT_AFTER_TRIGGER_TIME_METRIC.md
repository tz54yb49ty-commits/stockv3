# N5 Unified Buy/Sell Action Rule Repair Final Closeout After Trigger-Time Metric

Status: BLOCKED

```text
classification=BLOCKED
blocker=N4 ordinary BUY/SELL formal live TriggerMatched evidence is still absent in the current 20260608 v13 index-all persisted lineage
n5_action_executed_zero_resolved=true
generated_at=2026-06-09T12:50:31+08:00
```

## Root Cause

- RC1 N4 ordinary formal trigger: code path repaired and covered by tests, but current 20260608 persisted N4 lineage is still HINT-only. Ordinary BUY/SELL formal `TriggerMatched` remains `0`; ordinary states remain `pending_market_data / 30m`.
- RC2 N5 HINT special-case: repaired. `BUY_HINT` / `SELL_HINT` now stay as condition provenance; N5 uses canonical `B_BUY` / `S_SELL` unified metric-aware action confirmation.
- RC3 N3 metric alignment: repaired. New N3 metric rows are trigger-row/time aligned and joined deterministically by trigger refs, asset, identity, direction, condition, trigger_time/metric_time, trade_date, and metric_run_id.
- RC4 N5 event JSON serialization: repaired. N5 action event payloads now serialize nested metric traces with datetime/date/Decimal safely.

## Rollback Execution

- Old N6 scoped projection rollback executed:
  - report: `docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_ROLLBACK_REPORT_AFTER_TRIGGER_TIME_METRIC.json`
  - deleted `user_projection_run=1`, `user_signal_projection=122`, `user_signal_card=122`, `user_notification_queue=0`.
- Old N5 scoped action rollback executed:
  - report: `docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_ROLLBACK_REPORT_AFTER_TRIGGER_TIME_METRIC.json`
  - deleted `common_action_run=1`, `stock/index/board_action_fact=113/6/3`, `common_action_event=122`, `common_event_outbox=122`, `common_event_inbox=3892`, `common_event_consumer_checkpoint=1992`.
- Post-rollback old scoped counts: old N5 run/event `0/0`, old N6 projection run `0`.

## Final Distributions

N4 `TriggerMatched`:

```text
board SELL_HINT S_SELL 30m 30m_shrink = 3
index BUY_HINT B_BUY 30m 30m_volume = 6
stock BUY_HINT B_BUY 30m 30m_volume = 110
stock SELL_HINT S_SELL 30m 30m_shrink = 3
total=122, hint_matched=122, ordinary_formal_matched=0
ordinary_state pending_market_data/30m=3770
```

N3 trigger-time aligned metric:

```text
rows stock/index/board/total = 113/6/3/122
metric_ready/not_ready = 122/0
distinct_trigger_match_refs = 122
trigger_time_aligned_rows = 122
current_price_source minute_bar_1m = 122
minute distribution = 09:43=28, 09:44=81, 09:45=10, 14:59=3
```

N5 final action events:

```text
ActionExecuted = 1
ActionBlocked = 121
ActionEligible = 0
ActionSkipped = 0
ActionExecuted detail: action_state=executed, confirmation_status=passed, action_mark=30m_volume
ActionBlocked detail: action_state=blocked, confirmation_status=failed, action_mark=NULL
```

N6 shadow projection:

```text
user_projection_run=1
user_signal_projection=122
user_signal_card=122
user_notification_queue=0
N5 outbox unchanged: ActionBlocked:pending=121, ActionExecuted:pending=1
```

## Validation

```text
JSON parse PASS: 10 generated reports
compileall PASS: scripts src tests
targeted unittest PASS: 94 tests
full unittest discover PASS: 1789 tests
git diff --check PASS: scoped files
live DB row count proof PASS
N3 metric trigger-time alignment PASS
N5 unified action rule PASS for current TriggerMatched rows
N4 ordinary formal semantic proof BLOCKED: ordinary formal live TriggerMatched remains 0
```

## Forbidden Scope Proof

```text
old_system_touched=false
worker_started=false
real_trade=false
delivery_push_voice_mobile=false
sim_order_trade_position_pnl=false
N5 outbox consumed/delivered=false
N5 delivered/delivering outbox count=0
global user_signal_decision=0
global user_sim_order/trade/position=0/0/0
non_scoped_write_detected=false
```

## Required Next Gate

```text
blocked_by_layer=N4_trigger
source_layer=runtime_control
evidence=Current persisted N4 distribution remains HINT-only: TriggerMatched=122, ordinary_formal_matched=0, ordinary_state pending_market_data/30m=3770.
suggested_next_step=Regenerate or repair N3 B2/N4 formal enrichment input for 20260608 v13 index-all, then rerun scoped N4 trigger execute and downstream N5/N6 on the same trigger-time-aligned metric contract.
```
