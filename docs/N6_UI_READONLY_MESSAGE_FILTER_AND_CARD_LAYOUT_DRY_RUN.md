# N6 UI Readonly Message Filter And Card Layout Dry Run

Status: DRY_RUN_PASS

Layer role: N6_user

Date: 2026-06-06

This dry-run is read-only. It probes the current 20260605 N6 action projection
cards and validates the planned filter/card layout contract without writing
business data, consuming or updating N5 outbox, writing notification queue rows,
starting workers, delivering/pushing/voice/mobile, running sim/position/PnL/real
trade, generating proposal/order/trade, or modifying B-track.

## 1. Source Scope

```text
target_database=ashare_v3
target_user=ashare_v3_user
target_host=127.0.0.1
projection_scope=latest passed user_projection_run
user_id=1
```

Current projection scope:

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
```

## 2. Count Proof

Repository read proof:

```text
empty_filter_rows=605
ActionExecuted=1
ActionBlocked=604
```

Blocked reason distribution:

```text
price_confirmation_failed=305
metric_missing=289
amount_confirmation_failed=10
```

Additional dimensions:

```text
asset_kind stock=572
asset_kind board=33
asset_kind index=0
direction buy=573
direction sell=32
signal_type B_BUY=573
signal_type S_SELL=32
```

## 3. Filter Dry Run

```text
empty filters -> 605
blocked_reason=metric_missing -> 289
action_state=executed -> 1
event_type=ActionExecuted -> 1
event_type=ActionBlocked -> 604
```

Date coverage:

```text
source_payload_json.event_time present=605
date_from=2026-06-05&date_to=2026-06-05&time_field=event_time -> 605
adapter trade_date=20260605 -> 605
created_at local date=2026-06-06 -> 605
```

Interpretation:

```text
event_time should be the default user-facing market message time
created_at should remain available as projection insertion/audit time
trade_date is usable for business-date grouping but is not the requested time_field value
```

## 4. Planned UI Dry Run

Statistics card values:

```text
ActionExecuted count=1
ActionBlocked count=604
TriggerMatched count=not mixed into the 605 N6 card list by default
price_confirmation_failed count=305
metric_missing count=289
amount_confirmation_failed count=10
```

Default card list:

```text
page_size=100
total_count=605
filtered_count=605
first_page_items=100
long_event_id_in_list=false
detail_drawer_available=true
```

Expected click filters:

```text
click ActionExecuted -> filtered_count=1
click ActionBlocked -> filtered_count=604
click metric_missing -> filtered_count=289
```

## 5. Detail Drawer Dry Run

Current rows contain enough reviewed N6 projection payload to derive:

```text
event_id
N5 action event id
action_run_id
source_action_status
blocked_reason
triggered_periods
baseline_source
source_payload_json.event_time
```

The N4 trigger event id is available through trace payload when
`trace_json.condition_provenance.source_trigger_event_ids` is present. If absent
for a row, implementation must show `—` and a missing-field warning in the drawer;
it must not回扫 N4 raw facts.

## 6. Wording Dry Run

Allowed labels:

```text
ActionExecuted -> 市场动作确认成立
ActionBlocked -> 市场动作未确认
TriggerMatched -> 触发已匹配
```

Forbidden wording must be absent from rendered card labels:

```text
已下单
已成交
真实交易
虚拟成交
建议买入
交易失败
下单失败
持仓失败
```

## 7. Boundary Proof

```text
database_written=false
write_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
real_trade=false
proposal=false
order=false
trade=false
modify_b_track=false
```

## 8. Dry-Run Result

```text
dry_run_result=DRY_RUN_PASS
P0=0
P1=0
P2=1 detail_drawer_may_show_missing_n4_trigger_event_id_for_rows_without_trace
allow_implementation_gate=true
next_allowed_gate=N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION_GATE
```
