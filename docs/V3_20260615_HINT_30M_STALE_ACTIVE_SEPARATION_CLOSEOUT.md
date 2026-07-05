# V3 20260615 HINT 30m Stale Active Separation Closeout

Result: `CLOSEOUT_PASS`

layer_role: `runtime_control`

Gate: `V3_20260615_HINT_30M_STALE_ACTIVE_SEPARATION_POST_REVIEW_AND_CLOSEOUT_GATE`

## Summary

The stale 20260615 `BUY_HINT` / `30m_volume` lineage for `board:TDX:881470` is registered as `STALE`, preserved as historical evidence, and excluded by active N6 user-message query builders and N6 projection dry-run guard.

This artifact supersedes the prior `BLOCKED` closeout state. The only previous blocker was missing authenticated live active-query proof; the follow-up N6_user read-only gate produced `ACTIVE_QUERY_PASS` with returned item count `0` for `trade_date=20260615&q=881470`.

## Corrected Metric Proof

Status: `PASS`

Source artifacts:

- `docs/V3_20260615_HINT_30M_STALE_METRIC_POLLUTION_AUDIT.json`
- `docs/V3_20260615_HINT_30M_STALE_ACTIVE_LINEAGE_REGISTRY.json`
- `docs/V3_20260615_HINT_30M_ACTIVE_STALE_SEPARATION_IMPLEMENTATION.json`

Proof:

- `current_30m_virtual_amount=2348930635.56391`
- `previous_day_same_window_amount=2613103496`
- `amount_pass=false`
- corrected metric run: `v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_policy_fix_v1`

## Stale Registry Proof

Status: `PASS`

Registry: `V3_20260615_HINT_30M_STALE_ACTIVE_LINEAGE`

Classification: `STALE`

Historical policy:

- `delete_historical_rows=false`
- no historical facts are deleted or rewritten by the registry

Stale metric run IDs:

- `v3_n3_action_confirmation_metric_20260615_full_universe_replay_v1`
- `v3_n3_action_confirmation_metric_20260615_full_universe_formal_proof_enriched_v1`
- `v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1`

Stale N4 source trigger run IDs:

- `v3_n4_trigger_replay_20260615_after_n3_full_universe_metric_v1`
- `v3_n4_trigger_replay_20260615_after_formal_proof_enrichment_v1`
- `v3_n4_trigger_replay_20260615_attachment_rule_canonical_v1`

Stale N5 source action run IDs:

- `v3_n5_action_replay_20260615_after_n4_full_universe_trigger_v1`
- `v3_n5_action_replay_20260615_after_n4_formal_proof_enrichment_v1`
- `v3_n5_action_replay_20260615_attachment_rule_canonical_v1`

## Active UI Exclusion Proof

Status: `PASS_CODE_AND_TEST`

Code proof:

- `src/ashare_v3/user/stale_active_lineage.py` defines stale source action/trigger run registries and `is_stale_source_action_run_id`.
- `src/ashare_v3/web/n6_user_app.py` active app signal where-clause excludes `p.source_action_run_id = ANY(stale_source_action_run_ids)`.
- `src/ashare_v3/web/n6_user_app.py` UI v1 signal where-clause applies the same stale source action run exclusion.

Test proof:

- `tests/test_n6_user_app.py::test_b_track_signals_exclude_stale_hint_30m_source_action_runs` verifies stale rows are excluded from list/detail paths in the app model.

Fresh validation:

- `PYTHONPATH=src:tests python3 -m unittest tests.test_n6_user_app tests.test_n6_projection_plan tests.test_n6_projection_execute`
- result: `Ran 177 tests ... OK`

## Raw Diagnostic Stale Label Proof

Status: `PASS`

Code proof:

- `src/ashare_v3/web/n6_ui_v1.py` `n4_message_item` returns `stale_lineage=true` and `lineage_classification=STALE` for stale N4 source trigger runs.
- `src/ashare_v3/web/n6_ui_v1.py` `n5_message_item` returns `stale_lineage=true` and `lineage_classification=STALE` for stale N5 source action runs.

Test proof:

- `test_n4_message_item_marks_stale_hint_30m_trigger_lineage`
- `test_n5_message_item_marks_stale_hint_30m_action_lineage`

## Projection Guard Proof

Status: `PASS`

Code proof:

