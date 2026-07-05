# N5 Market Action Confirmation Spec v1 Metric-Aware Dry-Run Preflight Gate Report

Result: `DRY_RUN_PASS`

- source N4 execute_run_id: `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- N3 action_metric_run_id: `action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- action_run_id: `action_consumer_market_action_confirmation_v1_metric_aware_dry_run_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- read_event_count: `863`
- metric rows: `822`
- metric join coverage: `863/863`
- output plan: `{'ActionEligible': 0, 'ActionBlocked': 863, 'ActionExecuted': 0, 'ActionSkipped': 0}`
- P0/P1/P2: `0/0/0`

Boundary: read-only metric-aware dry-run/preflight only; no N5 execute, no DB business write, no outbox/inbox/checkpoint consumption, no N6, no worker, no market-data pull, no user/voice/mobile/sim/position/real trade.

## Summary

- N4 TriggerMatched pending rows: `863`.
- N3 action-confirmation metric rows: `822`.
- Deterministic metric join: `863/863`, missing `0`.
- N5 does not use opaque `payload.action_confirmation`; payload count is `0`.
- ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped: `0/863/0/0`.
- Invalid user-layer blocked_reason count: `0`.
- Rollback SQL required for this gate: `False`.

## N4 Outbox Payload Read

```json
{
  "read_event_count": 863,
  "source_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
  "by_event_type": {
    "TriggerMatched": 863
  },
  "by_asset_kind": {
    "board": 149,
    "index": 34,
    "stock": 680
  },
  "by_signal_type": {
    "B_BUY": 682,
    "S_SELL": 181
  },
  "by_direction": {
    "buy": 682,
    "sell": 181
  },
  "pending_status": 863,
  "source_outbox_status_summary": {
    "source_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
    "by_event_type_and_status": [
      {
        "event_type": "TriggerMatched",
        "status": "pending",
        "row_count": 863
      }
    ],
    "by_event_type": {
      "TriggerMatched": 863
    },
    "by_status": {
      "pending": 863
    },
    "standard_event_status": {
      "pending": 863
    },
    "delivered": 0,
    "delivering": 0
  },
  "payload_metric_fields_before_enrichment": {
    "row_count": 863,
    "payload_has_action_confirmation": 0,
    "payload_has_source_action_confirmation_metric_id": 0,
    "payload_nonempty_source_action_confirmation_metric_id": 0
  },
  "payload_metric_fields_after_deterministic_enrichment": {
    "row_count": 863,
    "payload_has_action_confirmation": 0,
    "payload_has_source_action_confirmation_metric_id": 863,
    "payload_nonempty_source_action_confirmation_metric_id": 863
  }
}
```

## Metric Join Coverage

```json
{
  "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
  "join_key": [
    "asset_kind",
    "identity_key",
    "trade_date/for_trade_date",
    "action_metric_run_id"
  ],
  "n4_trigger_matched_rows": 863,
  "n3_metric_rows": 822,
  "joined_n4_rows": 863,
  "missing_metric_rows": 0,
  "coverage": "863/863",
  "unique_joined_metric_ids": 822,
  "expected": {
    "n4_trigger_matched_rows": 863,
    "joined_n4_rows": 863
  },
  "status": "passed",
  "by_asset_kind": {
    "board": {
      "n4_trigger_matched_rows": 149,
      "metric_rows": 148,
      "joined_n4_rows": 149,
      "missing_n4_rows": 0
    },
    "index": {
      "n4_trigger_matched_rows": 34,
      "metric_rows": 34,
      "joined_n4_rows": 34,
      "missing_n4_rows": 0
    },
    "stock": {
      "n4_trigger_matched_rows": 680,
      "metric_rows": 640,
      "joined_n4_rows": 680,
      "missing_n4_rows": 0
    }
  },
  "unique_join_keys": 822,
  "duplicate_join_key_count": 0,
  "duplicate_join_key_rows": 0,
  "duplicate_join_keys_sample": {},
  "missing_metric_sample": []
}
```

## Action Distribution

```json
{
  "planned_output_events": {
    "ActionEligible": 0,
    "ActionBlocked": 863,
    "ActionExecuted": 0,
    "ActionSkipped": 0
  },
  "planned_action_fact_count": 863,
  "skipped_count": 0,
  "skip_reasons": {},
  "by_action_state": {
    "blocked": 863
  },
  "by_confirmation_status": {
    "failed": 863
  },
  "by_asset_kind": {
    "board": 149,
    "index": 34,
    "stock": 680
  },
  "by_signal_type": {
    "B_BUY": 682,
    "S_SELL": 181
  },
  "by_target_action_fact_table": {
    "board_action_fact": 149,
    "index_action_fact": 34,
    "stock_action_fact": 680
  },
  "legacy_output_events": {
    "ActionEvent": 0,
    "HintEvent": 0,
    "RiskEvent": 0,
    "PositionEvent": 0
  }
}
```

## Four-Period Confirmation Distribution

```json
{
  "B_BUY": {
    "row_count": 682,
    "flags": {
      "buy_120m_price_pass": {
        "pass": 1,
        "fail": 681,
        "missing": 0
      },
      "buy_30m_price_pass": {
        "pass": 321,
        "fail": 361,
        "missing": 0
      },
      "buy_5m_price_pass": {
        "pass": 475,
        "fail": 207,
        "missing": 0
      },
      "buy_5m_amount_pass": {
        "pass": 289,
        "fail": 393,
        "missing": 0
      },
      "buy_1m_price_pass": {
        "pass": 482,
        "fail": 200,
        "missing": 0
      },
      "buy_1m_amount_pass": {
        "pass": 682,
        "fail": 0,
        "missing": 0
      }
    },
    "all_selected_flags_pass": 0,
    "any_price_failed": 682,
    "any_amount_failed": 393
  },
  "S_SELL": {
    "row_count": 181,
    "flags": {
      "sell_120m_price_pass": {
        "pass": 25,
        "fail": 156,
        "missing": 0
      },
      "sell_30m_price_pass": {
        "pass": 79,
        "fail": 102,
        "missing": 0
      },
      "sell_5m_price_pass": {
        "pass": 88,
        "fail": 93,
        "missing": 0
      },
      "sell_5m_amount_pass": {
        "pass": 99,
        "fail": 82,
        "missing": 0
      },
      "sell_1m_price_pass": {
        "pass": 102,
        "fail": 79,
        "missing": 0
      },
      "sell_1m_amount_pass": {
        "pass": 0,
        "fail": 181,
        "missing": 0
      }
    },
    "all_selected_flags_pass": 0,
    "any_price_failed": 156,
    "any_amount_failed": 181
  }
}
```

## First-Period Boundary Distribution

```json
{
  "by_joined_n4_row": {
    "1m": {
      "row_count": 863,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0,
      "amount_default_pass_rows": 0
    },
    "5m": {
      "row_count": 863,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0,
      "amount_default_pass_rows": 0
    },
    "30m": {
      "row_count": 863,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0
    },
    "120m": {
      "row_count": 863,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0
    }
  },
  "by_unique_metric_fact": {
    "1m": {
      "row_count": 822,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0,
      "amount_default_pass_rows": 0
    },
    "5m": {
      "row_count": 822,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0,
      "amount_default_pass_rows": 0
    },
    "30m": {
      "row_count": 822,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0
    },
    "120m": {
      "row_count": 822,
      "first_period_rows": 0,
      "previous_source_distribution_for_first_rows": {},
      "previous_source_not_available_rows": 0,
      "previous_source_previous_day_rows": 0
    }
  },
  "policy": {
    "first_1m_amount_default_pass_allowed": true,
    "first_5m_amount_default_pass_allowed": true,
    "price_confirmation_default_pass_allowed": false,
    "missing_previous_session_reference_blocks": true
  }
}
```

## Blocked Reason Distribution

```json
{
  "blocked_action_fact_rows": 863,
  "by_blocked_reason": {
    "amount_confirmation_failed": 25,
    "price_confirmation_failed": 838
  },
  "invalid_user_layer_blocked_reason_count": 0,
  "invalid_user_layer_blocked_reasons": {},
  "allowed_user_layer_reasons_forbidden_by_contract": [
    "no_position",
    "insufficient_cash",
    "t_plus_one_locked",
    "already_sold",
    "position_limit",
    "blacklist"
  ]
}
```

## Action Mark Final-Only Proof

```json
{
  "policy": "final action_mark is only allowed when action_state=executed and confirmation_status=passed",
  "planned_action_fact_count": 863,
  "final_action_mark_non_null_count": 0,
  "executed_rows": 0,
  "executed_with_final_action_mark_count": 0,
  "non_executed_rows": 863,
  "non_executed_with_final_action_mark_count": 0,
  "by_final_action_mark": {
    "null": 863
  },
  "proof_status": "passed"
}
```

## Boundary Proof

```json
{
  "read_only_database_connection": true,
  "execute_n5": false,
  "db_business_writes": false,
  "consume_outbox": false,
  "write_common_event_inbox": false,
  "write_common_event_consumer_checkpoint": false,
  "write_action_fact": false,
  "write_common_action_event": false,
  "write_common_event_outbox": false,
  "enter_n6": false,
  "worker_started": false,
  "market_data_pulled": false,
  "opaque_payload_action_confirmation_used": false,
  "user_voice_mobile_sim_position_real_trade_touched": false
}
```

## Quality

```json
{
  "p0_count": 0,
  "p1_count": 0,
  "p2_count": 0,
  "items": [
    {
      "severity": "P0",
      "code": "n5_v1_n4_trigger_matched_count",
      "status": "passed",
      "expected": 863,
      "actual": 863,
      "evidence": "Read pending TriggerMatched rows from current N4 v4 outbox in a readonly transaction."
    },
    {
      "severity": "P0",
      "code": "n5_v1_n3_action_metric_row_count",
      "status": "passed",
      "expected": 822,
      "actual": 822,
      "evidence": "Read N3 action-confirmation metric rows from stock/index/board physical tables for the supplied metric run id."
    },
    {
      "severity": "P0",
      "code": "n5_v1_metric_join_coverage",
      "status": "passed",
      "expected": {
        "n4_trigger_matched_rows": 863,
        "joined_n4_rows": 863
      },
      "actual": {
        "joined_n4_rows": 863,
        "missing_metric_rows": 0
      },
      "evidence": "Deterministic join uses asset_kind + identity_key + trade_date/for_trade_date + metric run id."
    },
    {
      "severity": "P0",
      "code": "n5_v1_metric_join_key_unique",
      "status": "passed",
      "expected": 0,
      "actual": 0,
      "evidence": "N3 metric rows must have one deterministic row per asset_kind/identity_key/trade_date for this metric run."
    },
    {
      "severity": "P0",
      "code": "n5_v1_opaque_payload_action_confirmation_not_used",
      "status": "passed",
      "expected": "not_used",
      "actual": {
        "payload_action_confirmation_count": 0,
        "planner_metric_source": "N3 metric facts joined deterministically"
      },
      "evidence": "This dry-run ignores opaque payload.action_confirmation and injects only N3 action-confirmation metric lineage."
    },
    {
      "severity": "P0",
      "code": "n5_v1_canonical_output_events_only",
      "status": "passed",
      "expected": 0,
      "actual": 0,
      "evidence": "Output event plan is restricted to ActionEligible/ActionBlocked/ActionExecuted/ActionSkipped."
    },
    {
      "severity": "P0",
      "code": "n5_v1_invalid_user_layer_blocked_reason_absent",
      "status": "passed",
      "expected": 0,
      "actual": 0,
      "evidence": "Blocked reasons are market/system facts only; user-layer reasons stay in N6."
    },
    {
      "severity": "P0",
      "code": "n5_v1_action_mark_final_only",
      "status": "passed",
      "expected": 0,
      "actual": 0,
      "evidence": "final action_mark is only allowed on executed/passed action facts."
    },
    {
      "severity": "P0",
      "code": "n5_v1_no_db_side_effects",
      "status": "passed",
      "expected": "no row-count delta",
      "actual": {
        "guard_delta_changed": 0,
        "scoped_delta_changed": 0
      },
      "evidence": "Before/after DB guard row counts were collected on a readonly connection."
    }
  ]
}
```

## Next Gate

```json
{
  "allow_n5_v1_contract_preflight_rollback_materialization_gate": true,
  "allow_n5_execute_final_gate": false,
  "reason": "This gate is dry-run/preflight only. A separate contract/preflight/rollback materialization gate is required before execute final gate."
}
```
