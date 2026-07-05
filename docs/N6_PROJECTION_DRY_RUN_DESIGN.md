# N6 Projection Dry-Run Design

## Summary

- result: DESIGN_PASS
- layer_role: N6_user
- scope: N6 MVP projection dry-run design / contract only
- runner_implemented: false
- database_write: false
- N5 outbox consumed: false
- N5 outbox status updated: false
- user projection rows written: false
- session created: false
- notification pushed: false
- sim rows written: false
- real_trade: false

## Background

Current upstream state for this design:

- 020 N6 schema migration passed.
- N6 admin bootstrap passed.
- `admin` is active with `user_id=1`.
- `user_filter_profile` row count is `1`.
- `user_session` row count is `0`.
- N6 watchlist, projection, notification, decision, and sim tables are all `0`.
- N5 standard outbox remains pending:
  - `ActionEvent = 479`
  - `HintEvent = 9`

Current read-only evidence for the dry-run plan:

- N5 pending `ActionEvent / HintEvent` input events: `488`.
- N2 display-basis rows available:
  - `stock_condition_display_basis = 5504`
  - `index_condition_display_basis = 81`
  - `board_condition_display_basis = 428`
- Current N5 pending events are all stock events and all `488` match `stock_condition_display_basis` by `identity_key` and `source_condition_run_id`.
- `code/name` missing count is `0`.
- Optional target and expected-return warnings:
  - buy target / buy expected return missing: `100`
  - sell target / sell expected return missing: `92`
  - `current_price` is not present in the MVP input contract and must stay null with a missing warning.

## Input Boundary

N6 projection dry-run may read only:

1. N5 standard pending outbox events:
   - `source_layer = 'N5_action'`
   - `status = 'pending'`
   - `event_type IN ('ActionEvent', 'HintEvent')`
   - current real `source_run_id = action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`
2. N2 display-input tables:
   - `stock_condition_display_basis`
   - `index_condition_display_basis`
   - `board_condition_display_basis`
3. N6 user tables for admin MVP scoping:
   - `user_account`
   - `user_filter_profile`

Dry-run must not read N4 trigger facts, N5 action facts, N3 market facts, old synthetic outbox, or N1 historical K data to replace the N5 event contract.

Dry-run must not update `common_event_outbox.status`, `attempt_count`, `locked_by`, `locked_at`, `delivered_at`, or any N5 inbox/checkpoint. Future real N5 outbox consumption requires a separate N6 execute final gate.

## Dry-Run Algorithm

1. Run read-only preflight.
   - Confirm admin exists: `login_name=admin`, `role=admin`, `status=active`.
   - Confirm exactly one active default admin filter profile exists.
   - Confirm `user_session=0`.
   - Confirm projection, notification, decision, watchlist, and sim rows remain `0` for the first MVP dry-run readiness gate.
   - Confirm N5 outbox counts remain `ActionEvent=479`, `HintEvent=9`.

2. Read N5 standard events.
   - Query only N5 pending `ActionEvent / HintEvent`.
   - Preserve envelope fields: `outbox_id`, `event_id`, `event_type`, `event_schema_version`, `trade_date`, `asset_kind`, `identity_key`, `event_time`, `source_layer`, `source_run_id`, `dedup_key`, `partition_key`, `payload_json`.
   - Preserve payload fields including `direction`, `signal_type`, `action_type`, `lane`, `condition_key`, `trigger_period`, `source_condition_run_id`, `source_market_data_run_id`, and `source_market_trace`.

3. Join N2 display basis only for enrichment.
   - `stock`: join `stock_condition_display_basis` on `stock_identity_key = identity_key` and `run_id = payload_json.source_condition_run_id`.
   - `index`: join `index_condition_display_basis` on `index_identity_key = identity_key` and `run_id = payload_json.source_condition_run_id`.
   - `board`: join `board_condition_display_basis` on `board_identity_key = identity_key` and `run_id = payload_json.source_condition_run_id`.
   - If a display row is missing, the dry-run records a missing warning and does not query N1/N3/N4/N5 naked facts as a fallback.

4. Build planned rows in memory only.
   - One `user_projection_run` plan for the admin run.
   - One `user_signal_projection` plan per accepted N5 event.
   - One `user_signal_card` plan per projection.
   - One `user_notification_queue` plan per projection with `queue_status='queued_only'`.
   - Zero `user_signal_decision` rows.
   - Zero sim rows.

5. Write only dry-run artifacts.
   - Future runner may write `docs/N6_PROJECTION_DRY_RUN_REPORT.md` and `docs/N6_projection_dry_run_report.json`.
   - It must not write N6 business tables during dry-run.

## Planned Row Count Policy

Current MVP dry-run plan:

| Planned object | Count | Policy |
|---|---:|---|
| `user_projection_run` | 1 | One admin dry-run plan over the current N5 outbox range. |
| `user_signal_projection` | 488 | One row per accepted N5 `ActionEvent / HintEvent`. |
| `user_signal_card` | 488 | One card per signal projection. |
| `user_notification_queue` | 488 | One queued-only notification candidate per signal card. |
| `user_signal_decision` | 0 | Decisions are user intent and are not generated by projection dry-run. |
| `user_sim_account/order/trade/position` | 0 | Sim remains shadow schema only. |
| `user_session` | 0 | Projection dry-run does not log in or create sessions. |
| N5 outbox status updates | 0 | Dry-run does not consume or lock N5 events. |

