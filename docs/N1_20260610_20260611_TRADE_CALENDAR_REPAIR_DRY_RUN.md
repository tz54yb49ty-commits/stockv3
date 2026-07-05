# N1 20260610/20260611 Trade Calendar Repair Dry Run

Result: `DRY_RUN_PASS`

Layer role: `N1_ingestion`

This gate is dry-run only. It did not execute repair, write PostgreSQL, run rollback SQL, enter N2-N6, consume outbox/inbox/checkpoint, start a worker, pull realtime quotes, touch old system, or touch proposal/order/trade/sim/position/PnL/real trade.

## Source Proof

Authoritative source: `tushare.trade_cal`

Fallback used: `false`

Weekday-only proof used: `false`

Rows:

- `20260610`: open=`true`, prev=`20260609`, next=`20260611`
- `20260611`: open=`true`, prev=`20260610`, next=`20260612`

## Current DB Baseline

Target DB: `ashare_v3 / ashare_v3_user / 127.0.0.1/32:5432`

Transaction mode: `read_only=on`

- `common_trade_calendar(20260610)`: total=`0`, open=`0`
- `common_trade_calendar(20260611)`: total=`0`, open=`0`
- batch conflicts: `0`
- active source_version conflicts: `0`
- quality conflicts: `0`
- scoped outbox/inbox/checkpoint refs: `0/0/0`
- scoped N2/N3/N4/N5/N6 refs: `0/0/0/0/0`

## Planned Repair

Planned insert rows: `2`

No updates, no deletes.

Rows:

- `SSE:20260610`, source_batch_id/source_version=`trade_calendar_20260610_repair_v1`
- `SSE:20260611`, source_batch_id/source_version=`trade_calendar_20260611_repair_v1`

## Future Write Scope

Allowed only:

- `common_ingest_batch`
- `common_trade_calendar`
- `common_active_source_version`
- `common_quality_gate_result`

Forbidden:

- daily facts
- condition source facts
- N2/N3/N4/N5/N6
- outbox/inbox/checkpoint
- Parquet
- worker
- old system
- proposal/order/trade/sim/position/PnL/real trade

## Quality

P0/P1/P2: `0/0/0`

## Rollback

Rollback SQL:

`sql/N1_20260610_20260611_trade_calendar_repair_rollback.sql`

Rollback is scoped by trade_date/source_batch_id/source_version/scope_key and hard-fails before the first `DELETE`.

## Next Gate

`N1_20260610_20260611_TRADE_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW`
