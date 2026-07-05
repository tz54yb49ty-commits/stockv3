# N2/N4 Trigger Context Refresh Execute Preflight

Result: `PASS`

## Payload Readiness

- payload path: `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_PAYLOAD.jsonl`
- payload line count: `5118`
- expected context rows: `5118`
- rows by asset: stock `4186`, index `20`, board `912`
- JSON parse: `PASS`
- trigger_previous_entity_high/low missing: `0`
- trigger_previous_amount_baseline missing: `0`
- baseline_source_trade_date mismatch: `0`
- legacy previous used as trigger baseline: `0`
- D baseline from period_key_previous: `0`

## Runner Schema Compatibility

Required top-level keys are present:

```text
target_run_id
source_condition_run_id
for_trade_date
spec_version
policy_hash
expected_context_rows
rollback_sql_path
```

Runner compatibility: `PASS`

## Accepted Exception

- classification trace gap rows: `47`
- classification trace gap period entries: `73`
- exception encoded: `True`

## Execute Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n2_context_enrichment_materialization_execute.py --payload-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_PAYLOAD.jsonl --contract-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_EXECUTE_CONTRACT.json --execute --user-confirmed
```

No execute is performed in this gate.

## Rollback Proof

Rollback SQL `sql/N2_N4_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql` has hard-fail guards for event infra and downstream refs before the first DELETE/UPDATE. DELETE scope remains limited to the target refresh rows.
