# N3 20260609 B/C/B2 Scope Planning

Result: `PLANNING_PASS`

Layer role: `N3_market_data`

This planning gate is read-only. It did not execute commands, write database rows, run rollback SQL, pull today's realtime market data, consume or update outbox/inbox/checkpoint, start workers, enter N4/N5/N6, touch delivery/push/voice/mobile, touch proposal/order/trade/sim/position/PnL/real trade, or touch the old system.

## A1 Lineage Proof

```text
for_trade_date=20260609
source_trade_date=20260608
current local planning time=2026-06-09 14:31:28 CST +0800
target DB=ashare_v3 / ashare_v3_user / 127.0.0.1:5432
transaction_read_only=on
calendar=20260609 open, prev_trade_date=20260608
```

N2 source:

```text
run_id=condition_layer_20260608_source_20260608_for_20260609_v1
status=passed_active
P0/P1/P2=0/6/3
minute_target_scope stock/index/board=4043/216/265
```

N3 subscription stage:

```text
run_id=market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1
status=passed
P0/P1/P2=0/0/0
candidate/subscription/pull_plan=5226/2792/9
required_data_kind:
  realtime_daily_snapshot=2090
  minute_bar_1m=351
  previous_day_minute_bar_1m=351
market_data_pulled=false
market_data_fact_written=false
```

A1 previous-day minute preload:

```text
run_id=previous_day_minute_preload_20260608_for_20260609__market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1
status=passed
P0/P1/P2=0/0/0
trade_date=20260608
is_previous_day_preload=true
minute rows stock/index/board/total=69360/12240/2640/84240
```

Current downstream baseline:

```text
B1 realtime snapshot rows stock/index/board=0/0/0
C1 today minute rows stock/index/board=0/0/0
B2 projection metric rows stock/index/board=0/0/0
scoped outbox/inbox/checkpoint refs=0/0/0
N4/N5/N6 refs=0/0/0
```

## B1/C1/B2 Candidate Scope

### B1 Realtime Daily Snapshot

```text
recommended gate=N3_B1_20260609_REALTIME_SNAPSHOT_DRY_RUN_PREFLIGHT_GATE
source subscription run=market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1
required_data_kind=realtime_daily_snapshot
candidate objects=2090
recommended mode=fact_only_no_outbox
```

Allowed future write tables:

```text
common_market_data_run
common_market_data_quality_item
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
```

Forbidden future scope:

```text
today minute write
realtime projection write
N4/N5/N6
outbox consumption
worker
delivery/push/voice/mobile
proposal/order/trade/sim/position/PnL/real trade
```

Rollback requirement:

```text
hard-fail before DELETE
scope by B1 snapshot_run_id and source subscription run
guard outbox/inbox/checkpoint, N3-C/B2, N4/N5/N6 refs, worker/downstream flags
```

### C1 Today Minute Bar 1m

```text
recommended gate=N3_C1_20260609_TODAY_MINUTE_CLOSED_INCREMENTAL_DRY_RUN_PREFLIGHT_GATE
source subscription run=market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1
required_data_kind=minute_bar_1m
candidate objects=351
recommended mode=closed_minute_fact_only_no_outbox
```

Closed-minute rule:

```text
Minute label HH:MM is closed only after HH:MM+1.
The final gate must compute latest_allowed_closed_minute from current local time and trading session calendar.
No unclosed minute may be written.
```

Allowed future write tables:

```text
common_market_data_run
common_market_data_quality_item
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
```

Rollback requirement:

```text
hard-fail before DELETE
scope by C1 today_minute run_id, for_trade_date, trade_date, and source subscription run
guard outbox/inbox/checkpoint, B2, N4/N5/N6 refs, worker/downstream flags
```

### B2 Realtime Projection Metric

```text
recommended gate=N3_B2_20260609_REALTIME_PROJECTION_SCOPE_READINESS_GATE
depends_on=A1 previous-day preload + B1 realtime snapshot + C1 today minute
recommended mode=fact_only_no_outbox
requires_lineage_expansion_decision=true
```

Lineage expansion rule:

```text
Current subscription has realtime_daily_snapshot objects=2090 and minute_bar_1m objects=351.
If projection dry-run needs minute evidence for stock/index objects outside current minute_bar_1m coverage, enter N3_B2_20260609_STOCK_INDEX_LINEAGE_EXPANSION_DRY_RUN_PREFLIGHT_GATE before B2 execute.
```

Allowed future write tables:

```text
common_market_data_run
common_market_data_quality_item
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
```

Forbidden future scope:

