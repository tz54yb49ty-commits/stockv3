# N3 Intraday B1/B2 Auction Realtime Start Policy And Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `N3_market_data`

This gate fixes the intraday auto-poll start boundary so B1 realtime/auction snapshot and B2 realtime projection are no longer blocked by the C1 closed-minute gate. It does not install or modify launchd, manually execute wrapper/supervisor/B1/C1/B2, write database rows, consume or update outbox/inbox/checkpoint, enter N4/N5/N6, start a worker, or touch old-system/trading paths.

## Policy

```text
09:15-09:19: B1/B2 plan/prewarm only; no supervisor or child execution.
09:20-09:25: B1 auction snapshot and B2 auction/snapshot-only projection may execute.
09:25-09:30: B1 opening result / pre-continuous snapshot and B2 snapshot-only projection may execute.
09:30-09:31: B1 realtime snapshot and B2 snapshot-only projection may execute before first closed minute.
09:32+: first closed minute label 09:31 exists; use B1 -> C1 -> B2.
```

C1 remains strictly closed-minute bounded. The 09:31 minute label is executable only at 09:32 or later.

## Implementation Summary

- Supervisor now returns `auction_preopen_plan_only` for 09:15-09:19.
- Supervisor now returns B1 -> B2 child steps for 09:20 until the first closed minute is available.
- C1 is skipped before the first closed minute with `reason=no_closed_minute_available`.
- Auction/pre-minute B1/B2 run ids and artifact paths use `auction_HHMM`; closed-minute paths keep the existing `until_HHMM` form.
- Wrapper passes `projection_input_mode` and `effective_hhmm` into the child artifact generator.
- Child artifact generator writes B2 contracts with `projection_input_mode=auction_or_snapshot_only`, `today_minute_run_id=null`, and `requires_today_minute_run=false`.
- Child artifact generator reads same-day N3-A1 subscription dry-run/execute report artifacts when present and uses them to fill B1/C1/B2 expected counts; it does not connect to the database.

## Proof

```text
09:19 -> noop / auction_preopen_plan_only / B1_B2_PREWARM_ONLY / effective_hhmm=0920
09:20 -> ready / auction_snapshot_projection_ready / child_steps=B1,B2 / C1 skipped
09:25 -> ready / auction_snapshot_projection_ready / child_steps=B1,B2 / C1 skipped
09:32 -> ready / new_closed_minute_detected / child_steps=B1,C1,B2
B2 auction mode -> today_minute_run_id=null / requires_today_minute_run=false / closed_minute_forged=false
count enrichment -> source=docs/N3_A1_20260611_MARKET_DATA_SUBSCRIPTION_DRY_RUN.json
B1 expected snapshot counts -> stock=1890 index=83 board=127
C1 expected object counts -> stock=250 index=19 board=14
```

## Read-Only Scheduler Observation

The already-enabled launchd scheduler report was inspected read-only. This gate did not manually execute the wrapper. The latest observed automatic pass was:

```text
source=docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json
status=blocked
reason=child_step_failed
latest_closed_minute_hhmm=0946
stage_order_policy=B1_C1_B2_AFTER_CLOSED_MINUTE
projection_input_mode=closed_minute
executed_child_command_count=1
failed_stage=B1
root_cause=pre-fix dynamic artifact expected_asset_counts were 0 while live subscription counts were stock=1890,index=83,board=127
followup_fix=generator now enriches expected counts from subscription artifacts for future generated minutes
```

## Validation

```text
targeted_intraday_tests=PASS (36 tests)
compileall=PASS
json_parse=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS (tracked scope plus no-index equivalent for new untracked files)
```

## Forbidden Scope

```text
launchd_installed_or_modified=false
manual_wrapper_execute=false
manual_supervisor_execute=false
manual_b1_c1_b2_execute=false
database_written_by_this_gate=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started_by_this_gate=false
old_system_touched=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
```

## Decision

- allow post-review gate: `True`
- next gate: `N3_INTRADAY_B1_B2_AUCTION_REALTIME_START_POLICY_AND_IMPLEMENTATION_POST_REVIEW_GATE`
