# N3-C3 MinuteBarClosed Outbox Execute Preflight

## Summary

- result: `PREFLIGHT_PASS`
- layer_role: `N3_market_data`
- c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- runner_readiness: `ready`
- execute_authorized_now: `false`
- execute_allowed_after_user_final_gate: `true`
- common_market_data_run source_trade_date / prev_trade_date: `20260525 / 20260525`
- previous_day_minute_date trace: `20260522`
- writes_outbox: `true`
- consumes_outbox: `false`

This preflight is no-write. It confirms the runner and contract are ready, but C3 execute still requires explicit final user confirmation.

## Baseline Proof

- common_market_data_run scoped rows: `0`
- common_market_data_quality_item scoped rows: `0`
- common_event_outbox scoped rows: `0`
- common_event_inbox scoped rows: `0`
- common_event_consumer_checkpoint scoped refs: `0`
- source subscription status: `passed`
- source C2 replay status: `passed`

## Expected Write Summary

- outbox rows: `17432`
- event_type: `MinuteBarClosed`
- stock/index/board: `16344/72/1016`
- status after execute: `pending`
- delivered/delivering after execute: `0`
- quality P0/P1/P2: `0/1/0`

## Boundary

Allowed writes at execute:

```text
common_market_data_run
common_market_data_quality_item
common_event_outbox
```

Forbidden:

```text
common_event_inbox
common_event_consumer_checkpoint
closed summary modification
minute_bar modification
projection/snapshot modification
N4/N5/N6 replay
worker
old system
```

## Rollback

Rollback path: `sql/N3_C3_minute_bar_closed_outbox_rollback.sql`

Rollback is safe only while C3 outbox remains pending and no inbox/checkpoint references exist.
