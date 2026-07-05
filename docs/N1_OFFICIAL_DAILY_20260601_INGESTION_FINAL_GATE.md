# N1 Official Daily 20260601 Ingestion Final Gate

layer_role: `N1_ingestion`

Result: `PASS`

This is a read-only final gate. It does not authorize execution by itself.

```text
trade_date = 20260601
source_batch_id = official_daily_ingest_20260601_v1
stock source_version = stock_daily_20260601_v1
index source_version = index_daily_20260601_v1
board source_version = board_daily_20260601_v1
preflight = PREFLIGHT_PASS
runner_readiness = ready_for_final_gate
P0/P1/P2 = 0/0/0
execute_authorized = false
execute_allowed_after_user_confirmation = true
```

## Source Readiness

```text
stock = STOCK_PROBE_PASS
tushare_daily_count = 5508
adj_factor_count = 5525
matched_identity_count = 5508
unmapped_count = 0
official_no_trade_manifest_count = 17

index = FULL_PROBE_PASS
index source_count = 83
index missing_count = 0

board = FULL_PROBE_PASS
board source_count = 428
board missing_count = 0
```

## Live Baseline

```text
stock_daily_bar_fact(20260601) = 0
index_daily_bar_fact(20260601) = 0
board_daily_bar_fact(20260601) = 0
batch_conflict = 0
quality_conflict = 0
active_daily_source_version_conflict = 0
outbox/inbox/checkpoint = 151341/56170/4368
```

Expected rows after execute:

```text
stock_daily_bar_fact = 5508
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total_daily_fact = 6019
```

## Scope

Allowed write scope after explicit confirmation:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

Forbidden:

```text
Parquet
condition source
condition_* tables
common_event_outbox / common_event_inbox / common_event_consumer_checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

Rollback:

```text
rollback_sql = sql/N1_official_daily_20260601_ingestion_rollback.sql
rollback_safe_before_execute = true
rollback_risk = low
```

## A1 Context

```text
N2 active = condition_layer_20260529_source_20260529_v6 / passed_active
N3 subscription = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6 / passed
N3 subscription rows = 3319
N3 previous-day preload = previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6 / passed
N3 previous-day preload rows stock/index/board = 366/21/86
```

## Execute Prompt

```bash
source /Users/chuanfuchen/.secrets/ashare_v3_tushare.env

PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260601_once.py \
  --dsn "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" \
  --trade-date 20260601 \
  --execute \
  --user-confirmed \
  --source-fetch-enabled \
  --postgres-commit-enabled
```

After execute, do N1 post-review only. Do not automatically enter N2/N3.
