# N3 Intraday B1/C1/B2 Auto-Poll Activation Contract

Result: `CONTRACT_PASS`

Layer role: `N3_market_data`

This gate only defines the activation contract. It does not start cron, does not install or enable launchd, does not execute the supervisor, does not execute B1/C1/B2, does not write database rows, does not consume or update outbox/inbox/checkpoint, and does not enter N4/N5/N6.

## Source Proof

Inputs reviewed:

```text
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_POST_REVIEW.md/json
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_IMPLEMENTATION.md/json
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_BOUNDED_SMOKE_REPORT.md/json
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_BOUNDED_SMOKE_IDEMPOTENCY_REPORT.md/json
src/ashare_v3/market/intraday_supervisor.py
scripts/run_n3_intraday_b1_c1_b2_supervisor_once.py
```

Bounded smoke result:

```text
mode=plan_only
status=ready
latest_closed_minute_hhmm=0931
child_steps=B1 -> C1 -> B2
executed_child_command_count=0
```

Idempotency smoke result:

```text
status=noop
reason=latest_closed_minute_already_processed
child_steps=0
executed_child_command_count=0
```

## Activation Model

First version uses bounded polling, not a long-running worker.

Future activation may use `launchd` or `cron`, but only after a separate final gate. The scheduler wakes once per minute, invokes one supervisor run, and the supervisor process exits after that bounded pass.

This gate does not install, enable, unload, or edit any scheduler entry.

## Command Boundary

Future live activation must use an argv list equivalent to:

```text
python3
scripts/run_n3_intraday_b1_c1_b2_supervisor_once.py
--for-trade-date <for_trade_date>
--subscription-run-id <market_data_subscription_run_id>
--preload-run-id <previous_day_minute_preload_run_id>
--json-report-path docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_REPORT_<for_trade_date>.json
--markdown-report-path docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_REPORT_<for_trade_date>.md
--execute
--user-confirmed
```

Required environment:

```text
PYTHONPATH=src:scripts
ASHARE_V3_POSTGRES_DSN points to v3 runtime PostgreSQL
TUSHARE_TOKEN is available when child source adapters require it
```

Live activation remains blocked until a separate user-confirmed final gate. The supervisor itself must include `--execute --user-confirmed`, and each generated B1/C1/B2 child command must also include `--execute --user-confirmed`.

Shell strings are forbidden. Scheduler configuration must use `ProgramArguments` or equivalent argv-list semantics.

## Timing Policy

The supervisor reuses:

```text
ashare_v3.market.today_minute_plan.calculate_latest_closed_minute
```

Rules:

```text
only process closed minutes
current local date must equal for_trade_date
pre-open returns noop:no_closed_minute_available
date mismatch returns blocked:current_date_mismatch
midday break follows the same closed-minute policy
post-close may process the final closed minute only through reviewed child artifacts
never process an unclosed minute
```

## Idempotency Policy

Watermark source:

```text
common_market_data_run where status='passed'
```

No new state table is introduced.

Watermark run-id prefixes:

```text
realtime_daily_snapshot_<for_trade_date>_until_
today_minute_bar_1m_<for_trade_date>_until_
realtime_projection_metric_<for_trade_date>_until_
```

If the deterministic B2 run id for the latest `for_trade_date + HHMM` is already passed, supervisor returns:

```text
status=noop
reason=latest_closed_minute_already_processed
child_steps=[]
```

If only part of B1/C1/B2 has already passed, the supervisor filters passed stage run ids and keeps the remaining stages in B1 -> C1 -> B2 order.

## Stage Order

```text
1. B1 realtime_daily_snapshot
2. C1 today_minute_bar_1m
3. B2 realtime_projection_metric
```

If any child stage returns non-zero, the supervisor stops immediately:

```text
status=blocked
reason=child_step_failed
failed_stage=<stage>
```

## Forbidden Scope

The activation contract forbids:

```text
N4/N5/N6 execution
outbox/inbox/checkpoint consumption or update
long-running worker
cron/launchd install or enable in this gate
rollback SQL execution
delivery/push/voice/mobile
proposal/order/trade
sim/position/PnL/real trade
old system access or mutation
```

## Future Final Gate Requirements

Before activation can be enabled, runtime_control must re-review:

```text
for_trade_date calendar is open and current local date matches
subscription_run_id is passed
preload_run_id is passed
child B1/C1/B2 contract/preflight artifacts are ready or produced by an approved pre-step
scheduler command is argv-list only
no conflicting scheduler activation exists
stop/uninstall policy is reviewed
bounded smoke remains PASS after command changes
```

Next recommended gate:

```text
N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_PREFLIGHT_REVIEW_GATE
```
