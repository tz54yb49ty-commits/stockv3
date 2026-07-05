# N3 Action Confirmation Metric Coverage Policy Next Trading Day Validation

## Gate

- stage: `N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_NEXT_TRADING_DAY_VALIDATION_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-06T16:48:13+08:00`
- result: `VALIDATION_PASS`
- validation kind: read-only artifact and live DB consistency check

This gate validates additive repair metric coverage feasibility for N5 action metric-union consumption. It does not execute N5/N6 repair and does not pull or write next-trading-day market data.

## Lineage

- N4 trigger run: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N3 original metric run: `action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N3 additive repair metric run: `action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`

## Artifact Proof

N3 additive repair artifacts are present and JSON-parseable:

- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_CONTRACT.json`
- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_PREFLIGHT.json`
- `docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_DRY_RUN.json`
- `docs/N3_action_confirmation_metric_coverage_policy_repair_payload.json`
- `sql/N3_action_confirmation_metric_coverage_policy_repair_20260605_rollback.sql`

N5 metric-union artifacts are present and JSON-parseable:

- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.json`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.json`
- `docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DEFER_REGISTRATION.json`
- `docs/N3_N5_METRIC_COVERAGE_REPAIR_DEFER_CLOSEOUT.json`

Artifact values:

- N4 TriggerMatched universe: `605`
- original metric rows: `316`
- additive repair rows: stock/index/board/total = `256/0/5/261`
- repaired total coverage: stock/index/board/total = `572/0/5/577`
- remaining excluded: stock/index/board/total = `0/0/28/28`
- remaining excluded reason: `board_lineage_missing`
- duplicate vs original metric: `0`
- duplicate inside repair payload: `0`

## Live DB Read-Only Proof

DB connection was opened with `default_transaction_read_only=on`; only `SELECT` statements were used.

N4 TriggerMatched universe:

- stock: `572`
- index: `0`
- board: `33`
- total: `605`

N3 metric runs:

- original metric run status: `passed`, P0/P1/P2=`0/2/0`, rows=`316`
- additive repair metric run status: `passed`, P0/P1/P2=`0/2/0`, rows=`261`

Metric rows by table:

- original: stock/index/board/total = `316/0/0/316`
- additive repair: stock/index/board/total = `256/0/5/261`

Union join proof:

- N4 rows: `605`
- joined rows: `577`
- missing rows: `28`
- duplicate join rows: `0`
- duplicate metric join-key groups: `0`

Additive repair downstream refs:

- `common_action_event`: `0`
- `common_event_outbox`: `0`
- `user_signal_projection`: `0`
- `user_signal_card`: `0`
- `user_notification_queue`: `0`

## N5 Action Union Feasibility

The additive repair metric rows are feasible for N5 deterministic metric-union consumption:

- dry-run result: `DRY_RUN_PASS`
- contract result: `CONTRACT_PASS`
- deterministic join coverage: `577/605`
- missing rows after union: `28`
- duplicate join key count: `0`
- planned ActionExecuted: `1`
- planned ActionBlocked: `604`
- planned ActionEligible: `0`
- planned ActionSkipped: `0`

Remaining excluded rows stay excluded because board minute lineage is missing. No fallback, raw K reconstruction, or opaque payload inference is allowed.

## Artifact And Live Consistency

- N4 universe consistent: `true`
- original metric rows consistent: `true`
- additive repair metric rows consistent: `true`
- union coverage consistent: `true`
- remaining missing consistent: `true`
- duplicate join-key status consistent: `true`

## Forbidden Scope Proof

This validation did not:

- write database rows
- execute N5 repair
- update `common_action_event`
- update N5 outbox
- update N6 projection/card/UI
- consume or update outbox
- consume or update inbox/checkpoint
- start workers
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade
- pull or write next-trading-day market data

## Validation

- artifact existence check: `passed`
- JSON parse: `passed`
- live DB read-only select: `passed`
- report JSON assertion: `passed`
- git diff check: `passed`

## Next Gate

`WAIT_FOR_NEXT_TRADING_DAY_RUNTIME_INPUT_OR_N3_BOARD_LINEAGE_EXPANSION_GATE`
