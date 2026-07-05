# V3 Realtime Signal Action Engine Executable Plan

Status: PLAN_PASS

Frozen at: 2026-06-12

Layer scope:

```text
N3_market_data -> N4_trigger -> N5_action
```

This plan is documentation and contract planning only:

```text
execute=false
database_write=false
scheduler_modified=false
worker_started=false
outbox_consumed=false
inbox_checkpoint_updated=false
n6_entered=false
voice_mobile_sim_trade_touched=false
```

## 1. Purpose

This document turns the user-confirmed runtime intent into an executable V3
implementation guide.

The target system is a realtime monitoring engine:

```text
N3 realtime 1m K / quote / snapshot
  -> N3 standardized realtime virtual metrics
  -> N4 realtime trigger / invalidation
  -> N5 action eligibility and final market confirmation
  -> N6 user policy in a later, separate layer
```

This plan does not change current N4/N5 business rules. It changes the N3 input
contract and clarifies that N4 may use N3 standardized realtime virtual metrics.

中文冻结：不改 N4/N5 当前业务规则。

N4/N5 runtime semantics remain:

```text
N4 events:
  TriggerMatched
  TriggerPendingMarketData
  TriggerStateChanged

N5 events:
  ActionEligible
  ActionBlocked
  ActionExecuted
  ActionSkipped

runtime signal_type:
  B_BUY
  S_SELL
```

`ActionExecuted` means market action confirmation is established. It does not
mean real order submission, sim trade, voice, mobile push, user card display, or
trade intent approval.

## 2. Superseded Conflict

The old blanket sentence:

```text
N4 不得使用未闭合分钟 K 生成 TriggerMatched。
```

is superseded for new realtime engine work.

The replacement rule is:

```text
N4 不得直接读取 raw 未闭合分钟 K，也不得自己拼 raw 1m/5m/30m/120m 指标。
N4 允许消费 N3 标准化、可追溯 realtime virtual metric 生成 TriggerMatched。
```

This is not a change to N4's business rule. It is an input-boundary correction:
N3 owns the forming-bar and virtual-period metric computation; N4 only consumes
the standard metric fact/event.

`MinuteBarClosed` remains useful for strict confirmation, replay, correction,
and audit. It is not a fast-lane blocker for N4 realtime trigger matching.

中文冻结：MinuteBarClosed 不作为 fast-lane blocker。

## 3. N3 Realtime Metric Ownership

N3 owns all market-data facts and all action-confirmation metrics. N4/N5 must
not rebuild these metrics from raw minute rows.

N3 must produce a standard `RealtimeVirtualMetric` / action-confirmation metric
covering:

```text
1m
5m
30m
120m
D
W
M
Q
Y
```

For each covered period, N3 must provide:

```text
current entity high / low
current virtual amount
previous period entity high / low
previous period amount
period source
metric ready / quality status
trace
```

Minimum common metric fields:

```text
metric_id
metric_run_id
metric_schema_version
asset_kind
identity_key
trade_date
metric_time
metric_time_label
source_time
observed_at
session_kind
period_source
is_closed_1m
is_auction_virtual
midday_bridge_policy
current_price
current_price_source
source_minute_refs
snapshot_id
event_id
quality_status
metric_ready
trace_json
```

Minimum action-confirmation fields:

```text
current_1m_entity_high
current_1m_entity_low
current_5m_entity_high
current_5m_entity_low
current_30m_entity_high
current_30m_entity_low
current_120m_entity_high
current_120m_entity_low

previous_1m_entity_high
previous_1m_entity_low
previous_5m_entity_high
previous_5m_entity_low
previous_30m_entity_high
previous_30m_entity_low
previous_120m_entity_high
previous_120m_entity_low

current_1m_amount
previous_1m_amount
current_5m_virtual_amount
previous_5m_full_amount
current_30m_virtual_amount
previous_30m_full_amount
current_120m_virtual_amount
previous_120m_full_amount
```

Minimum higher-period trigger fields:

```text
current_day_entity_high / low
current_week_entity_high / low
current_month_entity_high / low
current_quarter_entity_high / low
current_year_entity_high / low

previous_day_entity_high / low
previous_week_entity_high / low
previous_month_entity_high / low
previous_quarter_entity_high / low
previous_year_entity_high / low

current_day_virtual_amount
current_week_virtual_amount
current_month_virtual_amount
current_quarter_virtual_amount
current_year_virtual_amount

previous_day_amount
previous_week_amount
previous_month_amount
previous_quarter_amount
previous_year_amount
```

