# N6 Poller V4 On-Demand Single-Event Mode Supersession

```text
contract=N6-poller-v4-on-demand-single-event-mode-supersession-v1
gate=N6_POLLER_V4_ON_DEMAND_SINGLE_EVENT_MODE_SUPERSESSION_GATE
layer_role=N6_user
status=EFFECTIVE_CONTRACT_REGISTERED
effective_mode=ON_DEMAND_SINGLE_EVENT_ONLY
resident_worker=false
launchagent_reactivation=false
automatic_projection=false
```

## 1. Purpose and effective decision

This artifact is the single effective successor to the unfinished resident-worker release chain for
the N6 B-track signal projection poller. The reviewed incremental projector remains available only
as an explicitly authorized, single-event, run-once command.

The user-facing behavior is frozen as follows:

```text
existing_8786_projection_rows_remain_readable=true
new_n5_events_projected_automatically=false
new_n5_events_projected_only_after_explicit_user_authorization=true
maximum_events_per_authorization=1
invalid_or_not_ready_event_stops_after_one=true
automatic_continue_to_next_ready_event=false
```

The poller is an N5-to-N6 materializer. It is not the 8786 web server, does not bypass PostgreSQL,
and is not a page-performance mechanism.

## 2. Reviewed source authority

```text
active_branch_before_integration=codex/new-demand-n2-n5-20260710
active_commit_before_integration=19f43cafa9abeeed2fea1c3d0d7b43b21c64598d
active_tree_before_integration=cb4f2f473ea4e936b805efd04ac50c46300653f0

candidate_branch=codex/n6-poller-bounded-canary-dual-lock-cas-fix-forward-v4
candidate_source_commit=dcf1499aa571796517eebca489f3e75a6675a8a6
candidate_source_parent=ce3fc5c08fffaa8426a57da7432ae4b29f4f2c53
candidate_source_tree=bcd93f198f58f44c09508605acbb09b69f01c16f
candidate_source_is_ff_descendant_of_active=true

dual_lock_cas_commit=104839e048abcf5b3c1c4cf0d03f04fea96a2698
single_event_limit_commit=ce3fc5c08fffaa8426a57da7432ae4b29f4f2c53
candidate_preparation_commit=dcf1499aa571796517eebca489f3e75a6675a8a6
```

Reviewed file identities:

```text
poller_path=scripts/run_n6_b_track_signal_projection_poller_once.py
poller_sha256=5fd4f35e26c385d9502ec310bcc90bdfcc30d8e0da1b2bc84e73ce5d775676c9
test_path=tests/test_n6_b_track_signal_projection_poller.py
test_sha256=47ccafdc90f3e64f1a09ede5aba9ca5862c47b6f93ccd5605c8a75c2a80481b1
candidate_preparation_path=docs/N6_POLLER_BOUNDED_CANARY_DUAL_LOCK_AND_CAS_FIX_FORWARD_IMMUTABLE_CANDIDATE_PREPARATION.md
candidate_preparation_sha256=a0316fc28a7cb7133e6a4a2766108393e929ecb1a9ad06358cd0bb4f08407574
reviewed_fixture_test_count=50
```

The current candidate sidecar remains evidence only:

```text
candidate_sidecar_path=tmp/n6_poller_bounded_canary_dual_lock_cas_fix_forward_v4/candidate_manifest.draft.json
candidate_sidecar_file_sha256=f2cf9631017ec67057910b6ffdfcc8b72e9135c0ce716632adad1db870184528
candidate_sidecar_integrity_sha256=8c70d4fac7d2403ed1a7ec3eb27efa587bf4fc42d386ad728292096ea73ff4ef
candidate_sidecar_classification=PRESERVE_ONLY_NOT_RUNTIME_AUTHORITY
```

## 3. Integration contract

The only authorized source integration is an exact fast-forward after a fresh dirty-intersection
review:

```text
git_merge_mode=ff-only
reset=false
revert=false
rebase=false
cherry_pick=false
stash=false
checkout_or_restore_user_files=false
```

The integration closure is limited to the reviewed poller, its test, the candidate preparation
document and this supersession artifact. All pre-existing active tracked modifications and untracked
artifacts are external-owned and must remain exact-byte unchanged.

Integration changes code availability only. It does not authorize a database connection, N6
execution, worker load, LaunchAgent operation, replay, backfill, notification, sim or real trade.

## 4. Resident-worker chain supersession

The following future resident-worker actions are superseded and closed by this artifact:

```text
immutable_daemon_promotion=false
new_promotion_manifest=false
new_versioned_plist=false
new_release_specific_lineage_publication=false
bounded_canary_for_reactivation=false
launchagent_bootstrap=false
launchagent_enable=false
launchagent_kickstart=false
resident_worker_reactivation=false
```

No further doc-only candidate, release generation, manifest-schema, plist, promotion or reactivation
gate may be inferred from the older chain. A future request for automatic realtime projection is a
new requirement and must reassess batch/CAS throughput and the standard LaunchAgents plist.

