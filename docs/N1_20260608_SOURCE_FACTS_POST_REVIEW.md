# N1 20260608 Source Facts Post Review

Result: `POST_REVIEW_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260608`
- official batch: `official_daily_ingest_20260608_v1`
- condition batch: `condition_source_activation_20260608_v1`
- combined rows: `86856`
- P0 failed quality gates: `0`
- event refs total: `0`
- downstream refs total: `0`
- rollback_safe: `True`

## Row Count Proof

```json
{
  "expected": {
    "official_daily": {
      "stock_daily_bar_fact": 5514,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "total": 6025
    },
    "condition_source": {
      "stock_daily_basic": 5514,
      "stock_financial_metrics_fact": 5514,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962,
      "total": 80831
    },
    "combined_total": 86856
  },
  "actual": {
    "official_daily": {
      "stock_daily_bar_fact": 5514,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "total": 6025
    },
    "condition_source": {
      "stock_daily_basic": 5514,
      "stock_financial_metrics_fact": 5514,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962,
      "total": 80831
    },
    "combined_total": 86856
  },
  "matched": true
}
```

## Active Source Versions

```json
{
  "expected_source_versions": [
    "stock_daily_20260608_v1",
    "index_daily_20260608_v1",
    "board_daily_20260608_v1",
    "stock_daily_basic_20260608_v1",
    "stock_financial_20260608_v1",
    "index_membership_20260608_v1",
    "board_membership_20260608_v1"
  ],
  "actual_rows": [
    {
      "data_domain": "board",
      "data_type": "board_daily",
      "scope_key": "20260608",
      "source_version": "board_daily_20260608_v1",
      "source_batch_id": "official_daily_ingest_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "board",
      "data_type": "board_membership",
      "scope_key": "TDX:20260608",
      "source_version": "board_membership_20260608_v1",
      "source_batch_id": "condition_source_activation_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "index",
      "data_type": "index_daily",
      "scope_key": "20260608",
      "source_version": "index_daily_20260608_v1",
      "source_batch_id": "official_daily_ingest_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "index",
      "data_type": "index_membership",
      "scope_key": "TDX:20260608",
      "source_version": "index_membership_20260608_v1",
      "source_batch_id": "condition_source_activation_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_daily",
      "scope_key": "20260608",
      "source_version": "stock_daily_20260608_v1",
      "source_batch_id": "official_daily_ingest_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_daily_basic",
      "scope_key": "20260608",
      "source_version": "stock_daily_basic_20260608_v1",
      "source_batch_id": "condition_source_activation_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    },
    {
      "data_domain": "stock",
      "data_type": "stock_financial",
      "scope_key": "20260608",
      "source_version": "stock_financial_20260608_v1",
      "source_batch_id": "condition_source_activation_20260608_v1",
      "previous_source_version": null,
      "activated_by": "n1_20260608_source_facts_guarded_runner"
    }
  ],
  "matched": true
}
```

## Quality Proof

```json
{
  "summary": [
    {
      "source_batch_id": "condition_source_activation_20260608_v1",
      "severity": "P0",
      "status": "passed",
      "count": 12
    },
    {
      "source_batch_id": "condition_source_activation_20260608_v1",
      "severity": "P1",
      "status": "warning",
      "count": 3
    },
    {
      "source_batch_id": "condition_source_activation_20260608_v1",
      "severity": "P2",
      "status": "warning",
      "count": 1
    },
    {
      "source_batch_id": "official_daily_ingest_20260608_v1",
      "severity": "P0",
      "status": "passed",
      "count": 28
    },
    {
      "source_batch_id": "official_daily_ingest_20260608_v1",
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
  "identity_key": "stock:BJ:920206",
  "ts_code": "920206.BJ",
  "absence_counts": {
    "stock_daily_bar_fact": 0,
    "stock_daily_basic": 0,
    "stock_financial_metrics_fact": 0
  },
  "not_written": true
}
```

## Dynamic No-Trade Manifest

```json
{
  "count": 13,
  "identities": [
    {
      "identity_key": "stock:BJ:920305",
      "ts_code": "920305.BJ"
    },
    {
      "identity_key": "stock:BJ:920675",
      "ts_code": "920675.BJ"
    },
    {
      "identity_key": "stock:SH:600228",
      "ts_code": "600228.SH"
    },
    {
      "identity_key": "stock:SH:688121",
      "ts_code": "688121.SH"
    },
    {
      "identity_key": "stock:SZ:000004",
      "ts_code": "000004.SZ"
    },
    {
      "identity_key": "stock:SZ:000638",
      "ts_code": "000638.SZ"
    },
    {
      "identity_key": "stock:SZ:001331",
      "ts_code": "001331.SZ"
    },
    {
      "identity_key": "stock:SZ:002731",
      "ts_code": "002731.SZ"
    },
    {
      "identity_key": "stock:SZ:002808",
      "ts_code": "002808.SZ"
    },
    {
      "identity_key": "stock:SZ:002898",
      "ts_code": "002898.SZ"
    },
    {
      "identity_key": "stock:SZ:300029",
      "ts_code": "300029.SZ"
    },
    {
      "identity_key": "stock:SZ:300114",
      "ts_code": "300114.SZ"
    },
    {
      "identity_key": "stock:SZ:300831",
      "ts_code": "300831.SZ"
    }
  ]
}
```

## Forbidden Scope Proof

```json
{
  "event_refs": {
    "common_event_outbox.source_run_id": 0,
    "common_event_inbox.source_run_id": 0,
    "common_event_ledger.source_run_id": 0,
    "common_event_consumer_checkpoint.payload": 0
  },
  "run_refs": {
    "common_condition_run.run_id": 0,
    "common_market_data_run.run_id": 0,
    "common_trigger_run.run_id": 0,
    "common_action_run.run_id": 0
  },
  "downstream_batch_refs": {
    "board_condition_basis": 0,
    "index_condition_basis": 0,
    "n6_board_membership_display_cache": 0,
    "n6_index_membership_display_cache": 0,
    "stock_condition_basis": 0
  },
  "downstream_refs_nonzero": {},
  "downstream_refs_total": 0,
  "downstream_ref_method": "events by source_run_id, checkpoints by checkpoint_payload, layer runs by run_id, downstream user/condition batch-bearing projections by source_batch_id",
  "writes_parquet": false,
  "writes_outbox": false,
  "writes_inbox_or_checkpoint": false,
  "enters_n2_n3_n4_n5_n6": false,
  "worker_started": false,
  "old_system_touched": false,
  "real_trading": false,
  "rollback_sql_executed": false,
  "event_refs_total": 0
}
```

## Rollback Proof

```json
{
  "rollback_sql_path": "sql/N1_20260608_source_facts_guarded_runner_rollback.sql",
  "rollback_static_check": {
    "path": "sql/N1_20260608_source_facts_guarded_runner_rollback.sql",
    "hard_fail_before_delete": true,
    "no_drop_truncate_cascade": true,
    "no_forbidden_table_dml": true,
    "forbidden_table_dml": [],
    "scope_ids_present": true,
    "passed": true
  },
  "rollback_safe": true,
  "rollback_executed": false
}
```
