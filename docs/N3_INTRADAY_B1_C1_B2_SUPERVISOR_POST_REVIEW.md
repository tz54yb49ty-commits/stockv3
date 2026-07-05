# N3 Intraday B1/C1/B2 Supervisor Post Review

Result: `POST_REVIEW_PASS`

Layer role: `runtime_control`

This post-review was read-only with respect to runtime data. It did not execute the supervisor, did not execute B1/C1/B2, did not write database rows, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, did not start workers, did not enter N4/N5/N6, and did not touch delivery/push/voice/mobile, proposal/order/trade, sim, position, PnL, real trade, or the old system.

## Implementation Proof

The implementation artifacts are present and parseable:

```text
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_IMPLEMENTATION.md
docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_IMPLEMENTATION.json
```

Implemented files:

```text
src/ashare_v3/market/intraday_supervisor.py
scripts/run_n3_intraday_b1_c1_b2_supervisor_once.py
tests/test_n3_intraday_supervisor.py
```

The supervisor is scoped to `layer_role=N3_market_data`. It builds a bounded run-once plan from `for_trade_date`, `subscription_run_id`, `preload_run_id`, and the latest closed minute. It does not embed B1/C1/B2 business logic; it delegates to existing guarded N3 runner scripts.

## Safety Proof

Default CLI behavior is plan-only:

```text
without --execute --user-confirmed:
  child_step_results=[]
  executed_child_command_count=0
  execution_mode=plan_only
```

Execute mode requires supervisor-level confirmation:

```text
--execute + --user-confirmed required before invoking child commands
```

Each child command is an argv list and includes its own execute confirmation:

```text
B1 -> scripts/run_realtime_daily_snapshot_once.py ... --execute --user-confirmed
C1 -> scripts/run_today_minute_bar_1m_once.py ... --execute --user-confirmed
B2 -> scripts/run_realtime_projection_metric_once.py ... --execute --user-confirmed
```

No `shell=True` usage was found in the supervisor implementation.

## Idempotency Proof

The supervisor uses `common_market_data_run.status='passed'` run ids as a watermark. For a detected `for_trade_date + HHMM`, if the derived B2 projection run id is already passed, the supervisor returns:

```text
status=noop
reason=latest_closed_minute_already_processed
child_steps=[]
```

If a subset of stage run ids is already passed, the stage list filters those run ids and only keeps remaining stages.

## Closed-Minute Proof

The supervisor reuses:

```text
ashare_v3.market.today_minute_plan.calculate_latest_closed_minute
```

It blocks realtime operation when local date does not equal `for_trade_date`:

```text
status=blocked
reason=current_date_mismatch
```

Before the first closed minute it returns:

```text
status=noop
reason=no_closed_minute_available
```

## Child Command / Failure Proof

Stage order is fixed:

```text
B1 -> C1 -> B2
```

The child command guard blocks:

```text
N4/N5/N6 command markers
worker markers
old system paths
common_event_outbox / common_event_inbox / common_event_consumer_checkpoint mutation markers
proposal/order/trade/sim/position/PnL markers
```

If a child command returns non-zero, the supervisor marks:

```text
status=blocked
reason=child_step_failed
failed_stage=<stage>
```

and stops without invoking later stages.

## Validation Summary

Fresh validation:

```text
PYTHONPATH=src:scripts python3 -m unittest tests.test_n3_intraday_supervisor tests.test_today_minute_plan tests.test_today_minute_execute tests.test_market_data_realtime_snapshot_execute tests.test_realtime_projection_execute
Ran 66 tests
OK

python3 -m compileall src/ashare_v3/market/intraday_supervisor.py scripts/run_n3_intraday_b1_c1_b2_supervisor_once.py tests/test_n3_intraday_supervisor.py
PASS

JSON parse
PASS

forbidden scope scan
PASS

git diff --check
PASS
```

## Residual Notes

`P1`: the supervisor does not generate B1/C1/B2 child business contract/preflight artifacts. Before a live bounded smoke can execute child runners, the selected `for_trade_date + HHMM` must have reviewed child artifacts or the bounded smoke must be explicitly scoped to plan-only / fake-child verification.

This residual is non-blocking for implementation post-review, but it must be handled by the bounded smoke gate.

## Decision

The supervisor implementation satisfies the reviewed automatic-running design and may enter:

```text
N3_INTRADAY_B1_C1_B2_SUPERVISOR_BOUNDED_SMOKE_GATE
```

