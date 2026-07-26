# N6 Poller First Immutable Candidate Preparation

准备日期：2026-07-15

layer_role：`N6_user`

gate：`N6_POLLER_FIRST_IMMUTABLE_CANDIDATE_PREPARATION_GATE`

candidate_id：`n6-b-track-first-immutable-candidate-v1-20260715`

## 1. Gate classification

```text
intent=prepare_first_future_immutable_n6_b_track_poller_candidate
layer_role=N6_user
risk_level=medium
execution_mode=FULL_MODE
```

Execution DAG:

```text
PLAN
-> VALIDATE_BASE_AND_ACTIVE_PRESERVATION
-> MODIFY_ONE_DOC_IN_ISOLATED_WORKTREE
-> VERIFY_BASELINE_AND_EXACT_SCOPE
-> COMMIT_ONE_DIRECT_DESCENDANT
-> BUILD_OFFLINE_VERSIONED_RUNTIME_ENV
-> WRITE_UNTRACKED_SIDECAR_DRAFT
-> VERIFY_ALL_IDENTITIES
-> FINALIZE_POST_REVIEW_HANDOFF
```

Kernel and runtime gate:

```text
kernel_decision=ACCEPT
runtime_gate=ACCEPT_PREPARATION_ONLY
N6_business_behavior_changed=false
LaunchAgent_operation=false
database_connected=false
queue_consumed_or_updated=false
promotion=false
canary=false
```

## 2. Candidate source boundary

The candidate is prepared only in:

```text
worktree=/Users/chuanfuchen/Documents/A股监控系统v3_n6_poller_first_immutable_candidate_v1
branch=codex/n6-poller-first-immutable-candidate-v1
```

The source commit created by this gate must be the only commit on the branch
after the following immutable parent:

```text
source_parent=7c209394786c4d5810c00de34baaffe4f86beb4b
source_parent_parent=81647fdecad551a02bb079ff6ecf9ce00958b8bf
source_parent_tree_oid=2a3b7ee9d09bcbda5e5b5ba52f8dee9765f9242e
source_parent_patch_sha256=e8f0dfd07544a017368453d88a0a01a65a73e931d43f77f117fef4ced313bf16
```

The final `source_commit`, `source_tree_oid`, candidate patch SHA-256 and this
document's committed blob/content identities are intentionally bound after the
commit in the untracked sidecar manifest. Embedding them in this committed file
would create a self-referential identity contract.

## 3. Exact allowlists

Candidate changed-path allowlists are exact and contain no wildcard:

```json
{
  "production_changed_allowlist": [],
  "test_changed_allowlist": [],
  "docs_changed_allowlist": [
    "docs/N6_POLLER_FIRST_IMMUTABLE_CANDIDATE_PREPARATION.md"
  ]
}
```

The reviewed runtime closure is exact:

```json
{
  "production_review_closure": [
    "scripts/run_n6_b_track_signal_projection_poller_once.py"
  ],
  "test_review_closure": [
    "tests/test_n6_b_track_signal_projection_poller.py"
  ],
  "docs_review_closure": [
    "docs/N6_POLLER_FIRST_IMMUTABLE_CANDIDATE_PREPARATION.md"
  ]
}
```

Frozen parent-commit production/test identities:

| Path | Git blob OID | SHA-256 |
|---|---|---|
| `scripts/run_n6_b_track_signal_projection_poller_once.py` | `380a185f775a3c4a3774c7d9dc672c82e0d7093d` | `991985fc0611876062ed7995bfa90ed499e92165f4f8eb9661cafe0ac23e58db` |
| `tests/test_n6_b_track_signal_projection_poller.py` | `dfb0fb6c7e97e996f1e013cbbc21302d80e4d738` | `9a23eb2b90c984a069f7c6ffd50b36706e4cf4eaa2e83de162bd7d522b6bda9d` |

The source commit must preserve those two identities byte-for-byte. Any extra
changed path, mode change, rename or content drift blocks the candidate.

## 4. Versioned runtime environment

The only permitted environment target is:

