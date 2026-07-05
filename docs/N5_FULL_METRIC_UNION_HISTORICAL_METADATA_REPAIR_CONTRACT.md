# N5 Full Metric Union Historical Metadata Repair Contract

Status: CONTRACT_PASS

## Contract Summary

```text
repair_type=historical_metadata_only
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
execute_authorized=false
metric_union_policy_version=n5.full_metric_union_historical_metadata_repair.v1
rollback_sql=sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql
```

The repair may only update payload metadata keys in `common_action_event.payload_json` and N5 `common_event_outbox.payload_json`.

It must not change event type, action state, confirmation status, action mark, event id, source ids, action_run_id, outbox status, delivery status, N4 payload, or N6 projection/card.

## Expected Old/New Comparison

```text
{
  "scoped_n5_action_rows": 605,
  "unchanged_action_status": 605,
  "changed_blocked_reason_rows": 289,
  "metric_missing_before": 289,
  "metric_missing_after": 0,
  "metric_missing_resolved_rows": 289,
  "price_confirmation_failed_before_after": [
    305,
    587
  ],
  "amount_confirmation_failed_before_after": [
    10,
    17
  ],
  "ActionExecuted_before_after": [
    1,
    1
  ],
  "ActionBlocked_before_after": [
    604,
    604
  ],
  "ActionSkipped_before_after": [
    0,
    0
  ],
  "ActionEligible_before_after": [
    0,
    0
  ],
  "event_type_changes": 0,
  "action_state_changes": 0,
  "confirmation_status_changes": 0,
  "action_mark_changes": 0,
  "old_blocked_reason_distribution": {
    "amount_confirmation_failed": 10,
    "metric_missing": 289,
    "price_confirmation_failed": 305
  },
  "new_blocked_reason_distribution": {
    "amount_confirmation_failed": 17,
    "price_confirmation_failed": 587
  },
  "sample_changed_blocked_reason": [
    {
      "source_trigger_event_id": "evt_8e7472d3bf7538bd0f45ae2bfe10b1cf560429fa",
      "common_action_event": {
        "action_event_row_id": 23050,
        "event_id": "evt_c125c176141d0598e0a3a4599015c3bc3786289e",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222976,
        "event_id": "evt_c125c176141d0598e0a3a4599015c3bc3786289e",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880202",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "304",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "304",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880202",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "304",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_8e7472d3bf7538bd0f45ae2bfe10b1cf560429fa",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_5aaf26c9038fcb291665dba304415ad97357406c",
      "common_action_event": {
        "action_event_row_id": 23051,
        "event_id": "evt_858857da7895c9a52674b80a9ad102d27c5eec18",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222977,
        "event_id": "evt_858857da7895c9a52674b80a9ad102d27c5eec18",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880210",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "299",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "299",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880210",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "299",
              "projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_5aaf26c9038fcb291665dba304415ad97357406c",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_f40d1b4df1975d981db891379ef61d5481be8b38",
      "common_action_event": {
        "action_event_row_id": 23052,
        "event_id": "evt_86b3474f9d5d6f86e7e136cbe762aaafd011d4b6",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222978,
        "event_id": "evt_86b3474f9d5d6f86e7e136cbe762aaafd011d4b6",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880217",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "305",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "305",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880217",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "305",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_f40d1b4df1975d981db891379ef61d5481be8b38",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_0fb9cf85f0fe6341bdb77c14f86cfc5eea0e79a7",
      "common_action_event": {
        "action_event_row_id": 23053,
        "event_id": "evt_71750fa956efbd815154b52fd94357ca97621abd",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222979,
        "event_id": "evt_71750fa956efbd815154b52fd94357ca97621abd",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880225",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "306",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "306",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880225",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "306",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_0fb9cf85f0fe6341bdb77c14f86cfc5eea0e79a7",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_6513e5c770e82e18a4c398ebd246d022a1811b9d",
      "common_action_event": {
        "action_event_row_id": 23054,
        "event_id": "evt_ae3744062dc33d4df77919978351670c257273ba",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222980,
        "event_id": "evt_ae3744062dc33d4df77919978351670c257273ba",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880568",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "307",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "307",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880568",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "307",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_6513e5c770e82e18a4c398ebd246d022a1811b9d",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_f5567ef5530a30b8949f0f6c490f62c6386582aa",
      "common_action_event": {
        "action_event_row_id": 23055,
        "event_id": "evt_39ffb2619c11ed6c0d6bf81e5f54925bf8184937",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222981,
        "event_id": "evt_39ffb2619c11ed6c0d6bf81e5f54925bf8184937",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880585",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "300",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "300",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880585",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "300",
              "projection_run_id": "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_f5567ef5530a30b8949f0f6c490f62c6386582aa",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_2a3b61f040c5fca5df7af0bbb86eecab9d81685d",
      "common_action_event": {
        "action_event_row_id": 23056,
        "event_id": "evt_5acf92f1532ac9f3a90950b98014b8f5ed41ca55",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222982,
        "event_id": "evt_5acf92f1532ac9f3a90950b98014b8f5ed41ca55",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880627",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "308",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "308",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880627",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "308",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_2a3b61f040c5fca5df7af0bbb86eecab9d81685d",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_a55d83b4312fe622a0a7b2eba186dfb30b401db6",
      "common_action_event": {
        "action_event_row_id": 23057,
        "event_id": "evt_6d81ef2c6a8d390dc47150c86769e3b12e82a032",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222983,
        "event_id": "evt_6d81ef2c6a8d390dc47150c86769e3b12e82a032",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880637",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "309",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "309",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880637",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "309",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_a55d83b4312fe622a0a7b2eba186dfb30b401db6",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_aff046efbbc331a960d051b2493b706e9d6f3e75",
      "common_action_event": {
        "action_event_row_id": 23058,
        "event_id": "evt_67364ea4bea7d214721a76c54f7998a87ed8725d",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222984,
        "event_id": "evt_67364ea4bea7d214721a76c54f7998a87ed8725d",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880719",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "310",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "310",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880719",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "310",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_aff046efbbc331a960d051b2493b706e9d6f3e75",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_c54374e0b78be9b99ea6e4f2290b82d474fc4085",
      "common_action_event": {
        "action_event_row_id": 23059,
        "event_id": "evt_35422f23e3b1e30c25f9a8c2c2f3f30442fa77be",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222985,
        "event_id": "evt_35422f23e3b1e30c25f9a8c2c2f3f30442fa77be",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880753",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "311",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "311",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880753",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "311",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_c54374e0b78be9b99ea6e4f2290b82d474fc4085",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_d3f8472e7f5ee478abf005a435d63a1ae0dc077f",
      "common_action_event": {
        "action_event_row_id": 23060,
        "event_id": "evt_238e99c8375cc8d75b020f8122fc9a2ec74f4755",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222986,
        "event_id": "evt_238e99c8375cc8d75b020f8122fc9a2ec74f4755",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880754",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,M,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "312",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "312",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880754",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "312",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_d3f8472e7f5ee478abf005a435d63a1ae0dc077f",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_2c6e2c6cd82551ff243502a4cbfffe26754f58fe",
      "common_action_event": {
        "action_event_row_id": 23061,
        "event_id": "evt_60ddad5d8555f9eb51d535b1685b27b55d613444",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222987,
        "event_id": "evt_60ddad5d8555f9eb51d535b1685b27b55d613444",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:880764",
      "signal_type": "S_SELL",
      "condition_key": "SELL:W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "313",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "313",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:880764",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "313",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_2c6e2c6cd82551ff243502a4cbfffe26754f58fe",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_ab91963297a6be6539b1fe719d6d3fe5a2dc9b19",
      "common_action_event": {
        "action_event_row_id": 23062,
        "event_id": "evt_7130e39370ea6b42788d99826ce60950da597e46",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222988,
        "event_id": "evt_7130e39370ea6b42788d99826ce60950da597e46",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881111",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,W,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "314",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "314",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881111",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "314",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_ab91963297a6be6539b1fe719d6d3fe5a2dc9b19",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_bab76df74c07f3ba350ccd007d5d1f5a8010096a",
      "common_action_event": {
        "action_event_row_id": 23063,
        "event_id": "evt_83bcd0a71651301bda314679f5dae050a3e3d996",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222989,
        "event_id": "evt_83bcd0a71651301bda314679f5dae050a3e3d996",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881119",
      "signal_type": "S_SELL",
      "condition_key": "SELL:D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "315",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "315",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881119",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "315",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_bab76df74c07f3ba350ccd007d5d1f5a8010096a",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_7368307224fe59a1a540a8f6a749db2802fba765",
      "common_action_event": {
        "action_event_row_id": 23064,
        "event_id": "evt_114f6062675f243c05095e9d4186a37503c62219",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222990,
        "event_id": "evt_114f6062675f243c05095e9d4186a37503c62219",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881140",
      "signal_type": "S_SELL",
      "condition_key": "SELL:D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "316",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "316",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881140",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "316",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_7368307224fe59a1a540a8f6a749db2802fba765",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_43054423ff23d2dfcb1a51b6ce1495c1a5b9d83a",
      "common_action_event": {
        "action_event_row_id": 23065,
        "event_id": "evt_819dca7ef9b9944bb454b581125ccac66e01d922",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222991,
        "event_id": "evt_819dca7ef9b9944bb454b581125ccac66e01d922",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881180",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q,W",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "317",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "317",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881180",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "317",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_43054423ff23d2dfcb1a51b6ce1495c1a5b9d83a",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_fe6ce256c3882e7150e190ac28164f42db503890",
      "common_action_event": {
        "action_event_row_id": 23066,
        "event_id": "evt_afc6869f927f8923ec58e0f0b34bf9fc51905db8",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222992,
        "event_id": "evt_afc6869f927f8923ec58e0f0b34bf9fc51905db8",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881190",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Q,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "318",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "318",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881190",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "318",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_fe6ce256c3882e7150e190ac28164f42db503890",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_de3007cf9a2d836ab9f882ae072765e3c643e236",
      "common_action_event": {
        "action_event_row_id": 23067,
        "event_id": "evt_a1695430d625e709634694a03d36244a2c0b1e77",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222993,
        "event_id": "evt_a1695430d625e709634694a03d36244a2c0b1e77",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881215",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Q,D",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "319",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "319",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881215",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "319",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_de3007cf9a2d836ab9f882ae072765e3c643e236",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_2c91d91c8787d07a62156be0e82ee30c89738ba0",
      "common_action_event": {
        "action_event_row_id": 23068,
        "event_id": "evt_b51bb980bc3a4ba050e05ff53923662ee4c80bfc",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222994,
        "event_id": "evt_b51bb980bc3a4ba050e05ff53923662ee4c80bfc",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881227",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "320",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "320",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881227",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "320",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_2c91d91c8787d07a62156be0e82ee30c89738ba0",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    },
    {
      "source_trigger_event_id": "evt_c5a85198dd74efb5ac4dc118133ccdf12c8d89a7",
      "common_action_event": {
        "action_event_row_id": 23069,
        "event_id": "evt_8ecd926c992259bc7e164be692f958cdc986947e",
        "current_event_type": "ActionBlocked",
        "planned_event_type": "ActionBlocked",
        "current_action_state": "blocked",
        "planned_action_state": "blocked",
        "current_confirmation_status": "failed",
        "planned_confirmation_status": "failed",
        "current_action_mark": null,
        "planned_action_mark": null,
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "n5_common_event_outbox": {
        "outbox_id": 222995,
        "event_id": "evt_8ecd926c992259bc7e164be692f958cdc986947e",
        "status": "pending",
        "current_blocked_reason": "metric_missing",
        "planned_blocked_reason": "price_confirmation_failed"
      },
      "asset_kind": "board",
      "identity_key": "board:TDX:881268",
      "signal_type": "S_SELL",
      "condition_key": "SELL:Y,Q",
      "source_projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
      "source_action_confirmation_metric_id": "321",
      "metadata_patch": {
        "blocked_reason": "price_confirmation_failed",
        "action_confirmation_metric_run_refs": [
          {
            "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            "source_action_confirmation_metric_id": "321",
            "metric_trace": {
              "join_policy": "deterministic_v1_asset_identity_trade_date_action_metric_run",
              "join_key": {
                "asset_kind": "board",
                "identity_key": "board:TDX:881268",
                "trade_date": "20260605",
                "action_metric_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
              },
              "action_confirmation_metric_id": "321",
              "projection_run_id": "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
              "metric_table": "board_action_confirmation_projection_metric",
              "metric_minute_label": "11:27",
              "metric_ready": true,
              "metric_quality_status": "passed",
              "projection_schema_version": "n3.action_confirmation_metric.v1"
            }
          }
        ],
        "metric_union_policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
        "metric_union_source_runs": [
          "action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
        ],
        "metric_coverage_status": "full",
        "metric_missing_resolved": true,
        "repair_trace": {
          "repair_run_id": "n5_full_metric_union_historical_metadata_repair_20260605_v1",
          "policy_version": "n5.full_metric_union_historical_metadata_repair.v1",
          "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "action_run_id": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
          "source_trigger_event_id": "evt_c5a85198dd74efb5ac4dc118133ccdf12c8d89a7",
          "previous_blocked_reason": "metric_missing",
          "new_blocked_reason": "price_confirmation_failed",
          "previous_event_type": "ActionBlocked",
          "new_event_type": "ActionBlocked",
          "previous_action_state": "blocked",
          "new_action_state": "blocked",
          "previous_confirmation_status": "failed",
          "new_confirmation_status": "failed",
          "previous_action_mark": null,
          "new_action_mark": null,
          "repair_type": "metadata_only_blocked_reason_and_metric_union_trace"
        }
      },
      "allowed_update_keys": [
        "blocked_reason",
        "action_confirmation_metric_run_refs",
        "metric_union_policy_version",
        "metric_union_source_runs",
        "metric_coverage_status",
        "metric_missing_resolved",
        "repair_trace"
      ],
      "forbidden_update_keys": [
        "event_type",
        "action_state",
        "confirmation_status",
        "action_mark",
        "event_id",
        "source_trigger_event_id",
        "run_id",
        "source_run_id",
        "status"
      ]
    }
  ]
}
```

## Rollback Requirement

Rollback must hard-fail before UPDATE, use no DELETE/INSERT/CASCADE/DROP/TRUNCATE, restore only scoped metadata keys, and not touch N4/N3/N2/N6 facts.

## Validation

```text
CONTRACT_PASS is backed by:
- full metric union coverage=605/605
- duplicate metric join key=0
- missing metric after union=0
- ActionExecuted before/after=1/1
- ActionBlocked before/after=604/604
- metric_missing before/after=289/0
- rollback static check passed
- JSON/payload parse passed
- targeted action tests passed
- forbidden scope proof passed
```
