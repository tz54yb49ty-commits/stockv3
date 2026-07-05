# N5 Trigger Fact Payload Historical Repair

Status: REPAIR_PASS

Layer role: N5_action

Generated at: 2026-06-06T05:35:45.723441+00:00

## Scope

```text
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

This repair updated only:

```text
common_action_event.payload_json
common_event_outbox.payload_json where source_layer=N5_action and source_run_id=action_run_id
```

It did not change N4 facts, N3/N2 facts, N6 projection/card, outbox status, inbox/checkpoint, delivery, push, voice, mobile, sim, position, pnl, proposal, order, real trade, or worker state.

## Updated Rows

```text
common_action_event=605
common_event_outbox_n5=605
```

## Payload Coverage After Repair

```text
rows=605
common_action_event trigger_price=605/605
common_action_event triggered_periods=605/605
common_action_event all_trigger_periods=605/605
common_action_event primary_trigger_period=605/605
common_action_event trigger_kind=605/605
common_action_event period_trigger_baseline_trace=605/605
common_action_event baseline_source=605/605
N5 outbox trigger_price=605/605
N5 outbox triggered_periods=605/605
N5 outbox all_trigger_periods=605/605
N5 outbox primary_trigger_period=605/605
N5 outbox trigger_kind=605/605
N5 outbox period_trigger_baseline_trace=605/605
N5 outbox baseline_source=605/605
```

## Mismatch Proof

```text
mismatch_vs_n4_match_price_period=0
mismatch_vs_n4_payload_price_period=0
mismatch_triggered_periods=0
mismatch_all_trigger_periods=0
mismatch_primary_period=0
```

## Sample Proof

```text
source_trigger_event_id=evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16
asset=stock / stock:SH:688690
action_payload_trigger_price=43.73
action_payload_triggered_periods=['D']
action_payload_all_trigger_periods=['D']
action_payload_primary_trigger_period=D
action_payload_trigger_kind=trigger
action_payload_baseline_source=trigger_baseline
outbox_payload_trigger_price=43.73
outbox_payload_triggered_periods=['D']
outbox_payload_baseline_source=trigger_baseline
```

## Boundary Scan

```text
N4 before=[{'table_name': 'common_event_outbox_n4', 'row_count': 605}, {'table_name': 'common_trigger_match', 'row_count': 605}]
N4 after=[{'table_name': 'common_event_outbox_n4', 'row_count': 605}, {'table_name': 'common_trigger_match', 'row_count': 605}]
N5 outbox status after=[{'event_type': 'ActionBlocked', 'status': 'pending', 'row_count': 604}, {'event_type': 'ActionExecuted', 'status': 'pending', 'row_count': 1}]
N5 event downstream refs after=[{'name': 'common_event_consumer_checkpoint_n5_downstream', 'row_count': 0}, {'name': 'common_event_delivery_attempt', 'row_count': 0}, {'name': 'common_event_inbox_n5_downstream', 'row_count': 0}]
N6/user/position refs after=[{'table': 'user_projection_run', 'row_count': 1}, {'table': 'user_signal_projection', 'row_count': 605}, {'table': 'user_signal_decision', 'row_count': 0}, {'table': 'user_notification_queue', 'row_count': 0}, {'table': 'user_signal_card', 'row_count': 605}, {'table': 'user_sim_account', 'row_count': 0}, {'table': 'user_sim_order', 'row_count': 0}, {'table': 'user_sim_trade', 'row_count': 0}, {'table': 'user_sim_position', 'row_count': 0}, {'table': 'common_position_state', 'row_count': 0}, {'table': 'common_position_event', 'row_count': 0}, {'table': 'n6_virtual_account', 'row_count': 0}, {'table': 'n6_virtual_order', 'row_count': 0}, {'table': 'n6_virtual_trade', 'row_count': 0}, {'table': 'n6_virtual_position', 'row_count': 0}, {'table': 'n6_virtual_position_event', 'row_count': 0}, {'table': 'n6_virtual_pnl_snapshot', 'row_count': 0}]
```

N6 projection/card refs are present and intentionally not repaired here. They require a separately authorized N6 projection/card repair gate.

## Rollback

```text
rollback_sql=sql/N5_trigger_fact_payload_historical_repair_20260605_rollback.sql
rollback_scope=N5 payload keys only
hard_fail_before_update=true
no_row_delete=true
no_N4_N3_N2_N6_mutation=true
```

## Validation

```text
JSON parse: passed
  python3 -m json.tool docs/N5_TRIGGER_FACT_PAYLOAD_HISTORICAL_REPAIR.json

compileall: passed
  python3 -m compileall scripts src tests

regression tests: passed
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_execute.py'
  Ran 21 tests

  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_event_contract.py'
  Ran 5 tests

  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action*.py'
  Ran 70 tests

rollback static check: passed
  method=statement scan after stripping SQL comments
  hard_fail_before_first_update=true
  no_delete_statement=true
  no_insert_statement=true
  no_truncate_statement=true
  updates_only=common_action_event, common_event_outbox
  no_common_trigger_mutation=true
  no_user_or_n6_mutation=true

git diff --check: run after this report update
```
