# N2 Financial Canonical 20260529 Execute Contract

result = CONTRACT_PASS

- requested_run_id: `condition_layer_20260529_source_20260529_v2`
- overwrite: `True`
- execute_request_allowed: `True`
- writes_performed=false; will_execute_sql=false

```json
{
  "stage": "N2-E1",
  "plan_mode": "condition_layer_execute_contract",
  "readiness_plan_id": "condition_layer_20260529_to_20260601_execute",
  "source_trade_date": "20260529",
  "for_trade_date": "20260601",
  "prev_trade_date": "20260529",
  "source_versions": {
    "stock_daily": "stock_daily_20260529_v1",
    "stock_daily_basic": "stock_daily_basic_20260529_v1",
    "stock_financial": "stock_financial_20260529_v2",
    "index_daily": "index_daily_20260529_v1",
    "index_membership": "index_membership_20260529_v1",
    "board_daily": "board_daily_20260529_v1",
    "board_membership": "board_membership_20260529_v1"
  },
  "policy_name": "default_adjusted_by_user",
  "policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
  "operator": "codex",
  "user_confirmed": true,
  "confirmation_note_present": true,
  "overwrite": true,
  "run_id_contract": {
    "readiness_planned_run_id": "condition_layer_20260529_to_20260601_execute",
    "execute_run_id_template": "condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute",
    "must_generate_new_run_id_per_execute": true,
    "reuse_existing_run_id_allowed": false,
    "shared_by_tables": [
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
      "index_minute_target_scope",
      "board_minute_target_scope",
      "stock_minute_target_scope"
    ],
    "same_transaction_required": true
  },
  "source_version_contract": {
    "source_versions": {
      "stock_daily": "stock_daily_20260529_v1",
      "stock_daily_basic": "stock_daily_basic_20260529_v1",
      "stock_financial": "stock_financial_20260529_v2",
      "index_daily": "index_daily_20260529_v1",
      "index_membership": "index_membership_20260529_v1",
      "board_daily": "board_daily_20260529_v1",
      "board_membership": "board_membership_20260529_v1"
    },
    "must_match_readiness_plan": true,
    "drift_check_required": true,
    "drift_check_sql_template": "SELECT data_type, active_source_version FROM common_condition_active_source_version_view WHERE trade_date = :source_trade_date;",
    "on_drift": "abort_execute_and_rerun_n2_e0_n2_e1"
  },
  "quality_policy": {
    "p0_count": 0,
    "p1_count": 6,
    "p2_count": 3,
    "p0_policy": "block_execute",
    "p1_policy": "requires_user_confirmation",
    "p2_policy": "record_only",
    "user_confirmation_required": true
  },
  "row_count_contract": {
    "expected_rows_by_table": {
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
    "pre_execute_expected_hash": "318e36deeaf5444764a1fafab8722e5bc5db88f9e1f88a69745232350439496f",
    "post_execute_hash_must_match": true,
    "row_count_mismatch_policy": "mark_run_failed_and_rollback"
  },
  "write_contract": {
    "write_order": [
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
      "index_minute_target_scope",
      "board_minute_target_scope",
      "stock_minute_target_scope"
    ],
    "transaction_required": true,
    "common_condition_run_initial_status": "running",
    "common_condition_run_success_status": "passed_active",
    "common_condition_run_failure_status": "failed",
    "id_mapping_requirements": {
      "condition_basis_source_monitor_target_id": "use INSERT RETURNING or equivalent monitor target identity-key mapping",
      "condition_pool_source_condition_basis_id": "use INSERT RETURNING or equivalent basis identity-key mapping",
      "scope_source_condition_pool_id": "use INSERT RETURNING or equivalent condition_pool_ref mapping for stock/index/board scope rows"
    },
    "stage_counts": {
      "condition_basis": {
        "stock": 5506,
        "index": 83,
        "board": 428
      },
      "condition_pool": {
        "stock": 4106,
        "index": 187,
        "board": 942
      },
      "minute_target_scope": {
        "stock": 4087,
        "index": 187,
        "board": 942
      }
    }
  },
  "active_run_contract": {
    "active_pointer": "common_condition_run.status = 'passed_active'",
    "legacy_active_pointer_read_compat": "common_condition_run.status = 'passed'",
    "canonical_active_status": "passed_active",
    "legacy_active_status": "passed",
    "active_run_lookup_sql_template": "SELECT run_id FROM common_condition_run WHERE source_trade_date = :source_trade_date AND for_trade_date = :for_trade_date AND status IN ('passed_active', 'passed') ORDER BY CASE status WHEN 'passed_active' THEN 0 WHEN 'passed' THEN 1 ELSE 2 END, finished_at DESC NULLS LAST, created_at DESC LIMIT 1;",
    "canonical_active_uniqueness": "one passed_active per source_trade_date + for_trade_date",
    "default_policy": "reject_if_active_exists",
    "active_run_policy": "overwrite_requires_confirmation",
    "overwrite_requires_explicit_flag": true,
    "overwrite_requires_user_confirmation": true,
    "previous_active_run_id_storage": "new common_condition_run.raw_json.previous_active_run_id",
    "switch_after_postcheck_sql_templates": [
      "UPDATE common_condition_run SET status = 'superseded', updated_at = now() WHERE run_id = :previous_active_run_id;",
      "UPDATE common_condition_run SET status = 'passed_active', finished_at = now(), updated_at = now() WHERE run_id = :execute_run_id;"
    ],
    "on_postcheck_failed": "keep_previous_active_status_and_mark_new_run_failed",
    "source_trade_date": "20260529",
    "for_trade_date": "20260601"
  },
  "rollback_contract": {
    "strategy": "delete_by_run_id_then_restore_previous_active",
    "run_id_parameter": ":execute_run_id",
    "delete_order": [
      {
        "table_name": "stock_minute_target_scope",
        "sql_template": "DELETE FROM stock_minute_target_scope WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "board_minute_target_scope",
        "sql_template": "DELETE FROM board_minute_target_scope WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "index_minute_target_scope",
        "sql_template": "DELETE FROM index_minute_target_scope WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "board_condition_pool",
        "sql_template": "DELETE FROM board_condition_pool WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "index_condition_pool",
        "sql_template": "DELETE FROM index_condition_pool WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "stock_condition_pool",
        "sql_template": "DELETE FROM stock_condition_pool WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "board_condition_basis",
        "sql_template": "DELETE FROM board_condition_basis WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "index_condition_basis",
        "sql_template": "DELETE FROM index_condition_basis WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "stock_condition_basis",
        "sql_template": "DELETE FROM stock_condition_basis WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "board_monitor_target",
        "sql_template": "DELETE FROM board_monitor_target WHERE source_version = :execute_run_id;"
      },
      {
        "table_name": "index_monitor_target",
        "sql_template": "DELETE FROM index_monitor_target WHERE source_version = :execute_run_id;"
      },
      {
        "table_name": "stock_monitor_target",
        "sql_template": "DELETE FROM stock_monitor_target WHERE source_version = :execute_run_id;"
      },
      {
        "table_name": "common_condition_quality_item",
        "sql_template": "DELETE FROM common_condition_quality_item WHERE run_id = :execute_run_id;"
      },
      {
        "table_name": "common_condition_run",
        "sql_template": "DELETE FROM common_condition_run WHERE run_id = :execute_run_id;"
      }
    ],
    "restore_previous_active_sql_template": "UPDATE common_condition_run SET status = 'passed_active', updated_at = now() WHERE run_id = :previous_active_run_id;",
    "rollback_report_required": true,
    "rollback_report_fields": [
      "execute_run_id",
      "previous_active_run_id",
      "operator",
      "reason",
      "started_at",
      "finished_at",
      "deleted_row_counts",
      "pre_rollback_hash",
      "post_rollback_hash"
    ],
    "readiness_rollback_plan": {
      "strategy": "delete_by_run_id",
      "run_id": "condition_layer_20260529_to_20260601_execute",
      "delete_order": [
        {
          "table_name": "stock_minute_target_scope",
          "sql_template": "DELETE FROM stock_minute_target_scope WHERE run_id = :run_id;"
        },
        {
          "table_name": "board_minute_target_scope",
          "sql_template": "DELETE FROM board_minute_target_scope WHERE run_id = :run_id;"
        },
        {
          "table_name": "index_minute_target_scope",
          "sql_template": "DELETE FROM index_minute_target_scope WHERE run_id = :run_id;"
        },
        {
          "table_name": "board_condition_pool",
          "sql_template": "DELETE FROM board_condition_pool WHERE run_id = :run_id;"
        },
        {
          "table_name": "index_condition_pool",
          "sql_template": "DELETE FROM index_condition_pool WHERE run_id = :run_id;"
        },
        {
          "table_name": "stock_condition_pool",
          "sql_template": "DELETE FROM stock_condition_pool WHERE run_id = :run_id;"
        },
        {
          "table_name": "board_condition_basis",
          "sql_template": "DELETE FROM board_condition_basis WHERE run_id = :run_id;"
        },
        {
          "table_name": "index_condition_basis",
          "sql_template": "DELETE FROM index_condition_basis WHERE run_id = :run_id;"
        },
        {
          "table_name": "stock_condition_basis",
          "sql_template": "DELETE FROM stock_condition_basis WHERE run_id = :run_id;"
        },
        {
          "table_name": "board_monitor_target",
          "sql_template": "DELETE FROM board_monitor_target WHERE source_version = :run_id;"
        },
        {
          "table_name": "index_monitor_target",
          "sql_template": "DELETE FROM index_monitor_target WHERE source_version = :run_id;"
        },
        {
          "table_name": "stock_monitor_target",
          "sql_template": "DELETE FROM stock_monitor_target WHERE source_version = :run_id;"
        },
        {
          "table_name": "common_condition_quality_item",
          "sql_template": "DELETE FROM common_condition_quality_item WHERE run_id = :run_id;"
        },
        {
          "table_name": "common_condition_run",
          "sql_template": "DELETE FROM common_condition_run WHERE run_id = :run_id;"
        }
      ],
      "will_execute_sql": false
    },
    "will_execute_sql": false
  },
  "verification_contract": {
    "pre_execute": [
      "readiness_plan_hash_recorded",
      "source_versions_match_active_source",
      "policy_hash_match",
      "expected_row_counts_recorded",
      "p0_count_is_zero",
      "user_confirmation_is_true",
      "active_run_conflict_checked"
    ],
    "post_execute": [
      "common_condition_run_row_count_matches",
      "common_condition_quality_item_row_count_matches",
      "stock_index_board_condition_basis_row_counts_match",
      "stock_index_board_condition_pool_row_counts_match",
      "stock_index_board_minute_target_scope_row_counts_match",
      "source_versions_not_drifted",
      "policy_hash_not_drifted",
      "physical_table_family_split_checked",
      "forbidden_field_scan_passed",
      "downstream_write_absence_checked"
    ],
    "expected_hash": "318e36deeaf5444764a1fafab8722e5bc5db88f9e1f88a69745232350439496f",
    "forbidden_field_scan_manifest": "condition_layer_execution_field_blocklist_from_AGENTS_and_design_doc",
    "forbidden_write_domains": [
      "trigger",
      "action",
      "mobile",
      "voice",
      "sim",
      "worker",
      "old_system"
    ],
    "downstream_write_policy": "no writes to trigger/action/mobile/voice/sim/worker/old_system"
  },
  "execute_guards": [
    {
      "gate_code": "readiness_preconditions_passed",
      "severity": "P0",
      "status": "passed",
      "expected_value": "true",
      "actual_value": "true"
    },
    {
      "gate_code": "p0_count_zero",
      "severity": "P0",
      "status": "passed",
      "expected_value": "0",
      "actual_value": "0"
    },
    {
      "gate_code": "p1_user_confirmation",
      "severity": "P1",
      "status": "passed",
      "expected_value": "true when P1 > 0",
      "actual_value": "true"
    },
    {
      "gate_code": "overwrite_user_confirmation",
      "severity": "P1",
      "status": "passed",
      "expected_value": "true when overwrite",
      "actual_value": "true"
    },
    {
      "gate_code": "n2_e1_contract_only_no_sql",
      "severity": "P0",
      "status": "passed",
      "expected_value": "false",
      "actual_value": "will_execute_sql=false"
    }
  ],
  "contract_hash": "52c15c4f57d7f61e727fe5e1ebe6c646cf9de68b63f61ef9d4e471f0f83e423a",
  "execute_request_allowed": true,
  "execute_ready": false,
  "execute_supported": false,
  "blocked_reasons": [],
  "not_ready_reasons": [
    "n2_e1_contract_only_execute_not_supported"
  ],
  "dry_run_only": true,
  "will_open_write_connection": false,
  "will_execute_sql": false,
  "writes_performed": false,
  "migration_performed": false,
  "minute_kline_pulled": false,
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
  "expected_rows_with_display": {
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
