# N1 Trade Calendar 20260605 Patch Final Gate

Result: `PASS`

This is a read-only final gate artifact. It does not execute the patch and does
not write PostgreSQL rows.

## Target

```text
layer_role = N1_ingestion
trade_date = 20260605
source_batch_id = trade_calendar_20260605_patch_v1
source_version = trade_calendar_20260605_patch_v1
scope_key = SSE:20260605
```

## Preflight

```text
preflight = docs/N1_trade_calendar_20260605_patch_preflight.json
result = PREFLIGHT_PASS
P0/P1/P2 = 0/0/0
fallback_used = false
tushare_available = true
calendar_row = is_open=true, prev=20260604, next=20260608
previous_calendar_next_trade_date = passed
```

## Live Baseline

```text
common_trade_calendar(20260605) = 0
active trade_calendar SSE:20260605 = 0
batch_conflict = 0
quality_conflict = 0
N1 source fact rows for 20260605 = 0
```

## Allowed Writes After User Confirmation

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

## Forbidden Scope

```text
stock_daily_bar_fact / index_daily_bar_fact / board_daily_bar_fact
stock_daily_basic / stock_financial_metrics_fact
index_membership_fact / board_membership_fact
condition_* tables
market_data_* tables
trigger/action/user tables
common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
N2/N3/N4/N5/N6
worker
old system
delivery / push / voice / mobile / sim / position / real trade
```

## Rollback Proof

```text
rollback_sql = sql/N1_trade_calendar_20260605_patch_rollback.sql
hard_fail_before_first_DELETE = true
guard_outbox_inbox_checkpoint = true
guard_N1_daily_fact_refs = true
guard_N2_N3_N4_N5_N6_refs = true
delete_scope = trade_calendar_20260605_patch_v1 control rows only
```

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_trade_calendar_patch_once.py \
  --dsn postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 \
  --trade-date 20260605 \
  --expected-prev-trade-date 20260604 \
  --fallback-next-trade-date 20260608 \
  --source-batch-id trade_calendar_20260605_patch_v1 \
  --source-version trade_calendar_20260605_patch_v1 \
  --json-report-path docs/N1_trade_calendar_20260605_patch_preflight.json \
  --markdown-report-path docs/N1_TRADE_CALENDAR_20260605_PATCH_PREFLIGHT.md \
  --rollback-sql-path sql/N1_trade_calendar_20260605_patch_rollback.sql \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Post-Execute Route

Only do N1 post-review:

```text
1. Confirm common_trade_calendar(20260605) exists and is_open=true.
2. Confirm prev/next = 20260604/20260608.
3. Confirm active source version SSE:20260605 exists.
4. Confirm no daily facts, outbox, inbox, checkpoint, N2/N3/N4/N5/N6 writes.
5. Do not enter official daily automatically.
```
