# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Archive / Supersession Registration

Result: `REGISTRATION_PASS`

This runtime_control gate only registers archive and supersession status for the N6 shadow projection/card unified output retry. It did not execute N6, write the database, consume or update N5 outbox, start a worker, execute rollback SQL, deliver push/voice/mobile output, create proposal/order/trade rows, update sim/position/PnL, touch real trade, or touch the old system.

## Current Authority Decision

Decision: `current_closed_shadow_projection`

Current run:

- user_projection_run_id: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- source_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- scope: 20260608 until 15:00 N6 shadow projection/card
- status: `passed`
- input/output: `556 / 556`
- closeout: `CLOSEOUT_PASS`

Live readonly DB scan found no later `user_projection_run` for the same `20260608 until_1500` N6 projection scope after the current run.

## Archive / Supersession Status

Archive status: `closed_current`

The current unified output retry run supersedes the earlier formal snapshot fallback metric-aware retry projection:

- superseded run: `user_projection_shadow_20260608_until_1500_formal_snapshot_fallback_metric_aware_retry__action_consumer_execute_20260608_until_1500_formal_snapshot_fallback_metric_aware_retry`
- reason: the unified output retry is the later closed N6 projection/card run for the same 20260608 until 15:00 scope and source lineage family.

No `superseded_by` run is registered for the current unified output retry run. Earlier artifacts remain historical evidence.

## N5 Outbox Boundary

The N5 outbox remains pending and was not consumed or updated by this N6 projection:

| event_type | pending |
|---|---:|
| `ActionExecuted` | 7 |
| `ActionBlocked` | 549 |

- delivered / delivering: `0 / 0`
- consumed: `false`
- status updated: `false`
- not registered as delivery, voice, mobile, sim, position, PnL, order, trade, or real trade

## Rollback Registry

Rollback SQL: `sql/N6_projection_20260608_until_1500_unified_output_retry_rollback.sql`

- purpose: emergency scoped rollback only
- rollback executed: `false`
- scoped by `user_projection_run_id`
- hard-fails before first executable `DELETE`
- delete order: `user_notification_queue`, `user_signal_card`, `user_signal_projection`, `user_projection_run`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- preserves N5/N4/N3/N2/N1

## Forbidden Scope Proof

- N6 execute performed in this gate: `false`
- database write performed: `false`
- N5 outbox consumed or updated: `false`
- worker started: `false`
- rollback executed: `false`
- delivery / push / voice / mobile touched: `false`
- sim / position / PnL / real trade touched: `false`
- proposal / order / trade touched: `false`
- old system touched: `false`

## Docs Update Summary

No update was made to `docs/Architecture.md`, `docs/Roadmap.md`, or `docs/Tasks.md` in this gate. The archive/supersession decision is registered in this dedicated artifact; broad status documents were left unchanged to avoid promoting live DB row counts into a general canonical status summary.

## Validation

- source artifact JSON parse: `PASS`
- live DB supersession scan: `PASS`
- N5 outbox boundary check: `PASS`
- rollback static check: `PASS`
- registration JSON parse: `PASS`
- `git diff --check`: `PASS`

Next recommended gate: `N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_LINEAGE_DASHBOARD_OR_READONLY_HANDOFF_GATE`.
