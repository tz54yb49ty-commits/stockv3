# N6 Poller Automatic Batch One-shot Mode Supersession

```text
contract=N6-poller-automatic-batch-oneshot-mode-v1
layer_role=N6_user
automatic_projection=true
scheduler=LaunchAgent recurring one-shot
resident_process=false
interval_seconds=3
internal_batch_size=100
external_canary_batch_size=1
```

## 1. Supersession

This contract supersedes the N6 on-demand-only decision recorded in
`N6_POLLER_V4_ON_DEMAND_SINGLE_EVENT_MODE_SUPERSESSION.md`. It restores the
automatic N5-to-N6 projection consumer without changing N1, N2, N3, N4, or N5.

The recurring task is not a resident daemon. LaunchAgent starts one bounded
process every three seconds; the process handles at most one ordered batch and
then exits. `KeepAlive` and `RunAtLoad` remain false.

## 2. Exact implementation scope

```text
scripts/run_n6_b_track_signal_projection_poller_once.py
tests/test_n6_b_track_signal_projection_poller.py
scripts/plan_n6_b_track_signal_projection_launchd.py
tests/test_n6_b_track_signal_launchd_plan.py
docs/N6_POLLER_AUTOMATIC_BATCH_ONESHOT_MODE_SUPERSESSION.md
```

No N1-N5 production, test, schema, event, payload, or status file is in scope.
`common_event_outbox` is a read-only N5 source; N6 never updates its status or
consumption fields.

## 3. Runtime contract

`internal_one_shot` accepts `max_events=1..100`; the reviewed LaunchAgent fixes
it to `100`. `external_bounded_canary` accepts exactly one event. Zero, values
above 100, or external batches above one fail before repository construction,
database connection, singleton acquisition, or report writes.

The existing OS singleton, consumer-scoped PostgreSQL transaction advisory
lock, checkpoint `FOR UPDATE`, ordered whole-batch event CAS, and transaction
rollback remain mandatory. An unexpected inbox idempotency conflict is a batch
failure: run, projection, card, inbox, and checkpoint writes all roll back.

Invalid or not-ready projection-message contracts are written only to N6 inbox
audit and advance the checkpoint in order. They do not create projection/card
rows and do not block a later ready event in the same batch.

## 4. Projection-field boundary

N6 freezes `condition_projection_context` from the reviewed N5 message without
reading N2 tables or recalculating values. Version, status, hash, nullable
fields, not-ready reasons, and all context fields remain unchanged.

```text
buy target_price             <- fields.buy_target_price
sell target_price            <- fields.sell_target_price
buy expected_return_pct      <- fields.buy_expected_return_pct
sell expected_return_pct     <- fields.sell_expected_return_pct
trigger_price/trigger_pct    <- N5 message, unchanged
ActionEligible action fields <- null in N6 display payload
ActionExecuted action fields <- N5 message, unchanged
```

Stock `score` and `pe_core` remain available. Index and board display payloads
do not expose those keys.

Stock industry context is frozen only from `v_n6_board_membership_fact` where
`trade_date=condition_projection_context.source_trade_date` and
`board_type=tdx_industry`. Exactly one mapping is ready. Zero or multiple
mappings are `not_ready`; there is no fallback to display cache, N2/N5 tables,
or unreviewed payload industry fields.

## 5. LaunchAgent boundary

```text
label=com.ashare-v3.n6.b-track-signal-projection-batch-v1
StartInterval=3
KeepAlive=false
RunAtLoad=false
```

The plist must use an immutable, versioned tracked-tree release; the reviewed
read-only Python runtime environment; the absolute Fast Lane-maintained lineage
file; and absolute state paths for singleton, reports, history, and logs. The
old label, releases, plists, locks, staging paths, and incident evidence remain
preserve-only and disabled/unloaded.

## 6. Release, verification, and rollback

Release requires: code/test review; immutable release/plist/worker preflight;
then one natural-message external canary followed by a bounded automatic batch
postcheck. No synthetic event, replay, backfill, schema migration, or webpage
change is authorized.

Rollback is limited to disabling and booting out the new label, proving related
processes are zero, and retaining all release/plist/report/lock/projection
evidence. Checkpoints are never rewound, correct N6 rows are not deleted, and N5
outbox is never modified.
