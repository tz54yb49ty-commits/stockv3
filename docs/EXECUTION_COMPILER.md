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
    `policy_id=n6_strategy_center_display_only_scheduled_evaluator_f464_v1`, or
    `policy_id=n6_strategy_center_schema_migration_maintenance_window_v1`, or
    `policy_id=n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, or
    `policy_id=n6_strategy_center_post_081_v2_catalog_migration_window_v1`, or
    `policy_id=n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, or
    `policy_id=n6_strategy_center_pre_canary_web_write_quiesce_v1`, or
    `policy_id=n6_strategy_center_shadow_activation_grant_v1`, and only after
    every rule in the corresponding named-policy section is structurally
    satisfied. The compiler still performs no
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

The compiler recognizes exactly one recurring F464 N6 display-only evaluator
policy. The superseded 658 policy is historical evidence and cannot compile an
F464 activation:

```text
policy_id = n6_strategy_center_display_only_scheduled_evaluator_f464_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
```

Its DAG remains:

```text
PLAN
  -> VALIDATE current-request automatic-evaluator authorization; exact F464
              commit/tree and runner/planner/worker blobs; frozen Temporal
              Confluence V2 candidate/canonical/bundle lineage; committed
              081/082/083 live predicate; exact Web target, Evaluator source/
              target plist and offline-manifest hashes; exact 78-event
              activation chain; 20260727 natural N6 input; exact
              principal-12/principal-type-human_user/user-11/revision-22/
              revision-no-1/package_1-v2 single-scope canary PASS with every
              CAS match, with user/admin/unknown principal types rejected;
              fresh business zero increment; strategy-write 0; Evaluator
              absent; Virtual Executor untouched
  -> MODIFY atomically replace one validated plist and bootstrap the exact
            absent label once, with zero bootout/kickstart/start/retry;
            launchd may then invoke only the exact bounded run-once runner
  -> VERIFY exact Release/runner/plist/PGSERVICE, StartInterval=5, launchd
            single-instance plus advisory-lock behavior, current-open-day and
            closed-day-no-op gates, per-user isolation, exact DML, readiness,
            no drift, and no forbidden effects; on install or natural
            post-activation acceptance failure, restore the exact frozen source
            plist at most once with label/process absent and never bootstrap 658
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
scheduler_mode = current_open_trade_date_pending_first_active_round_robin
scope_mode = single_scheduler_single_principal_user_revision_per_tick
database_role = n6_strategy_worker
pgservice = n6_strategy_worker
launch_agent_label = com.ashare-v3.n6.strategy-center-evaluator-v1
start_interval_seconds = 5
run_at_load = false
keep_alive = false
max_runtime_seconds = 12
max_scopes_per_tick = 1
pending_precedes_active = true
active_scope_cursor_mode = persistent_round_robin
all_users_transaction = false
```

The compiler returns `failed` before Kernel evaluation when the exact 20260727
natural-input canary scope or any CAS predicate is incomplete; fresh business
increment is nonzero; any singleton differs from one; the activation date is
not the freshly verified current open trade date; F464 Release, runner/planner/
worker blobs, Temporal Confluence V2 lineage, 081/082/083 predicate, Web/
Evaluator plist, offline manifest, activation chain, dependency lock,
runtime-env manifest/filesystem, exact argv, ACL, plist, or concurrency
evidence is incomplete or drifted; runner arguments accept an external
trade date/scope; the database
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
081 schema rollback while a V2 dependency exists. It also fails for the old
policy id, the 658 Release presented as the F464 target, wrong source-target-
source order, any bootout/kickstart/start/retry on the absent-label primary
path, restoring an empty state, or bootstrapping the superseded 658 source.

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

### 4.8 Reviewed-View Date Authority and Post-Canary Write Restore

`n6_strategy_center_reviewed_view_date_authority_084_v1` compiles only one
084 forward transaction with zero retries. The business date is the consensus
`for_trade_date` from the latest complete singleton batches of
`v_n6_stock_condition_display_basis`, `v_n6_index_condition_display_basis`,
and `v_n6_board_condition_display_basis`; `common_trade_calendar` and all
N1-N5 raw tables are forbidden. Source batch lineage and reviewed projection/
card watermarks are frozen, and membership is only an as-of lookup.

