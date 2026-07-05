# N3 Intraday C1 Dynamic Child Artifact Contract Compatibility Fix

Result: `FIX_PASS`

Layer role: `N3_market_data`

Fixed at: `2026-06-11T10:00:51+08:00`

This gate only changed generator code, tests, and compatibility artifacts. It did not manually execute the wrapper, supervisor, B1/C1/B2 child runners, rollback SQL, launchd changes, event consumers, N4/N5/N6, old-system paths, or trading paths.

## Root Cause

The dynamic C1 C0 dry-run artifact used:

```text
source_run_id=<market_data_subscription run_id>
```

but omitted:

```text
source_market_data_run_id
```

`scripts/run_today_minute_bar_1m_once.py` calls `today_minute_execute.py`, and `today_minute_execute.py` reads `plan["source_market_data_run_id"]` before any DB write. The live scheduler therefore blocked at C1 with:

```text
KeyError: source_market_data_run_id
```

## Canonical Field Decision

`source_market_data_run_id` must point to the N3 subscription control run:

```text
market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
```

It must not point to the B1 snapshot run. The C1 runner uses this id to load `minute_bar_1m` subscriptions from the N3 subscription control rows.

`source_run_id` remains as a compatibility alias.

## C1 Contract Compatibility Proof

In-memory dynamic artifact probe for `HHMM=0959` now produces:

```text
source_market_data_run_id=market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
source_run_id=market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
source_condition_run_id=condition_layer_20260610_source_20260610_for_20260611_v1
source_trade_date=20260610
prev_trade_date=20260610
latest_closed_minute=2026-06-11T09:59:00+08:00
execute_contract.source_market_data_run_id=market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
```

Wrapper-level test coverage also verifies that the generated C1 artifact exists before fake C1 child execution and contains the same source lineage fields.

## Live Scheduler Observation

Latest read-only report at fix time:

```text
path=docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json
status=blocked
failed_stage=C1
latest_closed_minute_hhmm=0957
error=KeyError: source_market_data_run_id
```

This report was generated from a pre-fix C1 artifact. Newly generated HHMM artifacts now contain the required field; the next observation gate should verify the next automatic wrapper run.

## Validation

```text
red_test_before_fix=PASS
targeted_intraday_tests=PASS
compileall=PASS
json_parse=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS
```

## Forbidden Scope Proof

```text
manual_wrapper_execute=false
manual_supervisor_execute=false
manual_b1_c1_b2_execute=false
database_written=false
launchd_installed_modified_or_unloaded=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started_by_this_gate=false
old_system_touched=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
```

## Decision

Allowed next gate:

```text
N3_INTRADAY_B1_C1_B2_AUTO_POLL_FIRST_EFFECTIVE_EXECUTION_OBSERVATION_AND_CLOSEOUT
```
