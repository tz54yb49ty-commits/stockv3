# Execution Compiler

## 1. Purpose

The Execution Compiler converts natural language tasks into a deterministic execution DAG.

It exists to make task planning explicit before any approved action is performed. The compiler translates a user request into ordered nodes and dependency edges so that validation, modification, verification, and finalization are visible and auditable.

This is a documentation-only system. It introduces no runtime implementation and does not itself execute a compiled plan. It may compile only the named bounded policies described below, but compilation is not runtime authorization and cannot replace Kernel or Runtime Gate `ACCEPT`.

## 2. Execution Plan Schema

The compiler output is a YAML `execution_plan`.

```yaml
execution_plan:
  plan_id: string
  layer_role: runtime_control | N1_ingestion | N2_condition | N3_market_data | N4_trigger | N5_action | N6_user
  risk_level: low | medium | high | critical
  affected_files:
    - string
  affected_resources:
    - string
  policy_id: string | null
  runtime_execution_requested: boolean

  nodes:
    - id: string
      type: PLAN | VALIDATE | MODIFY | VERIFY | FINALIZE
      description: string
      layer_role: string
      affected_files:
        - string

  edges:
    - from: string
      to: string
      reason: string
```

`nodes` define the work units. `edges` define dependency order between work units.

## 3. Node Types

### PLAN

Defines the intended work, scope, layer boundary, affected files, and risk level.

### VALIDATE

Checks that prerequisites, constraints, layer boundaries, and approved affected files are valid before any modification.

### MODIFY

Represents an approved file change. Every `MODIFY` node must be preceded by at least one `VALIDATE` node.

### VERIFY

Checks that the modification matches the approved plan and does not affect unapproved files or layers.

### FINALIZE

Produces the final status, summary, and audit-ready completion record.

## 4. Rules

```text
No execution without DAG.
Every MODIFY must be preceded by VALIDATE.
No cross-layer operations allowed.
No cycles in DAG.
```

Detailed rules:

1. A task must have an `execution_plan` before any approved action is performed.
2. The DAG must include `nodes` and `edges`.
3. A `MODIFY` node is invalid unless a dependency path from `VALIDATE` to `MODIFY` exists.
4. A DAG must not contain cycles.
5. Every node must declare its `layer_role`.
6. Every node must stay within the approved `layer_role`.
7. Every node must stay within the approved `affected_files`.
8. Cross-layer operations are rejected.
9. Runtime execution, database writes, worker startup, outbox consumption, rollback execution, and real trading are outside this documentation-only compiler contract by default.
10. The compiler may emit a runtime plan only for
    `policy_id=n6_strategy_center_display_only_bounded_run_once_v1`,
    `policy_id=n6_user_web_immutable_release_bounded_rebind_v1`, or
    `policy_id=n6_strategy_center_display_only_scheduled_evaluator_v1`, or
    `policy_id=n6_strategy_center_schema_migration_maintenance_window_v1`, or
    `policy_id=n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, or
    `policy_id=n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, or
    `policy_id=n6_strategy_center_post_081_v2_catalog_migration_window_v1`, or
    `policy_id=n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, or
    `policy_id=n6_strategy_center_pre_canary_web_write_quiesce_v1`, or
    `policy_id=n6_immutable_release_install_bounded_v1`, or
    `policy_id=n6_immutable_release_install_pre_rename_validator_recovery_v1`, or
    `policy_id=n6_immutable_release_install_preflight_git_violation_recovery_v1`, or
    `policy_id=n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`, and
    only after every rule in the corresponding section 4.1, 4.2, 4.3, 4.4,
    4.5, 4.5A, 4.6, 4.7, or 4.9 is structurally satisfied. The compiler still performs no
    runtime action.

### 4.1 Named N6 Bounded Run-Once Compilation

The compiler recognizes this N6 business runtime policy:

```text
policy_id = n6_strategy_center_display_only_bounded_run_once_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

Its DAG remains:

```text
PLAN
  -> VALIDATE active Release, exact single-user scope, ACL, current trade date,
              same-scope dry-run, watermark, plan hash, before/after, CAS,
              rollback, forbidden-runtime guards, and, only for the post-083
              Gate2 coexistence path, exact frozen virtual-executor identity,
              ACL/object/code disjointness, and zero operations
  -> MODIFY one bounded display-only primary evaluator commit
  -> VERIFY same scope, allowed tables, dry-run -> primary -> same-input replay,
            no drift, no virtual-executor operation, and no forbidden effects
  -> FINALIZE append-only trace and PASS/STOP
```

For this policy only, `MODIFY` means the one bounded strategy evaluator database
commit declared by the policy; it does not mean an unrestricted N6 execute. The
optional idempotence replay is part of `VERIFY`, is capped at one attempt, and
must use the same principal, user, selection revision, trade date, input, and
evaluator run id.

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  n6_user_strategy_selection_revision
  n6_strategy_match_projection
  n6_strategy_observation_projection
  n6_strategy_match_change
runner_basename = run_n6_strategy_center_once.py
scope_mode = single_user_revision
database_role = n6_strategy_worker
post_083 virtual-executor coexistence, when selected:
  phase_mode = post_083_maintenance_gate2_bounded_canary
  selection_revision_id = 20
  trade_date = current_trade_date = 20260723
  pre_gate_dry_run_attempts = 0
  pre_gate_primary_execute_attempts = 0
  pre_gate_same_input_replay_attempts = 0
  launch_agent_label = com.ashare-v3.n6.virtual-executor-v1
  database_role = n6_virtual_executor
  pgservice = n6_virtual_executor
  start_interval_seconds = 5
  virtual_executor_operation_attempts = 0
