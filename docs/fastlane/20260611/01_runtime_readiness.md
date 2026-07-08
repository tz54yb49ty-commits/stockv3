# 20260611 N1 -> N3-A1 Fast Lane Catch-up Readiness

Result: `READINESS_PASS`

- for_trade_date: `20260611`
- source_trade_date: `20260610` from `common_trade_calendar(20260611).prev_trade_date`
- decision: `READY_FOR_MANUAL_LAYER_SEQUENCE_N2_THEN_N3_A1`
- N1 source facts: `True`
- N2 baseline clean: `True`
- N3-A1 baseline clean: `True`

## Calendar Proof

```json
{
  "rows": [
    {
      "trade_date": "20260609",
      "is_open": true,
      "prev_trade_date": "20260608",
      "next_trade_date": "20260610",
      "source_batch_id": "trade_calendar_20260609_repair_v1",
      "source_version": "trade_calendar_20260609_repair_v1"
    },
    {
      "trade_date": "20260610",
      "is_open": true,
      "prev_trade_date": "20260609",
      "next_trade_date": "20260611",
      "source_batch_id": "trade_calendar_20260610_repair_v1",
      "source_version": "trade_calendar_20260610_repair_v1"
    },
    {
      "trade_date": "20260611",
      "is_open": true,
      "prev_trade_date": "20260610",
      "next_trade_date": "20260612",
      "source_batch_id": "trade_calendar_20260611_repair_v1",
      "source_version": "trade_calendar_20260611_repair_v1"
    }
  ],
  "calendar_ok": true
}
```

## N1 Source Facts Proof

```json
{
  "counts": {
    "20260609": {
      "stock_daily_bar_fact": 5513,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "stock_daily_basic": 5513,
      "stock_financial_metrics_fact": 5513,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962
    },
    "20260610": {
      "stock_daily_bar_fact": 5510,
      "index_daily_bar_fact": 83,
      "board_daily_bar_fact": 428,
      "stock_daily_basic": 5510,
      "stock_financial_metrics_fact": 5510,
      "index_membership_fact": 12841,
      "board_membership_fact": 56962
    }
  },
  "active_source_versions": {
    "20260609": [
      {
        "data_domain": "board",
        "data_type": "board_daily",
        "scope_key": "20260609",
        "source_version": "board_daily_20260609_v1",
        "source_batch_id": "official_daily_ingest_20260609_v1"
      },
      {
        "data_domain": "board",
        "data_type": "board_membership",
        "scope_key": "TDX:20260609",
        "source_version": "board_membership_20260609_v1",
        "source_batch_id": "condition_source_activation_20260609_v1"
      },
      {
        "data_domain": "index",
        "data_type": "index_daily",
        "scope_key": "20260609",
        "source_version": "index_daily_20260609_v1",
        "source_batch_id": "official_daily_ingest_20260609_v1"
      },
      {
        "data_domain": "index",
        "data_type": "index_membership",
        "scope_key": "TDX:20260609",
        "source_version": "index_membership_20260609_v1",
        "source_batch_id": "condition_source_activation_20260609_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily",
        "scope_key": "20260609",
        "source_version": "stock_daily_20260609_v1",
        "source_batch_id": "official_daily_ingest_20260609_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily_basic",
        "scope_key": "20260609",
        "source_version": "stock_daily_basic_20260609_v1",
        "source_batch_id": "condition_source_activation_20260609_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": "20260609",
        "source_version": "stock_financial_20260609_v1",
        "source_batch_id": "condition_source_activation_20260609_v1"
      }
    ],
    "20260610": [
      {
        "data_domain": "board",
        "data_type": "board_daily",
        "scope_key": "20260610",
        "source_version": "board_daily_20260610_v1",
        "source_batch_id": "official_daily_ingest_20260610_v1"
      },
      {
        "data_domain": "board",
        "data_type": "board_membership",
        "scope_key": "TDX:20260610",
        "source_version": "board_membership_20260610_v1",
        "source_batch_id": "condition_source_activation_20260610_v1"
      },
      {
        "data_domain": "index",
        "data_type": "index_daily",
        "scope_key": "20260610",
        "source_version": "index_daily_20260610_v1",
        "source_batch_id": "official_daily_ingest_20260610_v1"
      },
      {
        "data_domain": "index",
        "data_type": "index_membership",
        "scope_key": "TDX:20260610",
        "source_version": "index_membership_20260610_v1",
        "source_batch_id": "condition_source_activation_20260610_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily",
        "scope_key": "20260610",
        "source_version": "stock_daily_20260610_v1",
        "source_batch_id": "official_daily_ingest_20260610_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily_basic",
        "scope_key": "20260610",
        "source_version": "stock_daily_basic_20260610_v1",
        "source_batch_id": "condition_source_activation_20260610_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": "20260610",
        "source_version": "stock_financial_20260610_v1",
        "source_batch_id": "condition_source_activation_20260610_v1"
      }
    ]
  },
  "post_reviews": {
    "20260609": {
      "artifact": "docs/N1_20260609_SOURCE_FACTS_POST_REVIEW.json",
      "result": "POST_REVIEW_PASS",
      "combined_total": 86853,
      "p0_failed": 0
    },
    "20260610": {
      "artifact": "docs/N1_20260610_SOURCE_FACTS_POST_REVIEW.json",
      "result": "POST_REVIEW_PASS",
      "combined_total": 86844,
      "p0_failed": 0
    }
  },
  "n1_ok": true
}
```

## Runner Capability

```json
{
  "generic_guarded_n1_source_facts_runner": "implemented",
  "script": "scripts/run_n1_source_facts_once.py",
  "forbidden_runner": "scripts/run_real_daily_incremental.py",
  "fastlane_wrapper_real_orchestration": "not_complete_report_only_gap"
}
```

## N2 Baseline

```json
{
  "existing_runs": [],
  "expected_new_run_id": "condition_layer_20260610_source_20260610_for_20260611_v1",
  "clean": true
}
```

## N3-A1 Baseline

```json
{
  "existing_market_data_runs_for_20260611": [],
  "expected_subscription_run_id": "market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1",
  "expected_preload_data_trade_date": "20260610",
  "clean": true
}
```

## Forbidden Scope Proof

```json
{
  "execute_performed": false,
  "database_written": false,
  "rollback_executed": false,
  "outbox_inbox_checkpoint_consumed_or_updated": false,
  "worker_started": false,
  "entered_n3_b_c_b2_n4_n5_n6": false,
  "realtime_market_pulled": false,
  "old_system_touched": false,
  "proposal_order_trade_sim_position_pnl_real_trade": false
}
```

Next gate: `N2_20260611_CONDITION_LAYER_DRY_RUN_PREFLIGHT_GATE`
