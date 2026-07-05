# N2 Condition Layer 20260528 Execute Post-Review

Status: **POST_REVIEW_PASS**

## Run

- run_id: `condition_layer_20260528_source_20260528_v1`
- source_trade_date: `20260528`
- for_trade_date: `20260529`
- common_condition_run.status: `passed_active`
- active passed_active count for date pair: `1`
- P0/P1/P2: `0/6/3`

## Row Counts

| table family | stock | index | board |
|---|---:|---:|---:|
| condition_basis | 5506 | 83 | 428 |
| condition_pool | 4271 | 18 | 263 |
| minute_target_scope | 4271 | 18 | 263 |
| monitor_target | 5506 | 83 | 428 |
| condition_display_basis | 5506 | 83 | 428 |

- common_condition_quality_item: `106`

## Canonical Signal Audit

All new pool/scope/display rows for this run have:

- deprecated signal rows: `0`
- noncanonical signal rows: `0`

Canonical signal whitelist remains:

```text
BUY
BUY:FULL
SELL
SELL:FULL
BUY_HINT
SELL_HINT
```

## Boundary Proof

- common_event_outbox delta: `0`
- common_event_inbox delta: `0`
- common_event_consumer_checkpoint delta: `0`
- downstream refs for this run: `{'common_market_data_run': 0, 'common_trigger_run': 0, 'common_action_run': 0}`
- market data pulled: `false`
- N3/N4/N5/N6 entered: `false`
- worker started: `false`
- old system touched: `false`

## Rollback

- rollback_safe: `true`
- rollback SQL: `sql/N2_condition_layer_20260528_rollback.sql`

Rollback is guarded and blocks if downstream refs appear before rollback.
