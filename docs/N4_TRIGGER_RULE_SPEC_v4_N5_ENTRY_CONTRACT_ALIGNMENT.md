# N4 Trigger Rule Spec v4 N5 Entry Contract Alignment

Result: `N5_ENTRY_ALIGNMENT_PASS`


```json
{
  "bj_policy": "BJ 4 missing rows are quality_blocked and cannot enter N5",
  "condition_context_materialization_run_id": "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
  "diff_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_v3_v4_diff.json",
  "dry_run_report_path": "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json",
  "entry_allowed_event": "TriggerMatched only",
  "entry_required_fields": {
    "n5_entry_allowed": true,
    "outcome_classification": "matched",
    "output_event_type": "TriggerMatched",
    "signal_type": [
      "B_BUY",
      "S_SELL"
    ],
    "trigger_live": true
  },
  "execute_run_id": "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1",
  "for_trade_date": "20260603",
  "forbidden_entry_outcomes": [
    "pending_market_data",
    "no_op",
    "quality_blocked",
    "inactive"
  ],
  "full_policy": "FULL rows remain blocked and cannot enter N5 until FULL semantics are approved and produce TriggerMatched",
  "generated_at": "2026-06-04T02:03:53.852263+00:00",
  "invalid_n5_entry_count": 0,
  "layer_role": "N4_trigger",
  "n5_entry_allowed_count": 863,
  "no_op_policy": "no_op is complete evidence without trigger; no N5 action confirmation",
  "pending_market_data_policy": "pending_market_data evidence incomplete; no N5 action confirmation",
  "projection_run_id": "projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "quality_blocked_policy": "quality_blocked is quality/audit only; no N5 action confirmation",
  "result": "N5_ENTRY_ALIGNMENT_PASS",
  "snapshot_run_id": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
  "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
  "stage": "N4_V4_EXECUTE_CONTRACT_PREFLIGHT_GATE",
  "trigger_context_run_id": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
  "trigger_rule_policy_hash": "3d4b046ea6a02ad8",
  "trigger_rule_spec_version": "N4_TRIGGER_RULE_SPEC_v4"
}
```
