# N6 Poller Bounded Canary Dual-Lock and CAS Fix-Forward Immutable Candidate Preparation

## 1. Gate identity

```text
layer_role=N6_user
gate=N6_POLLER_BOUNDED_CANARY_DUAL_LOCK_AND_CAS_FIX_FORWARD_IMMUTABLE_CANDIDATE_PREPARATION_GATE
contract=N6-poller-bounded-canary-dual-lock-cas-fix-forward-immutable-candidate-preparation-v4
candidate_generation=BOUNDED_CANARY_DUAL_LOCK_CAS_FIX_FORWARD_V4
status=PREPARED_NOT_PROMOTED_NOT_RUNNABLE
```

This document prepares one immutable candidate descendant. It does not authorize
promotion, canary, worker reactivation, replay, backfill, database access, queue
consumption, or any LaunchAgent operation.

## 2. Reviewed implementation authority

```text
candidate_worktree=/Users/chuanfuchen/Documents/A股监控系统v3_n6_poller_bounded_canary_dual_lock_cas_fix_forward_v4
candidate_branch=codex/n6-poller-bounded-canary-dual-lock-cas-fix-forward-v4
reviewed_implementation_commit=ce3fc5c08fffaa8426a57da7432ae4b29f4f2c53
reviewed_implementation_parent=104839e048abcf5b3c1c4cf0d03f04fea96a2698
reviewed_implementation_tree=277037f9a631ea0065656c4e3e5681b93b4d4393
legacy_runtime_base_commit=19f43cafa9abeeed2fea1c3d0d7b43b21c64598d
legacy_runtime_base_tree=cb4f2f473ea4e936b805efd04ac50c46300653f0
```

The reviewed implementation aggregate relative to the legacy runtime base is
restricted to:

```text
production_changed_allowlist=[scripts/run_n6_b_track_signal_projection_poller_once.py]
test_changed_allowlist=[tests/test_n6_b_track_signal_projection_poller.py]
docs_changed_allowlist=[]
```

The implementation freezes OS singleton acquisition, the transaction-scoped
PostgreSQL advisory lock, exact checkpoint and selected-event CAS, and a single
natural N5 event per guarded invocation. Both `internal_one_shot` and
`external_bounded_canary` require `max_events=1`. Invalid projection messages
remain fail-closed and auditable; the following ready event is processed by a
subsequent invocation.

## 3. Unique docs-only candidate descendant

The source commit is created only after this document exists. Its exact commit,
parent, tree, committer time, and release identity are recorded in the ignored
candidate sidecar and are not guessed inside self-referential tracked bytes.

```text
integration_base_commit=ce3fc5c08fffaa8426a57da7432ae4b29f4f2c53
required_parent=ce3fc5c08fffaa8426a57da7432ae4b29f4f2c53
required_commit_count_from_integration_base=1
commit_subject=n6: prepare dual lock cas immutable candidate
integration_production_changed_allowlist=[]
integration_test_changed_allowlist=[]
integration_docs_changed_allowlist=[docs/N6_POLLER_BOUNDED_CANARY_DUAL_LOCK_AND_CAS_FIX_FORWARD_IMMUTABLE_CANDIDATE_PREPARATION.md]
```

Production and test blobs in the candidate source commit must remain exact-byte
identical to `ce3fc5c...`.

## 4. Commit-derived immutable release identity

After the docs-only commit exists, the sidecar derives the unique release ID:

```text
release_id_contract=<source_commit_committer_time_Asia_Shanghai_YYYYMMDD_HHMMSS>__<source_commit_40>
release_root=/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track
staging_path=<release_root>/.staging__<release_id>
final_path=<release_root>/<release_id>
promotion_manifest_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.json
versioned_plist_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.plist
lineage_publication_evidence_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.lineage-publication.json
```

Every derived target must remain absent and non-symlink throughout this gate.
No generation or singleton lock may be acquired.

## 5. Independent immutable runtime environment

The only new runtime environment permitted by this gate is:

```text
runtime_env=/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/n6-b-track-bounded-canary-dual-lock-cas-fix-forward-v4-20260716
runtime_environment_contract=INDEPENDENT_BYTE_COPY_OF_REVALIDATED_OFFLINE_CLOSURE_V1
network_access=false
dependency_upgrade=false
hardlink_reuse=false
enabled=false
read_only=true
bytecode_count=0
writable_entry_count=0
symlink_escape_count=0
```

The environment is copied without hardlinks from the preserved reviewed v3
offline closure. Its realpath, Python executable, dependency closure, entry
count, recursive canonical manifest, modes, symlinks, and file identities are
recomputed for the new absolute path. It contains no state, logs, reports,
locks, lineage, checkpoints, or bytecode and is not referenced by any worker.

## 6. Candidate sidecar

Exactly one ignored, untracked sidecar is permitted after the source commit:

```text
sidecar_path=tmp/n6_poller_bounded_canary_dual_lock_cas_fix_forward_v4/candidate_manifest.draft.json
sidecar_contract=N6-poller-bounded-canary-dual-lock-cas-fix-forward-candidate-manifest-draft-v4
sidecar_status=DRAFT_NOT_PROMOTED_NOT_RUNNABLE
```

The sidecar freezes:

- source commit, parent, tree, committer time, and release ID;
- integration and legacy-runtime bases, canonical patch commands and SHA-256;
- exact production, test, and docs allowlists and every allowlisted file SHA;
- the complete tracked-tree manifest count and canonical SHA;
- the complete active protected-path manifest and dirty intersection;
- runtime-env realpath, Python and dependency identity, recursive manifest,
  bytecode, writable, symlink-escape, and hardlink-reuse counts;
- all absent release targets and v4 lock paths;
- preserved v3 and incident authorities, worker quiescence, verification
  results, side-effect flags, and its own canonical integrity SHA-256.

## 7. Required absent v4 authorities

```text
generation_lock_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/locks/promotion.fix-forward-v4.lock
generation_lock_absent=true
production_singleton_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/locks/n6_b_track_signal_projection_poller.lock
production_singleton_absent=true
staging_created=false
final_release_created=false
promotion_manifest_created=false
versioned_plist_created=false
lineage_publication_evidence_created=false
```

## 8. Preserve-only authorities

The promoted-but-not-canaried v3 release, its promotion manifest, versioned
plist, runtime environment, state lineage, and retained v3 generation lock are
`PRESERVE_ONLY_NON_CANARIED_NON_RUNTIME_AUTHORITY`. They are not modified,
reused, relabeled, or treated as canary authority by this preparation.

The incident lock, retained incident staging, v1/v2/v3 candidate worktrees,
branches, sidecars, runtime environments, and all historical evidence are also
preserve-only. Nothing in this gate authorizes cleanup or supersession.

## 9. Verification and side-effect boundary

```text
associated_test_count=50
associated_tests_passed=true
ast_parse_only_passed=true
git_diff_check_passed=true
candidate_tracked_and_index_clean_after_commit=true
ignored_scope_only_candidate_sidecar=true
active_checkout_modified=false
production_modified=false
test_modified=false
database_connected=false
queue_consumed=false
N6_executed=false
generation_lock_acquired=false
singleton_lock_acquired=false
new_staging_created=false
new_final_created=false
promotion_manifest_created=false
versioned_plist_created=false
lineage_publication_evidence_created=false
launchagent_operated=false
worker_started=false
promotion_executed=false
canary_executed=false
replay_or_backfill_executed=false
reactivation_executed=false
```

Passing this preparation opens only the immutable candidate post-review gate.
