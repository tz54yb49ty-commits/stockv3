# N3 Intraday B1/C1/B2 Auto-Poll Scheduler No-Overlap Guard

Result: `GUARD_PASS`

Layer role: `N3_market_data`

This gate completes the no-overlap proof for scheduler activation review. It did not install, enable, or modify cron/launchd. It did not execute the wrapper, supervisor, B1/C1/B2, rollback SQL, database writes, event infra consumption, N4/N5/N6, worker startup, old-system paths, or trading paths.

## Selected Strategy

Use a single macOS user `launchd` job Label with `StartInterval=60`.

No wrapper lockfile is required for the selected v1 strategy. A cron fallback remains blocked until a separate wrapper lockfile or equivalent external lock guard is implemented and reviewed.

## No-Overlap Proof

Local `launchd.plist` manual proof:

- `Label` is required and uniquely identifies the job to launchd.
- `ProgramArguments` is the argument vector passed to the job.
- `StartInterval` starts the job every N seconds, and if the job is still running during an interval firing, that interval firing is missed.

Therefore, one loaded user LaunchAgent with one Label and `StartInterval=60` will not spawn a second overlapping instance of that same Label while the prior wrapper invocation is still running. The scheduler skips that firing instead.

## Launchd Draft Summary

- plist draft: `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_SCHEDULER_LAUNCHD_DRAFT.plist`
- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- `StartInterval`: `60`
- `RunAtLoad`: `false`
- `KeepAlive`: `false`
- working directory: `/Users/chuanfuchen/Documents/A股监控系统v3`
- `ProgramArguments`: argv list, no shell string
- `PYTHONPATH`: `src:scripts`
- timezone: `Asia/Shanghai`
- stdout: `/Users/chuanfuchen/Documents/A股监控系统v3/logs/n3_intraday_b1_c1_b2_auto_poll.stdout.log`
- stderr: `/Users/chuanfuchen/Documents/A股监控系统v3/logs/n3_intraday_b1_c1_b2_auto_poll.stderr.log`

## Activation Command

The plist draft uses:

```text
/usr/bin/env python3 scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py \
  --for-trade-date 20260611 \
  --subscription-run-id market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --preload-run-id previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --source-condition-run-id condition_layer_20260610_source_20260610_for_20260611_v1 \
  --docs-root docs \
  --sql-root sql \
  --json-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json \
  --markdown-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.md \
  --execute \
  --user-confirmed
```

The command is represented as plist `ProgramArguments`, not as a shell string.

## Lockfile Decision

Lockfile is not used in v1. If cron fallback is needed later, it must be BLOCKED until a reviewed implementation defines:

- lock path
- PID ownership check
- stale lock threshold
- safe stale lock removal
- cleanup on normal and blocked exit
- tests proving no overlapping wrapper execution

Proposed future lock path if needed:

```text
/tmp/ashare_v3_n3_intraday_b1_c1_b2_auto_poll_20260611.lock
```

## Stop Policy

- Disable/unload the single launchd Label in a future scheduler execute/stop gate.
- Verify no wrapper process remains with a scoped process check.
- Stop policy must not execute rollback SQL.
- Stop policy must not touch DB, outbox/inbox/checkpoint, N4/N5/N6, old system, or trading paths.
- If a wrapper pass blocks, review the latest wrapper report before re-enabling.

## BLOCK Conditions

- No-overlap proof missing.
- Scheduler artifact uses shell string.
- `ProgramArguments` missing `--execute` or `--user-confirmed`.
- `WorkingDirectory` missing or not project root.
- `PYTHONPATH` missing `src:scripts`.
- `KeepAlive=true`.
- `RunAtLoad=true` without explicit future approval.
- Multiple launchd Labels point to the same wrapper command.
- Cron fallback requested without lockfile guard implementation.
- Old-system, N4/N5/N6, or outbox consumer markers appear in scheduler argv.

## Forbidden Scope Proof

```text
cron_launchd_installed_or_enabled=false
cron_launchd_modified=false
wrapper_execute_invoked=false
supervisor_execute_invoked=false
b1_c1_b2_execute_invoked=false
database_written=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
old_system_touched=false
```

## Decision

- allow return to scheduler activation final gate review: `True`
- allow scheduler install now: `False`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_SCHEDULER_ACTIVATION_FINAL_GATE_REVIEW`