## 5. Preserve-only incident authority

The following existing authorities remain immutable evidence and are not runtime authority for this
on-demand mode:

```text
v3_release_path=/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260715_224550__19f43cafa9abeeed2fea1c3d0d7b43b21c64598d
v3_promotion_manifest_sha256=e4aa2677ab3a7a67915ed37a79adc3c4f3f43759efc03df5acbdc6e3a3e4d3cb
v3_versioned_plist_sha256=8d360b3efb3c96905cd0ab07c134af3fad3be8c39175edb518d7d90a227c68e6
retained_incident_lock_sha256=3d36e820245cc6af3207c17a4aac60871d627ee01b26fc6f5b9582f1948390c8
v3_generation_lock_sha256=b57eec8a7b22dac827a5cc7aef62fb44f57baebe749fe68b16981eb14832bbb0
classification=PRESERVE_ONLY_NON_CANARIED_NON_RUNTIME_AUTHORITY
```

The prepared v4 runtime environment may be used only as the Python dependency closure for an
explicit one-shot command; it is not a worker or release authority:

```text
runtime_env=/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/n6-b-track-bounded-canary-dual-lock-cas-fix-forward-v4-20260716
runtime_env_manifest_sha256=584517e2cd9ba819ddb7255bd55e640871c477a069948c2e3662043ec48ec214
runtime_env_writable_entries=0
runtime_env_bytecode_entries=0
runtime_env_worker_enabled=false
```

## 6. LaunchAgent boundary

```text
launchagent_label=com.ashare-v3.n6.b-track-signal-poller
standard_plist=/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.b-track-signal-poller.plist
standard_plist_sha256=eaefc32262527c01da302b8e35ba398e836efd9e943aced44ef7b15b57a91f80
required_state=disabled,unloaded,service-not-found,process-zero
standard_plist_action=preserve-only
```

This artifact does not authorize modifying, deleting, loading or enabling that plist. Every
on-demand execution must revalidate the required state. The old three-second configuration must
never be enabled as a shortcut.

## 7. First single-event validation contract

The first explicit validation must run in `layer_role=N6_user` and only during an open trading date
between `09:25` and `15:00` Asia/Shanghai.

Before the write attempt, a PostgreSQL `REPEATABLE READ READ ONLY` transaction must freeze the
canonical consumer checkpoint and at most one naturally ordered pending N5 action event, compute the
reviewed checkpoint/event CAS digests, and explicitly roll back.

The one permitted invocation must use:

```text
cas_authority_mode=external_bounded_canary
max_events=1
consumer_name=n6_b_track_signal_projection_poller_v1
singleton_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/locks/n6_b_track_signal_projection_poller.lock
report_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/reports/N6_b_track_signal_projection_on_demand_report.json
history_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/history/N6_b_track_signal_projection_on_demand_history.jsonl
execute=true
user_confirmed=true
historical_backfill=false
replay=false
synthetic_event=false
```

Allowed outcomes:

```text
ready_event=one projection,one card,one inbox audit,checkpoint advance
invalid_or_not_ready_event=zero projection/card,one inbox audit,checkpoint advance,stop
no_event=WAITING_FOR_LIVE_TRIGGER,zero business writes
cas_or_lock_drift=BLOCKED,transaction rollback,zero net business writes
```

The N5 outbox row and status/consumption fields must remain unchanged. The invocation stops after the
first selected event and must not automatically search for a later ready event.

## 8. Subsequent on-demand contract

Each future invocation requires a new explicit user instruction equivalent to “execute one N6
B-track projection”. The source authority is valid when the reviewed candidate commit remains an
ancestor of active and the poller/test exact-byte identities above remain unchanged; unrelated later
active commits do not invalidate the authority.

Subsequent calls use:

```text
cas_authority_mode=internal_one_shot
max_events=1
automatic_loop=false
automatic_retry=false
```

Before each call, revalidate the source file SHA, runtime environment, open trade date/window, worker
quiescence, singleton regular-file/owner/mode/nlink and absence of a live lock holder. The singleton
file may persist as a `0600` audit carrier after a completed invocation; path absence is not required
after first use.

## 9. Failure and rollback boundary

```text
failure_policy=STOP_AND_PRESERVE_EVIDENCE
active_history_rewrite=false
automatic_database_compensation=false
checkpoint_rewind=false
automatic_rerun=false
fix_forward_only=true
```

A failed or blocked invocation leaves the resident worker disabled/unloaded, preserves report,
history and lock evidence, and returns control to the user. No later layer or web-performance task is
entered automatically.

## 10. Explicit exclusions

This contract does not modify the 8786 page, add a POST route or button, change database schema,
change N2-N5 contracts, update N5 outbox status, send notifications, create sim/position facts or
perform a real trade. Page-performance diagnosis remains a separate read-only task.
