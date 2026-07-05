# N2 Condition Source Refresh for Stock Financial 20260615 v3 Active Supersede

Result: `CONTRACT_PASS`

```text
source_trade_date = 20260615
for_trade_date = 20260616
previous_active_run_id = condition_layer_20260615_source_20260615_for_20260616_v3
target_run_id = condition_layer_20260615_source_20260615_for_20260616_v4
overwrite = true
overwrite_semantics = lineage_supersede_only
active_run_exists_is_blocker = false
blocked_reasons = ['user_confirmation_required']
execute_allowed = false (user_confirmation_required_only)
writes_performed = false
will_execute_sql = false
n3_lineage_auto_switch = false
```
## Dry-run Summary

```json
{
  "status": "FULL_DRY_RUN_PASS",
  "expected_rows": {
    "common_condition_run": 1,
    "common_condition_quality_item": 103,
    "stock_monitor_target": 5504,
    "index_monitor_target": 83,
    "board_monitor_target": 427,
    "stock_condition_basis": 5504,
    "index_condition_basis": 83,
    "board_condition_basis": 427,
    "stock_condition_pool": 4215,
    "index_condition_pool": 183,
    "board_condition_pool": 307,
    "index_minute_target_scope": 183,
    "board_minute_target_scope": 307,
    "stock_minute_target_scope": 4194,
    "stock_condition_display_basis": 1822,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 127
  },
  "quality_summary": {
    "p0_count": 0,
    "p1_count": 3,
    "p2_count": 3,
    "quality_item_count": 93,
    "by_stage": {
      "condition_basis": {
        "p0_count": 0,
        "p1_count": 3,
        "p2_count": 1,
        "quality_item_count": 23
      },
      "condition_pool": {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 1,
        "quality_item_count": 24
      },
      "minute_target_scope": {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 1,
        "quality_item_count": 18
      },
      "condition_display_basis": {
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "quality_item_count": 28
      }
    }
  },
  "source_versions": {
    "stock_daily": "stock_daily_20260615_v1",
    "stock_daily_basic": "stock_daily_basic_20260615_v1",
    "stock_financial": "stock_financial_20260615_v3",
    "index_daily": "index_daily_20260615_v1",
    "index_membership": "index_membership_20260615_v1",
    "board_daily": "board_daily_20260615_v1",
    "board_membership": "board_membership_20260615_v1"
  },
  "review_checklist": {
    "readiness_pass": true,
    "active_stock_financial_v3": true,
    "current_n2_v3_consumed_v2": true,
    "target_dry_run_consumes_v3": true,
    "previous_active_run_id_match": true,
    "target_run_id_match": true,
    "overwrite_true": true,
    "active_run_exists_is_not_blocker": true,
    "blocked_only_user_confirmation": true,
    "p0_clean": true,
    "run_id_available": true,
    "schema_ready": true,
    "stock_financial_schema_ready": true,
    "passed_active_supported": true,
    "n3_lineage_auto_switch_false": true,
    "no_writes": true,
    "002831_basis_v3_financial": true,
    "002831_pool_scope_display_propagated_if_selected": true
  },
  "failed_review_items": []
}
```
## 002831 N2 Propagation Proof

