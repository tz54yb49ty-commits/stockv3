# N3 Subscription 20260527 Dry-Run Report

layer_role: `N3_market_data`

## Result

`PASS`

The subscription candidate/dedup/pull-plan calculation completed and the refreshed 20260527 calendar gate now passes. `common_trade_calendar` has a `20260527` row with `is_open=true` and `prev_trade_date=20260526`.

## Lineage

| item | value |
|---|---|
| source_condition_run_id | `condition_layer_20260526_source_20260526_v1` |
| source_trade_date | `20260526` |
| for_trade_date | `20260527` |
| prev_trade_date | `20260526` |
| planned execute run_id | `market_data_subscription_20260527_condition_layer_20260526_source_20260526_v1` |

## Scope Input

| asset_kind | scope rows | objects |
|---|---:|---:|
| stock | 4291 | 2045 |
| index | 19 | 9 |
| board | 264 | 127 |
| total | 4574 | 2181 |

## Dry-Run Output

| metric | value |
|---|---:|
| candidate rows | 13722 |
| dedup subscription rows | 6543 |
| subscription objects | 2181 |
| pull_plan rows | 9 |
| dedup ratio | 0.476826 |

## Required Data Kind

| required_data_kind | subscription rows | data_trade_date |
|---|---:|---|
| `realtime_daily_snapshot` | 2181 | `20260527` |
| `minute_bar_1m` | 2181 | `20260527` |
| `previous_day_minute_bar_1m` | 2181 | `20260526` |

## Pull Plan

| asset_kind | required_data_kind | object_count | adapter |
|---|---|---:|---|
| board | `minute_bar_1m` | 127 | `BoardMarketDataAdapter` |
| board | `previous_day_minute_bar_1m` | 127 | `BoardMarketDataAdapter` |
| board | `realtime_daily_snapshot` | 127 | `BoardMarketDataAdapter` |
| index | `minute_bar_1m` | 9 | `IndexMarketDataAdapter` |
| index | `previous_day_minute_bar_1m` | 9 | `IndexMarketDataAdapter` |
| index | `realtime_daily_snapshot` | 9 | `IndexMarketDataAdapter` |
| stock | `minute_bar_1m` | 2045 | `StockMarketDataAdapter` |
| stock | `previous_day_minute_bar_1m` | 2045 | `StockMarketDataAdapter` |
| stock | `realtime_daily_snapshot` | 2045 | `StockMarketDataAdapter` |

## Calendar Gate

| check | expected | actual | severity |
|---|---|---|---|
| `common_trade_calendar` row for `20260527` | exists | exists | passed |
| `is_open` | true | true | passed |
| `prev_trade_date` | `20260526` | `20260526` | passed |
| `next_trade_date` | `20260528` | `20260528` | passed |

The previous blocker is cleared by the 20260527 calendar patch.

## P0 / P1 / P2

| scope | P0 | P1 | P2 |
|---|---:|---:|---:|
| base dry-run planner | 0 | 0 | 0 |
| 20260527 strict execute gate | 0 | 0 | 0 |

## Boundary

- No market data was pulled.
- No N3 control rows were inserted.
- No realtime snapshot, minute bar, projection, closed summary, or EOD fact rows were written.
- No `common_event_outbox`, `common_event_inbox`, or checkpoint rows were written or consumed.
- No N4/N5/N6 layer was entered.
- No worker was started.
- Execute final gate is allowed after explicit user confirmation.

## Artifacts

- Dry-run JSON: `docs/N3_subscription_20260527_dry_run_report.json`
- Execute contract: `docs/N3_subscription_20260527_execute_contract.json`
- Execute preflight: `docs/N3_subscription_20260527_execute_preflight.json`
- Rollback draft: `sql/N3_subscription_20260527_rollback.sql`
