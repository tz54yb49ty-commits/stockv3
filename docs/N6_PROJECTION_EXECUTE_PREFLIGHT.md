# N6 Projection Execute Preflight

## Summary

- result: DESIGN_PASS
- layer_role: N6_user
- scope: projection execute preflight design only
- preflight_executed_now: false
- runner_implemented: true
- database_write_now: false
- N5 outbox consumed: false
- N5 outbox status updated: false
- worker_started: false
- actual_push: false
- real_trade: false

This document defines the read-only preflight that must pass before any future
N6 shadow projection execute runner may write N6 projection rows.

## Runner Implementation Candidate

Implemented runner path:

```text
scripts/run_n6_projection_once.py
```

Required command shape for a future final execute gate:

```text
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py \
  --projection-run-id user_projection_shadow_20260525__action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249 \
  --execute \
  --user-confirmed
```

The runner must block before database reads unless both `--execute` and
`--user-confirmed` are present. This document does not authorize running that
command.

## Preflight Inputs

Read-only inputs:

- `common_event_outbox` for N5 `ActionEvent / HintEvent` pending rows only.
- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `user_account`
- `user_filter_profile`
- N6 target and forbidden table row counts.

Forbidden preflight inputs:

- N4 trigger facts or outbox;
- N5 action facts, N5 inbox, N5 checkpoint, or N5 delivery attempts;
- N3 market facts or display events;
- N1 historical K;
- old synthetic outbox.

## Preflight Gates

### P0 Baseline Gates

1. `layer_role = N6_user`.
2. N6 schema tables exist for all 14 N6 tables.
3. Admin exists:
   - `login_name=admin`
   - `user_id=1`
   - `role=admin`
   - `status=active`
4. Exactly one active default admin filter profile exists.
5. First MVP baseline zero guard:
   - `user_projection_run=0`
   - `user_signal_projection=0`
   - `user_signal_card=0`
   - `user_notification_queue=0`
   - `user_signal_decision=0`
   - `user_session=0`
   - `user_watchlist=0`
   - `user_watchlist_item=0`
   - `user_sim_account=0`
   - `user_sim_order=0`
   - `user_sim_trade=0`
   - `user_sim_position=0`
6. N5 pending outbox baseline:
   - `ActionEvent:pending=479`
   - `HintEvent:pending=9`
   - input events total `488`
7. N5 outbox rows for the accepted range must all have:
   - `source_layer=N5_action`
   - `status=pending`
   - `source_run_id` equal to the accepted current-real N5 run id
   - event type in `ActionEvent / HintEvent`
8. Required event envelope fields are present.
9. Required projection payload fields are present, especially:
   - `direction`
   - `signal_type`
   - `action_type`
   - `lane`
   - `condition_key`
   - `trigger_period`
   - `action_key`
   - `source_condition_run_id`
   - `source_market_trace`
10. No duplicate `source_event_id` within the planned run.
11. All rows that would be inserted have non-empty `code` and `name` from N2
    display basis.
12. Planned row counts exactly match:
    - `user_projection_run=1`
    - `user_signal_projection=488`
    - `user_signal_card=488`
    - `user_notification_queue=488`
    - `user_signal_decision=0`
    - sim rows `0`
13. The planned execute does not include SQL or code paths to:
    - update N5 outbox;
    - create N5 inbox/checkpoint rows;
    - create sessions, decisions, sim rows, watchlist rows;
    - start a worker;
    - push notification, voice, mobile;
    - submit real trades.

Any failed P0 gate blocks execute.

### P1 Warning Gates

Known current warnings:

- `current_price_missing=488`
- `target_price_missing=192`
- `expected_return_pct_missing=192`
- `board_context_missing=488`

P1 warnings do not block shadow execute when P0 is zero. They must be written
into `quality_summary_json` and row payload JSON.

### P2 Notes

Known current notes:

- N2 display-basis contains more rows than the current N5 event range.
- N5 outbox remains pending because shadow execute does not consume it.
- Replay/rebuild is possible by a new `user_projection_run_id`.

## Preflight Output

The preflight report must include:

- `PREFLIGHT_PASS / PREFLIGHT_BLOCKED`
- blocker list
- source action run id
- proposed `user_projection_run_id`
- N5 outbox before count
- planned row counts
- baseline table counts
- missing-field summary
- P0/P1/P2 counts and items
- side-effect plan, all false for forbidden scopes
- rollback SQL path
- explicit `allow_execute=true` only when P0 is zero

Recommended report paths for the future runner:

- `docs/N6_PROJECTION_EXECUTE_PREFLIGHT_REPORT.md`
- `docs/N6_projection_execute_preflight_report.json`

These report files are not created in this design-only step.

## Execute Final Gate

Even if preflight passes, actual shadow execute still requires a separate user
confirmation message. That final gate must explicitly authorize writing only:

- `user_projection_run`
- `user_signal_projection`
- `user_signal_card`
- `user_notification_queue`

It must also explicitly keep these blocked:

- N5 outbox consumption/status update
- N5 inbox/checkpoint
- session
- decision
- sim
- worker
- push
- real trade

## Decision

DESIGN_PASS.

Allowed next gate:

```text
N6 projection execute runner implementation
```

Still blocked:

- running execute
- consuming/updating N5 outbox
- worker, push, sim, decision, session, real trade
