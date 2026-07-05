# V3 Realtime Signal Action Run-Once Wrapper Contract

Result: `CONTRACT_PASS`

This contract only describes the first runtime shape. It does not install launchd, enable a scheduler, execute a wrapper, start a worker, write a database row, mutate outbox/inbox/checkpoint, or enter N6.

## Runtime Model

First version:

```text
launchd StartInterval=3
run-once wrapper
PLAN_ONLY by default
execute requires --execute --user-confirmed
```

The wrapper must use an argv list for every child command. Shell strings are not allowed.

## No-Overlap

Each pass takes a no-overlap lock scoped by:

```text
for_trade_date + chain_name
```

If the lock is busy, the wrapper returns `NOOP_PASS`.

## Stage Order

1. N3 realtime virtual metric.
2. N4 trigger from N3 metric.
3. N5 action from `TriggerMatched`.

`MinuteBarClosed` is not a fast-lane blocker.

## Forbidden Scope

不进入 N6.

The wrapper contract does not allow:

- long-running worker
- voice
- mobile
- sim
- position/PnL
- real trade
- scheduler install/enable inside this contract gate
