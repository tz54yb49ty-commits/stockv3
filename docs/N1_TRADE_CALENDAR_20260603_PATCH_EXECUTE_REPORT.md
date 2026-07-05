# N1 Trade Calendar 20260603 Patch Execute Report

Result: `EXECUTE_PASS`

Command:

```bash
PYTHONPATH=src python3 scripts/run_trade_calendar_patch_once.py \
  --trade-date 20260603 \
  --expected-prev-trade-date 20260602 \
  --fallback-next-trade-date 20260604 \
  --json-report-path docs/N1_trade_calendar_20260603_patch_preflight.json \
  --markdown-report-path docs/N1_TRADE_CALENDAR_20260603_PATCH_PREFLIGHT.md \
  --rollback-sql-path sql/N1_trade_calendar_20260603_patch_rollback.sql \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

Calendar row:

```text
common_trade_calendar(20260603)=1
is_open=true
prev_trade_date=20260602
next_trade_date=20260604
source=tushare.trade_cal.patch
```

Active source version:

```text
common / trade_calendar / SSE:20260603 -> trade_calendar_20260603_patch_v1
```

Metadata:

```text
common_ingest_batch=1
common_quality_gate_result=11
common_active_source_version=1
persisted quality: P0 passed=11
```

Fix-forward risk:

```text
accepted_by_final_gate=true
N2 refs=1
N3 refs=2
A1 refs=1
```

Boundary proof:

```text
outbox/inbox/checkpoint delta=0/0/0
B1 realtime snapshot refs=0
N4 refs=0
N5 refs=0
worker_started=false
realtime_market_data_pulled=false
delivery/notification/push/voice/mobile/sim/position/real_trade=false
```

Rollback:

```text
rollback_sql=sql/N1_trade_calendar_20260603_patch_rollback.sql
rollback_safe_scope=true
hard_fail_before_delete=true
calendar rollback currently blocked by N2/N3/A1 refs
```

If calendar rollback is required, first rollback A1 previous-day minute preload,
N3 subscription, and N2 condition layer, or open a dedicated rollback plan.

Runtime-control registration is allowed.
