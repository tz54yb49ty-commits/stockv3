# N1 Condition Source 20260601 Activation Final Gate

Result: `PASS`

This is a user-confirmation point. No production write was executed in this gate.

```text
trade_date = 20260601
source_batch_id = condition_source_activation_20260601_v1
stock_daily_basic = stock_daily_basic_20260601_v1
stock_financial = stock_financial_20260601_v1
index_membership = index_membership_20260601_v1
board_membership = board_membership_20260601_v1
```

Expected rows:

```text
stock_daily_basic = 5508
stock_financial = 5508
index_membership = 12841
board_membership = 56960
total = 80817
```

Preflight:

```text
result = PREFLIGHT_PASS
runner_readiness = ready_for_final_gate
P0/P1/P2 = 0/2/1
blockers = []
```

Live baseline:

```text
target fact rows = 0/0/0/0
batch/quality/active conflicts = 0/0/0
outbox/inbox/checkpoint = 151341/56170/4368
```

Allowed write scope after confirmation:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_basic
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
```

Forbidden:

```text
daily bar fact
condition_* tables
Parquet
outbox/inbox/checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

Rollback:

```text
rollback_safe = true
rollback_sql = sql/N1_condition_source_20260601_activation_rollback.sql
```

Execute command:

```bash
set -a
source /Users/chuanfuchen/.secrets/ashare_v3_tushare.env
set +a
PYTHONPATH=src python3 scripts/run_condition_source_activation_20260601_once.py \
  --dsn "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

Post-execute route: N1 post-review only, then rerun `check_condition_source_ready --source-trade-date 20260601` before entering N2.
