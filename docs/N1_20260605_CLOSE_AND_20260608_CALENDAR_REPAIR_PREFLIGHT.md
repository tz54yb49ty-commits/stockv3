# N1 20260605 Close And 20260608 Calendar Repair Preflight

result: `PREFLIGHT_PASS_FOR_CONTRACT_ONLY`

This preflight only covers artifact readiness and live-readiness review. It does not authorize or execute N1 writes.

Checks:

```text
target_batch_ids_absent=true
target_downstream_refs_zero=true
rollback_sql_paths_generated=true
runtime_control_execute_forbidden=true
n2_n3_blocked_until_n1_post_review=true
```

Rollback SQL paths:

```text
sql/N1_trade_calendar_20260608_patch_rollback.sql
sql/N1_official_daily_20260605_ingestion_rollback.sql
sql/N1_condition_source_20260605_activation_rollback.sql
```

P0/P1/P2:

```text
0/2/1
```

Next gate:

```text
N1_20260605_CLOSE_AND_20260608_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW
```

