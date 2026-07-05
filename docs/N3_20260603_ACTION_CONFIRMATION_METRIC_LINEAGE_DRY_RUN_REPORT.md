# N3 20260603 Action-Confirmation Metric Lineage Dry-Run Report

- result: `DRY_RUN_PASS`
- planned_action_confirmation_metric_run_id: `action_confirmation_projection_metric_20260603__trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- trigger_execute_run_id: `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1`
- projection_enrichment_v4_run_id: `projection_enrichment_v4_20260603_until_1500__realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- target_db: `ashare_v3` / `ashare_v3_user` / `127.0.0.1/32:5432`

## Row Summary

| item | stock | index | board | total |
|---|---:|---:|---:|---:|
| planned metric rows | 640 | 34 | 148 | 822 |
| distinct matched identities | 640 | 34 | 148 | 822 |

N4 matched events: `863`. The action metric table grain is identity-level, so duplicate N4 matched events share one metric row. Event coverage after planned rows: `863/863`.

## Metric Coverage

- metric_ready/not_ready: `822/0`
- 120m price confirmation rows: `822`
- 30m price confirmation rows: `822`
- 5m price+amount confirmation rows: `822`
- 1m price+amount confirmation rows: `822`

## Lineage

- N4 TriggerMatched rows: `863`
- N3 projection_enrichment_v4 join: `863/863`
- source run pairs: `2`
- source_fact_ids/source_minute_refs non-empty: `822/822`
- DB CHECK simulation failures: `0`

## Boundary

- BJ identity rows: `0`
- FULL signal/condition rows: `0/0`
- writes_database=false, writes_outbox=false, consumes_outbox=false, N4/N5/N6 touched=false, worker_started=false

## Quality

- P0/P1/P2: `0/2/0`
- P1 warning 1: execute runner must support per-identity multi-source-pair materialization.
- P1 warning 2: N3 materialization will not mutate existing N4 payload `source_action_confirmation_metric_id`; downstream must use deterministic join or an N4 metric-link refresh.

## Gate

Direct execute final gate: `False`. Materialization implementation gate allowed: `True`.