```

The compiler returns `failed` before Kernel evaluation when any scope parameter
is missing or non-positive, any count is not one, the requested trade date is
not the freshly verified current trade date, the affected resource set differs,
the runner/role differs, all-users mode is requested, or the DAG attempts a
worker, LaunchAgent, migration, proposal/order/trade/position/cash, real-broker,
outbox/inbox/checkpoint, or N1-N5 operation.

A loaded or running virtual executor is not by itself a failure only when the
request selects the exact post-083 Gate2 coexistence contract. The compiler must
then require revision 20 and current trade date 20260723; zero dry-run/primary/
replay attempts before Gate2; exact dry-run, primary, same-input replay order; frozen
label/plist/immutable Release/runner/PGSERVICE/role-ACL/object-boundary hashes;
no write privilege on Strategy Center selection/catalog/projection/observation/
change tables; no `EXECUTE` on formal Strategy Center functions; no code
reference to those objects; and zero bootout/bootstrap/modification/other
operation attempts. Any missing evidence, privilege/reference, configuration or
identity drift returns `failed`. Normal existing `StartInterval=5` PID/runs
cycling alone is not drift. The exact four-table evaluator DML allowlist includes
observation. Its `SELECT FOR UPDATE/INSERT/UPDATE/DELETE` must carry complete
principal/type/user/revision/current-open-trade-date scope, the 081 unique grain,
watermark/plan-hash/selection-CAS replay authority, qualified/observation
episode exclusivity, `surface_kind=observation`, and change dedup. Any fifth
table, missing predicate, cross-scope/date write, dual surface, duplicate change,
Web/virtual-executor observation write authority, or executor observation code
reference returns `failed`.

The complete value-level authority remains the machine-readable policy in
`docs/EXECUTION_KERNEL.md`. Compiler success alone never changes the default
Runtime Gate decision from `REJECT`.

### 4.2 Named N6 Web Immutable Release Bounded-Rebind Compilation

The compiler also recognizes exactly one `runtime_control` service policy:

```text
policy_id = n6_user_web_immutable_release_bounded_rebind_v1
layer_role = runtime_control
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

Its DAG remains:

```text
PLAN
  -> VALIDATE exact label/plist, single source and target immutable Releases,
              non-regressing lineage, PID/PPID/argv/cwd, plist metadata,
              environment, launchd ownership, forbidden-runtime guards,
              readiness contract, and frozen-source rollback contract
  -> MODIFY install the validated target plist, perform one primary bootout,
            wait for old PID and job absence, then perform one primary bootstrap
  -> VERIFY target Release, PID, environment, port, routes, stability window,
            evaluator/executor absence, and no forbidden effects; on proven
            health failure only, restore the frozen source with one rollback pair
  -> FINALIZE append-only before/after trace and PASS/STOP
```

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist
  gui/current-user/com.ashare-v3.n6.user-web
release_root = /Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track
scope_mode = single_launch_agent_single_source_target_release
service_count = 1
source_release_count = 1
target_release_count = 1
primary_bootout_attempts = 1
primary_bootstrap_attempts = 1
maximum_primary_retries = 0
maximum_rollback_attempts = 1
```

The compiler returns `failed` before Kernel evaluation when ownership is
ambiguous; any singleton count differs from one; source/target Release identity,
hash, immutability, or lineage proof is incomplete; affected resources or
operations differ; another service/LaunchAgent is requested; fixed-delay or
repeat retry semantics appear; or the DAG attempts a database, migration,
evaluator, worker, N1-N6 business, queue, broker, or trading operation.

The complete value-level authority remains the machine-readable policy in
`docs/EXECUTION_KERNEL.md`. Compiler success alone never changes the default
Runtime Gate decision from `REJECT`.

### 4.3 Named N6 Strategy Center Scheduled Evaluator Compilation

The compiler recognizes exactly one recurring N6 display-only evaluator policy:

```text
policy_id = n6_strategy_center_display_only_scheduled_evaluator_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

Its DAG remains:

```text
PLAN
  -> VALIDATE current-request automatic-evaluator authorization; the frozen
              20260722 single-user bounded dry-run/primary/same-input replay,
              projection and SSE PASS; one exact immutable Release; exact
              pinned dfb5b04a/995e4803 source-authority blobs, dependency lock,
              isolated runtime-env
              manifest/filesystem and exact argv; current open trade date; exact ACL,
              PGSERVICE, label/plist, five-second schedule, per-user isolation,
              four-table DML allowlist, observation scope/grain/surface/dedup/
              replay guards, no-overlap guards, before-state, readiness,
              rollback, concurrency, and virtual-executor evidence
  -> MODIFY install one validated plist and bootstrap the exact absent label;
            launchd may then invoke only the exact bounded run-once runner
  -> VERIFY exact Release/runner/plist/PGSERVICE, StartInterval=5, launchd
            single-instance plus advisory-lock behavior, current-open-day and
            closed-day-no-op gates, per-user isolation, exact DML, readiness,
            no drift, and no forbidden effects; on readiness failure only,
            unload the exact label and remove the installed plist once
  -> FINALIZE append-only before/after/readiness/canary/rollback/concurrency
              trace and PASS/STOP
```

