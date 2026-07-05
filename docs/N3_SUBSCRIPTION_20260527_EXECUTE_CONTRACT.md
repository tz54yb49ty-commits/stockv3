# N3 Subscription 20260527 Execute Contract

layer_role: `N3_market_data`

## Status

`PASS`

This contract is ready for the explicit execute final gate for `market_data_subscription_20260527_condition_layer_20260526_source_20260526_v1`. It remains a no-write contract until the user separately authorizes execute.

## Run IDs

| item | value |
|---|---|
| source_condition_run_id | `condition_layer_20260526_source_20260526_v1` |
| execute run_id | `market_data_subscription_20260527_condition_layer_20260526_source_20260526_v1` |
| source_trade_date | `20260526` |
| for_trade_date | `20260527` |
| prev_trade_date | `20260526` |

## Expected Writes If Unblocked

Only these tables may be written by a future explicit execute:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`

Expected row counts:

| table | rows |
|---|---:|
| `common_market_data_run` | 1 |
| `common_market_data_subscription_candidate` | 13722 |
| `common_market_data_subscription` | 6543 |
| `common_market_data_pull_plan` | 9 |
| `common_market_data_quality_item` | dry-run quality items plus execute post-check items |

## Forbidden Writes

- `stock/index/board_minute_bar_1m`
- `stock/index/board_realtime_daily_snapshot`
- `stock/index/board_realtime_projection_metric`
- `stock/index/board_closed_30m_summary`
- `stock/index/board_closed_30m_signal_enrichment`
- `stock/index/board_eod_snapshot`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- trigger/action/user/voice/mobile/sim/position tables

## Required Gates

| gate | required result | current result |
|---|---|---|
| N2 run status | `passed` | `passed` |
| scope rows | stock=4291 index=19 board=264 | matched |
| target run baseline | 0 | 0 |
| same N2 subscription baseline | 0 | 0 |
| calendar row `20260527` | exists | exists |
| calendar `is_open` | true | true |
| calendar `prev_trade_date` | `20260526` | `20260526` |

## Rollback

Rollback draft: `sql/N3_subscription_20260527_rollback.sql`

Rollback scope is limited to the execute run_id:

- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`
- `common_market_data_quality_item`
- `common_market_data_run`

Rollback must not touch N2, market facts, event outbox/inbox/checkpoint, or N4-N6.
