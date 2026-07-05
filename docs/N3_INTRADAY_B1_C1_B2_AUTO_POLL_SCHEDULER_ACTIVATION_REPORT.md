# N3 Intraday B1/C1/B2 Auto-Poll Scheduler Activation Report

Result: `ACTIVATION_PASS`

Layer role: `N3_market_data`

The approved launchd user agent was installed and bootstrapped. This gate did not manually execute the wrapper, supervisor, B1/C1/B2, rollback SQL, N4/N5/N6, outbox/inbox/checkpoint consumers, delivery/push/voice/mobile, proposal/order/trade/sim/position/PnL/real trade, or old-system paths.

## Installed Plist Proof

- approved plist: `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_SCHEDULER_LAUNCHD_DRAFT.plist`
- installed plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist`
- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- installed plist lint: `PASS`
- `StartInterval=60`
- `RunAtLoad=false`
- `KeepAlive=false`
- working directory: `/Users/chuanfuchen/Documents/A股监控系统v3`
- `PYTHONPATH=src:scripts`
- command includes `--execute --user-confirmed`
- command is `ProgramArguments` argv, not shell string

## Launchctl Loaded Proof

```text
domain=gui/501
state=not running
runs=2
last_exit_code=0
run_interval=60 seconds
stdout_path=/Users/chuanfuchen/Documents/A股监控系统v3/logs/n3_intraday_b1_c1_b2_auto_poll.stdout.log
stderr_path=/Users/chuanfuchen/Documents/A股监控系统v3/logs/n3_intraday_b1_c1_b2_auto_poll.stderr.log
```

The scheduler performed one automatic interval run after bootstrap. The wrapper report shows a safe no-op:

```text
status=noop
reason=no_closed_minute_available
latest_closed_minute_hhmm=null
artifact_generation=not_written
artifact_validation=not_run
executed_child_command_count=0
```

## No-Overlap Proof

The active scheduler uses the reviewed strategy:

- single launchd Label
- `StartInterval=60`
- `KeepAlive=false`
- `RunAtLoad=false`

The no-overlap guard contract records the launchd behavior that an interval firing is missed while the same job is still running, preventing overlapping instances for this Label.

## Read-Only Checks

- crontab checked: no N3 auto-poll entry
- process check: no wrapper/supervisor/B1/C1/B2 runner process remains
- stderr log: empty

## Forbidden Scope Proof

```text
manual_wrapper_execute=false
manual_supervisor_execute=false
manual_b1_c1_b2_execute=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
old_system_touched=false
```

## Stop / Unload Command

Not executed in this gate:

```text
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Post-stop verification commands:

```text
launchctl print gui/$(id -u)/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll
ps -axo pid,ppid,command | rg 'run_n3_intraday_b1_c1_b2_auto_poll_once|run_n3_intraday_b1_c1_b2_supervisor_once|run_realtime_daily_snapshot_once|run_today_minute_bar_1m_once|run_realtime_projection_metric_once'
```

## Validation

```text
report_json_parse=PASS
installed_plist_lint=PASS
launchctl_print=PASS
wrapper_report_json_parse=PASS
forbidden_scope_assertions=PASS
git_diff_check=PASS
```

## Decision

- allow scheduler activation post-review: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_SCHEDULER_ACTIVATION_POST_REVIEW_GATE`
