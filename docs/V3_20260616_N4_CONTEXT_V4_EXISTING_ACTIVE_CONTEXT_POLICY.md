# V3 20260616 N4 Context V4 Existing Active Context Policy

Result: `POLICY_PASS`

Gate: `V3_20260616_N4_CONTEXT_V4_EXISTING_ACTIVE_CONTEXT_POLICY_GATE`

Layer role: `N4_trigger`

## Recommended Policy

Allow same `trade_date` multiple N4 context lineages to coexist only under an explicit scoped override.

Rationale:

- corrected metric v4 is a separate lineage from existing v1 context/replay evidence
- silently rolling back or superseding v1 context would mutate historical evidence
- blocking all same-day context coexistence prevents corrected v4 replay from using its required same-lineage N4 context
- N4 replay already requires an explicit `--trigger-context-run-id`, so downstream replay can bind to the intended context lineage without auto-selecting by trade_date

Policy:

1. Default context execute remains conservative and blocks if active context exists for the same trade date.
2. A later final gate may allow coexistence only with explicit `--allow-existing-context-for-trade-date`.
3. The target context run id remains deterministic:

   ```text
   trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
   ```

4. The same target run id must still be clean before execute.
5. Existing v1 context/replay rows are retained as historical evidence and are not superseded or rolled back by this gate.
6. Future N4 replay must explicitly pass the v4 `trigger_context_run_id`; it must not select context by `trade_date` alone.

## Runner / Artifact Changes

Modified runner:

- `scripts/run_trigger_context_snapshot_execute.py`

Change:

- added `--allow-existing-context-for-trade-date`
- default remains `false`
- the flag is passed to `run_trigger_context_snapshot_execute(...)`

Modified rollback generator:

- `src/ashare_v3/trigger/context_execute.py`

Change:

- generated rollback SQL now requires `ashare_v3.allow_n4_context_rollback_run_id`
- generated rollback SQL keeps hard-fail before first `DELETE`
- fixed the N4 outbox guard predicate with explicit parentheses:

  ```sql
  WHERE (source_layer = 'N4_trigger' AND source_run_id = v_run_id)
     OR payload_json::TEXT LIKE '%' || v_run_id || '%'
  ```

Modified tests:

- `tests/test_trigger_context_execute.py`

Coverage:

- CLI help exposes `--allow-existing-context-for-trade-date`
- default writer call keeps `allow_existing_context_for_trade_date=false`
- explicit flag passes `allow_existing_context_for_trade_date=true`
- rollback SQL generator includes hard-fail setting
- rollback SQL generator keeps N4 outbox guard parentheses

Updated artifacts:

- `docs/V3_20260616_N4_TRIGGER_CONTEXT_LOCALIZATION_FOR_CORRECTED_METRIC_V4_PREFLIGHT.md`
- `docs/V3_20260616_N4_TRIGGER_CONTEXT_LOCALIZATION_FOR_CORRECTED_METRIC_V4_PREFLIGHT.json`
- `sql/V3_20260616_N4_trigger_context_localization_for_corrected_metric_v4_rollback.sql`

## Rollback / Supersession Requirement

No v1 rollback or supersession is required for this policy.

Existing rows remain historical evidence:

- `trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- `v3_n4_trigger_replay_20260616_until_1401_v1`

Supersession would only be required if runtime_control decides the v1 lineage must no longer be considered valid evidence. That is a separate gate and must not be done silently here.

## Future Execute Command

The corrected v4 context localization final gate should use this explicit command:

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_context_snapshot_execute.py \
  --condition-run-id condition_layer_20260615_source_20260615_for_20260616_v4 \
  --for-trade-date 20260616 \
  --execute \
  --user-confirmed \
  --json-report-path docs/V3_20260616_N4_TRIGGER_CONTEXT_LOCALIZATION_FOR_CORRECTED_METRIC_V4_EXECUTE_REPORT.json \
  --markdown-report-path docs/V3_20260616_N4_TRIGGER_CONTEXT_LOCALIZATION_FOR_CORRECTED_METRIC_V4_EXECUTE_REPORT.md \
  --rollback-sql-path sql/V3_20260616_N4_trigger_context_localization_for_corrected_metric_v4_rollback.sql \
  --allow-existing-context-for-trade-date \
  --json
```

## Forbidden Scope Proof

This gate did not execute N4 context localization and did not write database rows.

- N4 context localization not executed
- N4 replay not executed
- no database writes
- no rollback executed
- no outbox / inbox / checkpoint consumption or update
- no N5 / N6 entry
- no scheduler / worker started
- no market pull
- no voice / mobile / sim / position / order / real trade
- old system untouched

## Validation

- targeted context tests: `26 OK`
- `scripts/check_n4_contract.py`: PASS
- policy / preflight JSON parse: PASS
- rollback static scan: PASS
- compileall touched files: PASS
- `git diff --check`: PASS

## Next Gate

`V3_20260616_N4_TRIGGER_CONTEXT_LOCALIZATION_FOR_CORRECTED_METRIC_V4_FINAL_GATE_REVIEW_RETRY`
