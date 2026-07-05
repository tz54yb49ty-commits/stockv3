# N1-N5 Current Completion Analysis Plan

Updated: 2026-06-02

Layer role: `runtime_control`

Scope: analysis and planning only. This document does not authorize implementation, database writes, N1-N6 execute, outbox consumption, worker startup, rollback execution, or downstream delivery.

## 1. Completion Summary

These percentages are engineering readiness estimates based on the current control docs, run artifacts, dashboard state, and rollback registry. They are not formal coverage percentages.

| Layer | Current Estimate | Current State |
|---|---:|---|
| N1 ingestion / official source | 92% | Core ingestion and canonical source lineage are mature; remaining work is operational hardening, archive closure, and known official daily gaps. |
| N2 condition | 96% | Canonical condition layer is effectively complete; latest active lineage and target-price/display-scope alignments are passed. |
| N3 market data | 78% | Subscription, snapshot, minute, and action-confirmation projection run-once paths are proven; latest N2 v6 subscription rebuild is no longer P0 after read-only evidence showed old N3 is aligned; remaining work is display/closed-minute paths, replay, archive handoff, runbook, and worker readiness. |
| N4 trigger | 80% | Action-confirmation metric trigger execute passed; remaining work is replay coverage, worker/bounded smoke, delivery lifecycle, and future lineage rebuild alignment. |
| N5 action | 83% | Action-confirmation metric action execute passed and N6 shadow projection consumed its pending outbox read-only; remaining work is delivery/status lifecycle, worker smoke, replay, and downstream policy gates. |

## 2. N1 Completion: 92%

Completed / stable:
- Physical stock/index/board ingestion model and common metadata are established.
- Official source, source version, quality, rollback, and audit conventions are in place.
- Canonical financial / daily lineage has passed recent gates.
- N1 remains the upstream authority for historical facts and archive handoff.

Missing / not yet fully closed:
- The 20260525 official daily gap / N3-EOD blocker is a historical item and is currently closed for the reviewed 300327 case: official daily proof exists and no longer blocks the N1 -> N2 -> N3 -> A1 mainline.
- Runtime archive lifecycle is not fully productionized end to end: sealed N3 runtime partition -> archive request -> Parquet/manifest -> cleanup.
- Long-term operational SOP for recurring official daily ingestion still needs final proof across multiple cycles.
- Historical repair/backfill queue is not fully automated.

Recommended next N1 gates, only if user chooses N1 work:
- N1 official daily historical blocker audit only if a new date or object is reported; 20260525 / 300327 is not a current P0.
- N3 sealed runtime archive request review.
- Archive manifest and rollback-readiness gate.

## 3. N2 Completion: 96%

Completed / stable:
- Latest active condition lineage is passed and active.
- Canonical signal rules are frozen: N2 emits condition semantics only, not runtime action semantics.
- Display scope alignment, target-price compatibility, secondary anchor, level score, and related canonical target-price gates have passed.
- N2 keeps `condition_key` as trace/audit/analytics and does not treat it as runtime `signal_type`.
- N2 does not write N3/N4/N5/N6 facts and does not pull行情.

Missing / not yet fully closed:
- Downstream rebuilds may still be on older N2 lineage in some historical artifacts; this is a downstream rebuild issue, not an N2 compute blocker.
- Policy/UI editing for condition pool and minute scope remains future work.
- Recurring multi-day regression and dashboard display for every N2 variant can be improved.
- Some legacy alias compatibility paths still require ongoing audit.

Recommended next N2 gates, only if user chooses N2 work:
- Read-only N2 active lineage audit against all downstream branches.
- N2 policy registry / display policy documentation gate.
- N2 regression report refresh for latest active lineage.

## 4. N3 Completion: 78%

Completed / stable:
- 20260602 action-confirmation chain closure confirms N3 subscription, A1 previous-day preload, B1 live3 snapshot, C1 today minute, and action-confirmation projection passed.
- Action-confirmation projection schema, writer, execute report, rollback, and dashboard detection are in place.
- N3 projection facts are used by N4/N5 instead of raw minute recomputation.
- Rollback registry is complete for the 20260602 action-confirmation run-once chain.
- Runtime dashboard v0.2 detects N3 action-confirmation timeline stages from docs artifacts.

Missing / not yet fully closed:
- Latest N2 lineage downstream coverage is not universal across all historical paths, but current read-only evidence shows the existing 20260601 N3 subscription already matches N2 v6 and is not a P0 rebuild blocker.
- N3 display / low-frequency market projection path is still not fully advanced to delivery.
- Closed-minute / closed-30m replay and C2/C3 paths are not fully productionized.
- N3 outbox delivery and consumption lifecycle remains separate from run-once fact writes.
- Bounded worker smoke and long-running worker readiness are not yet complete.
- N3 runtime archive handoff to N1/archive is not fully closed.

Recommended next N3 gates, only if user chooses N3 work:
- N1 -> N2 -> N3 -> A1 pipeline runner / runbook gate, focused on repeatable operator flow and lineage checks.
- N3 subscription rebuild for latest N2 v6 is currently non-P0 and execute is cancelled unless a new concrete data mismatch appears.
- N3 closed-minute / closed-30m dry-run and preflight gate.
- N3 display snapshot path review.
- N3 bounded worker smoke gate, separately authorized.

## 5. N4 Completion: 80%

