# N2/N4 Trigger Context Refresh Dry-Run

Result: `DRY_RUN_BLOCKED`

Semantic trigger baseline result: `PASS`

Strict contract result: `BLOCKED`

This dry-run used repaired N2 context enrichment code to replay the 20260605 N2/N4 trigger context inputs. It did not execute SQL, did not write database rows, did not roll back anything, did not enter N3/N4/N5/N6, did not consume or update outbox/inbox/checkpoint, and did not start a worker.

## Target

```text
condition_run_id = condition_layer_20260604_source_20260604_v1
context_run_id   = trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
source_trade_date = 20260604
for_trade_date    = 20260605
```

## Planned Refresh Rows

```text
condition_basis:
  stock = 5511
  index = 9
  board = 428
  total = 5948

context refresh:
  stock = 4186
  index = 20
  board = 912
  total = 5118
```

The replay row count matches the contract:

```text
context_row_count = 5118
context_candidate_mismatch = 0
context_enrichment_rows = 5118
```

## Semantic Proof

`stock:SZ:002399`

```text
condition_key = BUY:Y,Q,M,W,D
trigger_previous_open = 9.66
trigger_previous_close = 9.45
trigger_previous_entity_high = 9.66
trigger_previous_entity_low = 9.45
trigger_previous_amount_baseline = 43678.117
baseline_source_trade_date = 20260604

classification_previous_entity_high = 9.79
classification_previous_entity_low = 9.67
classification_period_key_previous = 20260603
```

`index:SZ:399006`

```text
condition_key = BUY:W,D
trigger_previous_open = 4072.55
trigger_previous_close = 4088.88
trigger_previous_entity_high = 4088.88
trigger_previous_entity_low = 4072.55
trigger_previous_amount_baseline = 703241125888
baseline_source_trade_date = 20260604

classification_previous_entity_high = 4122.99
classification_previous_entity_low = 4089.02
classification_period_key_previous = 20260603
```

Board sample `board:TDX:880201` uses the same mapping:

```text
condition_key = BUY:Q,M,W
trigger_previous_open = 934.28
trigger_previous_close = 948.33
trigger_previous_entity_high = 948.33
trigger_previous_entity_low = 934.28
trigger_previous_amount_baseline = 11529799680
baseline_source_trade_date = 20260604

classification_previous_entity_high = 947.51
classification_previous_entity_low = 933.9
classification_period_key_previous = 20260603
```

## Coverage

Trigger baseline coverage is complete:

```text
trigger_previous_open missing = 0
trigger_previous_close missing = 0
trigger_previous_entity_high missing = 0
trigger_previous_entity_low missing = 0
trigger_previous_amount_baseline missing = 0
baseline_source_trade_date missing = 0
trigger_fields_coverage = 100%
```

Context enrichment trace coverage is complete:

```text
context_enrichment_hash missing = 0
trigger_amount_chain_baseline missing = 0
trigger_amount_chain_formula_hash missing = 0
FULL_prerequisite_trace missing = 0
HINT_prerequisite_trace missing = 0
```

Classification trace coverage is not 100%:

```text
period entries = 25590
classification complete period entries = 25517
classification missing period entries = 73
rows with any classification gap = 47
classification complete row coverage = 99.08167252833138%
classification complete period-entry coverage = 99.71473231731145%
```

The non-missing classification fields still match legacy `previous_*` trace:

```text
legacy_classification_mismatch_non_amount = 0
```

## N4 Context Proof

```text
N4 trigger baseline source = trigger_previous_entity_high / trigger_previous_entity_low / trigger_previous_amount_baseline
legacy_previous_used_as_trigger_baseline_rows = 0
baseline_source_trade_date_mismatch_rows = 0
D_baseline_still_from_period_key_previous_rows = 0
legacy previous_* retained as classification trace = true
n4_can_recompute_context = false
```

## P0 Guard Dry-Run

```text
missing trigger_previous_entity_high/low = 0
missing trigger_previous_amount_baseline = 0
baseline_source_trade_date mismatch = 0
legacy previous used as trigger baseline = 0
D baseline still from period_key_previous = 0
```

## Quality

```text
P0/P1/P2 = 0/1/1
```

P1:

```text
classification_previous_* coverage is not 100%; 73 period entries across 47 rows lack legacy classification trace fields.
```

P2:

```text
period_baseline_ready has 73 not-ready period entries; required-period baseline missing rows remain 0.
```

## Rollback Preview

Rollback draft:

```text
sql/N2_N4_TRIGGER_CONTEXT_REFRESH_ROLLBACK_DRAFT.sql
```

Static rollback proof:

```text
rollback_static_check = passed
rollback_still_safe = true
N4 match refs = 0
N4 outbox refs = 0
N5 refs = 0
N6 refs = 0
event inbox/checkpoint refs = 0
```

## Boundary

```text
writes_performed = false
will_execute_sql = false
rollback_executed = false
downstream_layers_entered = false
outbox_consumed_or_updated = false
worker_started = false
```

## Next Gate

`N2_N4_TRIGGER_CONTEXT_REFRESH_EXECUTE_CONTRACT_GATE` is not allowed yet.

Reason:

```text
classification_coverage_not_100
```

The trigger baseline semantic repair is ready for N4 dry-run, but this gate explicitly required `classification_* coverage = 100%`. Runtime control needs to either accept the 73 missing classification trace period entries as non-blocking legacy gaps or route a repair to the owning layer before execute contract.
