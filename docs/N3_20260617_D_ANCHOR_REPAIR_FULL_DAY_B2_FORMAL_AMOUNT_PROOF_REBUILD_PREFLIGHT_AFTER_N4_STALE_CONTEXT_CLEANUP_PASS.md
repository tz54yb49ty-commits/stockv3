# N3 20260617 D-Anchor B2 Formal Amount Proof Rebuild Preflight After N4 Cleanup

Result: `BLOCKED`

## Scope

- Layer: `N3_market_data`
- Source condition run: `condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- Subscription run: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- C1 source minute run: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- Planned B2 metric run: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- N4 cleanup artifact: `docs/N4_20260617_D_ANCHOR_REPAIR_STALE_CONTEXT_REF_TO_B2_CLEANUP_GATE_POST_REVIEW.json`

## Evidence

N4 stale context cleanup is PASS and live DB confirms the stale N4 refs are gone:

- `common_trigger_run_by_source_market_data_run_id=0`
- trigger quality/context/state/match rows for stale N4 run = `0`
- N5/action/position refs to the B2 metric = `0`
- outbox/inbox/ledger refs for B2 and stale N4 run = `0`

C1 full-day source remains valid:

- stock `441840` rows, `1841` identities, min/max rows per identity `240/240`, max label `15:00`
- index `19440` rows, `81` identities, min/max rows per identity `240/240`, max label `15:00`
- board `30480` rows, `127` identities, min/max rows per identity `240/240`, max label `15:00`
- excluded BJ identities remain `index:BJ:899050`, `index:BJ:899601`; C1 minute rows for both = `0`; C1 quality rows = `2`

Canonical distribution for included scope is full-scope and not hint-only:

| canonical type | rows | identities |
|---|---:|---:|
| BUY | 1939 | 1939 |
| SELL | 2021 | 2021 |
| BUY:FULL | 110 | 110 |
| SELL:FULL | 28 | 28 |
| BUY_HINT | 59 | 59 |
| SELL_HINT | 165 | 165 |

N2 policy is applied:

- Policy: `n2_formal_amount_required_periods_only_qy_gap_policy_v1`
- Required-period Q/Y missing rows and identities are `0` for stock/index/board pool and minute scope.
- Non-required Q/Y gaps remain quality-visible, not hard blockers.

## Blockers

`b2_target_not_clean_after_n4_cleanup`:

- `common_market_data_run=1`
- `common_market_data_quality_item=8`
- stock/index/board B2 metric rows = `1841/81/127`

`previous_day_same_window_source_absent`:

- stock previous rows `0/1841` identities
- index previous rows `0/81` identities
- board previous rows `0/127` identities

`existing_b2_metric_lacks_formal_amount_proof`:

- `previous_day_same_window_amount` non-null rows = `0/0/0`
- `current_d/w/m/q/y_virtual_amount` non-null rows = `0` for stock/index/board

## Decision

Do not execute B2. Do not enter N4/N5/N6.

The next allowed step is N3-only scoped cleanup plus previous-day source/preload gate, using:

- `sql/N3_20260617_d_anchor_repair_full_day_action_confirmation_metric_rollback.sql`
- `docs/N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_REBUILD_PREFLIGHT_AFTER_N4_STALE_CONTEXT_CLEANUP_PASS.json`

Allowed next prompt is recorded in the JSON artifact.