Completed / stable:
- N4 action-confirmation metric dry-run, preflight, execute runner, rollback, and business execute have passed for the 20260602 chain.
- N4 consumes N3 standard action-confirmation metric facts.
- N4 no longer recomputes raw minute indicators for this path.
- N4 output for the 20260602 path is scoped to trigger run/state/match/outbox, with no N5/N6 writes.
- Runtime dashboard v0.2 detects the N4 stage as PASS.

Missing / not yet fully closed:
- N4 bounded worker smoke and long-running worker readiness are still pending.
- Event delivery lifecycle is not enabled by default; N4 outbox remains pending unless an explicit downstream gate consumes it.
- Replay coverage and closed-minute confirmation path are not fully productionized.
- Future N2/N3 rebuilds need corresponding N4 contract/preflight refresh.
- Broader negative-case / failure-mode regression can be expanded.

Recommended next N4 gates, only if user chooses N4 work:
- N4 read-only replay / closed-minute contract review.
- N4 bounded worker smoke gate, explicitly separated from long worker.
- N4 rollback-readiness audit for current and rebuilt lineages.

## 6. N5 Completion: 83%

Completed / stable:
- N5 action-confirmation metric runner alignment passed.
- N5 uses `TriggerMatched` as the only action-confirmation entry.
- N5 joins N3 standard action-confirmation metric facts and treats opaque `payload.action_confirmation` as trace-only.
- N5 metric-aware dedup merges same-minute / same-metric multi-condition-key grains.
- 20260602 N5 execute passed with `ActionExecuted=4` and `ActionBlocked=1`.
- N6 shadow projection has consumed the N5 events as a shadow projection without updating N5 outbox status.
- Rollback SQL has hard-fail guards for outbox delivery, downstream refs, and user/sim/voice/mobile/position refs.

Missing / not yet fully closed:
- N5 outbox delivery/status lifecycle has not been executed; current N5 events remain pending.
- N6 delivery, notification, push/voice/mobile/sim/position/real-trade policy remains separate and not executed.
- N5 bounded worker smoke and long-running worker readiness are pending.
- Replay / repeated-run idempotency proof can be expanded beyond current run-once path.
- Future rebuilt N4/N3 lineages require a new N5 contract/preflight/rollback gate.

Recommended next N5 gates, only if user chooses N5 work:
- N5 outbox delivery/status lifecycle design review, without execution.
- N5 bounded worker smoke gate, explicitly scoped.
- N5 replay/idempotency dry-run gate.

## 7. Cross-Layer Gaps

Current 20260602 run-once chain is closed to N6 shadow, but the following scopes remain intentionally not executed:
- N5 outbox delivery / status update.
- N6 notification delivery, push, voice, mobile, sim, position, real trade.
- Any worker or long-running consumer.
- Cross-day recurrence / nightly automation beyond read-only runtime dashboard detection.
- Runtime dashboard action-confirmation detector currently covers the 20260602 artifact chain; broader dates need explicit detector extension.

Closed / disproven items from the 20260602 read-only audit:
- `old N3 subscription missing 300327` is disproven. The old run `market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6` contains `stock:SZ:300327` with `realtime_daily_snapshot` and traces to N2 v6 scope/pool ids.
- `old N3 subscription inconsistent with N2 v6` is disproven. Re-planning from `condition_layer_20260529_source_20260529_v6` produced 3319 subscription keys, and the old N3 run has the same 3319 keys with missing=0 and extra=0.
- `20260525 official daily gap blocks N3-EOD` is historical and closed for the reviewed blocker: 300327 official daily proof exists for 20260525 and 20260529, and N2 v6 references it correctly.
- `N3 subscription rebuild for latest N2 v6` is no longer P0. Execute is cancelled for now; keep the prepared rollback SQL/registry only as optional evidence if a future explicit rebuild gate is revived.

Current mainline recommendation:
- Build a read-only-first N1 -> N2 -> N3 -> A1 pipeline runner / runbook that standardizes source lineage checks, subscription/A1 preflight checks, rollback registry checks, and stop-lines. This is the next useful mainline artifact because the data mismatch that motivated rebuild has been disproven.

## 8. Recommended Confirmation-Gated Routes

Choose one route before implementation begins:

1. Runtime control maintenance:
   - read-only lineage/dashboard review
   - dashboard detector generalization for more dates
   - release-note / rollback registry audit

2. N3 rebuild path:
   - currently paused / non-P0 after read-only audit showed old N3 matches latest N2 v6
   - revive only if a new concrete subscription key mismatch, missing object, or lineage policy requirement appears
   - closed-minute / closed-30m projection gate
   - no worker unless separately authorized

3. N1 -> N2 -> N3 -> A1 mainline runbook path:
   - pipeline runner / runbook contract
   - read-only source lineage and rollback registry checks
   - subscription and A1 preflight sequencing
   - no execute without separate layer gate

4. N5/N6 downstream path:
   - N5 outbox delivery contract review
   - N6 notification policy dry-run
   - no push/voice/mobile/sim/position/real trade unless separately authorized

5. Worker readiness path:
   - bounded worker smoke only
   - no long-running worker without separate confirmation

6. N1 operations path:
   - official daily blocker closure only for newly discovered gaps; 20260525 / 300327 is closed
   - archive handoff and manifest review

## 9. Stop Line

Until the user confirms a specific gate:

```text
code_change = false
database_write = false
migration_execute = false
N1-N6 execute = false
rollback_execute = false
outbox_consumption = false
outbox_status_update = false
worker_started = false
push/voice/mobile/sim/position/real_trade = false
old_system_touched = false
```
