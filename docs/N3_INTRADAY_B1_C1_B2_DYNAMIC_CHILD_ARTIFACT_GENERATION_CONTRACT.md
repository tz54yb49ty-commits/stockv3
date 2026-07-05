# N3 Intraday B1/C1/B2 Dynamic Child Artifact Generation Contract

Result: `CONTRACT_PASS`

Layer role: `N3_market_data`

This gate only designs the per-minute child artifact generator contract. It did not change code, execute the supervisor, execute B1/C1/B2, install cron/launchd, write database rows, consume or update outbox/inbox/checkpoint, enter N4/N5/N6, start a worker, touch delivery/mobile/voice/sim/trade paths, or touch the old system.

## Purpose

The bounded intraday supervisor can already derive deterministic B1/C1/B2 child commands for the latest closed minute. Live activation is still blocked because the child command inputs are missing for each minute and B1 rollback SQL is not represented in the B1 child step metadata.

This contract defines a dynamic, per-minute artifact generator. For each `for_trade_date + HHMM`, it must generate the B1/C1/B2 dry-run, contract, preflight/readiness, rollback, and report path artifacts required before a future supervisor execute pass may invoke child runners.

## Inputs

- `for_trade_date`
- `latest_closed_minute`
- `latest_closed_minute_hhmm`
- `subscription_run_id`
- `preload_run_id`
- `source_condition_run_id`
- `docs_root`
- `sql_root`

The generator must verify that the requested minute is closed, the current local date matches the trade date before live activation, and both the N3 subscription and A1 preload lineage are passed.

## Output Artifacts

### B1

- `docs/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_execute_contract.json`
- `docs/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_execute_contract.md`
- `docs/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_execute_readiness.json`
- `docs/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_execute_readiness.md`
- `sql/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_rollback.sql`

### C1

- `docs/N3_C0_today_minute_bar_1m_<for_trade_date>_until_<HHMM>_dry_run.json`
- `docs/N3_C0_today_minute_bar_1m_<for_trade_date>_until_<HHMM>_dry_run.md`
- `sql/N3_C1_today_minute_bar_1m_<for_trade_date>_until_<HHMM>_rollback.sql`

The current C1 runner carries execute contract and preflight readiness through the C0 plan artifact unless the runner contract shape changes.

### B2

- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_dry_run.json`
- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_dry_run.md`
- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_execute_contract.json`
- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_execute_contract.md`
- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_execute_preflight.json`
- `docs/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_execute_preflight.md`
- `sql/N3_B2_realtime_projection_<for_trade_date>_until_<HHMM>_rollback.sql`

## Boundary

Allowed:

- read source lineage and existing N3 artifacts
- generate dry-run, contract, preflight/readiness, rollback draft, and report path artifacts
- static-check rollback SQL
- static-check child command argv

Forbidden:

- execute supervisor
- execute B1/C1/B2
- write database rows
- install or enable cron/launchd
- consume or update outbox/inbox/checkpoint
- enter N4/N5/N6
- start worker
- delivery/push/voice/mobile
- proposal/order/trade/sim/position/PnL/real trade
- touch old system

## Idempotency

The deterministic artifact key is `for_trade_date + latest_closed_minute_hhmm`. Re-running the generator for the same key must produce identical paths and semantically equivalent content. Existing matching artifacts may be refreshed only when the generator can prove the same contract identity. Conflicting existing artifacts must block before any artifact write. Passed run watermarking remains the supervisor's responsibility through `common_market_data_run`; the generator must not introduce a new state table.

## B1 Rollback Wiring Decision

B1 rollback SQL is mandatory even though the current B1 runner does not accept a `--rollback-sql-path` argument. The next implementation gate must add B1 rollback path metadata to the supervisor child step and generate `sql/N3_B1_realtime_snapshot_<for_trade_date>_until_<HHMM>_rollback.sql`. The child command may remain runner-compatible, but the supervisor report must expose the rollback path for final gate review and rollback registry.

The B1 rollback SQL must hard-fail before the first executable `DELETE`, guard event infra, N3-B/C/B2, N4/N5/N6, `downstream_layers_touched`, and `worker_started`, and delete only scoped B1 snapshot, quality, and run rows.

## Next Implementation Scope

- `src/ashare_v3/market/intraday_child_artifacts.py`
- `scripts/run_n3_intraday_child_artifacts_once.py`
- `tests/test_n3_intraday_child_artifacts.py`
- `src/ashare_v3/market/intraday_supervisor.py`
- `tests/test_n3_intraday_supervisor.py`

## Decision

- allow auto-poll activation final gate now: `False`
- allow dynamic child artifact implementation gate: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_IMPLEMENTATION_GATE`

## Validation

```text
JSON parse=PASS
contract/preflight consistency=PASS
forbidden scope scan=PASS
git diff --check=PASS
```
