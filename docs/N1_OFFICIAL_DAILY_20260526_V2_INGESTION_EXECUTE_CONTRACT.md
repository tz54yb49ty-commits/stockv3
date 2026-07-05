# N1 Official Daily 20260526 V2 Ingestion Execute Contract

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DESIGN_PASS`

## Identity

```text
source_batch_id = official_daily_ingest_20260526_v2
stock source_version = stock_daily_20260526_v2
index source_version = index_daily_20260526_v2
board source_version = board_daily_20260526_v2
```

## V2 Expected

```json
{
  "stock_daily_bar_fact": 5520,
  "index_daily_bar_fact": 9,
  "board_daily_bar_fact": 428,
  "total_daily_fact": 5957
}
```

## Implementation Status

```json
{
  "execute_runner_implemented": true,
  "source_fetch_adapter_routing": true,
  "source_bundle_validation": true,
  "postgres_commit_transaction": true,
  "cli_execute_pipeline_wired": true,
  "execute_authorized": false,
  "final_execute_gate_allowed": true
}
```

## Execute Command Candidate

```bash
PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260526_v2_once.py \
  --trade-date 20260526 \
  --execute \
  --user-confirmed \
  --source-fetch-enabled \
  --postgres-commit-enabled
```

This contract is not execute authorization by itself.
