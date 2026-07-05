# V3 Realtime Metric N5 Contract Alignment

Result: `ALIGNMENT_PASS`

This is a static contract artifact. It does not execute N5, write action facts, publish action outbox, consume checkpoints, enter N6, or touch voice/mobile/sim/trade.

## Entry

不改 N5 当前业务规则.

`TriggerMatched` remains the only N5 entry event.

These events cannot create action confirmation:

- `TriggerPendingMarketData`
- `TriggerStateChanged`

## Outputs

N5 canonical outputs remain:

- `ActionEligible`
- `ActionBlocked`
- `ActionExecuted`
- `ActionSkipped`

## Realtime Semantics

`ActionEligible` can be produced immediately after a valid `TriggerMatched`.

`ActionExecuted` uses:

- trigger-time saved virtual `120m / 30m / 5m` evidence from N3,
- plus the closed trigger-minute `1m` fact.

ActionExecuted 不代表真实下单, sim, voice, mobile, N6 display, or any real-trade intent.

N5 does not pull market data and does not rebuild raw minute indicators.