For this policy only, `MODIFY` includes one exact-label scheduler activation and
the immutable runner's recurring bounded invocations. It is not permission for
a daemon, mutable checkout, arbitrary LaunchAgent, arbitrary all-users job, or
general N6 execute. Every invocation must freshly bind `Asia/Shanghai` current
date, derive its stable attempt-scoped run id from the frozen source state, and
fail closed/no-op without DML when the current date is not an open trade date.

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist
  gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1
  n6_user_strategy_selection_revision
  n6_strategy_match_projection
  n6_strategy_observation_projection
  n6_strategy_match_change
release_root = /Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track
runner_basename = run_n6_strategy_center_auto_once.py
planner_basename = plan_n6_strategy_center_launchd.py
runtime_env_root = /Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track
scheduler_mode = all_users_current_open_trade_date
scope_mode = single_scheduler_all_users_per_user_isolated
database_role = n6_strategy_worker
pgservice = n6_strategy_worker
launch_agent_label = com.ashare-v3.n6.strategy-center-evaluator-v1
start_interval_seconds = 5
```

The compiler returns `failed` before Kernel evaluation when the 20260722
bounded canary is incomplete; any singleton differs from one; the activation
date is not the freshly verified current open trade date; Release, runner/
planner blobs, dependency lock, runtime-env manifest/filesystem, exact argv,
ACL, plist, or concurrency evidence is incomplete or drifted; runner arguments
accept an external trade date/scope; the database
identity is not exactly `PGSERVICE=n6_strategy_worker`; the interval, label,
resource, operation, or DML set differs; per-user isolation is unproved; either
no-overlap guard is missing; the virtual executor is loaded; or the DAG attempts
mutable code, another LaunchAgent, migration/schema, N1-N5, outbox/inbox/
checkpoint, account/cash/position mutation, proposal/order/trade, real broker,
voice/mobile/sim, cross-user writes, or rollback DML. It also returns `failed`
for any fifth table; observation DML missing the full scope predicate/insert
columns or 081 grain; cross-scope/date writes; same-episode dual surfaces;
duplicate observation changes; replay without the same scope/input/run id or
same-hash unchanged result; Web/virtual-executor observation table authority;
executor observation code references; observation deletion during rollback; or
081 schema rollback while a V2 dependency exists.

The complete value-level authority remains the machine-readable policy in
`docs/EXECUTION_KERNEL.md`. Compiler success alone never changes the default
Runtime Gate decision from `REJECT`.

### 4.4 Named N6 Strategy Center 081 Maintenance Window Compilation

The compiler recognizes exactly one `runtime_control` maintenance-window policy:

```text
policy_id = n6_strategy_center_schema_migration_maintenance_window_v1
layer_role = runtime_control
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = prepare_081_window_only
```

Its DAG remains:

```text
PLAN
  -> VALIDATE current-request authorization; exact 081 forward/rollback and
              immutable Release hashes; exact Web/evaluator labels, plists,
              runners, roles, ownership and before-state; virtual-executor
              object disjointness; Web-only write-flag delta; routes,
              state-driven teardown, read-only watermark and token contracts
  -> MODIFY change only the Web strategy-write flag from 1 to 0, perform one
            state-driven Web bootout/bootstrap, bootout only the exact evaluator
            once, wait for its PID/job absence, then write one immutable token
  -> VERIFY Web readiness/stability, selection-write quiescence, evaluator
            absence, token hashes/expiry/watermarks, frozen virtual-executor
            configuration, no database write/lock, and no forbidden effect
  -> FINALIZE append-only before/after trace and PASS/STOP
```

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist
  gui/current-user/com.ashare-v3.n6.user-web
  gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1
  /Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/maintenance/<single-immutable-token>
migration_id = 081
migration_execution_attempts = 0
web_primary_bootout_attempts = 1
web_primary_bootstrap_attempts = 1
evaluator_bootout_attempts = 1
evaluator_bootstrap_attempts = 0
virtual_executor_operation_attempts = 0
primary_retries = 0
```

The compiler returns `failed` before Kernel evaluation when authorization is
missing; 082/083 or migration execution is requested; the Web delta changes
anything except the one strategy-write flag; evaluator ownership or full
teardown is unproved; virtual-executor operation is requested; immutable
Release, migration, plist, runner, role/ACL, watermark, or token evidence
drifts; a fixed sleep, kill, kickstart, repeated attempt, database write/lock,
another service, N1-N5 write, queue, business, broker, or trading path appears.

Normal StartInterval PID/runs cycling is not configuration drift. The compiler
must compare the virtual executor's frozen label/plist/Release/runner/role, not
require its periodic PID or runs counter to remain constant.

This plan ends with quiescence and a token. It cannot compile 081 itself, restore
the old evaluator after 081, activate V2, or combine runtime_control and N6_user
nodes. The complete value-level authority remains the machine-readable policy
in `docs/EXECUTION_KERNEL.md`; compiler success alone never changes Runtime Gate
from `REJECT`.

### 4.5 Named Strategy Center Post-081 V2 Web Rebind Compilation

The compiler recognizes one maintenance-phase `runtime_control` Web policy:

```text
policy_id = n6_strategy_center_post_081_v2_web_bounded_rebind_v1
layer_role = runtime_control
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = post_081_v2_web_rebind_only
```

Its DAG remains:

