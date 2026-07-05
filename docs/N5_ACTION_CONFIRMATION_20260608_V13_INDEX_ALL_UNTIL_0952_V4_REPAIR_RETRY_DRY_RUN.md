# N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_DRY_RUN Action Consumer Run-Once Dry-Run Report

## Summary

- stage: N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_DRY_RUN
- layer_role: N5_action
- consumer_name: n5_action_consumer_v1
- source_trigger_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
- action_run_id: action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
- for_trade_date: 20260608
- rollback_sql_path: sql/N5_action_confirmation_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql
- P0/P1/P2: 1/0/0
- passed: False

## Source Run Guard

- configured: True
- passed: True
- allowed_source_run_ids: ['trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry']
- denied_source_run_ids: []
- denied_observed_source_run_ids: []
- outside_allowlist_source_run_ids: []

## Baseline Check

- baseline_report_path: docs/N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_READINESS.json
- baseline_available: False
- explainable: False
- current_read_event_count: None
- baseline_read_event_count: None
- read_event_count_delta: None
- explanation: baseline report is not available

## N4 Outbox Statistics

- outbox_row_count: 3920
- source_run_id: {'trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry': 3920}
- only_expected_source_run_id: True
- unexpected_source_run_id_count: 0
- by_event_type: {'TriggerMatched': 119, 'TriggerPendingMarketData': 3801}
- by_signal_type: {'B_BUY': 2116, 'S_SELL': 1804}
- by_asset_kind: {'board': 267, 'index': 163, 'stock': 3490}
- by_direction: {'buy': 2116, 'sell': 1804}
- TriggerMatched: 119
- TriggerPendingMarketData: 3801
- TriggerCleared: 0
- BUY_HINT runtime signal matched/pending/total: 0/0/0
- SELL_HINT runtime signal matched/pending/total: 0/0/0
- BUY_HINT trace matched/pending/total: 116/9/125
- SELL_HINT trace matched/pending/total: 3/4/7

## Period Trigger Baseline Trace

- present_count: 3920
- missing_count: 0
- null_count: 0
- empty_object_count: 0
- present_flag_true_count: 3920
- present_flag_false_count: 0
- required_period_not_ready_count: 0
- by_trigger_period: {'30m': 3920}
- present_by_trigger_period: {'30m': 3920}
- missing_by_trigger_period: {}
- baseline_versions: {'N2-R4-period-trigger-baseline-v1': 3920}

## Consumer Plan

- read_event_count: 3920
- planned_receive_count: 3920
- skipped_count: 0
- ordering: ['partition_key', 'event_time', 'outbox_id', 'event_id']
- partition_count: 1997
- checkpoint_write_plan_count: 1997
- would_insert_inbox_count: 3920
- would_update_checkpoint_count: 1997
- would_consume_outbox_count: 0

## Action Write Plan

- candidate_count: 3920
- action_candidate_count: 119
- quality_plan_count: 3801
- planned_action_fact_count: 119
- quality_plan_only_count: 3801
- by_target_action_fact_table: {'index_action_fact': 6, 'stock_action_fact': 113}
- planned_action_fact_by_signal_type: {'B_BUY': 116, 'S_SELL': 3}
- planned_action_fact_by_direction: {'buy': 116, 'sell': 3}
- action_state: {'blocked': 3801, 'eligible': 119}
- confirmation_status: {'pending': 3920}
- BUY_HINT planned action fact count: 116
- SELL_HINT planned action fact count: 3
- BUY_HINT trace count: 125
- SELL_HINT trace count: 7
- deprecated_runtime_signal_type_count: 0
- deprecated_hint_event_plan_count: 0
- pending_action_fact_plan_count: 0
- duplicate_source_trigger_match_id_skipped_count: 0
- duplicate_source_trigger_match_id_planned_count: 0
- physical_split_error_count: 0

## N5 Output Event Plan

- event_type_contract: ['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']
- by_event_type: {'ActionEligible': 119, 'ActionBlocked': 0, 'ActionExecuted': 0, 'ActionSkipped': 0}
- planned_event_count: 119
- common_event_outbox_written: False
- executed_count: 0

## Row Count Guards

- before_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 194811, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 92517, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 3191, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 9, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 32316, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 15360, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 120, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1114, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 16594, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}
- after_row_counts: {'common_event_outbox': {'exists': True, 'row_count': 194811, 'status': 'present'}, 'common_event_inbox': {'exists': True, 'row_count': 92517, 'status': 'present'}, 'common_event_consumer_checkpoint': {'exists': True, 'row_count': 3191, 'status': 'present'}, 'common_action_run': {'exists': True, 'row_count': 9, 'status': 'present'}, 'common_action_quality_item': {'exists': True, 'row_count': 32316, 'status': 'present'}, 'stock_action_fact': {'exists': True, 'row_count': 15360, 'status': 'present'}, 'index_action_fact': {'exists': True, 'row_count': 120, 'status': 'present'}, 'board_action_fact': {'exists': True, 'row_count': 1114, 'status': 'present'}, 'common_action_event': {'exists': True, 'row_count': 16594, 'status': 'present'}, 'common_position_state': {'exists': True, 'row_count': 0, 'status': 'present'}, 'common_position_event': {'exists': True, 'row_count': 0, 'status': 'present'}}

