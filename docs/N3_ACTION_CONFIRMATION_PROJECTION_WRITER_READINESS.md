# N3 Action-Confirmation Projection Writer Readiness

Status: DRAFT_PASS

Generated at: 2026-06-02T14:26:42.291509+08:00

Layer role: N3_market_data

## Stage

```text
N3 action-confirmation projection writer/readiness alignment
```

## Lineage

```text
projection_run_id=action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_condition_run_id=condition_layer_20260601_source_20260601_v1
source_subscription_run_id=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_snapshot_run_id=realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_today_minute_run_id=today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
source_previous_day_minute_run_id=previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
```

## Candidate Summary

```text
stock=765
index=54
board=150
total=969
```


## Quality

```text
P0=0
P1=0
P2=0
blockers=[]
```

## Writer Boundary

```text
writes_database=False
writes_projection_business_rows=False
writes_outbox=False
consumes_outbox=False
writes_inbox_or_checkpoint=False
downstream_layers_touched=False
worker_started=False
```

## N4/N5 Boundary

N4/N5 must consume these N3 standard metrics and must not recompute 1m / 5m / 30m / 120m indicators from raw minute rows.
