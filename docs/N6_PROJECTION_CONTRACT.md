# N6 Projection Contract

## Summary

- result: DESIGN_PASS
- layer_role: N6_user
- contract_version: `N6-user-projection-mvp-v1`
- scope: MVP admin-only projection dry-run and future execute contract
- current phase: design only
- database_write: false
- N5 outbox consumed: false
- worker_started: false
- actual_push: false
- real_trade: false

## Contract Inputs

The MVP projection contract has two approved read paths.

Primary event input:

- `common_event_outbox`
- `source_layer = 'N5_action'`
- `status = 'pending'`
- `event_type IN ('ActionEvent', 'HintEvent')`
- current real `source_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`

Display enrichment input:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`

User scoping input:

- active admin from `user_account`
- admin default profile from `user_filter_profile`

Explicitly forbidden as replacement inputs:

- `RiskEvent` and `PositionEvent` in the current MVP path;
- N4 `TriggerMatched` or `TriggerPendingMarketData`;
- N3 `MarketSnapshotUpdated`, `MinuteBarClosed`, C3 outbox, or C2B enrichment;
- N4/N5 naked fact tables;
- old synthetic outbox;
- N1 historical K or official daily facts.

## Event Contract

Required N5 outbox envelope fields:

- `outbox_id`
- `event_id`
- `event_type`
- `event_schema_version`
- `trade_date`
- `asset_kind`
- `identity_key`
- `event_time`
- `source_layer`
- `source_run_id`
- `dedup_key`
- `partition_key`
- `payload_json`
- `status`

Required payload fields for MVP projection:

- `run_id`
- `asset_kind`
- `identity_key`
- `direction`
- `signal_type`
- `action_type`
- `lane`
- `condition_key`
- `trigger_period`
- `action_key`
- `dedup_key`
- `source_condition_run_id`
- `source_market_data_run_id`
- `source_market_trace`

The dry-run and future execute must preserve the full source trace in compact JSON fields and must not infer missing trigger/action state by reading upstream naked facts.

## User Scope

MVP projection is admin-only:

- `user_id = 1`
- `login_name = admin`
- `role = admin`
- `status = active`
- one active default `user_filter_profile`
- no watchlist filtering in MVP because watchlist tables are empty

The default profile currently has all MVP checkboxes enabled, so no current N5 events are suppressed by user filter. If future profiles disable a category, the runner must record suppression in dry-run output before any execute gate accepts it.

## Output Contract

Future execute may write only these N6-owned tables after a separate final gate:

- `user_projection_run`
- `user_signal_projection`
- `user_signal_card`
- `user_notification_queue`

Future execute must not write:

- `user_signal_decision`
- `user_session`
- `user_watchlist`
- `user_watchlist_item`
- `user_sim_account`
- `user_sim_order`
- `user_sim_trade`
- `user_sim_position`
- N1-N5 tables

Dry-run writes none of the above business rows and only emits report artifacts.

## Count Contract

For the current accepted input range:

- input N5 events: `488`
- `ActionEvent`: `479`
- `HintEvent`: `9`
- accepted admin events: `488`
- display matched events: `488`
- planned `user_projection_run`: `1`
- planned `user_signal_projection`: `488`
- planned `user_signal_card`: `488`
- planned `user_notification_queue`: `488`
- planned `user_signal_decision`: `0`
- planned sim rows: `0`

The current event distribution is:

| Event type | Direction | Signal type | Action type | Lane | Count |
|---|---|---|---|---|---:|
| `ActionEvent` | buy | `B_BUY_30M_VOL` | `buy_candidate` | `policy_pending` | 305 |
| `ActionEvent` | sell | `S_SELL_30M_SHRINK` | `sell_candidate` | `policy_pending` | 174 |
| `HintEvent` | buy | `BUY_HINT` | `buy_candidate` | `hint` | 6 |
| `HintEvent` | sell | `SELL_HINT` | `sell_candidate` | `hint` | 3 |

## Idempotency And Replay

Dry-run must be deterministic for the same N5 outbox range:

- sort by `partition_key`, `event_time`, `outbox_id`, `event_id`;
- deduplicate by `user_id + source_event_id` within a planned `user_projection_run_id`;
- preserve N5 `dedup_key` as `source_event_dedup_key`;
- preserve `source_action_run_id`.

Future execute must rely on existing N6 unique constraints:

- `user_signal_projection(user_projection_run_id, user_id, source_event_id)`
- `user_signal_card(user_projection_run_id, user_id, user_signal_projection_id)`

Replay is allowed from the same N5 `ActionEvent / HintEvent` events into a new `user_projection_run_id`. Replay must not mutate N5 outbox status.

## Notification Contract

MVP notification queue is queue-only:

- `queue_status = 'queued_only'`
- `channel = 'broadcast_queue'`
- `notification_source = 'n5_action_event'` for `ActionEvent`
- `notification_source = 'n5_hint_event'` for `HintEvent`

No provider payload, push token, voice engine call, delivery attempt, or mobile send is part of this contract.

## Quality Contract

P0 blockers:

- missing active admin or default profile;
- missing N6 projection schema table;
- event input outside N5 `ActionEvent / HintEvent`;
- source layer outside `N5_action`;
- current outbox count mismatch without a new final gate;
- required envelope field missing;
- required payload field missing;
- required card field `code` or `name` cannot be filled from N2 display basis.

P1 warnings:

- display-basis row missing;
- optional target price missing;
- optional expected return missing;
- optional board context missing;
- current price missing from MVP inputs.

P2 notes:

- N2 display basis may contain many more rows than current N5 events; N6 only projects N5 events in this MVP path.
- N5 outbox remains pending by design during dry-run.

## Boundary Contract

Dry-run and future execute must not:

- consume or mark N5 outbox rows delivered;
- lock N5 outbox rows;
- write N5 inbox/checkpoint;
- read N4/N5 naked facts as a substitute for events;
- write back N1-N5 facts;
- create sessions;
- create user decisions;
- create sim rows;
- start worker;
- push voice/mobile;
- submit real trades.

## Rollback Contract

Dry-run rollback is not needed because no DB rows are written.

Future execute rollback is a business rollback by `user_projection_run_id`. It may delete only:

- queued notification rows for that run;
- signal cards for that run;
- signal projections for that run;
- the projection run row.

It must block if signal decisions or sim rows are already linked to the run, because that means user intent or shadow simulation has been created and needs a separate rollback contract.

Rollback must not touch N5 outbox, N5 action facts, admin account, admin filter profile, sessions, N1-N4 facts, push state, or real trading state.

## Decision

DESIGN_PASS.

Allowed next gate:

```text
N6 projection dry-run runner implementation
```

Execute remains blocked until a future final gate explicitly authorizes N6 projection writes and N5 outbox consumption policy.