- `src/ashare_v3/user/projection_plan.py` adds P0 quality gate `stale_source_action_run_id`.
- If `source_action_run_id` is in the stale registry, N6 projection dry-run returns `BLOCKED`.

Test proof:

- `tests/test_n6_projection_plan.py::test_stale_hint_30m_source_action_run_blocks_projection_plan`

## 8786 Runtime Proof

Status: `PASS`

Proof:

- `127.0.0.1:8786` is listening on PID `1853`.
- Process command: `Python scripts/run_n6_user_app.py`.
- Process cwd: `/Users/chuanfuchen/Documents/A股监控系统v3`.
- Process start: `2026-06-16 08:46:56 +0800`.
- Referenced stale-separation files were modified before process start, latest checked source mtime: `src/ashare_v3/web/n6_ui_v1.py` at `2026-06-16 08:45:46 +0800`.
- `GET /n6/login` returned HTTP `200 OK`.

Authenticated live query:

- `GET /api/n6/app/v1/signals?trade_date=20260615&q=881470` without session returned HTTP `401` with `{"ok":false,"error":"unauthorized"}`.
- Follow-up N6_user live query gate created one temporary admin session.
- Login returned HTTP `302`.
- `GET /api/n6/me` returned HTTP `200`.
- Authenticated user: `admin / user_id=1 / role=admin`.
- Authenticated target query returned HTTP `200`.
- returned item count: `0`.
- Detail API was not called because count was `0`.

Session side effect proof:

- admin session before: `116`, max id `173`.
- admin session after: `117`, max id `174`.
- new session: `user_session_id=174`, active=`true`, issued_at=`2026-06-16 09:09:19+08`.
- temporary cookie file deleted; token/cookie not printed.

N6 business table proof:

- before `user_projection_run/user_signal_projection/user_signal_card/user_notification_queue = 19/28821/28821/5765`.
- after `user_projection_run/user_signal_projection/user_signal_card/user_notification_queue = 19/28821/28821/5765`.
- no projection/card/queue modification.

## Policy-Fix Projection Proof

Status: `PASS_ARTIFACT`

Source artifact:

- `docs/V3_20260615_ATTACHMENT_RULE_CANONICAL_POLICY_FIX_FULL_UNIVERSE_REPLAY_CLOSEOUT.json`

Proof:

- `n6_run=1`
- `user_signal_projection=2998`
- `user_signal_card=2998`
- `user_notification_queue=0`
- N6 run ID: `v3_n6_user_projection_20260615_attachment_rule_canonical_policy_fix_v1`
- N5 source action run ID: `v3_n5_action_replay_20260615_attachment_rule_canonical_policy_fix_v1`

Contract/preflight proof:

- `planned_writes.user_projection_run=1`
- `planned_writes.user_signal_projection=2998`
- `planned_writes.user_signal_card=2998`
- `planned_writes.user_notification_queue=0`

## Validation Summary

Fresh validation run in this gate:

- N6 tests: `PASS`, `Ran 177 tests in 2.602s OK`
- JSON parse: `PASS`
- compileall: `PASS`
- git diff --check: `PASS`

Notes:

- `pytest` was not installed for either system Python or bundled Codex Python, so unittest was used directly with the same three test modules.

## Forbidden Scope Proof

Status: `PASS`

This closeout did not:

- delete historical data
- rewrite historical facts
- execute rollback SQL
- consume or update outbox/inbox/checkpoint
- start scheduler or worker
- touch voice/mobile/sim/position/order/real trade
- read the old system
- connect directly to PostgreSQL

The follow-up N6_user live query gate created one temporary admin auth session for the authenticated read-only API verification. No N6 projection/card/queue business table changed.

Only read-only commands, code/artifact inspection, curl reads, and local validation commands were run by runtime_control. The only files created or modified by the runtime_control closeout are this closeout markdown and its JSON companion.

## Remaining Risk

- Temporary admin session `user_session_id=174` was created by the follow-up N6_user live query gate and was reported active at proof time. Revoke or allow TTL expiry according to normal N6 auth policy.

## Next Recommended Gate

`OPTIONAL_N6_TEMP_AUTH_SESSION_REVOKE_REVIEW`

Purpose: if desired, verify or revoke temporary admin session `user_session_id=174` without touching projection, outbox/inbox/checkpoint, worker, or trading state.
