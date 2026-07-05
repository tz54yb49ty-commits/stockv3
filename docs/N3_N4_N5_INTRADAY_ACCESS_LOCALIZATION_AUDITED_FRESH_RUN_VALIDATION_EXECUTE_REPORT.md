# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Execute Report

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_EXECUTE_GATE`

Result: `BLOCKED`

Layer role: `runtime_control`

Generated at: `2026-06-07T04:30:04.991076+00:00`

## Summary

The approved read-only probes did not all complete successfully, so this execute gate is blocked. The audit evidence collected so far shows no denied external display/membership table reads and no forbidden side effects, but N4 did not persist one required audit segment because the generated artifact filename exceeded the filesystem limit.

- audit artifacts: `5`
- audit entries: `108`
- denied table hit entries: `0`
- db write attempted entries: `0`
- worker started entries: `0`
- outbox consumed entries: `0`
- checkpoint updated entries: `0`
- pre/post forbidden snapshot equal: `True`

## Command Results

### AFR-N3-001 N3_market_data

- exit_code: `2`
- result: `BLOCKED`
- blocking assessment: P0: approved N3 probe targets an already materialized projection_run_id with downstream refs, so it cannot serve as a fresh execute-style validation baseline after closeout.

Failed quality items:

- `n3_action_metric_materialization_scoped_baseline_zero`: {"board_action_confirmation_projection_metric": 0, "common_event_consumer_checkpoint": 0, "common_event_inbox": 316, "common_event_outbox": 605, "common_market_data_quality_item": 8, "common_market_data_run": 1, "downstream_refs": {"common_action_event": 316, "common_trigger_match": 0, "common_trigger_state": 0, "n6_virtual_account": 0, "n6_virtual_order": 0, "n6_virtual_pnl_snapshot": 0, "n6_virtual_position": 0, "n6_virtual_position_event": 0, "n6_virtual_trade": 0, "total": 1526, "user_card_projection": 0, "user_notification_queue": 0, "user_signal_card": 605, "user_signal_projection": 605, "user_sim_order": 0, "user_sim_position": 0, "user_sim_trade": 0}, "index_action_confirmation_projection_metric": 0, "stock_action_confirmation_projection_metric": 316}
- `n3_action_metric_materialization_downstream_refs_zero`: {"common_action_event": 316, "common_trigger_match": 0, "common_trigger_state": 0, "n6_virtual_account": 0, "n6_virtual_order": 0, "n6_virtual_pnl_snapshot": 0, "n6_virtual_position": 0, "n6_virtual_position_event": 0, "n6_virtual_trade": 0, "total": 1526, "user_card_projection": 0, "user_notification_queue": 0, "user_signal_card": 605, "user_signal_projection": 605, "user_sim_order": 0, "user_sim_position": 0, "user_sim_trade": 0}

### AFR-N4-001 N4_trigger

- exit_code: `1`
- result: `COMMAND_ERROR`
- blocking assessment: P0: N4 approved probe did not complete and one required audit segment was not persisted; audit artifact filename hardening is required.

### AFR-N5-001 N5_action

- exit_code: `2`
- result: `PREFLIGHT_BLOCKED`
- blocking assessment: P0: approved N5 probe reports n5_0_buy_sell_hint_preserved failed (BUY_HINT=0, SELL_HINT=0) under current live N4/N5 state.

Failed quality items:

- `n5_0_buy_sell_hint_preserved`: BUY_HINT=0 SELL_HINT=0

## Blockers

- `P0-N3-FRESH-RUN-BASELINE-NONZERO` (P0): N3 approved probe returned BLOCKED/PREFLIGHT_BLOCKED because the target projection_run_id already has run/quality/metric/outbox/inbox rows and downstream refs.
  Required follow-up: Define a post-closeout read-only validation profile that audits existing N3 metric lineage without requiring scoped baseline zero, or choose a fresh non-materialized validation run_id in a later gate.
- `P0-N4-AUDIT-FILENAME-TOO-LONG` (P0): N4 approved probe failed before report completion because ArtifactAuditSink generated a path exceeding the filesystem filename limit.
  Required follow-up: Harden ArtifactAuditSink/audit path builder with deterministic short filenames plus full audit_run_id inside JSON, then rerun the N4 probe.
- `P0-N5-LEGACY-PROBE-SEMANTIC-MISMATCH` (P0): N5 approved probe returned p0_count=1 under current live state.
  Required follow-up: Re-contract N5 validation probe for current repaired-context/full-metric-union lineage, or explicitly classify the legacy BUY_HINT/SELL_HINT preservation check as out-of-scope for this audited access localization validation.

## Audit Proof

Collected audit entries reference no denied external display/membership tables:

- `board_action_confirmation_projection_metric`
- `board_action_fact`
- `board_realtime_daily_snapshot`
- `board_trigger_context_snapshot`
- `common_action_event`
- `common_action_quality_item`
- `common_action_run`
- `common_condition_run`
- `common_event_consumer_checkpoint`
- `common_event_inbox`
- `common_event_outbox`
- `common_market_data_quality_item`
- `common_market_data_run`
- `common_position_event`
- `common_position_state`
- `common_trigger_match`
- `common_trigger_quality_item`
- `common_trigger_run`
- `common_trigger_state`
- `index_action_confirmation_projection_metric`
- `index_action_fact`
- `index_realtime_daily_snapshot`
- `index_trigger_context_snapshot`
- `n6_virtual_account`
- `n6_virtual_order`
- `n6_virtual_pnl_snapshot`
- `n6_virtual_position`
- `n6_virtual_position_event`
- `n6_virtual_trade`
- `stock_action_confirmation_projection_metric`
- `stock_action_fact`
- `stock_realtime_daily_snapshot`
- `stock_trigger_context_snapshot`
- `user_notification_queue`
- `user_signal_card`
- `user_signal_projection`
- `user_sim_order`
- `user_sim_position`
- `user_sim_trade`

## Forbidden Scope Proof

- No DB writes were performed by this gate; audit `db_write_attempted_entries=0` and guarded pre/post snapshots are unchanged.
- No outbox/inbox/checkpoint consumption or mutation was performed; audit consumption/checkpoint flags are 0.
- No worker was started; audit `worker_started_entries=0`.
- No delivery/push/voice/mobile, sim/position/PnL/real_trade, proposal/order/trade, PostgreSQL config change, migration, or pg_stat_statements enablement occurred.

## P0/P1/P2

`P0/P1/P2 = 3/1/0`

P1: 33 N1/N2/ingestion script direct connect sites remain documented outside this N3/N4/N5 runtime validation scope.

## Next Gate Recommendation

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_ARTIFACT_FILENAME_HARDENING_GATE`

## Validation Summary

- JSON parse: `PASS`
- `python3 -m compileall src/ashare_v3/observability src/ashare_v3/trigger src/ashare_v3/action`: `PASS`
- structured query audit/adoption unittests: `22 OK`
- `git diff --check`: `PASS`
