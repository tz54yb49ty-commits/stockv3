# V3 20260616 N4 Corrected Historical Replay Runner Input Alignment Report

Result: `ALIGNMENT_PASS`

Gate: `V3_20260616_N4_CORRECTED_HISTORICAL_REPLAY_RUNNER_INPUT_ALIGNMENT_GATE`

Layer role: `N4_trigger`

## Code Repair Summary

Updated N4 action-confirmation metric replay input handling:

- Added allowlist support for `v3.realtime_virtual_metric.writer.contract.v1.historical_replay.formal_amount_chain_unit_proof`.
- Allowed that corrected historical replay schema to span multiple `source_snapshot_run_id` values under the same `projection_run_id`, `source_condition_run_id`, `source_subscription_run_id`, and `for_trade_date`.
- Preserved strict single-`source_snapshot_run_id` lineage checks for non-historical schemas.
- Added metric scope compatibility guard so HINT-only metrics cannot be reused by ordinary `B_BUY` / `S_SELL` contexts.
- Added source trace fields into N4 metric trace:
  - `historical_closed_minute_source_run_id`
  - `source_today_minute_run_id`
  - `source_previous_day_minute_run_id`
  - `fake_realtime_snapshot`
  - `stale_v1_b1_c1_reused`

## Schema Allowlist Proof

Accepted schema:

```text
v3.realtime_virtual_metric.writer.contract.v1.historical_replay.formal_amount_chain_unit_proof
```

After refresh:

```text
lineage allowlist mismatches = 0
metric_ready rows = 620
```

## Metric Fetch Completeness Proof

Corrected metric selection uses:

```text
projection_run_id
source_condition_run_id
source_subscription_run_id
for_trade_date
```

For this historical replay schema, N4 no longer requires a single `source_snapshot_run_id` to cover the full metric run.

Proof:

```text
metric rows expected = 620
metric rows read = 620
```

Source snapshot distribution:

```text
historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 = 467
previous_day_minute_preload_20260616_for_20260617__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1 = 153
```

## Lineage Boundary Proof

Bound inputs:

```text
trigger_context_run_id =
trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4

projection_run_id =
action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_unit_proof__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4

source_condition_run_id =
condition_layer_20260615_source_20260615_for_20260616_v4

source_subscription_run_id =
market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
```

Boundary:

```text
stale v1 metric fallback = false
stale v1 context fallback = false
fake_realtime_snapshot=true = 0
stale_v1_b1_c1_reused=true = 0
raw minute read = false
market pull = false
```

## Refreshed N4 Planned Distribution

Refreshed artifacts:

```text
dry-run = DRY_RUN_PASS
dry-run preflight = PREFLIGHT_PASS
contract = CONTRACT_PASS
final preflight = PREFLIGHT_PASS
P0/P1/P2 = 0/1/0
```

Planned writes for a future approved execute:

```text
common_trigger_run = 1
common_trigger_state = 4684
common_trigger_match = 157
common_event_outbox = 4684
TriggerMatched = 157
TriggerPendingMarketData = 4527
TriggerStateChanged = 0
```

## HINT Path Proof

`TriggerMatched` is HINT-only:

```text
BUY_HINT = 3
SELL_HINT = 154
ordinary B_BUY = 0
ordinary S_SELL = 0
```

Marker distribution:

```text
30m_volume = 3
30m_shrink = 154
```

## Ordinary / FULL Caveat

Preserved:

```text
source metric scope = HINT_ONLY
ordinary formal restored = false
ordinary / FULL TriggerMatched = 0
```

Ordinary context rows with HINT-only metric evidence are now blocked from reusing that metric and remain non-entry pending.

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

## Rollback Proof

Rollback SQL:

```text
sql/V3_20260616_n4_trigger_replay_after_corrected_metric_historical_replay_rollback.sql
```

Proof:

```text
hard-fail before DELETE/UPDATE = true
guards downstream refs = true
no DROP/TRUNCATE/CASCADE = true
rollback executed = false
```

## Validation Summary

Validation completed:

```text
targeted N4 tests = 49 OK
check_n4_contract.py = PASS
compileall = PASS
JSON parse = PASS
rollback static check = PASS
git diff --check = PASS
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
