# N3 Intraday B2 Dynamic Child Artifact Contract Compatibility Fix

Result: `FIX_PASS`

Layer role: `N3_market_data`

Fixed at: `2026-06-11T10:10:55+08:00`

This gate only changed generator code, tests, and compatibility artifacts. It did not manually execute the wrapper, supervisor, B1/C1/B2 child runners, rollback SQL, launchd changes, event consumers, N4/N5/N6, old-system paths, or trading paths.

## Root Cause

The dynamic B2 execute contract omitted:

```text
calculation_config
```

`scripts/run_realtime_projection_metric_once.py` calls `realtime_projection_execute.py`, and `realtime_projection_execute.py` reads `contract["calculation_config"]` while building projection rows. The live scheduler therefore blocked at B2 with:

```text
KeyError: calculation_config
```

## Canonical Calculation Config

Dynamic closed-minute B2 contracts now include the reviewed canonical config:

```text
calculation_method=active_30m_bucket_projection_v1_strict_current_lineage
calculation_config_hash=c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d
window_total_seconds=1800
completion_ratio_min_ready=0.2
amount_projection_expand_threshold=1.2
amount_projection_shrink_threshold=0.8
price_flat_abs_pct_threshold=0.001
```

This matches existing reviewed B2 contracts for 20260605 and 20260608.

## B2 Contract Compatibility Proof

In-memory dynamic artifact probe for closed-minute `HHMM=1000`:

```text
preflight_result=PREFLIGHT_PASS
today_minute_run_id=today_minute_bar_1m_20260611_until_1000__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
calculation_config_present=true
calculation_method=active_30m_bucket_projection_v1_strict_current_lineage
calculation_config_hash=c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d
```

Auction-mode artifacts also include `calculation_config`, but are explicitly blocked because the current B2 runner still requires `today_minute_run_id`:

```text
projection_input_mode=auction_or_snapshot_only
dry_run_result=DRY_RUN_BLOCKED
preflight_result=PREFLIGHT_BLOCKED
blocker=b2_auction_mode_runner_requires_today_minute_run
today_minute_run_id=null
```

## Live Scheduler Observation

Latest read-only report at fix time:

```text
path=docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json
status=blocked
failed_stage=B2
latest_closed_minute_hhmm=1003
error=KeyError: calculation_config
```

This report was generated from a pre-fix B2 artifact. Newly generated closed-minute HHMM artifacts now contain the required `calculation_config`; the next observation gate should verify the next automatic wrapper run.

## Validation

```text
red_test_before_fix=PASS
targeted_intraday_tests=PASS
json_parse=PASS
compileall=PASS
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
