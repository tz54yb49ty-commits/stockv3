{
  "stage": "N1 condition source activation 20260605 execute preflight",
  "layer_role": "N1_ingestion",
  "result": "PREFLIGHT_PASS",
  "blocked": false,
  "blockers": [],
  "trade_date": "20260609",
  "source_batch_id": "condition_source_activation_20260609_v1",
  "source_versions": {
    "stock_daily_basic": "stock_daily_basic_20260609_v1",
    "stock_financial": "stock_financial_20260609_v1",
    "index_membership": "index_membership_20260609_v1",
    "board_membership": "board_membership_20260609_v1"
  },
  "expected_rows": {
    "stock_daily_basic": 5513,
    "stock_financial": 5513,
    "index_membership": 12841,
    "board_membership": 56962,
    "total": 80829
  },
  "baseline": {
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
      "common_event_outbox": 198634,
      "common_event_inbox": 110805,
      "common_event_consumer_checkpoint": 19505
    }
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 2,
    "p2_count": 1
  },
  "quality_items": [
    {
      "gate_name": "upstream_stock_daily_active",
      "severity": "P0",
      "status": "passed",
      "expected_value": "active stock_daily rows > 0",
      "actual_value": "5513",
      "details": {}
    },
    {
      "gate_name": "condition_stock_universe_expected_scope",
      "severity": "P0",
      "status": "passed",
      "expected_value": "5513",
      "actual_value": "5513",
      "details": {
        "official_daily_bar_universe": 5513,
        "condition_source_gap_manifest_rows": 13
      }
    },
    {
      "gate_name": "official_no_trade_excluded_from_condition_universe",
      "severity": "P1",
      "status": "warning",
      "expected_value": "0 official no-trade rows required in condition source",
      "actual_value": "13",
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
            "identity_key": "stock:SZ:002160",
            "ts_code": "002160.SZ",
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
  "runner_readiness": "ready_for_final_gate",
  "execute_authorized": false,
  "final_gate_required": true,
  "final_execute_gate_allowed": true,
  "execute_runner_implemented": true,
  "postgres_commit_implemented": true,
  "execute_flags_seen": {
    "execute": true,
    "user_confirmed": true,
    "postgres_commit_enabled": true
  },
  "expected_future_writes": {
    "allowed_tables": [
      "common_ingest_batch",
      "common_quality_gate_result",
      "common_active_source_version",
      "stock_daily_basic",
      "stock_financial_metrics_fact",
      "index_membership_fact",
      "board_membership_fact"
    ],
    "writes_postgres": true,
    "writes_parquet": false,
    "updates_active_source_version": true,
    "writes_outbox": false,
    "enters_n2_n3_n4_n5_n6": false
  },
  "execute_command_template": "PYTHONPATH=src python3 scripts/run_condition_source_activation_20260605_once.py --execute --user-confirmed --postgres-commit-enabled --execute-report-json docs/N1_20260609_SOURCE_FACTS_EXECUTE_REPORT.json --execute-report-md docs/N1_20260609_SOURCE_FACTS_EXECUTE_REPORT.md",
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
  "rollback_sql_path": "sql/N1_20260609_source_facts_guarded_runner_rollback.sql",
  "generated_at": "2026-06-10T20:47:09+08:00"
}
