# N2 Period Context QFQ As-Of Alignment 20260615 Active Supersede Post Review

- result: `POST_REVIEW_PASS`
- run_id: `condition_layer_20260615_source_20260615_for_20260616_v2`
- previous_active_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- source_trade_date: `20260615`
- for_trade_date: `20260616`
- execute_report: `docs/N2_PERIOD_CONTEXT_QFQ_ASOF_ALIGNMENT_20260615_ACTIVE_SUPERSEDE_EXECUTE_REPORT.json`

## Execute Proof

- command_exit_code: `0`
- execute_report_json_parse: `true`
- writes_performed: `true`
- will_execute_sql: `true`
- minute_kline_pulled: `false`
- n3_lineage_auto_switch: `false`
- downstream_layers_touched: `false`

## Active Supersede Proof

- v2 status: `passed_active`
- v1 status: `superseded`
- active_run_count: `1`

## Row Count Proof

- condition_basis: `stock=5504 index=83 board=427`
- condition_pool: `stock=4215 index=183 board=307`
- minute_target_scope: `stock=4194 index=183 board=307`
- condition_display_basis: `stock=1822 index=83 board=127`
- monitor_target: `stock=5504 index=83 board=427`
- common_condition_quality_item: `103`
- common_condition_run: `1`
- row_counts_match_expected: `true`

## Quality Proof

- P0 failed: `0`
- non-passed warnings: `P1=4 / P2=4`
- note: P0 severity rows are passed guard checks, not blocking failures.

## 002831 Live Proof

- Q: `volume_up / volume_up`
- M: `low_volume_up / low_volume_up`
- W: `low_volume_up / volume_up`
- D: `low_volume_up / low_volume_up`
- Y: `volume_up / volume_up`
- level_up_score: `3098`

## Boundary Proof

- outbox/inbox/checkpoint delta: `0/0/0`
- N3/N4/N5/N6 refs for v2: `0/0/0/0`
- worker_started: `false`
- rollback_executed: `false`

## Rollback Proof

- rollback_sql_path: `sql/N2_period_context_qfq_asof_alignment_20260615_active_supersede_rollback.sql`
- rollback exists: `true`
- restores v1 passed_active: `true`
- guards event infra: `true`
- guards downstream refs: `true`
- no DROP/TRUNCATE/CASCADE: `true`

## Conclusion

N2 period_context QFQ/as-of active supersede is complete for N2. Downstream lineage refresh must be handled by a separate N3 gate.

Recommended next gate: `N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_READINESS_GATE`.
