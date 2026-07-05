# Daily Pipeline Catch-up 20260603 / 20260604 Readiness

Result: `BLOCKED`

Layer role: `runtime_control`  
Generated at: `2026-06-04T17:33:49+0800`

## Scope

This gate reviewed readiness for catching up two closed source trade dates:

| source_trade_date | expected for_trade_date | status |
|---|---|---|
| `20260603` | `20260604` | blocked before execute |
| `20260604` | `20260605` | blocked before execute |

The already closed 20260603 read-only runtime lineage is not the same scope:
that lineage is `source_trade_date=20260602 -> for_trade_date=20260603`.
This catch-up must create new lineage for `20260603 -> 20260604` and
`20260604 -> 20260605`.

## Runtime Control Boundary

`runtime_control` performed only readiness, read-only DB checks, dry-run source
readiness probes, and artifact review. It did not execute N1/N2/N3/A1, did not
write business rows, did not consume outbox, and did not start workers.

Project boundary still requires actual writes to be done in the corresponding
layer role:

| Step | Required layer_role |
|---|---|
| calendar / N1 official daily / condition source | `N1_ingestion` |
| N2 condition layer | `N2_condition` |
| N3 subscription / A1 previous-day minute preload | `N3_market_data` |

## Calendar Readiness

Fresh DB proof:

| trade_date | DB rows | is_open | prev | next | status |
|---|---:|---|---|---|---|
| `20260602` | 1 | true | `20260601` | `20260603` | ready |
| `20260603` | 1 | true | `20260602` | `20260604` | ready |
| `20260604` | 1 | true | `20260603` | `20260605` | post-review passed by user-provided DB proof |
| `20260605` | 0 | null | null | null | missing; final gate ready |

No-write preflight:

| target | preflight | P0/P1/P2 | finding |
|---|---|---|---|
| `20260604` calendar patch | `PREFLIGHT_PASS` | `0/0/0` | Tushare confirms open day, prev/next=`20260603/20260605` |
| `20260605` calendar patch | `PREFLIGHT_PASS` | `0/0/0` | Tushare confirms open day, prev/next=`20260604/20260608` |

Final gate materialized in this runtime_control turn:

| target | final gate | rollback | status |
|---|---|---|---|
| `20260604` calendar patch | `docs/N1_TRADE_CALENDAR_20260604_PATCH_FINAL_GATE.md` / `docs/N1_trade_calendar_20260604_patch_final_gate.json` | `sql/N1_trade_calendar_20260604_patch_rollback.sql` | `PASS`, user confirmation point ready in `N1_ingestion` |
| `20260605` calendar patch | `docs/N1_TRADE_CALENDAR_20260605_PATCH_FINAL_GATE.md` / `docs/N1_trade_calendar_20260605_patch_final_gate.json` | `sql/N1_trade_calendar_20260605_patch_rollback.sql` | `PASS`, user confirmation point ready in `N1_ingestion` |

20260604 rollback proof:

```text
hard_fail_before_first_DELETE=true
guard_outbox_inbox_checkpoint=true
guard_N1_daily_fact_refs=true
guard_N2_N3_N4_N5_N6_refs=true
delete_scope=trade_calendar_20260604_patch_v1 control rows only
```

20260605 rollback proof:

```text
hard_fail_before_first_DELETE=true
guard_outbox_inbox_checkpoint=true
guard_N1_daily_fact_refs=true
guard_N2_N3_N4_N5_N6_refs=true
delete_scope=trade_calendar_20260605_patch_v1 control rows only
```

Post-review registration:

| target | post-review | DB proof | status |
|---|---|---|---|
| `20260604` calendar patch | `docs/N1_TRADE_CALENDAR_20260604_PATCH_POST_REVIEW.md` / `docs/N1_trade_calendar_20260604_patch_post_review.json` | calendar/active/batch=`1/1/1`, quality=`11`, P0/P1/P2=`0/0/0` | `POST_REVIEW_PASS` |

Required order:

1. Execute the already passed `20260605` calendar patch user confirmation point in `N1_ingestion`.
2. Post-review `common_trade_calendar(20260605)`.
3. Only then enter N1 official daily catch-up for source dates `20260603` and `20260604`.

## Current DB Baseline

For both `20260603` and `20260604`, current source fact rows are zero:

| table | 20260603 rows | 20260604 rows |
|---|---:|---:|
| `stock_daily_bar_fact` | 0 | 0 |
| `index_daily_bar_fact` | 0 | 0 |
| `board_daily_bar_fact` | 0 | 0 |
| `stock_daily_basic` | 0 | 0 |
| `stock_financial_metrics_fact(source_trade_date)` | 0 | 0 |
| `index_membership_fact` | 0 | 0 |
| `board_membership_fact` | 0 | 0 |

