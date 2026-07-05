# N1 20260609 Trade Calendar Repair Dry-Run

result: `DRY_RUN_PASS`  
layer_role: `N1_ingestion`  
trade_date: `20260609`  
scope_key: `SSE:20260609`

## Source Proof

Tushare `trade_cal` returned one authoritative row for `20260609`.

```text
source=tushare.trade_cal
fallback_used=false
weekday_only_proof_used=false
is_open=true
prev_trade_date=20260608
next_trade_date=20260610
```

Local input artifacts:

```text
docs/RUNTIME_20260609_TRADE_CALENDAR_READINESS_OR_REPAIR.md
docs/RUNTIME_20260609_TRADE_CALENDAR_READINESS_OR_REPAIR.json
```

## Current DB Baseline

Readonly DB proof:

```text
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1/32:5432
transaction_read_only=on
common_trade_calendar(20260609).total_count=0
common_trade_calendar(20260609).open_count=0
active_conflict_count=0
batch_conflict_count=0
quality_conflict_count=0
outbox/inbox/checkpoint=194930/96437/5188
```

Upstream calendar chain proof:

```text
common_trade_calendar(20260608).is_open=true
common_trade_calendar(20260608).next_trade_date=20260609
```

## Repair Plan

```text
planned_insert_rows=1
planned_update_rows=0
planned_delete_rows=0
source_batch_id=trade_calendar_20260609_repair_v1
source_version=trade_calendar_20260609_repair_v1
calendar_row=20260609 / SSE / open / prev=20260608 / next=20260610
```

Future execute may write only:

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

## Quality

```text
P0/P1/P2=0/0/0
```

## Boundary

This dry-run did not write database rows, execute rollback SQL, enter N2/N3/N4/N5/N6, update outbox/inbox/checkpoint, start a worker, pull realtime quotes, or touch delivery/push/voice/mobile/sim/position/pnl/real_trade/proposal/order/trade.

## Rollback

Rollback draft:

```text
sql/N1_20260609_trade_calendar_repair_rollback.sql
```

Rollback is scoped by `trade_date=20260609`, `source_batch_id=trade_calendar_20260609_repair_v1`, `source_version=trade_calendar_20260609_repair_v1`, and `scope_key=SSE:20260609`. It includes a `RAISE EXCEPTION` guard before the first `DELETE`.

## Next Gate

`N1_20260609_TRADE_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW`
