# N2/N4 Trigger Context Refresh Execute Contract

Result: `CONTRACT_PASS`

This repaired contract is compatible with `scripts/run_n2_context_enrichment_materialization_execute.py` and keeps this gate no-write.

## Runner Top-Level Keys

| key | value |
|---|---|
| target_run_id | `trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1` |
| source_condition_run_id | `condition_layer_20260604_source_20260604_v1` |
| for_trade_date | `20260605` |
| spec_version | `N2-context-enrichment-row-materialization-v1` |
| policy_hash | `22b892190d9c271265f4f544aa455dec43aad710744deaf763df8bb09ab67434` |
| expected_context_rows | `5118` |
| rollback_sql_path | `sql/N2_N4_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql` |
| payload_path | `docs/N2_N4_TRIGGER_CONTEXT_REFRESH_PAYLOAD.jsonl` |

## Payload

- JSONL line count: `5118`
- rows by asset: stock `4186`, index `20`, board `912`
- JSON parse: `PASS`
- trigger field coverage: `100%`
- baseline_source_trade_date mismatch: `0`
- legacy previous used as trigger baseline: `0`

## Accepted Exception

Runtime control exception remains encoded and limited to legacy classification trace:

- classification rows with any gap: `47` / `5118`
- classification period entries with gap: `73` / `25590`
- trigger coverage remains `100%`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n2_context_enrichment_materialization_execute.py --payload-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_PAYLOAD.jsonl --contract-path docs/N2_N4_TRIGGER_CONTEXT_REFRESH_EXECUTE_CONTRACT.json --execute --user-confirmed
```

The command still requires a separate execute final gate and explicit `--execute --user-confirmed`.

## Rollback

Rollback SQL: `sql/N2_N4_TRIGGER_CONTEXT_REFRESH_ROLLBACK.sql`

Rollback hard-fails before DELETE/UPDATE if event infra, N4, N5, or N6 refs exist. It only clears the repaired refresh target rows and keeps N1/N3 facts and outbox/inbox/checkpoint untouched.

## Boundary

This repair gate did not execute SQL, write DB rows, enter N3/N4/N5/N6, consume/update outbox, or start workers.
