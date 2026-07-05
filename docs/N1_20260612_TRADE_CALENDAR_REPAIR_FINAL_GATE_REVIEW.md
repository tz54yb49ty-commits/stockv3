# N1 20260612 Trade Calendar Repair Final Gate Review

result: `PASS`  
execute_authorized: `false`  
final_execute_gate_allowed: `true`  
layer_role: `N1_ingestion`

## Findings

```text
20260611 calendar exists/open=true
20260611 next_trade_date=20260612
20260612 current calendar rows=0
Tushare read-only proof=PASS
fallback_used=false
planned 20260612 row=open / prev=20260611 / next=20260615
batch/active/quality conflicts=0/0/0
P0/P1/P2=0/0/0
```

## Planned Write Scope

Business write:

```text
common_trade_calendar: exactly 1 row for 20260612
```

Required N1 metadata:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
```

## Rollback

rollback_sql: `sql/N1_20260612_trade_calendar_repair_rollback.sql`

Rollback is scoped to `trade_date=20260612`, `source_batch_id=n1_trade_calendar_repair_20260612_v1`, `source_version=n1_trade_calendar_repair_20260612_v1`, and `scope_key=SSE:20260612`. It hard-fails before the first DELETE if N1 source facts, outbox/inbox/checkpoint, or N2-N6 refs exist.

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trade_calendar_patch_once.py \
  --dsn postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 \
  --trade-date 20260612 \
  --expected-prev-trade-date 20260611 \
  --fallback-next-trade-date 20260615 \
  --source-batch-id n1_trade_calendar_repair_20260612_v1 \
  --source-version n1_trade_calendar_repair_20260612_v1 \
  --json-report-path docs/N1_20260612_TRADE_CALENDAR_REPAIR_EXECUTE_REPORT.json \
  --markdown-report-path docs/N1_20260612_TRADE_CALENDAR_REPAIR_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N1_20260612_trade_calendar_repair_rollback.sql \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Forbidden Scope

```text
stock/index/board daily facts
stock_daily_basic / stock_financial_metrics_fact
index_membership_fact / board_membership_fact
condition_* tables
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
Parquet
worker
old system
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
```

## Next Gate

`N1_20260612_TRADE_CALENDAR_REPAIR_EXECUTE_USER_CONFIRMATION_GATE`
