# N4 Worker Bounded Polling Run-Once Wrapper Implementation Report

Result: `IMPLEMENTATION_PASS`

Layer role: `N4_trigger`

## Summary

Implemented `scripts/run_n4_worker_bounded_poll_once.py` as a bounded polling run-once wrapper.

The wrapper defaults to `PLAN_ONLY`. Execute mode requires both `--execute` and `--user-confirmed`; missing either flag blocks before invoking the child runner.

## Behavior

- Derives a dynamic `smoke_run_id` per pass.
- Derives per-pass status, JSON report, Markdown report, rollback SQL, and stop-file paths.
- Invokes `scripts/run_n4_worker_bounded_smoke_once.py` using an argv list only.
- Passes `--execute --user-confirmed` to the child runner only after wrapper confirmation passes.
- Exits after one bounded pass.

Dynamic artifact policy:

- `smoke_run_id=n4_worker_bounded_poll_<for_trade_date>_<YYYYMMDDTHHMMSS+0800>`
- `status_json=docs/N4_WORKER_BOUNDED_POLLING_<for_trade_date>_<HHMMSS>_STATUS.json`
- `json_report=docs/N4_WORKER_BOUNDED_POLLING_<for_trade_date>_<HHMMSS>_EXECUTE_REPORT.json`
- `markdown_report=docs/N4_WORKER_BOUNDED_POLLING_<for_trade_date>_<HHMMSS>_EXECUTE_REPORT.md`
- `rollback_sql=sql/N4_worker_bounded_polling_<for_trade_date>_<HHMMSS>_rollback.sql`

## Guard Proof

- Plan-only mode does not invoke the child runner.
- Missing `--execute` blocks before child invocation.
- Missing `--user-confirmed` blocks before child invocation.
- Execute mode invokes the child runner exactly once through an argv list.
- No scheduler install/enable logic exists in the wrapper.
- No long-running worker loop exists in the wrapper.

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_poll_once` -> PASS.
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_poll_once tests.test_n4_worker_bounded_smoke tests.test_n4_worker_state_transition` -> PASS, 42 tests OK.
- `python3 -m compileall scripts/run_n4_worker_bounded_poll_once.py tests/test_n4_worker_bounded_poll_once.py` -> PASS.
- `PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_poll_once.py --help` -> PASS.
- `PYTHONPATH=src python3 scripts/check_n4_contract.py` -> PASS.
- `git diff --check` -> PASS.

## Forbidden Scope Proof

This gate did not execute N4, did not write the database, did not consume/update N3 outbox/inbox/checkpoint, did not install or enable scheduler, did not start a worker, did not enter N5/N6, and did not touch delivery, push, voice, mobile, sim, position, order, trade, real trade, or the old system.

Next gate: `N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_IMPLEMENTATION_POST_REVIEW_GATE`.
