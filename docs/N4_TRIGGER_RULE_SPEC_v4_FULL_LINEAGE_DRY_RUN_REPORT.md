# N4 Trigger Rule Spec v4 Full-Lineage Dry-Run Report

Result: `FULL_LINEAGE_DRY_RUN_PASS`

Mode: `shadow_v4_full_lineage_dry_run`

Context run: `trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1`

Snapshot run: `realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`

V4 run: `trigger_rule_v4_shadow_dry_run_20260603_condition_layer_20260602_source_20260602_v1`

## Input Readiness

```json
{
  "context_rows": 5222,
  "legacy_trigger_context_rows": 5222,
  "context_enrichment_rows": 5222,
  "period_previous_transition_rows": 5222,
  "period_previous_amount_baseline_rows": 5222,
  "realtime_projection_rows": 5222,
  "realtime_projection_enrichment_rows": 5222,
  "complete_lineage_rows": 5218,
  "bj_quality_visible_rows": 4,
  "snapshot_only_fallback_rows": 0,
  "action_confirmation_projection_rows": 0,
  "action_confirmation_projection_enrichment_rows": 0
}
```

## Declared Enrichment Readiness

```json
{
  "n2_context_enrichment": {
    "path": "docs/N2_20260603_context_enrichment_row_level_materialization_execute_report.json",
    "path_exists": true,
    "result": "EXECUTED",
    "expected_context_candidates": 5222,
    "declared_context_enrichment_rows": 5222,
    "declared_previous_transition_rows": null,
    "declared_previous_amount_baseline_rows": null,
    "row_level_payload_available": false,
    "row_level_payload_policy": "N4 accepts only materialized DB rows or an explicit full row-level payload, not summary counts."
  },
  "n3_projection_enrichment": {
    "path": "docs/N3_projection_enrichment_v4_20260603_materialization_execute_report.json",
    "path_exists": true,
    "result": "EXECUTE_PASS",
    "expected_context_candidates": 5222,
    "declared_projection_rows": 5222,
    "declared_enrichment_rows": 5222,
    "declared_complete_lineage_rows": 5218,
    "missing_source_minute_rows": 4,
    "snapshot_only_fallback_rows": 0,
    "row_level_payload_available": false,
    "row_level_payload_policy": "N4 accepts only materialized DB rows or an explicit full row-level payload, not summary counts."
  }
}
```

## Blockers

```json
[]
```

## V4 Summary