```text
PLAN
  -> VALIDATE current-request authorization; committed 081 and absent 082/083
              evidence; exact source/target immutable Release hashes and
              non-regressing V2/081 compatibility; exact Web ownership,
              strategy-write=0 before/target/after; evaluator job/PID absence;
              frozen, object-disjoint virtual-executor configuration; routes,
              readiness, stability, rollback, and all forbidden fields
  -> MODIFY install only the validated Web target plist, perform one
            state-driven Web bootout/bootstrap, and perform no evaluator or
            virtual-executor operation
  -> VERIFY target Web Release, PID/environment/port/routes, write flag 0,
            stability, evaluator absence, frozen virtual-executor evidence,
            and no database, migration, business, or trading effect; on a
            proven primary health failure only, restore the frozen source with
            one rollback pair while preserving write flag 0
  -> FINALIZE append-only before/after trace and PASS/STOP
```

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist
  gui/current-user/com.ashare-v3.n6.user-web
scope_mode = post_081_single_web_single_source_target_release
phase_mode = post_081_v2_web_rebind_only
service_count = 1
source_release_count = 1
target_release_count = 1
strategy_write_flag_before = 0
strategy_write_flag_target = 0
strategy_write_flag_after = 0
primary_bootout_attempts = 1
primary_bootstrap_attempts = 1
maximum_primary_retries = 0
maximum_rollback_attempts = 1
evaluator_operation_attempts = 0
virtual_executor_operation_attempts = 0
database_connection_attempts = 0
migration_attempts = 0
```

The compiler returns `failed` before Kernel evaluation when authorization,
committed-081 evidence, absent-082/083 evidence, immutable Release hashes,
lineage/V2/081 compatibility, Web ownership, write-flag zero, evaluator absence,
virtual-executor frozen/disjoint evidence, readiness, rollback, or any required
field is missing. It also fails on any database or migration request,
evaluator/virtual-executor operation, extra service, fixed sleep, kill,
kickstart, repeated primary attempt, mutable Release, N1-N5 write, queue,
business, broker, or trading path.

Normal virtual-executor StartInterval PID/runs cycling is not configuration
drift. Its label/plist/Release/runner/role/ACL/object-boundary evidence must
remain frozen, but the compiler must not require the periodic PID or runs value
to remain constant.

This policy does not alter
`n6_user_web_immutable_release_bounded_rebind_v1`. It cannot compile 081/082/083,
restore the Strategy Center evaluator, enable strategy writes, or combine
runtime_control and N6_user nodes. The complete value-level authority remains
the machine-readable policy in `docs/EXECUTION_KERNEL.md`.

### 4.5A Named Strategy Center Post-083 V2 Web Rebind Compilation

The compiler recognizes one post-083/084 `runtime_control` Web policy:

```text
policy_id = n6_strategy_center_post_083_v2_web_bounded_rebind_v1
layer_role = runtime_control
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = post_083_v2_web_rebind_only
```

Its DAG is:

```text
PLAN
  -> VALIDATE current-request authorization; committed 081/082/083/084 and
              schema/catalog evidence; exact legacy source basename and
              full-commit/tree/archive/git-ls-tree/manifest/filesystem/
              blob-mode-path attestation; one formally named target and
              source-delta/non-regression proof; exact Web ownership and
              strategy-write=1 before/target/after/rollback; prior independent
              evaluator quiesce with job/PID absent; frozen, StartInterval=5,
              write-disjoint virtual-executor configuration; readiness,
              routes, stability, rollback, and all forbidden fields
  -> MODIFY install only the validated Web target plist, perform one
            state-driven Web bootout/bootstrap, and perform zero evaluator or
            virtual-executor operations
  -> VERIFY formal target Release, Web PID/environment/port/routes/write flag,
            30-second stability, evaluator absence, unchanged virtual-executor
            configuration/object boundary, and no database, migration,
            business, N1-N5, or trading effect; on proven primary health
            failure only, restore the exact attested legacy source with one
            rollback pair and write flag 1
  -> FINALIZE append-only before/after trace and PASS/STOP
```

The compiled plan must declare:

```text
affected_files = []
affected_resources =
  /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist
  gui/current-user/com.ashare-v3.n6.user-web
