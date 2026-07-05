# N5 20260612 Bounded Action Consumer Bounded Controls Command Contract Repair

Result: `FIX_PASS`

## Root Cause

The unified chain wrapper called `scripts/run_action_consumer_once.py` without the required bounded smoke controls:

- `--max-runtime-seconds`
- `--heartbeat-interval-seconds`

N5 correctly blocked with gate `n5_semantic_action_smoke_bounded_controls`.

## Repair

Updated `scripts/run_n3_n4_n5_realtime_chain_once.py` so the N5 child command includes:

- `--max-runtime-seconds 120`
- `--heartbeat-interval-seconds 10`

The wrapper also exposes defaults for these values.

## Validation

- red test observed
- targeted tests: `55 OK`
- compileall: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope

This repair did not start scheduler, manually execute wrapper/N3/N4/N5, write DB, run rollback, consume/update outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/trade.
