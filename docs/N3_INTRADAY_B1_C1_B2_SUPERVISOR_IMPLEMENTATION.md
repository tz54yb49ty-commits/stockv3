# N3 Intraday B1/C1/B2 Supervisor Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `N3_market_data`

This gate implemented a bounded run-once N3 intraday supervisor for B1/C1/B2 orchestration. It did not execute real B1/C1/B2 market-data commands, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not start a worker, did not enter N4/N5/N6, and did not touch delivery/push/voice/mobile, proposal/order/trade, sim, position, PnL, real trade, or the old system.

## Implemented Scope

- Added `src/ashare_v3/market/intraday_supervisor.py`.
- Added `scripts/run_n3_intraday_b1_c1_b2_supervisor_once.py`.
- Added `tests/test_n3_intraday_supervisor.py`.

The supervisor:

- computes the latest closed minute using the existing N3 C1 closed-minute policy;
- blocks when local date does not equal `for_trade_date`;
- no-ops before the first closed minute;
- derives deterministic B1/C1/B2 run ids for `for_trade_date + HHMM`;
- derives child commands as argument lists, never shell strings;
- requires child commands to include `--execute --user-confirmed`;
- defaults the CLI to plan-only mode unless supervisor-level `--execute --user-confirmed` is provided;
- stops after the first failed child command;
- writes JSON/Markdown supervisor reports;
- uses passed `common_market_data_run.run_id` values as an idempotency watermark when DB watermark lookup is enabled.

## Command Shape

The supervisor creates child commands in this order:

1. `scripts/run_realtime_daily_snapshot_once.py` for B1 fact-only no-outbox snapshot.
2. `scripts/run_today_minute_bar_1m_once.py` for C1 closed-minute facts.
3. `scripts/run_realtime_projection_metric_once.py` for B2 realtime projection facts.

The supervisor does not generate or rewrite B1/C1/B2 business contracts. It points each child runner at deterministic artifact paths for the detected closed minute. If a required child artifact is missing or incompatible, the relevant child runner blocks and the supervisor stops.

## Safety Proof

- `layer_role=N3_market_data`.
- `worker_started=false`.
- `outbox_consumed_or_updated=false`.
- `n4_n5_n6_entered=false`.
- `old_system_touched=false`.
- `trade_sim_position_pnl_touched=false`.
- No subprocess is executed in plan-only mode.
- Test fake subprocess execution proves failure stop without running real business runners.

## Validation

```text
PYTHONPATH=src:scripts python3 -m unittest \
  tests.test_n3_intraday_supervisor \
  tests.test_today_minute_plan \
  tests.test_today_minute_execute \
  tests.test_market_data_realtime_snapshot_execute \
  tests.test_realtime_projection_execute

Ran 65 tests in 0.046s
OK
```

Additional validation is recorded in the JSON artifact and final response.

## Next Gates

Recommended next gate:

```text
N3_INTRADAY_B1_C1_B2_SUPERVISOR_POST_REVIEW_GATE
```

After post-review, run a bounded smoke gate before any launchd/cron activation:

```text
N3_INTRADAY_B1_C1_B2_SUPERVISOR_BOUNDED_SMOKE_GATE
```

