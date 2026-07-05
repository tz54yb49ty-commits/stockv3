# N4 Trigger Rule Spec v4 V3-V4 Diff / Backtest Artifact

Result: `DIFF_BACKTEST_PASS`

Scope: `representative_contract_backtest_only_no_business_execute`

## V3 Baseline

```json
{
  "source": "docs/N4_20260603_local_trigger_dry_run_report.json",
  "result": "DRY_RUN_PASS",
  "context_candidates": 5222,
  "planned_trigger_matched": null,
  "planned_trigger_pending_market_data": null,
  "planned_trigger_state_changed": null,
  "p0_p1_p2": {
    "p0_count": 0,
    "p1_count": 2,
    "p2_count": 0,
    "items": [
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_context_run_ready",
        "gate_name": "N4 local dry-run must bind a passed 20260528 trigger context run",
        "expected_value": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
        "actual_value": "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_snapshot_run_ready",
        "gate_name": "N4 local dry-run must read the passed B1 retry1 snapshot run",
        "expected_value": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        "actual_value": "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_context_rows_available",
        "gate_name": "N4 local dry-run must read local context candidates",
        "expected_value": ">0",
        "actual_value": "5222"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_snapshot_rows_available",
        "gate_name": "N4 local dry-run must read B1 snapshot facts",
        "expected_value": ">0",
        "actual_value": "2474"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_context_snapshot_coverage",
        "gate_name": "Every local context object must be traceable to a B1 snapshot fact",
        "expected_value": "0 missing context objects",
        "actual_value": "0"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_period_trigger_baseline_json_present",
        "gate_name": "N4 local dry-run must use local period_trigger_baseline_json copies",
        "expected_value": "missing=0",
        "actual_value": "0"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_required_period_baseline_ready",
        "gate_name": "N4 local dry-run must not use rows whose required periods are not ready",
        "expected_value": "required_period_not_ready_rows=0",
        "actual_value": "0"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_plan_payload_traces_period_baseline",
        "gate_name": "All local dry-run plans must trace period_trigger_baseline_json",
        "expected_value": "10167",
        "actual_value": "10167"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_snapshot_ordinary_candidate_plans",
        "gate_name": "B1 snapshot facts must generate ordinary B_BUY/S_SELL dry-run matched plans",
        "expected_value": ">0",
        "actual_value": "1252"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_projection_signal_candidates_visible",
        "gate_name": "B_BUY_30M_VOL/S_SELL_30M_SHRINK/BUY_HINT/SELL_HINT remain visible as formal candidates",
        "expected_value": ">0",
        "actual_value": "5222"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_canonical_payload_alignment",
        "gate_name": "Local dry-run plans must expose canonical signal_type/trigger_mark_candidate and preserve original_condition_key",
        "expected_value": "canonical_payload_invalid_count=0",
        "actual_value": "0"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_no_database_rows_written",
        "gate_name": "N4 local dry-run must not write database rows",
        "expected_value": "before row counts equal after row counts",
        "actual_value": "unchanged"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_local_dry_run_upstream_input_refs_compatible",
        "gate_name": "N4 local dry-run may see allowlisted N3 MarketSnapshotUpdated pending input, but must not see consumed/acked or non-allowlisted upstream refs",
        "expected_value": "upstream disallowed/inbox/checkpoint refs=0",
        "actual_value": "{\"upstream_input_checkpoint_refs\": 0, \"upstream_input_inbox_refs\": 0, \"upstream_input_outbox_disallowed\": 0}"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_local_dry_run_upstream_input_outbox_allowlisted",
        "gate_name": "Allowlisted N3 MarketSnapshotUpdated pending outbox is input evidence and does not count as N4 output pollution",
        "expected_value": "allowed upstream input outbox >= 0",
        "actual_value": "0"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_local_dry_run_target_refs_zero",
        "gate_name": "N4 local dry-run must leave target N4 output/inbox/checkpoint/state/match refs at zero",
        "expected_value": "target output/state/match/inbox/checkpoint refs=0",
        "actual_value": "{\"target_checkpoint_refs\": 0, \"target_inbox_refs\": 0, \"target_output_outbox_refs\": 0, \"target_trigger_match_refs\": 0, \"target_trigger_state_refs\": 0}"
      },
      {
        "severity": "P1",
        "status": "warning",
        "gate_code": "n4_20260528_b1_p1_carried",
        "gate_name": "B1 retry1 non-blocking P1 is carried into the local dry-run report",
        "expected_value": "visible if present",
        "actual_value": "1"
      },
      {
        "severity": "P1",
        "status": "warning",
        "gate_code": "n4_20260528_projection_candidates_pending",
        "gate_name": "Projection/HINT candidates are held pending until N3 standardized projection or closed confirmation exists for this 20260528 lineage",
        "expected_value": "pending candidates visible, no TriggerMatched write",
        "actual_value": "5222"
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_no_outbox_consumption",
        "gate_name": "N4 local dry-run does not consume N3 or N5 outbox",
        "expected_value": null,
        "actual_value": null
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_no_trigger_fact_write",
        "gate_name": "N4 local dry-run does not write trigger_match or trigger_state",
        "expected_value": null,
        "actual_value": null
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_no_standard_outbox_write",
        "gate_name": "N4 local dry-run does not write TriggerMatched or TriggerPendingMarketData outbox",
        "expected_value": null,
        "actual_value": null
      },
      {
        "severity": "P0",
        "status": "passed",
        "gate_code": "n4_20260528_no_worker",
        "gate_name": "N4 local dry-run does not start worker or service",
        "expected_value": null,
        "actual_value": null
      }
    ]
  }
}
```

## V4 Sample

```json
{
  "plan_count": 9,
  "event_counts": {
    "TriggerMatched": 4,
    "TriggerPendingMarketData": 1
  },
  "outcome_counts": {
    "matched": 4,
    "no_op": 1,
    "pending_market_data": 1,
    "quality_blocked": 3
  },
  "signal_type_distribution": {
    "B_BUY": 5,
    "S_SELL": 4
  },
  "n5_entry_guard": {
    "allowed_count": 4,
    "violations": 0,
    "rule": "TriggerMatched+B_BUY/S_SELL+matched+trigger_live=true+n5_entry_allowed=true"
  },
  "full_blocked_proof": {
    "blocked_count": 2,
    "samples": [
      {
        "identity_key": "stock:SZ:000001",
        "condition_key": "BUY:FULL",
        "blocked_reason": "full_semantics_blocked"
      },
      {
        "identity_key": "stock:SZ:000001",
        "condition_key": "SELL:FULL",
        "blocked_reason": "full_semantics_blocked"
      }
    ]
  }
}
```

## Main Semantic Diff

```json
[
  "v4 distinguishes matched/pending_market_data/no_op/quality_blocked/inactive",
  "v4 reports only actual triggered Y/Q/M/W/D periods",
  "v4 keeps 30m as projection_period/projection_30m_type and never as primary/all periods",
  "v4 blocks FULL execute until final FULL prerequisite semantics are approved",
  "v4 allows N5 entry only for TriggerMatched with matched live state"
]
```