```text
runtime_env=/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track/n6-b-track-first-immutable-candidate-v1-20260715
```

The gate may build this environment only when the path does not exist and the
complete dependency closure can be constructed from already present local
Python packages without network access, dependency upgrades or online
resolution. Otherwise it must stop with:

```text
BLOCKED_N6_POLLER_IMMUTABLE_RUNTIME_ENV_OFFLINE_CLOSURE_UNAVAILABLE
```

The environment attestation must freeze:

- environment and Python executable realpaths;
- Python version and executable SHA-256;
- the exact offline dependency closure and its canonical SHA-256;
- expected `sys.path` with `PYTHONNOUSERSITE=1`;
- required environment key names without secret values;
- a sorted recursive filesystem manifest SHA-256.

After attestation the environment is made read-only. It must never contain
reports, history, logs, lineage, locks, checkpoints or bytecode caches, and this
gate must not import or invoke the poller entrypoint.

## 5. Release and mutable state paths

The future release path is derived after the source commit exists:

```text
release_path=/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/n6-b-track-first-immutable-candidate-v1-20260715__<source_commit_40>
```

This gate requires the final derived path to remain absent. It does not create
a release tree, staging tree or production plist.

Mutable state is separated from all source and release trees:

```text
state_root=/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track
lineage_path=<state_root>/lineage/current_intraday_worker_lineage.json
report_path=<state_root>/reports/N6_b_track_signal_projection_poller_launchd_report.json
history_path=<state_root>/history/N6_b_track_signal_projection_poller_history.jsonl
stdout_path=<state_root>/logs/com.ashare-v3.n6.b-track-signal-poller.out.log
stderr_path=<state_root>/logs/com.ashare-v3.n6.b-track-signal-poller.err.log
singleton_lock_path=<state_root>/locks/n6_b_track_signal_projection_poller.lock
promotion_lock_path=<state_root>/locks/promotion.lock
```

These are path registrations only. This gate must not publish lineage, create
locks or mutate existing state.

## 6. Post-commit sidecar contract

After the single source commit and runtime-environment freeze, write exactly one
untracked draft at:

```text
tmp/n6_poller_first_immutable_candidate_v1/candidate_manifest.draft.json
```

It must use contract
`N6-poller-first-immutable-candidate-manifest-draft-v1`, status
`DRAFT_NOT_PROMOTED_NOT_RUNNABLE`, bind the final source/patch/file/environment
identities, carry all absolute paths, and declare:

```text
previous_release_classification=NONE_FIRST_ADOPTION
previous_release_id=null
previous_release_path=null
previous_release_manifest_sha256=null
runtime_base_authority_classification=LEGACY_AUTO_EXECUTED_REGISTRATION
runtime_base_commit=7c209394786c4d5810c00de34baaffe4f86beb4b
runtime_base_tree_oid=2a3b7ee9d09bcbda5e5b5ba52f8dee9765f9242e
first_adoption_failure_policy=QUIESCE_AND_FIX_FORWARD_ONLY
promotion_authorized=false
canary_authorized=false
reactivation_authorized=false
```

The sidecar is never staged or committed and must contain no DSN, token,
credential or secret value.

## 7. Verification and stop conditions

Before the post-review handoff, this gate must freshly prove:

- the original 33 associated tests pass;
- the poller and poller test parse as Python AST;
- the source commit has exactly one parent and one changed docs path;
- the production/test closure blobs and SHA-256 values are unchanged;
- candidate worktree and index are clean apart from the ignored sidecar;
- the runtime environment and manifest identities match their attestations;
- the derived release path does not exist;
- active checkout HEAD/index/dirty/untracked fingerprints are unchanged.

Any failed proof blocks the gate. No repair may be performed in the active
checkout, and no second candidate commit may be created.

## 8. Non-authorization statement

This preparation is not a release, promotion, canary or worker authorization.
It does not permit LaunchAgent operations, database access, N6 execution,
queue consumption, replay, backfill, notification, push, voice, mobile, sim or
trade activity.
