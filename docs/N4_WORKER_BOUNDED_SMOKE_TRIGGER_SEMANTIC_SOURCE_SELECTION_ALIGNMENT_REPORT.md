# N4 Worker Bounded Smoke Trigger Semantic Source Selection Alignment Report

Result: `ALIGNMENT_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_SOURCE_SELECTION_ALIGNMENT_GATE`

Layer role: `N4_trigger`

Generated date: `2026-06-10`

## Root Cause

The bounded worker semantic smoke runner loaded N3 source events before loading semantic oracle evaluations. In semantic oracle mode it therefore selected the first `max_events` pending `MarketSnapshotUpdated` rows from N3 outbox, while oracle evaluations referenced later N3 source events. The source/oracle intersection was `0`, so no transition plans were generated even though the oracle run contained valid `TriggerMatched` facts.

## Code Repair Summary

- `src/ashare_v3/trigger/worker_consumer.py`
  - Added ordered, bounded semantic source id extraction from oracle/fixture evaluations.
  - Added read-only N3 source event fetch by exact oracle-backed `source_event_id`.
  - Preserved deterministic source event order from the oracle evaluation list.
  - Blocked semantic smoke when oracle-referenced N3 events are not still pending inputs.
  - Added oracle previous-state replay support so oracle `TriggerMatched` smoke emits only `TriggerMatched`, not synthetic `TriggerStateChanged`.

- `scripts/run_n4_worker_bounded_smoke_once.py`
  - In semantic mode, loads semantic fixture/oracle inputs before selecting source events.
  - Fetches N3 source events by oracle-backed `source_event_id` instead of blind first-pending order.
  - Keeps non-semantic consumption-only selection unchanged.

- `tests/test_n4_worker_bounded_smoke.py`
  - Added ordered and bounded semantic source id tests.
  - Added semantic replay test proving `TriggerMatched=10` and `TriggerStateChanged=0`.
  - Added execute-path test proving semantic mode calls exact source-event selection and does not call the first-pending selector.

## Semantic Source Selection Proof

Read-only DB proof used:

- `smoke_run_id=n4_worker_bounded_smoke_20260608_trigger_semantic_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_semantic_probe`
- `semantic_oracle_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- `max_events=10`

Result:

- selected source events: `10`
- semantic evaluations: `10`
- source/oracle intersection: `10`
- selected N3 source events are still `pending`
- N3 outbox status was not updated
- oracle facts/outbox were read-only

First 10 selected source ids:

```text
evt_2c6d17c3212ed18a554016322fd6f3be65acf694
evt_4f95867151e052456add141f41b73a5f48a36ca1
evt_6fdb0181e1982e75907cf249c31395baa5511639
evt_3f6f7ebe1b52fe5e09454203ab1325c48fb995c7
evt_543c7251077674dfbe944af464edabeadf7ef8b2
evt_ddb7622143c848106446970b755e88668ea2f6a5
evt_6bb9a45d143a22e6fb6875f4ea910e0e497aee2e
evt_66bdbc52dc4df4e7e0b1576d8f22bfa3b81b8054
evt_af306736ed3d6f9e886855216752cd39decda4b8
evt_a0b7212023e1ce2022158dd00fd6d612b05b7ec6
```

## Dry-Run Expectation Proof

Using the repaired source selection and read-only oracle evaluations:

- accepted source events: `10`
- transition_event_plan_count: `10`
- `TriggerMatched=10`
- `TriggerPendingMarketData=0`
- `TriggerStateChanged=0`

Expected scoped smoke write plan:

- `common_trigger_run=1`
- `common_trigger_quality_item=2`
- `common_event_inbox=10`
- `common_event_consumer_checkpoint=10`
- `common_trigger_state=10`
- `common_trigger_match=10`
- `common_event_outbox=10`

## Baseline And Source Boundary Proof

Target semantic smoke baseline remained clean after this gate:

- `common_trigger_run=0`
- `common_trigger_quality_item=0`
- `common_trigger_state=0`
- `common_trigger_match=0`
- `common_event_outbox=0`
- `common_event_inbox=0`
- `common_event_consumer_checkpoint=0`

N3 source outbox status proof:

- `MarketSnapshotUpdated pending=2155`
- delivered/delivering rows were not updated by this gate
- no N3 facts were modified

## Regression Proof

- Non-semantic consumption-only path still uses first-pending bounded selection.
- Semantic oracle mode is bounded by `max_events`.
- Semantic fixture/oracle mode still requires `--semantic-smoke`.
- Missing semantic fixture/oracle still blocks before DB write.
- N3 outbox status update path remains absent.
- `TriggerPendingMarketData` and `TriggerStateChanged` still do not write `common_trigger_match`.
- `TriggerMatched` remains the only semantic plan that can write match rows and N5-entry payload.

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_smoke tests.test_n4_worker_state_transition`: `26 OK`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`: `128 OK`
- `python3 -m compileall src/ashare_v3/trigger scripts tests`: `PASS`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: `PASS`
- rollback static check: `PASS`
- live read-only DB proof: `PASS`

## Forbidden Scope Proof

- worker started: `false`
- smoke executed: `false`
- database written: `false`
- N3 outbox consumed/updated: `false`
- N5/N6 entered: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Next Gate

Allowed to return to runtime_control for:

`N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`