## Boundary Confirmation

- writes_performed: False
- common_event_inbox_updated: False
- consumer_checkpoint_updated: False
- action_fact_written: False
- action_event_written: False
- common_event_outbox_written: False
- n5_outbox_written: False
- n4_outbox_consumed: False
- market_data_pulled: False
- n1_n2_n3_n4_modified: False
- n6_user_layer_touched: False
- voice_touched: False
- sim_touched: False
- mobile_touched: False
- real_trade_touched: False
- worker_started: False
- old_system_touched: False

## Notes

- This report is a run-once dry-run only. It plans action writes but executes none of them.
- Canonical mode accepts only B_BUY / S_SELL as runtime signal_type.
- BUY_HINT / SELL_HINT are condition trace only and do not map to HintEvent in N5 canonical runtime.
- Source-run allowlist and historical synthetic/current-real denylist are enforced by this gate.

## Runtime Control Regeneration Summary

{
  "regeneration_result": "REGENERATION_PASS",
  "P0_P1_P2": {
    "P0": 0,
    "P1": 0,
    "P2": 0
  },
  "hint_30m_passthrough_proof": {
    "all_119_actionable_trigger_matched_are_legal_hint": true,
    "TriggerMatched_pending": 119,
    "TriggerPendingMarketData_pending": 3801,
    "BUY_HINT": 116,
    "SELL_HINT": 3,
    "trigger_period_30m": 119,
    "triggered_periods_empty": 119,
    "all_trigger_periods_empty": 119,
    "primary_trigger_period_null_in_source": 119,
    "trigger_price_present": 119,
    "n5_entry_allowed_true": 119,
    "candidate_primary_trigger_period_null": 119,
    "action_write_plan_primary_trigger_period_null": 119,
    "build_n5_action_event_legal_hint_passthrough_errors": [],
    "build_n5_action_event_legal_hint_passthrough_pass_count": 119,
    "ordinary_trigger_kind_trigger_period_30m_count": 0,
    "formal_period_fields_contain_30m_count": 0,
    "sample": {
      "candidate": {
        "source_trigger_event_id": "evt_84ee09ba1e27795e1eb11c524a0bf5eaeae6c189",
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "trigger_kind": "hint",
        "trigger_period": "30m",
        "triggered_periods": null,
        "all_trigger_periods": null,
        "primary_trigger_period": null,
        "trigger_price": "3988.778",
        "n5_entry_allowed": null
      },
      "action_write_plan": {
        "source_trigger_event_id": "evt_84ee09ba1e27795e1eb11c524a0bf5eaeae6c189",
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "trigger_kind": "hint",
        "trigger_period": "30m",
        "primary_trigger_period": null,
        "trigger_price": "3988.778",
        "planned_output_event_type": "ActionEligible",
        "target_action_fact_table": "index_action_fact"
      },
      "passthrough_payload_before_envelope_enrichment": {
        "condition_key": null,
        "original_condition_key": null,
        "trigger_kind": "hint",
        "trigger_period": "30m",
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": null,
        "trigger_price": "3988.778",
        "n5_entry_allowed": null,
        "baseline_source": "condition_basis"
      },
      "enriched_event_payload": {
        "condition_key": "BUY_HINT",
        "original_condition_key": "BUY_HINT",
        "trigger_kind": "hint",
        "trigger_period": "30m",
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": null,
        "trigger_price": "3988.778",
        "n5_entry_allowed": null,
        "baseline_source": "condition_basis",
        "event_schema_version": "v1"
      }
    }
  },
  "planned_n5_scope": {
    "readable_n4_events": 3920,
    "actionable_trigger_matched": 119,
    "trigger_pending_market_data_quality_only_noop": 3801,
    "expected_ActionEligible": 119,
    "expected_ActionBlocked": 0,
    "expected_ActionExecuted": 0,
    "expected_ActionSkipped": 0,
    "expected_action_facts": {
      "stock": 113,
      "index": 6,
      "board": 0
    },
    "expected_common_action_quality_item": 3801,
    "expected_common_action_event": 119,
    "expected_N5_outbox": 119,
    "expected_N5_inbox": 3920,
    "expected_N5_checkpoint": 1997,
    "common_position_state": 0,
    "common_position_event": 0,
    "N6_rows": 0,
    "quality_only_event_distribution": {
      "TriggerPendingMarketData": 3801
    }
  },
  "allow_enter_execute_user_confirmation_gate": true
}
