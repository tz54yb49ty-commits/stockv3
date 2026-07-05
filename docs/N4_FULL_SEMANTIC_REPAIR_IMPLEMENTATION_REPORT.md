# N4 FULL Semantic Repair Implementation Report

Result: **IMPLEMENTATION_PASS**

Layer role: `N4_trigger`

This gate only repaired N4 code, tests, and contract/report artifacts. It did
not execute N4, write database rows, consume or update outbox/inbox/checkpoint,
start a worker, enter N5/N6, or touch old-system / trade / sim / position
surfaces.

## Repaired Semantic Rule

The previous implementation treated every `BUY:FULL / SELL:FULL`
`TriggerMatched` as forbidden. That was too broad.

The repaired rule is a strict whitelist:

- N4 still must not discover FULL by itself.
- FULL may only come from N2-localized context where `condition_key` and
  `original_condition_key` are the same `BUY:FULL` or `SELL:FULL`.
- `BUY:FULL` may match only on `D` when current transition is `volume_up`,
  transition amount passes, and the D trigger amount chain passes.
- `SELL:FULL` may match only on `D` when current transition is
  `low_volume_down`, transition amount passes, and the D trigger amount chain
  passes.
- Legal FULL `TriggerMatched` must emit `trigger_kind=trigger`,
  `trigger_period=D`, `triggered_periods=["D"]`, `all_trigger_periods=["D"]`,
  `primary_trigger_period=D`, `trigger_mark_candidate=normal`,
  `projection_30m_flag=false`, `projection_30m_type=none`,
  `n5_entry_allowed=true`, `trigger_live=true`, `current_status=matched`, and
  non-null reviewed `trigger_price`.

## Code Repair Summary

- `src/ashare_v3/trigger/rule_v4_matcher.py`
  - Replaced the early `full_semantics_blocked` branch with a D-only FULL
    evaluator.
  - FULL now uses the same transition and amount-chain proof as ordinary D,
    while forcing normal marker and no 30m projection marker.
  - FULL requires matching N2 context keys and blocks with
    `full_n2_context_missing` if the localized FULL context proof is absent.

- `src/ashare_v3/trigger/v4_enforcement.py`
  - Removed global `full_condition_matched_forbidden`.
  - Added strict FULL payload validation for context key, D-only periods,
    trigger kind, marker, projection flags, and signal type.

- `src/ashare_v3/trigger/v4_corrected_dry_run.py`
  - Replaced future `FULL forbidden` reporting with `FULL semantic blocked`.
  - Added `full_semantic_proof`; kept the old proof key only as a superseded
    compatibility alias.

- `src/ashare_v3/trigger/v4_corrected_execute_contract.py`
  - Replaced `FULL_forbidden_by_default` with `full_semantic_contract_guard`.
  - Contract now plans legal FULL rows as normal `TriggerMatched` and only
    counts invalid FULL rows as semantic blockers.

- `src/ashare_v3/trigger/rule_v4_execute.py`
  - Updated quality item wording so FULL is no longer described as permanently
    blocked; only whitelist-failing FULL rows remain visible.

- `docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_CONTRACT.md/json`
  - Updated P0-003 to the FULL semantic whitelist.

- `docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_PREFLIGHT.md/json`
  - Re-labeled stale pre-repair FULL evidence as historical.

## FULL Semantic Proof

Tests now prove:

- `BUY:FULL + D volume_up + amount chain pass` produces `TriggerMatched`.
- `SELL:FULL + D low_volume_down + amount chain pass` produces
  `TriggerMatched`.
- FULL output is `D` only and uses `trigger_mark_candidate=normal`.
- FULL with mismatched `condition_key/original_condition_key` is blocked.
- FULL with `trigger_period=30m` is blocked.
- FULL with `triggered_periods/all_trigger_periods/primary_trigger_period`
  containing `30m` is blocked.
- FULL with `trigger_kind=hint` is blocked.
- FULL with `trigger_mark_candidate=30m_volume/30m_shrink` is blocked.
- FULL missing reviewed `trigger_price` remains blocked by existing price
  source enforcement.

## Regression Proof

Ordinary BUY/SELL tests remain unchanged. HINT 30m tests remain unchanged:

- ordinary BUY/SELL `trigger_kind=trigger` still cannot use 30m as a formal
  period.
- `BUY_HINT / SELL_HINT` still use `trigger_kind=hint` and may use
  `trigger_period=30m`, while keeping formal period arrays empty.
- runtime `signal_type` is still only `B_BUY / S_SELL`.
- corrected dry-run still separates compliant and blocked plans before execute.
- execute planning still persists only valid N5-entry `TriggerMatched` rows.

## Forbidden Scope Proof

- N4 execute performed: `false`
- DB writes performed: `false`
- rollback executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N5/N6 entered: `false`
- worker started: `false`
- market data pulled: `false`
- delivery/push/voice/mobile: `false`
- sim/position/order/trade/real trade: `false`
- old system touched: `false`

## Next Gate

Allowed next gate:

```text
N4_FULL_SEMANTIC_REPAIR_POST_REVIEW_GATE
```
