# N6 Phase 3 038E PnL Migration Draft

Status: DRAFT_PASS

Layer role: N6_user

This draft defines the 038E virtual PnL snapshot schema split. It does not execute DDL, write business rows, consume or update outbox rows, start workers, modify N6_UI_v1/API/projection/shadow pipeline, or enter delivery/push/voice/mobile/sim/position/real trade.

## Scope

Create only:

- `n6_virtual_pnl_snapshot`

Do not create:

- leaderboard
- AI evaluation
- strategy ranking
- real brokerage performance table

## PnL Model

`n6_virtual_pnl_snapshot` is a virtual-account valuation snapshot. It stores one deterministic snapshot of virtual PnL and asset value for an account/principal/run.

Key fields:

- `virtual_account_id`
- `principal_id`
- `principal_type`
- `snapshot_time`
- `trade_date`
- `gross_pnl`
- `realized_pnl`
- `unrealized_pnl`
- `total_fee`
- `total_tax`
- `net_pnl`
- `total_asset_value`
- `cash_value`
- `position_market_value`
- `source_price_policy`
- `valuation_policy_version`
- `valuation_policy_hash`
- `source_cash_snapshot_id`
- `source_position_max_updated_at`
- `pnl_status`
- deterministic run/policy/rollback/lineage fields

Required checks:

- `virtual_account_id` references `n6_virtual_account`.
- `(principal_id, principal_type)` references `n6_principal`.
- `source_cash_snapshot_id` references `n6_virtual_cash_snapshot` and is nullable.
- `net_pnl = gross_pnl - total_fee - total_tax`.
- `total_asset_value = cash_value + position_market_value`.
- `total_fee >= 0`.
- `total_tax >= 0`.
- `cash_value >= 0`.
- `position_market_value >= 0`.
- `total_asset_value >= 0`.

## Valuation Source Boundary

`source_price_policy` must explicitly record the valuation source policy. Allowed values:

- `n6_display_snapshot`
- `reviewed_artifact`
- `virtual_mark_policy`

Forbidden sources:

- live price direct connection
- raw K recomputation
- N1 raw facts
- N3 raw facts
- broker account/funds/position

## Fee / Tax Boundary

038E only summarizes virtual trade / cash ledger fee and tax amounts that are already recorded by prior virtual tables. It does not encode fee rate, stamp duty, transfer fee, commission, settlement, or T+1 rules.

## Leaderboard Boundary

This gate does not create leaderboard, AI evaluation, strategy ranking, or real performance tables.

Future leaderboard may only read approved virtual PnL snapshots through a separate gate. PnL snapshots are not real returns, are not investment advice, and do not represent future returns.

## Rollback

Rollback SQL: `sql/038E_n6_virtual_pnl_schema_rollback.sql`

Rollback hard-fails before the first `DROP` if:

- `n6_virtual_pnl_snapshot` has rows.

Rollback drops only:

1. `n6_virtual_pnl_snapshot`

It does not use `CASCADE`, does not drop 038A/038B/038C/038D/036/037 objects, and does not touch N1-N6 facts or outbox.

## Final Gate Baseline Requirements

- `n6_virtual_pnl_snapshot` does not exist.
- `n6_virtual_account` exists and row_count=0.
- `n6_virtual_cash_ledger` exists and row_count=0.
- `n6_virtual_cash_snapshot` exists and row_count=0.
- `n6_virtual_order` exists and row_count=0.
- `n6_virtual_trade` exists and row_count=0.
- `n6_virtual_position` exists and row_count=0.
- `n6_virtual_position_event` exists and row_count=0.

## Remaining Gaps

- No DDL executed in this gate.
- No live DB proof in this gate.
- No PnL rows.
- No PnL runner.
- No approved leaderboard gate.
- No valuation policy runner.
