# N5 Rollback Before N4 Formal Transition Gate Repair Rerun Execute Report

- Result: BLOCKED
- rollback_sql_path: `sql/N5_action_after_n4_y_amount_semantic_repair_rerun_rollback.sql`
- psql_exit_code: `3`
- blocked_error: `N5 rollback blocked: non-scoped consumer checkpoint refs exist for source_trigger_run_id (5331)`
- DELETE executed: `false`
- COMMIT executed: `false`

No N4 rollback/rerun, no N6, no N5 outbox consumption, no N4 outbox status update, no scheduler/worker, no voice/mobile/sim/position/order/real trade/old system.
