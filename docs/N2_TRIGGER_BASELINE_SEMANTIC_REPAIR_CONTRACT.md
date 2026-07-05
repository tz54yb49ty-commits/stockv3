# N2 Trigger Baseline Semantic Repair Contract

Gate: `N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_CONTRACT_GATE`

Layer role: `N2_condition`

Result: `CONTRACT_PASS`

This gate is contract-only. It did not execute N2, did not write database rows, did not roll back any run, did not enter N3/N4/N5/N6, did not consume outbox, and did not start any worker.

## Background

`N2_N4_TRIGGER_BASELINE_SEMANTIC_AUDIT_GATE` reported `SEMANTIC_FAIL`.

The failing semantic is:

```text
period_trigger_baseline_json.periods.D.previous_* currently means classification previous period.
N4 localized the same previous_* fields as for_trade_date trigger baseline.
```

That makes N4 trigger thresholds one trading day older than required.

Examples:

```text
002399.SZ:
  source_trade_date=20260604
  official open/close=9.66/9.45
  expected N4 trigger entity high/low=9.66/9.45
  current previous_entity_high/low=9.79/9.67 from 20260603

399006:
  expected N4 trigger entity high/low=4088.88/4072.55
  current previous_entity_high/low=4122.99/4089.02 from 20260603
```

## Contract

N2 must split the JSON semantics into two independent field families.

### Classification Baseline

These fields are for source-date classification and audit trace only:

```text
classification_previous_open
classification_previous_close
classification_previous_entity_high
classification_previous_entity_low
classification_previous_amount_baseline
classification_period_key_previous
```

They map from the legacy `previous_*` / `period_key_previous` values.

### N4 Trigger Baseline

These fields are the only fields N4 may use as trigger thresholds:

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

## Compatibility

Legacy `previous_*` fields may remain in `period_trigger_baseline_json`; N2 copies the previous complete period entity baseline into `trigger_previous_*` so N4 does not need to dereference legacy names.

N4 context must not use current period seed fields as formal entity trigger baselines after this repair.

## P0 Blockers

The implementation must block if any of these are true:

```text
N4 context trigger baseline comes from current_open_seed/current_close_seed
trigger_previous_entity_high / trigger_previous_entity_low is missing
baseline_source_trade_date != source_trade_date
N4 dereferences legacy previous_* directly instead of N2-frozen trigger_previous_*
trigger_previous_amount_baseline is missing
```

## Repair Scope

```text
N2 condition basis enrichment
N2 context enrichment row-level materialization
N2 trigger_context_snapshot generation contract
N4 context reader/localizer verification or handoff, including current-seed guard
stock/index/board sample tests
P0 guard tests
```

## Next Gate

Allowed next gate:

```text
N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_IMPLEMENTATION_GATE
```

The next gate may modify N2 implementation and tests, but must still remain no-execute and no-DB-write unless a later user confirmation explicitly changes that boundary.