No N2/N3 runs exist yet for the catch-up target pairs:

| lineage | condition_run rows | market_data_run rows |
|---|---:|---:|
| `20260603 -> 20260604` | 0 | 0 |
| `20260604 -> 20260605` | 0 | 0 |

## Source Readiness

No token value was printed.

| Source dependency | Readiness |
|---|---|
| Tushare token autoload | present, length=56 |
| `tushare` import | ready |
| `mootdx` import | ready |
| `psycopg` import | ready |
| TDX root | `/Volumes/MacRaid/tdxdata/tdx` exists |
| TDX required txt files | `指数板块.txt`, `行业板块.txt`, `概念板块.txt`, `地区板块.txt` present |

Dry-run daily incremental summaries for `20260603` and `20260604` both pass as
plans, each with 11 tasks across common/stock/index/board and no side effects.

## Proposed Run IDs

These are proposed names for the next layer gates; final execute contracts must
confirm or regenerate them.

### 20260603 source catch-up

| Layer | Proposed run_id / source_version |
|---|---|
| N1 official daily | `official_daily_ingest_20260603_v1`; facts `stock_daily_20260603_v1`, `index_daily_20260603_v1`, `board_daily_20260603_v1` |
| N1 condition source | `condition_source_activation_20260603_v1`; facts `stock_daily_basic_20260603_v1`, `stock_financial_20260603_v1`, `index_membership_20260603_v1`, `board_membership_20260603_v1` |
| N2 condition | `condition_layer_20260603_source_20260603_v1` |
| N3 subscription | `market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` |
| A1 previous-day minute preload | `previous_day_minute_preload_20260603_for_20260604__market_data_subscription_20260604_condition_layer_20260603_source_20260603_v1` |

### 20260604 source catch-up

| Layer | Proposed run_id / source_version |
|---|---|
| N1 official daily | `official_daily_ingest_20260604_v1`; facts `stock_daily_20260604_v1`, `index_daily_20260604_v1`, `board_daily_20260604_v1` |
| N1 condition source | `condition_source_activation_20260604_v1`; facts `stock_daily_basic_20260604_v1`, `stock_financial_20260604_v1`, `index_membership_20260604_v1`, `board_membership_20260604_v1` |
| N2 condition | `condition_layer_20260604_source_20260604_v1` |
| N3 subscription | `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` |
| A1 previous-day minute preload | `previous_day_minute_preload_20260604_for_20260605__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` |

## Required Gate Order

1. `N1_ingestion`: calendar patch `20260605` execute, post-review.
2. `N1_ingestion`: official daily + condition source for `20260603`, with dry-run/preflight/final gate/execute/post-review.
3. `N2_condition`: condition execute for `20260603 -> 20260604`, with dry-run/contract/preflight/final gate/execute/post-review.
4. `N3_market_data`: subscription and A1 preload for `20260604`, with dry-run/preflight/final gate/execute/post-review.
5. `N1_ingestion`: official daily + condition source for `20260604`, with dry-run/preflight/final gate/execute/post-review.
6. `N2_condition`: condition execute for `20260604 -> 20260605`, with dry-run/contract/preflight/final gate/execute/post-review.
7. `N3_market_data`: subscription and A1 preload for `20260605`, with dry-run/preflight/final gate/execute/post-review.

Every write step must have rollback SQL with a hard-fail guard before the first
`DELETE`.

## Decision

`BLOCKED`

Blocking reasons:

1. `common_trade_calendar(20260605)` is missing, though its final gate is now ready for `N1_ingestion` execute confirmation.
2. The current session is `runtime_control`, which may not execute N1/N2/N3/A1
   business writes under the project layer boundary.

## Next Prompt

```text
layer_role=N1_ingestion。

进入 N1 20260605 trade calendar patch execute gate。

目标：
1. 执行已通过 final gate 的 common_trade_calendar(20260605) patch。
2. post-review passed 后暂停。
3. 不执行 official daily，不进入 N2/N3/N4/N5/N6。

必须使用 Tushare trade_cal；禁止静默 fallback；不得打印 TUSHARE_TOKEN 明文。

20260605 expected:
- trade_date=20260605
- is_open=true
- prev_trade_date=20260604
- next_trade_date=20260608
- source_batch_id/source_version=trade_calendar_20260605_patch_v1

20260605 已有 final gate artifact；execute 后做 post-review。
rollback SQL 必须首个 DELETE 前 hard-fail。
```
