# N4 Action-Confirmation Metric Consumption Contract Alignment

Status: CONTRACT_ALIGNMENT_PASS

Layer role: N4_trigger

Generated at: 2026-06-02

This gate is contract/readiness only:

```text
execute=false
database_write=false
outbox_write=false
inbox_checkpoint_write=false
trigger_fact_write=false
worker_started=false
n5_n6_entered=false
real_trade=false
```

## 1. Input Lineage

N3 action-confirmation projection writer execute has passed:

```text
projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
projection_schema_version=n3.action_confirmation_metric.v1
source_condition_run_id=condition_layer_20260601_source_20260601_v1
source_subscription_run_id=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_snapshot_run_id=realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_today_minute_run_id=today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_previous_day_minute_run_id=previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
for_trade_date=20260602
```

N3 metric facts are ready:

```text
stock/index/board/total=765/54/150/969
metric_ready/not_ready=969/0
metric_quality_status=passed rows=969
P0/P1/P2=0/0/0
source_fact_ids empty=0
source_minute_refs empty=0
required numeric fields missing=0
scoped outbox/inbox/checkpoint refs=0/0/0
```

## 2. N4 Consumption Contract

N4 may consume only N3 standard action-confirmation projection metric facts:

```text
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
```

N4 consumption key:

```text
projection_run_id
asset_kind
identity_key
trade_date
source_condition_run_id
```

N4 must require lineage alignment:

```text
metric.projection_run_id = allowlisted projection_run_id
metric.source_condition_run_id = current source_condition_run_id
metric.source_snapshot_run_id = allowlisted snapshot_run_id
metric.source_subscription_run_id = allowlisted subscription_run_id
metric.trade_date / for_trade_date = target trade date
```

N4 may read and carry these N3 metric fields as traceable trigger evidence:

```text
action_confirmation_metric_id
projection_run_id
projection_schema_version
source_snapshot_run_id
source_snapshot_event_id
source_today_minute_run_id
source_previous_day_minute_run_id
current_price
current_price_source
current_price_time
previous_120m_body_high / previous_120m_body_low
previous_30m_body_high / previous_30m_body_low
previous_5m_body_high / previous_5m_body_low
previous_1m_body_high / previous_1m_body_low
current_1m_amount / previous_1m_amount
current_5m_virtual_amount / previous_5m_full_amount
is_first_1m_of_day / is_first_5m_of_day / is_first_30m_of_day / is_first_120m_of_day
first_1m_amount_default_pass / first_5m_amount_default_pass
previous_1m_period_source / previous_5m_period_source / previous_30m_period_source / previous_120m_period_source
boundary_policy_version
buy_120m_price_pass / buy_30m_price_pass / buy_5m_price_pass / buy_5m_amount_pass / buy_1m_price_pass / buy_1m_amount_pass
sell_120m_price_pass / sell_30m_price_pass / sell_5m_price_pass / sell_5m_amount_pass / sell_1m_price_pass / sell_1m_amount_pass
metric_quality_status
metric_ready
source_fact_ids
source_minute_refs
previous_day_minute_refs
raw_json
```

N4 must not trust an opaque `action_confirmation` payload as proof. Any historical or compatibility payload field with that name is trace-only until replaced by this metric contract.

## 3. N4 Decision Boundary

N4 may decide only:

```text
trigger_live
current_status
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
projection_30m_flag
projection_30m_type
trigger_mark_candidate
```

N4 must not decide:

```text
final action_mark
ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped
alert-only / display / voice / sim / mobile / position / real-trade intent
```

N5 remains responsible for final action confirmation using N3 metrics plus N4 `TriggerMatched`.

## 4. Metric Ready Handling

When a matching metric row exists and is ready:

```text
metric_ready=true
metric_quality_status=passed
```

N4 may use the metric row as standardized evidence for trigger live state and 30m marker evidence, according to the N4 run-mode contract.

When the metric row is missing or not ready:

```text
metric_ready=false
metric row missing
metric_quality_status != passed
trace refs incomplete
lineage mismatch
```

N4 must not repair the evidence by reading raw minute facts or calling market adapters. N4 must produce only one of:

```text
TriggerPendingMarketData
quality-only / no-op plan
blocked dry-run/preflight item
```

N4 must not emit `TriggerMatched` from unready or missing metric evidence.

## 5. Forbidden Reads And Writes

Forbidden N4 reads for this contract:

```text
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
raw minute source tables
external market adapters
opaque payload.action_confirmation as proof
```

Forbidden writes in this gate:

```text
common_trigger_state
common_trigger_match
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N5/N6/action/user/voice/mobile/sim/position/real trade
```

## 6. Current N4 Divergence

Existing N4 matcher code is not yet aligned to this action-confirmation metric contract.

Current implementation status:

```text
src/ashare_v3/trigger/projection_matcher.py reads:
  stock_realtime_projection_metric
  index_realtime_projection_metric
  board_realtime_projection_metric

src/ashare_v3/trigger/projection_matcher.py does not read:
  stock_action_confirmation_projection_metric
  index_action_confirmation_projection_metric
  board_action_confirmation_projection_metric
```

Existing N4 tests prove the old projection matcher does not read raw minutes or market adapters, but they do not yet prove N4 consumes the new action-confirmation metric facts.

Therefore:

```text
N3 metric facts readiness = ready
N4 contract alignment = passed
N4 action-confirmation metric dry-run runner readiness = blocked until implementation
N4 business execute = blocked
```

## 7. Required N4 Alignment Scope

N4 needs a dedicated action-confirmation metric dry-run/preflight path.

Minimum implementation scope:

```text
new N4 read-only metric fetcher for stock/index/board_action_confirmation_projection_metric
allowlisted projection_run_id and lineage validation
metric_ready / metric_quality_status gating
missing metric -> TriggerPendingMarketData / quality-only / no-op plan
ready metric -> traceable trigger evidence plan
payload trace fields:
  source_action_confirmation_metric_id
  source_projection_run_id
  projection_schema_version
  source_snapshot_run_id
  source_snapshot_event_id
  metric_quality_status
  metric_ready
  source_fact_ids / source_minute_refs / previous_day_minute_refs
canonical boundary:
  runtime signal_type only B_BUY/S_SELL
  no final action_mark
  trigger_mark_candidate only
  TriggerStateChanged not written to common_trigger_match
```

Suggested new or updated artifacts:

```text
src/ashare_v3/trigger/action_confirmation_metric_matcher.py
scripts/plan_trigger_action_confirmation_metric_dry_run.py
tests/test_trigger_action_confirmation_metric_matcher.py
docs/N4_ACTION_CONFIRMATION_METRIC_DRY_RUN_REPORT.md
docs/N4_action_confirmation_metric_dry_run_report.json
docs/N4_ACTION_CONFIRMATION_METRIC_EXECUTE_PREFLIGHT.md
docs/N4_action_confirmation_metric_execute_preflight.json
```

## 8. Boundary Proof

This alignment gate was read-only and documentation-only.

Proof:

```text
database_write=false
trigger_fact_write=false
outbox_write=false
inbox_checkpoint_write=false
n3_outbox_consumed=false
n5_n6_entered=false
worker_started=false
market_data_pulled=false
old_system_touched=false
real_trade=false
```

## 9. Next Gate

Allowed next step:

```text
N4 action-confirmation metric dry-run/preflight runner implementation
```

Not allowed yet:

```text
N4 action-confirmation metric business execute
N5 action execute
N6 user projection
worker
outbox consumption
real trade
```
