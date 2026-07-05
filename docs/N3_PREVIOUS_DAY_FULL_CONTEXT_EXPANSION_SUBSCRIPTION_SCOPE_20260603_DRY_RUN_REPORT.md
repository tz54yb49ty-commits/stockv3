# N3 Previous-Day Full-Context Expansion Subscription Scope Dry-Run

## Result

- result: `SCOPE_DRY_RUN_PASS`
- market_data_run_id: `market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- previous_day_minute_date: `20260602`
- P0/P1/P2: `0/1/0`

## Planned Additive Rows

- candidate rows: `4391`
- subscription rows: `2197`
- pull_plan rows: `3`
- expected rows: `{'stock': 413280, 'index': 19440, 'board': 94560}`

## Boundary

- no market pull
- no minute/snapshot/projection facts
- no outbox/inbox/checkpoint writes
- no N4/N5/N6
- no worker

## Rollback

- rollback_sql: `sql/N3_previous_day_full_context_expansion_subscription_scope_20260603_rollback.sql`
- hard-fail guard before first DELETE