If future preflight observes a different N5 pending count, the runner must report the observed count and mark the fixed current-real baseline as changed. Execute remains blocked until a new final gate accepts the new input range.

## Field Mapping

### user_signal_projection

| Target field | Source |
|---|---|
| `user_projection_run_id` | planned dry-run run id candidate |
| `user_id` | admin `user_id=1` |
| `user_filter_profile_id` | admin default profile |
| `user_watchlist_id` | null in MVP |
| `permission_scope` | `self` |
| `source_layer` | `N5_action` |
| `source_event_id` | N5 outbox `event_id` |
| `source_outbox_id` | N5 outbox `outbox_id` |
| `source_event_type` | N5 outbox `event_type` |
| `source_event_schema_version` | N5 outbox `event_schema_version` |
| `source_event_dedup_key` | N5 outbox `dedup_key` |
| `source_action_event_id` | N5 outbox `event_id` for MVP; payload `action_key` is preserved in JSON |
| `source_action_run_id` | N5 outbox `source_run_id` |
| `asset_kind`, `identity_key` | N5 outbox envelope |
| `code`, `name` | N2 display basis |
| `direction`, `signal_type` | N5 payload |
| `target_price` | buy: `buy_target_price`; sell: `sell_target_price` |
| `current_price` | null unless future N5 event contract carries it |
| `expected_return_pct` | buy: `target_price_summary_json.buy_expected_return_pct`; sell: `target_price_summary_json.sell_expected_return_pct` |
| `board_identity_key`, `board_code`, `board_name` | stock preferred board fields or board display fields |
| `source_display_table` | matched physical display-basis table name |
| `source_condition_display_basis_id` | matched display-basis primary key |
| `source_condition_display_run_id` | display-basis `run_id` |
| `projection_status` | `visible` when required fields are present; otherwise `blocked` in future execute planning |
| `source_payload_json` | compact N5 envelope and payload trace |
| `display_payload_json` | display-basis summaries and missing warnings |

### user_signal_card

| Target field | Source |
|---|---|
| `card_type` | `hint` for `HintEvent`; `buy_candidate` or `sell_candidate` for `ActionEvent` by direction |
| `card_status` | `active` for visible projections; `blocked` if required display fields are missing |
| `display_priority` | `10` for `ActionEvent`, `20` for `HintEvent`, plus direction/signal tie-breakers |
| `title` | `{name} {signal_type}` or `{code} {signal_type}` |
| `summary` | direction, signal type, target/expected-return summary, board context if present |
| asset fields | copied from `user_signal_projection` |
| `card_payload_json` | event time, lane, action_type, condition_key, trigger_period, display summaries, missing warnings |

### user_notification_queue

| Target field | Source |
|---|---|
| `notification_source` | `n5_action_event` for `ActionEvent`; `n5_hint_event` for `HintEvent` |
| `queue_status` | always `queued_only` in MVP dry-run / first execute design |
| `channel` | `broadcast_queue` |
| `title`, `message` | derived from card title/summary |
| `priority` | copied from card priority |
| `source_event_id`, `source_action_run_id` | N5 outbox envelope |
| `asset_kind`, `identity_key` | N5 outbox envelope |
| `notification_payload_json` | queue-only proof, no provider payload, no push attempt state |

## Missing Field Policy

Missing fields must be visible in the dry-run report and future `display_payload_json`, not hidden by cross-layer backfill.

P0 blockers:

- missing admin active account or default admin profile;
- missing N6 schema tables;
- N5 pending `ActionEvent / HintEvent` count no longer matches the accepted current-real baseline and no new final gate exists;
- missing required N5 envelope fields;
- event type outside `ActionEvent / HintEvent`;
- source layer other than `N5_action`;
- display enrichment missing `code` or `name` for rows that would be written.

P1 warnings:

- missing display-basis row when the dry-run can still account for the event;
- missing target price;
- missing expected return percentage;
- missing board context;
- missing current price because the MVP input contract does not include a N3 display event or current-price field.

For the current evidence:

- `display_missing=0`
- `code_name_missing=0`
- `target_price_missing=192`
- `expected_return_pct_missing=192`
- `current_price_missing=488`

No missing field may be filled by querying N1 historical K, N3 market facts, N4 trigger facts, N5 action facts, or old synthetic outbox.

## Rollback Strategy

Dry-run has no database rollback because it writes no N6 business rows.

Future projection execute rollback must use `user_projection_run_id` and delete only rows created by that projection run:

1. `user_notification_queue`
2. `user_signal_card`
3. `user_signal_projection`
4. `user_projection_run`

Rollback must not touch:

- `user_account`
- `user_filter_profile`
- `user_session`
- `user_watchlist`
- `user_signal_decision` unless a separate decision rollback contract exists
- `user_sim_*`
- N5 outbox / action facts
- N1-N5 upstream facts or events

Rollback draft: `sql/N6_projection_dry_run_rollback.sql`.

## Decision

DESIGN_PASS.

Allowed next gate:

```text
N6 projection dry-run runner implementation
```

Still blocked:

- N6 projection execute
- N5 outbox consumption or status update
- session creation
- projection/card/notification DB writes
- decision writes
- sim writes
- worker
- actual push
- real trade
