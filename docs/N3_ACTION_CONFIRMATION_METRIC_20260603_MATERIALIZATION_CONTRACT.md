# N3 Action-Confirmation Metric 20260603 Materialization Contract

Status: CONTRACT_PASS

```text
projection_run_id=action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
runner_readiness=ready
expected_rows stock/index/board/total=640/34/148/822
writes_outbox=false
allowed_write_tables=['common_market_data_run', 'common_market_data_quality_item', 'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric']
actual_032_target_tables={'stock': 'stock_action_confirmation_projection_metric', 'index': 'index_action_confirmation_projection_metric', 'board': 'board_action_confirmation_projection_metric'}
requested_target_aliases=['stock_action_confirmation_metric', 'index_action_confirmation_metric', 'board_action_confirmation_metric']
rollback_sql=sql/N3_action_confirmation_metric_20260603_materialization_rollback.sql
```
