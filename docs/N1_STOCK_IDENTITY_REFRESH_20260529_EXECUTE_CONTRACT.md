# N1 Stock Identity Refresh 20260529 Execute Contract

状态：`DESIGN_PASS`

```text
source_batch_id = stock_identity_refresh_20260529_v1
source_version = stock_identity_20260529_v1
active_scope_key = A_STOCK:20260529
previous_source_version = stock_identity_20260527_v1
runner_readiness = ready_for_final_gate
expected_stock_identity_insert_rows = 1
P0/P1/P2 = 0/0/0
```

本 runner 只允许写 stock_identity、common_ingest_batch、common_quality_gate_result、common_active_source_version。
禁止写 daily fact、condition source、Parquet、outbox/inbox/checkpoint、N2-N6、worker、旧系统或真实交易。
