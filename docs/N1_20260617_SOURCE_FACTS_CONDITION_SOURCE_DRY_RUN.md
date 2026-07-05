{
  "stage": "N1 condition source activation 20260605 dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_BLOCKED",
  "blocked": true,
  "blockers": [
    "target_fact_already_exists",
    "target_source_version_conflict",
    "active_source_version_conflict",
    "condition_source_batch_conflict"
  ],
  "trade_date": "20260617",
  "source_batch_id": "condition_source_activation_20260617_v1",
  "source_versions": {
    "stock_daily_basic": "stock_daily_basic_20260617_v1",
    "stock_financial": "stock_financial_20260617_v1",
    "index_membership": "index_membership_20260617_v1",
    "board_membership": "board_membership_20260617_v1"
  },
  "expected_rows": {
    "stock_daily_basic": 5505,
    "stock_financial": 5505,
    "index_membership": 12841,
    "board_membership": 56962,
    "total": 80813
  },
  "condition_universe_summary": {
    "official_daily_stock_rows": 5505,
    "condition_stock_rows": 5505,
    "official_no_trade_excluded": 21,
    "stale_identity_manifest_rows": 1
  },
  "membership_summary": {
    "source_available": true,
    "tdx_root": "/Volumes/MacRaid/tdxdata/tdx",
    "index_membership": {
      "raw_rows": 12841,
      "filtered_rows": 12841,
      "missing_index_identity": 0,
      "missing_stock_identity": 0,
      "unmapped_raw_count": 0,
      "unmapped_unique_identity_count": 0,
      "duplicate_rows": 0,
      "raw_hash": "74e4dfb95d44d8f1ece7e6d082160b8038054f6c9838d30a24ee9791ede08883"
    },
    "board_membership": {
      "raw_rows": 56970,
      "filtered_rows": 56962,
      "missing_board_identity": 0,
      "missing_stock_identity": 6,
      "unmapped_raw_count": 8,
      "unmapped_unique_identity_count": 6,
      "duplicate_rows": 0,
      "raw_hash": "a4a48be38c9f76d0aaf0152d49f308ac43e3dd06b91d3c43c5879cf77523ad14"
    }
  },
  "baseline": {
    "upstream_daily": {
      "stock_daily": {
        "active_source_version": "stock_daily_20260617_v1",
        "row_count": 5505
      },
      "index_daily": {
        "active_source_version": "index_daily_20260617_v1",
        "row_count": 83
      },
      "board_daily": {
        "active_source_version": "board_daily_20260617_v1",
        "row_count": 427
      }
    },
    "current_target_fact_rows": {
      "stock_daily_basic": 5505,
      "stock_financial": 5505,
      "index_membership": 12841,
      "board_membership": 56962
    },
    "active_target_source_versions": [
      {
        "data_domain": "board",
        "data_type": "board_membership",
        "scope_key": "TDX:20260617",
        "source_version": "board_membership_20260617_v1",
        "source_batch_id": "condition_source_activation_20260617_v1",
        "previous_source_version": null
      },
      {
        "data_domain": "index",
        "data_type": "index_membership",
        "scope_key": "TDX:20260617",
        "source_version": "index_membership_20260617_v1",
        "source_batch_id": "condition_source_activation_20260617_v1",
        "previous_source_version": null
      },
      {
        "data_domain": "stock",
        "data_type": "stock_daily_basic",
        "scope_key": "20260617",
        "source_version": "stock_daily_basic_20260617_v1",
        "source_batch_id": "condition_source_activation_20260617_v1",
        "previous_source_version": null
      },
      {
        "data_domain": "stock",
        "data_type": "stock_financial",
        "scope_key": "20260617",
        "source_version": "stock_financial_20260617_v1",
        "source_batch_id": "condition_source_activation_20260617_v1",
        "previous_source_version": null
      }
    ],
    "target_source_version_conflicts": {
      "stock_daily_basic": 5505,
      "stock_financial": 5505,
      "index_membership": 12841,
      "board_membership": 56962
    },
    "contract_batch_exists": true,
    "event_counts": {
      "common_event_outbox": 663681,
      "common_event_inbox": 188649,
      "common_event_consumer_checkpoint": 58923
    }
  },
  "quality": {
    "p0_count": 4,
    "p1_count": 2,
    "p2_count": 1
  },
  "quality_items": [
    {
      "gate_name": "upstream_stock_daily_active",
      "severity": "P0",
      "status": "passed",
      "expected_value": "active stock_daily rows > 0",
      "actual_value": "5505",
      "details": {}
    },
    {
      "gate_name": "condition_stock_universe_expected_scope",
      "severity": "P0",
      "status": "passed",
      "expected_value": "5505",
      "actual_value": "5505",
      "details": {
        "official_daily_bar_universe": 5505,
        "condition_source_gap_manifest_rows": 21
      }
    },
    {
      "gate_name": "official_no_trade_excluded_from_condition_universe",
      "severity": "P1",
      "status": "warning",
      "expected_value": "0 official no-trade rows required in condition source",
      "actual_value": "21",
      "details": {
        "manifest": [
          {
            "identity_key": "stock:BJ:920305",
            "ts_code": "920305.BJ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:BJ:920675",
            "ts_code": "920675.BJ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600228",
            "ts_code": "600228.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600717",
            "ts_code": "600717.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:603137",
            "ts_code": "603137.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:603159",
            "ts_code": "603159.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:603721",
            "ts_code": "603721.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:688121",
            "ts_code": "688121.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:688143",
            "ts_code": "688143.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:688287",
            "ts_code": "688287.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:688689",
            "ts_code": "688689.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:000004",
            "ts_code": "000004.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:000638",
            "ts_code": "000638.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:001331",
            "ts_code": "001331.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:002496",
            "ts_code": "002496.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:002731",
            "ts_code": "002731.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:002808",
            "ts_code": "002808.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:002898",
            "ts_code": "002898.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:300029",
            "ts_code": "300029.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:300411",
            "ts_code": "300411.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:300665",
            "ts_code": "300665.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          }
        ],
        "writes_target_fact": false
      }
    },
    {
      "gate_name": "index_membership_local_tdx_available",
      "severity": "P0",
      "status": "passed",
      "expected_value": "local TDX index membership rows > 0",
      "actual_value": "12841",
      "details": {}
    },
    {
      "gate_name": "board_membership_local_tdx_available",
      "severity": "P0",
      "status": "passed",
      "expected_value": "local TDX board membership rows > 0",
      "actual_value": "56962",
      "details": {}
    },
    {
      "gate_name": "index_membership_unique_key",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 duplicates",
      "actual_value": "0",
      "details": {}
    },
    {
      "gate_name": "board_membership_unique_key",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 duplicates",
      "actual_value": "0",
      "details": {}
    },
    {
      "gate_name": "target_fact_already_exists",
      "severity": "P0",
      "status": "failed",
      "expected_value": "0 existing 20260605 target fact rows",
      "actual_value": "{'stock_daily_basic': 5505, 'stock_financial': 5505, 'index_membership': 12841, 'board_membership': 56962}",
      "details": {}
    },
    {
      "gate_name": "target_source_version_conflict",
      "severity": "P0",
      "status": "failed",
      "expected_value": "0 target source_version conflicts",
      "actual_value": "{'stock_daily_basic': 5505, 'stock_financial': 5505, 'index_membership': 12841, 'board_membership': 56962}",
      "details": {}
    },
    {
      "gate_name": "active_source_version_conflict",
      "severity": "P0",
      "status": "failed",
      "expected_value": "0 target active source rows",
      "actual_value": "4",
      "details": {}
    },
    {
      "gate_name": "condition_source_batch_conflict",
      "severity": "P0",
      "status": "failed",
      "expected_value": "batch absent",
      "actual_value": "True",
      "details": {}
    },
    {
      "gate_name": "rollback_sql_scope_available",
      "severity": "P0",
      "status": "passed",
      "expected_value": "delete by batch/source_version/trade_date and restore/delete active",
      "actual_value": "available",
      "details": {}
    },
    {
      "gate_name": "forbidden_scope_excluded",
      "severity": "P0",
      "status": "passed",
      "expected_value": "no daily bar, no Parquet, no outbox, no N2-N6",
      "actual_value": "excluded",
      "details": {}
    },
    {
      "gate_name": "board_unmapped_raw_count_filtered",
      "severity": "P2",
      "status": "warning",
      "expected_value": "0",
      "actual_value": "8",
      "details": {
        "raw_unmapped": 8,
        "unique_identity_unmapped": 6,
        "action": "filtered",
        "blocking": false
      }
    },
    {
      "gate_name": "stale_identity_manifest_only",
      "severity": "P1",
      "status": "warning",
      "expected_value": "0",
      "actual_value": "1",
      "details": {
        "manifest": [
          {
            "identity_key": "stock:SZ:300114",
            "ts_code": "300114.SZ",
            "name": "中航成飞",
            "disposition": "exclude_from_expected_universe",
            "severity": "P1",
            "superseded_by_identity_key": "stock:SZ:302132"
          }
        ],
        "writes_identity": false
      }
    }
  ],
  "side_effects": {
    "writes_postgres": false,
    "writes_parquet": false,
    "updates_active_source_version": false,
    "writes_outbox": false,
    "writes_inbox_or_checkpoint": false,
    "enters_n2_n3_n4_n5_n6": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trading": false
  },
  "rollback_sql_path": "sql/N1_20260617_source_facts_guarded_runner_rollback.sql",
  "generated_at": "2026-06-17T21:33:52+08:00"
}
