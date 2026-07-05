# N1 Official Daily 20260605 Guarded Runner Contract

result: `CONTRACT_PASS`

layer_role: `runtime_control`

## Objective

Define the implementation contract for a guarded 20260605 official daily ingestion runner. This is required before any 20260605 close facts can be written and before the 20260608 N2/N3-A1 chain can continue.

## Current State

Calendar is ready:

```text
20260605 is_open=true, prev=20260604, next=20260608
20260608 is_open=true, prev=20260605, next=20260609
```

Target baseline:

```text
official_daily_ingest_20260605_v1 batch conflicts = 0
condition_source_activation_20260605_v1 batch conflicts = 0
stock_daily_bar_fact(20260605) = 0
index_daily_bar_fact(20260605) = 0
board_daily_bar_fact(20260605) = 0
N2 refs = 0
N3 refs = 0
```

## Why Implementation Is Required

No date-specific 20260605 official daily guarded runner or artifacts exist.

`scripts/run_real_daily_incremental.py` is a direct write runner and does not expose the required final-gate flags:

```text
--execute
--user-confirmed
--source-fetch-enabled
--postgres-commit-enabled
```

Therefore the next step is an N1 implementation gate, not an execute gate.

## Required Implementation

Preferred path: adapt the verified 20260602 guarded pattern.

New or aligned files:

```text
src/ashare_v3/ingestion/official_daily_20260605_execute.py
scripts/run_official_daily_ingestion_20260605_once.py
tests/test_official_daily_ingestion_20260605_execute.py
```

Required artifacts after implementation/preflight:

```text
docs/N1_official_daily_20260605_ingestion_dry_run_report.json
docs/N1_OFFICIAL_DAILY_20260605_INGESTION_DRY_RUN_REPORT.md
docs/N1_official_daily_20260605_ingestion_execute_contract.json
docs/N1_OFFICIAL_DAILY_20260605_INGESTION_EXECUTE_CONTRACT.md
docs/N1_official_daily_20260605_ingestion_execute_preflight.json
docs/N1_OFFICIAL_DAILY_20260605_INGESTION_EXECUTE_PREFLIGHT.md
```

Rollback:

```text
sql/N1_official_daily_20260605_ingestion_rollback.sql
```

## Guard Requirements

Execute must require:

```text
--execute
--user-confirmed
--source-fetch-enabled
--postgres-commit-enabled
```

Missing any required flag must block before DB write. Missing `--source-fetch-enabled` must also block before external source fetch.

Preflight without `--execute` must remain read-only.

## Future Write Scope

Allowed only after implementation pass, final gate pass, `layer_role=N1_ingestion`, and explicit user confirmation:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

Forbidden:

```text
common_trade_calendar
stock_daily_basic
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
worker
realtime/minute market data pull
old system
delivery/push/voice/mobile/sim/position/pnl/real_trade/proposal/order/trade
```

## Acceptance Criteria

- Runner help exposes required execute flags.
- Missing `--execute` blocks before DB write.
- Missing `--user-confirmed` blocks before DB write.
- Missing `--source-fetch-enabled` blocks before external source fetch or DB write.
- Missing `--postgres-commit-enabled` blocks before DB write.
- Preflight-only generates artifacts without DB writes.
- Target batch/source-version conflicts are P0 blockers.
- Existing active 20260605 daily source is a P0 blocker.
- Source probe determines expected 20260605 stock/index/board row counts.
- Rollback hard-fails before DELETE/UPDATE and blocks downstream refs.

## Next Gate

```text
N1_OFFICIAL_DAILY_20260605_GUARDED_RUNNER_IMPLEMENTATION_GATE
```