`n6_strategy_center_post_canary_web_write_restore_v1` compiles only one exact
Web `0 -> 1` strategy-write rebind after bounded canary PASS, 12 stable
evaluator ticks, pending count zero, and immutable Release/ACL/ownership hashes
unchanged. The evaluator remains quiesced; any extra service, retry, database,
migration, virtual-executor, or trading operation returns `REJECT`.

### 4.9 Named N6 Resumable Dual-Service Bounded-Rebind Compilation

`n6_strategy_center_shadow_activation_grant_v1` compiles only for a later,
independent `runtime_control` request under the accepted parent approval. The
four user-visible stages remain unchanged; `BOUNDED_REBIND` contains two
strictly ordered internal checkpoints.

```text
failed BOUNDED_REBIND + frozen failure evidence
  -> BOUNDED_REBIND_WEB_TARGET planned
  -> install immutable f464
  -> exact Web d85 -> f464 with strategy-write=0
  -> Web target passed
  -> independent current-date bounded canary PASS
  -> BOUNDED_REBIND_EVALUATOR_TARGET planned
  -> exact Evaluator bootstrap on the same f464
```

Before the canary PASS evidence exists, the evaluator target remains
`blocked_pending_canary`; the compiler must not emit its plan or lease. The Web
target requires the second-level immutable supersession, complete SHA chain,
external final-governance attestation, fresh ee2b Web/control-plane anchors,
failed-checkpoint resume evidence and a matching short lease. It contains no
Evaluator operation, kickstart, runner, canary, database, Virtual Executor,
N1-N5, broker or trading node.

### 4.10 Pre-Canary Web Write Quiesce Compilation

`n6_strategy_center_pre_canary_web_write_quiesce_v1` compiles only one exact-Web
flag-only `1 -> 0` rebind on an otherwise unchanged immutable Release. The
Evaluator must already be absent and the Virtual Executor remains untouched.
The policy cannot compile a canary, Evaluator bootstrap, database access,
N1-N5 operation, or trading effect.

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

### 4.8 Named Strategy Center Remaining-Users Pending V2 Revision Compilation

```text
policy_id = n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1
layer_role = N6_user
kernel_decision = ACCEPT
runtime_gate_decision = ACCEPT
phase_mode = create_remaining_post_083_pending_v2_revision_once
```

This policy is parameterized, but never broad: one positive principal, one
user, one active V1 predecessor, one current N6 authority date, and one target
revision. The target revision number is predecessor plus one and its
`previous_revision_id` is an exact CAS. Package keys must be identical to the
predecessor and only versions may change from v1 to v2. The current authority
date comes only from `n6_strategy_center_trade_date_authority_v1`; no fixed
date or membership date may be substituted.

Compilation requires an independently attested immutable owner-isolated
selection creation function. The existing session-token/Web
`n6_btrack_strategy_selection_put` function and hand-written SQL are not an
approved path. If the formal owner function is absent, compilation returns
`scope_expansion_required=owner_selection_function` and `REJECT`.

The mutation plan contains one transaction, one advisory lock, one official
function call, one attempt and zero retries. It writes only the selection
revision and item tables, leaves the revision pending, and proves unchanged
other users and projection/change watermarks. Web PUT, evaluator operation,
virtual-executor operation, activation, catalog/schema/projection/change,
business, trading, and N1-N5 effects are compile-time rejects. A running
evaluator may be observed but cannot be operated by this policy.

### 4.9 N6 B-track Delivery Lane Compilation

New N6 B-track work must compile through exactly one reusable lane declared in
`docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json`:

```text
n6_btrack_delivery_l1_web_readonly_v1
n6_btrack_delivery_l2_n6_business_v1
n6_btrack_delivery_l3_virtual_runtime_v1
```

Compilation requires the four user brief fields `page_or_feature`, `users`,
`expected_behavior`, and `affects_virtual_money_proposals_or_positions`.
Missing, ambiguous, mixed-lane, real-broker, real-order, N6-to-N1-N5 writeback,
automatic-proposal-creation, or automatic-proposal-confirmation requests
compile to `REJECT`.

