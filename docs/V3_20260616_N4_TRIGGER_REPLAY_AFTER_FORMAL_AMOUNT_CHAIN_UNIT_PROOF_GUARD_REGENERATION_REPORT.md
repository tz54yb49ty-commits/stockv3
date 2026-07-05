# V3 20260616 N4 Trigger Replay After Formal Amount Chain Unit Proof Guard Regeneration Report

## Result

REGENERATION_PASS

## Scope

- layer_role: N4_trigger
- target run: `v3_n4_trigger_replay_20260616_until_1401_v1`
- trigger context run: `trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- projection run: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- trade_date: `20260616`

This gate regenerated dry-run, dry-run preflight, contract, final preflight, and rollback artifacts only. N4 replay was not executed.

## Refreshed Artifacts

- `docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN.md`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN.json`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN_PREFLIGHT.md`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN_PREFLIGHT.json`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_CONTRACT.md`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_CONTRACT.json`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_PREFLIGHT.md`
- `docs/V3_20260616_N4_TRIGGER_REPLAY_PREFLIGHT.json`
- `sql/V3_20260616_n4_trigger_replay_rollback.sql`

## Planned Row Counts

- candidates: `4698`
- `TriggerMatched`: `159`
- `TriggerPendingMarketData`: `4539`
- `TriggerStateChanged`: `0`
- planned `common_trigger_state`: `4698`
- planned `common_trigger_match`: `159`
- planned `common_event_outbox`: `4698`

By legacy signal:

- matched `BUY_HINT`: `3`
- matched `SELL_HINT`: `156`
- matched ordinary `B_BUY`: `0`
- matched ordinary `S_SELL`: `0`
- pending ordinary `B_BUY`: `2032`
- pending ordinary `S_SELL`: `2032`

Quality:

- P0/P1/P2: `0/1/0`
- P1 is the expected pending-candidate visibility advisory.

## Unit Proof Guard Proof

N4 ordinary formal BUY/SELL/FULL now accepts formal amount-chain proof only when all canonical proof fields are present:

- `unit_conversion_policy=formal_amount_chain_thousand_yuan_to_yuan_v1`
- `amount_unit=yuan`
- `amount_rule=attachment_dwmqy_avg_chain`

Regenerated dry-run outcome confirms the guard is active:

- ordinary `B_BUY` matched: `0`
- ordinary `S_SELL` matched: `0`
- ordinary pending due to missing formal proof / unit proof path: included under `formal_trigger_period_proof_missing=1268`
- sample pending plans include `formal_amount_chain_unit_proof_missing_or_invalid`

## Pending Non-Entry Proof

Contract/final preflight planned writes:

- `common_trigger_match=159`
- `TriggerMatched=159`
- `TriggerPendingMarketData=4539`

Therefore `common_trigger_match` equals `TriggerMatched` only. Pending rows are planned as state/outbox only and are not N5 action entries.

## HINT Unaffected Proof

BUY_HINT / SELL_HINT calibrated 30m path remains active:

- matched `BUY_HINT=3`
- matched `SELL_HINT=156`
- `trigger_mark_candidate` matched distribution:
  - `30m_volume=3`
  - `30m_shrink=156`

The formal unit proof guard does not apply to HINT 30m projection evaluation.

## Target Baseline Proof

Live target baseline after rollback and before execute remains zero:

- `common_trigger_run=0`
- `common_trigger_state=0`
- `common_trigger_match=0`
- `common_trigger_quality_item=0`
- `common_event_outbox=0`
- downstream inbox refs `0`
- downstream checkpoint refs `0`

## Rollback Proof

Rollback SQL was regenerated at:

- `sql/V3_20260616_n4_trigger_replay_rollback.sql`

Static checks:

- scoped target run id present
- hard-fail setting guard present before mutation
- delivered/delivering guard present
- N5/N6/downstream refs guards present
- no `DROP`
- no `TRUNCATE`
- no `CASCADE`

## Validation

- `PYTHONPATH=src:scripts python3 scripts/plan_trigger_action_confirmation_metric_dry_run.py ...`: PASS
- `PYTHONPATH=src:scripts python3 scripts/run_trigger_action_confirmation_metric_once.py ... --json`: PASS, final preflight `PREFLIGHT_PASS`
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher tests.test_trigger_action_confirmation_metric_execute tests.test_n4_v4_enforcement`: PASS, 84 tests OK
- `python3 -m compileall src/ashare_v3/trigger tests/test_trigger_action_confirmation_metric_matcher.py tests/test_trigger_action_confirmation_metric_execute.py tests/test_n4_v4_enforcement.py`: PASS
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: PASS
- JSON parse for refreshed artifacts: PASS
- rollback static check: PASS
- live target baseline proof: PASS
- `git diff --check`: PASS

## Forbidden Scope Proof

- N4 replay was not executed.
- No database business rows were written by this regeneration gate.
- No outbox/inbox/checkpoint was consumed or updated.
- No scheduler/worker was started.
- N5/N6 were not entered.
- No voice/mobile/sim/position/order/real trade path was touched.

## Next Gate

`V3_20260616_N4_TRIGGER_REPLAY_AFTER_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_FINAL_GATE_REVIEW_GATE`
