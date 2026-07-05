# N1 20260609 Source Facts Post Review

Result: `POST_REVIEW_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260609`
- for_trade_date: `20260610`
- official batch: `official_daily_ingest_20260609_v1`
- condition batch: `condition_source_activation_20260609_v1`
- combined rows: `86853`
- P0 failed quality gates: `0`
- event refs total: `0`
- downstream refs total: `0`
- rollback_safe: `True`

## Row Count Proof

```json
{
  "expected": {
    "official_daily": {
      "stock_daily_bar_fact": 5513,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "total_daily_fact": 6024
    },
    "condition_source": {
      "stock_daily_basic": 5513,
      "stock_financial_metrics_fact": 5513,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962,
      "total_condition_source_fact": 80829
    },
    "combined_total": 86853
  },
  "actual": {
    "official_daily": {
      "stock_daily_bar_fact": 5513,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "total_daily_fact": 6024
    },
    "condition_source": {
      "stock_daily_basic": 5513,
      "stock_financial_metrics_fact": 5513,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962,
      "total_condition_source_fact": 80829
    },
    "combined_total": 86853
  },
  "matched": true
}
```

## Active Source Versions

```json
{
  "expected_source_versions": [
    "stock_daily_20260609_v1",
    "index_daily_20260609_v1",
    "board_daily_20260609_v1",
    "stock_daily_basic_20260609_v1",
    "stock_financial_20260609_v1",
    "index_membership_20260609_v1",
    "board_membership_20260609_v1"
  ],
  "actual_rows": [
    {
      "data_domain": "board",
      "data_type": "board_daily",
      "scope_key": "20260609",
      "source_version": "board_daily_20260609_v1",
      "source_batch_id": "official_daily_ingest_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "board",
      "data_type": "board_membership",
      "scope_key": "TDX:20260609",
      "source_version": "board_membership_20260609_v1",
      "source_batch_id": "condition_source_activation_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "index",
      "data_type": "index_daily",
      "scope_key": "20260609",
      "source_version": "index_daily_20260609_v1",
      "source_batch_id": "official_daily_ingest_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "index",
      "data_type": "index_membership",
      "scope_key": "TDX:20260609",
      "source_version": "index_membership_20260609_v1",
      "source_batch_id": "condition_source_activation_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_daily",
      "scope_key": "20260609",
      "source_version": "stock_daily_20260609_v1",
      "source_batch_id": "official_daily_ingest_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_daily_basic",
      "scope_key": "20260609",
      "source_version": "stock_daily_basic_20260609_v1",
      "source_batch_id": "condition_source_activation_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_financial",
      "scope_key": "20260609",
      "source_version": "stock_financial_20260609_v1",
      "source_batch_id": "condition_source_activation_20260609_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    }
  ],
  "matched": true
}
```

## Ingest Batch Proof

```json
[
  {
    "batch_id": "condition_source_activation_20260609_v1",
    "trade_date": "20260609",
    "data_domain": "common",
    "data_type": "condition_source_activation",
    "source": "n1.source_facts_20260609.condition_source",
    "source_version": "condition_source_activation_20260609_v1",
    "row_count": 80829,
    "error_count": 0,
    "status": "passed",
    "quality_gate_summary": {
      "expected_rows": {
        "total": 80829,
        "stock_financial": 5513,
        "board_membership": 56962,
        "index_membership": 12841,
        "stock_daily_basic": 5513
      },
      "board_unmapped_raw_count": 8,
      "missing_stock_identity_skip_manifest": [
        {
          "action": "exclude_from_20260608_source_facts",
          "reason": "stock_identity_missing_below_threshold",
          "ts_code": "920206.BJ",
          "severity": "P1",
          "asset_kind": "stock",
          "policy_name": "skip_missing_stock_identity_when_count_lte_10",
          "source_presence": [
            "tushare.daily",
            "tushare.daily_basic"
          ],
          "canonical_identity_key": "stock:BJ:920206",
          "writes_stock_daily_basic": false,
          "writes_stock_daily_bar_fact": false,
          "writes_stock_financial_metrics_fact": false
        }
      ]
    },
    "rollback_strategy": "sql/N1_20260609_source_facts_guarded_runner_rollback.sql",
    "started_at": "2026-06-10 20:47:37.133680+08:00",
    "finished_at": "2026-06-10 20:47:37.133680+08:00"
  },
  {
    "batch_id": "official_daily_ingest_20260609_v1",
    "trade_date": "20260609",
    "data_domain": "common",
    "data_type": "official_daily",
    "source": "n1.source_facts_20260609.official_daily",
    "source_version": "official_daily_ingest_20260609_v1",
    "row_count": 6024,
    "error_count": 0,
    "status": "passed",
    "quality_gate_summary": {
      "p0_count": 0,
      "validation": "passed",
      "p1_skip_policy": true
    },
    "rollback_strategy": "sql/N1_20260609_source_facts_guarded_runner_rollback.sql",
    "started_at": "2026-06-10 20:42:28.192655+08:00",
    "finished_at": "2026-06-10 20:42:28.192655+08:00"
  }
]
```

