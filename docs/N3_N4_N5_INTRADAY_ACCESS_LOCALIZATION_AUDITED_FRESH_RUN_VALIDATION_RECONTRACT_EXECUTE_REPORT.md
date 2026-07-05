# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Recontract Execute Report

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_EXECUTE_GATE`

Result: `EXECUTE_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-07T05:24:18.459294+00:00`

## Proof Summary

- N3 probe: `PROBE_PASS`
- N4 probe: `DRY_RUN_PASS`, compliant/block = `605/291`
- N5 probe: `PROBE_PASS`
- audit artifacts: `7`
- audit entries: `33`
- denied table hit entries: `0`
- denied referenced tables: `[]`
- db_write_attempted entries: `0`
- worker_started entries: `0`
- outbox_consumed entries: `0`
- checkpoint_updated entries: `0`
- pre/post snapshot unchanged: `True`

## Audit Artifact Summary

- `N3_market_data_n3_post_closeout_metric_lineage_audit_runtime_control_intraday_access_localization_recontract_20260607_n3_N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE_510e013b8cfe7c84.json`: entries `5`, layers `['N3_market_data']`, path_roles `['n3_readonly_plan']`, denied `[]`
- `N4_trigger_n4_20260605_corrected_dry_run_capture_refs_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1_N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHA_31dbca55c6f2afcc.json`: entries `7`, layers `['N4_trigger']`, path_roles `['n4_readonly_plan']`, denied `[]`
- `N4_trigger_n4_local_trigger_dry_run_fetch_context_trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1_N3_N4_N5_STRUCTURED_QUERY_AUDI_6f78e5b0e168131c.json`: entries `4`, layers `['N4_trigger']`, path_roles `['n4_readonly_plan']`, denied `[]`
- `N4_trigger_n4_local_trigger_dry_run_fetch_snapshot_realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_32d41c7d2eb63a37.json`: entries `4`, layers `['N4_trigger']`, path_roles `['n4_readonly_plan']`, denied `[]`
- `N4_trigger_n4_projection_matcher_fetch_projection_realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_13187546295924ed.json`: entries `3`, layers `['N4_trigger']`, path_roles `['n4_readonly_plan']`, denied `[]`
- `N5_action_n5_post_closeout_action_lineage_audit_runtime_control_intraday_access_localization_recontract_20260607_n5_N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_0de0828f8a3861d1.json`: entries `5`, layers `['N5_action']`, path_roles `['n5_readonly_plan']`, denied `[]`
- `N5_action_n5_post_closeout_action_lineage_audit_runtime_control_intraday_access_localization_recontract_20260607_n5_r1_N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_15f436a47d2dfe9a.json`: entries `5`, layers `['N5_action']`, path_roles `['n5_readonly_plan']`, denied `[]`

## Denied Table Proof

Denied external display/membership tables checked:

- `board_condition_display_basis`
- `board_membership_fact`
- `index_condition_display_basis`
- `index_membership_fact`
- `stock_condition_display_basis`

Result: `0` denied references and `0` denied table hit entries.

## N5 Schema Adjustment

`common_action_event` live schema uses `run_id`, not `action_run_id`. The initial N5 probe exposed this mismatch without writing database rows. The preflight artifact was amended docs-only, and the N5 probe reran successfully with `run_id`.

## Forbidden Scope Proof

- No database write or migration was performed.
- No N3/N4/N5 business execute was performed; N4 was dry-run only.
- No rollback was executed.
- No outbox/inbox/checkpoint consumption or update was performed.
- No worker was started.
- No delivery/push/voice/mobile, sim/position/PnL/real_trade, proposal/order/trade was entered.
- `pg_stat_statements` was not enabled and PostgreSQL config was not changed.

## P0/P1/P2

`P0/P1/P2 = 0/1/1`

P1: 33 N1/N2/ingestion script direct connect sites remain documented outside this N3/N4/N5 runtime validation scope.

P2: N5 probe command required a docs-only schema-column amendment from `action_run_id` to `run_id`; final probe passed.

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_POST_REVIEW_GATE`

## Validation Summary

- JSON parse: `19 files PASS`
- structured query audit/adoption unittests: `23 OK`
- `python3 -m compileall src/ashare_v3/observability src/ashare_v3/market src/ashare_v3/trigger src/ashare_v3/action`: `PASS`
- `git diff --check`: `PASS`
- requirement completion audit: `PASS`