N3 may expose deterministic pass flags, but those flags must be derived from the
canonical numeric fields above and must keep source trace.

## 4. Session And Minute Label Policy

### 4.1 Realtime Cadence

First production version:

```text
launchd StartInterval=3
run-once process
no-overlap lock
run report per pass
long-running worker deferred
```

The preferred first version is a short-cycle run-once scheduler, not a permanent
loop worker. This keeps stop/unload, audit, and recovery simple.

### 4.2 Auction Session

From `09:20` to `09:30`, if mootdx returns a `09:31` label 1m K / minute state,
N3 treats it as:

```text
auction realtime virtual 1m
```

Allowed:

```text
N3 computes realtime virtual metrics.
N4 may emit TriggerMatched.
N5 may emit ActionEligible.
```

Not allowed:

```text
N3 must not write MinuteBarClosed before the minute is settled.
N5 must not emit ActionExecuted before the corresponding 1m confirmation fact is closed/settled.
```

### 4.3 Morning Continuous Session

From `09:30` to `11:30`:

```text
quote / snapshot / 1m K checked every 3 seconds
current minute is forming and may be used by N3 realtime virtual metric
closed 1m confirmation becomes available only after HH:MM+1
```

### 4.4 Lunch Break

From `11:30` to `13:00`:

```text
do not forge new minute K
low-frequency heartbeat or NOOP is allowed
retain the latest morning metric and closed minute context
```

There is no physical `11:30` minute K in the observed mootdx minute sequence.

### 4.5 Midday Bridge

N3 must use this bridge:

```text
13:00 label == equivalent to the missing 11:30 bar
13:01 compares against 13:00
```

Implications:

```text
13:01 previous 1m = 13:00
13:00 is not part of 13:01 current 5m
13:00 may close the previous 5m segment that otherwise would have ended at 11:30
N3 must not fabricate a separate 11:30 row
```

### 4.6 Afternoon Session

From `13:00` to `15:00`:

```text
quote / snapshot / 1m K checked every 3 seconds
current minute can form realtime virtual metrics
N4 may trigger from N3 metrics without waiting for full 5m/30m/120m period close
N5 ActionExecuted still requires the trigger-minute 1m confirmation fact
```

### 4.7 After Close

After `15:00`:

```text
stop realtime trigger creation
wait for official close / seal / archive path
replay and reconciliation may run separately
```

## 5. N4 Contract

N4 consumes:

```text
N2 localized condition context
N3 MarketSnapshotUpdated
N3 RealtimeVirtualMetric / action-confirmation metric
```

N4 must not:

```text
pull market data
read raw minute rows to assemble metrics
write action/user/sim/trade facts
decide final action_mark
decide alert-only / voice / mobile / sim / trade intent
```

N4 may emit `TriggerMatched` when:

```text
N2 condition provenance exists
N3 metric_ready=true
N3 metric_quality_status allows realtime trigger
side-specific price / amount / projection rule is satisfied
source trace is complete
```

N4 emits `TriggerPendingMarketData` when:

```text
N2 condition provenance exists
N3 metric is missing, not ready, delayed, or quality-blocked
```

N4 emits `TriggerStateChanged(trigger_live=false)` when:

```text
a previously live trigger becomes inactive under the latest N3 metric
```

N4 may emit `TriggerMatched + TriggerStateChanged` in the same transaction when
the matched outcome also creates a material state transition.

## 6. N5 Contract

N5 consumes only canonical N4 events:

```text
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
```

Only `TriggerMatched` starts action confirmation.

### 6.1 ActionEligible

When N5 receives a valid `TriggerMatched`, it may immediately write:

```text
ActionEligible(action_state=eligible)
```

`ActionEligible` means:

```text
the trigger has entered the action confirmation window
```

It is realtime and does not require the trigger-minute 1m confirmation fact to
be closed.

### 6.2 ActionExecuted

`ActionExecuted` requires:

```text
the original TriggerMatched is still valid for the action grain
the trigger-time N3 virtual 120m / 30m / 5m metric snapshot is saved and traceable
the trigger-minute 1m confirmation fact is closed/settled
the side-specific N5 B_BUY / S_SELL rules pass
idempotency and write-once guards pass
```

