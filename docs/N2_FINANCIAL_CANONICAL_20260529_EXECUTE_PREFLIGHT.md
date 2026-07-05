# N2 Financial Canonical 20260529 Execute Preflight

result = PREFLIGHT_PASS

- execute_allowed: `True`
- blocked_reasons: `[]`
- schema_ready: `True`
- stock_financial_fields_ready: `True`
- writes_performed=false; will_execute_sql=false

```json
{
  "stage": "N2-E2",
  "plan_mode": "condition_layer_execute_preflight",
  "source_trade_date": "20260529",
  "for_trade_date": "20260601",
  "prev_trade_date": "20260529",
  "run_id_preview": "condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute",
  "readiness_plan_id": "condition_layer_20260529_to_20260601_execute",
  "policy_name": "default_adjusted_by_user",
  "policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
  "expected_row_counts": {
    "common_condition_run": 1,
    "common_condition_quality_item": 78,
    "stock_monitor_target": 5506,
    "index_monitor_target": 83,
    "board_monitor_target": 428,
    "stock_condition_basis": 5506,
    "index_condition_basis": 83,
    "board_condition_basis": 428,
    "stock_condition_pool": 4106,
    "index_condition_pool": 187,
    "board_condition_pool": 942,
    "index_minute_target_scope": 187,
    "board_minute_target_scope": 942,
    "stock_minute_target_scope": 4087
  },
  "expected_hash": "318e36deeaf5444764a1fafab8722e5bc5db88f9e1f88a69745232350439496f",
  "quality_summary": {
    "p0_count": 0,
    "p1_count": 6,
    "p2_count": 3
  },
  "schema_status": {
    "schema_ready": true,
    "required_tables": [
      "common_condition_run",
      "common_condition_quality_item",
      "stock_monitor_target",
      "index_monitor_target",
      "board_monitor_target",
      "stock_condition_basis",
      "index_condition_basis",
      "board_condition_basis",
      "stock_condition_pool",
      "index_condition_pool",
      "board_condition_pool",
      "stock_minute_target_scope",
      "index_minute_target_scope",
      "board_minute_target_scope"
    ],
    "table_status": {
      "common_condition_run": {
        "exists": true,
        "regclass": "public.common_condition_run"
      },
      "common_condition_quality_item": {
        "exists": true,
        "regclass": "public.common_condition_quality_item"
      },
      "stock_monitor_target": {
        "exists": true,
        "regclass": "public.stock_monitor_target"
      },
      "index_monitor_target": {
        "exists": true,
        "regclass": "public.index_monitor_target"
      },
      "board_monitor_target": {
        "exists": true,
        "regclass": "public.board_monitor_target"
      },
      "stock_condition_basis": {
        "exists": true,
        "regclass": "public.stock_condition_basis"
      },
      "index_condition_basis": {
        "exists": true,
        "regclass": "public.index_condition_basis"
      },
      "board_condition_basis": {
        "exists": true,
        "regclass": "public.board_condition_basis"
      },
      "stock_condition_pool": {
        "exists": true,
        "regclass": "public.stock_condition_pool"
      },
      "index_condition_pool": {
        "exists": true,
        "regclass": "public.index_condition_pool"
      },
      "board_condition_pool": {
        "exists": true,
        "regclass": "public.board_condition_pool"
      },
      "stock_minute_target_scope": {
        "exists": true,
        "regclass": "public.stock_minute_target_scope"
      },
      "index_minute_target_scope": {
        "exists": true,
        "regclass": "public.index_minute_target_scope"
      },
      "board_minute_target_scope": {
        "exists": true,
        "regclass": "public.board_minute_target_scope"
      }
    },
    "missing_tables": [],
    "canonical_target_schema_tables": [
      "stock_condition_basis",
      "index_condition_basis",
      "board_condition_basis",
      "stock_condition_pool",
      "index_condition_pool",
      "board_condition_pool",
      "stock_minute_target_scope",
      "index_minute_target_scope",
      "board_minute_target_scope",
      "stock_condition_display_basis",
      "index_condition_display_basis",
      "board_condition_display_basis"
    ],
    "canonical_target_schema_columns": [
      "symmetry_anchor",
      "secondary_symmetry_anchor",
      "amplitude_source_period",
      "a_segment_start_date",
      "a_segment_end_date",
      "a_segment_high",
      "a_segment_low",
      "a_segment_amplitude",
      "base_price_policy",
      "base_price",
      "reference_target_price",
      "secondary_target_price",
      "target_price_trace_json"
    ],
    "canonical_target_table_status": {
      "stock_condition_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "index_condition_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "board_condition_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_condition_pool": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "index_condition_pool": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "board_condition_pool": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_minute_target_scope": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "index_minute_target_scope": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "board_minute_target_scope": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_condition_display_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "index_condition_display_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "board_condition_display_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      }
    },
    "canonical_target_fields_ready": true,
    "canonical_target_missing_columns": {},
    "canonical_target_forbidden_columns": {},
    "stock_financial_schema_tables": [
      "stock_condition_basis",
      "stock_condition_pool",
      "stock_minute_target_scope",
      "stock_condition_display_basis"
    ],
    "stock_financial_schema_columns": [
      "cash_realization_rate",
      "revenue_yoy_pct",
      "core_profit_yoy_pct",
      "report_core_revenue",
      "report_core_profit",
      "core_profit_ttm",
      "core_gt_revenue_yoy",
      "revenue_growth_streak_q",
      "core_growth_streak_q",
      "core_gt_revenue_streak_q",
      "forecast_type",
      "forecast_score",
      "score_breakdown_json",
      "financial_warning_json",
      "financial_metric_version",
      "pe_core",
      "score",
      "financial_quality_status"
    ],
    "stock_financial_table_status": {
      "stock_condition_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_condition_pool": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_minute_target_scope": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      },
      "stock_condition_display_basis": {
        "exists": true,
        "missing_columns": [],
        "forbidden_columns_present": [],
        "ready": true
      }
    },
    "stock_financial_fields_ready": true,
    "stock_financial_missing_columns": {},
    "stock_financial_forbidden_columns": {},
    "condition_run_status_check_name": "common_condition_run_status_check",
    "condition_run_status_check_definition": "CHECK ((status = ANY (ARRAY['planned'::text, 'running'::text, 'passed'::text, 'passed_active'::text, 'failed'::text, 'blocked'::text, 'superseded'::text, 'rolled_back'::text])))",
    "passed_active_status_supported": true,
    "status_migration_required": false,
    "migration_required": false,
    "migration_performed": false,
    "read_only": true
  },
  "active_run_status": {
    "table_exists": true,
    "active_exists": true,
    "active_runs": [
      {
        "run_id": "condition_layer_20260529_source_20260529_v1",
        "status": "passed_active",
        "source_trade_date": "20260529",
        "for_trade_date": "20260601",
        "prev_trade_date": "20260529",
        "source_versions": {
          "board_daily": "board_daily_20260529_v1",
          "index_daily": "index_daily_20260529_v1",
          "stock_daily": "stock_daily_20260529_v1",
          "stock_financial": "stock_financial_20260529_v1",
          "board_membership": "board_membership_20260529_v1",
          "index_membership": "index_membership_20260529_v1",
          "stock_daily_basic": "stock_daily_basic_20260529_v1"
        },
        "p0_count": 0,
        "p1_count": 9,
        "p2_count": 3,
        "created_at": "2026-06-01T04:43:14.228258+08:00",
        "finished_at": "2026-06-01T04:43:14.228258+08:00"
      }
    ],
    "active_run_count": 1,
    "canonical_active_status": "passed_active",
    "legacy_active_status": "passed",
    "canonical_active_run_count": 1,
    "legacy_active_run_count": 0,
    "default_policy": "reject_if_active_exists",
    "overwrite": true,
    "blocked_by_active_run": false,
    "blocked_by_multiple_passed_active": false,
    "read_only": true
  },
  "run_id_status": {
    "requested_run_id": "condition_layer_20260529_source_20260529_v2",
    "table_counts": {
      "common_condition_run": 0,
      "common_condition_quality_item": 0,
      "stock_monitor_target": 0,
      "index_monitor_target": 0,
      "board_monitor_target": 0,
      "stock_condition_basis": 0,
      "index_condition_basis": 0,
      "board_condition_basis": 0,
      "stock_condition_pool": 0,
      "index_condition_pool": 0,
      "board_condition_pool": 0,
      "stock_minute_target_scope": 0,
      "index_minute_target_scope": 0,
      "board_minute_target_scope": 0,
      "stock_condition_display_basis": 0,
      "index_condition_display_basis": 0,
      "board_condition_display_basis": 0
    },
    "total_existing_rows": 0,
    "run_id_available": true,
    "read_only": true
  },
  "source_version_status": {
    "source_versions": {
      "stock_daily": "stock_daily_20260529_v1",
      "stock_daily_basic": "stock_daily_basic_20260529_v1",
      "stock_financial": "stock_financial_20260529_v2",
      "index_daily": "index_daily_20260529_v1",
      "index_membership": "index_membership_20260529_v1",
      "board_daily": "board_daily_20260529_v1",
      "board_membership": "board_membership_20260529_v1"
    },
    "required_keys": [
      "stock_daily",
      "stock_daily_basic",
      "stock_financial",
      "index_daily",
      "index_membership",
      "board_daily",
      "board_membership"
    ],
    "missing_keys": [],
    "complete": true,
    "drift_check_required": true,
    "drift_check_performed": false,
    "status": "contract_frozen_pending_execute_recheck"
  },
  "rollback_sql_preview": [
    "DELETE FROM stock_minute_target_scope WHERE run_id = :execute_run_id;",
    "DELETE FROM board_minute_target_scope WHERE run_id = :execute_run_id;",
    "DELETE FROM index_minute_target_scope WHERE run_id = :execute_run_id;",
    "DELETE FROM board_condition_pool WHERE run_id = :execute_run_id;",
    "DELETE FROM index_condition_pool WHERE run_id = :execute_run_id;",
    "DELETE FROM stock_condition_pool WHERE run_id = :execute_run_id;",
    "DELETE FROM board_condition_basis WHERE run_id = :execute_run_id;",
    "DELETE FROM index_condition_basis WHERE run_id = :execute_run_id;",
    "DELETE FROM stock_condition_basis WHERE run_id = :execute_run_id;",
    "DELETE FROM board_monitor_target WHERE source_version = :execute_run_id;",
    "DELETE FROM index_monitor_target WHERE source_version = :execute_run_id;",
    "DELETE FROM stock_monitor_target WHERE source_version = :execute_run_id;",
    "DELETE FROM common_condition_quality_item WHERE run_id = :execute_run_id;",
    "DELETE FROM common_condition_run WHERE run_id = :execute_run_id;"
  ],
  "rollback_strategy": "delete_by_run_id_then_restore_previous_active",
  "user_confirmation_required": true,
  "user_confirmed": true,
  "overwrite": true,
  "execute_allowed": true,
  "execute_allowed_meaning": "true means eligible to request N2-E3 execute; N2-E2 never executes SQL",
  "blocked_reasons": [],
  "preflight_guards": [
    {
      "gate_code": "schema_ready",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "canonical_target_schema_ready",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "stock_financial_schema_ready",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "passed_active_status_supported",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "active_run_conflict",
      "severity": "P0",
      "status": "passed",
      "expected_value": "no active run unless overwrite",
      "actual_value": "true"
    },
    {
      "gate_code": "single_passed_active_per_date_pair",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 or 1",
      "actual_value": "1"
    },
    {
      "gate_code": "requested_run_id_available",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0 existing rows for requested run_id",
      "actual_value": "0"
    },
    {
      "gate_code": "source_versions_complete",
      "severity": "P0",
      "status": "passed",
      "expected_value": "all required source versions",
      "actual_value": ""
    },
    {
      "gate_code": "readiness_preconditions",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "aggregate_p0_clean",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0",
      "actual_value": "0"
    },
    {
      "gate_code": "user_confirmation",
      "severity": "P1",
      "status": "passed",
      "expected_value": "true when required",
      "actual_value": "true"
    },
    {
      "gate_code": "rollback_sql_preview_present",
      "severity": "P0",
      "status": "passed",
      "expected_value": ">0 rollback SQL templates",
      "actual_value": "14"
    },
    {
      "gate_code": "no_migration_performed",
      "severity": "P0",
      "status": "passed",
      "expected_value": "false",
      "actual_value": "migration_performed=false"
    },
    {
      "gate_code": "no_business_write",
      "severity": "P0",
      "status": "passed",
      "expected_value": "false",
      "actual_value": "writes_performed=false"
    },
    {
      "gate_code": "no_market_data_pull",
      "severity": "P0",
      "status": "passed",
      "expected_value": "false",
      "actual_value": "minute_kline_pulled=false"
    }
  ],
  "dry_run_only": true,
  "read_only_database_checks": true,
  "will_execute_sql": false,
  "writes_performed": false,
  "migration_performed": false,
  "minute_kline_pulled": false,
  "downstream_layers_touched": false,
  "policy_source": "8782_console",
  "policy_id": "n2_default_policy",
  "policy_version": "v4",
  "previous_policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
  "policy_diff_summary": {
    "index": {
      "changed": false,
      "changed_keys": [],
      "before_key_count": 16,
      "after_key_count": 16,
      "summary": "unchanged"
    },
    "board": {
      "changed": false,
      "changed_keys": [],
      "before_key_count": 18,
      "after_key_count": 18,
      "summary": "unchanged"
    },
    "stock": {
      "changed": false,
      "changed_keys": [],
      "before_key_count": 25,
      "after_key_count": 25,
      "summary": "unchanged"
    }
  },
  "n3_rebuild_required": false,
  "n3_lineage_auto_switch": false,
  "active_lineage_plan": {
    "overwrite_semantics": "lineage_supersede_only",
    "n3_lineage_auto_switch": false
  },
  "scope_delta_summary": {
    "stock": {
      "minute_target_scope_rows": 4087,
      "minute_target_scope_objects": 1862,
      "selected_from_condition_pool": true
    },
    "index": {
      "minute_target_scope_rows": 187,
      "minute_target_scope_objects": 83,
      "selected_from_condition_pool": true
    },
    "board": {
      "minute_target_scope_rows": 942,
      "minute_target_scope_objects": 428,
      "selected_from_condition_pool": true
    }
  },
  "expected_row_counts_with_display": {
    "common_condition_run": 1,
    "common_condition_quality_item": 106,
    "stock_monitor_target": 5506,
    "index_monitor_target": 83,
    "board_monitor_target": 428,
    "stock_condition_basis": 5506,
    "index_condition_basis": 83,
    "board_condition_basis": 428,
    "stock_condition_pool": 4106,
    "index_condition_pool": 187,
    "board_condition_pool": 942,
    "index_minute_target_scope": 187,
    "board_minute_target_scope": 942,
    "stock_minute_target_scope": 4087,
    "stock_condition_display_basis": 1862,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 428
  },
  "requested_run_id": "condition_layer_20260529_source_20260529_v2",
  "rollback_sql_path": "sql/N2_condition_layer_20260529_financial_v2_rollback.sql"
}
```
