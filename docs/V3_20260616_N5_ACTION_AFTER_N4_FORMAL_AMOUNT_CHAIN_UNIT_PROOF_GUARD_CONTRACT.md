# V3 20260616 N5 Action After N4 Formal Amount Chain Unit Proof Guard Contract

Result: `CONTRACT_PASS`

Generated at: `2026-06-17 02:42:25 +0800`

## Scope

- layer_role: `N5_action`
- source N4 run: `v3_n4_trigger_replay_20260616_until_1401_v1`
- action_run_id: `v3_n5_action_replay_20260616_after_n4_formal_amount_chain_unit_proof_guard_v1`
- consumer_name: `n5_action_consumer_v1_20260616_formal_amount_chain_unit_proof_guard_replay`
- metric_run_id: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- execute_authorized: `false`

## Source N4 Proof

```text
common_trigger_run.status = passed
P0/P1/P2 = 0/1/0
common_trigger_state = 4698
common_trigger_match = 159
N4 outbox = 4698 pending=4698 delivered/delivering=0/0
TriggerMatched = 159
TriggerPendingMarketData = 4539
TriggerStateChanged = 0
```

TriggerMatched input composition:

```text
BUY_HINT = 3
SELL_HINT = 156
stock/index/board = 131/9/19
trigger_mark_candidate 30m_volume/30m_shrink = 3/156
```

## N5 Entry Contract

```text
execute scope event_type = TriggerMatched
expected_read_event_count = 159
TriggerPendingMarketData non-entry = 4539
pending creates action fact/event = false/false
N5 does not infer triggered_periods from condition_key/original_condition_key/required_periods
final action_mark source = N3 calibrated action-confirmation metric only
```

## Metric Join Proof

```text
coverage = 159/159
metric_missing = 0
stock/index/board joined = 131/9/19
N3 metric rows stock/index/board = 564/17/53
opaque payload.action_confirmation trusted = false
raw K read = false
market data pulled = false
```

## Planned Writes

```text
common_action_run = 1
common_action_quality_item = 0
stock/index/board_action_fact = 131/9/19
common_action_event = 159
common_event_outbox = 159
common_event_inbox = 159
common_event_consumer_checkpoint = 159
common_position_state/event = 0/0
```

## Planned Event Distribution

```text
ActionExecuted = 7
ActionBlocked = 152
ActionEligible = 0
ActionSkipped = 0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent = 0/0/0/0
```

Blocked reason distribution:

```text
price_confirmation_failed = 118
amount_confirmation_failed = 34
metric_missing = 0
```

## Baseline Proof

```text
target common_action_run/action_event/N5 outbox = 0/0/0
target consumer N4 inbox/checkpoint = 0/0
N6/user/position refs = 0
```

## Consumer Strategy Proof

```text
uses_dedicated_consumer = true
dedicated_consumer_name = n5_action_consumer_v1_20260616_formal_amount_chain_unit_proof_guard_replay
source_trigger_run_id = v3_n4_trigger_replay_20260616_until_1401_v1
metric_run_id = action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1
live baseline inbox/checkpoint = 0/0
baseline_dedicated_consumer_declared = true
```

## Rollback Proof

Rollback SQL: `sql/V3_20260616_n5_action_after_n4_formal_amount_chain_unit_proof_guard_rollback.sql`

- scoped to the new N5 action run and dedicated consumer
- hard-fail before first DELETE/UPDATE
- guards N5 delivered/delivering and downstream refs
- guards N6/user/sim/voice/mobile/position refs
- does not delete N4/N3 facts
- does not update N4 outbox status
- does not delete other consumer checkpoint rows

## Quality

```text
P0/P1/P2 = 0/0/0
```

## Forbidden Scope Proof

```text
n5_execute_performed = false
database_business_write_performed = false
n4_outbox_consumed_or_updated = false
inbox_checkpoint_updated = false
n6_entered = false
scheduler_worker_started = false
voice_mobile_sim_position_order_real_trade_touched = false
old_system_touched = false
```

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py --source-trigger-run-id v3_n4_trigger_replay_20260616_until_1401_v1 --action-run-id v3_n5_action_replay_20260616_after_n4_formal_amount_chain_unit_proof_guard_v1 --consumer-name n5_action_consumer_v1_20260616_formal_amount_chain_unit_proof_guard_replay --baseline-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_CONTRACT.json --expected-read-event-count 159 --allow-source-run-id v3_n4_trigger_replay_20260616_until_1401_v1 --source-event-type TriggerMatched --json-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_EXECUTE_REPORT.json --markdown-report-path docs/V3_20260616_N5_ACTION_AFTER_N4_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_EXECUTE_REPORT.md --rollback-sql-path sql/V3_20260616_n5_action_after_n4_formal_amount_chain_unit_proof_guard_rollback.sql --execute --user-confirmed
```