scope_mode = post_083_single_web_legacy_source_formal_target_release
phase_mode = post_083_v2_web_rebind_only
service_count = 1
source_release_count = 1
target_release_count = 1
source_release_name = 20260724_042200__a1dc7350
source_release_full_commit = a1dc73503a07055f7bdb9cd29b378d1272642473
legacy_source_usage = frozen_rollback_source_once
strategy_write_flag_before = 1
strategy_write_flag_target = 1
strategy_write_flag_after = 1
primary_bootout_attempts = 1
primary_bootstrap_attempts = 1
maximum_primary_retries = 0
maximum_rollback_attempts = 1
evaluator_operation_attempts = 0
virtual_executor_start_interval_seconds = 5
virtual_executor_operation_attempts = 0
database_connection_attempts = 0
migration_attempts = 0
```

Compilation fails before Kernel evaluation on any missing authorization or
committed-stage evidence; a source other than the one exact legacy basename;
an unclosed short/full commit, tree, archive, git-ls-tree, manifest, filesystem,
blob/mode/path, ownership, or immutable attestation; reuse, mutation, or target
use of the legacy source; a short target; target lineage/schema/N6 regression;
strategy write other than `1`; missing independent evaluator quiesce; any
evaluator operation; virtual-executor operation or configuration/ACL/object
drift; extra plist/environment delta; repeated attempt; fixed sleep, signal,
kill, or kickstart; database, migration, queue, business, N1-N5, broker, or
trading path.

Normal virtual-executor `StartInterval=5` PID/runs cycling alone is not
configuration drift. This policy cannot compile evaluator quiesce; that must be
completed by an earlier independent N6 gate. It does not alter either existing
Web rebind policy. The complete value-level authority remains the
machine-readable policy in `docs/EXECUTION_KERNEL.md`.

### 4.6 Named Strategy Center Post-081 V2 Catalog Migration Compilation

The compiler recognizes one policy with two strictly ordered, independently
authorized `N6_user` phases:

```text
policy_id = n6_strategy_center_post_081_v2_catalog_migration_window_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = execute_082_tooling_once | execute_083_catalog_activation_once
```

Exactly one phase and one migration may appear in a plan. 082 requires
committed 081, absent 082/083, zero pending revisions, and an install-only
constraint/index/function/ACL plan with no function call or row mutation. 083
requires committed 081/082, absent 083, passed 082 postflight/ACL, current open
trade date, zero pending revisions, zero V2 selection items, and one active V1
revision per active principal. Its write plan is limited to the four frozen
catalog transitions.

Both phases require strategy write `0`, evaluator job/PID absence, immutable
Release and migration hashes, frozen write-disjoint virtual-executor evidence,
one explicit `ON_ERROR_STOP` transaction, one advisory transaction lock, one
forward attempt, and zero retry. Combined 082/083, wrong order, compensation
function calls, selection/projection/change writes, Web/evaluator/executor
operation, business DML, N1-N5, broker, or trading paths fail compilation.
Rollback is not part of either forward phase and requires separate authority.

The governance request that introduces or changes this policy may compile only
documents and static tests. It cannot execute either migration phase.

### 4.7 Named Strategy Center Post-083 Single-User Pending V2 Revision Compilation

```text
policy_id = n6_strategy_center_post_083_single_user_pending_v2_revision_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

The DAG binds `pre_dml_guard_harness_recovery_v2`, one exact
principal/user/current-open-trade-date scope, and one active-V1 predecessor to
one pending V2 revision. The first canary is frozen to principal/user 1/1,
active revision 15/revision_no 5, target revision_no 6, trade date 20260723,
and package_1/v1 -> package_1/v2 with no package-key addition or removal.

`VALIDATE` first proves exactly two ordered, automatically aborted historical
pre-DML harness transactions: SQLSTATE `42704` at the PUBLIC ACL audit guard,
then SQLSTATE `42601` because the psql `request_id` variable inside a
dollar-quoted `DO` body did not expand. Both must have zero official selection-
function calls, zero revision/item DML, zero commits, no persisted request id,
zero mutation attempts, and equality of every frozen before/after hash. It
accepts only an audit-only ACL repair using
`pg_catalog.aclexplode(COALESCE(proacl,
pg_catalog.acldefault('f', proowner))).grantee=0`; the official selection
function must remain byte-for-byte unchanged. It then requires a new,
independent `READ ONLY` preflight transaction to finish every complex
validation and a new request id supplied through shell/driver parameter
binding, and freshly proves committed
081/082/083 postflights and hashes, V2 catalog active, strategy write `0`,
evaluator job/PID absence, frozen and unoperated virtual executor, zero pending
and zero V2 items for the target scope, unique active V1 predecessor,
owner/user isolation, official-function authority, request-id
idempotence, previous-revision CAS, before-state, and zero forbidden effects.
`MODIFY` is limited to one new transaction and at most one mutation attempt
inserting the pending selection revision and its single V2 item. The mutation
transaction permits only `BEGIN`, `SET`, one advisory-lock `SELECT`, one
official selection-function `SELECT`, read-only postflight `SELECT`, and
`COMMIT`; it forbids `DO`, psql variable interpolation, dynamic SQL, and
complex validation. The request-id hash may be audited, but token/secret values
must not be logged. `VERIFY`
proves pending/pending state, no activation, request-id replay safety, unchanged
other users and projection/change watermarks, and zero N1-N5, queue,
proposal/order/trade/position/cash, broker, Web, evaluator, or virtual-executor
effect.

All-users, multi-scope, non-current/non-open trade date, package-key set change,
strategy write `1`, evaluator presence, uncommitted or drifted 083, existing
pending/V2 item, predecessor drift, direct activation, 082 compensation call,
extra DML, retry, or missing current-request authorization fails compilation.
Any historical official-function call, revision/item DML, commit, persisted
request id, mutation attempt, hash mismatch, reordered/different failure
reason, third pre-DML error kind, third harness transaction, same request id,
non-audit guard change, official-function modification, `DO`, psql
interpolation, dynamic SQL, secret leakage, or second mutation attempt also
fails compilation. The governance session may compile only documents and
static tests and cannot use this policy.

## 5. Output Format

### 4.8 Strategy Center Evaluator Quiesce for Web Rebind Compilation

```text
policy_id = n6_strategy_center_evaluator_quiesce_for_web_rebind_v1
layer_role = runtime_control
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = post_083_write_enabled_prepare_web_rebind
```

The compiled DAG is:

```text
PLAN
  -> VALIDATE current-request authorization; post-083 and strategy-write=1;
              exact evaluator label/plist/path/runner/Release/role/ACL,
              launchd ownership and before state; frozen Web state; frozen,
              write-disjoint virtual-executor configuration; one-target
              operation and all forbidden fields
  -> MODIFY perform one launchctl bootout for only the exact evaluator label
  -> VERIFY state-driven evaluator PID/job absence; unchanged Web and virtual
            executor; zero bootstrap/kickstart/kill/retry/automatic restore;
            zero database, evaluator execution, migration, business, trading
            or N1-N5 effect
  -> FINALIZE freeze after-state or failure evidence and PASS/STOP
```

