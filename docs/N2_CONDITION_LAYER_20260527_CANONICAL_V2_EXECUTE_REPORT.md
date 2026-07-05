# N2 20260527 Canonical V2 Execute Report

## Result

```text
EXECUTED
layer_role=N2_condition
run_id=condition_layer_20260527_source_20260527_v2
source_trade_date=20260527
for_trade_date=20260528
prev_trade_date=20260527
status=passed_active
previous_run=condition_layer_20260527_source_20260527_v1 -> superseded
```

## Scope

Written N2 tables only:

```text
common_condition_run
common_condition_quality_item
stock/index/board_monitor_target
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
stock/index/board_condition_display_basis
```

No N1 rows, event infrastructure, N3/N4/N5/N6 facts, market data, workers, old system, or trading interfaces were touched.

## Row Counts

```text
condition_basis: stock=5506 index=83 board=428
condition_pool: stock=4307 index=22 board=273
minute_target_scope: stock=4307 index=22 board=273
condition_display_basis: stock=5506 index=83 board=428
monitor_target: stock=5506 index=83 board=428
common_condition_quality_item=103
P0/P1/P2=0/3/3
```

## Lineage

```text
v2.status=passed_active
v1.status=superseded
active_passed_count=1
v1 rows preserved=true
v1 downstream refs preserved=true
v2 downstream refs=0
n3_lineage_auto_switch=false
```

Existing v1 downstream refs remain:

```text
common_market_data_run refs=3
common_trigger_run refs=2
common_action_run refs=0
```

## Canonical Signal Audit

`allowed_signal_types` / `selected_signal_types` in v2 contain only:

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
```

Deprecated signal rows in v2:

```text
B_BUY=0
B_BUY_30M_VOL=0
S_SELL=0
S_SELL_30M_SHRINK=0
```

## Boundary Proof

Event infrastructure counts after execute:

```text
common_event_outbox=83063
common_event_inbox=2952
common_event_consumer_checkpoint=2803
```

No market data was pulled and no downstream layer was executed.

## Rollback

```text
sql/N2_condition_layer_20260527_canonical_v2_rollback.sql
```

Rollback deletes only v2 N2 rows and restores v1 to `passed_active`. Rollback is blocked if v2 already has N3/N4/N5/outbox/inbox refs.
