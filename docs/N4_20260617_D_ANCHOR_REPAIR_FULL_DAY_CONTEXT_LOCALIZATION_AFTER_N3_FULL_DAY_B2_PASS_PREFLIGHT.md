# N4 D Anchor Repair Full-Day Context Localization Preflight

Result: `N4_PREFLIGHT_PASS`

- trigger_context_run_id: `trigger_context_snapshot_20260617_full_day__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- context rows: `{'stock': 3882, 'index': 173, 'board': 271, 'total': 4326}`
- metric rows: `{'stock': 1841, 'index': 81, 'board': 127, 'total': 2049}`
- 000012 D high/low/amount: `4.52 / 4.1 / 189512.92713`
- trigger_state/match/outbox scoped rows: `0 / 0 / 0`
- rollback_sql: `sql/N4_20260617_d_anchor_repair_full_day_context_rollback.sql`
- warnings: `["N3 d_anchor_repair B2 metric is 15:00 one-row-per-identity (2049 rows), not 240x full-day time-series; next trigger replay must explicitly use this final-snapshot scope or request N3 time-series B2 rebuild."]`
- errors: `[]`
