# N1 Condition Source 20260602 Activation Execute Report

Result: `EXECUTE_PASS`

Command:

```bash
PYTHONPATH=src python3 scripts/run_condition_source_activation_20260602_once.py \
  --trade-date 20260602 \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

Rows written:

```text
stock_daily_basic=5507
stock_financial_metrics_fact=5507
index_membership_fact=12841
board_membership_fact=56960
total=80815
```

Metadata:

```text
common_ingest_batch=1
common_quality_gate_result=15
common_active_source_version=4
```

Quality:

```text
P0/P1/P2=0/2/1
persisted: P0 passed=12, P1 warning=2, P2 warning=1
```

Boundary proof:

```text
outbox/inbox/checkpoint delta=0/0/0
official daily rows remain stock/index/board=5507/83/428
N2/N3/N4/N5/N6 refs=0/0/0/0/0
worker_started=false
Parquet written=false
old system touched=false
delivery/notification/real trading=false
```

Rollback:

```text
rollback_safe=true
rollback_sql=sql/N1_condition_source_20260602_activation_rollback.sql
hard_fail_before_delete=true
```

Next gate: N1 condition source 20260602 post-review.
