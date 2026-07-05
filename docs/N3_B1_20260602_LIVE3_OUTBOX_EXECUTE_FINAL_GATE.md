# N3-B1 20260602 live3 Outbox Execute Final Gate

## Result

```text
status = PASS_WAIT_USER_CONFIRMATION
target_snapshot_run_id = realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_subscription_run_id = market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
expected rows = stock 1976 / index 83 / board 428 / total 2487
expected outbox = MarketSnapshotUpdated 2487
```

This final gate does **not** execute production writes. It prepares the confirmation point.

## Readiness Evidence

```text
BJ fallback readonly probe = PASS
contract P0/P1/P2 = 0/0/0
readiness ready = true
readiness blocked = false
live3 baseline rows/outbox = 0
calendar = 20260602 open, prev=20260601, next=20260603
preload = passed, 969 objects
```

Evidence files:

- `docs/N3_B1_20260602_BJ_INDEX_FALLBACK_READONLY_PROBE.json`
- `docs/N3_B1_realtime_snapshot_20260602_live3_outbox_execute_contract.json`
- `docs/N3_B1_realtime_snapshot_20260602_live3_outbox_execute_readiness.json`

## Required Production Order

1. Roll back failed live2 source first:

```bash
PYTHONPATH=src python3 - <<'ROLLBACK_PY'
from pathlib import Path
import psycopg
DSN='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3'
sql=Path('sql/N3_B1_realtime_snapshot_20260602_live2_outbox_rollback.sql').read_text()
with psycopg.connect(DSN, connect_timeout=10) as conn:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(sql)
ROLLBACK_PY
```

2. Execute live3 after sourcing token without printing it:

```bash
set -a; source /Users/chuanfuchen/.secrets/ashare_v3_tushare.env; set +a
PYTHONPATH=src:scripts python3 scripts/run_realtime_daily_snapshot_once.py \
  --contract-path docs/N3_B1_realtime_snapshot_20260602_live3_outbox_execute_contract.json \
  --readiness-path docs/N3_B1_realtime_snapshot_20260602_live3_outbox_execute_readiness.json \
  --pre-backup-path docs/N3_B1_realtime_snapshot_20260602_live3_outbox_backup_before.json \
  --post-backup-path docs/N3_B1_realtime_snapshot_20260602_live3_outbox_backup_after.json \
  --json-report-path docs/N3_B1_realtime_snapshot_20260602_live3_outbox_execute_report.json \
  --markdown-report-path docs/N3_B1_REALTIME_SNAPSHOT_20260602_LIVE3_OUTBOX_EXECUTE_REPORT.md \
  --for-trade-date 20260602 \
  --snapshot-run-id realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1 \
  --writes-outbox=true \
  --execute \
  --user-confirmed \
  --progress-every 200
```

## Risk

```text
execute_risk = medium
rollback_risk = low if downstream refs remain zero
```

Reason: live3 will really pull market data and write N3 snapshot facts plus N3 outbox. It will not enter N4/N5/N6, start worker, or touch old system/real trading.

## Post Execute Review

```text
live3.status = passed
snapshot rows = 1976 / 83 / 428 / 2487
MarketSnapshotUpdated pending = 2487
N4/N5/N6 refs = 0 before next explicit gate
```
