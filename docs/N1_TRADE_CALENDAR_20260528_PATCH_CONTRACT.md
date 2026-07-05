# N1 Trade Calendar 20260528 Patch Contract

Date: 2026-05-28
layer_role: `N1_ingestion`
Status: `DESIGN_PASS`

## Purpose

Patch `common_trade_calendar` for `20260528` and activate the `SSE:20260528`
`trade_calendar` source version to unblock the 20260528 N3 subscription
calendar readiness check.

The default runner mode is preflight only: read-only PostgreSQL checks, Tushare
`trade_cal` lookup, and preflight artifact generation. Database writes require
the explicit execute flags.

## Identity

```text
source_batch_id = trade_calendar_20260528_patch_v1
source_version  = trade_calendar_20260528_patch_v1
scope_key       = SSE:20260528
```

## Source Policy

Preferred source:

```text
Tushare trade_cal
exchange = SSE
trade_date = 20260528
```

Fallback is allowed only with explicit `--allow-minimal-fallback`:

```text
Use common_trade_calendar 20260527.next_trade_date=20260528
source = manual.calendar_patch
quality gate writes P2 warning: manual_calendar_patch_used
```

## Future Write Scope

Future execute may write only these tables in one transaction:

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

Forbidden:

```text
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
stock_daily_basic
stock_financial_metrics_fact
condition source
Parquet
common_event_outbox
common_event_inbox
checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

## Execute Flags

Future execute must include all flags:

```text
--execute
--user-confirmed
--postgres-commit-enabled
```

Command:

```bash
PYTHONPATH=src python3 scripts/run_trade_calendar_patch_20260528_once.py \
  --trade-date 20260528 \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Quality Gate

P0 gates:

```text
target_calendar_missing_before_patch
active_trade_calendar_missing_before_patch
patch_batch_absent
patch_active_conflict_absent
patch_quality_conflict_absent
previous_calendar_next_trade_date
tushare_trade_cal_available
calendar_target_open
calendar_prev_trade_date
calendar_next_trade_date_present
calendar_patch_scope_limited
```

Fallback gate:

```text
manual_calendar_patch_used = P2 warning
```

## Rollback

Rollback SQL:

```text
sql/N1_trade_calendar_20260528_patch_rollback.sql
```

Rollback only clears this calendar patch by
`source_batch_id/source_version/trade_date=20260528/scope_key=SSE:20260528`
and deletes or restores the `SSE:20260528` active source version. It does not
touch 20260527 calendar, daily fact, condition source, Parquet, outbox, or
N2/N3/N4/N5/N6 artifacts.