L1 compiles to an offline implementation/test gate followed by at most one
exact N6 Web immutable-Release rebind gate. It may not compile database,
quote-writer, executor, stop-loss, proposal, order, trade, cash, position, or
lot effects.

When `phase_id=post_decommission_web_readonly_rebind`, L1 compiles a separate
`runtime_control` deployment phase only for an already accepted Web/read-only,
UX-only, non-Strategy, non-regressing candidate whose source and target both
remain decommissioned. Its DAG is:

```text
PLAN
  -> VALIDATE exact L1 ACCEPT; exact source evidence mode, target immutable
              manifest, non-regressing lineage and exact diff;
              strategy-write=0 throughout; retired 307/410/no-store routes;
              evaluator absent; virtual executor disjoint and operation-free;
              one accepted interpreter plus relative-script form and exact
              source/target ProgramArguments and target script
  -> MODIFY one safe Web plist Release-binding replace/swap; one bootout; wait
            >=1 second and prove old job/PID absent; one bootstrap
  -> VERIFY Web readiness and exact retired routes; all forbidden effects=0;
            failure only may enter one frozen-source rollback
  -> FINALIZE append-only trace and PASS/STOP
```

ProgramArguments must remain exactly two byte-identical source/target tokens:
literal `python3` or a frozen absolute immutable non-Release-bound system
interpreter, then relative `scripts/run_n6_user_app.py`. Only
WorkingDirectory/PYTHONPATH Release bindings move source to target. The target
script must resolve inside target and match its immutable manifest entry. An
absolute interpreter compiles only with source/target-identical evidence for
the `/Library` trusted path chain, every in-boundary symlink hop/readlink text,
the resolved canonical regular target, owner/group/mode/flags/ACL/SHA, no
escape/cycle/ambiguity, zero replacement, and effective non-writability of every
object by the frozen Web service principal.

Target always requires a Release-specific immutable manifest. A pre-manifest
legacy source may compile only with read-only reconstructed commit/tree,
canonical-exclusion, complete present-fileset blob/mode, no-extra, sealed and
deterministic object-hash evidence; it is source/rollback-only and cannot be
written back or substitute for target manifest. Missing fields, mixed/extra
argv, interpreter/script or source/target evidence drift, Strategy restoration,
route/plist/lineage/allowlist drift, kickstart, retry, second primary attempt,
downgrade, operation-count drift, or any forbidden effect compiles to `REJECT`.
This remains part of the existing L1 policy and cannot create a one-off policy.

L2 compiles into separately authorized phases: offline implementation and
isolated PG16 verification, one exact N6 migration gate with rollback, one
immutable-Release rebind gate, and read-only acceptance. Migration identity is
the full filename and contract, never the numeric prefix alone. L2 cannot
compile automatic virtual-money effects.

For `phase_id=trigger_status_projection_20260731_backfill`, L2 may additionally
compile one independent `N6_user` historical bounded-consumer gate. It compiles
only when the complete phase object exactly matches
`docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json`: consumer
`n6_trigger_status_projection_v1`, runner
`scripts/run_n6_trigger_status_projection_once.py`, date `20260731`, projection
run `n6_trigger_status_projection_20260731_backfill_v1`, limit/input count
`2296`, outbox range `4103761..4107616`, and event counts `1042/723/194/337`.
The DAG is read-only preflight -> zero-persistence full-batch simulation -> one
execute -> read-only postflight. Before execute, a separate N6-owned exact-run
rollback artifact must pass static and PG16 verification; migration 089's
table-dropping rollback is not acceptable. Compilation rejects any date/input/
runner/argument/allowlist drift, retry, manual SQL, migration, Release/service,
outbox status update, protected-consumer/checkpoint change, `trigger_pct` status
surface, immutable `ActionEligible` payload change, or next-phase bundling. The
governance session can register this phase but cannot compile its execution.

