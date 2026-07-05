# N6 Projection Execute Contract

## Summary

- result: DESIGN_PASS
- layer_role: N6_user
- contract_version: `N6-user-projection-shadow-execute-v1`
- scope: N6 MVP admin-only shadow projection execute contract
- runner_implemented: false
- database_write_now: false
- N5 outbox consumed: false
- N5 outbox status updated: false
- worker_started: false
- actual_push: false
- real_trade: false

This contract upgrades the reviewed dry-run plan into a future execute shape.
The execute remains a shadow projection: it writes only N6-owned projection
tables and does not consume, lock, deliver, or checkpoint N5 outbox rows.

## Current Baseline

Reviewed dry-run evidence:

- `result = DRY_RUN_PASS`
- input N5 events: `488`
- `ActionEvent = 479`
- `HintEvent = 9`
- planned projections/cards/notifications: `488 / 488 / 488`
- planned decisions: `0`
- planned sim rows: `0`
- display-basis missing: `0`
- P0/P1/P2: `0/4/2`

Required first shadow execute baseline:

- active admin exists with `user_id=1`, `login_name=admin`, `role=admin`,
  `status=active`;
- exactly one active default admin `user_filter_profile`;
- N6 projection target tables are empty:
  `user_projection_run`, `user_signal_projection`, `user_signal_card`,
  `user_notification_queue`;
- forbidden N6 rows are empty for the MVP gate:
  `user_session`, `user_signal_decision`, `user_watchlist`,
  `user_watchlist_item`, `user_sim_account`, `user_sim_order`,
  `user_sim_trade`, `user_sim_position`;
- N5 current-real pending outbox remains exactly
  `ActionEvent=479`, `HintEvent=9`.

If any baseline row count differs, execute must be `BLOCKED` until a new
contract review accepts the changed state or the old rows are rolled back by
their own reviewed rollback.

## Input Contract

Future shadow execute may read only:

1. N5 standard pending outbox events:
   - table: `common_event_outbox`
   - `source_layer = 'N5_action'`
   - `source_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`
   - `status = 'pending'`
   - `event_type IN ('ActionEvent', 'HintEvent')`
2. N2 display enrichment tables:
   - `stock_condition_display_basis`
   - `index_condition_display_basis`
   - `board_condition_display_basis`
3. N6 admin scope tables:
   - `user_account`
   - `user_filter_profile`

It must not read N4 trigger facts, N5 action facts, N3 market facts, old
synthetic outbox, N1 historical K, or any upstream naked fact table to replace
the N5 event contract.

## Execute Write Scope

After a separate implementation and final user confirmation gate, future
shadow execute may write only:

1. `user_projection_run`
2. `user_signal_projection`
3. `user_signal_card`
4. `user_notification_queue`

All four table families must be written in one transaction. If any row insert
fails, the transaction must roll back.

The execute must not write:

- `user_signal_decision`
- `user_session`
- `user_watchlist`
- `user_watchlist_item`
- `user_sim_account`
- `user_sim_order`
- `user_sim_trade`
- `user_sim_position`
- N5 outbox status, lock, delivery, inbox, checkpoint, or delivery attempt
- N1-N5 facts or events
- push, voice, mobile, worker, or real trade state

## Projection Run

Recommended run id:

```text
user_projection_shadow_execute_20260525__action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
```

`user_projection_run` must store:

- `projection_contract_version = N6-user-projection-shadow-execute-v1`
- `source_layer = N5_action`
- `source_action_run_id`
- `source_event_types = ['ActionEvent', 'HintEvent']`
- `source_n5_outbox_range` JSON containing:
  - `event_status = pending`
  - `event_type_counts`
  - `min_outbox_id`
  - `max_outbox_id`
  - `first_event_time`
  - `last_event_time`
  - `event_id_sha256`
  - `outbox_consumed = false`
  - `outbox_status_updated = false`
- `input_event_count = 488`
- `output_projection_count = 488`
- P0/P1/P2 summary from preflight
- status transition within the transaction:
  `ready` or `executing` -> `passed`; on failure the transaction rolls back.

## Dedup And Uniqueness

Event ordering must be deterministic:

```text
partition_key, event_time, outbox_id, event_id
```

Projection dedup key:

```text
user_projection_run_id + user_id + source_event_id
```

This is enforced by the existing unique key on
`user_signal_projection(user_projection_run_id, user_id, source_event_id)`.

Card uniqueness:

```text
user_projection_run_id + user_id + user_signal_projection_id
```

