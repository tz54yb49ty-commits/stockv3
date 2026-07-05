# Runtime Control N1 to N3-A1 Fast Lane Real Execute Orchestration Alignment

Gate: `RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_EXECUTE_ORCHESTRATION_ALIGNMENT_GATE`

Result: `ALIGNMENT_PASS`

Layer role: `runtime_control`

For trade date: `20260609`

Source trade date derivation: `common_trade_calendar(20260609).prev_trade_date`

Derived source trade date: `20260608`

This gate is a read-only alignment review and contract decision. It does not modify code, write the database, execute N1/N2/N3 commands, execute rollback SQL, consume or update outbox/inbox/checkpoint, start workers, enter N3-B/N3-C/N4/N5/N6, pull realtime market data, generate proposal/order/trade, update sim/position/PnL, submit real trade, or touch the old system.

## Current Blocker Proof

### Calendar Proof

Fresh read-only DB proof was collected from `ashare_v3 / ashare_v3_user / 127.0.0.1:5432` with `transaction_read_only=on` at `2026-06-09 08:26:42.585369+08:00`.

`common_trade_calendar` proof:

```text
20260608: is_open=true, prev_trade_date=20260605, next_trade_date=20260609, source_version=trade_calendar_20260608_patch_v1
20260609: is_open=true, prev_trade_date=20260608, next_trade_date=20260610, source_version=trade_calendar_20260609_repair_v1
```

Calendar proof is `PASS`. The pilot source date is DB-derived as `20260608`; it is not hard-coded.

### N1 Source Facts Missing

Fresh read-only source-fact counts for `20260608`:

```text
stock_daily_bar_fact=0
index_daily_bar_fact=0
board_daily_bar_fact=0
stock_daily_basic=0
stock_financial_metrics_fact=0
```

Downstream lineage is also absent:

```text
common_condition_run for source_trade_date=20260608 or for_trade_date=20260609 = 0
common_market_data_run for source_trade_date=20260608 or for_trade_date=20260609 = 0
```

This remains a P0 blocker for any real N2/N3-A1 pilot execute.

### Fast Lane Wrapper Capability

The three current Fast Lane wrapper scripts are validation/report wrappers only:

```text
scripts/run_n1_fastlane_bundle_once.py -> main_for_bundle("n1")
scripts/run_n2_fastlane_bundle_once.py -> main_for_bundle("n2")
scripts/run_n3_a1_fastlane_bundle_once.py -> main_for_bundle("n3_a1")
```

`src/ashare_v3/runtime/fastlane_contract.py` explicitly defines the wrappers as pure schema and validation orchestration. `main_for_bundle` accepts `--child-step-json`, validates step dictionaries, and writes bundle report files. It does not connect to a database, invoke business runner modules, or execute subprocesses.

This remains a P0 blocker for a real Fast Lane execute pilot.

### N1 Runner Availability

The available guarded N1 runners are fixed to `20260605`:

```text
scripts/run_official_daily_ingestion_20260605_once.py
scripts/run_condition_source_activation_20260605_once.py
```

Both have a trade-date guard that blocks when `args.trade_date != TRADE_DATE`, and the imported implementation is specific to `20260605`.

No dedicated `20260608` guarded N1 official-daily or condition-source runner was found under `scripts/` or `src/ashare_v3/ingestion/`.

`scripts/run_real_daily_incremental.py` is not an acceptable Fast Lane guarded execute runner for this pilot because it does not implement the approved Fast Lane execute contract. It has no `--execute`, `--user-confirmed`, or `--postgres-commit-enabled` gate, writes broader N1/archive scope, and can archive Parquet through `archive_rows`.

## Recommended Decision

Primary decision: `FIRST_BUILD_N1_20260608_GUARDED_RUNNER`

Secondary decision: `IMPLEMENT_REAL_SAME_LAYER_ORCHESTRATION`

Rejected for the current real-pilot objective: `DOWNSCOPE_FIRST_PILOT_TO_DRY_RUN_ONLY`

Not required: `BLOCKED_NEED_USER_POLICY`

Rationale:

- The user policy is already clear: the desired end state is a real 20260609 Fast Lane pilot, but only if P0, rollback, scope, and guard requirements are satisfied.
- The earliest data blocker is N1-owned: `source_trade_date=20260608` has no N1 source facts.
- Even after N1 is repaired, current Fast Lane wrappers still cannot perform real same-layer business-runner orchestration.
- A dry-run-only pilot can remain available as a fallback, but it would not satisfy the requested real pilot objective.

