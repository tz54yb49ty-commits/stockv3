# N2 Trigger Baseline Semantic Repair Implementation Readiness

Gate: `N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_IMPLEMENTATION_GATE`

Layer role: `N2_condition`

Result: `IMPLEMENTATION_PASS`

This gate only changed code, tests, and artifacts. It did not execute N2, did not write database rows, did not roll back any run, did not enter N3/N4/N5/N6, did not consume outbox, and did not start a worker.

## Field Mapping

N2 now treats the two baseline families as separate semantics.

Classification trace:

```text
classification_previous_open = previous_open
classification_previous_close = previous_close
classification_previous_entity_high = previous_entity_high
classification_previous_entity_low = previous_entity_low
classification_previous_amount_baseline = previous_amount_baseline
classification_period_key_previous = period_key_previous
```

N4 trigger baseline:

```text
trigger_previous_open = previous_open
trigger_previous_close = previous_close
trigger_previous_entity_high = previous_entity_high
trigger_previous_entity_low = previous_entity_low
current_seed_entity_high = max(current_open_seed, current_close_seed)  # trace only
current_seed_entity_low = min(current_open_seed, current_close_seed)   # trace only
trigger_previous_amount_baseline = current_amount_seed or current_avg_amount_seed
baseline_source_trade_date = source_trade_date
```

Legacy `previous_*` remains in JSON as source trace. N4 must still read the N2-frozen `trigger_previous_*` fields, not recompute or dereference historical K. Current period seed fields are trace-only for entity trigger semantics.

## Implementation Scope

Changed implementation paths:

```text
N2 context enrichment:
  src/ashare_v3/condition/context_enrichment.py

N4 local context preflight guard:
  blocked_by_layer=N4_trigger
```

N4 execute was not run. The N4 current-seed guard remains a handoff item for `layer_role=N4_trigger`.

## Sample Proof

`002399.SZ`:

```text
source_trade_date=20260604
legacy classification previous high/low=9.79/9.67
current seed high/low=9.66/9.45
expected trigger high/low=9.79/9.67
baseline_source_trade_date=20260604
```

`399006`:

```text
source_trade_date=20260604
legacy classification previous high/low=4122.99/4089.02
current seed high/low=4088.88/4072.55
expected trigger high/low=4122.99/4089.02
baseline_source_trade_date=20260604
```

`board:TDX:881078` W:

```text
current seed high/low=712.3/706.84
expected trigger high/low=696.8/632.78
```

## N4 Context Guard

N4 preflight now emits these P0 gates:

```text
trigger_baseline_semantic_fields_present
trigger_baseline_source_trade_date_match
trigger_baseline_not_from_current_seed
n4_context_uses_trigger_baseline_fields
```

Top-level report count:

```text
trigger_baseline_semantic_missing
```

## Forbidden Scope Proof

```text
writes_performed=false
will_execute_sql=false
database_touched=false
rollback_executed=false
downstream_layers_entered=false
outbox_consumed=false
worker_started=false
```

## Remaining Blockers

```text
No active N2 condition run has been regenerated in this gate.
Existing live N2/N4 context rows remain historical evidence until a later execute gate is explicitly approved.
runtime_control must review this implementation before any N2/N4 refresh or execute path.
```

## Next Gate

Allowed next step:

```text
runtime_control implementation review
```
