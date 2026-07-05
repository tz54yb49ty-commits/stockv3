# N4 FULL Semantic Repair Post Review

Result: **POST_REVIEW_PASS**

Layer role: `N4_trigger`

This gate was read-only except for generating this post-review artifact. It did
not execute N4, write business database rows, consume or update
outbox/inbox/checkpoint, start a worker, enter N5/N6, or touch old-system /
delivery / push / voice / mobile / sim / position / order / trade / real-trade
surfaces.

## Implementation Proof Summary

- `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.json` parses.
- implementation report result: `IMPLEMENTATION_PASS`.
- The old global FULL block is removed from future N4 trigger code paths:
  - no `full_semantics_blocked`
  - no `full_condition_matched_forbidden`
  - no `FULL_forbidden_by_default`
- New FULL semantic guard is present:
  - matcher uses `_evaluate_full`.
  - enforcement uses `_full_condition_violations`.
  - corrected dry-run reports `FULL semantic blocked`.
  - execute contract uses `full_semantic_contract_guard`.
- Targeted tests: `62 OK` with `PYTHONPATH=src:scripts`.
- `check_n4_contract.py`: PASS, `finding_count=0`.
- implementation report JSON parse: PASS.
- `git diff --check`: PASS.
- The exact `PYTHONPATH=src` test command failure noted in the implementation
  report is only a script runner import-path issue for
  `run_n4_trigger_rule_v4_execute_once.py`; the same requested tests pass with
  `PYTHONPATH=src:scripts`.

## FULL Semantic Proof

`BUY:FULL` can become a legal `TriggerMatched` only when all are true:

- N2-localized context has `condition_key=BUY:FULL`.
- `original_condition_key=BUY:FULL`.
- `direction=buy`.
- D current transition is `volume_up`.
- D `transition_amount_pass=true`.
- D `trigger_amount_chain_pass=true`.
- `trigger_price` is non-null and traceable to reviewed N3 evidence.

`SELL:FULL` can become a legal `TriggerMatched` only when all are true:

- N2-localized context has `condition_key=SELL:FULL`.
- `original_condition_key=SELL:FULL`.
- `direction=sell`.
- D current transition is `low_volume_down`.
- D `transition_amount_pass=true`.
- D `trigger_amount_chain_pass=true`.
- `trigger_price` is non-null and traceable to reviewed N3 evidence.

Legal FULL `TriggerMatched` output is frozen to:

- `signal_type=B_BUY / S_SELL`
- `trigger_kind=trigger`
- `trigger_period=D`
- `triggered_periods=["D"]`
- `all_trigger_periods=["D"]`
- `primary_trigger_period=D`
- `trigger_mark_candidate=normal`
- `projection_30m_flag=false`
- `projection_30m_type=none`
- `n5_entry_allowed=true`
- `trigger_live=true`
- `current_status=matched`

## Negative Guard Proof

The implementation still blocks:

- FULL `trigger_period=30m`.
- FULL `triggered_periods/all_trigger_periods/primary_trigger_period`
  containing `30m`.
- FULL `trigger_kind=hint`.
- FULL `trigger_mark_candidate=30m_volume/30m_shrink`.
- FULL missing reviewed `trigger_price`.
- FULL without matching N2-localized `condition_key/original_condition_key`
  proof.
- ordinary BUY/SELL rows being reinterpreted by N4 as FULL.

## Regression Proof

- ordinary BUY/SELL rule tests remain green.
- `BUY_HINT / SELL_HINT` 30m rule tests remain green.
- runtime `signal_type` remains restricted to `B_BUY / S_SELL`.
- N5 action confirmation rules are unchanged.
- N6/user policy is unchanged.
- N4 still does not pull market data.
- N4 still does not write action/user/sim facts.

## Baseline Proof

Live DB read-only checks confirm the 20260608 context still contains the FULL
rows expected by the contract:

- stock `BUY:FULL`: `47`
- stock `SELL:FULL`: `35`
- board `SELL:FULL`: `4`
- total FULL rows: `86`

The `N4_FULL_SEMANTIC_REPAIR_POST_REVIEW_GATE` scoped DB refs are all zero:

- `common_trigger_run=0`
- `common_trigger_state=0`
- `common_trigger_match=0`
- `common_event_outbox=0`
- `common_event_inbox=0`
- `common_event_consumer_checkpoint=0`
- `common_action_run=0`
- `common_action_event=0`
- N6/user/sim scoped refs: `0`

No N4 matcher retry, N5/N6 execute, or worker was run in this gate.

## Forbidden Scope Proof

- N4 matcher execute: `false`
- DB business write: `false`
- rollback executed: `false`
- N3/N4/N5 outbox/inbox/checkpoint consumed or updated: `false`
- N5 entered: `false`
- N6 entered: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/pnl/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Decision

`POST_REVIEW_PASS`

Allowed next gate:

```text
N4_PROJECTION_MATCHER_20260608_UNTIL_1500_FULL_REPAIR_RETRY_REGENERATION_GATE
```
