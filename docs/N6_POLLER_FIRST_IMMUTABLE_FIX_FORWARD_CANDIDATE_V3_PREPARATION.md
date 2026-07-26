# N6 Poller First Immutable Fix-Forward Candidate V3 Preparation

## 1. Gate identity and authority

```text
layer_role=N6_user
gate=N6_POLLER_FIX_FORWARD_V3_CANDIDATE_PREPARATION_GATE_RERUN_WITH_N5_ATTESTATION
contract=N6-poller-first-immutable-fix-forward-candidate-preparation-v3
candidate_generation=FIRST_IMMUTABLE_FIX_FORWARD_V3
candidate_id=n6-b-track-first-immutable-fix-forward-candidate-v3-20260715
status=PREPARED_NOT_PROMOTED_NOT_RUNNABLE
```

This preparation consumes only the source/integration reselection registered by:

```text
reselection_registration_path=/Users/chuanfuchen/Documents/A股监控系统v3_n6_poller_immutable_release_boundary_design_v1/docs/N6_POLLER_FIX_FORWARD_SOURCE_INTEGRATION_RESELECTION_REGISTRATION.md
reselection_registration_sha256=aad62004eaa3d5843f0d073366568d1c959ab6d5beb295275497affe0badc12b
selection_issued_at=2026-07-15T22:11:37+08:00
selection_expires_at=2026-07-16T08:30:00+08:00
selection_single_use=true
recovery_policy=QUIESCE_AND_FIX_FORWARD_ONLY
```

The selection was revalidated before any v3 namespace was created. Active Git
identity and protected state, superseded candidates, retained incident evidence,
worker quiescence, and all v3 namespace absence checks matched the registration.
This document does not authorize promotion, cleanup, canary, or reactivation.

## 2. Inherited N5 review authority

The integration base contains an inherited N5 runtime delta. Its sole semantic
review and fixture-test authority is the existing N5_action attestation below:

```text
n5_attestation_path=/Users/chuanfuchen/Documents/A股监控系统v3_n5_live_tracking_deadlock_retry_attestation_v1/docs/N5_LIVE_TRACKING_DEADLOCK_RETRY_INHERITED_REVIEW_ATTESTATION.md
n5_attestation_evidence_commit=a0d1bfb2af698bc0f2e762bb6112c5e3624b3fad
n5_attestation_evidence_parent=060a5aef92058842bd706984f36370f6450a2dbe
n5_attestation_evidence_tree=010755488dcd46f09ab0e8bbfc3817715edabc4b
n5_attestation_raw_sha256=3bd9c581fd4dc90dfc840ce831f00594b0261f35ac5af8d8cb4e331c11b54df2
n5_attestation_canonical_sha256=5a612c98c8cd8a388f3ad2e2eca57800e9fdae231218725c15f2759c16580379
n5_attestation_review_verdict=PASS
n5_attestation_tests_run=105
n5_attestation_test_result=OK
n5_attestation_runtime_side_effects=false
n5_attestation_database_or_queue_side_effects=false
```

The reviewed inherited delta is frozen exactly as:

```text
inherited_n5_parent=b338082f7dc9b1fc32dd49bf414a46cfcc8eff1d
inherited_n5_commit=060a5aef92058842bd706984f36370f6450a2dbe
inherited_n5_tree=9e348b2dc2ef87284f1d02195f85a56b883b88c7
inherited_n5_patch_sha256=36c8315a238aaf57f3c675d8850de882914a7589c52ef789a728483a87ca4aec
inherited_n5_poller_path=scripts/run_n5_live_tracking_poller_once.py
inherited_n5_poller_sha256=bf090a3f576a990cca91abedf57227aef5422e3429f11c3fbd2a1054a7977f4d
inherited_n5_test_path=tests/test_n5_live_tracking_poller.py
inherited_n5_test_sha256=de59eaef246a0a1e6a1fd8406e32a4f0a336fa86713a36e6baab90a6eb4e2292
```

These two N5 files are inherited reviewed runtime delta, not N6 candidate
changes. This gate does not rerun N5 runtime, connect to a database, or consume
a queue, and it does not independently reinterpret N5_action review authority.

## 3. Source and exact change scope

```text
worktree=/Users/chuanfuchen/Documents/A股监控系统v3_n6_poller_first_immutable_fix_forward_candidate_v3
branch=codex/n6-poller-first-immutable-fix-forward-candidate-v3
integration_base_commit=060a5aef92058842bd706984f36370f6450a2dbe
integration_base_tree_oid=9e348b2dc2ef87284f1d02195f85a56b883b88c7
runtime_base_commit=7c209394786c4d5810c00de34baaffe4f86beb4b
runtime_base_tree_oid=2a3b7ee9d09bcbda5e5b5ba52f8dee9765f9242e
required_parent=060a5aef92058842bd706984f36370f6450a2dbe
required_commit_count_from_integration_base=1
commit_subject=n6: prepare immutable poller fix-forward candidate v3
```

Exact integration allowlists:

```text
production_changed_allowlist=[]
test_changed_allowlist=[]
docs_changed_allowlist=[docs/N6_POLLER_FIRST_IMMUTABLE_FIX_FORWARD_CANDIDATE_V3_PREPARATION.md]
changed_paths=[docs/N6_POLLER_FIRST_IMMUTABLE_FIX_FORWARD_CANDIDATE_V3_PREPARATION.md]
production_review_closure=[scripts/run_n6_b_track_signal_projection_poller_once.py]
test_review_closure=[tests/test_n6_b_track_signal_projection_poller.py]
```

