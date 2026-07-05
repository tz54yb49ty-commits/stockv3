# N1 Official Daily 20260529 Ingestion Execute Contract

layer_role: `N1_ingestion`
状态: `DESIGN_PASS`

```text
source_batch_id = official_daily_ingest_20260529_v1
stock source_version = stock_daily_20260529_v1
index source_version = index_daily_20260529_v1
board source_version = board_daily_20260529_v1
expected_rows = {'stock_daily_bar_fact': 5506, 'index_daily_bar_fact': 83, 'board_daily_bar_fact': 428, 'total_daily_fact': 6017}
runner_readiness = ready_for_final_gate
```

```bash
PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260529_once.py \
  --trade-date 20260529 \
  --execute \
  --user-confirmed \
  --source-fetch-enabled \
  --postgres-commit-enabled
```

This contract is not execute authorization by itself.
