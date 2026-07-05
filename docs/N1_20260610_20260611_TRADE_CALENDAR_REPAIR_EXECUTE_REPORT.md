# N1 20260610/20260611 Trade Calendar Repair Execute Report

Result: `EXECUTE_PASS`

## Inserted Row Proof

- 20260610 row_count=`1`, open=`True`, prev=`20260609`, next=`20260611`
- 20260611 row_count=`1`, open=`True`, prev=`20260610`, next=`20260612`

## Metadata Proof

- batch rows: 20260610=`1`, 20260611=`1`
- active rows: SSE:20260610=`1`, SSE:20260611=`1`
- quality rows: 20260610=`11`, 20260611=`11`
- P0 failed rows: 20260610=`0`, 20260611=`0`

## Boundary Proof

- N1 source fact row counts for 20260610/20260611 remain `0` across checked stock/index/board daily, stock_daily_basic, stock_financial, index_membership, board_membership tables.
- scoped outbox/inbox/checkpoint refs: `0/0/0`
- scoped N2/N3/N4/N5/N6 refs: `0/0/0/0/0`

## Rollback

- rollback SQL: `sql/N1_20260610_20260611_trade_calendar_repair_rollback.sql`
- rollback_safe: `True`
- hard_fail_before_delete: `True`
- delete targets: `COMMON_ACTIVE_SOURCE_VERSION, COMMON_INGEST_BATCH, COMMON_QUALITY_GATE_RESULT, COMMON_TRADE_CALENDAR`

## Forbidden Scope

No condition source, N2-N6, outbox/inbox/checkpoint, worker, realtime quote, rollback SQL execution, old system, or trading/sim scope was touched by this gate.
