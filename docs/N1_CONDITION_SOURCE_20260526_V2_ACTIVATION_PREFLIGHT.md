# N1 Condition Source 20260526 V2 Activation Preflight

Result: `PREFLIGHT_PASS`

- runner_readiness: `ready_for_final_gate`
- execute_runner_implemented: `True`
- postgres_commit_implemented: `True`
- execute_authorized: `False`
- final_execute_gate_allowed: `True`
- P0/P1/P2: `0/1/1`

Expected rows:

```json
{
  "stock_daily_basic": 5504,
  "stock_financial": 5504,
  "index_membership": 12841,
  "board_membership": 56872,
  "total": 80721
}
```

Condition source gap manifest rows: `16`

Rollback SQL: `sql/N1_condition_source_20260526_v2_activation_rollback.sql`
