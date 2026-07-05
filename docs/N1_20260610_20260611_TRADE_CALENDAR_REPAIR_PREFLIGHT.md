# N1 20260610/20260611 Trade Calendar Repair Preflight

Result: `PREFLIGHT_PASS`

Blocked: `false`

Execute authorized: `false`

This gate did not execute repair or write the database.

## Source Proof

- source: `tushare.trade_cal`
- source status: `PASS`
- fallback used: `false`
- weekday-only proof used: `false`
- `20260610`: open=`true`, prev=`20260609`, next=`20260611`
- `20260611`: open=`true`, prev=`20260610`, next=`20260612`

## Current DB Baseline

- `common_trade_calendar(20260610)`: total=`0`, open=`0`
- `common_trade_calendar(20260611)`: total=`0`, open=`0`
- common_ingest_batch conflict: `0`
- common_active_source_version conflict: `0`
- common_quality_gate_result conflict: `0`
- scoped outbox/inbox/checkpoint refs: `0/0/0`
- scoped N2/N3/N4/N5/N6 refs: `0/0/0/0/0`

## Planned Repair

Planned insert rows: `2`

- `trade_calendar_20260610_repair_v1`, scope=`SSE:20260610`
- `trade_calendar_20260611_repair_v1`, scope=`SSE:20260611`

Allowed future write tables:

- `common_ingest_batch`
- `common_trade_calendar`
- `common_active_source_version`
- `common_quality_gate_result`

## Quality

P0/P1/P2: `0/0/0`

## Rollback

Rollback SQL:

`sql/N1_20260610_20260611_trade_calendar_repair_rollback.sql`

Static scope:

- `RAISE EXCEPTION` before first `DELETE`
- no `DROP`, `TRUNCATE`, or `CASCADE`
- no DML against outbox/inbox/checkpoint
- no DML against N2/N3/N4/N5/N6
- no N1 source fact deletes

## Next Gate

Allowed:

`N1_20260610_20260611_TRADE_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW`