The plan must declare:

```text
affected_files = []
affected_resources =
  gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1
evaluator_bootout_attempts = 1
evaluator_bootstrap_attempts = 0
maximum_retries = 0
web_operation_attempts = 0
virtual_executor_operation_attempts = 0
database_connection_attempts = 0
```

Compilation fails when ownership or any frozen evaluator identity/configuration
is unclear; strategy write is not `1`; another service or more than one target
appears; Web or virtual executor is operated; evaluator execution, bootstrap,
kickstart, kill/signal, retry, or automatic restore is requested; or any
database, migration, selection/projection/change, queue, N1-N5, business,
broker, or trading path appears. Normal configured virtual-executor
StartInterval PID/runs cycling alone is not configuration drift.

The governance request that introduces or changes this policy may compile only
documents and static tests. It cannot execute the quiesce action.

### 4.9 Named N6 Immutable Release Install Compilation

`n6_immutable_release_install_bounded_v1` compiles only one already-attested
N6 Release artifact. It requires one new direct-child target, one unique
same-parent staging path, verified commit/tree/archive/manifest/filesystem/
attestation hashes, immutable owner/mode/ACL/xattr checks, and one atomic
staging-to-target rename. If the frozen Release root begins at `0555` and no
separate privileged installer is available, it compiles exactly one owner-only
`0555 -> 0755` mode change before staging and exactly one `0755 -> 0555`
restoration on every success or failure path; owner/group/ACL/xattr remain
frozen and group/other write is forbidden. It never compiles service, LaunchAgent, database,
evaluator, migration, business, trading, or N1-N6 mutation steps. Failure
cleanup is limited to paths created by this attempt; existing Releases are
never deleted or modified. Any missing authorization, hash drift, target
existence, non-atomic finalization, concurrent drift, or forbidden operation
compiles to `REJECT`.

`n6_immutable_release_install_pre_rename_validator_recovery_v1` compiles only
one later, separately authorized recovery for the exact aa6d19c pre-rename
validator-capability failure. PLAN and VALIDATE must first bind the immutable
BLOCKED attestation and sidecar, exact source hashes, zero prior rename/
fallback/retry/cleanup attempts, absent target, restored `0555` Release root,
unchanged existing Releases, and the preserved staging-v1 identity and
metadata/xattr fingerprints. The preserved staging is evidence-only and never
appears in MODIFY.

The acyclic recovery DAG is:

```text
PLAN
  -> VALIDATE-0(frozen failure/source/staging/root/target evidence)
  -> MODIFY-A(create and seal exact capability artifact only)
  -> VERIFY-A(capability/hash binding)
       PASS -> MODIFY-B
       FAIL -> FINALIZE-A(root confirmed 0555, sealed failure artifacts) -> STOP
  -> MODIFY-B(one root window, fresh staging-v2, one exclusive renameatx_np)
  -> VERIFY-B(full staging/target/metadata/no-side-effect postflight)
  -> FINALIZE(root 0555, immutable evidence, no writable failure residue)
```

The later recovery DAG must next generate exactly one SHA-bound macOS
xattr-validator capability attestation and sidecar. VERIFY-A must prove the
bound executable and protocol can read xattr names and values without
mutation, and must freeze the attestation/sidecar/executable/protocol hash
bindings before any Release-root mutation. Capability failure must compile to
FINALIZE-A with capability evidence sealed, Release root confirmed unchanged
at `0555`, no staging-v2, and exact sealed recovery failure artifacts, then
STOP. It must perform no Release-root mode change or staging-v2 creation. Only after
capability PASS may MODIFY open one owner-only Release-root write window,
create the exact fresh same-parent staging-v2, rematerialize it from the
frozen archive, seal and fully validate blob/path/mode/ACL/xattr names and
values. Xattr validation must derive its exact 6288-record path set from the
frozen release-content manifest's 6243 path fields plus 45 directories/root,
then match the sole name, raw-value SHA and length-prefixed canonical
fingerprint and exact owner/group before it may call one same-dirfd
`renameatx_np` with EXCL/NOFOLLOW_ANY/RESOLVE_BENEATH. The compiler must
restore the root to `0555` immediately after the rename attempt, then run
target/staging final postflight for the selected success or failure branch.
Only after the root is confirmed `0555` and the selected recovery outcome
branch (including capability failure) has finalized may FINALIZE create the
exact new recovery output directories and
write the validation, attestation and SHA-sidecar paths using exclusive
no-follow creation. No recovery output path may exist during the root window,
staging materialization/validation, rename or Release postflight. Any
failure after the first output path is created must compile a branch that
seals all created output files/directories to `0444/0555`, records partial
identity/hash evidence and leaves no writable residue.
If any step fails after staging-v2 creation but before successful rename,
FINALIZE must recursively seal every created staging-v2 file/directory to
`0444/0555`, freeze its identity and metadata evidence, restore the Release
root and leave no writable staging. A post-rename postflight failure instead
preserves and attests the immutable target without modification or deletion.
Missing capability proof, partial validation, staging-v1 reuse/modification/
deletion, cleanup, another staging name, second recovery, policy fallback or
any Git/test/port/service/LaunchAgent/database/evaluator/executor/migration/
N1-N6/business/trading operation compiles to `REJECT`. The governance
definition request compiles documents and static tests only and cannot execute
the recovery. Unknown request fields, ordinary/overwrite rename, unbound
artifact paths or output overwrite also compile to `REJECT`.

