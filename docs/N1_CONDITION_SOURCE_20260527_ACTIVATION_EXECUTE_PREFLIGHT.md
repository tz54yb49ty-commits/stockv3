# N1 Condition Source 20260527 Activation Preflight

Result: `PREFLIGHT_BLOCKED`

- runner_readiness: `blocked`
- execute_runner_implemented: `True`
- postgres_commit_implemented: `True`
- execute_authorized: `False`
- final_execute_gate_allowed: `False`
- P0/P1/P2: `4/3/1`

Expected rows:

```json
{
  "stock_daily_basic": 5506,
  "stock_financial": 5506,
  "index_membership": 12841,
  "board_membership": 56958,
  "total": 80811
}
```

Rollback SQL: `sql/N1_condition_source_20260527_activation_rollback.sql`
