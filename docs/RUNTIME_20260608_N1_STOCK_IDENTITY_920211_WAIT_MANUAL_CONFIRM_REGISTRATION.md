# Runtime 20260608 N1 Stock Identity 920211 Wait Manual Confirm Registration

Result: `WAIT_MANUAL_CONFIRM_REGISTERED`

This runtime_control gate only registers the next command and rollback path. It does not execute N1 and does not write the database.

Manual gate:

```text
status = WAIT_MANUAL_CONFIRM
required_layer_role = N1_ingestion
target = 920211.BJ / stock:BJ:920211
source_batch_id = stock_identity_refresh_20260605_920211_v1
source_version = stock_identity_20260605_v1
```

Registered command:

```bash
PYTHONPATH=src python3 scripts/run_stock_identity_refresh_20260605_920211_once.py --trade-date 20260605 --execute --user-confirmed
```

Expected writes after explicit N1 confirmation:

```text
stock_identity = 1
common_ingest_batch = 1
common_quality_gate_result = 8
common_active_source_version = 1
```

Rollback registry:

```text
sql/N1_stock_identity_920211_20260605_refresh_rollback.sql
hard-fail before first DELETE/UPDATE = true
no CASCADE/DROP/TRUNCATE = true
runtime_control executes rollback = false
```

Current live baseline:

```text
stock_identity(920211.BJ) = 0
ingest_batch rows = 0
quality rows = 0
active scope rows = 0
20260605 official daily stock/index/board = 0/0/0
N2 20260605 source runs = 0
```

Forbidden scope held:

```text
runtime_control did not execute N1
runtime_control did not write DB
rollback not executed
official daily not executed
condition source not executed
N2/N3 not executed
outbox/inbox/checkpoint unchanged
worker not started
market data not pulled
old system untouched
real trade false
```

After the N1 identity execute passes, refresh the 20260605 official daily stock probe and preflight, then return to the official daily execute final gate review.

Copy-ready next prompt:

```text
layer_role=N1_ingestion

进入 N1_STOCK_IDENTITY_920211_20260605_REFRESH_EXECUTE_USER_CONFIRMATION_GATE。

目标：
执行 scoped stock_identity refresh，插入 920211.BJ / stock:BJ:920211，使 20260605 official daily stock source probe unmapped 从 1 修正为 0。

依据：
- docs/N1_STOCK_IDENTITY_920211_20260605_REFRESH_EXECUTE_FINAL_GATE_REVIEW.json
- docs/N1_stock_identity_920211_20260605_refresh_execute_contract.json
- docs/N1_stock_identity_920211_20260605_refresh_execute_preflight.json
- sql/N1_stock_identity_920211_20260605_refresh_rollback.sql

允许执行命令：
PYTHONPATH=src python3 scripts/run_stock_identity_refresh_20260605_920211_once.py --trade-date 20260605 --execute --user-confirmed

要求：
- 只写 stock_identity / common_ingest_batch / common_quality_gate_result / common_active_source_version
- 不写 official daily facts
- 不写 condition source
- 不进入 N2/N3/N4/N5/N6
- 不消费/update outbox/inbox/checkpoint
- 不启动 worker
- 不执行 rollback
- 不触碰旧系统
- 不 real trade

输出：
- EXECUTE_PASS / BLOCKED
- execution proof
- row count proof
- rollback proof
- forbidden scope proof
- 是否允许返回 runtime_control 刷新 20260605 official daily stock probe/preflight
```