```json
{
  "matched": 863,
  "pending_market_data": 0,
  "no_op": 4263,
  "quality_blocked": 96,
  "inactive": 0,
  "n5_entry_allowed": 863,
  "primary_trigger_period_distribution": {
    "None": 4477,
    "Q": 175,
    "Y": 131,
    "D": 212,
    "W": 141,
    "M": 86
  },
  "trigger_kind_distribution": {
    "trigger": 4945,
    "hint": 277
  },
  "trigger_mark_candidate_distribution": {
    "normal": 3938,
    "30m_shrink": 280,
    "30m_volume": 1004
  },
  "by_asset_kind": {
    "stock": 4164,
    "index": 168,
    "board": 890
  },
  "by_signal_type": {
    "B_BUY": 2690,
    "S_SELL": 2532
  },
  "by_condition_key": {
    "BUY:Y,Q,M,W,D": 926,
    "SELL:M,W": 10,
    "SELL:FULL": 31,
    "SELL:M,W,D": 79,
    "BUY:Y,D": 7,
    "SELL:Y,Q,M,W,D": 752,
    "BUY:Y,Q": 25,
    "SELL:Y,M,W": 12,
    "SELL:Y,W,D": 119,
    "BUY:D": 41,
    "BUY:Y,Q,D": 32,
    "BUY:Y,Q,M,D": 88,
    "SELL:W,D": 46,
    "SELL:Y,M,W,D": 158,
    "BUY:Y,Q,W,D": 58,
    "SELL:Y,Q,M,W": 97,
    "BUY:W,D": 359,
    "BUY:Q,M,W,D": 238,
    "SELL:Y,Q,D": 196,
    "BUY_HINT": 216,
    "SELL:Y": 84,
    "BUY:FULL": 61,
    "SELL_HINT": 61,
    "SELL:Y,Q,W": 40,
    "SELL:Y,W": 30,
    "BUY:Q,D": 22,
    "BUY:Q": 15,
    "BUY:Q,M": 6,
    "SELL:Y,Q,W,D": 116,
    "SELL:Y,D": 110,
    "BUY:W": 70,
    "BUY:Y,Q,M,W": 77,
    "BUY:M,W,D": 206,
    "BUY:Q,M,W": 46,
    "SELL:Y,Q": 181,
    "SELL:W": 13,
    "SELL:Q,W": 4,
    "SELL:Q,M,W,D": 47,
    "SELL:Y,Q,M": 77,
    "BUY:M,W": 29,
    "BUY:Y,Q,M": 24,
    "BUY:M,D": 4,
    "BUY:Q,M,D": 16,
    "BUY:Y,W,D": 27,
    "SELL:D": 40,
    "SELL:Q": 20,
    "BUY:Q,W,D": 35,
    "BUY:Y,Q,W": 16,
    "BUY:Q,W": 11,
    "SELL:Y,Q,M,D": 164,
    "SELL:Q,D": 8,
    "SELL:Q,W,D": 7,
    "BUY:Y": 6,
    "SELL:Q,M,W": 6,
    "SELL:Q,M,D": 4,
    "SELL:Y,M": 2,
    "SELL:Y,M,D": 5,
    "SELL:M": 5,
    "SELL:Q,M": 3,
    "BUY:Y,M,W,D": 20,
    "BUY:Y,M,D": 4,
    "SELL:M,D": 5,
    "BUY:M": 4,
    "BUY:Y,M,W": 1
  },
  "by_asset_kind_signal_type": {
    "stock|B_BUY": 2155,
    "stock|S_SELL": 2009,
    "index|B_BUY": 84,
    "index|S_SELL": 84,
    "board|B_BUY": 451,
    "board|S_SELL": 439
  },
  "by_asset_kind_condition_key": {
    "stock|BUY:Y,Q,M,W,D": 725,
    "stock|SELL:M,W": 10,
    "stock|SELL:FULL": 30,
    "stock|SELL:M,W,D": 71,
    "stock|BUY:Y,D": 6,
    "stock|SELL:Y,Q,M,W,D": 539,
    "stock|BUY:Y,Q": 25,
    "stock|SELL:Y,M,W": 11,
    "stock|SELL:Y,W,D": 98,
    "stock|BUY:D": 38,
    "stock|BUY:Y,Q,D": 30,
    "stock|BUY:Y,Q,M,D": 80,
    "stock|SELL:W,D": 41,
    "stock|SELL:Y,M,W,D": 91,
    "stock|BUY:Y,Q,W,D": 57,
    "stock|SELL:Y,Q,M,W": 92,
    "stock|BUY:W,D": 275,
    "stock|BUY:Q,M,W,D": 173,
    "stock|SELL:Y,Q,D": 150,
    "stock|BUY_HINT": 192,
    "stock|SELL:Y": 64,
    "stock|BUY:FULL": 59,
    "stock|SELL_HINT": 49,
    "stock|SELL:Y,Q,W": 38,
    "stock|SELL:Y,W": 27,
    "stock|BUY:Q,D": 20,
    "stock|BUY:Q": 15,
    "stock|BUY:Q,M": 4,
    "stock|SELL:Y,Q,W,D": 102,
    "stock|SELL:Y,D": 92,
    "stock|BUY:W": 50,
    "stock|BUY:Y,Q,M,W": 68,
    "stock|BUY:M,W,D": 139,
    "stock|BUY:Q,M,W": 32,
    "stock|SELL:Y,Q": 144,
    "stock|SELL:W": 12,
    "stock|SELL:Q,W": 4,
    "stock|SELL:Q,M,W,D": 43,
    "stock|SELL:Y,Q,M": 72,
    "stock|BUY:M,W": 16,
    "stock|BUY:Y,Q,M": 22,
    "stock|BUY:M,D": 4,
    "stock|BUY:Q,M,D": 13,
    "stock|BUY:Y,W,D": 27,
    "stock|SELL:D": 38,
    "stock|SELL:Q": 20,
    "stock|BUY:Q,W,D": 30,
    "stock|BUY:Y,Q,W": 14,
    "stock|BUY:Q,W": 8,
    "stock|SELL:Y,Q,M,D": 128,
    "stock|SELL:Q,D": 8,
    "stock|SELL:Q,W,D": 7,
    "stock|BUY:Y": 6,
    "stock|SELL:Q,M,W": 6,
    "stock|SELL:Q,M,D": 4,
    "stock|SELL:Y,M": 1,
    "stock|SELL:Y,M,D": 4,
    "stock|SELL:M": 5,
    "stock|SELL:Q,M": 3,
    "stock|BUY:Y,M,W,D": 19,
    "stock|BUY:Y,M,D": 4,
    "stock|SELL:M,D": 5,
    "stock|BUY:M": 3,
    "stock|BUY:Y,M,W": 1,
    "index|BUY:M,W": 3,
    "index|SELL:M,W,D": 3,
    "index|BUY:M,W,D": 13,
    "index|SELL:Y,Q,M,W,D": 42,
    "index|SELL:Y,Q,D": 11,
    "index|BUY:Q,M,D": 1,
    "index|BUY:Y,Q,M,W,D": 12,
    "index|SELL_HINT": 1,
    "index|BUY:W": 5,
    "index|SELL:Y,W,D": 2,
    "index|BUY:W,D": 35,
    "index|SELL:Y,Q,M,D": 16,
    "index|SELL:Y,Q,M,W": 2,
    "index|BUY:Q,M,W,D": 2,
    "index|SELL:Y": 2,
    "index|SELL:Y,M,W,D": 4,
    "index|BUY:Q,M,W": 2,
    "index|BUY:Y,D": 1,
    "index|BUY:Y,Q,M": 1,
    "index|SELL:Y,D": 1,
    "index|BUY:Y,Q,M,W": 2,
    "index|BUY:Q,W,D": 1,
    "index|BUY:Y,Q,D": 1,
    "index|BUY:Y,Q,M,D": 2,
    "index|BUY:Q,M": 1,
    "index|BUY_HINT": 1,
    "index|BUY:D": 1,
    "board|BUY:Q,M,W,D": 63,
    "board|SELL:Y,Q,W": 2,
    "board|BUY:Y,Q,M,W,D": 189,
    "board|SELL:Y,W,D": 19,
    "board|SELL:Y,M,D": 1,
    "board|SELL:Y,Q,M": 5,
    "board|BUY_HINT": 23,
    "board|BUY:M,W,D": 54,
    "board|SELL:Y,Q": 37,
    "board|BUY:Q,M,W": 12,
    "board|SELL:Y,Q,M,W,D": 171,
    "board|SELL:Y,Q,D": 35,
    "board|BUY:W,D": 49,
    "board|SELL_HINT": 11,
    "board|SELL:Y,Q,M,D": 20,
    "board|BUY:M,W": 10,
    "board|SELL:Y,Q,W,D": 14,
    "board|BUY:D": 2,
    "board|BUY:Q,M,D": 2,
    "board|BUY:Q,W,D": 4,
    "board|BUY:Y,Q,M,W": 7,
    "board|BUY:M": 1,
    "board|SELL:Y,W": 3,
    "board|SELL:Y,D": 17,
    "board|BUY:W": 15,
    "board|SELL:Y,M,W,D": 63,
    "board|SELL:Y": 18,
    "board|BUY:Q,M": 1,
    "board|BUY:Q,D": 2,
    "board|SELL:Y,Q,M,W": 3,
    "board|BUY:Q,W": 3,
    "board|SELL:W,D": 5,
    "board|BUY:FULL": 2,
    "board|SELL:M,W,D": 5,
    "board|BUY:Y,Q,M,D": 6,
    "board|SELL:D": 2,
    "board|SELL:Q,M,W,D": 4,
    "board|BUY:Y,M,W,D": 1,
    "board|BUY:Y,Q,D": 1,
    "board|SELL:FULL": 1,
    "board|BUY:Y,Q,W": 2,
    "board|SELL:Y,M,W": 1,
    "board|BUY:Y,Q,M": 1,
    "board|SELL:W": 1,
    "board|BUY:Y,Q,W,D": 1,
    "board|SELL:Y,M": 1
  },
  "by_trigger_kind_trigger_mark_candidate": {
    "trigger|normal": 3779,
    "trigger|30m_shrink": 268,
    "trigger|30m_volume": 898,
    "hint|normal": 159,
    "hint|30m_shrink": 12,
    "hint|30m_volume": 106
  }
}
```

