# 20260608 v13 Index-All Until 15:00 Metric-Aware Final Lineage Dashboard

- result: `PASS`
- layer_role: `runtime_control`
- cutoff range: `09:53 -> 15:00`
- latest closed minute: `2026-06-08T15:00:00+08:00`
- classification: `20260608_until_1500_metric_aware_action_confirmation_complete_shadow_projected`

## Lineage

- N2: `condition_layer_20260605_to_20260608_v13_index_all_execute`
- N3 subscription: `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- N3 C1: `today_minute_bar_1m_20260608_until_1500__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- N3 B2: `realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- N4: `trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- N3 metric: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- N5: `action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- N6: `user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry`

## Summary

| Stage | Result |
|---|---|
| N3 C1 today minute | `89280` rows, stock/index/board=`84720/1440/3120`, objects=`353/6/13`, duplicate keys=`0/0/0` |
| N3 B2 realtime projection | `2155` rows, ready/not_ready=`372/1783`, writes_outbox=`false` |
| N4 projection matcher | `TriggerMatched=122`, `TriggerPendingMarketData=3770`, delivered/delivering=`0` |
| N3 action-confirmation metric | metric rows=`122`, coverage=`122/122`, duplicate metric grain=`0` |
| N5 metric-aware action confirmation | `ActionBlocked=122`, `ActionExecuted=0`, `ActionEligible=0`, `ActionSkipped=0` |
| N6 readonly shadow projection/card | projection/card/notification=`122/122/0`, N5 outbox not consumed or updated |

## Rollback

Rollback SQL static contract is `PASS` after the guard repair post-review:

- `docs/RUNTIME_CONTROL_20260608_UNTIL_1500_ROLLBACK_GUARD_REPAIR_POST_REVIEW.json`

Current dependency note: because N6/N5/N4 downstream refs now exist, upstream rollback must be evaluated in reverse order under a scoped rollback gate. No rollback was executed by this registration.

## Forbidden Scope

- outbox consumed/status updated: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/order/trade/position/PnL: `false`
- real trade: `false`
- old system touched: `false`
