{
  "stage": "N1 condition source activation 20260605 dry-run",
  "layer_role": "N1_ingestion",
  "result": "DRY_RUN_PASS",
  "blocked": false,
  "blockers": [],
  "trade_date": "20260709",
  "source_batch_id": "condition_source_activation_20260709_v1",
  "source_versions": {
    "stock_daily_basic": "stock_daily_basic_20260709_v1",
    "stock_financial": "stock_financial_20260709_v1",
    "index_membership": "index_membership_20260709_v1",
    "board_membership": "board_membership_20260709_v1"
  },
  "expected_rows": {
    "stock_daily_basic": 5508,
    "stock_financial": 5508,
    "index_membership": 15360,
    "board_membership": 57045,
    "total": 83421
  },
  "condition_universe_summary": {
    "official_daily_stock_rows": 5508,
    "condition_stock_rows": 5508,
    "official_no_trade_excluded": 18,
    "stale_identity_manifest_rows": 1
  },
  "membership_summary": {
    "source_available": true,
    "tdx_root": "/Volumes/MacRaid/tdxdata/tdx",
    "index_membership": {
      "raw_rows": 15361,
      "filtered_rows": 15360,
      "missing_index_identity": 0,
      "missing_stock_identity": 1,
      "unmapped_raw_count": 1,
      "unmapped_unique_identity_count": 1,
      "duplicate_rows": 0,
      "raw_hash": "556a759974716954ebc9d14488ab4a7b6a62c5f6080fe8a0ca9c72f586d7f830"
    },
    "board_membership": {
      "raw_rows": 57147,
      "filtered_rows": 57045,
      "missing_board_identity": 2,
      "missing_stock_identity": 16,
      "unmapped_raw_count": 102,
      "unmapped_unique_identity_count": 18,
      "duplicate_rows": 0,
      "raw_hash": "f18a23897df192c36ceb8c0bc072c3e8f222567e49d4000b40cb84b56bb83363"
    }
  },
  "baseline": {
    "upstream_daily": {
      "stock_daily": {
        "active_source_version": "stock_daily_20260709_v1",
        "row_count": 5508
      },
      "index_daily": {
        "active_source_version": "index_daily_20260709_v1",
        "row_count": 83
      },
      "board_daily": {
        "active_source_version": "board_daily_20260709_v1",
        "row_count": 427
      }
    },
    "current_target_fact_rows": {
      "stock_daily_basic": 0,
      "stock_financial": 0,
      "index_membership": 0,
      "board_membership": 0
    },
    "active_target_source_versions": [],
    "target_source_version_conflicts": {
      "stock_daily_basic": 0,
      "stock_financial": 0,
      "index_membership": 0,
      "board_membership": 0
    },
    "contract_batch_exists": false,
    "event_counts": {
      "common_event_outbox": 13266,
      "common_event_inbox": 8397,
      "common_event_consumer_checkpoint": 10977
    }
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 3,
    "p2_count": 1
  },
  "quality_items": [
    {
      "gate_name": "upstream_stock_daily_active",
      "severity": "P0",
      "status": "passed",
      "expected_value": "active stock_daily rows > 0",
      "actual_value": "5508",
      "details": {}
    },
    {
      "gate_name": "condition_stock_universe_expected_scope",
      "severity": "P0",
      "status": "passed",
      "expected_value": "5508",
      "actual_value": "5508",
      "details": {
        "official_daily_bar_universe": 5508,
        "condition_source_gap_manifest_rows": 18
      }
    },
    {
      "gate_name": "official_no_trade_excluded_from_condition_universe",
      "severity": "P1",
      "status": "warning",
      "expected_value": "0 official no-trade rows required in condition source",
      "actual_value": "18",
      "details": {
        "manifest": [
          {
            "identity_key": "stock:SH:600193",
            "ts_code": "600193.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600405",
            "ts_code": "600405.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600421",
            "ts_code": "600421.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600491",
            "ts_code": "600491.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600599",
            "ts_code": "600599.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600608",
            "ts_code": "600608.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600636",
            "ts_code": "600636.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:600696",
            "ts_code": "600696.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:601369",
            "ts_code": "601369.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:603580",
            "ts_code": "603580.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:605081",
            "ts_code": "605081.SH",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SH:688072",
            "ts_code": "688072.SH",
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
            "identity_key": "stock:SZ:000008",
            "ts_code": "000008.SZ",
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
            "identity_key": "stock:SZ:300214",
            "ts_code": "300214.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:300567",
            "ts_code": "300567.SZ",
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": false,
            "condition_source_available": false,
            "tushare_suspend_d_present": true,
            "bak_daily_zero_volume_present": true,
            "action": "exclude_from_condition_universe",
            "severity": "P1"
          },
          {
            "identity_key": "stock:SZ:301234",
            "ts_code": "301234.SZ",
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
      "actual_value": "15360",
      "details": {}
    },
    {
      "gate_name": "board_membership_local_tdx_available",
      "severity": "P0",
      "status": "passed",
      "expected_value": "local TDX board membership rows > 0",
      "actual_value": "57045",
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
      "status": "passed",
      "expected_value": "0 existing 20260605 target fact rows",
      "actual_value": "{'stock_daily_basic': 0, 'stock_financial': 0, 'index_membership': 0, 'board_membership': 0}",
      "details": {}
    },
    {
      "gate_name": "target_source_version_conflict",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 target source_version conflicts",
      "actual_value": "{'stock_daily_basic': 0, 'stock_financial': 0, 'index_membership': 0, 'board_membership': 0}",
      "details": {}
    },
    {
      "gate_name": "active_source_version_conflict",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 target active source rows",
      "actual_value": "0",
      "details": {}
    },
    {
      "gate_name": "condition_source_batch_conflict",
      "severity": "P0",
      "status": "passed",
      "expected_value": "batch absent",
      "actual_value": "False",
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
      "actual_value": "102",
      "details": {
        "raw_unmapped": 102,
        "unique_identity_unmapped": 18,
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
    },
    {
      "gate_name": "board_membership_row_count_changed_from_recent_active",
      "severity": "P1",
      "status": "warning",
      "expected_value": "56962",
      "actual_value": "57045",
      "details": {
        "action": "reviewed_against_current_local_tdx_txt",
        "blocking": false
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
  "rollback_sql_path": "sql/N1_20260709_source_facts_guarded_runner_rollback.sql",
  "generated_at": "2026-07-09T18:01:35+08:00"
}
