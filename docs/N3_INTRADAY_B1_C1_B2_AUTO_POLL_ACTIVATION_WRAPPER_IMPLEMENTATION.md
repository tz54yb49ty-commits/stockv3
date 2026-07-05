# N3 Intraday B1/C1/B2 Auto-Poll Activation Wrapper Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `N3_market_data`

This gate implemented the run-once auto-poll wrapper and tests. It did not install or enable cron/launchd, did not execute the real supervisor command path in validation, did not execute real B1/C1/B2 runners, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trading paths.

## Modified Files

- `scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`
- `tests/test_n3_intraday_auto_poll_activation.py`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_WRAPPER_IMPLEMENTATION.md`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_WRAPPER_IMPLEMENTATION.json`

## Wrapper Behavior

- Default mode is `PLAN_ONLY`.
- Execute requires both `--execute` and `--user-confirmed`.
- Missing either confirmation blocks before child artifact generation or supervisor execution.
- No closed minute returns `NOOP`.
- Current date mismatch returns `BLOCKED`.
- Existing passed B2 watermark returns `NOOP` before artifact generation.
- Execute mode generates and validates child artifacts before invoking the supervisor bounded pass.
- Artifact conflicts block before supervisor execution.
- Supervisor child commands remain argv lists and retain `--execute --user-confirmed`.
- No new state table is introduced.

## Guard Proof

- default plan-only does not execute supervisor
- default plan-only does not write child artifacts
- missing `--execute` or `--user-confirmed` blocks early
- child artifact conflict blocks early
- supervisor child failure blocks wrapper
- no shell string command composition

## Validation

```text
RED observed:
  ModuleNotFoundError for scripts.run_n3_intraday_b1_c1_b2_auto_poll_once

targeted tests:
  PYTHONPATH=src:scripts python3 -m unittest tests.test_n3_intraday_auto_poll_activation tests.test_n3_intraday_child_artifacts tests.test_n3_intraday_supervisor
  25 tests OK

compileall:
  PASS

implementation JSON parse:
  PASS

forbidden scope scan:
  PASS

git diff --check:
  PASS
```

## Forbidden Scope Proof

```text
cron_launchd_installed_or_enabled=false
supervisor_execute_invoked_by_validation=false
real_b1_c1_b2_execute_invoked=false
database_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
rollback_sql_executed=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
old_system_touched=false
```

## Decision

- allow wrapper post-review gate: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_WRAPPER_POST_REVIEW_GATE`