The source commit must be the unique docs-only child of `060a5aef...`. N6
production and test blobs must remain exact-byte identical to that parent. The
runtime-base delta must retain the first immutable candidate preparation, the
reviewed N5 two-file delta, and this v3 preparation as distinct provenance.

## 4. Independent immutable runtime environment

The only permitted new runtime environment is:

```text
runtime_env=/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/n6-b-track-first-immutable-fix-forward-candidate-v3-20260715
runtime_environment_contract=INDEPENDENT_BYTE_COPY_OF_REVALIDATED_OFFLINE_CLOSURE_V1
network_access=false
dependency_upgrade=false
hardlink_reuse=false
enabled=false
read_only=true
bytecode_count=0
writable_entry_count=0
required_environment_key_names=ASHARE_V3_POSTGRES_DSN,PYTHONDONTWRITEBYTECODE,PYTHONNOUSERSITE,PYTHONPATH
```

The environment is copied byte-for-byte from the revalidated immutable offline
closure without hardlinks. Its realpath, Python executable, dependency closure,
`sys.path`, recursive filesystem manifest, entry counts, modes, and hashes are
recomputed for the new absolute path. It contains no state, reports, logs,
locks, lineage, checkpoints, or bytecode and is not referenced by LaunchAgent.

## 5. Commit-dependent immutable release identity

The exact source commit is not guessed or embedded in its own tracked bytes.
After the single docs-only commit exists, the ignored candidate manifest freezes
the real commit and derives the release identity as follows:

```text
release_id_contract=<source_commit_committer_time_Asia_Shanghai_YYYYMMDD_HHMMSS>__<source_commit_40>
release_root=/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track
staging_path=<release_root>/.staging__<release_id>
final_path=<release_root>/<release_id>
promotion_manifest_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.json
versioned_plist_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.plist
lineage_publication_evidence_path=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests/<release_id>.lineage-publication.json
```

Every derived target must be absent and non-symlink. This preparation creates
no staging, final release, promotion manifest, plist, lineage evidence, or lock.

## 6. Corrected future promotion order

The only reviewable future promotion sequence remains:

```text
1_REVALIDATE=successor authority, candidate, active, protected state, worker, checkpoint, lineage
2_LOCK=obtain separately reviewed exclusive promotion authority
3_MATERIALIZE=create complete source tree in unique staging with root mode 0755
4_PRE_RENAME_VERIFY=verify Git tree, runtime closure, staging filesystem manifest, bytecode=0
5_ACTIVE_FF=git merge --ff-only exact source commit
6_ATOMIC_RENAME=renamex_np(new_staging,new_final,RENAME_EXCL)
7_FINAL_READ_ONLY_FREEZE=directories 0555, regular files 0444, executable files 0555
8_POST_FREEZE_VERIFY=recompute final manifest, writable=0, bytecode=0
9_PLIST_AND_MANIFEST=write reviewed absolute plist and promotion manifest only after step 8
10_FINAL_POSTCHECK=verify active, final, runtime env, plist, manifest, and protected evidence
```

Staging must remain writable through atomic rename. The final is frozen only
after rename, and plist/manifest creation remains blocked until independent
post-freeze verification succeeds.

## 7. Preserve-only evidence and absent future authorities

The v1/v2 candidate worktrees, branches, sidecars, runtime environments, the
retained incident lock, and retained incident staging are immutable
preserve-only evidence. They are not deleted, chmodded, renamed, reused,
merged, rebased, cherry-picked, or otherwise modified by this preparation.

The following v3 authorities remain absent:

```text
successor_promotion_lock_created=false
staging_created=false
final_release_created=false
promotion_manifest_created=false
versioned_plist_created=false
lineage_publication_evidence_created=false
launchagent_plist_created_or_modified=false
```

## 8. Post-commit ignored manifest

After the unique docs-only commit exists, exactly one ignored sidecar is
permitted:

```text
sidecar_path=tmp/n6_poller_first_immutable_fix_forward_candidate_v3/candidate_manifest.draft.json
sidecar_contract=N6-poller-first-immutable-fix-forward-candidate-manifest-draft-v3
sidecar_status=DRAFT_NOT_PROMOTED_NOT_RUNNABLE
```

The sidecar freezes the real source/parent/tree, integration/runtime patches,
tracked-tree manifest, per-file identities, N5 attestation authority,
independent runtime-env identity, exact release ID and absent paths, active
protected-state fingerprints, retained authorities, verification results, and
its own canonical integrity SHA-256. It is ignored, untracked, and never staged.

## 9. Verification and prohibited side effects

Only pure N6 fixture tests, `ast.parse`, and `git diff --check` are permitted.
No N5 runtime test or execute entrypoint is invoked.

```text
production_modified=false
test_modified=false
active_checkout_modified=false
old_candidate_or_runtime_env_modified=false
incident_lock_modified=false
incident_staging_modified=false
promotion_lock_acquired=false
new_staging_created=false
new_final_created=false
promotion_manifest_created=false
versioned_plist_created=false
lineage_publication_evidence_created=false
launchagent_operated=false
database_connected=false
queue_consumed=false
worker_started=false
N6_executed=false
promotion_executed=false
canary_executed=false
reactivation_executed=false
replay_or_backfill_executed=false
```

Passing this preparation opens only the v3 candidate post-review gate.