## Quality Proof

```json
{
  "summary": [
    {
      "source_batch_id": "condition_source_activation_20260609_v1",
      "severity": "P0",
      "status": "passed",
      "count": 12
    },
    {
      "source_batch_id": "condition_source_activation_20260609_v1",
      "severity": "P1",
      "status": "warning",
      "count": 3
    },
    {
      "source_batch_id": "condition_source_activation_20260609_v1",
      "severity": "P2",
      "status": "warning",
      "count": 1
    },
    {
      "source_batch_id": "official_daily_ingest_20260609_v1",
      "severity": "P0",
      "status": "passed",
      "count": 28
    },
    {
      "source_batch_id": "official_daily_ingest_20260609_v1",
      "severity": "P1",
      "status": "warning",
      "count": 4
    }
  ],
  "p0_failed_count": 0
}
```

## Missing Identity Skip Proof

```json
{
  "policy": "skip_missing_stock_identity_when_count_lte_10",
  "threshold": 10,
  "items": [
    {
      "identity_key": "stock:BJ:920206",
      "ts_code": "920206.BJ",
      "absence_counts": {
        "stock_daily_bar_fact": 0,
        "stock_daily_basic": 0,
        "stock_financial_metrics_fact": 0
      },
      "not_written": true,
      "policy_entry": {
        "ts_code": "920206.BJ",
        "canonical_identity_key": "stock:BJ:920206",
        "asset_kind": "stock",
        "reason": "stock_identity_missing_below_threshold",
        "policy_name": "skip_missing_stock_identity_when_count_lte_10",
        "source_presence": [
          "tushare.daily",
          "tushare.daily_basic"
        ],
        "severity": "P1",
        "writes_stock_daily_bar_fact": false,
        "writes_stock_daily_basic": false,
        "writes_stock_financial_metrics_fact": false,
        "action": "exclude_from_20260608_source_facts"
      }
    }
  ],
  "all_not_written": true
}
```

## Forbidden Scope Proof

```json
{
  "transaction_read_only": "on",
  "writes_postgres_in_this_gate": false,
  "rollback_executed": false,
  "writes_outbox": false,
  "event_refs": {
    "common_event_outbox": 0,
    "common_event_inbox": 0
  },
  "checkpoint_refs": {
    "official_daily_ingest_20260609_v1": 0,
    "condition_source_activation_20260609_v1": 0
  },
  "event_refs_total": 0,
  "downstream_refs": {
    "common_condition_run_by_source_trade_date": 0,
    "common_market_data_run_by_source_trade_date": 0,
    "common_trigger_run_by_source_trade_date": 0,
    "common_action_run_by_source_condition_run_id_like_date": 0,
    "user_projection_run_by_source_action_run_id_like_date": 0
  },
  "downstream_refs_total": 0,
  "n2_n3_n4_n5_n6_entered_in_this_gate": false,
  "worker_started": false,
  "realtime_market_pulled": false,
  "old_system_touched": false,
  "proposal_order_trade_sim_position_pnl_real_trade_touched": false
}
```

## Rollback Summary

```json
{
  "path": "sql/N1_20260609_source_facts_guarded_runner_rollback.sql",
  "exists": true,
  "hard_fail_before_delete": true,
  "no_drop_truncate_cascade": true,
  "no_forbidden_table_dml": true,
  "forbidden_table_dml": [],
  "scope_ids_present": true,
  "passed": true
}
```

## Next Gate

`RUNTIME_CONTROL_20260611_N1_TO_N3_A1_FAST_LANE_CATCHUP_READINESS_GATE_REFRESH`
