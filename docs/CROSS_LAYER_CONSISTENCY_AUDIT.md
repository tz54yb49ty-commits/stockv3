# Cross Layer Consistency Audit

Gate: `CROSS_LAYER_CONSISTENCY_AUDIT_GATE`
Layer role: `runtime_control`
Result: `BLOCKED`
Date: `2026-06-08`

This audit is read-only except for writing this report artifact. It did not change
business code, write database rows, execute migrations, consume or update outbox,
start workers, generate proposal/order/trade, update position/PnL, or submit real
trade.

## Scope

Scanned scope:

```text
src/ashare_v3/
scripts/
tests/
docs/
sql/
```

Runtime probes:

```text
GET http://127.0.0.1:8786/n6/login -> 200
GET http://127.0.0.1:8786/n6/app/filter-center -> 302 /n6/login?next=/n6/app/filter-center
GET http://127.0.0.1:8786/api/n6/app/v2/filter/stocks -> 401
```

Target DB read-only proof:

```text
db=ashare_v3
user=ashare_v3_user
host=127.0.0.1:5432
db_time=2026-06-08 21:04:36+08
```

## Summary

```text
P0 = 1
P1 = 1
P2 = 1
```

The audit is `BLOCKED` because B-track V2 filter-center reads the approved
readonly views but selects rows by `max(source_trade_date)` instead of an
approved/active `run_id`. The live DB now has two 20260605 N2 runs in the views,
so the current implementation can mix runs and duplicate identities.

## Findings

### CLCA-P0-001: B-track filter-center mixes multiple N2 runs

Severity: `P0`

Location:

```text
src/ashare_v3/web/n6_user_app.py:2489
src/ashare_v3/web/n6_user_app.py:2624
src/ashare_v3/web/n6_user_app.py:2626
docs/B_TRACK_V2_FILTER_CENTER_CLOSEOUT.md:51
docs/B_TRACK_V2_FILTER_CENTER_CLOSEOUT.md:55
docs/B_TRACK_V2_FILTER_CENTER_CLOSEOUT.md:56
docs/B_TRACK_V2_FILTER_CENTER_CLOSEOUT.md:57
```

Expected:

```text
B-track filter-center must preserve N2 display_basis source grain and read a
single approved source run. The repaired closeout row counts were
stock/index/board=1952/9/428 for condition_layer_20260604_source_20260604_v1.
```

Actual:

```text
fetch_app_filter_items reads v_n6_* views but only constrains:
source_trade_date = (SELECT max(source_trade_date) FROM view)

It does not constrain run_id/source_condition_run_id. Live DB max source_trade_date
is 20260605 and has two runs in each display view.
```

Evidence:

```text
Code:
src/ashare_v3/web/n6_user_app.py:2624 FROM {table_name}
src/ashare_v3/web/n6_user_app.py:2626 AND source_trade_date = (SELECT max(source_trade_date) FROM {table_name})

Live DB latest source-date rows:
stock latest source_date rows=3890 distinct_identity=1945 distinct_runs=2 duplicate_identity_rows=1945
index latest source_date rows=92 distinct_identity=83 distinct_runs=2 duplicate_identity_rows=9
board latest source_date rows=555 distinct_identity=428 distinct_runs=2 duplicate_identity_rows=127

Live DB by latest source-date run:
stock 20260605:
  condition_layer_20260605_to_20260608_20260608013900_execute rows=1945
  condition_layer_20260605_to_20260608_v13_index_all_execute rows=1945
index 20260605:
  condition_layer_20260605_to_20260608_20260608013900_execute rows=9
  condition_layer_20260605_to_20260608_v13_index_all_execute rows=83
board 20260605:
  condition_layer_20260605_to_20260608_20260608013900_execute rows=428
  condition_layer_20260605_to_20260608_v13_index_all_execute rows=127

Expected 20260604 repaired run still exists:
condition_layer_20260604_source_20260604_v1 rows stock/index/board=1952/9/428
```

Recommended fix:

```text
Add an explicit B-track filter source-run resolver and require filter-center
queries to anchor to exactly one reviewed run_id/source_condition_run_id.
Do not use max(source_trade_date) as the source authority when multiple runs can
share the same source date.
```

Affected gate:

```text
B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE
B_TRACK_V2_FIELD_VISIBILITY_POLICY_CLOSEOUT_GATE
future B_TRACK_V2_DETAIL_DRAWER_* gates
```

Safe next step:

```text
B_TRACK_V2_FILTER_CENTER_ACTIVE_RUN_ANCHOR_REPAIR_PLAN_GATE
```

### CLCA-P1-001: Experimental local display cache remains active after being marked tainted

Severity: `P1`

Location:

