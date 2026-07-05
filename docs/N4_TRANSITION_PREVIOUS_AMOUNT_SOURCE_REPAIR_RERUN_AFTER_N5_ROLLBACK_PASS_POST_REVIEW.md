# N4 Transition Previous Amount Source Repair Rerun Post Review

- result: PASS
- new_execute_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback_result: ROLLED_BACK `trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- TriggerMatched: 491
- TriggerPendingMarketData: 3835
- TriggerStateChanged: 0
- Y triggered count: match=0, state=0
- always_true_for_Y count: state=0, match=0, outbox=0
- HINT match count: 29, ordinary period pollution: state=0, match=0
- pending no-match count: pending=3835, pending_join_match=0
- rollback SQL: `sql/N4_transition_previous_amount_source_repair_rerun_rollback.sql`

## Sample Proofs
### stock_SZ_301611_BUY_M_W_D
```json
{
  "identity_key": "stock:SZ:301611",
  "condition_key": "BUY:M,W,D",
  "trigger_state_id": 1211680,
  "current_status": "matched",
  "trigger_live": true,
  "primary_trigger_period": "M",
  "all_trigger_periods": [
    "M",
    "W",
    "D"
  ],
  "last_trigger_match_id": 335911,
  "plan_status": "would_trigger",
  "output_event_type": "TriggerMatched",
  "triggered_periods": [
    "M",
    "W",
    "D"
  ],
  "n5_entry_allowed": true,
  "is_n5_action_entry": true,
  "period_details": {
    "M": {
      "period": "M",
      "status": "triggered",
      "price_pass": true,
      "amount_pass": true,
      "previous_transition": "low_volume_up",
      "current_transition": "volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": true,
      "transition_amount_pass": true,
      "transition_amount_fields": [
        "monthly_avg_with_today",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "monthly_avg_with_today": "1857514491.2569902",
        "n2_previous_amount_yuan": "1843735462.896666667000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "1843735.462896666667",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": true,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "monthly_avg_with_today",
        "quarterly_avg_with_today",
        "prev_quarterly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_quarterly_avg": "1362073966.0535712",
        "monthly_avg_with_today": "1857514491.2569902",
        "quarterly_avg_with_today": "1651204933.9323244"
      },
      "operator_chain": ">=",
      "reason": null
    },
    "W": {
      "period": "W",
      "status": "triggered",
      "price_pass": true,
      "amount_pass": true,
      "previous_transition": "low_volume_up",
      "current_transition": "volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": true,
      "transition_amount_pass": true,
      "transition_amount_fields": [
        "weekly_avg_with_today",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "weekly_avg_with_today": "2034987963.0636244",
        "n2_previous_amount_yuan": "2011713272.55000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "2011713.27255",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": true,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "weekly_avg_with_today",
        "monthly_avg_with_today",
        "prev_monthly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_monthly_avg": "1843735462.8966668",
        "weekly_avg_with_today": "2034987963.0636244",
        "monthly_avg_with_today": "1857514491.2569902"
      },
      "operator_chain": ">=",
      "reason": null
    },
    "D": {
      "period": "D",
      "status": "triggered",
      "price_pass": true,
      "amount_pass": true,
      "previous_transition": "low_volume_down",
      "current_transition": "volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": true,
      "transition_amount_pass": true,
      "transition_amount_fields": [
        "today_virt_amount",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "today_virt_amount": "2222464879.640873",
        "n2_previous_amount_yuan": "2120832269.27000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "2120832.26927",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": true,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "today_virt_amount",
        "weekly_avg_with_today",
        "prev_weekly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_weekly_avg": "2011713272.5500002",
        "today_virt_amount": "2222464879.640873",
        "weekly_avg_with_today": "2034987963.0636244"
      },
      "operator_chain": ">=",
      "reason": null
    }
  }
}
```
### stock_SZ_300684_BUY_M_D
```json
{
  "identity_key": "stock:SZ:300684",
  "condition_key": "BUY:M,D",
  "trigger_state_id": 1211304,
  "current_status": "pending_market_data",
  "trigger_live": false,
  "primary_trigger_period": null,
  "all_trigger_periods": [],
  "last_trigger_match_id": null,
  "plan_status": "would_pending",
  "output_event_type": "TriggerPendingMarketData",
  "triggered_periods": [],
  "n5_entry_allowed": false,
  "is_n5_action_entry": false,
  "period_details": {
    "M": {
      "period": "M",
      "status": "not_triggered",
      "price_pass": true,
      "amount_pass": false,
      "previous_transition": "low_volume_up",
      "current_transition": "low_volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": false,
      "transition_amount_pass": false,
      "transition_amount_fields": [
        "monthly_avg_with_today",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "monthly_avg_with_today": "904695410.947954",
        "n2_previous_amount_yuan": "1006479660.574444444000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "1006479.660574444444",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": true,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "monthly_avg_with_today",
        "quarterly_avg_with_today",
        "prev_quarterly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_quarterly_avg": "693802524.2321428",
        "monthly_avg_with_today": "904695410.947954",
        "quarterly_avg_with_today": "856835757.5319886"
      },
      "operator_chain": ">=",
      "reason": null
    },
    "D": {
      "period": "D",
      "status": "not_triggered",
      "price_pass": true,
      "amount_pass": false,
      "previous_transition": "low_volume_up",
      "current_transition": "low_volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": false,
      "transition_amount_pass": false,
      "transition_amount_fields": [
        "today_virt_amount",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "today_virt_amount": "545405086.4834027",
        "n2_previous_amount_yuan": "972043480.55000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "972043.48055",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": false,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "today_virt_amount",
        "weekly_avg_with_today",
        "prev_weekly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_weekly_avg": "797720056.046",
        "today_virt_amount": "545405086.4834027",
        "weekly_avg_with_today": "742834330.1778008"
      },
      "operator_chain": ">=",
      "reason": null
    }
  }
}
```
### stock_SZ_300687_BUY_Y_M_D
```json
{
  "identity_key": "stock:SZ:300687",
  "condition_key": "BUY:Y,M,D",
  "trigger_state_id": 1211306,
  "current_status": "pending_market_data",
  "trigger_live": false,
  "primary_trigger_period": null,
  "all_trigger_periods": [],
  "last_trigger_match_id": null,
  "plan_status": "would_pending",
  "output_event_type": "TriggerPendingMarketData",
  "triggered_periods": [],
  "n5_entry_allowed": false,
  "is_n5_action_entry": false,
  "period_details": {
    "Y": {
      "period": "Y",
      "status": "not_triggered",
      "price_pass": true,
      "amount_pass": false,
      "previous_transition": "low_volume_up",
      "current_transition": "low_volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": false,
      "transition_amount_pass": false,
      "transition_amount_fields": [
        "yearly_avg_with_today",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "yearly_avg_with_today": "483615927.84180576",
        "n2_previous_amount_yuan": "572064875.987654321000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "572064.875987654321",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": false,
      "trigger_amount_chain_status": "not_applicable",
      "trigger_amount_chain_fields": [],
      "trigger_amount_chain_values": {},
      "operator_chain": "no_upper_period_chain",
      "reason": "year_period_has_no_upper_amount_chain"
    },
    "M": {
      "period": "M",
      "status": "not_triggered",
      "price_pass": true,
      "amount_pass": false,
      "previous_transition": "low_volume_up",
      "current_transition": "low_volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": false,
      "transition_amount_pass": false,
      "transition_amount_fields": [
        "monthly_avg_with_today",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "monthly_avg_with_today": "514098733.61038643",
        "n2_previous_amount_yuan": "1068186249.887777778000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "1068186.249887777778",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": false,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "monthly_avg_with_today",
        "quarterly_avg_with_today",
        "prev_quarterly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_quarterly_avg": "360561206.91071427",
        "monthly_avg_with_today": "514098733.61038643",
        "quarterly_avg_with_today": "616136396.5368273"
      },
      "operator_chain": ">=",
      "reason": null
    },
    "D": {
      "period": "D",
      "status": "not_triggered",
      "price_pass": true,
      "amount_pass": false,
      "previous_transition": "low_volume_up",
      "current_transition": "low_volume_up",
      "target_transition": "volume_up",
      "transition_upgrade_pass": false,
      "transition_amount_pass": false,
      "transition_amount_fields": [
        "today_virt_amount",
        "n2_previous_amount_yuan"
      ],
      "transition_amount_values": {
        "today_virt_amount": "597599234.415023",
        "n2_previous_amount_yuan": "665564097.76000"
      },
      "transition_previous_amount_trace": {
        "source": "N2_period_trigger_baseline",
        "raw_value": "665564.09776",
        "source_unit": "thousand_yuan",
        "source_field": "previous_avg_amount",
        "unit_conversion_policy": "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1",
        "forbidden_fields_ignored": [
          "trigger_previous_amount_baseline",
          "current_amount_seed",
          "current_avg_amount_seed",
          "current_amount_total_seed"
        ]
      },
      "trigger_amount_chain_pass": false,
      "trigger_amount_chain_status": "passed",
      "trigger_amount_chain_fields": [
        "today_virt_amount",
        "weekly_avg_with_today",
        "prev_weekly_avg"
      ],
      "trigger_amount_chain_values": {
        "prev_weekly_avg": "459084901.64599997",
        "today_virt_amount": "597599234.415023",
        "weekly_avg_with_today": "597862926.258341"
      },
      "operator_chain": ">=",
      "reason": null
    }
  }
}
```

## Forbidden Scope
```json
{
  "common_trigger_run_flags": {
    "market_data_pulled": false,
    "action_layer_touched": false,
    "user_layer_touched": false,
    "voice_touched": false,
    "sim_touched": false,
    "real_trade_touched": false,
    "worker_started": false
  },
  "run_raw_json_flags": {
    "writes_outbox": true,
    "projection_run_id": "action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
    "consumes_n3_outbox": false,
    "canonical_runtime_spec": "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
    "source_snapshot_run_id": "realtime_daily_snapshot_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
    "trigger_context_run_id": "trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
    "source_subscription_run_id": "market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
    "writes_inbox_or_checkpoint": false,
    "action_confirmation_rule_spec": "docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md"
  },
  "old_system_touched": false,
  "outbox_consumed": false,
  "scheduler_worker_started": false,
  "n5_n6_entered": false
}
```

## Allowed Next Prompt
```text
layer_role=N5_action. Enter N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS. Use source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1; trade_date=20260617. Run N5 preflight first; do not enter N6; do not consume N5 outbox unless separately authorized.
```
