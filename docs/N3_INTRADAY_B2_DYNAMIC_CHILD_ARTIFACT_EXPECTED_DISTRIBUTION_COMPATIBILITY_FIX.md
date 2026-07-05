# N3 Intraday B2 Dynamic Child Artifact Expected Distribution Compatibility Fix

Result: `FIX_PASS`

Gate: `N3_INTRADAY_B2_DYNAMIC_CHILD_ARTIFACT_EXPECTED_DISTRIBUTION_COMPATIBILITY_FIX_GATE`

Layer role: `N3_market_data`

## Root Cause

The dynamic intraday B2 execute contract already included `calculation_config`, but it still omitted runner-compatible `expected_distribution`.

`realtime_projection_execute.py` builds projection rows and then validates:

- `ready_rows`
- `not_ready_rows`
- `ready_by_asset`
- `not_ready_by_asset`
- `projection_signal_status`
- `board_not_ready`
- `bj_920xxx_not_ready`

Because the generated contract had no canonical distribution, B2 failed with:

```text
N3-B2 blocked: not_ready row count differs from contract
```

A later read-only observation saw HHMM `1020` still blocked with a B2 contract that had `expected_distribution=false`; that artifact was generated before this fix was available to the scheduler and is historical blocked evidence, not a post-fix generated contract proof.

## Fix

Dynamic B2 dry-run, execute contract, and execute preflight now include:

- `expected_distribution`
- `expected_distribution_policy`

For `artifact_generation_mode=dynamic_intraday_child_artifact`, the policy is:

```text
mode=derive_from_projection_rows
```

The B2 runner materializes the canonical distribution from the projection rows it just built, then runs the same strict validation against that materialized distribution.

Formal non-dynamic B2 contracts are unchanged: they must still provide explicit reviewed distribution counts.

## Auction Mode

Auction / snapshot-only B2 remains explicitly blocked until a snapshot-only B2 runner path exists:

```text
PREFLIGHT_BLOCKED
blocker=b2_auction_mode_runner_requires_today_minute_run
today_minute_run_id=null
closed_minute_forged=false
```

## Forbidden Scope

```text
manual_wrapper_execute=false
manual_supervisor_execute=false
manual_b1_execute=false
manual_c1_execute=false
manual_b2_execute=false
database_written=false
launchd_modified_or_unloaded=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
old_system_touched=false
trade_path_touched=false
```

## Validation

```text
targeted_intraday_tests=PASS
targeted_realtime_projection_tests=PASS
json_parse=PASS
compileall=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS
```

Next gate:

```text
N3_INTRADAY_B1_C1_B2_AUTO_POLL_FIRST_EFFECTIVE_EXECUTION_OBSERVATION_AND_CLOSEOUT
```
