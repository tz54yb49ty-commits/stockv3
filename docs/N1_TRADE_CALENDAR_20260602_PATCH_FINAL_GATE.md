# N1 Trade Calendar 20260602 Patch Final Gate

Result: `PASS`

This is a read-only final gate artifact. It does not execute the patch and does not write PostgreSQL rows.

## Target

```text
layer_role = N1_ingestion
trade_date = 20260602
source_batch_id = trade_calendar_20260602_patch_v1
source_version = trade_calendar_20260602_patch_v1
scope_key = SSE:20260602
```

## Preflight

```text
preflight = docs/N1_trade_calendar_20260602_patch_preflight.json
result = PREFLIGHT_PASS
P0/P1/P2 = 0/0/1
fallback_used = true
fallback_evidence = 20260601.next_trade_date=20260602
```

## Live Baseline

```text
common_trade_calendar(20260602) = 0
active trade_calendar SSE:20260602 = 0
batch_conflict = 0
quality_conflict = 0
outbox/inbox/checkpoint baseline = 151341/56170/4368
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
condition_* tables
common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

## Execute Command Candidate

```bash
PYTHONPATH=src python3 scripts/run_trade_calendar_patch_once.py \
  --trade-date 20260602 \
  --expected-prev-trade-date 20260601 \
  --fallback-next-trade-date 20260603 \
  --json-report-path docs/N1_trade_calendar_20260602_patch_preflight.json \
  --markdown-report-path docs/N1_TRADE_CALENDAR_20260602_PATCH_PREFLIGHT.md \
  --rollback-sql-path sql/N1_trade_calendar_20260602_patch_rollback.sql \
  --allow-minimal-fallback \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Post-Execute Route

Only do N1 post-review:

```text
1. Confirm common_trade_calendar(20260602) exists and is_open=true.
2. Confirm active source version SSE:20260602 exists.
3. Confirm outbox/inbox/checkpoint unchanged.
4. Do not enter N2 automatically.
```