## V3-V4 Diff Summary

```json
{
  "v3_plan_count": 10167,
  "v4_plan_count": 5222,
  "false_positive_count": 656,
  "false_negative_count": 267,
  "changed_count": 0,
  "interpretation": "false positives/negatives are shadow comparisons between production v3 plans and shadow v4 outcomes."
}
```

## BJ Missing Quality Visible Proof

```json
{
  "declared_by_n3_missing_source_minute_rows": 4,
  "declared_snapshot_only_fallback_rows": 0,
  "n4_row_level_projection_enrichment_rows": 5222,
  "n4_bj_quality_blocked_rows": 4,
  "bj_rows_quality_blocked": true,
  "status": "materialized_quality_blocked",
  "policy": "BJ missing rows must be quality-visible from row-level N3 enrichment; N4 must not fallback or infer them from summary counts."
}
```

## FULL Blocked Proof

```json
{
  "blocked_count": 92,
  "samples": [
    {
      "identity_key": "stock:SH:600004",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600032",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600171",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600185",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600301",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600378",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600500",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600515",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600575",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600667",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600809",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:600869",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601026",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601101",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601138",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601865",
      "condition_key": "SELL:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601869",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:601991",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:603002",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    },
    {
      "identity_key": "stock:SH:603078",
      "condition_key": "BUY:FULL",
      "blocked_reason": "full_semantics_blocked"
    }
  ]
}
```

## N5 Entry Guard

```json
{
  "allowed_count": 863,
  "violations": 0,
  "rule": "TriggerMatched+B_BUY/S_SELL+matched+trigger_live=true+n5_entry_allowed=true"
}
```
