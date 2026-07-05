# N3 Intraday B1/C1/B2 Preopen 09:25 Artifact Prewarm Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `N3_market_data`

This gate implemented the 09:25 preopen child-artifact prewarm branch in the auto-poll wrapper. It did not install or modify launchd, did not manually execute wrapper/supervisor/B1/C1/B2, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trading paths.

## Modified Files

- `scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`
- `tests/test_n3_intraday_auto_poll_activation.py`
- `docs/N3_INTRADAY_B1_C1_B2_PREOPEN_0925_ARTIFACT_PREWARM_IMPLEMENTATION.md`
- `docs/N3_INTRADAY_B1_C1_B2_PREOPEN_0925_ARTIFACT_PREWARM_IMPLEMENTATION.json`

## Prewarm Behavior

The wrapper now has a bounded preopen branch:

```text
09:25:00 <= as_of < 09:32:00 Asia/Shanghai
same for_trade_date
supervisor plan status=noop
reason=no_closed_minute_available
```

In that window the wrapper prepares `prepared_hhmm=0931` and generates B1/C1/B2 child artifacts for the expected first closed minute label. It validates generated JSON and rollback SQL, then returns without invoking supervisor or child runners.

Statuses:

- `prewarm_ready`: artifacts written or already identical and validation passed.
- `prewarm_blocked`: artifact generation conflict or validation failure.

The CLI treats `prewarm_ready` as exit code 0. `prewarm_blocked` remains nonzero.

## Boundary Proof

- 09:24 remains `noop/no_closed_minute_available`.
- 09:25-09:31 prewarms `0931` artifacts only.
- 09:32 and later continue through the normal latest-closed-minute execution path.
- Prewarm never writes facts and never allows unclosed-minute B1/C1/B2 execution.
- Conflicting artifacts block before supervisor execution.
- Identical artifacts are idempotent and return `artifact_generation=unchanged`.

## Read-Only Scheduler Observation

The already-enabled launchd scheduler report was inspected read-only after implementation:

```text
source=docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json
manual_wrapper_execute_by_this_gate=false
status=prewarm_ready
reason=preopen_first_closed_minute_artifacts_ready
prepared_hhmm=0931
artifact_generation=unchanged
artifact_validation=passed
executed_child_command_count=0
supervisor_executed=false
b1_c1_b2_executed=false
database_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
```

## Tests

TDD red checks were observed:

- 09:25 prewarm status/idempotency/conflict tests failed against old noop behavior.
- CLI `prewarm_ready` return-code test failed before the success status whitelist update.

Current validation:

```text
targeted_auto_poll_tests=PASS (14 tests)
related_intraday_tests=PASS (15 tests)
combined_intraday_tests=PASS (29 tests)
compileall=PASS
json_parse=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS (tracked scope plus no-index equivalent for new untracked artifacts)
```

## Forbidden Scope Proof

```text
launchd_installed_or_modified=false
manual_wrapper_execute=false
manual_supervisor_execute=false
manual_b1_c1_b2_execute=false
database_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started_by_this_gate=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
old_system_touched=false
```

## Decision

- allow prewarm post-review gate: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_PREOPEN_0925_ARTIFACT_PREWARM_POST_REVIEW_GATE`
