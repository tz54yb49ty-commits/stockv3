# V3 Realtime Metric N4 Contract Alignment

Result: `ALIGNMENT_PASS`

This is a static contract alignment artifact. It does not execute N4, write a database row, publish outbox, consume inbox/checkpoint, start a worker, enter N5/N6, or touch trading paths.

## Input Policy

不改 N4 当前业务规则.

N4 can consume N3 standardized, traceable realtime virtual metrics from the N3 metric contract. N4 不直接读取 raw minute rows, does not call market adapters, and does not rebuild 1m/5m/30m/120m indicators.

`MinuteBarClosed` is not a fast-lane blocker. It remains strict/replay/correction evidence.

## Outputs

N4 canonical outputs remain:

- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`

Runtime `signal_type` remains only:

- `B_BUY`
- `S_SELL`

## Routing

- Metric ready: evaluate the current N4 business rule.
- Metric missing or quality failed: write `TriggerPendingMarketData`.
- New valid match: write `TriggerMatched`.
- Previously live trigger now invalid: write `TriggerStateChanged(trigger_live=false)`.

N4 does not enter N5 directly. N5 only consumes standard N4 events.
