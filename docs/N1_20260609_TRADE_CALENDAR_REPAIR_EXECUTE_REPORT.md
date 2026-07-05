# N1 20260609 Trade Calendar Repair Execute Report

result: `EXECUTE_PASS`  
post_review_status: `SCOPED_POST_REVIEW_PASS_GLOBAL_COUNTER_DRIFT_OBSERVED`  
layer_role: `N1_ingestion`

## Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_trade_calendar_patch_once.py \
  --dsn postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 \
  --trade-date 20260609 \
  --expected-prev-trade-date 20260608 \
  --fallback-next-trade-date 20260610 \
  --source-batch-id trade_calendar_20260609_repair_v1 \
  --source-version trade_calendar_20260609_repair_v1 \
  --json-report-path docs/N1_20260609_TRADE_CALENDAR_REPAIR_EXECUTE_REPORT.json \
  --markdown-report-path docs/N1_20260609_TRADE_CALENDAR_REPAIR_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N1_20260609_trade_calendar_repair_rollback.sql \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Inserted Row Proof

```text
common_trade_calendar(20260609)=1
exchange=SSE
is_open=true
prev_trade_date=20260608
next_trade_date=20260610
source=tushare.trade_cal.patch
source_batch_id=trade_calendar_20260609_repair_v1
source_version=trade_calendar_20260609_repair_v1
```

## Metadata Proof

```text
common_ingest_batch=1
common_active_source_version=1
common_quality_gate_result=11
batch_status=passed
batch_row_count=1
active_scope=SSE:20260609 -> trade_calendar_20260609_repair_v1
```

## Quality Proof

```text
P0/P1/P2=0/0/0
quality_by_severity_status=P0:passed=11
P0 failed=0
```

## Boundary Proof

No scoped refs were found for this repair batch/source/scope in outbox, inbox, checkpoint, N2, N3, N4, N5, or N6.

```text
stock_daily_bar_fact(20260609)=0
index_daily_bar_fact(20260609)=0
board_daily_bar_fact(20260609)=0
stock_daily_basic(20260609)=0
stock_financial_metrics_fact(20260609)=0
index_membership_fact(20260609)=0
board_membership_fact(20260609)=0
N2/N3/N4/N5/N6 refs=0/0/0/0/0
```

Global outbox/inbox/checkpoint counts changed during the execute window:

```text
before=194930/96437/5188
after=194811/92517/3191
delta=-119/-3920/-1997
```

This N1 calendar repair runner does not write those tables, and scoped refs to `trade_calendar_20260609_repair_v1` / `SSE:20260609` are `0/0/0`.

## Rollback Proof

```text
rollback_safe=true
rollback_sql=sql/N1_20260609_trade_calendar_repair_rollback.sql
hard_fail_before_delete=true
rollback refs outbox/inbox/checkpoint/N2/N3/N4/N5/N6=0/0/0/0/0/0/0/0
```

## Next Gate

`N1_20260609_TRADE_CALENDAR_REPAIR_POST_REVIEW_REGISTRATION_GATE`
