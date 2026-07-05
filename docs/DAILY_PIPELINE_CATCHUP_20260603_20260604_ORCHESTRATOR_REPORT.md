# Daily Pipeline Catch-up 20260603 / 20260604 Orchestrator Report

Result: `CATCHUP_PASS`

Generated at: `2026-06-04T21:08:00+08:00`

## Scope

This catch-up completed N1 -> N2 -> N3 subscription -> N3-A1 previous-day
minute preload for two closed source trade dates:

| source_trade_date | for_trade_date | status |
|---|---|---|
| `20260603` | `20260604` | passed through A1 |
| `20260604` | `20260605` | passed through A1 |

This run did not enter N4/N5/N6, did not consume outbox, and did not start any
worker or delivery path.

## N1 Official Daily / Condition Source

| source_trade_date | stock_daily | index_daily | board_daily | stock_daily_basic | stock_financial | index_membership | board_membership | batch_count | quality P0/P1/P2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `20260603` | 5511 | 9 | 428 | 5511 | 5511 | 12841 | 56960 | 10 | `0/0/0` |
| `20260604` | 5511 | 9 | 428 | 5511 | 5511 | 12841 | 56960 | 10 | `0/0/0` |

Calendar patches:

- `20260604`: `POST_REVIEW_PASS`, `trade_calendar_20260604_patch_v1`.
- `20260605`: `POST_REVIEW_PASS`, `trade_calendar_20260605_patch_v1`.

## N2 Condition Layer

| source_trade_date | for_trade_date | run_id | status | P0/P1/P2 | quality | basis stock/index/board | pool stock/index/board | scope stock/index/board | display stock/index/board |
|---|---|---|---|---|---:|---|---|---|---|
| `20260603` | `20260604` | `condition_layer_20260603_source_20260603_v1` | `passed_active` | `0/6/3` | 106 | `5511/9/428` | `4222/20/892` | `4201/20/892` | `1960/9/428` |
| `20260604` | `20260605` | `condition_layer_20260604_source_20260604_v1` | `passed_active` | `0/6/3` | 106 | `5511/9/428` | `4207/20/912` | `4186/20/912` | `1952/9/428` |

N2 rollback SQL:

- `sql/N2_condition_layer_20260603_rollback.sql`
- `sql/N2_condition_layer_20260604_rollback.sql`

Both rollback files hard-fail before the first `DELETE` and guard downstream
market-data, trigger, action, condition enrichment, position, outbox and inbox
refs.

## N3 Subscription

| for_trade_date | run_id | status | P0/P1/P2 | source_scope | candidate | subscription | objects | pull_plan |
|---|---|---|---|---:|---:|---:|---:|---:|
| `20260604` | `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` | `passed` | `0/0/0` | 5113 | 5757 | 3041 | 2397 | 9 |
| `20260605` | `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` | `passed` | `0/0/0` | 5118 | 5802 | 3073 | 2389 | 9 |

Both subscription runs wrote only N3 control rows. `market_data_pulled=false`,
`market_data_fact_written=false`, `event_outbox_rows=0`, `worker_started=false`.

## N3-A1 Previous-Day Minute Preload

| for_trade_date | preload_run_id | status | P0/P1/P2 | stock minute/status | index minute/status | board minute/status | total minute/status |
|---|---|---|---|---|---|---|---|
| `20260604` | `previous_day_minute_preload_20260603_for_20260604__market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` | `passed` | `0/0/0` | `68160/284` | `480/2` | `8640/36` | `77280/322` |
| `20260605` | `previous_day_minute_preload_20260604_for_20260605__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` | `passed` | `0/0/0` | `68160/284` | `480/2` | `13440/56` | `82080/342` |

A1 wrote previous-day minute facts and preload status rows only. It did not
write common_event_outbox and did not enter N4/N5/N6.

## Boundary Proof

```text
scoped outbox refs=0
scoped inbox refs=0
N4 refs=0
N5 refs=0
N6 refs=0
worker_started=false
delivery/notification/push/voice/mobile/sim/position/real_trade=false
```

## Rollback Summary

Rollback must proceed downstream first:

1. A1 previous-day minute preload rollback.
2. N3 subscription rollback.
3. N2 condition rollback.
4. N1 daily/source rollback.
5. Calendar patch rollback only after downstream refs are cleared.

Rollback SQL files generated or verified:

- `sql/N1_daily_catchup_20260603_rollback.sql`
- `sql/N1_daily_catchup_20260604_rollback.sql`
- `sql/N2_condition_layer_20260603_rollback.sql`
- `sql/N2_condition_layer_20260604_rollback.sql`
- `sql/N3_subscription_20260604_rollback.sql`
- `sql/N3_subscription_20260605_rollback.sql`
- `sql/N3_A1_previous_day_minute_20260604_rollback.sql`
- `sql/N3_A1_previous_day_minute_20260605_rollback.sql`

All checked rollback SQL has a hard-fail guard before the first `DELETE`.

## Remaining Scope

Allowed next gates are separate N3 B1/C1 readiness or N4/N5 planning gates for
the new lineages. This report does not authorize N4/N5/N6 execute, outbox
consumption, workers, delivery, notification, push, voice, mobile, sim,
position, or real trade.
