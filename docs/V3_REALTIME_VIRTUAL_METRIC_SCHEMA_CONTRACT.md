# V3 Realtime Virtual Metric Schema Contract

Result: `CONTRACT_PASS`

This contract is draft-only. It does not execute a migration, write a database row, start a worker, update outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/position/PnL/real trade.

## Decision

Use the existing N3-owned physical table family as the base:

- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`

The next additive schema draft is [039_v3_realtime_virtual_metric_schema_draft.sql](/Users/chuanfuchen/Documents/A股监控系统v3/sql/039_v3_realtime_virtual_metric_schema_draft.sql). This keeps the current N4/N5 integration points intact and adds the realtime virtual metric fields required by the executable plan.

不改 N4/N5 当前业务规则. N4 可以消费 N3 标准化、可追溯 realtime virtual metric to generate realtime `TriggerMatched`, but N4 still must not read raw unclosed minute rows or recompute 1m/5m/30m/120m indicators. N5 不拉行情、不拼 raw 分钟, and still enters only from `TriggerMatched`.

## N3 Ownership

N3 is the unique owner of action-confirmation market metrics. N3 must produce standardized, traceable realtime metrics for:

`1m / 5m / 30m / 120m / D / W / M / Q / Y`

N4 and N5 consume these facts/events. They do not call market adapters, pull minute bars, or rebuild period indicators.

## Session Policies

- Auction: 09:20-09:30 may use a mootdx `09:31` label as `auction realtime virtual 1m`.
- Midday: do not forge an `11:30` bar. `13:00` is equivalent to the missing `11:30` for the `13:01` previous-1m comparison.
- `MinuteBarClosed` is not a fast-lane blocker. It remains a strict/replay/correction input.
- After close replay is audit evidence. It must not erase the fact that a realtime tick or virtual metric was true at trigger time.

## Added Field Groups

Core trace and session:

- `realtime_metric_schema_version`
- `metric_time_label`
- `snapshot_id`
- `event_id`
- `quality_status`
- `source_time`
- `observed_at`
- `session_kind`
- `period_source`
- `is_closed_1m`
- `is_auction_virtual`
- `midday_bridge_policy`
- `trace_json`
- `deterministic_pass_flags`

Realtime period entities:

- current and previous entity high/low for `1m / 5m / 30m / 120m / D / W / M / Q / Y`

Amounts:

- existing `current_1m_amount / previous_1m_amount`
- existing `current_5m_virtual_amount / previous_5m_full_amount`
- new `current_30m_virtual_amount / previous_day_same_window_amount / previous_30m_full_amount`
- new `current_120m_virtual_amount / previous_120m_full_amount`
- new DB columns `current_d/current_w/current_m/current_q/current_y_virtual_amount` and `previous_d/previous_w/previous_m/previous_q/previous_y_amount`

## Field Name Canonicalization

PostgreSQL DB columns use lowercase identifiers. Uppercase period names (`D/W/M/Q/Y`) are display and payload aliases only. The contract freezes `field_registry.display_alias_to_db_column`; examples:

- `current_D_body_high` -> `current_d_body_high`
- `current_Y_virtual_amount` -> `current_y_virtual_amount`
- `previous_Y_amount` -> `previous_y_amount`

Writers must canonicalize payload aliases before insert. N4/N5 may display uppercase periods, but DB writes and SQL must use lowercase column names.

## N4 Contract

N4 canonical events remain:

- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`

N4 may use N3 standardized realtime virtual metrics before 1m close. N4 must not directly use raw unclosed K rows.

## N5 Contract

N5 canonical events remain:

- `ActionEligible`
- `ActionBlocked`
- `ActionExecuted`
- `ActionSkipped`

`ActionEligible` is realtime after `TriggerMatched`.

`ActionExecuted` uses the trigger-time saved virtual `120m/30m/5m` evidence plus the closed trigger-minute `1m` fact. ActionExecuted 不代表下单、sim、语音、N6 展示或真实交易.

## Rollback

Rollback draft: [039_v3_realtime_virtual_metric_schema_rollback_draft.sql](/Users/chuanfuchen/Documents/A股监控系统v3/sql/039_v3_realtime_virtual_metric_schema_rollback_draft.sql)

It hard-fails before any column removal and must pass a separate final gate before use.
