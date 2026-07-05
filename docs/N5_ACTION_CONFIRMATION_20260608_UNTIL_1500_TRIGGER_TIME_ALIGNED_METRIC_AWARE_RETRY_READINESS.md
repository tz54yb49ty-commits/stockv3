# N5 20260608 Until 1500 Trigger-Time Aligned Metric-Aware Retry Readiness

classification=READY_WITH_ROLLBACK_PREREQUISITE

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
metric_run_id=action_confirmation_metric_20260608_trigger_time_aligned_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
target_action_run_id=action_consumer_execute_20260608_until_1500_trigger_time_aligned_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
target_consumer_name=n5_action_consumer_v1_20260608_until_1500_trigger_time_aligned_reprocess
db_writes_performed=false
```

## Join

```json
{
  "join_policy": "deterministic_v2_trigger_row_time_action_metric_run",
  "join_key": [
    "source_trigger_match_id/source_trigger_event_id",
    "asset_kind",
    "identity_key",
    "direction",
    "condition_key",
    "trigger_time/metric_time",
    "trade_date/for_trade_date",
    "action_metric_run_id"
  ],
  "metric_run_id": "action_confirmation_metric_20260608_trigger_time_aligned_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
  "metric_rows": 122,
  "n4_trigger_matched_rows": 122,
  "joined_n4_rows": 122,
  "payload_metric_id_rows": 0,
  "missing_n4_rows": 0,
  "coverage": "122/122",
  "duplicate_join_key_count": 0,
  "duplicate_join_key_rows": 0,
  "duplicate_join_keys_sample": {},
  "missing_sample": [],
  "by_asset_kind": {
    "board": {
      "n4_trigger_matched_rows": 3,
      "joined_n4_rows": 3,
      "missing_n4_rows": 0,
      "metric_rows": 3
    },
    "index": {
      "n4_trigger_matched_rows": 6,
      "joined_n4_rows": 6,
      "missing_n4_rows": 0,
      "metric_rows": 6
    },
    "stock": {
      "n4_trigger_matched_rows": 113,
      "joined_n4_rows": 113,
      "missing_n4_rows": 0,
      "metric_rows": 113
    }
  }
}
```

## Planned Output

```json
{
  "ActionEligible": 0,
  "ActionBlocked": 121,
  "ActionExecuted": 1,
  "ActionSkipped": 0
}
```

## Planned Action State

```json
{
  "blocked": 121,
  "executed": 1
}
```

## Metric Readiness

```json
{
  "action_confirmation_candidate_count": 122,
  "source_action_confirmation_metric_id_count": 122,
  "metric_fact_available_count": 122,
  "metric_fact_missing_count": 0,
  "by_metric_status": {
    "ready": 122
  },
  "by_metric_quality_status": {
    "passed": 122
  },
  "all_period_confirmation_pass_count": 1,
  "all_period_confirmation_failed_count": 121
}
```

## Blockers / Warnings

```json
{
  "blockers": [],
  "warnings": [
    "stale_prior_n5_action_runs_exist_for_same_source_trigger_run",
    "stale_prior_n6_downstream_refs_exist_for_same_source_trigger_run",
    "unified_rule_does_not_execute_all_joined_trigger_matched_rows"
  ]
}
```

## Boundary

No DB writes, no rollback SQL, no outbox consumption, no N6/user/voice/mobile/sim/trade/position/PnL, no worker, no old system touch.
