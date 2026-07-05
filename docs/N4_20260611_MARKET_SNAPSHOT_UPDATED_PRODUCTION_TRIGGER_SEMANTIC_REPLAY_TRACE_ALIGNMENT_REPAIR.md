# N4 20260611 Production Replay Trace Alignment Repair Decision

Result: `DECISION_PASS`

This was a read-only runtime_control decision gate. It did not execute N4/N5, did not execute N3 B2, did not modify scheduler, did not write the database, did not consume/update outbox/inbox/checkpoint, and did not enter N6 or any trading/sim/position/voice/mobile path.

## Current Blocker

The production replay source itself is healthy:

- N3 `MarketSnapshotUpdated`: `2100` pending
- stock/index/board: `1890/83/127`
- N4 localized context: `4480` rows, `2100` objects
- new replay consumer baseline: `0`

The blocker is trace alignment:

- candidate projection rows: `2100`
- join by `projection.snapshot_event_id = MarketSnapshotUpdated.event_id`: `0`
- join by `snapshot_id + identity`: `0`
- projection status: all `not_ready/blocked`

This means the candidate projection run cannot be safely treated as the production metric for the current B1 standard outbox source.

## Decision

Recommended route:

`N3_GENERATE_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC`

Ownership:

`blocked_by_layer=N3_market_data`

Why:

N3 owns realtime projection facts and their trace. N4 may consume N3 standard projection metrics, but it must not reinterpret an unaligned projection run as if it belonged to the current `MarketSnapshotUpdated` source.

## Rejected Route

`N4_REVIEWED_MATCHER_COMPATIBILITY_PATH` is blocked for now.

Reason: the issue is not only event_id mismatch. Even `snapshot_id + identity` joins `0`, so an N4 compatibility path would require raw fact scanning or out-of-band inference. That violates the production replay boundary unless N3 first provides an approved summary/equivalence contract.

## N5 Status

N5 readiness remains blocked:

- no production `TriggerMatched`
- fixture semantic smoke remains excluded from formal N5 input
- `TriggerPendingMarketData` and `TriggerStateChanged` are not N5 action entries

## Next Gate

Enter:

`N3_20260611_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_CONTRACT_PREFLIGHT_GATE`

It should start as dry-run/contract/preflight only.
