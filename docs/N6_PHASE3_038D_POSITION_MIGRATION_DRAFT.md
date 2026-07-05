# N6 Phase 3 038D Position Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

This draft defines the 038D virtual position schema split. It does not execute DDL, write business rows, consume or update outbox rows, start workers, modify N6_UI_v1/API/projection/shadow pipeline, or enter delivery/push/voice/mobile/sim/real position/real trade.

## Scope

Create only:

- `n6_virtual_position`
- `n6_virtual_position_event`

Do not create:

- `n6_virtual_pnl_snapshot`

## Position Model

`n6_virtual_position` is the current virtual position state table. It is owned by `n6_virtual_account` and by the `(principal_id, principal_type)` composite owner root. It stores current quantity, available quantity, locked quantity, cost, optional valuation fields, and deterministic run/policy/rollback/lineage metadata.

Key constraints:

- `virtual_account_id` references `n6_virtual_account`.
- `(principal_id, principal_type)` references `n6_principal`.
- `principal_type` allows only `admin`, `human_user`, `ai_user`.
- `last_virtual_trade_id` references `n6_virtual_trade` and is nullable.
- `quantity`, `available_quantity`, and `locked_quantity` are non-negative.
- `quantity = available_quantity + locked_quantity`.
- `average_cost >= 0`.
- `market_value` is nullable and non-negative when present.
- `source_lineage_json` must be a JSON object.
- No broker, real position, or real trade field exists.

## Position Event Model

`n6_virtual_position_event` is the immutable adjustment/event lineage table. It stores fill-derived changes, adjustments, split adjustments, close events, rollback adjustments, source virtual order/trade references, event time, and deterministic run/policy/rollback/lineage metadata.

Event type values:

- `virtual_buy_fill`
- `virtual_sell_fill`
- `adjustment`
- `split_adjustment`
- `close_position`
- `rollback_adjustment`

Key constraints:

- `virtual_position_id` is nullable and references `n6_virtual_position`.
- `virtual_account_id` references `n6_virtual_account`.
- `(principal_id, principal_type)` references `n6_principal`.
- `source_virtual_order_id` references `n6_virtual_order` and is nullable.
- `source_virtual_trade_id` references `n6_virtual_trade` and is nullable.
- `quantity_delta` and `cost_delta` may be positive or negative.
- The event table has no `updated_at` field and is append-only by contract.

## T+1 Boundary

038D only reserves `available_quantity` and `locked_quantity`. It does not encode T+1, settlement, fee, tax, or transfer rules. Those rules require a later execution policy gate.

## Rollback

Rollback SQL: `sql/038D_n6_virtual_position_schema_rollback.sql`

Rollback hard-fails before the first `DROP` if:

- `n6_virtual_position_event` has rows.
- `n6_virtual_position` has rows.
- Future `n6_virtual_pnl_snapshot` exists and has rows.

Rollback drops only:

1. `n6_virtual_position_event`
2. `n6_virtual_position`

It does not use `CASCADE`, does not drop 038A/038B/038C/036/037 objects, and does not touch N1-N6 facts or outbox.

## Final Gate Baseline Requirements

- `n6_virtual_position` does not exist.
- `n6_virtual_position_event` does not exist.
- `n6_virtual_account` exists and row_count=0.
- `n6_virtual_cash_ledger` exists and row_count=0.
- `n6_virtual_cash_snapshot` exists and row_count=0.
- `n6_virtual_order` exists and row_count=0.
- `n6_virtual_trade` exists and row_count=0.
- Future `n6_virtual_pnl_snapshot` does not exist or row_count=0.

## Remaining Gaps

- No DDL executed in this gate.
- No live DB proof in this gate.
- No position rows.
- No position event rows.
- No PnL table.
- No T+1 execution policy.
- No position runner.
