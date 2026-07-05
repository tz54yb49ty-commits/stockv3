# V3 Phase 1 N3 Bounded Worker Entry Contract

Scope: `scripts/run_n3_bounded_worker_once.py` implements one N3 Phase 1 bounded wrapper invocation for the existing B1/C1/B2 path.

This document is a PR-2 contract. It does not authorize DB execution, migration, rollback execution, scheduler activation, N4/N5/N6 consumption, voice, mobile, sim, or trade execution by itself.

## 1. Runtime Assumption

Phase 1 is single-host and assumes all future N3/N4/N5 bounded wrappers share the same visible filesystem.

The wrapper uses the PR-1.1 common lock path builder:

```text
build_phase1_realtime_chain_lock_path(repo_root, trade_date)
=> <repo_root>/tmp/v3_phase1_realtime_chain_<trade_date>.lock
```

The path intentionally contains no `n3`, `n4`, or `n5` layer name. Old entrypoints, manual SQL, launchd jobs, and ad hoc shell commands can bypass this protocol; runbooks must forbid running them in parallel with this wrapper.

## 2. CLI Contract

Allowed arguments:

```text
--for-trade-date
--source-condition-run-id
--source-subscription-run-id
--previous-day-preload-run-id
--dsn
--status-json
--rollback-manifest-json
--stop-file
--max-runtime-seconds
--python-executable
--docs-root
--sql-root
--execute
--user-confirmed
--json
```

Forbidden arguments:

```text
--max-cycles
--max-events
--batch-size
--auto-resolve-lineage
--passed-run-id
--skip-db-watermark
```

Lineage IDs must be explicit. `latest`, `active`, `fallback`, `auto`, `auto-resolve`, and equivalent implicit selectors are rejected before child execution.

Default mode is plan-only. Only `--execute` together with `--user-confirmed` may start B1/C1/B2 children.

Each invocation processes at most one N3 plan:

```text
processed_count_unit = n3_plan
stage_count_total = 3
completed_stage_count = 0..3
```

## 3. Child Boundary

The wrapper must not call `run_auto_poll_once()` as an opaque child.

Required call boundary:

```text
build_intraday_supervisor_plan(...)
-> plan["child_steps"]
-> validate_child_command(command)
-> per-stage stop/deadline check
-> run_child_with_timeout(command, remaining_total_deadline)
```

The wrapper reuses existing child artifact generation and existing supervisor command validation. It does not duplicate or weaken forbidden command marker checks.

Stage order is fixed:

```text
B1 -> C1 -> B2
```

## 4. Stop, Deadline, Timeout

The wrapper checks `check_stop_file()` before every stage.

The wrapper checks `remaining_deadline_seconds()` before every stage. Child timeout uses the remaining total deadline; it does not reset a fresh timeout per child.

Timeout handling is fail-closed:

```text
UNKNOWN_AFTER_TIMEOUT
exit_code = 3
requires_post_check = true
no automatic retry
no automatic rollback
```

## 5. Result State Machine

| Condition | Result | Exit | Post-check |
|---|---:|---:|---:|
| plan-only | `NOOP` | 0 | false |
| singleton lock held | `NOOP` | 0 | false |
| stop file before B1 | `NOOP` | 0 | false |
| lineage/preflight failure before child | `BLOCKED` | 2 | false |
| deadline exhausted before B1 | `BLOCKED` | 2 | false |
| stop/deadline after completed stage | `PARTIAL` | 2 | false |
| previous stage committed and next child controlled-blocked with no current commit | `PARTIAL` | 2 | false |
| child timeout | `UNKNOWN_AFTER_TIMEOUT` | 3 | true |
| child technical failure and read-only post-check confirms no current commit | `CRASHED` | 1 | false |
| commit/report/connection evidence unresolved | `COMMIT_UNKNOWN` | 3 | true |
| B1/C1/B2 all pass with valid reports and rollback SQL | `PASS` | 0 | false |

`PARTIAL` must include:

```text
completed_stages
pending_stages
partial_reason
output_run_ids
rollback_artifacts
downstream_consumption_allowed=false
n4_consumption_allowed=false
```

`PARTIAL` must not be handed to N4.

## 6. Output Run IDs

The wrapper records:

```text
snapshot_run_id
today_minute_run_id
projection_run_id
source_metric_run_id
```

`source_metric_run_id` is only a cross-layer status/manifest alias:

```text
source_metric_run_id = projection_run_id
```

The B2 database schema and B2 internal code continue to use `projection_run_id`. No migration is introduced.

## 7. Child Report And Rollback Artifact Validation

For a stage to count as completed, all checks must pass:

```text
expected run_id matches plan
child report path exists
child report is valid JSON
child report run_id equals expected run_id
rollback SQL exists
artifact SHA-256 is computed
```

If a completed stage lacks rollback SQL, the wrapper fails closed with:

```text
result = CRASHED
stop_reason = artifact_contract_corruption_<stage>
```

It must not report `PASS` or controlled `PARTIAL`.

## 8. Read-Only Post-Check Contract

Post-check is read-only and must not retry, rollback, or write.

Stage evidence:

| Stage | Run ID | Run table | Fact evidence |
|---|---|---|---|
| B1 | `snapshot_run_id` | `common_market_data_run` | `stock/index/board_realtime_daily_snapshot` by `run_id` |
| C1 | `today_minute_run_id` | `common_market_data_run` | `stock/index/board_minute_bar_1m` by `run_id` |
| B2 | `projection_run_id` | `common_market_data_run` | `stock/index/board_realtime_projection_metric` by `projection_run_id` |

Classification:

```text
committed = run/fact/quality evidence is consistent and no downstream refs exist
rolled_back = run/fact/quality evidence absent and no downstream refs exist
unresolved = running, mixed evidence, field mismatch, or downstream refs
```

Only `rolled_back` permits a human to re-run the same stage manually.

## 9. Rollback Manifest

The wrapper writes `--rollback-manifest-json` with PR-1 `atomic_write_json()`.

Required fields:

```text
invocation_id
wrapper_run_id
trade_date
result
requires_post_check
completed_stages
pending_stages
stage_run_ids
output_run_ids
stage_reports
stage_rollback_sql
artifact_exists
artifact_hash
downstream_consumption_allowed
n4_consumption_allowed
partial_reason
input_lineage_ids
```

Only completed and validated stage artifacts are marked usable in `stage_reports` and `stage_rollback_sql`.

## 10. Forbidden Scope

The wrapper must not:

```text
start long-running workers
install or enable schedulers
consume or update outbox/inbox/checkpoints
enter N4/N5/N6
write trigger/action/user facts
write voice/mobile/sim/trade/position/order paths
execute rollback SQL
run migration SQL
call real trading APIs
```

B1 and C1 child scripts may call market data providers only when this wrapper is explicitly run with `--execute --user-confirmed`. Tests must use fake children and fake post-checks.

## 11. Test Contract

Tests use stdlib `unittest` only. No `pytest` dependency is added.

Required verification:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python3 -m unittest \
  tests.test_bounded_worker_control \
  tests.test_n3_bounded_worker_once

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts python3 -m unittest \
  tests.test_n3_intraday_supervisor

python3 -m compileall \
  scripts/run_n3_bounded_worker_once.py \
  tests/test_n3_bounded_worker_once.py

git diff --check
git status --short --untracked-files=all
```
