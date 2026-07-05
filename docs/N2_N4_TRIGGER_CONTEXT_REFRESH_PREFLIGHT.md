# N2/N4 Trigger Context Refresh Preflight

Result: `PASS`

Mode: read-only DB plus artifact check.

This preflight does not execute refresh SQL and does not write database rows.

## Target

```text
condition_run_id = condition_layer_20260604_source_20260604_v1
context_run_id   = trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
source_trade_date = 20260604
for_trade_date    = 20260605
```

## Planned Scope

```text
condition_basis rows:
  stock = 5511
  index = 9
  board = 428
  total = 5948

context refresh rows:
  stock = 4186
  index = 20
  board = 912
  total = 5118
```

## Read-Only Live Ref Check

The DB check was run under `default_transaction_read_only=on`.

```text
old context exists = true
common_trigger_run context rows = 1
stock/index/board context rows = 4186 / 20 / 912

N4 match refs = 0
N4 state refs = 0
N4 outbox refs = 0
event inbox refs = 0
event checkpoint refs = 0
N5 action_run refs = 0
N5 action_event refs = 0
N6 refs = 0
```

## Checks

```text
old_context_exists = passed
current_n4_match_outbox_zero = passed
n5_n6_refs_zero = passed
event_infra_refs_zero = passed
repaired_code_readiness = passed
target_refresh_baseline_can_be_replayed = passed
```

## Semantic Post-Check Plan

After a later dry-run or execute gate, the repaired context must prove:

```text
stock:SZ:002399
  trigger_previous_entity_high = 9.66
  trigger_previous_entity_low  = 9.45
  baseline_source_trade_date   = 20260604

index:SZ:399006
  trigger_previous_entity_high = 4088.88
  trigger_previous_entity_low  = 4072.55
  baseline_source_trade_date   = 20260604
```

N4 context must read `trigger_*` fields for trigger baselines. Legacy `previous_*` fields may remain only as classification trace.

## Boundary

```text
will_execute_sql = false
writes_performed = false
outbox_consumed_or_updated = false
downstream_layers_entered = false
worker_started = false
```

Allowed next gate:

```text
N2_N4_TRIGGER_CONTEXT_REFRESH_DRY_RUN_GATE
```
