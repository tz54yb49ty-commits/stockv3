# V3 Phase 1 N4 Replay Bounded Worker Contract

## Scope

PR-3 adds the N4 replay bounded worker wrapper only:

```text
scripts/run_n4_replay_bounded_worker_once.py
  -> scripts/run_trigger_action_confirmation_metric_once.py
  -> src/ashare_v3/trigger/action_confirmation_metric_execute.py replay path
```

This is the active path for Phase 1 N4 replay. The wrapper does not use
`src/ashare_v3/trigger/worker_consumer.py`, does not use
`scripts/run_n4_worker_bounded_poll_once.py`, and does not consume N3 outbox
events as its active path. The bounded poll/smoke consumer remains deferred.

There is no SQL migration in PR-3.

## Lineage

All lineage is explicit and supplied by CLI:

```text
for_trade_date
source_metric_run_id
projection_run_id
context_run_id
source_condition_run_id
source_subscription_run_id
source_snapshot_run_id
trigger_run_id
```

`source_metric_run_id` must equal `projection_run_id`. Values such as
`latest`, `active`, `fallback`, `auto`, and `auto-resolve` are rejected before
the child replay command can be built.

## Guardrails

The wrapper estimates `candidate_total` before replay. If
`candidate_total > max_candidates`, the result is `BLOCKED`, the child is not
invoked, and N4 business writes remain zero. The wrapper does not implement
pagination, batching, replay `LIMIT`, or silent partial processing.

Scope coverage is checked at this grain:

```text
asset_kind + identity_key + direction + condition_key
```

Expected scope comes from authoritative N4 context. Actual scope comes from N3
action-confirmation projection metrics. Missing keys are grouped by
`condition_key` with counts and samples. HINT-only expected scope may pass with
complete HINT actual coverage. Ordinary/FULL expected scope cannot pass when
actual coverage is HINT-only.

PR-3 exposes an injectable coverage provider for tests and later production
wiring. Without an authoritative provider, the wrapper fails closed and does
not claim production DB coverage is wired.

## Runtime Result Contract

The wrapper uses the shared Phase 1 realtime chain lock path from
`build_phase1_realtime_chain_lock_path(repo_root, trade_date)`. The path is the
same chain-level lock used by N3 and is not N3/N4/N5-specific.

The shared global lock protects only Phase 1 bounded wrappers that follow this
contract. Legacy or direct entrypoints can bypass the global lock, including
directly running `scripts/run_trigger_action_confirmation_metric_once.py`,
`scripts/run_n4_worker_bounded_poll_once.py`,
`src/ashare_v3/trigger/worker_consumer.py`, or manual SQL. The Phase 1 runbook
must prohibit these legacy/direct entrypoints and manual SQL from running in
parallel with the PR-3 wrapper. They must not run in parallel.

Default mode is plan-only and never invokes the child. Replay can start only
with both:

```text
--execute --user-confirmed
```

The child replay is one transaction. PR-3 has no `PARTIAL` result. Timeout or
commit/report ambiguity returns `UNKNOWN_AFTER_TIMEOUT` or `COMMIT_UNKNOWN`
with `requires_post_check=true`; the wrapper does not retry and does not run
rollback.

PASS requires:

```text
child exit 0
valid child report
report trigger_run_id matches requested trigger_run_id
rollback SQL exists
rollback SQL sha256 recorded
```

Rollback SQL missing cannot PASS. If the child already started, the wrapper
fails closed through post-check classification.

## Event Contract

Manifest and status record counts for:

```text
TriggerMatched
TriggerStateChanged
TriggerPendingMarketData
```

`TriggerMatched` is the only future N5 action-confirmation entry event.
`TriggerStateChanged` is state broadcast only and does not write
`common_trigger_match`. `TriggerPendingMarketData` is no-op/quality/state-gate
only and does not write `common_trigger_match`.

If the replay path produces no pending event, the pending count is recorded as
zero.

## Downstream Gate

`downstream_consumption_allowed` and `n5_consumption_allowed` are true only when
the wrapper result is `PASS`. They are false for candidate overflow, scope
coverage failure, singleton lock NOOP, stop-file NOOP, timeout, crash, and
commit-unknown outcomes.

PR-3 does not write N5, N6, action, trade, sim, voice, mobile, worker state, N3
inbox/checkpoint, or N3 outbox consumption state.