```json
{
  "source_trade_date": "20260615",
  "target_run_id": "condition_layer_20260615_source_20260615_for_20260616_v4",
  "active_stock_financial_source_version": "stock_financial_20260615_v3",
  "basis_hit": true,
  "pool_hit_count": 2,
  "scope_hit_count": 2,
  "display_hit_count": 1,
  "basis": {
    "stock_identity_key": "stock:SZ:002831",
    "code": "002831",
    "exchange": "SZ",
    "name": "裕同科技",
    "financial_source_version": "stock_financial_20260615_v3",
    "financial_quality_status": "warning",
    "pe_core": "20.2506996374",
    "total_mv": "3929409.6385",
    "score": "87",
    "cash_realization_rate": "1.9254856573",
    "revenue_yoy_pct": "2.55",
    "core_profit_yoy_pct": "57.1302091953",
    "report_core_revenue": "3793342067.38",
    "report_core_profit": "3.4158605E+8",
    "core_profit_ttm": "1940382164",
    "core_gt_revenue_yoy": true,
    "revenue_growth_streak_q": 9,
    "core_growth_streak_q": 4,
    "core_gt_revenue_streak_q": 2,
    "forecast_type": null,
    "forecast_score": "0",
    "financial_metric_version": "financial_metric_v1",
    "financial_warning_json": {
      "warnings": [
        "forecast_missing"
      ],
      "source_type": "tdx_financial_package",
      "tdx_parity_repair": true,
      "interest_expense_used": "19744658"
    },
    "source_version": "stock_daily_20260615_v1"
  },
  "pool_samples": [
    {
      "stock_identity_key": "stock:SZ:002831",
      "code": "002831",
      "exchange": "SZ",
      "name": "裕同科技",
      "financial_quality_status": "warning",
      "pe_core": "20.2506996374",
      "total_mv": "3929409.6385",
      "score": "87",
      "cash_realization_rate": "1.9254856573",
      "revenue_yoy_pct": "2.55",
      "core_profit_yoy_pct": "57.1302091953",
      "report_core_revenue": "3793342067.38",
      "report_core_profit": "3.4158605E+8",
      "core_profit_ttm": "1940382164",
      "core_gt_revenue_yoy": true,
      "revenue_growth_streak_q": 9,
      "core_growth_streak_q": 4,
      "core_gt_revenue_streak_q": 2,
      "forecast_type": null,
      "forecast_score": "0",
      "financial_metric_version": "financial_metric_v1",
      "financial_warning_json": {
        "warnings": [
          "forecast_missing"
        ],
        "source_type": "tdx_financial_package",
        "tdx_parity_repair": true,
        "interest_expense_used": "19744658"
      },
      "direction": "buy",
      "condition_key": "BUY:M,D",
      "allowed_signal_types": [
        "BUY"
      ],
      "source_version": "stock_daily_20260615_v1"
    },
    {
      "stock_identity_key": "stock:SZ:002831",
      "code": "002831",
      "exchange": "SZ",
      "name": "裕同科技",
      "financial_quality_status": "warning",
      "pe_core": "20.2506996374",
      "total_mv": "3929409.6385",
      "score": "87",
      "cash_realization_rate": "1.9254856573",
      "revenue_yoy_pct": "2.55",
      "core_profit_yoy_pct": "57.1302091953",
      "report_core_revenue": "3793342067.38",
      "report_core_profit": "3.4158605E+8",
      "core_profit_ttm": "1940382164",
      "core_gt_revenue_yoy": true,
      "revenue_growth_streak_q": 9,
      "core_growth_streak_q": 4,
      "core_gt_revenue_streak_q": 2,
      "forecast_type": null,
      "forecast_score": "0",
      "financial_metric_version": "financial_metric_v1",
      "financial_warning_json": {
        "warnings": [
          "forecast_missing"
        ],
        "source_type": "tdx_financial_package",
        "tdx_parity_repair": true,
        "interest_expense_used": "19744658"
      },
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "allowed_signal_types": [
        "SELL"
      ],
      "source_version": "stock_daily_20260615_v1"
    }
  ],
  "scope_samples": [
    {
      "stock_identity_key": "stock:SZ:002831",
      "code": "002831",
      "exchange": "SZ",
      "name": "裕同科技",
      "financial_quality_status": "warning",
      "pe_core": "20.2506996374",
      "total_mv": "3929409.6385",
      "score": "87",
      "cash_realization_rate": "1.9254856573",
      "revenue_yoy_pct": "2.55",
      "core_profit_yoy_pct": "57.1302091953",
      "report_core_revenue": "3793342067.38",
      "report_core_profit": "341586050",
      "core_profit_ttm": "1940382164",
      "core_gt_revenue_yoy": true,
      "revenue_growth_streak_q": 9,
      "core_growth_streak_q": 4,
      "core_gt_revenue_streak_q": 2,
      "forecast_type": null,
      "forecast_score": "0",
      "financial_metric_version": "financial_metric_v1",
      "financial_warning_json": {
        "warnings": [
          "forecast_missing"
        ],
        "source_type": "tdx_financial_package",
        "tdx_parity_repair": true,
        "interest_expense_used": "19744658"
      },
      "direction": "buy",
      "condition_key": "BUY:M,D",
      "allowed_signal_types": [
        "BUY"
      ],
      "source_version": "stock_daily_20260615_v1",
      "scope_status": "planned"
    },
    {
      "stock_identity_key": "stock:SZ:002831",
      "code": "002831",
      "exchange": "SZ",
      "name": "裕同科技",
      "financial_quality_status": "warning",
      "pe_core": "20.2506996374",
      "total_mv": "3929409.6385",
      "score": "87",
      "cash_realization_rate": "1.9254856573",
      "revenue_yoy_pct": "2.55",
      "core_profit_yoy_pct": "57.1302091953",
      "report_core_revenue": "3793342067.38",
      "report_core_profit": "341586050",
      "core_profit_ttm": "1940382164",
      "core_gt_revenue_yoy": true,
      "revenue_growth_streak_q": 9,
      "core_growth_streak_q": 4,
      "core_gt_revenue_streak_q": 2,
      "forecast_type": null,
      "forecast_score": "0",
      "financial_metric_version": "financial_metric_v1",
      "financial_warning_json": {
        "warnings": [
          "forecast_missing"
        ],
        "source_type": "tdx_financial_package",
        "tdx_parity_repair": true,
        "interest_expense_used": "19744658"
      },
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "allowed_signal_types": [
        "SELL"
      ],
      "source_version": "stock_daily_20260615_v1",
      "scope_status": "planned"
    }
  ],
  "display_samples": [
    {
      "stock_identity_key": "stock:SZ:002831",
      "code": "002831",
      "exchange": "SZ",
      "name": "裕同科技",
      "financial_quality_status": "warning",
      "pe_core": "20.2506996374",
      "total_mv": "3929409.6385",
      "score": "87",
      "cash_realization_rate": "1.9254856573",
      "revenue_yoy_pct": "2.55",
      "core_profit_yoy_pct": "57.1302091953",
      "report_core_revenue": "3793342067.38",
      "report_core_profit": "3.4158605E+8",
      "core_profit_ttm": "1940382164",
      "core_gt_revenue_yoy": true,
      "revenue_growth_streak_q": 9,
      "core_growth_streak_q": 4,
      "core_gt_revenue_streak_q": 2,
      "forecast_type": null,
      "forecast_score": "0",
      "financial_metric_version": "financial_metric_v1",
      "financial_warning_json": {
        "warnings": [
          "forecast_missing"
        ],
        "source_type": "tdx_financial_package",
        "tdx_parity_repair": true,
        "interest_expense_used": "19744658"
      },
      "source_version": "stock_daily_20260615_v1",
      "display_status": "visible",
      "selected_condition_keys": [
        "BUY:M,D",
        "SELL:Y,Q,M,W,D"
      ],
      "selected_signal_types": [
        "BUY",
        "SELL"
      ]
    }
  ]
}
```
## Rollback / Boundary

```json
{
  "rollback_sql_path": "sql/N2_condition_source_refresh_for_stock_financial_20260615_v3_rollback.sql",
  "allowed_write_tables": [
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
    "board_minute_target_scope",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis"
  ],
  "forbidden_scopes": [
    "N1 facts/source versions",
    "N3/N4/N5/N6 facts",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "market data pull",
    "worker",
    "old system",
    "real trading",
    "rollback execution"
  ],
  "rollback_static_requirements": {
    "hard_fail_before_first_delete_or_update": true,
    "guard_outbox_inbox_checkpoint": true,
    "guard_n3_n4_n5_n6_refs": true,
    "scoped_to_target_run_id": "condition_layer_20260615_source_20260615_for_20260616_v4",
    "restore_previous_active_run_id": "condition_layer_20260615_source_20260615_for_20260616_v3",
    "no_drop_truncate_cascade": true
  }
}
```
