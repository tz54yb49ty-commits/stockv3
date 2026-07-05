# N4 Trigger Rule Spec v4 Execute Report Schema

Result: `SCHEMA_DRAFT_PASS`


```json
{
  "actual_outcomes_schema": {
    "inactive": "integer",
    "matched": "integer",
    "n5_entry_allowed": "integer",
    "no_op": "integer",
    "pending_market_data": "integer",
    "quality_blocked": "integer"
  },
  "actual_writes_schema": {
    "TriggerMatched": "integer",
    "TriggerPendingMarketData": "integer",
    "TriggerStateChanged": "integer",
    "common_event_outbox": "integer",
    "common_trigger_match": "integer",
    "common_trigger_quality_item": "integer",
    "common_trigger_run": "integer",
    "common_trigger_state": "integer"
  },
  "boundary_proof_schema": {
    "database_writes": "true only during authorized execute",
    "inbox_checkpoint_written": false,
    "market_data_pulled": false,
    "n5_n6_entered": false,
    "outbox_consumed": false,
    "real_trade_touched": false,
    "worker_started": false
  },
  "condition_context_materialization_run_id": "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
  "diff_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_v3_v4_diff.json",
  "dry_run_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
  "execute_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
  "for_trade_date": "20260603",
  "generated_at": "2026-06-04T02:03:53.852263+00:00",
  "layer_role": "N4_trigger",
  "must_match_dry_run_counts": {
    "inactive": 0,
    "matched": 863,
    "n5_entry_allowed": 863,
    "no_op": 4263,
    "pending_market_data": 0,
    "quality_blocked": 96
  },
  "projection_run_id": "projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "required_top_level_fields": [
    "result",
    "execute_run_id",
    "trigger_rule_spec_version",
    "trigger_rule_policy_hash",
    "run_status",
    "actual_outcomes",
    "actual_writes",
    "n5_entry_guard",
    "bj_quality_visible_proof",
    "full_blocked_proof",
    "rollback_safe",
    "boundary_proof"
  ],
  "result": "SCHEMA_DRAFT_PASS",
  "schema_name": "N4_TRIGGER_RULE_SPEC_v4_execute_report_schema",
  "snapshot_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
  "stage": "N4_V4_EXECUTE_CONTRACT_PREFLIGHT_GATE",
  "trigger_context_run_id": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
  "trigger_rule_policy_hash": "3d4b046ea6a02ad8",
  "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4"
}
```
