# N3 Lineage Refresh For N2 20260615 V4 Readiness

- result: READINESS_PASS
- layer_role: N3_market_data
- mode: readiness only
- source_trade_date: 20260615
- for_trade_date: 20260616
- new_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- target_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- target_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- P0/P1/P2: 0/0/0

## Prerequisite Proof
- n2_v4_post_review_status: POST_REVIEW_PASS
- n2_v4_execute_run_id: condition_layer_20260615_source_20260615_for_20260616_v4
- n2_v4_db_status: passed_active
- n2_v3_db_status: superseded
- active_n2_run_count: 1
- db_readonly: on

## Previous Lineage Proof
- previous lineage remains registered evidence and must not be mutated.
- market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2: status=passed, source_condition_run_id=condition_layer_20260615_source_20260615_for_20260616_v2
- previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2: status=passed, source_condition_run_id=condition_layer_20260615_source_20260615_for_20260616_v2
- candidate: 5924
- subscription: 3272
- pull_plan: 9
- previous_preload_stock_minute_rows: 132000
- previous_preload_index_minute_rows: 4080
- previous_preload_board_minute_rows: 12720

## New N2 V4 Source Readiness Proof
- minute_target_scope rows: {'stock': 4194, 'index': 183, 'board': 307}
- minute_target_scope objects: {'stock': 1822, 'index': 83, 'board': 127}
- 002831 artifact proof present: True
- 002831 v4 stock scope rows: 2

## Target Baseline Clean Proof
- common_market_data_run: 0
- common_market_data_quality_item: 0
- common_market_data_subscription_candidate: 0
- common_market_data_subscription: 0
- common_market_data_pull_plan: 0
- stock_previous_day_minute_preload_status: 0
- index_previous_day_minute_preload_status: 0
- board_previous_day_minute_preload_status: 0
- stock_minute_bar_1m_previous_day_scoped: 0
- index_minute_bar_1m_previous_day_scoped: 0
- board_minute_bar_1m_previous_day_scoped: 0
- previous_day_minute_preload_status_total: 0
- previous_day_minute_bar_1m_scoped_total: 0
- outbox/inbox/checkpoint refs: {'outbox': 0, 'inbox': 0, 'checkpoint': 0}
- N4/N5/N6 refs: N4=0, N5=0, N6=0

## Proposed N3 V4 Refresh Scope
- Stage 1: write v4 subscription control rows only.
- Stage 2: write v4 A1 previous-day minute preload rows/status/quality/run only.
- Use new v4 run ids; do not mutate v1/v2/v3 evidence.

## Rollback Planning
- required_for_next_contract_gate: True
- scope: new v4 subscription/preload run ids only
- preserve_prior_lineages: ['v1', 'v2', 'v3']
- must_hard_fail_before_delete_or_update: True
- must_guard: ['common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint', 'N3-B/C/B2 refs', 'N4 refs', 'N5 refs', 'N6 refs', 'worker/downstream flags']
- must_not_touch: ['N2 facts', 'prior v1/v2/v3 N3 subscription/preload lineage', 'realtime snapshot facts', 'today minute facts', 'projection facts', 'N4/N5/N6 facts']
- no_drop_truncate_cascade: True

## Forbidden Scope Proof
- n3_execute: False
- db_write: False
- rollback_executed: False
- outbox_inbox_checkpoint_consumed_or_updated: False
- N4_N5_N6_entered: False
- worker_started: False
- voice_mobile_sim_position_order_real_trade: False

## Checks
- [PASS] N2 v4 post-review artifact status: expected=POST_REVIEW_PASS, actual=POST_REVIEW_PASS
- [PASS] N2 v4 execute run id artifact matches target: expected=condition_layer_20260615_source_20260615_for_20260616_v4, actual=condition_layer_20260615_source_20260615_for_20260616_v4
- [PASS] N2 v4 DB status: expected=passed_active, actual=passed_active
- [PASS] N2 v3 DB status: expected=superseded, actual=superseded
- [PASS] active N2 run count: expected=1, actual=1
- [PASS] v4 minute_target_scope rows: expected={'stock': 4194, 'index': 183, 'board': 307}, actual={'stock': 4194, 'index': 183, 'board': 307}
- [PASS] 002831 propagation proof present: expected=artifact proof and DB scope rows > 0, actual={'artifact_has_002831': True, 'db_scope_rows': 2}
- [PASS] previous subscription run exists passed: expected=passed, actual=passed
- [PASS] previous preload run exists passed: expected=passed, actual=passed
- [PASS] target v4 baseline clean: expected=all 0, actual={'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'common_market_data_subscription_candidate': 0, 'common_market_data_subscription': 0, 'common_market_data_pull_plan': 0, 'stock_previous_day_minute_preload_status': 0, 'index_previous_day_minute_preload_status': 0, 'board_previous_day_minute_preload_status': 0, 'stock_minute_bar_1m_previous_day_scoped': 0, 'index_minute_bar_1m_previous_day_scoped': 0, 'board_minute_bar_1m_previous_day_scoped': 0, 'previous_day_minute_preload_status_total': 0, 'previous_day_minute_bar_1m_scoped_total': 0}
- [PASS] target v4 event refs clean: expected={'outbox': 0, 'inbox': 0, 'checkpoint': 0}, actual={'outbox': 0, 'inbox': 0, 'checkpoint': 0}
- [PASS] target v4 N4 refs clean: expected=0, actual=0
- [PASS] target v4 N5 refs clean: expected=0, actual=0
- [PASS] target v4 N6 refs clean: expected=0, actual=0

## Next Gate
- N3_LINEAGE_REFRESH_FOR_N2_20260615_V4_CONTRACT_GATE
