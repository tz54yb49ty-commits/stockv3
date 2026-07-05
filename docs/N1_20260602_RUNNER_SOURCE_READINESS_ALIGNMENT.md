# N1 20260602 Runner Source Readiness Alignment

```json
{
  "stage": "N1_20260602 runner/source readiness alignment gate",
  "layer_role": "N1_ingestion",
  "result": "BLOCKED",
  "source_trade_date": "20260602",
  "for_trade_date": "20260603",
  "runners": {
    "official_daily": {
      "exists": true,
      "default_execute": false,
      "script": "scripts/run_official_daily_ingestion_20260602_once.py",
      "module": "ashare_v3.ingestion.n1_20260602_runner_alignment"
    },
    "condition_source": {
      "exists": true,
      "default_execute": false,
      "script": "scripts/run_condition_source_activation_20260602_once.py",
      "module": "ashare_v3.ingestion.n1_20260602_runner_alignment"
    }
  },
  "blockers": [
    "official_daily_baseline_clean"
  ],
  "source_readiness": {
    "tushare_token_present": true,
    "tushare_fallback_approved": false,
    "tdx_root": "/Volumes/MacRaid/tdxdata/tdx",
    "tdx_root_exists": true,
    "tdx_root_readable": true,
    "mootdx_import_present": true,
    "tdx_mootdx_local_source_available": true,
    "source_fetch_boundary": {
      "live_fetch_performed": false,
      "external_tushare_fetch_performed": false,
      "external_mootdx_fetch_performed": false
    },
    "p0_blockers": []
  },
  "expected_scope": {
    "official_daily": {
      "stock_scope_basis": {
        "active_stock_identity": 5526,
        "daily_bar_rows": "TBD_after_Tushare_daily_adj_factor_source_probe"
      },
      "index_scope_basis": {
        "fixed_9_present": 9,
        "fixed_9_missing": [],
        "daily_bar_rows": "TBD_after_Mootdx_Tushare_BJ_source_probe"
      },
      "board_scope_basis": {
        "board_identity_total": 428,
        "industry_881": 127,
        "daily_bar_rows": "TBD_after_TDX_Mootdx_source_probe"
      }
    },
    "condition_source": {
      "stock_daily_basic": "blocked_until_official_daily_20260602_passed",
      "stock_financial": "blocked_until_official_daily_20260602_passed",
      "index_membership": "TBD_after_TDX_membership_validation",
      "board_membership": "TBD_after_TDX_membership_validation"
    }
  },
  "planned_ids": {
    "official_daily": {
      "source_batch_id": "official_daily_ingest_20260602_v1",
      "source_versions": {
        "stock": "stock_daily_20260602_v1",
        "index": "index_daily_20260602_v1",
        "board": "board_daily_20260602_v1"
      }
    },
    "condition_source": {
      "source_batch_id": "condition_source_activation_20260602_v1",
      "source_versions": {
        "stock_daily_basic": "stock_daily_basic_20260602_v1",
        "stock_financial": "stock_financial_20260602_v1",
        "index_membership": "index_membership_20260602_v1",
        "board_membership": "board_membership_20260602_v1"
      }
    }
  },
  "baseline": {
    "source_trade_date": "20260602",
    "for_trade_date": "20260603",
    "calendar": {
      "trade_date": "20260602",
      "is_open": true,
      "prev_trade_date": "20260601",
      "next_trade_date": "20260603",
      "source_version": "trade_calendar_20260602_patch_v1",
      "row_count": 1
    },
    "next_calendar": {
      "trade_date": "20260603",
      "row_count": 0
    },
    "official_daily_rows": {
      "stock": 5507,
      "index": 83,
      "board": 428,
      "total": 6018
    },
    "condition_source_rows": {
      "stock_daily_basic": 0,
      "stock_financial": 0,
      "index_membership": 0,
      "board_membership": 0,
      "total": 0
    },
    "official_batch_conflict": 1,
    "official_quality_conflict": 31,
    "official_active_conflict": 3,
    "condition_batch_conflict": 0,
    "condition_quality_conflict": 0,
    "condition_active_conflict": 0,
    "active_daily_source_versions": [
      {
        "data_domain": "board",
        "data_type": "board_daily",
        "scope_key": "20260602",
        "source_version": "board_daily_20260602_v1",
        "source_batch_id": "official_daily_ingest_20260602_v1"
      },
      {
        "data_domain": "index",
        "data_type": "index_daily",
        "scope_key": "20260602",
        "source_version": "index_daily_20260602_v1",
        "source_batch_id": "official_daily_ingest_20260602_v1"
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily",
        "scope_key": "20260602",
        "source_version": "stock_daily_20260602_v1",
        "source_batch_id": "official_daily_ingest_20260602_v1"
      }
    ],
    "active_condition_source_versions": [],
    "scope_basis": {
      "stock_identity_active_universe": 5526,
      "fixed_9_index_present": 9,
      "fixed_9_index_missing": [],
      "index_identity_active": null,
      "board_identity_total": 428,
      "board_881": 127
    },
    "event_counts": {
      "outbox": 164214,
      "inbox": 68560,
      "checkpoint": 5163
    },
    "read_only_database_checks": true
  },
  "rollback": {
    "official_daily": {
      "path": "sql/N1_official_daily_20260602_ingestion_rollback.sql",
      "result": "ROLLBACK_SCOPE_PASS",
      "hard_fail_before_delete": true,
      "required_tokens_present": {
        "official_daily_ingest_20260602_v1": true,
        "stock_daily_20260602_v1": true,
        "index_daily_20260602_v1": true,
        "board_daily_20260602_v1": true
      },
      "forbidden_scope_touched": false
    },
    "condition_source": {
      "path": "sql/N1_condition_source_20260602_activation_rollback.sql",
      "result": "ROLLBACK_SCOPE_PASS",
      "hard_fail_before_delete": true,
      "required_tokens_present": {
        "condition_source_activation_20260602_v1": true,
        "stock_daily_basic_20260602_v1": true,
        "stock_financial_20260602_v1": true,
        "index_membership_20260602_v1": true,
        "board_membership_20260602_v1": true
      },
      "forbidden_scope_touched": false
    }
  },
  "quality": {
    "p0_count": 1,
    "p1_count": 1,
    "p2_count": 0,
    "p0_items": [
      "official_daily_baseline_clean"
    ]
  },
  "side_effects": {
    "writes_database": false,
    "postgres_fact_written": false,
    "parquet_written": false,
    "condition_source_written": false,
    "executes_n1_n6": false,
    "enters_n2_n3_a1": false,
    "enters_n2_n3_n4_n5_n6": false,
    "consumes_outbox": false,
    "starts_worker": false,
    "delivery_or_notification": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "return_to_dry_run_preflight_gate": true,
  "generated_at": "2026-06-03T04:20:10+08:00"
}
```