`n6_immutable_release_install_preflight_git_violation_recovery_v1` compiles
only the single frozen `BLOCKED_PRE_MUTATION` procedural failure of the prior
validator-recovery gate. VALIDATE uses no Git and no tests: it binds the prior
governance literals, independently attested current `AGENTS.md` and Kernel
policy-block raw-byte hashes, unique session turn segment/prefix byte
boundaries and hashes, sole Git tool-call identity/arguments/output, and
direct filesystem evidence. It proves the historical Git commands were only
`rev-parse`, `diff`, and `show`, with zero Git/worktree mutation and zero
artifact/root-mode/staging-v2/target/runtime mutation. Summary evidence,
append-drifting whole-session hashes, Git verification, or tests compile to
STOP.

The acyclic execution DAG is
`PLAN -> VALIDATE-NO-GIT-NO-TEST -> CAPABILITY -> FINALIZE-A -> STOP` on
capability failure, or
`PLAN -> VALIDATE-NO-GIT-NO-TEST -> CAPABILITY -> ROOT-WRITE-ON ->
FRESH-STAGING-V2 -> FULL-VALIDATE -> EXCLUSIVE-RENAME -> ROOT-RESTORE ->
POSTFLIGHT -> FINALIZE -> STOP` on success. It preserves staging-v1 as
immutable evidence, permits one root owner-write window and one exclusive
same-dirfd rename, and rejects prior-policy reuse, fallback, retry, another
recovery, Git, tests, cleanup, runtime/service/DB, evaluator/executor,
migration, N1-N6 or trading work. This governance definition gate cannot
execute the policy.

`n4_lifecycle_deactivation_state_columns_controlled_promotion_v1` compiles
the frozen `8229124a -> 6d1b7a24 -> a1ff8b0e` history only as non-executable
source evidence. It fixes the eight N4 paths, source endpoint blobs,
combined/rollback patch hashes and the two exact label/original-plist
path/SHA bindings. It does not compile `6d1b7a24` or `a1ff8b0e` as execution
targets and does not contain the not-yet-created final commit SHAs.

After this policy is committed, a separate `N4_trigger` preparation must
recreate exactly two promotion commits plus one rollback from the policy
commit. A later independent `runtime_control` gate freezes those exact SHAs
before any bootout and verifies the direct-parent chain, final combined patch,
eight final blobs, and rollback tree equality with the policy commit. Only
then may the DAG compile
`PLAN -> VALIDATE -> BOOTOUT-EXACT-TWO -> WAIT-ABSENCE -> FF-ONLY-MERGE-ONCE
-> BOOTSTRAP-ORIGINAL-TWO -> VERIFY -> FINALIZE`.

Dirty tracked/index state, plist drift, a busy worker/child, another path,
blob, patch, plist, label or LaunchAgent, a non-ff merge, kickstart, manual
execute, retry, push, checkout/rebase/cherry-pick, automatic rollback, DB,
message/queue, historical-event, N2/N3/N5/N6 or trading work compiles to
`REJECT`. Failure compiles only a report containing the frozen final rollback
target; it never compiles rollback execution. This governance definition gate
cannot execute the policy.

`n6_immutable_release_install_eacces_retry_v1` compiles only a separately
authorized retry after exactly one frozen `EACCES` result from the initial
installer. It requires a new target and a new same-parent staging path; the
old staging is evidence-only and may not be reused, modified or removed. It
requires a fresh `0555 -> 0755 -> 0555` release-root window and, after full
content validation, exactly one `0555 -> 0755 -> 0555` transition on the new
staging root solely for the atomic rename. The renamed target is immediately
sealed back to `0555`. A non-EACCES failure, absent trace, metadata drift,
second retry, non-atomic finalization or any service/database/business action
compiles to `REJECT`.

`n6_immutable_release_install_host_eacces_remediation_v1` compiles one fresh
artifact-only installation only when a frozen, readable host trace proves
`EACCES` for a `0555` staging both within the Release root and when moved to
`/tmp`. It binds the current orphaned staging as immutable evidence but never
reuses it. After validation, only the new staging root may have one owner-only
write window for one rename. Any missing host trace, metadata drift, retry or
runtime/database/business action compiles to `REJECT`.

`n6_immutable_release_privileged_atomic_install_v1` compiles only one separate
host-side helper invocation after its fixed binary SHA/signature, Release
root, staging/target direct-child names and full input attestation match. The
helper must use one parent-dirfd `renameatx_np` with exclusive/no-follow/beneath
flags; shell, copy, overwrite, delete, chmod/xattr/ACL, fallback and every
runtime/database/business action compile to `REJECT`.

`n6_immutable_release_privileged_materialize_and_install_v1` compiles one
fixed `d85df6328bde223e912dabc3bd65e16df984aa45` root-only V2 helper invocation
only after the exact archive path/SHA, manifest path/SHA, source tree,
filesystem validation SHA, 6240-file/45-directory counts, helper attestation,
and orphan evidence hashes are frozen. The archive mode contract accepts only
file modes `0644`/`0664`/`0755`/`0775` and directory modes `0755`/`0775`, then
seals non-executable files to `0444`, executable files to `0555`, and
directories to `0555`. V2 itself creates one new staging under the fixed root,
validates every archive entry before promotion and retains it on failure. Any
other source/hash/count, shell, arbitrary path, overwrite/delete, xattr/ACL,
fallback, retry or runtime/database/business action compiles to `REJECT`.