```text
B1 snapshot write
C1 minute write
TriggerMatched / TriggerPendingMarketData / TriggerStateChanged
N4/N5/N6
outbox consumption
worker
delivery/push/voice/mobile
proposal/order/trade/sim/position/PnL/real trade
```

## Freshness / Timing Constraints

```text
current local time proof=2026-06-09 14:31:28 CST +0800
```

B1:

```text
planning status=READY_FOR_READINESS_RECHECK
current local date must equal for_trade_date
common_trade_calendar(for_trade_date).is_open must be true
final gate must re-check local time and source adapter freshness
if current local date != for_trade_date, BLOCK and use historical/EOD route
```

C1:

```text
planning status=READY_FOR_CLOSED_MINUTE_READINESS_RECHECK
current local date must equal for_trade_date
latest minute label must be closed before write
if after market close, use C1 historical/current-minute catch-up route with explicit latest_closed_minute
no unclosed minute may be written
```

B2:

```text
planning status=WAIT_FOR_B1_C1
B1 snapshot must be passed
C1 today minute must be passed
A1 previous-day minute preload must be passed
projection dry-run must prove duplicate=0, missing required=0, and ready/not_ready distribution
lineage expansion must be separately approved if needed
```

## Planning Blockers

P0:

```text
none
```

P1:

```text
fast_lane_real_orchestration_not_complete:
  registered non-blocking for manual N3 sequence

b2_lineage_expansion_may_be_required:
  current realtime_daily_snapshot objects=2090 vs minute_bar_1m objects=351
  defer to B2 scope readiness

n2_quality_p1_p2_carried:
  N2 P0=0; P1/P2 already registered as non-blocking
```

P2:

```text
prefer_fact_only_no_outbox_until_n4_ready:
  B1/C1/B2 planning recommends fact-only no-outbox unless a later final gate explicitly authorizes standard N3 events
```

## Recommended Gate Order

```text
1. N3_B1_20260609_REALTIME_SNAPSHOT_DRY_RUN_PREFLIGHT_GATE
2. N3_C1_20260609_TODAY_MINUTE_CLOSED_INCREMENTAL_DRY_RUN_PREFLIGHT_GATE
3. N3_B2_20260609_REALTIME_PROJECTION_SCOPE_READINESS_GATE
4. N3_B2_20260609_REALTIME_PROJECTION_DRY_RUN_PREFLIGHT_GATE_OR_LINEAGE_EXPANSION_GATE
```

## Forbidden Scope Proof

```text
executed_command=false
wrote_database=false
rollback_executed=false
pulled_today_realtime_market_data=false
consumed_or_updated_outbox_inbox_checkpoint=false
worker_started=false
entered_n4_n5_n6=false
delivery_push_voice_mobile_touched=false
proposal_order_trade_sim_position_pnl_real_trade_touched=false
old_system_touched=false
```

## Next Prompt

```text
layer_role=N3_market_data。

进入 N3_B1_20260609_REALTIME_SNAPSHOT_DRY_RUN_PREFLIGHT_GATE。

目标：
基于 20260609 N3 subscription run 和已完成的 A1 lineage，只读执行 B1 realtime_daily_snapshot dry-run / preflight，确认是否允许进入 B1 execute final gate。

依据：
- docs/N3_20260609_BC_B2_SCOPE_PLANNING.md/json
- docs/fastlane/20260609/05_closeout_registration.md/json
- docs/RUNTIME_CONTROL_20260609_N3_A1_POST_REVIEW_REGISTRATION.md/json
- source_subscription_run_id=market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1
- source_condition_run_id=condition_layer_20260608_source_20260608_for_20260609_v1

要求：
- 只读 dry-run/preflight
- 不 execute
- 不写数据库
- 不执行 rollback SQL
- 不消费/update outbox/inbox/checkpoint
- 不启动 worker
- 不进入 N3-C/B2/N4/N5/N6
- 不 delivery/push/voice/mobile
- 不 proposal/order/trade/sim/position/PnL/real trade
- 不触碰旧系统

请复核：
1. current local date / common_trade_calendar 是否支持 20260609 B1。
2. subscription required_data_kind=realtime_daily_snapshot rows/objects 是否为 2090。
3. B1 target baseline 是否为 0。
4. freshness / source adapter readiness。
5. expected snapshot rows stock/index/board。
6. rollback SQL requirement。
7. P0/P1/P2。

输出：
- DRY_RUN_PREFLIGHT_PASS / BLOCKED
- B1 source proof
- expected rows
- baseline proof
- freshness proof
- rollback requirement
- forbidden scope proof
- 是否允许进入 N3_B1_20260609_REALTIME_SNAPSHOT_EXECUTE_FINAL_GATE_REVIEW
```
