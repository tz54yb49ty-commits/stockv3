# N2-E7 Condition Layer Migration Review

## Summary

- migration_safe_to_apply: true
- additive_only: true
- affects_existing_rows: existing rows keep their data and receive NULL in newly added nullable columns; no backfill is planned
- requires_backup: true
- rollback_manual_only: true
- user_confirmation_required: true

## Schema Gap

- missing_tables: []
- missing_column_count: 16
- type_mismatch_count: 0
- not_null_risk_count: 15
- constraint_deferred_count: 10

Missing columns by table:

- board_condition_pool: policy_name, policy_hash, selected_reason, excluded_reason
- index_condition_pool: policy_name, policy_hash, selected_reason, excluded_reason
- stock_condition_basis: is_st, stock_status, official_daily_proof, financial_quality_status
- stock_condition_pool: policy_name, policy_hash, selected_reason, excluded_reason

## SQL Review

- additive_only: true
- nullable_only: true
- no_drop: true
- no_backfill: true
- no_not_null: true
- no_check_or_fk: true
- add_column_count: 16
- disallowed_hits: []

## Nullable Compatibility

- execute_py: compatible - basis_insert_row/pool_insert_row use row.get(...) and selected_reason/excluded_reason default to empty lists before insert
- basis_py: compatible - new stock basis fields are read from source facts for new dry-runs; missing source values remain nullable
- pool_py: compatible - default policy generates policy_name/policy_hash/selected_reason for new pool rows and uses row.get(...) for source evidence
- old_active_run: compatible - 005 adds nullable columns only; existing active-run rows can retain NULL policy/basis metadata until a future execute/backfill

## Boundaries

- This review did not execute migration SQL.
- This review did not write business data.
- This review did not pull market data or enter trigger/action/voice/mobile/sim/worker.
- N2-E8 still requires explicit user confirmation before applying 005.
