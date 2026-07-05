# N3 true full-day B2 formal amount chain rebuild post review

- result: `B2_METRIC_PASS`
- metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- rows stock/index/board/total: `441840/19440/30480/491760`
- formal proof nested amount_chain_metrics rows: `491760/491760`
- refs after write: `{'outbox_refs': 0, 'inbox_refs': 0, 'checkpoint_refs': 0, 'ledger_refs': 0, 'delivery_attempt_refs': 0, 'trigger_run_refs': 0}`
- rollback SQL: `sql/N3_20260617_true_full_day_minute_b2_formal_amount_chain_rebuild_rollback.sql`

No N4/N5/N6 entry, no outbox/inbox/checkpoint consumption, no worker/scheduler, no old system.