```text
docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.md:1
docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.md:2
docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.md:3
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:48
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:52
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:53
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:54
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:129
docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md:136
```

Expected:

```text
The local display cache physical tables are experimental/tainted for B-track
filter-center and must not be treated as an authoritative B-track source.
```

Actual:

```text
The experimental cache is still active in live DB:
cache_run_id=n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
status=passed
is_active=true
```

Evidence:

```text
Live DB cache rows:
n6_stock_display_cache=8370
n6_index_display_cache=40
n6_board_display_cache=1824
n6_index_membership_display_cache=12841
n6_board_membership_display_cache=56960

Docs:
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.md says result=EXECUTED and database_written=True.
B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md says the same cache must be treated as
experimental/tainted_for_b_track_filter_center.
```

Recommended fix:

```text
Open a dedicated retire/rollback decision gate. Either deactivate/rollback the
tainted cache or rename/mark it so no future B-track source resolver can select
it as authoritative.
```

Affected gate:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_* gates
B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_* gates
```

Safe next step:

```text
N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_RETIRE_OR_ROLLBACK_DECISION_GATE
```

### CLCA-P2-001: Legacy fetch_cards still joins base display table

Severity: `P2`

Location:

```text
src/ashare_v3/web/n6_user_app.py:445
src/ashare_v3/web/n6_user_app.py:474
src/ashare_v3/web/n6_user_app.py:478
docs/B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_AUDIT.md:169
docs/B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_AUDIT.md:171
```

Expected:

```text
B-track app source-boundary closeout should avoid base display_basis reads in
current app routes, and residual base-table reads should remain isolated.
```

Actual:

```text
fetch_cards still contains:
LEFT JOIN stock_condition_display_basis s

The previous global audit documents this as out-of-scope because fetch_cards is
not called by current /api/n6/app/* or /n6/app/... routes.
```

Evidence:

```text
src/ashare_v3/web/n6_user_app.py:478 LEFT JOIN stock_condition_display_basis s
docs/B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_AUDIT.md:171 documents the legacy join and
states it is not currently called by B-track app routes.
```

Recommended fix:

```text
Keep this non-blocking for current B-track routes, but open a cleanup gate to
either remove fetch_cards or switch it to v_n6_stock_condition_display_basis
before any future route can call it.
```

Affected gate:

```text
B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_AUDIT_GATE
future N6 legacy card/detail route gates
```

Safe next step:

```text
N6_LEGACY_USER_CARD_SOURCE_BOUNDARY_CLEANUP_GATE
```

## Non-Finding Proofs

### GET-only B-track routes

Static route scan found only GET routes for:

```text
/api/n6/app/v1/*
/api/n6/app/v2/*
/n6/app
/n6/app/{page_key}
```

No B-track app POST/PUT/PATCH/DELETE route was found.

### Forbidden wording in source UI

Forbidden wording scan over `src/ashare_v3/web` did not find active UI/source
strings for:

```text
建议买入 / 建议卖出 / 买入机会 / 卖出提醒 / 一键下单 /
已买入 / 已卖出 / 已成交 / 实盘账户 / 可用下单资金 /
真实收益 / 稳赚 / 高胜率 / 低风险 / 高收益
```

Hits in `tests/` and `docs/` are negative assertions or forbidden-word lists,
not UI output.

### N5 state machine boundary

Static scan shows N5 execute enforces TriggerMatched-only action facts:

```text
src/ashare_v3/action/execute.py:665 if event_type != "TriggerMatched": continue
```

TriggerPendingMarketData remains documented as quality-only and did not show a
direct action fact write path in this audit.

### Runtime route availability

The 8786 process responded:

```text
/n6/login -> 200
/n6/app/filter-center -> 302 login redirect
/api/n6/app/v2/filter/stocks -> 401 unauthorized
```

This audit did not find a TestClient-pass/live-404 contradiction for these
routes.

## Recommended Remediation Gates

1. `B_TRACK_V2_FILTER_CENTER_ACTIVE_RUN_ANCHOR_REPAIR_PLAN_GATE`
2. `B_TRACK_V2_FILTER_CENTER_ACTIVE_RUN_ANCHOR_REPAIR_IMPLEMENTATION_GATE`
3. `B_TRACK_V2_FILTER_CENTER_ACTIVE_RUN_ANCHOR_REPAIR_POST_REVIEW_GATE`
4. `N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_RETIRE_OR_ROLLBACK_DECISION_GATE`
5. `N6_LEGACY_USER_CARD_SOURCE_BOUNDARY_CLEANUP_GATE`

N5 consumption, N6 proposal/order/trade, position/PnL, delivery/push/voice/mobile,
sim, worker, and real trade remain out of scope.
