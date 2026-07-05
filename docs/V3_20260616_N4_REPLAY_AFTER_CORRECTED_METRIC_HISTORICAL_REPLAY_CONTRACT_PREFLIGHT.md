# V3 20260616 N4 Corrected Metric Historical Replay Contract / Preflight Retry

Result: `DRY_RUN_PREFLIGHT_PASS`

Gate: `V3_20260616_N4_REPLAY_AFTER_CORRECTED_METRIC_HISTORICAL_REPLAY_CONTRACT_PREFLIGHT_GATE_RETRY`

Layer role: `N4_trigger`

## Source Metric Proof

N4 replay is explicitly bound to the corrected N3 historical replay metric run:

```text
projection_run_id =
action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4

projection_schema_version =
v3.realtime_virtual_metric.writer.contract.v1.historical_replay.formal_amount_chain_unit_proof

source_condition_run_id =
condition_layer_20260615_source_20260615_for_20260616_v4

source_subscription_run_id =
market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
```

Metric scope:

```text
metric rows = 620
metric_ready = 620
metric_quality_passed = 620
BUY_HINT / SELL_HINT / non-HINT = 46 / 574 / 0
fake_realtime_snapshot=true = 0
stale_v1_b1_c1_reused=true = 0
```

Historical replay source scope is multi-source by design:

```text
historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 = 467
previous_day_minute_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1 = 153
```

N4 now accepts this corrected historical schema and does not truncate the 620-row metric scope to a single `source_snapshot_run_id`.

## Context Proof

N4 replay is explicitly bound to v4 context:

```text
trigger_context_run_id =
trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4

context status = passed
context rows stock/index/board/total = 4194/183/307/4684
context BUY_HINT / SELL_HINT = 46 / 574
```

The corrected metric HINT scope aligns with v4 context HINT rows.

## Planned Distribution

Generated artifacts:

```text
docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN.md/json
docs/V3_20260616_N4_TRIGGER_REPLAY_DRY_RUN_PREFLIGHT.md/json
docs/V3_20260616_N4_TRIGGER_REPLAY_CONTRACT.md/json
docs/V3_20260616_N4_TRIGGER_REPLAY_PREFLIGHT.md/json
sql/V3_20260616_n4_trigger_replay_after_corrected_metric_historical_replay_rollback.sql
```

Planned writes after a future final-gate-confirmed execute:

```text
common_trigger_run = 1
common_trigger_state = 4684
common_trigger_match = 157
common_event_outbox = 4684
TriggerMatched = 157
TriggerPendingMarketData = 4527
TriggerStateChanged = 0
P0/P1/P2 = 0/1/0
```

No execute was performed in this gate.

## HINT Path Proof

`TriggerMatched` is HINT-only:

```text
BUY_HINT = 3
SELL_HINT = 154
ordinary B_BUY = 0
ordinary S_SELL = 0
```

30m marker distribution:

```text
30m_volume = 3
30m_shrink = 154
```

## Ordinary / FULL Caveat

Preserved:

```text
source metric scope = HINT_ONLY
BUY / BUY:FULL / SELL / SELL:FULL metric scope = 0
ordinary formal restored = false
```

Ordinary/FULL context rows remain non-entry pending when no compatible corrected metric exists.

## Trigger Price Proof

All planned `TriggerMatched` rows include:

```text
trigger_price
trigger_price_source = n3_action_confirmation_metric.current_price
```

Missing counts:

```text
trigger_price missing = 0
trigger_price_source missing = 0
```

## Pending Non-Entry Proof

`TriggerPendingMarketData` remains non-entry:

```text
TriggerPendingMarketData = 4527
pending writes common_trigger_match = 0
pending n5_entry_allowed=true = 0
pending trigger_live=true = 0
```

## Target Baseline Proof

Target execute run:

```text
v3_n4_trigger_replay_20260616_after_corrected_metric_historical_replay_v1
```

Baseline:

```text
common_trigger_run = 0
common_trigger_quality_item = 0
common_trigger_state = 0
common_trigger_match = 0
common_event_outbox = 0
downstream inbox refs = 0
downstream checkpoint refs = 0
n5 action run refs = 0
```

## Rollback Proof

Rollback SQL:

```text
sql/V3_20260616_n4_trigger_replay_after_corrected_metric_historical_replay_rollback.sql
```

Proof:

```text
hard-fail before DELETE/UPDATE = true
scoped to execute_run_id = true
guards N5/N6/downstream refs = true
no DROP/TRUNCATE/CASCADE = true
```

## Forbidden Scope Proof

Confirmed:

```text
N4 replay executed = false
database written = false
rollback executed = false
outbox/inbox/checkpoint consumed or updated = false
scheduler/worker started = false
entered N5/N6 = false
market pull = false
voice/mobile/sim/position/order/real trade touched = false
old system touched = false
```

## Next Gate

`V3_20260616_N4_REPLAY_AFTER_CORRECTED_METRIC_HISTORICAL_REPLAY_FINAL_GATE_REVIEW_GATE`
