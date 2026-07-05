# N4 20260615 Repaired Formal Price Amount Chain Replay Dry-Run Preflight Path Repair

Result: `REPAIR_PASS`

## Root Cause

The previous artifact refresh used the same `PREFLIGHT` artifact path for two different artifacts:

- dry-run preflight
- business execute final preflight

The final preflight refresh overwrote the dry-run preflight. If a later execute or final-gate command omitted `--dry-run-preflight-json-path`, the runner could fall back to the default stale file:

`docs/N4_action_confirmation_metric_execute_preflight.json`

That default file is a 20260602 lineage artifact and is forbidden for this 20260615 replay gate.

## Path Repair

Dedicated 20260615 dry-run preflight artifact:

`docs/N4_20260615_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_REPLAY_DRY_RUN_PREFLIGHT.json`

Dedicated 20260615 final preflight artifact:

`docs/N4_20260615_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_REPLAY_PREFLIGHT.json`

The refreshed contract/final preflight command explicitly used:

```text
--dry-run-preflight-json-path docs/N4_20260615_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_REPLAY_DRY_RUN_PREFLIGHT.json
```

## Refreshed Proof

- dry-run: `DRY_RUN_PASS`
- dry-run preflight: `PREFLIGHT_PASS`
- contract: `CONTRACT_PASS`
- final preflight: `PREFLIGHT_PASS`
- candidate_count: `4725`
- TriggerMatched: `0`
- TriggerPendingMarketData: `4725`
- TriggerStateChanged: `0`
- planned common_trigger_state: `4725`
- planned common_trigger_match: `0`
- planned common_event_outbox: `4725`
- P0/P1/P2: `0/1/0`

## Stale Default Avoidance

The execute final gate allowed command must include the dedicated 20260615 dry-run preflight path:

```text
--dry-run-preflight-json-path docs/N4_20260615_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_REPLAY_DRY_RUN_PREFLIGHT.json
```

It must not use:

```text
docs/N4_action_confirmation_metric_execute_preflight.json
```

## Forbidden Scope

- N4 execute: false
- database write: false
- rollback execute: false
- outbox/inbox/checkpoint consume or update: false
- N5/N6 entered: false
- scheduler/worker started: false
- voice/mobile/sim/position/order/real trade touched: false
- old system touched: false

## Next Gate

`N4_20260615_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_REPLAY_FINAL_GATE_REVIEW_RETRY`
