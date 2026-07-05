# N6 Action Projection 20260608 v13 index-all until 09:52 Post-review

- result: `POST_REVIEW_PASS`
- layer_role: `runtime_control`
- reviewed_at: `2026-06-08T13:01:22+08:00`
- source_action_run_id: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- user_projection_run_id: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`

## Proof Summary

- execute report JSON parsed and shows `result=EXECUTED`
- live DB scoped rows match expected: projection run `1`, signal projection `201`, signal card `201`, notification queue `0`
- distribution: `ActionEligible / eligible = 201`; card status `candidate = 201`
- N5 outbox remains `ActionEligible / pending = 201`; no N5 inbox/checkpoint rows for this N6 source action run

## Row Count Proof

| table | expected | actual |
|---|---:|---:|
| `user_projection_run` | 1 | 1 |
| `user_signal_projection` | 201 | 201 |
| `user_signal_card` | 201 | 201 |
| `user_notification_queue` | 0 | 0 |

## UI Readonly Smoke

- `http://127.0.0.1:8786/n6/action-events` -> `200` / `ok`
- `http://127.0.0.1:8786/api/n6/ui/v1/signals?source_run_id=user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952` -> `401` / `auth_required_no_bypass`
- `http://127.0.0.1:8786/api/n6/ui/v1/lineage-stats` -> `401` / `auth_required_no_bypass`

Runtime control did not create a login session or bypass auth. Authenticated UI smoke can be run as an optional follow-up; projection/card DB closeout and UI unit tests passed.

## Rollback Proof

- rollback SQL: `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`
- hard-fail guard is before the first executable DELETE/UPDATE
- no `CASCADE`, no `DROP`, no `TRUNCATE`
- rollback was not executed

## Forbidden Scope Proof

- `n5_outbox_consumed` = `False`
- `n5_outbox_status_updated` = `False`
- `n5_inbox_checkpoint_updated` = `False`
- `user_notification_queue_scoped_rows` = `0`
- `delivery_push_voice_mobile` = `0`
- `decision_sim_order_trade_position_pnl_refs` = `0`
- `worker_started` = `False`
- `proposal_order_trade` = `False`
- `real_trade` = `False`
- `old_system_touched` = `False`
- `rollback_executed` = `False`

## Validation Summary

- `rollback_static_check`: `PASS`
- `compileall`: `PASS`
- `targeted_runtime_tests`: `PASS: 81 tests OK`
- `n6_user_app_tests`: `PASS: 80 tests OK`
- `key_json_parse`: `PASS`
- `new_artifact_json_parse`: `PASS`
- `git_diff_check`: `PASS`

Recommended next gate: `RUNTIME_20260608_N3_TO_N6_ONE_SHOT_CLOSEOUT_GATE`