`ActionExecuted` must use:

```text
trigger-time virtual 120m / 30m / 5m evidence
plus closed trigger-minute 1m evidence
```

It must not replace the trigger-time virtual evidence with a later 120m/30m/5m
metric snapshot.

### 6.3 ActionBlocked / ActionSkipped

N5 writes `ActionBlocked` or `ActionSkipped` when:

```text
N3 metric is missing or quality-blocked
trigger-minute 1m confirmation does not pass
trigger_live=false before confirmation
confirmation window expires
idempotency or source allowlist fails
```

`TriggerPendingMarketData` and `TriggerStateChanged` must not create new action
confirmation by themselves.

## 7. Target-Machine Comparison Policy

Target-machine SQLite path:

```text
/Users/chuanfuchen/stock_monitor_isolated/data/monitor.db
```

This database is read-only reference material. It must not be modified by V3.

Initial comparison scope:

```text
signal_date=2026-06-12
signal_type in B_BUY / S_SELL
expected target count:
  B_BUY = 76
  S_SELL = 24
```

V3 comparison output must classify differences as:

```text
final_minute_correct_exclusion
target_fast_tick_alert_only
target_legacy_stock_board_alert_compatibility
true_v3_gap
```

Do not change N4/N5 canonical business rules just to reproduce target-machine
alert-lane counts. If an old target row was realtime alert-only and not confirmed
by final minute facts, it can be explained but must not force V3 `ActionExecuted`.

## 8. Implementation Sequence

1. Freeze this plan and static tests.
2. Extend N3 metric schema/contract for `RealtimeVirtualMetric`.
3. Implement N3 metric builder with auction and midday policies.
4. Add N3 dry-run/replay tests using 2026-06-12 target-machine data.
5. Align N4 input contract to consume N3 metrics, not raw minute rows.
6. Align N5 entry and final confirmation contract to save trigger-time metric snapshot.
7. Add run-once wrapper with `StartInterval=3` scheduler draft, no-overlap lock, and report output.
8. Run offline replay against target-machine B_BUY/S_SELL and classify differences.
9. Only after dry-run parity review, consider explicit execute gates.

## 9. Test Requirements

N3 metric tests:

```text
09:20-09:30 09:31 label becomes auction realtime virtual 1m
13:00 equals missing 11:30 and 13:01 compares with 13:00
current 5m / 30m / 120m / D / W / M / Q / Y virtual entity and amount are correct
previous period entity high/low and amount are correct
quality and trace fields are complete
```

N4 tests:

```text
N3 realtime virtual metric ready -> TriggerMatched without waiting for 1m close
N4 does not read raw minute rows
N3 metric missing -> TriggerPendingMarketData
matched then invalidated -> TriggerStateChanged(trigger_live=false)
```

N5 tests:

```text
TriggerMatched -> ActionEligible immediately
ActionExecuted uses trigger-time virtual metric snapshot
closed trigger-minute 1m not passing -> no ActionExecuted
TriggerPendingMarketData / TriggerStateChanged cannot create action confirmation
```

Regression tests:

```text
runtime signal_type remains B_BUY / S_SELL
canonical events remain unchanged
no N6 / voice / mobile / sim / trade
2026-06-12 B_BUY/S_SELL replay report JSON parse
compileall
git diff --check
```

## 10. Forbidden Scope

This plan does not authorize:

```text
database writes
scheduler install/enable
manual wrapper execution
N3/N4/N5 execute
outbox/inbox/checkpoint consumption or update
rollback SQL execution
N6 execution
voice/mobile/sim/position/PnL/real trade
old system modification
```

## 11. Acceptance

The implementation is acceptable when:

```text
N3 publishes traceable realtime virtual metrics for all required periods.
N4 can use those metrics for realtime TriggerMatched / invalidation without raw minute access.
N5 can emit ActionEligible immediately and ActionExecuted only after trigger-minute 1m confirmation.
The 09:20 auction and 13:00 midday bridge policies are explicitly tested.
N4/N5 business rules and canonical event names remain unchanged.
The 2026-06-12 B_BUY/S_SELL replay report classifies differences instead of masking them.
No N6/user/trade/sim/voice/mobile path is touched.
```
