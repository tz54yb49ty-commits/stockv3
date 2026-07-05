# N3 Intraday B1/C1/B2 Dynamic Child Artifact Generation Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `N3_market_data`

This gate changed only the approved implementation, tests, and implementation report artifacts. It did not execute the supervisor, did not execute B1/C1/B2, did not write database rows, did not install cron/launchd, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system, delivery, mobile, voice, sim, position, PnL, proposal, order, or real-trade paths.

## Modified Files

- `src/ashare_v3/market/intraday_child_artifacts.py`
- `scripts/run_n3_intraday_child_artifacts_once.py`
- `tests/test_n3_intraday_child_artifacts.py`
- `src/ashare_v3/market/intraday_supervisor.py`
- `tests/test_n3_intraday_supervisor.py`
- `docs/N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_IMPLEMENTATION.md`
- `docs/N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_IMPLEMENTATION.json`

## Generator Behavior

- Default CLI mode is plan-only.
- Artifact writes require explicit `--write-artifacts`.
- Replacing conflicting artifacts requires explicit `--allow-overwrite`.
- The generator builds stable paths from `for_trade_date + latest_closed_minute_hhmm`.
- Existing identical artifacts are treated as unchanged.
- Existing conflicting artifacts block before any artifact write.
- The module does not import DB or subprocess APIs and does not execute child runners.

## Generated Artifact Schema

B1:

- `execute_contract_json`
- `execute_contract_md`
- `execute_readiness_json`
- `execute_readiness_md`
- `rollback_sql`

C1:

- `c0_dry_run_json`
- `c0_dry_run_md`
- `rollback_sql`

B2:

- `dry_run_json`
- `dry_run_md`
- `execute_contract_json`
- `execute_contract_md`
- `execute_preflight_json`
- `execute_preflight_md`
- `rollback_sql`

## B1 Rollback Wiring Proof

`IntradaySupervisorPaths` now includes `b1_rollback_sql_path`, and the B1 child step metadata exposes that path. The B1 child command still does not pass `--rollback-sql-path`, because `scripts/run_realtime_daily_snapshot_once.py` does not support that argument. The rollback path is now available for review, report, and registry wiring without breaking runner compatibility.

## Rollback Static Safety

Generated B1/C1/B2 rollback SQL drafts:

- hard-fail before first executable `DELETE`
- contain no `DROP`, `TRUNCATE`, or `CASCADE`
- guard event infra refs
- guard N3-B/C/B2 downstream refs
- guard N4/N5/N6 refs
- guard `downstream_layers_touched` and `worker_started`
- do not touch N2 facts

## Validation

```text
RED observed:
  missing intraday_child_artifacts module
  B1 child rollback_sql_path was empty

targeted tests:
  PYTHONPATH=src:scripts python3 -m unittest tests.test_n3_intraday_child_artifacts tests.test_n3_intraday_supervisor
  15 tests OK

compileall:
  PASS

sample generated artifact JSON parse:
  PASS

sample generated rollback static check:
  PASS

forbidden scope scan:
  PASS

git diff --check:
  PASS
```

## Decision

- allow post-review gate: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_POST_REVIEW_GATE`
