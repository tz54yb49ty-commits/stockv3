# N1 Official Daily 20260526 Ingestion Execute Contract

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DESIGN_PASS`

## Identity

```text
source_batch_id = official_daily_ingest_20260526_v1
stock source_version = stock_daily_20260526_v1
index source_version = index_daily_20260526_v1
board source_version = board_daily_20260526_v1
```

## Implementation Status

```json
{
  "source_fetch_adapter_routing": true,
  "source_bundle_validation": true,
  "postgres_commit_transaction": true,
  "cli_execute_pipeline_wired": true,
  "execute_authorized": false
}
```

## Execute Command Candidate

```bash
PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_once.py \
  --trade-date 20260526 \
  --execute \
  --user-confirmed \
  --source-fetch-enabled \
  --postgres-commit-enabled
```

This contract is not execute authorization by itself.
