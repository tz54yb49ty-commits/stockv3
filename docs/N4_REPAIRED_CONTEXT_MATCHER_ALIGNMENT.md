# N4 Repaired Context Matcher Alignment

- result: ALIGNMENT_PASS
- layer_role: N4_trigger
- stage: N4_REPAIRED_CONTEXT_MATCHER_ALIGNMENT_GATE
- mode: matcher / trace / tests only
- database_written: false
- execute_performed: false
- outbox_consumed: false
- N5/N6 entered: false
- worker_started: false

## Root Cause

The repaired context dry-run was blocked because the matcher could not prove it was consuming repaired trigger baselines.

Before this alignment:

- `local_trigger_dry_run.py` ordinary BUY/SELL used `previous_amount / previous_avg_amount`.
- It did not enforce `trigger_previous_entity_high / trigger_previous_entity_low`.
- `synthetic_dry_run.py` trace omitted `trigger_previous_entity_high`, `trigger_previous_entity_low`, and `trigger_previous_amount_baseline`.

That caused the repaired-context corrected dry-run to keep the same compliant count as the tainted run:

- previous tainted compliant count: 1240
- repaired-context compliant count before this fix: 1240
- delta before this fix: 0

## Matcher Rule

Ordinary BUY now requires:

- `current_price_or_close > open`
- `current_price_or_close > trigger_previous_entity_high`
- `snapshot amount >= trigger_previous_amount_baseline`

Ordinary SELL now requires:

- `current_price_or_close < open`
- `current_price_or_close < trigger_previous_entity_low`
- `snapshot amount <= trigger_previous_amount_baseline`

If `trigger_*` is missing, the matcher can fallback to legacy previous fields only for compatibility. The primary path is repaired trigger baseline.

## Trace Rule

`period_trigger_baseline_trace` now outputs:

- `baseline_source`
- `previous_amount_baseline`
- `classification_previous_entity_high`
- `classification_previous_entity_low`
- `classification_previous_amount_baseline`
- `trigger_previous_entity_high`
- `trigger_previous_entity_low`
- `trigger_previous_amount_baseline`
- `baseline_source_trade_date`

When trigger fields are present:

```text
baseline_source=trigger_baseline
```

## Semantic Delta Probe

A read-only probe was run to prove the matcher consumed repaired baseline. Probe output was written to `/tmp/N4_REPAIRED_CONTEXT_MATCHER_ALIGNMENT_probe.json`.

Counts:

- previous tainted candidate count: 1537
- new candidate count: 896
- candidate delta: -641
- previous tainted compliant count: 1240
- new compliant count: 605
- compliant delta: -635
- previous tainted blocked count: 297
- new blocked count: 291
- blocked delta: -6
- probe result: DRY_RUN_PASS
- probe P0/P1/P2: 0/1/0

No DB write proof:

```text
common_trigger_run=0 -> 0
common_trigger_quality_item=0 -> 0
common_trigger_state=0 -> 0
common_trigger_match=0 -> 0
common_event_outbox=0 -> 0
common_event_inbox=0 -> 0
common_event_consumer_checkpoint=0 -> 0
```

## Trace Sample

Sample 1:

```text
identity_key=stock:SH:600009
condition_key=BUY:Y,Q,M,W,D
trigger_period=D
trigger_price=23.63
baseline_source=trigger_baseline
trigger_previous_entity_high=23.6
trigger_previous_entity_low=23.39
trigger_previous_amount_baseline=460386.175
legacy_previous_entity_high=24.28
legacy_previous_entity_low=23.79
legacy_previous_amount=467628.899
```

Sample 2:

```text
identity_key=stock:SH:600010
condition_key=BUY:Q,M,W,D
trigger_period=D
trigger_price=2.43
baseline_source=trigger_baseline
trigger_previous_entity_high=2.42
trigger_previous_entity_low=2.39
trigger_previous_amount_baseline=1267467.543
legacy_previous_entity_high=2.41
legacy_previous_entity_low=2.36
legacy_previous_amount=1622788.097
```

## Test Coverage

- `stock:SZ:002399`: BUY test proves amount and entity trigger baselines are used.
- `index:SZ:399006`: SELL test proves trigger entity low is used.
- `board:TDX:880920`: trace test proves board traces expose repaired trigger baseline fields.

## Modified Files

- `src/ashare_v3/trigger/local_trigger_dry_run.py`
- `src/ashare_v3/trigger/synthetic_dry_run.py`
- `tests/test_local_trigger_dry_run.py`
- `tests/test_trigger_synthetic_dry_run.py`
- `docs/N4_REPAIRED_CONTEXT_MATCHER_ALIGNMENT.md`
- `docs/N4_REPAIRED_CONTEXT_MATCHER_ALIGNMENT.json`

## Next Gate

Allowed next:

```text
N4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN_GATE
```

Still forbidden:

```text
N4 execute
N5/N6
outbox consumption
worker
delivery / push / voice / mobile / sim / position / real trade
```
