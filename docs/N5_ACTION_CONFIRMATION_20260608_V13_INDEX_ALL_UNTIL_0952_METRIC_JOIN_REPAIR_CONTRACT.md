# N5 Action Confirmation 20260608 V13 Index-All Until 09:52 Metric Join Repair Contract

- gate: `N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_METRIC_JOIN_REPAIR_CONTRACT_GATE`
- layer_role: `runtime_control`
- contract_result: `BLOCKED`
- blocked_by_layer: `N3_market_data`
- blocker: `n3_action_confirmation_metric_missing_for_20260608_until_0952`

## Current Classification Proof

The current N5/N6 lineage is explicitly registered as eligibility-only:

| Field | Value |
|---|---:|
| lineage classification | `HINT_30M_ELIGIBILITY_ONLY` |
| N6 classification | `ELIGIBILITY_SHADOW_PROJECTION_ONLY` |
| ActionEligible | 119 |
| ActionExecuted | 0 |
| ActionBlocked | 0 |
| ActionSkipped | 0 |
| confirmation_status=pending | 119 |
| N6 user_signal_projection/card | 119 / 119 |
| user_notification_queue | 0 |

It must not be interpreted as metric-aware market action confirmation complete, final market action result, or an `ActionExecuted` result.

## Metric Source Discovery Result

Result: `MISSING`.

No 20260608 until 09:52 N3 action-confirmation metric run is available in the reviewed artifacts:

- `metric_run_id=""`
- `metric_rows=0`
- `joined_n4_rows=0`
- deterministic coverage=`0/119`
- `source_action_confirmation_metric_id_count=0`
- alignment review reports `n3_action_confirmation_metric_run_id_found_in_artifacts=false`
- docs filename search for `20260608` + action-confirmation metric artifacts returned 0 matches

Important distinction: `N3_B2 realtime_projection_metric_20260608_until_0952` exists, but it is N4 projection evidence, not the N5 120m/30m/5m/1m action-confirmation metric baseline.

Decision: metric-aware N5 dry-run/preflight/final gate is blocked until N3 provides an explicit action-confirmation metric `metric_run_id` and coverage proof.

## Metric Join Repair Requirements

Future N5 metric-aware gates must require:

- explicit `metric_run_id`, `action_metric_run_id`, or a reviewed baseline report carrying `metric_run_id`
- deterministic metric join coverage target=`119/119`
- `coverage=0/119` as P0 BLOCK
- missing metric rows > 0 as P0 BLOCK unless an explicit reviewed exclusion list exists
- `ActionExecuted` / `ActionBlocked` only from metric-aware confirmation
- `ActionEligible/pending` never marked as complete

The N5 runner/report path must expose:

- `metric_run_id`
- `metric_rows`
- `joined_n4_rows`
- `missing_n4_rows`
- coverage by asset kind
- derivation of `ActionExecuted` / `ActionBlocked` from N3 metric facts
- explicit eligibility-only classification if metrics are absent or incomplete

Dashboard and closeout artifacts must distinguish `HINT_30M_ELIGIBILITY_ONLY` from `METRIC_AWARE_ACTION_CONFIRMATION_COMPLETE`.

## Existing Eligibility Run Handling

Recommended route: `A_ROLLBACK_FIRST`.

Rollback order:

1. Roll back N6 eligibility shadow projection/card.
2. Roll back N5 eligibility-only action run.
3. After N3 metric readiness and N5 metric-aware final gate, regenerate and execute metric-aware N5/N6 with fresh run ids.

Reason: rollback-first keeps final lineage unambiguous, removes eligibility-only user projection/cards before metric-aware re-execute, and avoids dashboard/UI filtering ambiguity. Existing evidence shows no delivery, worker, sim, position, order, trade, or real-trade refs.

Alternative route: `B_SUPERSEDE_LINEAGE`.

This is allowed only after a separate supersede policy gate that defines a new metric-aware N5 run id, dashboard filtering, visible eligibility-only annotation, and rollback strategy for both lineages.

## Future Rollback Requirement

Future metric-aware N5 rollback must:

- hard-fail before first `DELETE` / `UPDATE`
- guard N5 outbox delivered/delivering
- guard downstream N6/user/delivery/push/voice/mobile/sim/order/trade/position/PnL refs
- delete only scoped metric-aware N5 rows
- preserve N4 trigger facts/outbox status
- preserve N3 metric and market facts
- preserve N2/N1 facts
- contain no `CASCADE`, `DROP`, or `TRUNCATE`

## Forbidden Scope Proof

- runtime_control executed command: `false`
- database written: `false`
- N5 execute performed: `false`
- action fact/event/outbox written: `false`
- N4/N5 outbox consumed or updated: `false`
- N5 inbox/checkpoint written: `false`
- N6 entered: `false`
- worker started: `false`
- rollback SQL executed: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Validation

- `source_json_parse`: `PASS`
- `eligibility_annotation_proof`: `PASS`
- `metric_gap_proof`: `PASS`
- `contract_json_parse`: `PASS`
- `git_diff_check`: `PASS`

## Required Follow-Up Gates

1. `N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_0952_READINESS_GATE`
2. `N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_0952_CONTRACT_GATE`
3. `N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_ELIGIBILITY_ONLY_ROLLBACK_CHAIN_GATE`
4. `N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_METRIC_AWARE_REGENERATION_GATE`

## Next Gate Recommendation

`N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_0952_READINESS_GATE`
