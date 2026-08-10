# N6 Migration Lineage 040–075 Registration Decision

```text
layer_role=runtime_control
mode=FULL
risk=high
result=REGISTRATION_IMPLEMENTED_REVIEW_REQUIRED
origin_main=1a4fd887b253474827bca91147e5d8e3d64c351e
approved_n6_integration_base_commit=NONE
migration_executed=false
database_connected=false
n6_source_modified=false
```

## Purpose

This gate records the split Git lineage for N6 migrations 040–075. It does not restore N6 source files to remote main, execute SQL, prove current database state, deploy a release, or authorize an N6 integration branch.

## Authorities

| Scope | Commit | Tree |
|---|---|---|
| remote-main candidate restoration base | `1a4fd887b253474827bca91147e5d8e3d64c351e` | `bc691336fe4e4eabddb3bc6ef1e307eb34a8ea92` |
| 040–073 canonical source | `c188a7fc2489fcc9d7d870260168dafd132d8711` | `fbf7d6d6b32f7720e1113edbf20a32ac6ed3076c` |
| 074 canonical source | `8c0aa5a284fc07f30531aad275c8ba140e82ff23` | `f8812287e489dc83203f012f60f0a6ce4c5e3b97` |
| 075 canonical source and observed active release | `af16803fd0f3411ad302b0df36b46b995c9c284c` | `c10ddfcac50ec34edf1630f39fbd50499ddb6470` |

Remote main and the N6 source lineage have no merge-base. Direct merge, rebase, cherry-pick, wholesale tree replacement, and execution inference from release presence remain forbidden.

## Registered inventory

- Migration identities: `36`
- SQL files: `71`
- Introduction commits: `34`
- Direct introduction-bundle paths: `176`
- Top-level distribution: `docs=33, scripts=12, sql=71, src=15, tests=45`
- Missing number 050 is recorded without inferring intent.
- 040 has no rollback and remains fail-closed.
- 073 contains two separately identified migration families.

## Execution evidence

- `executed_historical`: 055, 056, 057, 058, 063.
- `not_applied_as_of_contract`: 065, 066, 068, 069, 071.
- All other identities: `unknown`.

Historical execution never means current-live proof. Unknown is preserved whenever no durable per-migration repository artifact exists. In particular, 074 remains unknown even though an operator transcript reported execution, because the approved source commits contain no durable registration artifact for it.

## Dependency decision

T0 SQL authority and T1 introduction bundles are registered. T2 follow-up repair closure and T3 runtime/test dependency closure require a separate read-only N6_user review. The 176 direct paths are candidate dependencies, not an approved source-restoration allowlist. Cross-layer paths may never be auto-included.

## Files

- `docs/runtime/N6_MIGRATION_LINEAGE_040_075_REGISTRATION_MANIFEST.json`
- `docs/runtime/N6_MIGRATION_LINEAGE_040_075_DEPENDENCY_CLOSURE.json`
- `docs/runtime/N6_MIGRATION_LINEAGE_040_075_REGISTRATION_DECISION.md`

No other file is authorized in this gate.

## Decision

```text
registration_manifest_status=IMPLEMENTED_REVIEW_REQUIRED
transitive_dependency_closure_status=PENDING
n6_source_restoration_status=BLOCKED
approved_n6_integration_base_commit=NONE
stage_commit_push_pr_merge_authorized=false
```
