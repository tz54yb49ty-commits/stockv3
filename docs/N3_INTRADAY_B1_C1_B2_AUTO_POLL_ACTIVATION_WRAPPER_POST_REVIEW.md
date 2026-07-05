# N3 Intraday B1/C1/B2 Auto-Poll Activation Wrapper Post-Review

Result: `POST_REVIEW_PASS`

Layer role: `N3_market_data`

This gate reviewed the auto-poll run-once wrapper against the command composition contract. It did not install or enable cron/launchd, did not execute wrapper `--execute`, did not execute supervisor `--execute`, did not execute B1/C1/B2, did not write database rows, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trading paths.

## Reviewed Artifacts

- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_COMMAND_COMPOSITION.json`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_COMMAND_COMPOSITION_PREFLIGHT.json`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_WRAPPER_IMPLEMENTATION.json`
- `scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`
- `tests/test_n3_intraday_auto_poll_activation.py`
- `src/ashare_v3/market/intraday_supervisor.py`
- `src/ashare_v3/market/intraday_child_artifacts.py`

## Wrapper Behavior Proof

- Default mode is `PLAN_ONLY`; plan-only does not write child artifacts or execute supervisor/B1/C1/B2.
- Missing `--execute` or missing `--user-confirmed` blocks with `auto_poll_execute_requires_user_confirmed` before child artifact generation or supervisor execution.
- The wrapper first builds the supervisor plan, which calculates the latest closed minute and applies date/no-closed-minute/watermark no-op policy.
- Current date mismatch blocks with `current_date_mismatch`.
- No closed minute returns `NOOP` with `no_closed_minute_available`.
- Passed deterministic B2 watermark returns `NOOP` with `latest_closed_minute_already_processed` before child artifact generation.

## Artifact-Before-Supervisor Proof

The execute path is ordered as:

1. `write_intraday_child_artifacts`
2. `validate_generated_child_artifacts`
3. `run_intraday_supervisor_plan`

Generated artifacts are JSON-parsed before supervisor execution. B1/C1/B2 rollback SQL is statically checked for `RAISE EXCEPTION` before `DELETE`, no `DROP/TRUNCATE/CASCADE`, and required event/downstream guard markers.

## Command Proof

Supervisor child commands are `list[str]` argv values. `validate_child_command` rejects non-list commands and rejects child commands missing `--execute --user-confirmed`.

B1 rollback SQL is present in child step metadata as `rollback_sql_path`; it is not passed to the B1 runner as an unsupported command argument.

## Failure Policy

- Existing conflicting child artifacts block before supervisor execution.
- Child command failure blocks the wrapper with `child_step_failed` and stops the current pass.

## Validation

```text
targeted_tests=PASS (25 tests)
compileall=PASS
json_parse=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS
```

## Forbidden Scope Proof

```text
cron_launchd_installed_or_enabled=false
supervisor_execute_invoked=false
b1_c1_b2_execute_invoked=false
database_written=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
old_system_touched=false
```

## Decision

- allow return to final gate review: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_FINAL_GATE_REVIEW`
