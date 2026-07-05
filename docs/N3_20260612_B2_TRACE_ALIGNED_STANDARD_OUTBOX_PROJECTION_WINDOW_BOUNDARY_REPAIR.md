# N3 20260612 B2 Trace-Aligned Standard Outbox Projection Window Boundary Repair

Result: `REPAIR_PASS`

## Root Cause

The 20260612 auto chain blocked at `N3-B2 trace-aligned standard outbox` for `UNTIL_1430`.

The standard-outbox projection policy used:

```text
projection_snapshot_time = latest_closed_minute + 1 minute
```

For a bucket boundary such as `latest_closed_minute=2026-06-12T14:30:00+08:00`, this produced `snapshot_time=14:31:00`, while the projection window remained `14:00-14:30`. PostgreSQL then rejected the row through `stock_realtime_projection_metric_check2`.

## Repair

Updated `src/ashare_v3/market/realtime_projection_execute.py` to separate:

- `projection_closed_label`: the closed minute used for calculation and trace.
- stored `snapshot_time`: the projection bucket timestamp that must satisfy DB window constraints.

For `standard_outbox_observed_at_to_latest_closed_minute`, boundary timestamps are now clamped to `window_end` for the stored `snapshot_time`, while the original source observed time and unclamped value remain in `raw_json`.

## Read-Only 1430 Proof

Contract:

```text
docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1430_EXECUTE_CONTRACT.json
```

Row-builder proof:

```text
rows=2082
stock/index/board=1872/83/127
ready stock/index/board=245/33/19
not_ready stock/index/board=1627/50/108
snapshot_time > window_end violations=0
contract distribution validation=PASS
```

Sample:

```text
identity_key=stock:SH:600000
snapshot_time=2026-06-12T14:30:00+08:00
window_start=2026-06-12T14:00:00+08:00
window_end=2026-06-12T14:30:00+08:00
projection_closed_label=2026-06-12T14:30:00+08:00
source_snapshot_time=2026-06-12T14:34:11.809967+08:00
unclamped_projection_snapshot_time=2026-06-12T14:31:00+08:00
projection_snapshot_time_clamped_to_window_end=true
```

## Validation

```text
focused realtime projection tests: 3 OK
targeted realtime chain/action tests: 77 OK
compileall scripts src tests: PASS
```

## Forbidden Scope

No scheduler start, no manual wrapper/N3/N4/N5 execution, no DB write by this repair, no rollback execution, no outbox/inbox/checkpoint consumption or update, no N6/voice/mobile/sim/trade path touched.

Scheduler is still `not_loaded`; wrapper/child process count is `0`.

Next gate:

```text
N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_REACTIVATION_GATE_AFTER_B2_PROJECTION_WINDOW_BOUNDARY_REPAIR
```
