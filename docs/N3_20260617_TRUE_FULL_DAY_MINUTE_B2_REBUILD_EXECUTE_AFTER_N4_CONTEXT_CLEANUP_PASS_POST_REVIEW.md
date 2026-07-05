# N3 True Full-Day Minute B2 Rebuild Execute Post-Review

- result: `B2_METRIC_PASS`
- metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- row grain: `identity_key + metric_minute_label`
- rows stock/index/board/total: `441840/19440/30480/491760`
- labels: `09:31-15:00`, distinct=`240`
- metric_ready rows: `491760`
- BJ blockers: `{'index:BJ:899050': 1, 'index:BJ:899601': 1}`, metric rows `{'index:BJ:899050': 0, 'index:BJ:899601': 0}`
- event refs: `{'outbox': 0, 'inbox': 0, 'checkpoint': 0}`
- trigger refs: `{'common_trigger_run': 0, 'common_trigger_state': 0, 'common_trigger_match': 0}`
- rollback SQL: `sql/N3_20260617_true_full_day_minute_b2_rebuild_rollback.sql`

## Boundary

- N4/N5/N6 entered: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
