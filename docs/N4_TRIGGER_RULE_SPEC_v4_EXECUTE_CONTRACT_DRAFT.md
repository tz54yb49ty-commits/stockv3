# N4 Trigger Rule Spec v4 Execute Contract Draft

Result: `CONTRACT_PASS`

This contract prepares v4 execute semantics but does not authorize execute. Outcome persistence is matched-only.

```json
{
  "allow_enter_execute_final_gate": true,
  "allowed_write_tables_after_future_final_gate": [
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox"
  ],
  "condition_context_materialization_run_id": "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
  "contract_scope": "prepare v4 run-once execute contract; no business writes authorized by this artifact",
  "diff_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_v3_v4_diff.json",
  "dry_run_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
  "execute_allowed": false,
  "execute_authorized": false,
  "execute_command_candidate": "PYTHONPATH=src:scripts python3 scripts/run_n4_trigger_rule_v4_execute_once.py \\\n  --execute-run-id trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1 \\\n  --dry-run-json-path docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json \\\n  --contract-path docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json \\\n  --preflight-path docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json \\\n  --rollback-sql-path sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql \\\n  --execute \\\n  --user-confirmed",
  "execute_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
  "expected_future_writes": {
    "TriggerMatched": 863,
    "TriggerPendingMarketData": 0,
    "TriggerStateChanged": 0,
    "common_event_outbox": 863,
    "common_trigger_match": 863,
    "common_trigger_quality_item": "quality summary rows, including BJ quality-visible and FULL blocked proof",
    "common_trigger_run": 1,
    "common_trigger_state": 863,
    "no_op_event": 0,
    "quality_blocked_event": 0
  },
  "expected_outcomes": {
    "inactive": 0,
    "matched": 863,
    "n5_entry_allowed": 863,
    "no_op": 4263,
    "pending_market_data": 0,
    "quality_blocked": 96
  },
  "for_trade_date": "20260603",
  "forbidden_write_tables": [
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2 condition tables",
    "N3 market facts/outbox",
    "N5/N6/action/user/voice/mobile/sim/position/real-trade tables",
    "worker state"
  ],
  "generated_at": "2026-06-04T02:37:53.093175+00:00",
  "layer_role": "N4_trigger",
  "n5_entry_alignment_note_path": "docs/N4_TRIGGER_RULE_SPEC_v4_N5_ENTRY_CONTRACT_ALIGNMENT.json",
  "n5_entry_contract": {
    "allow_entry_only_when": {
      "n5_entry_allowed": true,
      "outcome_classification": "matched",
      "output_event_type": "TriggerMatched",
      "signal_type": [
        "B_BUY",
        "S_SELL"
      ],
      "trigger_live": true
    },
    "forbidden_n5_entry_outcomes": [
      "pending_market_data",
      "no_op",
      "quality_blocked",
      "inactive"
    ],
    "invalid_n5_entry_count": 0
  },
  "outcome_persistence_strategy": {
    "reason": "common_trigger_state current_status does not support no_op/quality_blocked; v4 execute persists only valid N5-entry matched rows and keeps other outcomes report/quality-visible.",
    "schema_review_required_for_full_outcome_audit": true,
    "strategy": "matched_only"
  },
  "planned_write_policy": {
    "BJ": "BJ 920xxx missing rows remain quality_blocked; no fallback and no TriggerMatched",
    "FULL": "BUY:FULL/SELL:FULL remain quality_blocked; no TriggerMatched for FULL rows",
    "TriggerMatched": "only rows with outcome_classification=matched and n5_entry_allowed=true",
    "TriggerPendingMarketData": "not written in current v4 execute plan",
    "TriggerStateChanged": "not written in current v4 execute plan; state transition model remains separate",
    "contract_shape": "v4_matched_only_persistence",
    "inactive": "0 in current dry-run; future inactive state changes require separate TriggerStateChanged/state transition review",
    "matched": "persist common_trigger_state + common_trigger_match + TriggerMatched outbox only when n5_entry_allowed=true",
    "no_op": "no standard outbox, no common_trigger_state/match, no N5 entry; visible only in execute report summary until a v4 audit schema is approved",
    "pending_market_data": "0 in current dry-run; future nonzero pending rows must not enter N5 and require a separate persistence review before write",
    "quality_blocked": "no standard outbox, no common_trigger_state/match, no N5 entry; FULL/BJ proofs remain quality/report-visible"
  },
  "projection_run_id": "projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "proofs": {
    "bj_quality_visible": {
      "bj_rows_quality_blocked": true,
      "declared_by_n3_missing_source_minute_rows": 4,
      "declared_snapshot_only_fallback_rows": 0,
      "n4_bj_quality_blocked_rows": 4,
      "n4_row_level_projection_enrichment_rows": 5222,
      "policy": "BJ missing rows must be quality-visible from row-level N3 enrichment; N4 must not fallback or infer them from summary counts.",
      "recognized_bj_identity_keys": [
        "index:BJ:899050",
        "index:BJ:899601"
      ],
      "status": "materialized_quality_blocked"
    },
    "full_blocked": {
      "blocked_count": 92,
      "policy": "BUY:FULL/SELL:FULL continue BLOCKED; no FULL TriggerMatched"
    },
    "v3_v4_diff": {
      "changed_count": 0,
      "false_negative_count": 267,
      "false_positive_count": 656,
      "interpretation": "false positives/negatives are shadow comparisons between production v3 plans and shadow v4 outcomes.",
      "v3_plan_count": 10167,
      "v4_plan_count": 5222
    }
  },
  "remaining_final_gate_blockers": [],
  "report_schema_path": "docs/N4_TRIGGER_RULE_SPEC_v4_execute_report_schema.json",
  "requires_execute_flag": true,
  "requires_user_confirmed_flag": true,
  "result": "CONTRACT_PASS",
  "rollback_sql_path": "sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql",
  "runner_readiness": {
    "does_not_consume_n3_outbox": true,
    "double_confirmation_required": true,
    "matched_only_persistence_strategy": true,
    "missing_execute_blocks_before_write": true,
    "missing_user_confirmed_blocks_before_write": true,
    "ready": true,
    "recomputes_full_lineage_plan_from_n2_n3_enrichment": true,
    "runner": "scripts/run_n4_trigger_rule_v4_execute_once.py",
    "supports_dry_run_json_path_alias": true,
    "supports_preflight_path_alias": true
  },
  "snapshot_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
  "stage": "N4_V4_EXECUTE_CONTRACT_PREFLIGHT_GATE",
  "trigger_context_run_id": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
  "trigger_rule_policy_hash": "3d4b046ea6a02ad8",
  "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4"
}
```