This is enforced by the existing unique key on
`user_signal_card(user_projection_run_id, user_id, user_signal_projection_id)`.

Notification queue dedup must be implemented by the runner because the 020
schema intentionally has only a source index, not a unique notification key.
For the MVP execute, the runner must create exactly one notification per
signal projection and assert:

```text
count(user_notification_queue where user_projection_run_id = run_id) =
count(user_signal_projection where user_projection_run_id = run_id)
```

Recommended notification logical key:

```text
user_projection_run_id + user_id + notification_source + source_event_id
```

## Row Mapping

`user_signal_projection`:

- `user_id = 1`
- `user_filter_profile_id = admin default profile`
- `user_watchlist_id = null`
- `permission_scope = self`
- source fields copied from N5 outbox envelope
- `source_action_event_id = source_event_id` for MVP
- `source_action_run_id = N5 outbox source_run_id`
- `asset_kind`, `identity_key` copied from N5 envelope
- `code`, `name` from N2 display basis
- `direction`, `signal_type` from N5 payload
- `target_price`: buy uses `buy_target_price`; sell uses `sell_target_price`
- `current_price = null` unless a future N5 contract carries it
- `expected_return_pct`: buy/sell value from `target_price_summary_json`
- display trace fields from the matched physical display-basis row
- `projection_status = visible`
- missing warnings preserved in `display_payload_json`

`user_signal_card`:

- one card per projection
- `card_type = hint` for `HintEvent`
- `card_type = buy_candidate` or `sell_candidate` for `ActionEvent`
- `card_status = active`
- title and summary derived from code/name, signal type, direction, and
  optional target/expected-return fields

`user_notification_queue`:

- one queued candidate per card
- `notification_source = n5_action_event` for `ActionEvent`
- `notification_source = n5_hint_event` for `HintEvent`
- `queue_status = queued_only`
- `channel = broadcast_queue`
- no provider payload, delivery attempt, voice/mobile send, or push token

## Missing Field Quality Policy

P0 blockers:

- missing active admin or active default admin profile;
- missing any of the four allowed target tables;
- baseline=0 guard fails for projection/card/queue/run or forbidden N6 tables;
- N5 pending outbox counts differ from `ActionEvent=479`, `HintEvent=9`;
- input event type outside `ActionEvent / HintEvent`;
- source layer outside `N5_action`;
- required N5 envelope field missing;
- required payload field missing for `direction` or other projection-critical
  fields;
- display basis cannot provide required `code` or `name`;
- duplicate source events within the planned run;
- any attempted N5 outbox mutation, worker start, push, sim, decision, session,
  or real trade write.

P1 warnings:

- `current_price_missing = 488`, because current price is outside the MVP input
  contract;
- `target_price_missing = 192`;
- `expected_return_pct_missing = 192`;
- optional board context missing;
- display-basis row missing when the event can still be accounted for without
  upstream backfill.

P2 notes:

- N2 display-basis row counts exceed the current N5 event range;
- N5 outbox remains pending because this is shadow projection execute;
- execute writes are replayable and rollbackable by `user_projection_run_id`.

P1/P2 do not block shadow execute when P0 is zero. They must be stored in
`quality_summary_json` and in per-row payload JSON where relevant.

## Replay And Rebuild Strategy

Replay is allowed only from the same N5 standard `ActionEvent / HintEvent`
event range into a new `user_projection_run_id`.

Rebuild options:

1. Roll back the previous N6 projection run by `user_projection_run_id`, then
   rerun with the same run id after the rollback has marked/deleted all target
   rows.
2. Preserve the previous run and replay into a new run id for comparison.

Neither option may mutate N5 outbox status. N5 event rows remain the immutable
source contract for N6.

## Rollback Strategy

Rollback must use `user_projection_run_id` and may delete only rows created by
that run:

1. `user_notification_queue`
2. `user_signal_card`
3. `user_signal_projection`
4. `user_projection_run`

Rollback must block if linked `user_signal_decision` or `user_sim_*` rows exist.
Rollback must not touch `user_account`, `user_filter_profile`, `user_session`,
`user_watchlist`, N5 outbox, N5 action facts, N1-N4 facts, push state, worker
state, or real trading state.

Rollback draft: `sql/N6_projection_business_rollback.sql`.

## Decision

DESIGN_PASS.

Allowed next gate:

```text
N6 projection execute runner implementation
```

Still blocked until a separate final confirmation:

- running projection execute
- consuming or updating N5 outbox
- creating sessions, decisions, sim rows, watchlists
- worker, push, voice, mobile, or real trading
