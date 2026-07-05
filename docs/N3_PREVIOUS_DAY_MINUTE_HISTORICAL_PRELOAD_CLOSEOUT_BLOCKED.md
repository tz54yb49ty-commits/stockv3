# N3 Previous-Day Minute Historical Preload Closeout

Result: BLOCKED

Generated at: 2026-06-07T16:30:24+08:00

Closeout cannot be marked complete.

```text
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
status=failed
P0/P1/P2=1/2/0
minute rows total=0
preload status rows total=256
quality rows=12
outbox refs=0
N4/N5/N6 refs=0
```

The failed run is contained to N3 evidence rows:

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_previous_day_minute_preload_status
```

No minute facts were written.

## Forbidden Scope Proof

```text
rollback_executed=false
outbox_consumed_or_updated=false
worker_started=false
entered_n4_n5_n6=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```

## Recommended Next Gate

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_FAILED_RUN_ROLLBACK_OR_REPAIR_DECISION_GATE
```
