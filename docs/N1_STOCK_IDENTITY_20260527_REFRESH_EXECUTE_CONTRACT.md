# N1 Stock Identity 20260527 Refresh Execute Contract

状态：`DESIGN_PASS`

```text
source_batch_id = stock_identity_refresh_20260527_v1
source_version = stock_identity_20260527_v1
active_scope_key = A_STOCK:20260527
runner_readiness = ready_for_final_gate
expected_stock_identity_insert_rows = 2
P0/P1/P2 = 0/1/0
```

本 runner 只允许写 stock_identity、common_ingest_batch、common_quality_gate_result、common_active_source_version。
stale identity stock:SZ:300114 仅记录 manifest，本 gate 不修改。
