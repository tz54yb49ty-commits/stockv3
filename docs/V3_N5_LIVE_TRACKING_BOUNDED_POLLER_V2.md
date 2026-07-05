# V3 N5 Live Tracking Bounded Poller v2

## Scope

This contract defines the N5-only live tracking bounded one-shot poller.
It leaves the existing Phase 1 bounded wrapper unchanged.

The runner is invoked repeatedly by an external scheduler or operator. It is
not a long-running worker and it does not change launchd configuration.

## CLI Contract

Required arguments:

- `--for-trade-date`
- `--source-trigger-run-id`
- `--source-metric-run-id`
- `--action-run-id`
- `--consumer-name`
- `--max-events`
- `--max-runtime-seconds`

Execution writes are allowed only when both flags are present:

- `--execute`
- `--user-confirmed`

Without `--execute`, the runner is plan-only. With `--execute` but without
`--user-confirmed`, the runner is blocked before planning or writing.

`action_run_id` is stable across repeated one-shot invocations for the same
trade date and source trigger run. Each invocation has a separate invocation id.

## Inputs

The only N4 input events are pending rows from `common_event_outbox`:

- `TriggerMatched`: action entry.
- `TriggerStateChanged` with `trigger_live=false`: active tracking exit only.

`TriggerPendingMarketData` is not an action entry for this poller.
`TriggerStateChanged` never creates action confirmation.

The poller reads N3T action-confirmation metric rows by explicit
`source_metric_run_id`. N5 does not pull market data and does not assemble
confirmation indicators from lower-level intraday bars.

`ActionExecuted` requires the selected metric row to prove:

```text
source_basis=N3T_C1_CLOSED
```

N3P/B1/B2/realtime_action_confirmation_metric lineage is trace-only and must
fail closed for `ActionExecuted` with
`BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF` or `BLOCKED_N3T_METRIC_REQUIRED`.
`ActionEligible` from a valid `TriggerMatched` remains allowed.

## Tracking Grain

The active list grain is:

```text
trade_date + asset_kind + identity_key + direction + signal_type + condition_key
```

The tracking key uses the existing N5 action tracking state key helper. The same
object with a different `condition_key` is tracked independently.

## Active Scope Snapshot Artifact

The plan must include an N5-owned active scope snapshot artifact for
runtime_control to pass explicitly to scoped N3-C1 / N3T gates. The artifact is
plan output only; this contract does not write the artifact to DB and does not
write N3/N4/N6 rows.

Required artifact row grain:

```text
for_trade_date
asset_kind
identity_key
direction
signal_type
condition_key
source_trigger_event_id
source_trigger_run_id
scope_status=active
```

Scope entry can come only from read-only N4 pending `TriggerMatched` intake.
Scope removal happens when the same grain reaches `ActionExecuted` or when N5
observes `TriggerStateChanged(trigger_live=false)`.

Empty scope must produce an explicit no-op artifact with
`empty_scope_noop=true`. Missing or empty scope must not fall back to full-market
pull or full-market processing. N3 must consume only the explicit artifact /
scoped input and must not scan N5 internal tracking, inbox, checkpoint, or
outbox tables.

Artifact boundary flags must remain false:

```text
full_market_fallback_allowed
n3_scans_n5_internals
db_write_allowed
n4_outbox_status_update_allowed
updates_n4_outbox
```

## Output Events

For this poller, N5 outbox output to N6 is limited to:

- `ActionEligible`
- `ActionExecuted`

Internal tracking can record pending or expired state, but this poller does not
emit `ActionBlocked` or `ActionSkipped` to N6.

On the first valid `TriggerMatched`, N5 creates or updates active tracking and
emits one `ActionEligible`:

- `action_mark=null`
- `confirmation_status=pending`

If final confirmation passes in the same invocation, the transaction emits
`ActionEligible` first and `ActionExecuted` second.

When a later invocation confirms an active tracking row, N5 emits one
`ActionExecuted`, writes final `action_mark`, and marks tracking executed.

When `TriggerStateChanged(trigger_live=false)` is received for active tracking,
N5 marks the tracking row expired and emits no N6 event.

## Final Confirmation

N5 evaluates the N3T standard metric for 120m, 30m, 5m, and 1m confirmation.
Missing, unready, or not-passed metric evidence keeps active tracking alive
while the trigger is still live and emits no `ActionBlocked`.

## Action Mark

N5 treats N4 `trigger_mark_candidate` and projection candidate fields as trace
only. N5 owns final `action_mark`.

Final values:

- `normal`
- `30m_volume`
- `30m_shrink`

Rules:

- `B_BUY` plus `current_30m_virtual_amount > previous_day_same_window_amount`
  plus buy 30m price confirmation passes -> `30m_volume`.
- `S_SELL` plus `current_30m_virtual_amount < previous_day_same_window_amount`
  plus sell 30m price confirmation passes -> `30m_shrink`.
- Otherwise, if all final confirmations pass -> `normal`.

If `previous_day_same_window_amount` is missing, `ActionExecuted` can still pass,
but final `action_mark` must be `normal` and the reason must be
`previous_day_same_window_amount_missing`.

Pending, blocked, skipped, or expired tracking state must not write a final
`action_mark`; it can only retain candidate trace.

## Persistence Boundary

Plan-only mode performs no writes.

Execute mode writes only N5-owned rows:

- `common_action_tracking_state`
- `common_event_outbox` with `source_layer=N5_action`
- `common_event_inbox` for the N5 consumer
- `common_event_consumer_checkpoint` for the N5 consumer

Execute mode must not update N4 outbox rows. N4 rows remain pending/delivered
according to their own layer policy; N5 idempotency is tracked through N5 inbox
and checkpoint rows.

No N3, N4, or N6 facts are written. No market fetch, launchd mutation, worker
daemon, voice, mobile, sim, or trade execution is part of this contract.

## Rollback Contract

Rollback scope is N5-only and must be filtered by `action_run_id` and
`consumer_name`.

Allowed rollback targets:

- N5 consumer checkpoints whose payload references `action_run_id`.
- N5 inbox rows for `consumer_name` whose raw payload references `action_run_id`.
- N5 outbox rows where `source_layer='N5_action'` and
  `source_run_id=action_run_id`.
- N5 tracking rows where `run_id=action_run_id`.

Rollback must not delete or update N4 outbox rows, N3/N4 facts, N6 user rows,
launchd files, or old-system artifacts.