For `phase_id=trigger_status_projection_20260803_recovery`, L2 may compile one
independent `N6_user` current-day bounded-consumer gate only when the complete
phase object exactly matches `docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json` and
policy `n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1`.
It binds date `20260803`, consumer `n6_trigger_status_projection_v1`, runner
`scripts/run_n6_trigger_status_projection_once.py`, projection run
`n6_trigger_status_projection_20260803_recovery_v1`, partition
`trigger-status:20260803`, limit/input count `1769`, frozen outbox range
`4107628..4110567`, event counts `863/587/8/311`, and expected active episode
count `552`. The DAG is read-only preflight -> exact-run rollback artifact
static and PG16 verification -> one execute -> read-only postflight. Writes are
limited to the new current-status table and this consumer's exact inbox and
checkpoint; `common_event_outbox` remains SELECT-only. Compilation rejects
date, N5 proof, census/high-water, runner/argument, allowlist or rollback drift,
retry, manual SQL, migration, Release/service/scheduler, existing projection or
checkpoint changes, `trigger_pct`, ActionEligible payload mutation, or bundled
next-phase work. The governance session can register this phase but cannot
compile or execute it.

For `phase_id=trigger_status_web_immutable_release_rebind`, L2 may compile one
later independent `runtime_control` Web deployment gate only when the complete
phase object exactly matches
`docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json`. Its operation class is
`single_web_immutable_release_rebind`; neither the legacy
`n6_user_web_immutable_release_bounded_rebind_v1` nor L1 /
`post_decommission_web_readonly_rebind` can substitute. The DAG is:

```text
PLAN
  -> VALIDATE exact target 985202144.../f741f0f0... and reviewed 27-file
              lineage; completed 089 and 2296-consumer PASS evidence; unique
              active Web rollback Release/plist/manifest/PID/8786; strategy
              write=0; frozen evaluator baseline; loaded operation-free
              virtual executor; prior successful phase executions=0
  -> MODIFY materialize exactly one fresh immutable Release; apply owner/mode/
            ACL/xattr/flags -> manifest -> seal -> byte verify; replace only
            exact Web Release binding/WorkingDirectory/PYTHONPATH; one bootout
            and one bootstrap
  -> VERIFY target commit/tree/manifest/plist/new PID/cwd/argv/listen 8786;
            unauthenticated Strategy 410 and status-monitor 401 by GET/HEAD
            only; all other routes and non-Web services unchanged
  -> FINALIZE preserve authenticated desktop and 320/375/390/430 DOM
              acceptance as a separate authorized gap
```

Compilation rejects any target, 27-file lineage, prerequisite PASS, source
rollback evidence, business-state, service scope, route, manifest, plist, or
postflight drift; any existing/reused/overwritten target Release; kickstart,
retry, second execution, rollback-target substitution; database/consumer/
migration/rollback/other-service/scheduler/N1-N6 business/trading/browser/push
effect; any `trigger_pct` status surface; non-GET/HEAD curl; or bundling
authenticated browser acceptance. This
governance session registers the phase but cannot compile or perform it.

L3 compiles into separately authorized implementation/regression, migration
and immutable-Release deployment, bounded smoke, confirmed-queue governance,
and continuous-runtime authorization phases. Missing bounded-smoke evidence,
queue disposition, immutable lineage, service-role boundary, full business
audit, or immediate bootout proof compiles to `REJECT`.

Legacy one-off policies remain historical compatibility evidence. The compiler
must not mint a new one-off policy for an ordinary request already covered by
L1, L2, or L3.

## 5. Output Format

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

### 4.8 Reviewed-View Date Authority and Post-Canary Write Restore

`n6_strategy_center_reviewed_view_date_authority_084_v1` compiles only one
084 forward transaction with zero retries. The business date is the consensus
`for_trade_date` from the latest complete singleton batches of
`v_n6_stock_condition_display_basis`, `v_n6_index_condition_display_basis`,
and `v_n6_board_condition_display_basis`; `common_trade_calendar` and all
N1-N5 raw tables are forbidden. Source batch lineage and reviewed projection/
card watermarks are frozen, and membership is only an as-of lookup.

`n6_strategy_center_post_canary_web_write_restore_v1` compiles only one exact
Web `0 -> 1` strategy-write rebind after bounded canary PASS, 12 stable
evaluator ticks, pending count zero, and immutable Release/ACL/ownership hashes
unchanged. The evaluator remains quiesced; any extra service, retry, database,
migration, virtual-executor, or trading operation returns `REJECT`.
