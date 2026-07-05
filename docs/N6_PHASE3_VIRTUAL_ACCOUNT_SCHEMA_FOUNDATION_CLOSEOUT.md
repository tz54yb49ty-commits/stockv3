# N6 Phase 3 Virtual Account Schema Foundation Closeout

Status: CLOSEOUT_PASS

Layer role: runtime_control

Date: 2026-06-05

This closeout registers the Phase 3 virtual account schema foundation after
split migrations 038A through 038E. This gate did not execute DDL, write
business rows, consume or update outbox rows, start workers, modify N6_UI_v1,
modify existing APIs, modify projection or shadow pipelines, deliver
notifications, push to voice or mobile, run sim, create positions, or place
real trades.

## 1. Completed Splits

| Split | Scope | Status | Rollback |
|---|---|---|---|
| 038A | `n6_virtual_account` | complete | `sql/038A_n6_virtual_account_schema_rollback.sql` |
| 038B | `n6_virtual_cash_ledger`, `n6_virtual_cash_snapshot` | complete | `sql/038B_n6_virtual_cash_schema_rollback.sql` |
| 038C | `n6_virtual_order`, `n6_virtual_trade` | complete | `sql/038C_n6_virtual_order_trade_schema_rollback.sql` |
| 038D | `n6_virtual_position`, `n6_virtual_position_event` | complete | `sql/038D_n6_virtual_position_schema_rollback.sql` |
| 038E | `n6_virtual_pnl_snapshot` | complete | `sql/038E_n6_virtual_pnl_schema_rollback.sql` |

## 2. Table Proof

Target database proof:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
```

All Phase 3 tables exist:

```text
n6_virtual_account=true
n6_virtual_cash_ledger=true
n6_virtual_cash_snapshot=true
n6_virtual_order=true
n6_virtual_trade=true
n6_virtual_position=true
n6_virtual_position_event=true
n6_virtual_pnl_snapshot=true
```

## 3. Row Count Proof

All Phase 3 tables are schema-only and currently contain no business rows:

```text
n6_virtual_account=0
n6_virtual_cash_ledger=0
n6_virtual_cash_snapshot=0
n6_virtual_order=0
n6_virtual_trade=0
n6_virtual_position=0
n6_virtual_position_event=0
n6_virtual_pnl_snapshot=0
```

## 4. FK / CHECK Proof

Key FK and CHECK families are present:

```text
virtual_account -> n6_principal(principal_id, principal_type)
cash_ledger -> n6_virtual_account
cash_snapshot -> n6_virtual_account
cash_snapshot.source_ledger_max_id -> n6_virtual_cash_ledger
order -> n6_virtual_account
order -> n6_principal(principal_id, principal_type)
trade -> n6_virtual_order
trade -> n6_virtual_account
trade -> n6_principal(principal_id, principal_type)
position -> n6_virtual_account
position -> n6_virtual_trade(last_virtual_trade_id)
position -> n6_principal(principal_id, principal_type)
position_event -> n6_virtual_position
position_event -> n6_virtual_account
position_event -> n6_virtual_order
position_event -> n6_virtual_trade
position_event -> n6_principal(principal_id, principal_type)
pnl_snapshot -> n6_virtual_account
pnl_snapshot -> n6_virtual_cash_snapshot
pnl_snapshot -> n6_principal(principal_id, principal_type)
```

Key CHECK families are present:

```text
cash_snapshot: total_cash = available_cash + frozen_cash
trade: total_fee_amount = commission_amount + stamp_tax_amount + transfer_fee_amount
position: quantity = available_quantity + locked_quantity
pnl_snapshot: net_pnl = gross_pnl - total_fee - total_tax
pnl_snapshot: total_asset_value = cash_value + position_market_value
pnl_snapshot: source_price_policy in n6_display_snapshot / reviewed_artifact / virtual_mark_policy
```

## 5. Forbidden Scope Proof

Forbidden side effects remain absent:

```text
common_event_outbox refs for Phase 3 virtual schema=0
common_event_inbox refs for Phase 3 virtual schema=0
common_event_consumer_checkpoint refs for Phase 3 virtual schema=0
worker_started=false
N6_UI_v1/API/projection/shadow mutation=false
delivery/push/voice/mobile/sim/position/real_trade=false
```

Forbidden future tables are not present:

```text
n6_leaderboard=false
n6_ai_evaluation=false
n6_strategy_ranking=false
n6_real_performance=false
n6_virtual_leaderboard=false
```

## 6. Rollback Summary

All split rollback files remain usable as schema rollbacks while their target
tables have zero rows. Each rollback hard-fails before the first `DROP TABLE`
and uses no `CASCADE`.

```text
038A rollback: raise_before_drop=true, drop_count=1, cascade_count=0
038B rollback: raise_before_drop=true, drop_count=2, cascade_count=0
038C rollback: raise_before_drop=true, drop_count=2, cascade_count=0
038D rollback: raise_before_drop=true, drop_count=2, cascade_count=0
038E rollback: raise_before_drop=true, drop_count=1, cascade_count=0
```

Rollback dependency remains downstream-first after future business rows exist.
This closeout does not authorize rollback execution.

## 7. Boundary

Phase 3 schema foundation is complete, but business behavior is not yet
implemented. The following remain out of scope until separate gates:

```text
virtual account seed rows
virtual account operation runner
cash ledger/snapshot runner
virtual order/trade runner
position/event runner
PnL valuation runner
valuation policy
leaderboard
AI evaluation
strategy ranking
N6 UI adapter
delivery / push / voice / mobile
sim / position execution
real trade
```

## 8. Next Recommended Gate

Recommended next gate:

```text
N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OR_OPERATION_DESIGN_GATE
```

Alternative allowed gates:

```text
N6_PHASE3_VIRTUAL_ACCOUNT_ROLLBACK_REVIEW_GATE
N6_PHASE3_VALUATION_POLICY_DRAFT_GATE
N6_PHASE3_VIRTUAL_ACCOUNT_API_ADAPTER_DRAFT_GATE
runtime_control read-only schema foundation review
```
