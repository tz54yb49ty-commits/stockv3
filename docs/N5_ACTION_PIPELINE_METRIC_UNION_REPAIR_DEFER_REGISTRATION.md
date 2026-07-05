# N5 Action Pipeline Metric-Union Repair Defer Registration

## Gate

- stage: `N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DEFER_REGISTRATION_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-06T16:36:16+08:00`
- decision: `DEFERRED`
- result: `DEFER_REGISTRATION_PASS`

## Decision Summary

This gate registers the decision to defer N5 metric-union repair execution. The N3 coverage additive repair is preserved, and the N5 metric-union dry-run/contract evidence is archived, but no N5 action rows, N5 outbox rows, or N6 projection/card/UI rows are rewritten in this gate.

## Source Context

N3 coverage additive repair:

- original metric rows: `316`
- additive repair rows: `261`
- union metric rows: `577`
- missing after union: `28`
- remaining excluded reason: `board_lineage_missing`

N5 metric-union repair dry-run/contract:

- N4 input rows: `605`
- deterministic join coverage: `577/605`
- missing rows: `28`
- duplicate join key count: `0`
- ActionExecuted: `1`
- ActionBlocked: `604`
- ActionSkipped: `0`
- ActionEligible: `0`
- P0/P1/P2: `0/0/0`

## Value Assessment

The N5 metric-union repair is valid and improves explanation quality, but it does not change the market action confirmation result:

- old ActionExecuted: `1`
- new ActionExecuted: `1`
- old ActionBlocked: `604`
- new ActionBlocked: `604`

The changed surface is blocked-reason metadata. The repair reduces `metric_missing` rows from `289` to `28` and reclassifies 261 previously missing-metric blocked rows into deterministic market-confirmation failures.

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

## Reason For Defer

- `ActionExecuted` count is unchanged at `1`.
- `ActionBlocked` count is unchanged at `604`.
- The repair improves `blocked_reason` metadata but does not change the user-visible market action confirmation outcome.
- Executing the N5 repair would rewrite N5 action/event/outbox payloads and then require a separate N6 projection/card/UI refresh for a lineage that has already been closeout reviewed.
- Current benefit is better classified as a deferred metadata correction rather than a required historical rewrite.
- The upstream N3 additive metric repair remains valuable and should be validated on the next trading day before deciding whether to rewrite downstream historical N5/N6 rows.

## Preserved Artifacts

- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.md`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.json`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.md`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.json`

## Next Gate

`N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_NEXT_TRADING_DAY_VALIDATION_GATE`

## Optional Future Gates

- `N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_EXECUTE_GATE`
- `N6_PROJECTION_CARD_REPAIR_FOR_N5_METRIC_UNION_GATE`
- `N3_BOARD_LINEAGE_EXPANSION_GATE`

## Forbidden Scope Proof

This registration gate did not:

- write database rows
- execute N5 repair
- update `common_action_event`
- update N5 outbox
- enter N6
- update projection/card/UI rows
- consume or update outbox/inbox/checkpoint
- start workers
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Validation

- source artifact existence check: `passed`
- source JSON parse: `passed`
- registration JSON parse: `passed`
- forbidden scope assertion: `passed`
- git diff check: `passed`
