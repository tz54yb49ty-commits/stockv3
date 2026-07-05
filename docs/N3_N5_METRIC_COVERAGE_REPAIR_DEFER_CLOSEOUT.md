# N3/N5 Metric Coverage Repair Defer Closeout

## Gate

- stage: `N3_N5_METRIC_COVERAGE_REPAIR_DEFER_CLOSEOUT_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-06T16:40:58+08:00`
- result: `CLOSEOUT_PASS`
- decision: N3 additive metric repair preserved; N5 metric-union repair deferred

## N3 Additive Repair Summary

N3 coverage policy repair has completed as an additive repair:

- original metric rows: `316`
- additive repair rows: `261`
- union coverage: `577/605`
- union metric rows: `577`
- remaining missing: `28`
- remaining missing reason: `board_lineage_missing`
- duplicate vs original metric: `0`
- duplicate inside repair payload: `0`

Quality state:

- P0/P1/P2: `0/2/0`
- accepted exception scope: remaining board lineage-missing rows stay quality-visible and excluded; N3 does not mutate N4 payload metric ids.

## N5 Metric-Union Deferred Summary

N5 metric-union repair dry-run and contract passed, but execution is deferred:

- dry-run result: `DRY_RUN_PASS`
- contract result: `CONTRACT_PASS`
- N4 input rows: `605`
- deterministic join coverage: `577/605`
- remaining missing: `28`
- duplicate join key count: `0`
- P0/P1/P2: `0/0/0`

Action conclusion comparison:

- ActionExecuted old/new: `1/1`
- ActionBlocked old/new: `604/604`
- ActionSkipped old/new: `0/0`
- ActionEligible old/new: `0/0`

The repair would not change the user-visible market action confirmation conclusion. It would only improve blocked-reason metadata.

## Blocked Reason Comparison

Old distribution:

- `price_confirmation_failed`: `305`
- `metric_missing`: `289`
- `amount_confirmation_failed`: `10`

New distribution:

- `price_confirmation_failed`: `559`
- `metric_missing`: `28`
- `amount_confirmation_failed`: `17`

Transitions:

- `metric_missing -> price_confirmation_failed`: `254`
- `metric_missing -> amount_confirmation_failed`: `7`
- `ActionBlocked -> ActionBlocked`: `261`

## Defer Rationale

- `ActionExecuted` remains `1`.
- `ActionBlocked` remains `604`.
- The change is limited to blocked-reason metadata explanation quality.
- Executing the N5 repair would rewrite historical N5 `common_action_event` / N5 outbox payloads.
- A separate N6 projection/card/UI refresh would then be required for an already closeout-reviewed display lineage.
- Current benefit is not sufficient to immediately rewrite historical N5/N6 outputs.

## Preserved Artifacts

N3 repair:

- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_CONTRACT.json`
- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_PREFLIGHT.json`
- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_DRY_RUN.json`
- `docs/N3_action_confirmation_metric_coverage_policy_repair_payload.json`
- `sql/N3_action_confirmation_metric_coverage_policy_repair_20260605_rollback.sql`

N5 metric-union:

- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.md`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.json`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.md`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.json`

N5 defer registration:

- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DEFER_REGISTRATION.md`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DEFER_REGISTRATION.json`

## Forbidden Scope Proof

This closeout did not:

- execute N5 repair
- write database rows
- update `common_action_event`
- update N5 outbox
- update N6 projection/card/UI
- consume or update outbox
- consume or update inbox/checkpoint
- start workers
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Next Gate

`N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_NEXT_TRADING_DAY_VALIDATION_GATE`

## Validation

- preserved artifact existence check: `passed`
- JSON parse: `passed`
- closeout JSON assertion: `passed`
- forbidden scope assertion: `passed`
- git diff check: `passed`
