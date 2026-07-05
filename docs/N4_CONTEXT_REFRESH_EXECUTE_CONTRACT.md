# N4 Context Refresh Execute Contract

Result: `CONTRACT_PASS`

Layer role: `N4_trigger`

This gate generated the execute contract, preflight, and rollback SQL for refreshing the 20260605 N4 trigger context snapshot. It did not execute, did not write database rows, did not write trigger state/match/outbox, did not consume/update outbox, and did not enter N5/N6.

## Target

```text
source_condition_run_id = condition_layer_20260604_source_20260604_v1
for_trade_date = 20260605
target_context_run_id = trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
```

## Planned Rows

```text
stock = 4186
index = 20
board = 912
total = 5118
```

## Reader Source

N4 must read the N2 semantic refresh from:

```text
stock_condition_context_enrichment
index_condition_context_enrichment
board_condition_context_enrichment
```

Precise join keys:

```text
materialization_run_id
source_condition_run_id
for_trade_date
source_minute_target_scope_id
identity_key
condition_key
direction
```

N4 must not read raw K, N1 daily, or self-aggregate. It must not fall back to a dry-run artifact as the primary source.

## Required P0 Post-Review Checks

```text
trigger_previous_entity_high/low missing = 0
trigger_previous_amount_baseline missing = 0
baseline_source_trade_date mismatch = 0
legacy previous used as trigger baseline = 0
required_period_not_ready_rows = 0
```

## Sample Proof

`stock:SZ:002399`, D:

```text
trigger_previous_entity_high = 9.66
trigger_previous_entity_low = 9.45
```

`index:SZ:399006`, D:

```text
trigger_previous_entity_high = 4088.88
trigger_previous_entity_low = 4072.55
```

## Execute Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py \
  --condition-run-id condition_layer_20260604_source_20260604_v1 \
  --for-trade-date 20260605 \
  --json-report-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_N4_EXECUTE_REPORT.json \
  --markdown-report-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_N4_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_20260605_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql
```

Direct execute is not currently allowed because the target context run already exists. The current runner does not overwrite the same run_id.

Required before direct execute:

```text
runtime_control approves N4-only context rollback/cleanup using sql/N4_20260605_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql
or a separate refresh-replace runner alignment gate is approved
```

## Rollback

Rollback SQL:

```text
sql/N4_20260605_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql
```

Rollback hard-fails before the first DELETE/UPDATE. DELETE scope is only:

```text
common_trigger_quality_item
stock_trigger_context_snapshot
index_trigger_context_snapshot
board_trigger_context_snapshot
common_trigger_run
```

Rollback does not touch N1/N2/N3 facts, N2 condition_context_enrichment rows, common_event_outbox/inbox/checkpoint, common_trigger_match/state, or N5/N6.

## Boundary

Still forbidden:

```text
N4 TriggerMatched execute
common_trigger_match/state/outbox writes
outbox consumption/update
N5/N6
worker
delivery/push/voice/mobile/sim/position/real trade
```