`n6_immutable_release_privileged_materialize_and_install_f67_v1` compiles one
dedicated f67 helper invocation only after the exact f67 commit/tree,
archive/git-ls-tree/manifest/filesystem and bundle hashes, 6240-file,
45-directory and PAX 1/108 counts, helper signature and orphan evidence are
frozen. The compiled plan contains one root-only `mkdirat` staging creation,
one safe extraction, one sealed validation, one parent-dirfd
`renameatx_np(EXCL|NOFOLLOW|BENEATH)` and one immutable attestation write.
Using the d85 helper, another source/path/hash/count, an old staging, a retry,
or any runtime/database/business operation compiles to `REJECT`.

The compiler output must be YAML:

```yaml
execution_plan:
  plan_id: "example_plan"
  layer_role: "runtime_control"
  risk_level: "low"
  affected_files:
    - "docs/EXAMPLE.md"

  nodes:
    - id: "plan"
      type: "PLAN"
      description: "Define documentation-only change."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "validate"
      type: "VALIDATE"
      description: "Validate scope and file boundary."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "modify"
      type: "MODIFY"
      description: "Create the approved documentation file."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "verify"
      type: "VERIFY"
      description: "Confirm only approved file changed."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "finalize"
      type: "FINALIZE"
      description: "Return final execution status."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

  edges:
    - from: "plan"
      to: "validate"
      reason: "Validation follows planning."

    - from: "validate"
      to: "modify"
      reason: "Modification requires prior validation."

    - from: "modify"
      to: "verify"
      reason: "Verification follows modification."

    - from: "verify"
      to: "finalize"
      reason: "Finalization follows verification."
```

## 6. Golden Rule

No execution without a valid acyclic execution DAG.

### Strategy Center Gate3+ Canonical Compilation

For Strategy Center only, the compiler must derive the current business date
from the unique `for_trade_date` consensus of the latest complete singleton
batches in `v_n6_stock_condition_display_basis`,
`v_n6_index_condition_display_basis`, and
`v_n6_board_condition_display_basis`. Reviewed projections/cards are the
current-date natural-event availability proof. `common_trade_calendar` and
N1-N5 raw tables are forbidden authority; membership is only
`max(trade_date) <= source_trade_date` as-of evidence.

The Gate3+ DAG is strictly:

```text
exact Web strategy-write 1 -> 0 on unchanged d85 Release
  -> current-date single-scope dry-run -> primary -> same-input replay
  -> install/observe exact 5-second evaluator for at least 12 ticks
  -> exact Web strategy-write 0 -> 1 rebind
  -> seven independent remaining-user single-scope CAS migrations
  -> full-user replay/isolation/projection/SSE acceptance
  -> independent catalog-only V1 retirement
```

The bounded scope is dynamic positive principal/user/revision authority; no
historical date or revision identifier may be compiled. Scheduled evaluation
processes at most one principal/user/revision per tick, pending first and active
round-robin. Each remaining-user migration is one transaction and zero retry.
V1 retirement compiles only when every active scope is V2 and pending is zero.
Any all-users transaction, missing reviewed consensus, calendar/raw authority,
virtual-executor operation, cross-user write, second attempt, N1-N5 or trading
path fails compilation. The governance request that adds these policies cannot
execute them.

The leading flag-quiesce node compiles only under
`n6_strategy_center_pre_canary_web_write_quiesce_v1`: exact Web, unchanged d85
Release/paths/environment, evaluator already absent, virtual executor
untouched, one bootout/bootstrap and conditional rollback to frozen flag `1`.

### Strategy Center 30-Day Isolation Decommission Compilation

The compiler applies the Kernel lifecycle registry before historical policy
compilation. Every retired Strategy Center policy id compiles directly to
`FINALIZE(REJECT)`; its historical DAG is audit-only and cannot be reactivated.
Only the following two Strategy Center decommission DAGs are active:

```text
n6_strategy_center_decommission_web_runtime_v1
  PLAN exact Web, frozen source/target immutable Releases and archive scope
  -> VALIDATE write=0, evaluator absent, target removes Strategy Center,
              rollback source frozen, virtual executor/DB/other services zero
  -> MODIFY one exact-Web bootout/bootstrap
  -> VERIFY readiness, stability, write=0, evaluator still absent,
            non-Strategy N6 non-regression and zero forbidden operations
  -> MODIFY optional post-stability evaluator plist/state/log/history archive
  -> VERIFY new archive root is read-only and manifest/hash complete
  -> FINALIZE append-only trace; rollback frozen source only on primary failure

n6_strategy_center_decommission_schema_archive_v1
  PLAN one N6_user transaction, six exact tables, owned sequence/index inventory
  -> VALIDATE Web decommission PASS, write=0, evaluator absent, fresh owner-only
              archive schema, per-table evidence and dedicated 30-day rollback
  -> MODIFY one transaction: move tables/dependents, revoke archive USAGE,
            remove Strategy Center-exclusive triggers/functions
  -> VERIFY row counts/content hashes, DDL/ACL/dependencies, protected objects,
            zero drop/data-DML/retry and rollback deadline
  -> FINALIZE append-only trace; no automatic physical deletion
```

The two DAGs are independent and cannot be combined. Physical deletion after
30 days and canary-heartbeat suspension/removal require separate future
authorization and do not compile under either policy. The governance session
that defines these DAGs has `runtime_execution_requested=false`.
