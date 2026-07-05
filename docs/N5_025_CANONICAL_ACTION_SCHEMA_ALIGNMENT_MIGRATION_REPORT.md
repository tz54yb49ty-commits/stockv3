# N5 025 Canonical Action Schema Alignment Migration Report

## Summary

- status: EXECUTED
- layer_role: N5_action
- migration_file: sql/025_n5_canonical_action_schema_alignment.sql
- rollback_file: sql/025_n5_canonical_action_schema_alignment_rollback.sql
- before_snapshot: docs/N5_025_canonical_action_schema_alignment_before_snapshot.json
- after_snapshot: docs/N5_025_canonical_action_schema_alignment_after_snapshot.json
- database: ashare_v3
- user: ashare_v3_user
- host: 127.0.0.1
- port: 5432
- old_system_touched: false

## Scope

- actual_ddl_target_tables: ['board_action_fact', 'common_action_event', 'index_action_fact', 'stock_action_fact']
- dml_keywords: []
- N5 business execute: false
- N4 outbox consumed: false
- N5 inbox/checkpoint business write: false
- N6 touched: false
- worker_started: false
- real_trade_touched: false

## Additive Columns

- stock_action_fact: ['action_mark', 'action_policy', 'action_state', 'confirmation_status', 'last_checked_minute_label', 'original_condition_key', 'source_trigger_state_id', 'trace_json', 'tracking_until', 'trigger_mark_candidate']
- index_action_fact: ['action_mark', 'action_policy', 'action_state', 'confirmation_status', 'last_checked_minute_label', 'original_condition_key', 'source_trigger_state_id', 'trace_json', 'tracking_until', 'trigger_mark_candidate']
- board_action_fact: ['action_mark', 'action_policy', 'action_state', 'confirmation_status', 'last_checked_minute_label', 'original_condition_key', 'source_trigger_state_id', 'trace_json', 'tracking_until', 'trigger_mark_candidate']
- common_action_event: ['action_mark', 'action_policy', 'action_state', 'confirmation_status', 'last_checked_minute_label', 'original_condition_key', 'source_trigger_state_id', 'trace_json', 'tracking_until', 'trigger_mark_candidate']

## Constraints

- source_trigger_event_type_compat: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True}
- common_action_event_event_type_compat: True
- action_state_checks: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- confirmation_status_checks: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- action_mark_checks: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- trigger_mark_candidate_checks: {'stock_action_fact': True, 'index_action_fact': True, 'board_action_fact': True, 'common_action_event': True}
- note: long source_trigger_event_type constraint names were truncated by PostgreSQL to the standard identifier limit; definitions are compatible.

## Row Count Delta

- stock_action_fact: 488 -> 488 (delta=0)
- index_action_fact: 0 -> 0 (delta=0)
- board_action_fact: 0 -> 0 (delta=0)
- common_action_event: 488 -> 488 (delta=0)
- common_action_run: 1 -> 1 (delta=0)
- common_action_quality_item: 276 -> 276 (delta=0)
- common_event_outbox: 100837 -> 100837 (delta=0)
- common_event_inbox: 2952 -> 2952 (delta=0)
- common_event_consumer_checkpoint: 2803 -> 2803 (delta=0)

## Rollback

- rollback_path: sql/025_n5_canonical_action_schema_alignment_rollback.sql
- rollback_guard_counts: {'canonical_common_action_event_rows': 0, 'canonical_stock_action_fact_values': 0, 'canonical_index_action_fact_values': 0, 'canonical_board_action_fact_values': 0, 'canonical_common_action_event_values': 0}
- rollback_safe_now: True
- rollback_executed: false

## Verification

- python3 -m compileall scripts src tests: PASS
- PYTHONPATH=src python3 -m unittest discover -s tests: PASS (988 tests)
- PYTHONPATH=src python3 -m unittest discover -s tests -p test_n5_canonical_schema_migration_draft.py: PASS (5 tests)
- git diff --check: PASS
- PYTHONPATH=src python3 scripts/check_n5_contract.py: FAILED

## Remaining Contract Checker Blockers

- schema missing N5 output event type: ActionEligible
- schema missing N5 output event type: ActionBlocked
- schema missing N5 output event type: ActionExecuted
- schema missing N5 output event type: ActionSkipped
- schema missing N5 input trigger event type: TriggerStateChanged

Interpretation: the DB schema is aligned by 025, but check_n5_contract.py still statically checks sql/011_action_layer_schema.sql and therefore reports legacy blockers.

## Next Gate

- contract_refresh_allowed: true
- n5_canonical_execute_preflight_review_allowed: true
- n5_business_execute_allowed_without_new_gate: false