Recommended gate order:

```text
1. N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_CONTRACT_GATE
2. N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_IMPLEMENTATION_GATE
3. N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW
4. N1_20260608_SOURCE_FACTS_EXECUTE
5. N1_20260608_SOURCE_FACTS_POST_REVIEW_REGISTRATION_GATE
6. RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_SAME_LAYER_ORCHESTRATION_IMPLEMENTATION_CONTRACT_GATE
7. RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_SAME_LAYER_ORCHESTRATION_IMPLEMENTATION_GATE
8. RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_PILOT_READINESS_GATE_WITH_DATE
```

## Required Implementation Scope

### N1 20260608 Guarded Runner

The next N1 contract should define dedicated guarded runner coverage for `20260608` source facts:

- official daily stock/index/board facts
- stock daily basic
- stock financial metrics
- condition-source activation inputs
- N1 quality/run/active-source registration
- rollback SQL for the exact source versions and batch ids

Required command guards:

- every execute must include `--execute --user-confirmed`
- N1 PostgreSQL commit path must include `--postgres-commit-enabled` when the runner requires it
- missing execute confirmation must block before any DB write
- P0 must be zero
- rollback SQL must exist and hard-fail before destructive DML
- expected rows must equal actual rows
- scoped outbox/inbox/checkpoint refs must remain zero
- N2/N3/N4/N5/N6 refs must remain zero before handoff

`scripts/run_real_daily_incremental.py` may be used only as reference material or refactored behind a new guarded contract. It must not be used directly as the approved Fast Lane N1 execute command.

### Fast Lane Real Same-Layer Orchestration

After N1 has an approved same-layer guarded runner, a separate runtime_control implementation contract should decide how to extend Fast Lane wrappers from report-only validation to real orchestration.

Required properties:

- real orchestration must be explicit and opt-in
- wrappers must still be same-layer only
- N1 wrapper can only orchestrate N1 guarded runners
- N2 wrapper can only orchestrate N2 guarded runners
- N3-A1 wrapper can only orchestrate N3-A1 guarded runners
- execute child commands must include `--execute --user-confirmed`
- N1 child commands must include `--postgres-commit-enabled` where required
- dry-run/preflight child steps may remain no-execute
- child failure must stop the bundle
- original child report paths must be preserved in `sub_report_paths`
- rollback paths and side-effect flags must be carried into bundle reports
- wrappers must not consume outbox/inbox/checkpoint or start workers
- wrappers must not enter N3-B/C, N4, N5, or N6

## Required Tests

N1 20260608 guarded runner tests:

- blocks missing `--execute`
- blocks missing `--user-confirmed`
- blocks missing `--postgres-commit-enabled` when required
- blocks wrong trade date
- validates planned table scope
- validates P0 zero
- validates expected/actual row matching
- validates rollback SQL hard-fail before destructive DML
- validates no N2/N3/N4/N5/N6 refs
- validates no scoped outbox/inbox/checkpoint refs
- rejects direct old-system touch

Fast Lane orchestration tests:

- report-only `--child-step-json` mode remains available
- real orchestration mode requires explicit wrapper execute confirmation
- execute child command without `--execute --user-confirmed` blocks
- N1 execute child command without required commit flag blocks
- cross-layer child command blocks
- N1 wrapper rejects N2/N3 commands
- N2 wrapper rejects N3 command and market-data pull
- N3-A1 wrapper rejects B1/C1/B2/N4/N5/N6 commands
- child failure stops subsequent child execution
- original child report paths are preserved
- rollback paths are preserved
- side-effect flags are recorded and forbidden flags block
- JSON schema validation still passes

## Forbidden Scope Proof

This alignment gate performed no business execution and no business write.

```text
code_modified=false
database_written=false
n1_execute=false
n2_execute=false
n3_a1_execute=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
n3_b_or_n3_c_entered=false
n4_n5_n6_entered=false
realtime_market_data_pulled=false
proposal_order_trade_touched=false
sim_position_pnl_real_trade_touched=false
old_system_touched=false
```

## Next Recommended Gate

`N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_CONTRACT_GATE`

After the N1 guarded-runner contract and implementation are approved and post-reviewed, return to runtime_control for:

`RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_SAME_LAYER_ORCHESTRATION_IMPLEMENTATION_CONTRACT_GATE`
