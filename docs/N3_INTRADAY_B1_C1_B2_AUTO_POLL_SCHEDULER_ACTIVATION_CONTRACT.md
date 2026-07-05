# N3 Intraday B1/C1/B2 Auto-Poll Scheduler Activation Contract

Result: `CONTRACT_PASS`

Layer role: `N3_market_data`

This gate defines the scheduler activation contract and stop policy for the N3 intraday B1/C1/B2 auto-poll wrapper. It did not install or enable cron/launchd, did not execute the wrapper, did not execute the supervisor, did not execute B1/C1/B2, did not write database rows, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trading paths.

## Recommended Scheduler Model

Use a macOS user `launchd` agent as the first scheduler model. It should invoke one bounded wrapper command per minute during approved activation windows. The wrapper exits after each pass, so this is not a long-running worker.

`cron` is acceptable only as a fallback if launchd is unavailable, and it must call the same argv command.

The scheduler owns no business state. Idempotency remains owned by the wrapper and `common_market_data_run` passed-run watermark.

## Activation Command

The scheduler must call an argv list equivalent to:

```text
PYTHONPATH=src:scripts python3 scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py \
  --for-trade-date <for_trade_date> \
  --subscription-run-id <subscription_run_id> \
  --preload-run-id <preload_run_id> \
  --source-condition-run-id <source_condition_run_id> \
  --docs-root docs \
  --sql-root sql \
  --json-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_<for_trade_date>.json \
  --markdown-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_<for_trade_date>.md \
  --execute \
  --user-confirmed
```

Hard requirements:

- working directory: `/Users/chuanfuchen/Documents/A股监控系统v3`
- `PYTHONPATH=src:scripts`
- timezone: `Asia/Shanghai`
- DSN from the approved runtime environment, not embedded in scheduler text
- command composition must be argv list, not a shell string
- installing/enabling the scheduler requires a separate future user confirmation gate

## Run-Once Flow

1. Scheduler invokes the wrapper once.
2. Wrapper calculates latest closed minute.
3. Wrapper blocks or no-ops for date mismatch, no closed minute, or passed B2 watermark.
4. Wrapper dynamically generates B1/C1/B2 child artifacts.
5. Wrapper validates JSON artifacts and rollback SQL static safety.
6. Wrapper executes supervisor bounded pass.
7. Supervisor executes guarded child runners in B1 -> C1 -> B2 order.
8. Wrapper writes JSON/Markdown report and exits.

## Timing Policy

- First version is bounded polling, once per minute.
- Candidate windows are 09:31-11:31 and 13:01-15:01 Asia/Shanghai.
- Pre-open calls must no-op unless wrapper closed-minute policy reports a valid closed minute.
- Lunch break may no-op or process the last closed minute once; passed B2 watermark prevents repeats.
- Post-close may process only an unprocessed final closed minute.
- Final scheduler activation must prove a no-overlap mechanism before installation.

## Stop Policy

- `NOOP`: exit 0; wait until the next scheduled minute.
- `BLOCKED`: exit nonzero; current pass stops and report captures reason.
- Artifact conflict: block before supervisor execution.
- Artifact validation failure: block before supervisor execution.
- Child failure: supervisor stops at the failed stage; wrapper reports blocked.
- No in-process retry loop.
- No long-running worker.

## BLOCK Conditions

- Wrapper post-review is not `POST_REVIEW_PASS`.
- Activation command is not argv list.
- Activation command lacks `--execute` or `--user-confirmed`.
- `PYTHONPATH` or working directory is not pinned.
- `for_trade_date` and current date mismatch.
- Missing subscription/preload/source-condition run ids.
- Child artifact generation conflict.
- Child artifact JSON parse failure.
- Rollback SQL static check failure.
- Passed B2 watermark exists for the latest closed minute.
- A previous scheduler pass is still running or overlap cannot be ruled out.
- Scheduler command uses shell string execution.
- Scheduler argv references N4/N5/N6, outbox consumers, delivery, sim, position, order, or old-system paths.

## Forbidden Scope Proof

```text
cron_launchd_installed_or_enabled=false
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

- allow scheduler install now: `False`
- allow scheduler activation final gate review: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_SCHEDULER_ACTIVATION_FINAL_GATE_REVIEW`
