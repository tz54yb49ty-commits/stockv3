# Execution Kernel

## 1. Purpose

The Execution Kernel is the decision-control layer for Codex actions in A股监控系统 v3.

It exists to prevent Codex from executing, modifying, or crossing project boundaries without an explicit decision gate. Every requested task must be parsed, normalized, evaluated, and approved by the Kernel before any file change or execution step is allowed.

The Kernel is documentation-only in this phase. It introduces no runtime logic, no code, no database changes, and no N1-N6 system behavior.

## 2. Kernel Input Schema

```yaml
kernel_input:
  intent:
    description: "What the user is asking Codex to do."
    type: string

  layer_role:
    description: "The project layer in which the request belongs."
    allowed_values:
      - runtime_control
      - N1_ingestion
      - N2_condition
      - N3_market_data
      - N4_trigger
      - N5_action
      - N6_user
    required: true

  affected_files:
    description: "Exact files that may be created or modified."
    type: list[string]

  data_flow:
    description: "Declared direction of system impact."
    allowed_direction: "N1 -> N2 -> N3 -> N4 -> N5 -> N6"
    rule: "Downstream must not mutate upstream; upstream must not perform downstream work."

  risk_level:
    description: "Estimated risk of the requested action."
    allowed_values:
      - low
      - medium
      - high
      - critical
```

## 3. Kernel Decision States

### ACCEPT

The request is clear, scoped to the declared `layer_role`, affects only allowed files, follows N1 -> N6 one-way data flow, and introduces no forbidden runtime execution.

Result: Codex may proceed with the requested action.

### REJECT

The request violates a hard project boundary.

Examples:

```text
cross-layer mutation
runtime execution
unauthorized code changes
touching src/ during documentation-only work
modifying existing files when only new documentation is allowed
```

Result: Codex must not proceed.

### BLOCK

The request may be valid, but required information is missing.

Examples:

```text
missing layer_role
missing affected_files
missing risk_level
unclear data_flow impact
missing authorization for a risky step
```

Result: Codex must stop and request clarification or required evidence.

### ESCALATE

The request requires a human decision, layer switch, or separate gate before it can continue.

Examples:

```text
task belongs to another layer_role
rollback implications are unclear
downstream references may exist
request may affect N1-N6 runtime semantics
```

Result: Codex must stop and hand off with explicit evidence and next-step guidance.

## 4. Hard Validation Rules

```text
cross-layer mutation detection = reject
missing layer_role = block
runtime execution = forbidden
ambiguity = stop
```

Detailed rules:

1. If the request attempts to mutate another layer, the Kernel returns `REJECT`.
2. If `layer_role` is missing or unclear, the Kernel returns `BLOCK`.
3. If the request includes runtime execution, worker startup, database writes, rollback execution, outbox consumption, or real trading, the Kernel returns `REJECT` for this phase.
4. If the request is ambiguous, Codex must stop before modifying files.
5. If the request affects files outside `affected_files`, the Kernel returns `REJECT`.
6. If the request violates one-way N1 -> N6 data flow, the Kernel returns `REJECT`.

### 4.1 N6 Strategy Center Display-Only Bounded Run-Once Exception

This is the only bounded single-user N6 business runtime/database-write exception
recognized by the Kernel. It is an `N6_user` policy, not a `runtime_control`
execution permission. The control-plane
governance task that creates or changes this policy cannot execute it in the same
session.

The following JSON block is the machine-readable authority for static policy tests:

<!-- policy:n6_strategy_center_display_only_bounded_run_once_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_display_only_bounded_run_once_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "runner_basename": "run_n6_strategy_center_once.py",
  "scope_mode": "single_user_revision",
  "database_role": "n6_strategy_worker",
  "virtual_executor_coexistence_contract": {
    "phase_mode": "post_083_maintenance_gate2_bounded_canary",
    "required_selection_revision_id": 20,
    "required_trade_date": "20260723",
    "launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
    "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.virtual-executor-v1.plist",
    "database_role": "n6_virtual_executor",
    "pgservice": "n6_virtual_executor",
    "start_interval_seconds": 5,
    "required_attempt_order": [
      "same_scope_dry_run",
      "primary_execute",
      "same_input_replay"
    ],
    "required_pre_gate_attempt_counts": {
      "pre_gate_dry_run_attempts": 0,
      "pre_gate_primary_execute_attempts": 0,
      "pre_gate_same_input_replay_attempts": 0
    },
    "required_hash_fields": {
      "virtual_executor_label_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_plist_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_release_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_runner_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_pgservice_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_role_acl_sha256": "^[0-9a-f]{64}$",
      "virtual_executor_object_boundary_sha256": "^[0-9a-f]{64}$"
    },
    "required_true_fields": [
      "post_083_maintenance_window_verified",
      "gate2_bounded_canary_verified",
      "virtual_executor_existing_start_interval_verified",
      "virtual_executor_label_frozen",
      "virtual_executor_plist_frozen",
      "virtual_executor_release_frozen",
      "virtual_executor_runner_frozen",
      "virtual_executor_pgservice_frozen",
      "virtual_executor_role_acl_frozen",
      "virtual_executor_object_boundary_frozen",
      "virtual_executor_strategy_center_table_write_disjoint_verified",
      "virtual_executor_strategy_center_function_execute_disjoint_verified",
      "virtual_executor_strategy_center_code_reference_disjoint_verified",
      "virtual_executor_not_operated_verified"
    ],
    "required_false_fields": [
      "virtual_executor_operation_requested",
      "virtual_executor_bootout_requested",
      "virtual_executor_bootstrap_requested",
      "virtual_executor_modification_requested",
      "virtual_executor_label_drift_detected",
      "virtual_executor_plist_drift_detected",
      "virtual_executor_release_drift_detected",
      "virtual_executor_runner_drift_detected",
      "virtual_executor_pgservice_drift_detected",
      "virtual_executor_role_acl_drift_detected",
      "virtual_executor_object_boundary_drift_detected",
      "virtual_executor_strategy_center_table_write_privilege_detected",
      "virtual_executor_strategy_center_function_execute_privilege_detected",
      "virtual_executor_strategy_center_code_reference_detected"
    ],
    "forbidden_strategy_center_write_tables": [
      "n6_user_strategy_selection_revision",
      "n6_user_strategy_selection_item",
      "n6_strategy_package_catalog",
      "n6_strategy_match_projection",
      "n6_strategy_observation_projection",
      "n6_strategy_match_change"
    ],
    "forbidden_strategy_center_execute_scope": "all_formal_strategy_center_functions",
    "required_operation_attempts": 0,
    "normal_start_interval_pid_runs_change_is_configuration_drift": false
  },
  "required_scope_fields": [
    "principal_id",
    "user_id",
    "selection_revision_id"
  ],
  "observation_dml_contract": {
    "table": "n6_strategy_observation_projection",
    "operations": [
      "select_for_update",
      "insert",
      "update",
      "delete"
    ],
    "scope_predicate_fields": [
      "selection_revision_id",
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date"
    ],
    "insert_scope_columns": [
      "selection_revision_id",
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date"
    ],
    "unique_grain_081": [
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date",
      "stock_identity_key",
      "action_episode_key",
      "coherence_episode_key",
      "observation_kind",
      "selection_revision_id"
    ],
    "same_hash_replay_behavior": "unchanged",
    "qualified_surface_kind": "qualified_match",
    "observation_surface_kind": "observation",
    "same_episode_surface_mode": "mutually_exclusive",
    "change_dedup_required": true
  },
  "rollback_contract": {
    "allowed_mutation_resources": [],
    "database_mutation_allowed": false,
    "observation_delete_allowed": false,
    "schema_081_rollback_reject_if_v2_dependencies": [
      "selection_revision",
      "match_projection",
      "observation_projection",
      "match_change"
    ]
  },
  "trade_date_field": "trade_date",
  "current_trade_date_field": "current_trade_date",
  "required_strategy_write_flag_value": "0",
  "required_singleton_counts": {
    "principal_count": 1,
    "user_count": 1,
    "selection_revision_count": 1,
    "trade_date_count": 1
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "display_only",
    "current_trade_date_verified",
    "strategy_write_zero_verified",
    "active_immutable_release_verified",
    "release_commit_verified",
    "release_tree_verified",
    "release_hash_verified",
    "bounded_runner_present_in_active_release",
    "same_scope_dry_run_passed",
    "input_watermark_frozen",
    "plan_hash_frozen",
    "strategy_worker_acl_verified",
    "before_after_scope_frozen",
    "cas_enabled",
    "rollback_defined",
    "observation_select_for_update_scope_predicate_verified",
    "observation_insert_scope_columns_verified",
    "observation_update_scope_predicate_verified",
    "observation_delete_scope_predicate_verified",
    "observation_unique_grain_081_verified",
    "same_hash_replay_unchanged_verified",
    "qualified_observation_surface_mutually_exclusive_verified",
    "observation_change_surface_kind_verified",
    "observation_change_dedup_verified",
    "same_scope_input_run_id_replay_verified",
    "web_observation_function_only_verified",
    "virtual_executor_observation_write_disjoint_verified",
    "virtual_executor_observation_code_reference_disjoint_verified",
    "observation_rows_preserved_by_rollback",
    "v2_dependency_blocks_081_schema_rollback_verified"
  ],
  "required_false_fields": [
    "all_users_mode",
    "release_drift_detected",
    "acl_drift_detected",
    "selection_revision_drift_detected",
    "input_watermark_drift_detected",
    "long_running_worker_requested",
    "launch_agent_install_or_start_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "n1_n5_write_requested",
    "outbox_inbox_checkpoint_mutation_requested",
    "concurrent_runtime_change",
    "strategy_write_nonzero_detected",
    "fifth_write_table_requested",
    "cross_scope_observation_write_detected",
    "cross_trade_date_observation_write_detected",
    "observation_scope_predicate_missing",
    "same_episode_dual_surface_detected",
    "duplicate_observation_change_detected",
    "web_observation_table_write_privilege_detected",
    "virtual_executor_observation_table_write_privilege_detected",
    "virtual_executor_observation_code_reference_detected",
    "observation_delete_rollback_requested",
    "schema_081_rollback_with_v2_dependency_requested"
  ],
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_strategy_match_projection",
    "n6_strategy_observation_projection",
    "n6_strategy_match_change"
  ],
  "primary_execute_attempts": 1,
  "maximum_idempotence_replay_attempts": 1,
  "idempotence_replay_requires_same_scope": true,
  "idempotence_replay_requires_same_input": true,
  "idempotence_replay_requires_same_run_id": true
}
```
<!-- policy:n6_strategy_center_display_only_bounded_run_once_v1:end -->

Evaluation is fail-closed and ordered:

1. The current request must explicitly authorize this policy and declare
   `layer_role=N6_user`.
2. `principal_id`, `user_id`, and `selection_revision_id` must each be present
   exactly once and be strict positive integers. The request must declare one
   trade date, and it must equal the freshly verified current trade date.
3. The active immutable Release must independently pass commit, tree, hash, and
   bounded-runner verification. A historical validation artifact alone is not
   active-Release proof.
4. The same-scope dry-run, input watermark, plan hash, dedicated
   `n6_strategy_worker` ACL, before/after scope, CAS, and rollback evidence must
   all be frozen before primary execute.
5. If the virtual executor is loaded or running, coexistence is allowed only
   for `phase_mode=post_083_maintenance_gate2_bounded_canary` and exact
   `selection_revision_id=20` on current trade date `20260723`, with dry-run,
   primary, and replay attempts all verified zero before Gate2 begins. Its exact
   label, plist, immutable Release,
   runner, `PGSERVICE=n6_virtual_executor`, role ACL, and Strategy Center object
   boundary must be hash-frozen. The role must have no write privilege on the
   declared selection/catalog/projection/observation/change tables, no
   `EXECUTE` on formal Strategy Center functions, and its code must contain no
   reference to those objects. This task must perform zero virtual-executor
   operations. A normal existing `StartInterval=5` PID or runs-counter change
   alone is not configuration drift.
6. The declared database write allowlist must equal the four strategy tables
   above. Observation `SELECT FOR UPDATE`, `INSERT`, `UPDATE`, and `DELETE`
   must each remain bound to the exact principal/type/user/revision/trade-date
   scope; inserts must carry those same scope columns. The 081 unique grain,
   same-hash unchanged replay, qualified/observation episode exclusivity,
   observation change-surface identity, and change dedup must all be verified.
   Any fifth table or missing predicate returns `REJECT`.
7. At most one primary execute and one replay are permitted. In the post-083
   coexistence mode the exact order is same-scope dry-run, primary execute, then
   same-input replay. A replay is allowed
   only for the same principal/user/revision/trade-date, input, and evaluator
   run id.
8. Any true forbidden field, missing coexistence evidence, virtual-executor
   operation, configuration/ACL/object-boundary/runner/Release/label drift,
   extra write table, general
   N6/all-users mode, or scope ambiguity returns `REJECT`.

This policy never permits proposal, order, trade, position, cash, real-broker,
N1-N5, outbox/inbox/checkpoint, long-running worker, LaunchAgent, virtual
executor modification/stop/start, migration, or schema behavior. It permits
only the fail-closed coexistence of the already-scheduled exact virtual executor
described above and grants that executor no observation table authority or code
reference. Web access remains function-only. Rollback preserves observation
rows, and an 081 schema rollback is rejected while any V2 dependency exists.

### 4.2 N6 Web Immutable Release Bounded-Rebind Exception

This is the only `runtime_control` service-rebind exception recognized by the
Kernel. It changes no N1-N6 business data and grants no evaluator or database
authority. A governance task that creates or changes this policy cannot execute
it in the same session.

The following JSON block is the machine-readable authority for static policy tests:

<!-- policy:n6_user_web_immutable_release_bounded_rebind_v1:begin -->
```json
{
  "policy_id": "n6_user_web_immutable_release_bounded_rebind_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "scope_mode": "single_launch_agent_single_source_target_release",
  "launch_agent_label": "com.ashare-v3.n6.user-web",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
  "service_port": 8786,
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_name_pattern": "^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$",
  "required_resource_fields": [
    "source_release_path",
    "target_release_path"
  ],
  "required_singleton_counts": {
    "service_count": 1,
    "launch_agent_count": 1,
    "source_release_count": 1,
    "target_release_count": 1
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "source_release_immutable_verified",
    "source_release_commit_verified",
    "source_release_tree_verified",
    "source_release_archive_hash_verified",
    "source_release_manifest_hash_verified",
    "target_release_immutable_verified",
    "target_release_commit_verified",
    "target_release_tree_verified",
    "target_release_archive_hash_verified",
    "target_release_manifest_hash_verified",
    "target_no_lineage_regression_verified",
    "current_pid_frozen",
    "current_ppid_frozen",
    "current_argv_frozen",
    "current_cwd_frozen",
    "current_plist_sha_frozen",
    "current_plist_owner_group_mode_frozen",
    "current_plist_acl_xattr_frozen",
    "current_environment_frozen",
    "launchd_ownership_verified",
    "target_plist_lint_passed",
    "target_plist_hash_verified",
    "target_plist_only_release_paths_changed",
    "owner_group_mode_acl_xattr_preservation_defined",
    "state_driven_teardown_defined",
    "old_pid_exit_required_before_bootstrap",
    "job_absence_required_before_bootstrap",
    "readiness_contract_frozen",
    "route_contract_frozen",
    "stability_window_frozen",
    "automatic_rollback_contract_frozen",
    "rollback_restores_frozen_source_only",
    "strategy_write_flag_preserved",
    "strategy_evaluator_unloaded_verified",
    "virtual_executor_unloaded_verified",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "runtime_ownership_ambiguous",
    "multiple_services_requested",
    "release_drift_detected",
    "plist_drift_detected",
    "environment_drift_detected",
    "lineage_regression_detected",
    "immutable_release_content_modification_requested",
    "extra_environment_change_requested",
    "other_launch_agent_touched",
    "fixed_sleep_bootstrap_requested",
    "primary_retry_requested",
    "signal_or_kill_requested",
    "long_running_worker_requested",
    "strategy_evaluator_execute_requested",
    "strategy_evaluator_start_requested",
    "virtual_executor_start_requested",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "selection_projection_change_touched",
    "outbox_inbox_checkpoint_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "n1_n6_business_mutation_requested",
    "concurrent_runtime_change"
  ],
  "allowed_mutation_resources": [
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
    "gui/current-user/com.ashare-v3.n6.user-web"
  ],
  "allowed_runtime_operations": [
    "install_validated_target_plist",
    "launchctl_bootout_exact_label",
    "state_driven_wait_for_pid_and_job_absence",
    "launchctl_bootstrap_exact_plist",
    "readiness_and_stability_probe",
    "rollback_restore_frozen_source_plist",
    "rollback_bootout_exact_label",
    "rollback_bootstrap_exact_plist"
  ],
  "primary_bootout_attempts": 1,
  "primary_bootstrap_attempts": 1,
  "maximum_primary_retries": 0,
  "maximum_rollback_attempts": 1,
  "rollback_requires_primary_failure": true,
  "rollback_requires_frozen_source": true,
  "teardown_timeout_seconds": 30,
  "readiness_timeout_seconds": 60,
  "stability_window_seconds": 30,
  "required_strategy_write_flag_value": "1",
  "required_login_redirect_path": "/n6/login",
  "required_route_expectations": {
    "/n6/app/strategy-center": 302,
    "/api/n6/app/v3/strategy-center": 401,
    "/n6/app/signals": 302
  }
}
```
<!-- policy:n6_user_web_immutable_release_bounded_rebind_v1:end -->

Evaluation is fail-closed and ordered:

1. The current request must explicitly authorize this policy and declare
   `layer_role=runtime_control`.
2. The exact label, plist path, port, source Release, target Release, singleton
   counts, mutation resources, and operation list must match the policy. Source
   and target Release paths must be distinct direct children of the approved
   Release root, match the immutable Release name pattern, and be absolute.
3. Both Releases must independently pass commit, tree, archive hash, manifest
   hash, and immutable-content verification. The target must prove that it does
   not discard any valid source-lineage increment.
4. PID, PPID, argv, cwd, plist SHA/metadata, environment, and launchd ownership
   must be freshly frozen. Ownership ambiguity or any concurrent drift rejects
   the request before plist installation or `launchctl` mutation.
5. The primary path permits exactly one bootout and one bootstrap, with no
   primary retry. Bootstrap is forbidden until the old PID is absent and
   `launchctl print` proves the job absent; fixed-delay substitution is rejected.
6. A rollback attempt is optional and capped at one. It is allowed only after a
   proven primary health failure and may restore only the frozen source
   plist/Release using at most one rollback bootout/bootstrap pair.
7. The declared readiness, route, stability, strategy-write-flag, evaluator,
   virtual-executor, and before/after trace evidence must remain valid through
   finalization. Any extra service, environment, Release, database, migration,
   evaluator, worker, N1-N6 business, or trading effect returns `REJECT`.

This policy never authorizes evaluator execution, database access, migration,
N1-N6 business mutation, proposal/order/trade/position/cash, real broker,
outbox/inbox/checkpoint mutation, long-running worker, another LaunchAgent, or
modification of immutable Release content.

### 4.3 N6 Strategy Center Display-Only Scheduled Evaluator Exception

This is the only recurring N6 evaluator exception recognized by the Kernel. It
is an `N6_user` policy with one exact LaunchAgent label, not a general
`runtime_control` service permission. The control-plane governance task that
creates or changes this policy cannot execute it in the same session. Activation
requires a separate, currently authorized `N6_user` gate after the bounded
single-user canary in section 4.1 has passed in full.

The following JSON block is the machine-readable authority for static policy tests:

<!-- policy:n6_strategy_center_display_only_scheduled_evaluator_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_display_only_scheduled_evaluator_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "scope_mode": "single_scheduler_single_principal_user_revision_per_tick",
  "scheduler_mode": "current_open_trade_date_pending_first_active_round_robin",
  "launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_name_pattern": "^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$",
  "runtime_env_root": "/Users/chuanfuchen/.local/share/ashare-v3/runtime-envs/n6-b-track",
  "state_root": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track",
  "service_file": "/Users/chuanfuchen/.config/ashare-v3/postgresql/pg_service.conf",
  "pass_file": "/Users/chuanfuchen/.config/ashare-v3/postgresql/n6_strategy_worker.pgpass",
  "runner_basename": "run_n6_strategy_center_auto_once.py",
  "planner_basename": "plan_n6_strategy_center_launchd.py",
  "required_source_authority_commits": [
    "dfb5b04a9fd771377369344c6d27da9292ef496f",
    "995e4803a9b639f7d4f6ed9b93b7a2455c8bff15"
  ],
  "required_capability_ancestor_commit": "c7bd4a819646d9921e2268cdf46442022298f06c",
  "required_dto_fix_ancestor_commit": "c2974d6a72674c464079101872fd70242f42ffa5",
  "required_membership_asof_ancestor_commit": "10718f21dd6ec35b171a1a9a823c2cf24aaecb9a",
  "required_stable_replay_ancestor_commit": "335cdd8eaf0aa17ba85e611f6c716af60368ffd8",
  "required_single_scope_parent_commit": "2d89c45b2afeb0960d514553d5cc10210452f91a",
  "required_integrated_implementation_commit": "658ebb3995a7c539ac211258c378af6499635df4",
  "required_integrated_implementation_tree": "016f154e6716ce0c4f2c7dcee74808e9f95c6dc9",
  "required_release_git_blobs": {
    "scripts/run_n6_strategy_center_auto_once.py": "e8dc2c5d1f959e590ec1ea9431354e2ce1c18017",
    "scripts/plan_n6_strategy_center_launchd.py": "d195b4800e1dc036a25756ec43434fe3bdcb9774",
    "requirements/n6_strategy_evaluator_py311.lock.txt": "1365d5f667144149dcacc5e38d31b0c65d060759",
    "requirements/n6_strategy_evaluator_py311.wheel-manifest.v1.json": "05dd4dc5b87dc27fb00618fb77ba36b3e5aed2c6",
    "src/ashare_v3/web/n6_app_v1.py": "fc1c43ca88e15d7e684f9a9daaaf49717730161c",
    "src/ashare_v3/user/strategy_center_worker.py": "b5130d845c8248e05f3964413fcc343b03c45671",
    "tests/test_n6_strategy_center_auto.py": "831b97013c4994e6e0c059c10b6bc3d8d99e2d8e",
    "tests/test_n6_strategy_center_launchd_plan.py": "f22abd6ccd2a79f282b1e2a735753fb2cb314ab2",
    "tests/test_n6_strategy_center_worker.py": "b9d904c7a078dc50800abf183d436825d16d1578",
    "tests/test_n6_user_app.py": "acecbf97cc113038e4263a5de5cda905570a037b",
    "sql/080_n6_strategy_membership_asof_constraint.sql": "a650d41d511ed02acbeb04dda132e5c6a3fe086a",
    "sql/080_n6_strategy_membership_asof_constraint_rollback.sql": "f2e96719a9869018c70ee72360fd05ff38faaf18",
    "tests/test_n6_strategy_membership_asof_constraint_080.py": "149c6292f7239f8d0f10eb1eb60c9a0d0d28ad8a"
  },
  "database_role": "n6_strategy_worker",
  "pgservice_value": "n6_strategy_worker",
  "timezone": "Asia/Shanghai",
  "start_interval_seconds": 5,
  "max_scopes_per_tick": 1,
  "transaction_scope": "single_principal_user_revision",
  "observation_dml_contract": {
    "table": "n6_strategy_observation_projection",
    "operations": [
      "select_for_update",
      "insert",
      "update",
      "delete"
    ],
    "scope_predicate_fields": [
      "selection_revision_id",
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date"
    ],
    "insert_scope_columns": [
      "selection_revision_id",
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date"
    ],
    "unique_grain_081": [
      "principal_id",
      "principal_type",
      "user_id",
      "trade_date",
      "stock_identity_key",
      "action_episode_key",
      "coherence_episode_key",
      "observation_kind",
      "selection_revision_id"
    ],
    "same_hash_replay_behavior": "unchanged",
    "qualified_surface_kind": "qualified_match",
    "observation_surface_kind": "observation",
    "same_episode_surface_mode": "mutually_exclusive",
    "change_dedup_required": true
  },
  "rollback_contract": {
    "allowed_mutation_resources": [
      "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist",
      "gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1"
    ],
    "database_mutation_allowed": false,
    "observation_delete_allowed": false,
    "schema_081_rollback_reject_if_v2_dependencies": [
      "selection_revision",
      "match_projection",
      "observation_projection",
      "match_change"
    ]
  },
  "pending_scope_order": [
    "selection_revision_id",
    "principal_id",
    "user_id"
  ],
  "active_scope_order": [
    "selection_revision_id",
    "principal_id",
    "user_id"
  ],
  "active_scope_cursor_mode": "persistent_round_robin",
  "failure_queue_behavior": "retain_selected_and_remaining",
  "evaluation_budget_seconds": 11.5,
  "evidence_grace_seconds": 0.5,
  "required_canary_policy_id": "n6_strategy_center_display_only_bounded_run_once_v1",
  "canary_trade_date_contract": "must_equal_current_trade_date",
  "canary_freshness_contract": "fresh_current_trade_date_exact_release_only",
  "canary_release_contract": "must_match_exact_required_release",
  "historical_canary_trade_dates": [
    "20260722"
  ],
  "historical_canary_authority": "evidence_only_no_activation",
  "trade_date_field": "trade_date",
  "current_trade_date_field": "current_trade_date",
  "onsite_current_date_field": "onsite_asia_shanghai_date",
  "trade_calendar_date_field": "common_trade_calendar_trade_date",
  "trade_calendar_open_field": "common_trade_calendar_is_open",
  "required_release_fields": [
    "release_path"
  ],
  "required_runtime_env_fields": [
    "runtime_env_path"
  ],
  "required_hash_fields": {
    "release_commit_sha": "^[0-9a-f]{40}$",
    "release_tree_sha": "^[0-9a-f]{40}$",
    "release_archive_sha256": "^[0-9a-f]{64}$",
    "release_manifest_sha256": "^[0-9a-f]{64}$",
    "release_filesystem_sha256": "^[0-9a-f]{64}$",
    "runner_blob_sha256": "^[0-9a-f]{64}$",
    "planner_blob_sha256": "^[0-9a-f]{64}$",
    "runner_argv_sha256": "^[0-9a-f]{64}$",
    "launch_agent_plist_sha256": "^[0-9a-f]{64}$",
    "dependency_lock_sha256": "^[0-9a-f]{64}$",
    "runtime_env_manifest_sha256": "^[0-9a-f]{64}$",
    "runtime_env_filesystem_sha256": "^[0-9a-f]{64}$",
    "bounded_canary_artifact_sha256": "^[0-9a-f]{64}$",
    "acl_evidence_sha256": "^[0-9a-f]{64}$",
    "before_state_sha256": "^[0-9a-f]{64}$",
    "after_state_sha256": "^[0-9a-f]{64}$",
    "readiness_evidence_sha256": "^[0-9a-f]{64}$",
    "rollback_contract_sha256": "^[0-9a-f]{64}$",
    "concurrency_baseline_sha256": "^[0-9a-f]{64}$"
  },
  "required_singleton_counts": {
    "release_count": 1,
    "launch_agent_count": 1,
    "scheduler_runner_count": 1,
    "database_role_count": 1,
    "bounded_canary_principal_count": 1,
    "bounded_canary_user_count": 1,
    "bounded_canary_selection_revision_count": 1,
    "selected_principal_count": 1,
    "selected_user_count": 1,
    "selected_revision_count": 1,
    "scope_transaction_count": 1,
    "evaluation_call_count": 1
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "automatic_evaluator_authorized_current_request",
    "display_only",
    "bounded_canary_dry_run_passed",
    "bounded_canary_primary_passed",
    "bounded_canary_same_input_replay_passed",
    "bounded_canary_same_scope_replay_passed",
    "bounded_canary_projection_acceptance_passed",
    "bounded_canary_sse_acceptance_passed",
    "bounded_canary_result_frozen",
    "bounded_canary_trade_date_matches_current_verified",
    "bounded_canary_current_open_trade_date_verified",
    "bounded_canary_exact_release_verified",
    "bounded_canary_fresh_evidence_verified",
    "strategy_write_zero_verified",
    "onsite_asia_shanghai_current_date_verified",
    "release_immutable_verified",
    "release_commit_verified",
    "release_tree_verified",
    "release_archive_hash_verified",
    "release_manifest_hash_verified",
    "release_filesystem_hash_verified",
    "runner_present_in_release_verified",
    "runner_executable_verified",
    "runner_blob_hash_verified",
    "planner_present_in_release_verified",
    "planner_blob_hash_verified",
    "planner_exact_output_verified",
    "source_authority_equivalence_verified",
    "capability_ancestor_verified",
    "dto_fix_ancestor_verified",
    "membership_asof_080_ancestor_verified",
    "stable_replay_ancestor_verified",
    "single_scope_direct_parent_verified",
    "membership_asof_080_blobs_verified",
    "strategy_center_worker_blob_verified",
    "deadline_12s_runner_planner_blobs_verified",
    "integrated_implementation_commit_tree_verified",
    "release_git_blobs_verified",
    "runner_exact_argv_verified",
    "runner_rejects_external_trade_date",
    "runner_rejects_external_scope",
    "runner_binds_asia_shanghai_current_date",
    "runner_uses_source_fingerprint_attempt_run_id",
    "single_scope_per_tick_verified",
    "single_scope_transaction_verified",
    "pending_scope_order_verified",
    "pending_precedes_active_verified",
    "active_round_robin_cursor_verified",
    "scope_cursor_restart_restore_verified",
    "failure_preserves_scope_queue_verified",
    "runtime_budget_split_verified",
    "all_users_transaction_absent_verified",
    "current_trade_date_verified",
    "current_trade_date_open_verified",
    "trade_calendar_fresh_verified",
    "per_user_selection_activation_only",
    "per_user_projection_transaction_boundary_verified",
    "cross_user_leakage_guard_verified",
    "strategy_worker_acl_verified",
    "pgservice_only_verified",
    "dependency_lock_verified",
    "runtime_env_manifest_verified",
    "runtime_env_filesystem_verified",
    "write_allowlist_verified",
    "launchd_single_instance_verified",
    "advisory_lock_verified",
    "advisory_lock_fail_closed_verified",
    "keep_alive_false_verified",
    "run_at_load_false_verified",
    "target_label_absent_before_install_verified",
    "target_plist_absent_before_install_verified",
    "closed_day_noop_verified",
    "before_state_frozen",
    "readiness_contract_frozen",
    "canary_contract_frozen",
    "rollback_contract_frozen",
    "rollback_restores_absent_prior_state_only",
    "rollback_preserves_strategy_audit_rows",
    "concurrency_baseline_frozen",
    "virtual_executor_unloaded_verified",
    "standing_authorization_scope_frozen",
    "before_after_trace_defined",
    "input_watermark_frozen",
    "plan_hash_frozen",
    "selection_cas_verified",
    "observation_select_for_update_scope_predicate_verified",
    "observation_insert_scope_columns_verified",
    "observation_update_scope_predicate_verified",
    "observation_delete_scope_predicate_verified",
    "observation_unique_grain_081_verified",
    "same_hash_replay_unchanged_verified",
    "qualified_observation_surface_mutually_exclusive_verified",
    "observation_change_surface_kind_verified",
    "observation_change_dedup_verified",
    "same_scope_input_run_id_replay_verified",
    "web_observation_function_only_verified",
    "virtual_executor_observation_write_disjoint_verified",
    "virtual_executor_observation_code_reference_disjoint_verified",
    "observation_rows_preserved_by_rollback",
    "v2_dependency_blocks_081_schema_rollback_verified"
  ],
  "required_false_fields": [
    "bounded_canary_missing_or_failed",
    "historical_canary_activation_requested",
    "bounded_canary_trade_date_mismatch_detected",
    "bounded_canary_release_mismatch_detected",
    "bounded_canary_stale_evidence_detected",
    "strategy_write_nonzero_detected",
    "onsite_current_date_drift_detected",
    "trade_calendar_date_mismatch_detected",
    "non_current_trade_date_requested",
    "non_open_trade_date_write_requested",
    "external_trade_date_argument_requested",
    "external_scope_argument_requested",
    "release_drift_detected",
    "commit_tree_archive_manifest_filesystem_drift_detected",
    "runner_blob_or_argv_drift_detected",
    "planner_blob_or_output_drift_detected",
    "source_authority_or_git_blob_drift_detected",
    "capability_ancestor_missing_or_drifted",
    "dto_fix_ancestor_missing_or_drifted",
    "membership_asof_080_ancestor_missing_or_drifted",
    "stable_replay_ancestor_missing_or_drifted",
    "single_scope_parent_missing_or_drifted",
    "membership_asof_080_blob_drift_detected",
    "strategy_center_worker_blob_drift_detected",
    "deadline_12s_runner_planner_blob_drift_detected",
    "more_than_one_scope_per_tick_requested",
    "all_users_transaction_requested",
    "pending_scope_order_drift_detected",
    "active_scope_cursor_drift_detected",
    "scope_queue_advanced_on_failure",
    "runtime_budget_split_drift_detected",
    "integrated_implementation_commit_tree_drift_detected",
    "runtime_env_or_dependency_drift_detected",
    "plist_drift_detected",
    "acl_drift_detected",
    "pgservice_drift_detected",
    "write_allowlist_drift_detected",
    "overlap_detected",
    "advisory_lock_bypass_requested",
    "other_launch_agent_touched",
    "mutable_code_requested",
    "primary_retry_requested",
    "migration_or_schema_requested",
    "n1_n5_write_requested",
    "outbox_inbox_checkpoint_mutation_requested",
    "account_mutation_requested",
    "cash_mutation_requested",
    "position_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "real_broker_connected",
    "voice_mobile_sim_requested",
    "virtual_executor_loaded_or_running",
    "other_database_role_requested",
    "raw_dsn_or_password_environment_requested",
    "inherited_environment_requested",
    "cross_user_write_detected",
    "rollback_database_mutation_requested",
    "concurrent_runtime_change",
    "fifth_write_table_requested",
    "cross_scope_observation_write_detected",
    "cross_trade_date_observation_write_detected",
    "observation_scope_predicate_missing",
    "same_episode_dual_surface_detected",
    "duplicate_observation_change_detected",
    "web_observation_table_write_privilege_detected",
    "virtual_executor_observation_table_write_privilege_detected",
    "virtual_executor_observation_code_reference_detected",
    "observation_delete_rollback_requested",
    "schema_081_rollback_with_v2_dependency_requested"
  ],
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_strategy_match_projection",
    "n6_strategy_observation_projection",
    "n6_strategy_match_change"
  ],
  "allowed_mutation_resources": [
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist",
    "gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1"
  ],
  "allowed_runtime_operations": [
    "install_exact_validated_plist",
    "launchctl_bootstrap_exact_label",
    "startinterval_invoke_exact_scheduled_run_once",
    "readiness_and_non_overlap_probe",
    "rollback_bootout_exact_label",
    "rollback_remove_installed_plist"
  ],
  "required_plist_values": {
    "StartInterval": 5,
    "ThrottleInterval": 5,
    "KeepAlive": false,
    "RunAtLoad": false,
    "ProcessType": "Background",
    "Umask": 63
  },
  "required_database_service_arguments": {
    "PGPASSFILE": "/Users/chuanfuchen/.config/ashare-v3/postgresql/n6_strategy_worker.pgpass",
    "PGSERVICE": "n6_strategy_worker",
    "PGSERVICEFILE": "/Users/chuanfuchen/.config/ashare-v3/postgresql/pg_service.conf"
  },
  "required_env_launcher": [
    "/usr/bin/env",
    "-i"
  ],
  "runtime_python_relative_path": "bin/python3.11",
  "required_runtime_state_paths": {
    "state_path": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/evaluator-state.json",
    "singleton_lock_path": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/evaluator.lock",
    "json_report_path": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/latest-report.json",
    "history_path": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/history.jsonl"
  },
  "required_signal_source_user_id": 1,
  "required_max_runtime_seconds": 12,
  "required_strategy_write_flag_value": "0",
  "required_runner_flags": [
    "--execute",
    "--runtime-authorized"
  ],
  "forbidden_runner_arguments": [
    "--trade-date",
    "--evaluator-run-id",
    "--dsn"
  ],
  "closed_day_behavior": "fail_closed_noop_no_dml",
  "primary_install_attempts": 1,
  "primary_bootstrap_attempts": 1,
  "maximum_primary_retries": 0,
  "maximum_rollback_attempts": 1,
  "rollback_requires_readiness_failure": true,
  "rollback_restores_absent_prior_state": true,
  "scheduled_tick_requires_fresh_gate": true
}
```
<!-- policy:n6_strategy_center_display_only_scheduled_evaluator_v1:end -->

Evaluation is fail-closed and ordered:

1. The current request must explicitly authorize automatic strategy evaluation,
   declare `layer_role=N6_user`, and identify this exact policy.
2. A fresh bounded canary for the current open trade date must prove one
   principal, one user, one selection revision, dry-run, primary commit,
   same-scope/same-input replay, projection, and SSE acceptance against the exact
   pinned Release commit, tree, archive, manifest, and filesystem. Its
   `canary_trade_date` must equal the onsite `current_trade_date`. The frozen
   20260722 artifact is historical evidence only and cannot authorize activation
   for 20260723 or any later trade date. A historical PASS label without a fresh
   current-date exact-Release artifact hash is insufficient. The matching
   `common_trade_calendar_trade_date` row must also have `is_open=true`; another
   date's calendar evidence cannot satisfy this gate.
3. One direct child of the approved Release root must independently pass exact
   integrated commit `658ebb3995a7c539ac211258c378af6499635df4`, integrated
   tree `016f154e6716ce0c4f2c7dcee74808e9f95c6dc9`, archive, manifest,
   filesystem, the thirteen critical deployed Git blobs pinned above,
   runner/planner SHA256,
   argv, and immutable Release verification. Commit
   `2d89c45b2afeb0960d514553d5cc10210452f91a` must be the verified direct parent
   and single-scope source, but a 2d89 Release is no longer deployable. Commit
   `335cdd8eaf0aa17ba85e611f6c716af60368ffd8` remains the verified stable-replay
   ancestor. Commit
   `10718f21dd6ec35b171a1a9a823c2cf24aaecb9a` remains the verified 080
   membership-as-of ancestor.
   Commit `c2974d6a72674c464079101872fd70242f42ffa5` remains the verified DTO-fix
   ancestor. Commit
   `c7bd4a819646d9921e2268cdf46442022298f06c` remains a verified capability
   ancestor. The imported dfb5b04a/995e4803 source authorities remain provenance
   only; none can
   substitute for the 658 integrated commit/tree or deployed critical blobs.
   The single-scope runner, strategy-center worker, and their static fixtures are
   explicit release-integrity gates.
   The 080 forward/rollback/test blobs are presence and integrity gates only;
   this policy still grants no migration or schema execution. The
   frozen dependency lock
   and the isolated Python 3.11 runtime environment must pass manifest/filesystem
   verification.
   The exact runner is
   `run_n6_strategy_center_auto_once.py`, and the only planner is
   `plan_n6_strategy_center_launchd.py`; the runner accepts no external trade-date
   or scope argument.
4. Activation is allowed only on the freshly verified current open trade date.
   Each tick derives the `Asia/Shanghai` current date and a deterministic
   attempt-scoped run id from trade date, source fingerprint, Release, policy,
   trigger kind, and the selected principal/user/revision. On a non-open day the
   already installed runner must return the declared no-DML no-op; it receives
   no write authority.
5. A work-bearing tick may select exactly one principal/user/selection revision,
   call the evaluator once, and open only that scope's transaction; a no-op tick
   selects zero. Pending scopes always precede active scopes and use stable
   `(selection_revision_id, principal_id, user_id)` order. Active scopes use the
   same order through a persisted round-robin cursor, one scope per tick. A failed
   evaluation must retain the selected scope and every remaining scope without
   advancing the cursor. An all-users transaction is forbidden. Selection
   activation and projection remain per-user, and the write allowlist must equal
   the four N6 strategy tables above. Observation `SELECT FOR UPDATE`, `INSERT`,
   `UPDATE`, and `DELETE` must carry the complete principal/type/user/revision/
   current-open-trade-date scope and the 081 unique grain. Observation output
   must be mutually exclusive with the qualified surface for the same episode,
   use `surface_kind=observation`, deduplicate change rows, and preserve
   watermark/plan-hash/selection-CAS plus same-scope/input/run-id and same-hash
   unchanged replay.
6. The exact plist must use `StartInterval=5`, `ThrottleInterval=5`,
   `KeepAlive=false`, `RunAtLoad=false`, `ProcessType=Background`, `Umask=077`,
   and the planner's exact immutable argv. The argv starts with `/usr/bin/env -i`,
   uses the fixed service/pass files, and selects only
   `PGSERVICE=n6_strategy_worker` as its database role; inherited environment,
   raw DSN, and password literals are forbidden. Launchd single-instance
   semantics and the dedicated PostgreSQL advisory lock must both pass; either
   guard missing or any overlap returns `REJECT`.
   `--max-runtime-seconds` is exactly 12: the evaluation alarm is exactly 11.5
   seconds and the reserved evidence-finalization grace is exactly 0.5 seconds;
   neither phase may borrow from or extend the twelve-second ceiling.
7. Primary activation permits one plist install and one bootstrap with no retry.
   The label and plist must both be absent in the frozen before-state. A single
   rollback may unload only this label and remove only the installed plist after
   readiness failure; strategy audit/projection/observation rows are not rolled
   back. An 081 schema rollback is rejected while any V2 selection, projection,
   observation, or change dependency exists.
8. Every scheduled tick requires a fresh gate over current trade date, Release,
   runner, plist, ACL, write allowlist, concurrency, and executor evidence. Drift
   fails closed and does not inherit stale activation evidence.

This policy never authorizes mutable checkout code, another LaunchAgent, schema
or migration changes, N1-N5 or outbox/inbox/checkpoint writes, account/cash/
position mutation, proposal/order/trade, real broker, voice/mobile/sim, virtual
executor, raw DSN/password injection, cross-user writes, or rollback DML. Reads
needed to derive the N6 display-only scope do not widen the four-table DML
allowlist. Web remains function-only, and the virtual executor receives no
observation table privilege or observation code-reference authority.

### 4.3A F464 Scheduled Evaluator Policy Supersession

The historical
`n6_strategy_center_display_only_scheduled_evaluator_v1` contract remains
unchanged evidence for its exact
`658ebb3995a7c539ac211258c378af6499635df4` Release and returns `REJECT` for
F464. It is not an activation policy for the integrated F464 Release. The only
scheduled-evaluator policy that may compile and pass Runtime Gate for F464 is
the following machine-readable policy. This governance session cannot use it.

<!-- policy:n6_strategy_center_display_only_scheduled_evaluator_f464_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_display_only_scheduled_evaluator_f464_v1",
  "supersedes_policy_id": "n6_strategy_center_display_only_scheduled_evaluator_v1",
  "supersession_scope": "f464_release_only",
  "legacy_policy_f464_decision": "REJECT",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "governance_session_execution_allowed": false,
  "layer_role": "N6_user",
  "required_next_gate": "N6_F464_20260727_NATURAL_INPUT_BOUNDED_CANARY",
  "required_post_canary_gate": "N6_F464_SCHEDULED_EVALUATOR_RUNTIME_ACTIVATION",
  "required_trade_date": "20260727",
  "required_trade_date_authority": "natural_n6_input_current_open_trade_date",
  "required_release": {
    "commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "tree": "c654cbc03c0341c9b3490a02a432b136984c43ce"
  },
  "superseded_release": {
    "commit": "658ebb3995a7c539ac211258c378af6499635df4",
    "tree": "016f154e6716ce0c4f2c7dcee74808e9f95c6dc9"
  },
  "required_release_git_blobs": {
    "scripts/run_n6_strategy_center_auto_once.py": "edd4cee4ae5003a77b4d9b4dc2548596f3e51eb6",
    "scripts/plan_n6_strategy_center_launchd.py": "f1a45c39b0f5a066028d558c37366e71fb2ca111",
    "src/ashare_v3/user/strategy_center_worker.py": "e356efcb3019d20e2c6d18b5cbec485d1d7fda38",
    "docs/N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723.json": "fe6bc0b75a5acf14b7c58143c98ed6d651fae802",
    "docs/N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2_SHADOW_CANONICAL.md": "a675197ed35deb8996404c145f353be8c4872d57",
    "config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json": "98cb884d9f8ef9a00c8244510d94508682e2b98e",
    "scripts/build_n6_strategy_center_temporal_confluence_v2_bundle.py": "6033e0cec2a680415a2a57a35aa936b441b6559d",
    "sql/081_n6_strategy_center_temporal_confluence_v2_catalog.sql": "982751c8db9a2e3e834ee3b5d36bf03f9f33cdc3",
    "sql/081_n6_strategy_center_temporal_confluence_v2_catalog_rollback.sql": "be793dd5ec7fc5b916c811ff1725359d1d89e78b",
    "sql/082_n6_strategy_center_v2_user_compensation.sql": "a2c3d9383b9774bc93d325070a50c59bd57de17f",
    "sql/082_n6_strategy_center_v2_user_compensation_rollback.sql": "71d72eb1e1d91b2232a26c3c32882104d3a14295",
    "sql/083_n6_strategy_center_v2_catalog_activation.sql": "cdd5bf3e5f3521862f00b874c7550084482c09fb",
    "sql/083_n6_strategy_center_v2_catalog_activation_rollback.sql": "aa2b0a533fd1a00d335fc6d5b51bd61f6b9e1c16"
  },
  "temporal_confluence_v2_lineage": {
    "candidate_path": "docs/N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723.json",
    "candidate_sha256": "94f5a6d88717688bfe079930edb956c20acd6c0c66aef870b332d5c2b221e489",
    "canonical_path": "docs/N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2_SHADOW_CANONICAL.md",
    "canonical_sha256": "17c655213243a820955fe154ac981f1d2b9f16e580bc93a1042d0d9e846986f9",
    "bundle_path": "config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_canonical_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
    "implementation_commit": "5c2c38d184385a317afe69b6397f7d98393ff24f",
    "implementation_tree": "0a02ac53513946ca530d3420b2bd06c60630388e",
    "policy_version": "n6_strategy_center_matcher_v2",
    "package_1": "v2",
    "package_2": "v2"
  },
  "required_runtime_file_sha256": {
    "scripts/run_n6_strategy_center_auto_once.py": "2d8bacb52bbb6e4c6011e69151b0ccd53c79708442d3a6b4d7944e91fb707c70",
    "scripts/plan_n6_strategy_center_launchd.py": "93ad94e36496619516f3a0afb3eecb834bdcecb91553d9731312555c53fdccab",
    "src/ashare_v3/user/strategy_center_worker.py": "02d4194eade8ff965a73fde56f2a60b36e1e6124f181d742f050028c8781d30a"
  },
  "required_migration_live_predicate": {
    "081": "PASS_COMMITTED",
    "082": "PASS_COMMITTED",
    "083": "PASS_COMMITTED",
    "active_catalog_version": "v2",
    "all_users_transaction": false
  },
  "required_live_web": {
    "release_commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "release_tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
    "plist_sha256": "7532979992d8e73a02a6bf81c0a43fa89e49843589d348792abfd62e3b0e64b8",
    "strategy_write": "0"
  },
  "required_evaluator_before_state": {
    "plist_present": true,
    "label_absent": true,
    "process_count": 0,
    "source_release_commit": "658ebb3995a7c539ac211258c378af6499635df4",
    "source_release_tree": "016f154e6716ce0c4f2c7dcee74808e9f95c6dc9",
    "source_plist_sha256": "60e9446a89b5f84ff5dee874eab6d05974c4e2dd6fb63a30c2d77074bb0c501a"
  },
  "required_evaluator_target": {
    "release_commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "release_tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
    "offline_activation_package_directory_name": "n6_f464_evaluator_activation_package_prepare_only",
    "offline_activation_package_directory_count": 1,
    "target_plist_sha256": "a0219e9585c8e67c905805c9d603d854aa2fb67e44857b240e4509cc7d4fe936",
    "offline_activation_manifest_sha256": "b80edef162d08b857c81677f20166987c7c03a32af6cabf0dd1632af04da2afa"
  },
  "required_activation_chain": {
    "event_count": 78,
    "file_sha256": "23ec1552b7cc21ed9970674d6f2ce7cc1ba83eeb27aa79ed9469bbd76ba40fc4",
    "tail_event_sha256": "5fc40a82e9045e0c3791389a88b1a8a1c09154f24e830347d0fc52b23ba6d925",
    "checkpoint_sha256": "caf33d4393e8df0987b0397d627397dc3c60cbe20469298e3f0c4b5d96f6cf00"
  },
  "required_virtual_executor": {
    "operation_count": 0,
    "configuration_untouched": true,
    "plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469"
  },
  "required_canary_scope": {
    "principal_id": 12,
    "principal_type": "human_user",
    "user_id": 11,
    "selection_revision_id": 22,
    "selection_revision_no": 1,
    "package_key": "package_1",
    "package_version": "v2"
  },
  "required_canary_result": {
    "scope_count": 1,
    "dry_run": "PASS",
    "primary": "PASS",
    "same_input_replay": "PASS",
    "projection": "PASS",
    "sse": "PASS",
    "all_cas_predicates_match": true,
    "fresh_business_increment_count": 0,
    "strategy_write": "0",
    "evaluator_absent": true,
    "virtual_executor_untouched": true
  },
  "scheduler_contract": {
    "launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
    "start_interval_seconds": 5,
    "run_at_load": false,
    "keep_alive": false,
    "max_runtime_seconds": 12,
    "max_scopes_per_tick": 1,
    "pending_precedes_active": true,
    "active_scope_cursor_mode": "persistent_round_robin",
    "transaction_scope": "single_principal_user_revision",
    "all_users_transaction": false,
    "display_only": true,
    "shadow_only": true
  },
  "activation_operation_counts": {
    "primary_atomic_plist_replace": 1,
    "primary_bootstrap": 1,
    "primary_bootout": 0,
    "primary_kickstart": 0,
    "primary_start": 0,
    "primary_retry": 0,
    "maximum_exact_source_restore": 1
  },
  "failure_compensation_contract": {
    "settled_absence_barrier_before_bootstrap": true,
    "restore_exact_source_plist": true,
    "restore_source_label_state": "absent",
    "restore_source_process_count": 0,
    "bootstrap_superseded_658_source": false,
    "restore_empty_state_allowed": false,
    "applies_to_install_failure": true,
    "applies_to_post_activation_natural_acceptance_failure": true
  },
  "required_transition_order": [
    "frozen_source",
    "validated_f464_target",
    "frozen_source_on_failure_only"
  ],
  "required_zero_side_effect_counts": {
    "n1_n5": 0,
    "outbox_inbox_checkpoint": 0,
    "proposal": 0,
    "order": 0,
    "trade": 0,
    "position": 0,
    "lot": 0,
    "cash": 0,
    "real_broker": 0,
    "voice": 0,
    "mobile": 0,
    "sim": 0,
    "deepseek": 0,
    "autonomous_execution": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "natural_n6_input_verified",
    "current_open_trade_date_verified",
    "exact_single_scope_canary_passed",
    "all_cas_predicates_match_verified",
    "fresh_business_zero_increment_verified",
    "strategy_write_zero_verified",
    "evaluator_absent_verified",
    "virtual_executor_untouched_verified",
    "release_commit_tree_verified",
    "release_git_blobs_verified",
    "temporal_confluence_v2_lineage_verified",
    "migration_081_082_083_live_predicate_verified",
    "web_target_plist_verified",
    "evaluator_source_target_plists_verified",
    "offline_activation_manifest_verified",
    "activation_chain_verified",
    "source_target_source_transition_verified",
    "settled_absence_barrier_verified"
  ],
  "required_false_fields": [
    "wrong_order_requested",
    "cas_drift_detected",
    "hash_drift_detected",
    "all_users_transaction_requested",
    "side_effect_requested",
    "deepseek_requested",
    "autonomous_execution_requested",
    "trading_side_effect_requested",
    "other_launch_agent_touched",
    "n1_n5_touched",
    "database_or_release_mutation_requested_by_governance_session",
    "empty_state_restore_requested",
    "superseded_658_bootstrap_requested"
  ]
}
```
<!-- policy:n6_strategy_center_display_only_scheduled_evaluator_f464_v1:end -->

Evaluation is fail-closed. The exact F464 Release, all frozen Git blobs and
candidate/canonical/bundle hashes, committed 081/082/083 V2 predicate, Web and
Evaluator plist hashes, offline manifest, and 78-event activation-chain tail
must match. Activation requires the 20260727 natural-input canary for exactly
principal 12/principal-type human_user/user 11/revision 22/revision-no
1/package_1 v2 with every CAS predicate matched, zero fresh business increment,
strategy-write `0`, Evaluator absent, and Virtual Executor untouched. The
principal type `user`, `admin`, or any unknown value cannot substitute for this
revision 22 `human_user` scope. Wrong order, CAS/hash drift, all-users, DeepSeek,
autonomous execution, N1-N5, or any trading/business side effect returns
`REJECT`.

The primary absent-label path permits exactly one atomic plist replacement and
one bootstrap, with zero bootout, kickstart, start, or retry. Bootstrap requires
a settled-absence barrier. A failure may restore the exact frozen source plist
at most once and must finish with plist present, label absent, process count
zero. It must not bootstrap the superseded 658 evaluator or restore an empty
state. The same source-state compensation applies to a post-activation natural
acceptance failure.

### 4.4 N6 Strategy Center 081 Schema-Migration Maintenance Window Exception

This `runtime_control` policy prepares one fail-closed maintenance window for
the exact 081 schema/catalog migration. It does not execute 081 and cannot be
combined with the later `N6_user` migration gate. The governance task that
creates or changes this policy cannot use it in the same session.

The following JSON block is the machine-readable authority for static policy tests:

<!-- policy:n6_strategy_center_schema_migration_maintenance_window_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_schema_migration_maintenance_window_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "scope_mode": "single_081_quiesce_window",
  "phase_mode": "prepare_081_window_only",
  "migration_id": "081",
  "migration_forward_basename": "081_n6_strategy_center_temporal_confluence_v2_catalog.sql",
  "migration_rollback_basename": "081_n6_strategy_center_temporal_confluence_v2_catalog_rollback.sql",
  "forbidden_migration_ids": [
    "082",
    "083"
  ],
  "web_launch_agent_label": "com.ashare-v3.n6.user-web",
  "web_launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
  "evaluator_launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "evaluator_launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "maintenance_token_root": "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/maintenance",
  "maintenance_token_name_pattern": "^081-maintenance-[0-9]{8}T[0-9]{6}[+-][0-9]{4}__[0-9a-f]{64}\\.json$",
  "web_strategy_write_flag": "ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED",
  "web_strategy_write_flag_before": "1",
  "web_strategy_write_flag_during": "0",
  "web_teardown_timeout_seconds": 30,
  "web_readiness_timeout_seconds": 60,
  "web_stability_window_seconds": 30,
  "evaluator_teardown_timeout_seconds": 30,
  "maintenance_token_max_age_seconds": 900,
  "required_route_expectations": {
    "/n6/app/strategy-center": 302,
    "/api/n6/app/v3/strategy-center": 401,
    "/n6/app/signals": 302
  },
  "allowed_readonly_watermark_tables": [
    "n6_user_strategy_selection_revision",
    "n6_strategy_match_projection",
    "n6_strategy_match_change",
    "n6_strategy_observation_projection"
  ],
  "allowed_mutation_resources": [
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
    "gui/current-user/com.ashare-v3.n6.user-web",
    "gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1",
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center/maintenance/<single-immutable-token>"
  ],
  "allowed_runtime_operations": [
    "freeze_exact_web_evaluator_and_virtual_executor_configuration",
    "install_web_plist_with_only_strategy_write_flag_zero",
    "launchctl_bootout_exact_web_label_once",
    "state_driven_wait_for_web_pid_and_job_absence",
    "launchctl_bootstrap_exact_web_plist_once",
    "verify_web_readiness_routes_and_stability",
    "launchctl_bootout_exact_evaluator_label_once",
    "state_driven_wait_for_evaluator_pid_and_job_absence",
    "read_strategy_watermarks_once_without_lock_or_write",
    "write_single_immutable_maintenance_token",
    "restore_frozen_web_plist_once_before_migration_only"
  ],
  "required_singleton_counts": {
    "maintenance_window_count": 1,
    "migration_count": 1,
    "web_launch_agent_count": 1,
    "evaluator_launch_agent_count": 1,
    "maintenance_token_count": 1,
    "source_release_count": 1
  },
  "required_operation_counts": {
    "web_primary_bootout_attempts": 1,
    "web_primary_bootstrap_attempts": 1,
    "evaluator_bootout_attempts": 1,
    "evaluator_bootstrap_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "primary_retries": 0,
    "migration_execution_attempts": 0,
    "database_write_attempts": 0
  },
  "maximum_pre_migration_web_restore_attempts": 1,
  "required_hash_fields": {
    "migration_forward_sha256": "^[0-9a-f]{64}$",
    "migration_rollback_sha256": "^[0-9a-f]{64}$",
    "release_commit_sha": "^[0-9a-f]{40}$",
    "release_tree_sha": "^[0-9a-f]{40}$",
    "release_archive_sha256": "^[0-9a-f]{64}$",
    "release_manifest_sha256": "^[0-9a-f]{64}$",
    "release_filesystem_sha256": "^[0-9a-f]{64}$",
    "web_plist_before_sha256": "^[0-9a-f]{64}$",
    "web_plist_quiesced_sha256": "^[0-9a-f]{64}$",
    "evaluator_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_runner_sha256": "^[0-9a-f]{64}$",
    "web_before_state_sha256": "^[0-9a-f]{64}$",
    "evaluator_before_state_sha256": "^[0-9a-f]{64}$",
    "selection_projection_change_watermark_sha256": "^[0-9a-f]{64}$",
    "maintenance_token_payload_sha256": "^[0-9a-f]{64}$",
    "maintenance_token_file_sha256": "^[0-9a-f]{64}$"
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "exact_081_maintenance_window_authorized",
    "governance_policy_integrated_verified",
    "web_launchd_ownership_verified",
    "evaluator_launchd_ownership_verified",
    "web_plist_release_runner_permissions_frozen",
    "evaluator_plist_release_runner_permissions_frozen",
    "virtual_executor_configuration_frozen",
    "virtual_executor_object_disjoint_verified",
    "release_immutable_verified",
    "release_commit_tree_archive_manifest_filesystem_verified",
    "migration_forward_hash_verified",
    "migration_rollback_hash_verified",
    "web_only_strategy_write_flag_changed",
    "web_other_environment_byte_equivalent",
    "web_owner_group_mode_acl_xattr_preserved",
    "web_old_pid_absent_before_bootstrap",
    "web_job_absent_before_bootstrap",
    "web_readiness_routes_passed",
    "web_stability_window_passed",
    "evaluator_pid_absent",
    "evaluator_job_absent",
    "selection_writes_quiesced",
    "strategy_watermarks_frozen",
    "maintenance_token_fields_complete",
    "maintenance_token_hash_verified",
    "maintenance_token_mode_0444_verified",
    "before_after_trace_defined",
    "pre_migration_failure_restore_contract_frozen",
    "post_commit_fail_closed_contract_frozen",
    "v2_web_then_bounded_canary_then_v2_evaluator_order_frozen"
  ],
  "required_false_fields": [
    "migration_execution_requested",
    "migration_082_requested",
    "migration_083_requested",
    "database_write_requested",
    "database_lock_requested",
    "evaluator_bootstrap_requested",
    "old_v1_evaluator_restore_after_081_requested",
    "virtual_executor_operation_requested",
    "other_launch_agent_touched",
    "multiple_services_requested",
    "fixed_sleep_substituted_for_state_wait",
    "kill_or_kickstart_requested",
    "primary_retry_requested",
    "release_drift_detected",
    "migration_hash_drift_detected",
    "plist_or_runner_drift_detected",
    "acl_or_role_drift_detected",
    "ownership_ambiguous",
    "maintenance_token_missing_expired_or_drifted",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "n1_n5_write_requested",
    "outbox_inbox_checkpoint_mutation_requested",
    "long_term_worker_install_requested",
    "concurrent_runtime_change"
  ],
  "normal_periodic_pid_runs_change_is_configuration_drift": false,
  "migration_transaction_authorized": false,
  "post_081_keep_web_strategy_writes_disabled": true,
  "post_081_keep_old_evaluator_quiesced": true
}
```
<!-- policy:n6_strategy_center_schema_migration_maintenance_window_v1:end -->

Evaluation is fail-closed and ordered:

1. The current request must explicitly authorize one exact 081 maintenance
   window, declare `layer_role=runtime_control`, and select this policy. A policy
   governance request cannot open the window in the same session.
2. The only Web change is
   `ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED=1→0`; every other plist byte-level
   semantic, environment variable, Release path, owner/group, mode, ACL, and
   xattr must remain frozen. The Web receives one state-driven bootout/bootstrap
   pair and must pass the declared routes and stability window.
3. After Web selection writes are closed, the exact Strategy Center evaluator
   receives one bootout and zero bootstrap attempts. The maintenance token
   cannot be written until its PID is absent and `launchctl print` proves its job
   absent.
4. The virtual executor is configuration-frozen and object-disjoint from 081.
   Its ordinary five-second PID/runs changes are not configuration drift and do
   not block this policy. Any request to stop, start, modify, or otherwise
   operate it returns `REJECT`.
5. One read-only, non-locking watermark snapshot may cover only the four named
   N6 Strategy Center tables. It grants no database write, DDL, migration, or
   transaction authority.
6. The one maintenance token must bind policy, exact 081 forward/rollback
   hashes, immutable Release commit/tree/archive/manifest/filesystem hashes,
   Web/evaluator plist and runner hashes, quiesce time, the frozen strategy
   watermarks, expiry, and its canonical payload/file hashes. Missing, expired,
   writable, or drifted evidence returns `REJECT`.
7. This policy ends after a valid token is created. A separate `N6_user` request
   must verify that token before attempting 081 once. It may not include 082,
   083, evaluator execution, or any business/transaction path.
8. Before 081 starts, a failed quiesce may restore the frozen Web plist once; it
   does not automatically restore the evaluator. After 081 commits, selection
   writes and the old evaluator remain quiesced. The required sequence is
   V2-compatible Web, bounded single-scope canary, then V2 evaluator. SQL
   rollback requires a separate `N6_user` authorization and proof that no V2
   revision or projection depends on 081.

True configuration drift is limited to label, plist, Release, runner, role/ACL,
ownership, migration/manifest/token hashes, or target-object changes. Normal
`StartInterval` PID/runs cycling alone is not `concurrent_runtime_change`.

This policy never authorizes 081/082/083 execution, database writes or locks,
old-evaluator restoration after 081, virtual-executor operation, another
LaunchAgent, N1-N5 writes, queues, proposal/order/trade/position/cash, real
broker, or mutable Release content.

<!-- policy:n6_strategy_center_post_081_v2_web_bounded_rebind_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_081_v2_web_bounded_rebind_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "scope_mode": "post_081_single_web_single_source_target_release",
  "phase_mode": "post_081_v2_web_rebind_only",
  "launch_agent_label": "com.ashare-v3.n6.user-web",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
  "evaluator_launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "service_port": 8786,
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_name_pattern": "^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$",
  "required_resource_fields": [
    "source_release_path",
    "target_release_path"
  ],
  "required_singleton_counts": {
    "service_count": 1,
    "launch_agent_count": 1,
    "source_release_count": 1,
    "target_release_count": 1
  },
  "required_hash_fields": {
    "source_release_commit_sha": "^[0-9a-f]{40}$",
    "source_release_tree_sha": "^[0-9a-f]{40}$",
    "source_release_archive_sha256": "^[0-9a-f]{64}$",
    "source_release_manifest_sha256": "^[0-9a-f]{64}$",
    "source_release_filesystem_sha256": "^[0-9a-f]{64}$",
    "target_release_commit_sha": "^[0-9a-f]{40}$",
    "target_release_tree_sha": "^[0-9a-f]{40}$",
    "target_release_archive_sha256": "^[0-9a-f]{64}$",
    "target_release_manifest_sha256": "^[0-9a-f]{64}$",
    "target_release_filesystem_sha256": "^[0-9a-f]{64}$",
    "post_081_schema_evidence_sha256": "^[0-9a-f]{64}$",
    "web_before_plist_sha256": "^[0-9a-f]{64}$",
    "web_target_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_runner_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_plist_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_release_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_runner_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_role_acl_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_object_boundary_sha256": "^[0-9a-f]{64}$"
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "migration_081_committed_verified",
    "migration_082_not_executed_verified",
    "migration_083_not_executed_verified",
    "post_081_schema_evidence_verified",
    "source_release_immutable_verified",
    "target_release_immutable_verified",
    "target_no_lineage_regression_verified",
    "target_v2_web_api_ui_sse_verified",
    "target_observation_surface_verified",
    "target_direction_and_trading_minute_freshness_verified",
    "target_081_schema_compatible_verified",
    "current_pid_frozen",
    "current_ppid_frozen",
    "current_argv_frozen",
    "current_cwd_frozen",
    "current_plist_sha_frozen",
    "current_plist_owner_group_mode_frozen",
    "current_plist_acl_xattr_frozen",
    "current_environment_frozen",
    "launchd_ownership_verified",
    "target_plist_lint_passed",
    "target_plist_hash_verified",
    "target_plist_only_release_paths_changed",
    "owner_group_mode_acl_xattr_preservation_defined",
    "web_strategy_write_before_zero_verified",
    "web_strategy_write_target_zero_verified",
    "web_strategy_write_after_zero_required",
    "evaluator_plist_runner_frozen",
    "evaluator_job_absent_verified",
    "evaluator_pid_absent_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_role_acl_frozen",
    "virtual_executor_object_boundary_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "state_driven_teardown_defined",
    "old_pid_exit_required_before_bootstrap",
    "job_absence_required_before_bootstrap",
    "readiness_contract_frozen",
    "route_contract_frozen",
    "stability_window_frozen",
    "automatic_rollback_contract_frozen",
    "rollback_restores_frozen_source_only",
    "rollback_preserves_strategy_write_zero",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "runtime_ownership_ambiguous",
    "multiple_services_requested",
    "release_drift_detected",
    "plist_drift_detected",
    "environment_drift_detected",
    "lineage_regression_detected",
    "post_081_schema_drift_detected",
    "immutable_release_content_modification_requested",
    "extra_environment_change_requested",
    "other_launch_agent_touched",
    "fixed_sleep_bootstrap_requested",
    "primary_retry_requested",
    "signal_or_kill_requested",
    "strategy_write_enable_requested",
    "strategy_evaluator_execute_requested",
    "strategy_evaluator_start_requested",
    "strategy_evaluator_restore_requested",
    "virtual_executor_operation_requested",
    "virtual_executor_stop_requested",
    "virtual_executor_start_requested",
    "virtual_executor_configuration_drift_detected",
    "virtual_executor_acl_or_object_boundary_drift_detected",
    "normal_virtual_executor_pid_runs_change_is_configuration_drift",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "migration_082_requested",
    "migration_083_requested",
    "selection_projection_change_touched",
    "outbox_inbox_checkpoint_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "n1_n5_write_requested",
    "long_running_worker_requested",
    "concurrent_runtime_change"
  ],
  "allowed_mutation_resources": [
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
    "gui/current-user/com.ashare-v3.n6.user-web"
  ],
  "allowed_runtime_operations": [
    "install_validated_target_plist",
    "launchctl_bootout_exact_web_label",
    "state_driven_wait_for_web_pid_and_job_absence",
    "launchctl_bootstrap_exact_web_plist",
    "readiness_and_stability_probe",
    "rollback_restore_frozen_source_plist",
    "rollback_bootout_exact_web_label",
    "rollback_bootstrap_exact_web_plist"
  ],
  "primary_bootout_attempts": 1,
  "primary_bootstrap_attempts": 1,
  "maximum_primary_retries": 0,
  "maximum_rollback_attempts": 1,
  "rollback_requires_primary_failure": true,
  "rollback_requires_frozen_source": true,
  "teardown_timeout_seconds": 30,
  "readiness_timeout_seconds": 60,
  "stability_window_seconds": 30,
  "required_strategy_write_flag_value": "0",
  "required_login_redirect_path": "/n6/login",
  "required_route_expectations": {
    "/n6/app/strategy-center": 302,
    "/api/n6/app/v3/strategy-center": 401,
    "/n6/app/signals": 302
  },
  "normal_virtual_executor_pid_runs_change_is_configuration_drift": false
}
```
<!-- policy:n6_strategy_center_post_081_v2_web_bounded_rebind_v1:end -->

Evaluation is fail-closed and ordered:

1. The current independent `runtime_control` request must explicitly authorize
   one post-081 V2 Web rebind and select this policy. The policy-governance
   session cannot use the new exception.
2. Fresh evidence must prove 081 committed, 082/083 did not execute, and the
   post-081 schema matches the immutable evidence bound to the target Release.
   This policy grants no database connection or migration authority.
3. The exact Web is the only mutable service. Its strategy-write flag must be
   `0` before the rebind, in the target plist, after readiness, and after any
   rollback. Only WorkingDirectory and PYTHONPATH may select the target Release.
4. The exact Strategy Center evaluator must already have no job and no runner
   process. This policy cannot execute, start, restore, bootstrap, kickstart, or
   otherwise operate it.
5. The virtual executor remains loaded or scheduled exactly as found. Its
   plist, Release, runner, role/ACL, and object-boundary hashes must remain
   frozen and its writes must be disjoint from Strategy Center. The policy
   cannot stop, start, restart, or modify it. Normal StartInterval PID/runs
   cycling alone is not configuration drift.
6. Source and target are one distinct immutable Release each. Commit, tree,
   archive, manifest, filesystem, V2 Web/API/UI/SSE, observation, direction,
   trading-minute freshness, 081 compatibility, and non-regression evidence
   must all pass before the target plist is installed.
7. The Web receives at most one state-driven primary bootout/bootstrap pair,
   zero primary retries, a 60-second readiness window, and a 30-second stability
   window. Fixed sleeps, signals, kill, kickstart, or a second primary attempt
   return `REJECT`.
8. A proven primary health failure may use one rollback bootout/bootstrap pair
   to restore only the frozen source plist/Release with strategy writes still
   `0`. Rollback is never a second target attempt.
9. Any database/migration/evaluator/virtual-executor operation, N1-N5 write,
   queue mutation, proposal/order/trade/position/cash path, broker connection,
   extra LaunchAgent, mutable Release change, or missing/drifted evidence
   returns `REJECT`.

This policy is separate from and does not relax
`n6_user_web_immutable_release_bounded_rebind_v1`, whose normal non-maintenance
contract still requires strategy write `1` and its existing executor guard.

### 4.6 Strategy Center Post-081 V2 Catalog Migration Window Exception

This fail-closed policy authorizes one exact migration phase in an independent
`N6_user` request after the 081 maintenance window and V2 Web deployment. It
requires two separate gates and transactions: 082 first, then 083. The
`runtime_control` governance request that creates or changes this policy cannot
use it in the same session.

<!-- policy:n6_strategy_center_post_081_v2_catalog_migration_window_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_081_v2_catalog_migration_window_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "scope_mode": "single_post_081_v2_catalog_migration",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "web_launch_agent_label": "com.ashare-v3.n6.user-web",
  "evaluator_launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "required_strategy_write_flag_value": "0",
  "required_database_authority_mode": "owner_only",
  "allowed_phase_modes": {
    "execute_082_tooling_once": {
      "migration_id": "082",
      "forward_basename": "082_n6_strategy_center_v2_user_compensation.sql",
      "rollback_basename": "082_n6_strategy_center_v2_user_compensation_rollback.sql",
      "allowed_schema_objects": [
        "n6_user_strategy_selection_revision_selection_status_check",
        "n6_user_strategy_selection_revision_check",
        "n6_user_strategy_selection_revision_previous_revision_id_key",
        "idx_082_n6_strategy_selection_live_previous_revision",
        "n6_strategy_center_compensate_revision_v1",
        "n6_strategy_center_abandon_pending_v2"
      ],
      "allowed_data_mutations": [],
      "required_true_fields": [
        "migration_081_committed_verified",
        "migration_082_not_executed_verified",
        "migration_083_not_executed_verified",
        "pending_revision_count_zero_verified",
        "migration_082_dependency_preflight_passed",
        "migration_082_postflight_and_acl_contract_frozen",
        "compensation_functions_install_only_verified",
        "selection_revision_rows_unchanged_required",
        "catalog_rows_unchanged_required",
        "projection_change_rows_unchanged_required"
      ],
      "required_false_fields": [
        "migration_082_compensation_function_call_requested",
        "selection_revision_write_requested",
        "catalog_write_requested",
        "projection_change_write_requested"
      ]
    },
    "execute_083_catalog_activation_once": {
      "migration_id": "083",
      "forward_basename": "083_n6_strategy_center_v2_catalog_activation.sql",
      "rollback_basename": "083_n6_strategy_center_v2_catalog_activation_rollback.sql",
      "allowed_schema_objects": [],
      "allowed_data_mutations": [
        "n6_strategy_package_catalog.package_1_v1_active_to_grandfathered",
        "n6_strategy_package_catalog.package_2_v1_active_to_grandfathered",
        "n6_strategy_package_catalog.package_1_v2_selectable_to_active_default",
        "n6_strategy_package_catalog.package_2_v2_selectable_to_active"
      ],
      "required_true_fields": [
        "migration_081_committed_verified",
        "migration_082_committed_verified",
        "migration_083_not_executed_verified",
        "migration_082_postflight_and_acl_passed",
        "current_open_trade_date_verified",
        "pending_revision_count_zero_verified",
        "unique_active_v1_per_active_principal_verified",
        "v2_selection_item_count_zero_verified",
        "catalog_transition_exact_verified",
        "selection_revision_rows_unchanged_required"
      ],
      "required_false_fields": [
        "selection_revision_write_requested",
        "selection_item_write_requested",
        "projection_change_write_requested",
        "schema_object_write_requested"
      ]
    }
  },
  "required_singleton_counts": {
    "migration_phase_count": 1,
    "migration_count": 1,
    "database_transaction_count": 1,
    "release_count": 1,
    "web_launch_agent_count": 1,
    "evaluator_launch_agent_count": 1
  },
  "required_operation_counts": {
    "forward_attempts": 1,
    "primary_retries": 0,
    "rollback_attempts": 0,
    "evaluator_execution_attempts": 0,
    "evaluator_bootstrap_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "web_rebind_attempts": 0
  },
  "required_hash_fields": {
    "release_commit_sha": "^[0-9a-f]{40}$",
    "release_tree_sha": "^[0-9a-f]{40}$",
    "release_archive_sha256": "^[0-9a-f]{64}$",
    "release_manifest_sha256": "^[0-9a-f]{64}$",
    "release_filesystem_sha256": "^[0-9a-f]{64}$",
    "migration_forward_sha256": "^[0-9a-f]{64}$",
    "migration_rollback_sha256": "^[0-9a-f]{64}$",
    "maintenance_evidence_sha256": "^[0-9a-f]{64}$",
    "web_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_runner_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_plist_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_release_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_runner_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_role_acl_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_object_boundary_sha256": "^[0-9a-f]{64}$",
    "before_state_sha256": "^[0-9a-f]{64}$",
    "after_state_sha256": "^[0-9a-f]{64}$"
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "exact_single_migration_phase_authorized",
    "governance_policy_integrated_verified",
    "release_immutable_verified",
    "release_hashes_verified",
    "migration_hashes_verified",
    "maintenance_evidence_verified",
    "strategy_write_zero_verified",
    "evaluator_job_absent_verified",
    "evaluator_pid_absent_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_role_acl_frozen",
    "virtual_executor_object_boundary_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "database_owner_authority_verified",
    "on_error_stop_enabled",
    "explicit_begin_commit_defined",
    "advisory_transaction_lock_defined",
    "before_after_watermarks_frozen",
    "postflight_defined",
    "zero_retry_contract_frozen",
    "rollback_requires_separate_authorization"
  ],
  "required_false_fields": [
    "combined_082_083_requested",
    "migration_order_bypass_requested",
    "strategy_write_enable_requested",
    "strategy_evaluator_execute_requested",
    "strategy_evaluator_start_requested",
    "strategy_evaluator_restore_requested",
    "virtual_executor_operation_requested",
    "virtual_executor_configuration_drift_detected",
    "virtual_executor_acl_or_object_boundary_drift_detected",
    "web_rebind_requested",
    "other_migration_requested",
    "other_launch_agent_touched",
    "business_dml_requested",
    "outbox_inbox_checkpoint_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "n1_n5_write_requested",
    "long_term_worker_install_requested",
    "release_drift_detected",
    "migration_hash_drift_detected",
    "plist_runner_acl_or_ownership_drift_detected",
    "maintenance_evidence_drift_detected",
    "concurrent_runtime_change"
  ],
  "normal_virtual_executor_pid_runs_change_is_configuration_drift": false,
  "transaction_not_committed_skips_sql_rollback": true,
  "post_082_keep_maintenance_window_open": true,
  "post_083_failure_keeps_strategy_write_zero_and_evaluator_quiesced": true
}
```
<!-- policy:n6_strategy_center_post_081_v2_catalog_migration_window_v1:end -->

Evaluation is fail-closed and phase-specific:

1. The request must select exactly one phase and migration. 082 and 083 cannot
   be combined, retried, reordered, or executed in the governance session.
2. Both phases require immutable Release and SQL hashes, fresh maintenance
   evidence, strategy write `0`, exact evaluator job/PID absence, and frozen,
   write-disjoint virtual-executor configuration. Periodic executor PID/runs
   changes alone are not configuration drift.
3. The 082 phase only installs its declared constraint, unique index,
   compensation functions, and ACL. It cannot invoke either function or mutate
   revision, catalog, projection, observation, or change rows.
4. The 083 phase requires committed 082 plus its postflight/ACL proof, an open
   trade date, zero pending revisions, zero V2 selection items, and one active
   V1 revision per active principal. It may only perform the four declared
   catalog transitions and cannot modify existing selections or schema.
5. Each phase uses one `ON_ERROR_STOP` transaction with explicit
   `BEGIN/COMMIT`, one advisory transaction lock, one forward attempt, and zero
   retries. If it does not commit, SQL rollback is not run. Rollback after a
   commit always requires a separate authorization and dependency proof.
6. Database business DML, evaluator or Web operation, virtual-executor
   operation, another migration/service, N1-N5, queues, broker, or any trading
   path returns `REJECT`.

### 4.7 Strategy Center Post-083 Single-User Pending V2 Revision Exception

This fail-closed policy authorizes one later, independently approved
`N6_user` request to recover from exactly two already-observed pre-DML harness
failures and create the first pending V2 selection revision after 083. The
first failure is SQLSTATE `42704` from treating `PUBLIC` as a role name. The
second is SQLSTATE `42601` because a psql variable inside a dollar-quoted `DO`
body was not expanded. Neither harness transaction is a mutation attempt only
when immutable evidence proves automatic abort, zero official selection-
function calls, zero target-table DML, zero commits, no persisted request id,
zero mutation attempts, and identical before/after hashes for both failures.
Recovery v2 requires a separate `READ ONLY` preflight for every complex check.
The later mutation transaction forbids `DO`, psql interpolation, and dynamic
SQL and is limited to transaction control, `SET`, one advisory-lock `SELECT`,
one official selection-function `SELECT`, read-only postflight `SELECT`
statements, and `COMMIT`. The new request id must enter through shell/driver
parameter binding; only its non-secret audit hash may be recorded. It does not
open the Web write path, activate the revision, or run any evaluator. The
`runtime_control` governance request that creates or changes this policy cannot
use it in the same session.

<!-- policy:n6_strategy_center_post_083_single_user_pending_v2_revision_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_083_single_user_pending_v2_revision_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": [
    "ACCEPT",
    "REJECT",
    "BLOCK",
    "ESCALATE"
  ],
  "layer_role": "N6_user",
  "scope_mode": "single_principal_user_pending_v2_revision",
  "phase_mode": "recover_two_verified_pre_dml_harness_failures_then_create_first_post_083_pending_v2_revision_once",
  "recovery_contract_version": "pre_dml_guard_harness_recovery_v2",
  "required_strategy_write_flag_value": "0",
  "required_database_authority_mode": "owner_only",
  "required_request_id_pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
  "required_historical_pre_dml_harness_failures": [
    {
      "transaction_ordinal": 1,
      "guard_id": "public_execute_acl_audit_guard",
      "failure_class": "pre_dml_audit_guard_public_pseudo_role_lookup",
      "sqlstate": "42704",
      "error_message": "role \"PUBLIC\" does not exist",
      "root_cause": "has_function_privilege_public_role_name"
    },
    {
      "transaction_ordinal": 2,
      "guard_id": "request_id_pre_dml_harness_guard",
      "failure_class": "pre_dml_harness_psql_variable_not_expanded_in_dollar_quoted_do",
      "sqlstate": "42601",
      "error_token": ":'request_id'",
      "root_cause": "psql_request_id_variable_inside_dollar_quoted_do_not_expanded"
    }
  ],
  "required_guard_repair_mode": "pg_catalog_aclexplode_coalesced_function_acl_public_grantee_zero",
  "required_preflight_mode": "independent_read_only_transaction_all_complex_validation",
  "required_request_id_binding_mode": "shell_or_driver_parameter_binding",
  "required_mutation_statement_classes": [
    "BEGIN",
    "SET",
    "SELECT_ADVISORY_XACT_LOCK",
    "SELECT_OFFICIAL_SELECTION_FUNCTION",
    "SELECT_READ_ONLY_POSTFLIGHT",
    "COMMIT"
  ],
  "allowed_selection_creation_authority_modes": [
    "official_owner_user_isolated_selection_function"
  ],
  "exact_canary_scope": {
    "principal_id": 1,
    "user_id": 1,
    "for_trade_date": "20260723",
    "expected_active_revision_id": 15,
    "expected_active_revision_no": 5,
    "expected_active_selection_status": "active",
    "expected_active_package_items": [
      {
        "package_key": "package_1",
        "package_version": "v1"
      }
    ],
    "target_revision_no": 6,
    "target_previous_revision_id": 15,
    "target_selection_status": "pending",
    "target_replay_status": "pending",
    "target_package_items": [
      {
        "package_key": "package_1",
        "package_version": "v2"
      }
    ]
  },
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_user_strategy_selection_item"
  ],
  "allowed_mutations": [
    "insert_one_pending_selection_revision",
    "insert_one_package_1_v2_selection_item"
  ],
  "required_singleton_counts": {
    "scope_count": 1,
    "principal_count": 1,
    "user_count": 1,
    "predecessor_revision_count": 1,
    "target_revision_count": 1,
    "target_item_count": 1,
    "historical_pre_dml_harness_transaction_count": 2,
    "historical_pre_dml_harness_failure_count": 2,
    "new_mutation_transaction_count": 1,
    "new_request_id_count": 1
  },
  "required_operation_counts": {
    "historical_pre_dml_harness_attempts": 2,
    "prior_official_selection_function_calls": 0,
    "prior_selection_revision_dml_count": 0,
    "prior_selection_item_dml_count": 0,
    "prior_commit_count": 0,
    "prior_explicit_rollback_count": 0,
    "prior_mutation_attempts": 0,
    "mutation_do_block_count": 0,
    "mutation_psql_variable_interpolation_count": 0,
    "mutation_dynamic_sql_count": 0,
    "mutation_complex_validation_query_count": 0,
    "mutation_advisory_lock_select_count": 1,
    "mutation_official_selection_function_select_count": 1,
    "new_mutation_attempts": 1,
    "new_mutation_retries": 0,
    "activation_attempts": 0,
    "web_put_attempts": 0,
    "evaluator_execution_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "compensation_function_call_attempts": 0
  },
  "required_hash_fields": {
    "migration_081_postflight_sha256": "^[0-9a-f]{64}$",
    "migration_082_postflight_sha256": "^[0-9a-f]{64}$",
    "migration_083_postflight_sha256": "^[0-9a-f]{64}$",
    "v2_catalog_state_sha256": "^[0-9a-f]{64}$",
    "selection_creation_authority_sha256": "^[0-9a-f]{64}$",
    "selection_creation_contract_sha256": "^[0-9a-f]{64}$",
    "new_request_id_sha256": "^[0-9a-f]{64}$",
    "historical_harness_42704_evidence_sha256": "^[0-9a-f]{64}$",
    "historical_harness_42601_evidence_sha256": "^[0-9a-f]{64}$",
    "historical_harness_sequence_sha256": "^[0-9a-f]{64}$",
    "before_scope_sha256": "^[0-9a-f]{64}$",
    "after_scope_sha256": "^[0-9a-f]{64}$",
    "other_users_before_after_sha256": "^[0-9a-f]{64}$",
    "projection_change_before_after_sha256": "^[0-9a-f]{64}$",
    "non_trading_side_effect_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_frozen_state_sha256": "^[0-9a-f]{64}$",
    "prior_selection_revision_before_sha256": "^[0-9a-f]{64}$",
    "prior_selection_revision_after_sha256": "^[0-9a-f]{64}$",
    "prior_selection_item_before_sha256": "^[0-9a-f]{64}$",
    "prior_selection_item_after_sha256": "^[0-9a-f]{64}$",
    "prior_match_projection_before_sha256": "^[0-9a-f]{64}$",
    "prior_match_projection_after_sha256": "^[0-9a-f]{64}$",
    "prior_match_change_before_sha256": "^[0-9a-f]{64}$",
    "prior_match_change_after_sha256": "^[0-9a-f]{64}$",
    "prior_observation_projection_before_sha256": "^[0-9a-f]{64}$",
    "prior_observation_projection_after_sha256": "^[0-9a-f]{64}$",
    "prior_catalog_state_before_sha256": "^[0-9a-f]{64}$",
    "prior_catalog_state_after_sha256": "^[0-9a-f]{64}$",
    "prior_selection_function_before_sha256": "^[0-9a-f]{64}$",
    "prior_selection_function_after_sha256": "^[0-9a-f]{64}$"
  },
  "required_equal_hash_pairs": [
    [
      "prior_selection_revision_before_sha256",
      "prior_selection_revision_after_sha256"
    ],
    [
      "prior_selection_item_before_sha256",
      "prior_selection_item_after_sha256"
    ],
    [
      "prior_match_projection_before_sha256",
      "prior_match_projection_after_sha256"
    ],
    [
      "prior_match_change_before_sha256",
      "prior_match_change_after_sha256"
    ],
    [
      "prior_observation_projection_before_sha256",
      "prior_observation_projection_after_sha256"
    ],
    [
      "prior_catalog_state_before_sha256",
      "prior_catalog_state_after_sha256"
    ],
    [
      "prior_selection_function_before_sha256",
      "prior_selection_function_after_sha256"
    ]
  ],
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "exact_single_scope_authorized",
    "governance_policy_integrated_verified",
    "current_trade_date_matches_for_trade_date",
    "current_trade_date_open_verified",
    "migration_081_committed_and_postflight_verified",
    "migration_082_committed_and_postflight_verified",
    "migration_083_committed_and_postflight_verified",
    "v2_catalog_active_verified",
    "v1_catalog_grandfathered_verified",
    "strategy_write_zero_verified",
    "evaluator_job_absent_verified",
    "evaluator_pid_absent_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_strategy_center_object_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "target_scope_pending_count_zero_verified",
    "target_scope_v2_item_count_zero_verified",
    "target_scope_unique_active_v1_verified",
    "active_predecessor_exact_verified",
    "package_key_set_unchanged_verified",
    "package_version_v1_to_v2_only_verified",
    "selection_creation_authority_owner_verified",
    "selection_creation_authority_user_isolation_verified",
    "selection_creation_path_equivalence_verified",
    "request_id_idempotence_defined",
    "same_request_id_returns_same_revision_without_extra_rows_verified",
    "previous_revision_compare_and_swap_defined",
    "single_transaction_atomicity_defined",
    "on_error_stop_enabled",
    "before_after_scope_proof_defined",
    "other_users_unchanged_verified",
    "projection_change_unchanged_verified",
    "zero_trading_side_effects_verified",
    "target_pending_revision_only_verified",
    "historical_harness_transactions_automatically_aborted_verified",
    "historical_harness_failure_sequence_exact_verified",
    "prior_official_selection_function_calls_zero_verified",
    "prior_revision_item_dml_zero_verified",
    "prior_commit_zero_verified",
    "prior_request_id_absent_verified",
    "prior_before_after_hashes_identical_verified",
    "historical_failures_exact_pre_dml_harness_verified",
    "historical_failure_evidence_immutable_verified",
    "guard_repair_audit_only_verified",
    "guard_repair_semantically_correct_verified",
    "official_selection_function_unchanged_verified",
    "fresh_live_preflight_passed",
    "preflight_independent_transaction_verified",
    "preflight_transaction_read_only_verified",
    "all_complex_validation_completed_in_preflight_verified",
    "mutation_statement_classes_exact_verified",
    "mutation_official_function_single_select_verified",
    "request_id_bound_by_shell_or_driver_verified",
    "request_id_hash_auditable_verified",
    "request_id_token_secret_redaction_verified",
    "new_request_id_distinct_from_prior_verified",
    "recovery_is_not_retry_verified"
  ],
  "required_false_fields": [
    "all_users_requested",
    "multi_scope_requested",
    "non_current_trade_date_requested",
    "closed_trade_date_requested",
    "package_key_set_change_requested",
    "strategy_write_enable_requested",
    "web_put_requested",
    "evaluator_operation_requested",
    "virtual_executor_operation_requested",
    "migration_083_missing_or_uncommitted",
    "existing_pending_revision_detected",
    "existing_v2_selection_item_detected",
    "active_predecessor_drift_detected",
    "direct_activation_requested",
    "non_pending_selection_status_requested",
    "non_pending_replay_status_requested",
    "migration_082_compensation_function_call_requested",
    "projection_write_requested",
    "change_write_requested",
    "catalog_write_requested",
    "schema_write_requested",
    "extra_table_write_requested",
    "n1_n5_write_requested",
    "outbox_inbox_checkpoint_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "long_term_worker_requested",
    "policy_governance_session_execution_requested",
    "rollback_requested",
    "concurrent_runtime_change",
    "postflight_hash_drift_detected",
    "catalog_state_drift_detected",
    "prior_official_selection_function_called",
    "prior_revision_item_dml_detected",
    "prior_commit_detected",
    "prior_request_id_persisted",
    "prior_before_after_hash_drift_detected",
    "historical_harness_failure_reason_or_order_differs",
    "third_pre_dml_harness_transaction_requested",
    "third_pre_dml_error_kind_detected",
    "same_request_id_requested",
    "second_mutation_attempt_requested",
    "official_selection_function_modification_requested",
    "guard_repair_outside_audit_requested",
    "mutation_do_block_requested",
    "mutation_psql_variable_interpolation_requested",
    "mutation_dynamic_sql_requested",
    "mutation_complex_validation_requested",
    "request_id_embedded_in_do_requested",
    "request_id_literal_or_secret_logged"
  ],
  "strategy_write_must_remain_zero": true,
  "web_write_path_used": false,
  "revision_activation_authorized": false,
  "transaction_not_committed_skips_sql_rollback": true,
  "rollback_requires_separate_authorization": true
}
```
<!-- policy:n6_strategy_center_post_083_single_user_pending_v2_revision_v1:end -->

Evaluation is fail-closed and ordered:

1. The later request must explicitly select this policy, recovery contract
   version, and `layer_role=N6_user`
   for the exact frozen canary scope. All-users, multiple scopes, a different
   predecessor, or a non-current/non-open trade date returns `REJECT`.
2. Immutable historical evidence must bind exactly two ordered pre-DML harness
   transactions: first SQLSTATE `42704`, `role "PUBLIC" does not exist`, at
   `public_execute_acl_audit_guard`; then SQLSTATE `42601` at the unexpanded
   `:'request_id'` token because the psql variable was placed inside a
   dollar-quoted `DO` body. Both must prove automatic
   transaction abort, zero official selection-function calls, zero
   revision/item DML, zero commits, no persisted request id, zero mutation
   attempts, and equality for every declared before/after hash pair. A third
   harness transaction, a third error kind, changed order/reason, or any
   nonzero/mismatched fact returns `REJECT`.
3. The only permitted guard correction is an audit-only
   `pg_catalog.aclexplode(COALESCE(proacl,
   pg_catalog.acldefault('f', proowner)))` check whose PUBLIC grantee is OID
   `0`. This handles both explicit and default function ACLs without treating
   `PUBLIC` as a role name. The official selection function must remain
   byte-for-byte unchanged. A fresh, independent `READ ONLY` preflight
   transaction must complete every complex validation before the later request
   may use a new request id.
4. Fresh evidence must prove committed 081/082/083 postflights, V2 active/V1
   grandfathered catalog state, strategy write `0`, evaluator job/PID absence,
   and frozen, write-disjoint, unoperated virtual executor state.
5. The target must have zero pending revisions and zero V2 items, exactly one
   active V1 predecessor, and the same package-key set. Only package_1 version
   v1 may become v2.
6. The write path must be the official owner/user-isolated selection creation
   function. The new request id must be supplied by shell/driver parameter
   binding, never embedded in `DO` or psql interpolation. Its SHA-256 may be
   traced, but the request-id value, token, and secrets must not be logged. The
   function must enforce request-id idempotence and
   `previous_revision_id=15` compare-and-swap.
7. One new transaction and at most one mutation attempt may insert only the
   pending revision and its single item. Its allowed statement classes are
   exactly `BEGIN`, `SET`, one advisory-lock `SELECT`, one official-function
   `SELECT`, read-only postflight `SELECT`, and `COMMIT`. `DO`, psql variable
   interpolation, dynamic SQL, and complex mutation-transaction validation are
   forbidden. The two aborted historical harness transactions are recorded
   separately and are not mutation attempts. A third harness transaction,
   reusing an old request id, a second mutation attempt, any retry, activation,
   compensation function, Web PUT, projection/change/catalog/schema, or
   extra-table write returns `REJECT`.
8. Postflight must prove pending/pending status, unchanged other users and
   projection/change watermarks, and zero N1-N5, queue, business, broker, or
   trading effect. Rollback is never part of this request.

### 4.8 Named Strategy Center Remaining-Users Pending V2 Revision

The first post-083 pending-V2 policy is permanently scoped to principal/user
1/1 and cannot be reused for later users. The following independent policy is
parameterized for exactly one remaining principal/user at a time; it does not
authorize an all-users sweep or a Web selection PUT.

<!-- policy:n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "N6_user",
  "scope_mode": "single_principal_user_pending_v2_revision",
  "phase_mode": "create_remaining_post_083_pending_v2_revision_once",
  "database_authority_mode": "owner_only",
  "required_strategy_write_flag_value": "1",
  "effective_trade_date_source": "n6_strategy_center_trade_date_authority_v1",
  "selection_creation_authority_mode": "official_owner_user_isolated_selection_function",
  "owner_selection_function_attestation_required": true,
  "scope_expansion_if_owner_function_missing": "owner_selection_function",
  "required_target_status": "pending",
  "required_target_replay_status": "pending",
  "required_package_version_transition": "same_active_v1_keys_to_v2",
  "required_mutation_statement_classes": [
    "BEGIN", "SET", "SELECT_ADVISORY_XACT_LOCK",
    "SELECT_OFFICIAL_SELECTION_FUNCTION",
    "SELECT_READ_ONLY_POSTFLIGHT", "COMMIT"
  ],
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_user_strategy_selection_item"
  ],
  "allowed_mutations": [
    "insert_one_pending_selection_revision",
    "insert_v2_items_for_same_active_package_keys"
  ],
  "required_singleton_counts": {
    "scope_count": 1,
    "principal_count": 1,
    "user_count": 1,
    "predecessor_revision_count": 1,
    "target_revision_count": 1,
    "target_mutation_transaction_count": 1,
    "new_request_id_count": 1
  },
  "required_operation_counts": {
    "target_mutation_attempts": 1,
    "target_mutation_retries": 0,
    "target_advisory_lock_select_count": 1,
    "target_official_function_select_count": 1,
    "activation_attempts": 0,
    "web_put_attempts": 0,
    "evaluator_operation_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "projection_change_write_attempts": 0,
    "forbidden_business_write_attempts": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "exact_single_scope_authorized",
    "governance_policy_integrated_verified",
    "current_trade_date_matches_n6_authority",
    "current_trade_date_open_verified",
    "migration_081_082_083_postflight_hashes_verified",
    "v2_catalog_active_verified",
    "v1_catalog_grandfathered_verified",
    "active_predecessor_exact_verified",
    "target_scope_pending_zero_verified",
    "target_scope_v2_item_zero_verified",
    "same_package_keys_verified",
    "target_revision_no_predecessor_plus_one_verified",
    "previous_revision_cas_verified",
    "selection_creation_authority_owner_verified",
    "selection_creation_authority_user_isolation_verified",
    "selection_creation_function_attested_immutable",
    "selection_creation_path_not_web_put",
    "request_id_idempotence_defined",
    "fresh_read_only_preflight_verified",
    "strategy_write_flag_stable_verified",
    "evaluator_coexistence_stable_verified",
    "virtual_executor_not_operated_verified",
    "single_transaction_atomicity_defined",
    "on_error_stop_enabled",
    "before_after_scope_proof_defined",
    "other_users_unchanged_verified",
    "projection_change_unchanged_verified",
    "zero_forbidden_side_effects_verified"
  ],
  "required_false_fields": [
    "all_users_requested",
    "multi_scope_requested",
    "non_current_trade_date_requested",
    "closed_trade_date_requested",
    "package_key_set_change_requested",
    "web_put_requested",
    "evaluator_operation_requested",
    "virtual_executor_operation_requested",
    "revision_activation_requested",
    "projection_write_requested",
    "change_write_requested",
    "catalog_write_requested",
    "schema_write_requested",
    "n1_n5_write_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "retry_requested",
    "second_mutation_attempt_requested",
    "owner_selection_function_missing",
    "concurrent_runtime_change",
    "scope_or_hash_drift"
  ],
  "strategy_write_must_remain_one": true,
  "web_write_path_used": false,
  "revision_activation_authorized": false,
  "rollback_requires_separate_authorization": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1:end -->

Evaluation is fail-closed: the request must provide positive principal/user,
active predecessor, target revision and current N6 authority date values. The
target package keys must equal the predecessor's v1 keys and every target item
must be v2. The predecessor and target are bound by one CAS; no hard-coded
principal, user, revision, or date is accepted. The formal owner-isolated
selection function must be independently attested before execution. The
existing session-token/Web `n6_btrack_strategy_selection_put` function and
manual SQL are not substitutes; if the owner function is absent, return
`scope_expansion_required=owner_selection_function` and `REJECT`.

One transaction may insert only the pending revision and its same-key v2
items. It cannot activate the revision, write projection/change, invoke an
evaluator, or touch Web, virtual executor, trading, or N1-N5 paths. A running
evaluator may coexist but cannot be operated; the migration must prove a stable
single-scope CAS and unchanged other-user/projection/change hashes. Any
all-users request, key change, predecessor/date/hash drift, missing owner
function, retry, second mutation, or forbidden side effect returns `REJECT`.

### 4.9 N6 B-track Reusable Delivery Policies

<!-- policy:n6_btrack_delivery_l1_web_readonly_v1:begin -->
```json
{
  "policy_id": "n6_btrack_delivery_l1_web_readonly_v1",
  "policy_family": "n6_btrack_delivery_lanes_v1",
  "layer_role": "N6_user",
  "lane": "L1",
  "default_runtime_execution_decision": "REJECT",
  "required_brief_fields": [
    "page_or_feature",
    "users",
    "expected_behavior",
    "affects_virtual_money_proposals_or_positions"
  ],
  "allowed_effects": [
    "n6_web_layout",
    "n6_web_copy",
    "n6_read_only_query",
    "n6_filter_display",
    "separate_exact_web_release_rebind"
  ],
  "forbidden_effects": [
    "database_write",
    "migration",
    "quote_writer_change",
    "executor_change",
    "stop_loss_change",
    "proposal_order_trade_cash_position_lot",
    "real_broker",
    "n1_n5_writeback"
  ],
  "max_mutating_gates": 2,
  "governance_session_cannot_execute": true,
  "legacy_contract_sha256": "64c31c8b992029072461aaee430bc44f3724a803ff3edb48ce6a3bb339d5dd13",
  "deployment_phase_contract": {
    "phase_id": "post_decommission_web_readonly_rebind",
    "layer_role": "runtime_control",
    "source": "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json#/lanes/L1/deployment_phases/post_decommission_web_readonly_rebind",
    "source_policy_legacy_contract_sha256": "ff9d899636e0e742d833709eb3e778781522b33b0800557ce2ef30173b2f1a47",
    "exact_source_object_required": true,
    "missing_or_source_mismatch_decision": "REJECT",
    "governance_session_runtime_operation_allowed": false
  }
}
```
<!-- policy:n6_btrack_delivery_l1_web_readonly_v1:end -->

The L1 deployment phase above is not a new policy and does not revive any
historical one-off Strategy Center policy. It compiles only after an L1
classification `ACCEPT`, and only for a separately authorized
`runtime_control` deployment of a Web/read-only, UX-only, non-Strategy,
non-regressing candidate whose source and target both retain Strategy Center
decommission.

The referenced phase object is the complete value-level authority. Kernel
evaluation requires exact equality with that object: strategy-write is `0` at
live/source/target/readiness/rollback; the exact Strategy evaluator is absent
and has zero operations; the virtual executor has zero operations and remains
object-disjoint from Web while normal StartInterval PID/runs rotation is not
drift. The retired page remains an exact `307` to
`/n6/app/signals?notice=strategy_center_retired`; all three retired Strategy
APIs remain exact `410`, `Cache-Control: no-store`, and
`code=strategy_center_retired`.

The target Release always requires a Release-specific immutable manifest that
binds target commit/tree, exact archive/fileset, per-entry mode/owner/SHA, the
canonical retirement exclusion set, and filesystem/object hash. A pre-manifest
legacy source may instead be frozen by read-only reconstruction of exact source
commit/tree, exact canonical exclusions, full present-fileset Git blob/mode
equivalence, no extras, sealed owner/mode, no write bits or symlinks, and a
deterministic filesystem/object hash. Reconstruction is source/rollback-only:
it cannot write back to the legacy Release or substitute for the target
manifest. Missing, ambiguous, extra, or drifted evidence returns `REJECT`.

The Web plist may change only WorkingDirectory/PYTHONPATH Release bindings.
ProgramArguments must contain exactly two byte-identical source/target tokens:
either literal `python3` or a frozen absolute immutable system interpreter,
followed by relative `scripts/run_n6_user_app.py` without `..`. The absolute
interpreter token may be a frozen symlink chain. Its token, every hop and
readlink text, resolved canonical regular target, and the full trusted path
chain from `/Library` through the Python 3.11 bin boundary must remain within
that boundary where applicable, be escape/cycle/ambiguity-free, and have exact
source/target owner/group/mode/flags/ACL/SHA evidence. The Web service principal
must be neither the owner nor a member of a write-enabled group, and no ACL or
flags may grant it write access; every path-chain object must be effectively
non-writable by that principal. The interpreter is not Release-bound, cannot be
replaced, and has replacement count `0`. The relative script must resolve inside
the target Release and be regular, non-symlink, non-writable, and exact against
its target-manifest owner/mode/hash entry. Mixed forms, extra argv, or
interpreter/script/evidence drift returns `REJECT`.

The primary budget is one safe plist replace/swap, one bootout, a wait of at
least one second followed by old job/PID absence, and one bootstrap. Kickstart,
retry, downgrade, or a second primary attempt is forbidden; only primary
failure permits one frozen-source rollback. Database, N1-N5, evaluator,
virtual-executor, business, proposal, cash, position, and trade effects must
all remain zero. Missing fields or classification, runner, route, plist,
side-effect, or operation-count drift returns `REJECT`.

<!-- policy:n6_btrack_delivery_l2_n6_business_v1:begin -->
```json
{
  "policy_id": "n6_btrack_delivery_l2_n6_business_v1",
  "policy_family": "n6_btrack_delivery_lanes_v1",
  "layer_role": "N6_user",
  "lane": "L2",
  "default_runtime_execution_decision": "REJECT",
  "required_phases": [
    "offline_implementation_and_pg16",
    "exact_n6_migration_with_rollback",
    "immutable_release_rebind",
    "read_only_acceptance"
  ],
  "required_controls": [
    "full_migration_filename_identity",
    "owner_acl_security_definer_search_path",
    "business_table_pre_post_digest",
    "rollback_round_trip"
  ],
  "forbidden_effects": [
    "automatic_virtual_money_effect",
    "automatic_proposal_creation",
    "automatic_proposal_confirmation",
    "real_broker",
    "n1_n5_writeback"
  ],
  "bounded_consumer_phase_contract": {
    "phase_id": "trigger_status_projection_20260731_backfill",
    "layer_role": "N6_user",
    "source": "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json#/lanes/L2/bounded_consumer_phases/trigger_status_projection_20260731_backfill",
    "exact_source_object_required": true,
    "missing_or_source_mismatch_decision": "REJECT",
    "governance_session_runtime_operation_allowed": false
  },
  "current_day_bounded_recovery_phase_contract": {
    "phase_id": "trigger_status_projection_20260803_recovery",
    "policy_id": "n5_n6_trigger_status_current_day_bounded_recovery_20260803_v1",
    "layer_role": "N6_user",
    "source": "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json#/lanes/L2/bounded_consumer_phases/trigger_status_projection_20260803_recovery",
    "exact_source_object_required": true,
    "missing_or_source_mismatch_decision": "REJECT",
    "governance_session_runtime_operation_allowed": false
  },
  "trigger_status_scheduled_convergence_contract": {
    "policy_id": "n5_n6_trigger_status_scheduled_convergence_30s_v1",
    "source": "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json#/lanes/L2/scheduled_convergence_phases",
    "exact_source_object_required": true,
    "activation_order": ["trigger_status_n5_forward_scheduler_activation", "trigger_status_n6_projection_scheduler_activation"],
    "missing_or_source_mismatch_decision": "REJECT",
    "governance_session_runtime_operation_allowed": false
  },
  "web_deployment_phase_contract": {
    "phase_id": "trigger_status_web_immutable_release_rebind",
    "operation_class": "single_web_immutable_release_rebind",
    "executor_role": "runtime_control",
    "source": "docs/N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json#/lanes/L2/deployment_phases/trigger_status_web_immutable_release_rebind",
    "exact_source_object_required": true,
    "missing_or_source_mismatch_decision": "REJECT",
    "legacy_named_policy_or_l1_substitution_decision": "REJECT",
    "governance_session_runtime_operation_allowed": false
  },
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_btrack_delivery_l2_n6_business_v1:end -->

The L2 `trigger_status_web_immutable_release_rebind` phase accepts only the
exact source object above in a later, independently authorized
`runtime_control` request. It binds canonical target
`985202144febffeef3302012675f285e1cf1061a` /
`f741f0f0cd7d80648f9897267eb0b2ac8410f9f0`, the complete reviewed 27-file
lineage from `16950435d4e407890f98234f35fa507ed1a11441`, completed 089 and
2296-row consumer `PASS` evidence, and the frozen active Web Release/plist as
the sole rollback target. `n6_user_web_immutable_release_bounded_rebind_v1`,
L1, and `post_decommission_web_readonly_rebind` are not substitutes.

The phase may build exactly one fresh immutable Release, apply owner/mode/ACL/
xattr/flags before manifest/seal/byte verification, and change only the exact
Web Release binding, WorkingDirectory, and PYTHONPATH. It permits one safe
plist replace/swap, one bootout, and one bootstrap; kickstart, retry, a second
primary execution, Release reuse/overwrite, or rollback-target substitution
returns `REJECT`. Strategy-write stays `0`; the Strategy evaluator remains on
its freshly frozen baseline with zero operations; the loaded virtual executor
may rotate naturally but cannot be stopped, started, or modified.

Database connection, consumer, migration, rollback, other-service, scheduler,
N1-N6 business, proposal/cash/position/trade, browser, and push effects are
zero. Unauthenticated curl probes are GET/HEAD only: Strategy APIs retain 410,
the status-monitor API retains 401, trigger-status schema/API/UI/payload remain
free of `trigger_pct`, and all other routes remain unchanged.
Postflight must freeze target commit/tree/manifest/plist, new PID/cwd/argv,
listen 127.0.0.1:8786, and route evidence. Authenticated DOM acceptance at
desktop and 320/375/390/430 remains a separate gate and cannot be claimed here.

<!-- policy:n6_btrack_delivery_l3_virtual_runtime_v1:begin -->
```json
{
  "policy_id": "n6_btrack_delivery_l3_virtual_runtime_v1",
  "policy_family": "n6_btrack_delivery_lanes_v1",
  "layer_role": "N6_user",
  "lane": "L3",
  "default_runtime_execution_decision": "REJECT",
  "required_phases": [
    "offline_implementation_and_full_n6_regression",
    "migration_and_immutable_release",
    "bounded_virtual_smoke",
    "confirmed_queue_governance",
    "separate_continuous_runtime_authorization"
  ],
  "required_controls": [
    "explicit_current_request_authorization",
    "two_stage_human_confirmation",
    "claim_apply_fail_closed",
    "independent_service_role",
    "proposal_order_trade_cash_position_lot_audit",
    "immediate_bootout_plan"
  ],
  "forbidden_effects": [
    "automatic_proposal_creation",
    "automatic_proposal_confirmation",
    "real_broker",
    "real_order",
    "n1_n5_writeback"
  ],
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_btrack_delivery_l3_virtual_runtime_v1:end -->

These policies classify and constrain work; they do not authorize their
defining governance session to deploy or execute it. Exactly one lane must
match. Missing brief fields, mixed lanes, a request for a new one-off policy
where a reusable lane applies, or any forbidden effect returns `REJECT`.

## 5. Execution Flow

```text
1. parse request
2. normalize task
3. evaluate kernel
4. decision gate
5. execute only if ACCEPT
```

Expanded flow:

```text
parse request
  -> identify intent, layer_role, affected_files, data_flow, risk_level

normalize task
  -> convert the request into kernel_input
  -> remove assumptions
  -> mark missing fields

evaluate kernel
  -> apply hard validation rules
  -> detect cross-layer mutation
  -> detect forbidden runtime execution
  -> detect ambiguity

decision gate
  -> ACCEPT: continue
  -> REJECT: stop
  -> BLOCK: stop and request missing information
  -> ESCALATE: stop and hand off to the correct gate or layer

execute only if ACCEPT
  -> perform only the approved action
  -> touch only approved files
  -> do not introduce runtime behavior
```

## 6. Golden Rule

No execution without kernel approval.
<!-- policy:n6_strategy_center_reviewed_view_date_authority_084_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_reviewed_view_date_authority_084_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "migration_id": "084",
  "phase_mode": "execute_084_forward_once",
  "required_authority_views": ["v_n6_stock_condition_display_basis", "v_n6_index_condition_display_basis", "v_n6_board_condition_display_basis"],
  "authority_rule": "latest_complete_single_batch_for_trade_date_consensus",
  "required_authority_fields": ["for_trade_date", "source_trade_date", "source_run_id", "row_count"],
  "membership_rule": "max_trade_date_lte_source_trade_date",
  "attempts": 1,
  "retries": 0,
  "function_calls": 0,
  "evaluator_must_be_quiesced": true,
  "web_strategy_write": 0,
  "compensation_function_calls": 0,
  "forbidden_objects": ["common_trade_calendar", "selection_revision", "selection_item", "match_projection", "observation_projection", "match_change", "catalog", "proposal", "order", "trade", "position", "cash"]
}
```
<!-- policy:n6_strategy_center_reviewed_view_date_authority_084_v1:end -->

<!-- policy:n6_strategy_center_post_canary_web_write_restore_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_canary_web_write_restore_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "launch_agent_label": "com.ashare-v3.n6.user-web",
  "required_flag_before": "0",
  "required_flag_after": "1",
  "required_canary": "display_only_bounded_canary_pass",
  "required_evaluator_ticks": 12,
  "required_pending_count": 0,
  "max_bootout_attempts": 1,
  "max_bootstrap_attempts": 1,
  "max_retries": 0,
  "evaluator_must_remain_quiesced": true,
  "virtual_executor_operations": 0,
  "database_writes": 0,
  "trade_writes": 0
}
```
<!-- policy:n6_strategy_center_post_canary_web_write_restore_v1:end -->

<!-- policy:n6_strategy_center_post_083_multi_user_pending_v2_revision_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_083_multi_user_pending_v2_revision_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "scope_mode": "single_principal_user_revision_per_transaction",
  "phase_mode": "post_083_create_one_pending_v2_revision_once",
  "required_user_authorization": true,
  "required_081_committed": true,
  "required_082_committed": true,
  "required_083_committed": true,
  "required_strategy_write_flag": "0",
  "required_evaluator_job_absent": true,
  "required_evaluator_pid_absent": true,
  "virtual_executor_operations": 0,
  "required_current_n6_trade_date_authority": true,
  "required_predecessor_active_v1": true,
  "required_predecessor_cas": true,
  "required_target_v2_catalog_active": true,
  "required_pending_before": 0,
  "required_projection_change_writes": 0,
  "required_mutation_attempts": 1,
  "required_retries": 0,
  "allowed_write_function": "public.n6_strategy_center_migrate_v2_selection_v1(bigint,bigint,bigint,bigint,text)",
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_user_strategy_selection_item"
  ],
  "forbidden_write_tables": [
    "n6_strategy_match_projection",
    "n6_strategy_match_change",
    "n6_strategy_observation_projection",
    "proposal",
    "order",
    "trade",
    "position",
    "cash",
    "N1-N5"
  ],
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"]
}
```
<!-- policy:n6_strategy_center_post_083_multi_user_pending_v2_revision_v1:end -->

### 4.12 N6 Strategy Center Resumable Shadow-Activation Grant

This policy is usable only by a later independent `runtime_control` execution
request. A governance request that creates, repairs, or attests it cannot use it
in the same session. The default remains fail-closed.

<!-- policy:n6_strategy_center_shadow_activation_grant_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_shadow_activation_grant_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "required_parent_approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "required_supersession_manifest": true,
  "required_manifest_sha_chain": true,
  "required_external_governance_attestation": true,
  "required_hash_chain_checkpoints": {
    "GOVERNANCE": "passed",
    "EVALUATOR_RESUME_FIX": "passed",
    "BOUNDED_REBIND": "running"
  },
  "required_internal_checkpoints": {
    "BOUNDED_REBIND_WEB_TARGET": "planned",
    "BOUNDED_REBIND_EVALUATOR_TARGET": "blocked_pending_canary"
  },
  "required_active_stage_lease": "BOUNDED_REBIND_WEB_TARGET",
  "required_control_plane_commit": "72b1d50b6658d89e3aff6ed15619b875814f8e5e",
  "required_control_plane_tree": "f7e835e53146e30b8ab4ed8096133b1e14b14a12",
  "required_source_web_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
  "required_source_web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
  "required_web_strategy_write_before": "0",
  "required_web_strategy_write_after": "0",
  "required_target_commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "required_target_tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
  "required_target_bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
  "required_target_bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
  "required_live_anchor_revalidation": true,
  "allowed_drift": ["operational_source_runtime_anchor"],
  "semantic_drift_terminates_parent_approval": true,
  "required_lineage_proofs": ["original_web_source_to_current_web_source", "current_web_source_to_target", "current_evaluator_source_to_target"],
  "required_non_regression": ["critical_n6_blobs", "api_contract", "strategy_semantics", "virtual_executor_boundary", "N1-N5_boundary", "trading_boundary"],
  "web_target_exact_label": "com.ashare-v3.n6.user-web",
  "evaluator_target_exact_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "web_target_max_bootout_attempts": 1,
  "web_target_max_atomic_plist_replacements": 1,
  "web_target_max_bootstrap_attempts": 1,
  "web_target_evaluator_job_must_remain_absent": true,
  "web_target_evaluator_runner_count": 0,
  "evaluator_target_requires_web_target_passed": true,
  "evaluator_target_requires_current_date_bounded_canary_pass": true,
  "evaluator_target_pre_canary_status": "blocked_pending_canary",
  "evaluator_target_pre_canary_bootstrap_attempts": 0,
  "max_exact_source_restore_attempts": 1,
  "restore_empty_state": false,
  "kickstart_attempts": 0,
  "runner_attempts": 0,
  "canary_attempts": 0,
  "virtual_executor_operations": 0,
  "database_writes": 0,
  "N1-N5_writes": 0,
  "broker_writes": 0,
  "trade_writes": 0,
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"]
}
```
<!-- policy:n6_strategy_center_shadow_activation_grant_v1:end -->

### 4.13 Pre-Canary Web Strategy-Write Quiesce

<!-- policy:n6_strategy_center_pre_canary_web_write_quiesce_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_pre_canary_web_write_quiesce_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_exact_web_strategy_write_flag_only",
  "phase_mode": "post_083_pre_canary_strategy_write_quiesce",
  "launch_agent_label": "com.ashare-v3.n6.user-web",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
  "strategy_write_flag_name": "ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED",
  "required_flag_before": "1",
  "required_flag_target": "0",
  "required_flag_after": "0",
  "rollback_flag_value": "1",
  "required_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
  "required_release_tree": "d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1",
  "source_target_release_relation": "same_exact_immutable_release",
  "allowed_mutation_resources": [
    "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
    "gui/current_uid/com.ashare-v3.n6.user-web"
  ],
  "allowed_runtime_operations": [
    "install_exact_web_plist_flag_one_to_zero_only",
    "launchctl_bootout_exact_web_label_once",
    "state_driven_wait_for_old_web_pid_and_job_absence",
    "launchctl_bootstrap_exact_web_label_once",
    "readiness_and_stability_observation",
    "conditional_restore_frozen_web_plist_flag_one_once"
  ],
  "required_hash_fields": {
    "release_archive_sha256": "^[0-9a-f]{64}$",
    "release_manifest_sha256": "^[0-9a-f]{64}$",
    "release_filesystem_sha256": "^[0-9a-f]{64}$",
    "web_plist_before_sha256": "^[0-9a-f]{64}$",
    "web_plist_target_sha256": "^[0-9a-f]{64}$",
    "evaluator_plist_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_boundary_sha256": "^[0-9a-f]{64}$"
  },
  "required_singleton_counts": {
    "web_label_count": 1,
    "source_release_count": 1,
    "target_release_count": 1,
    "web_bootout_attempts": 1,
    "web_bootstrap_attempts": 1,
    "primary_retries": 0,
    "evaluator_operation_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "database_connection_attempts": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "post_083_state_verified",
    "exact_web_launchd_ownership_verified",
    "web_pid_argv_cwd_environment_frozen",
    "web_plist_owner_group_mode_acl_xattr_frozen",
    "strategy_write_before_one_verified",
    "target_plist_only_flag_one_to_zero_verified",
    "strategy_write_target_zero_verified",
    "source_target_release_same_verified",
    "d85_release_commit_tree_verified",
    "release_archive_manifest_filesystem_verified",
    "release_immutable_verified",
    "evaluator_job_absent_verified",
    "evaluator_runner_process_count_zero_verified",
    "evaluator_not_operated_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "state_driven_teardown_defined",
    "readiness_60s_defined",
    "stability_30s_defined",
    "routes_and_strategy_write_zero_postflight_defined",
    "rollback_to_frozen_flag_one_defined",
    "zero_forbidden_side_effects_verified"
  ],
  "required_false_fields": [
    "web_release_change_requested",
    "working_directory_change_requested",
    "pythonpath_change_requested",
    "non_flag_environment_change_requested",
    "second_web_service_requested",
    "second_primary_attempt_requested",
    "kickstart_requested",
    "kill_or_signal_requested",
    "evaluator_operation_requested",
    "virtual_executor_operation_requested",
    "database_connection_requested",
    "migration_requested",
    "bounded_canary_requested_in_same_gate",
    "selection_projection_change_requested",
    "n1_n5_write_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "release_or_plist_hash_drift_detected",
    "runtime_ownership_ambiguous",
    "concurrent_runtime_change"
  ],
  "teardown_timeout_seconds": 30,
  "readiness_timeout_seconds": 60,
  "stability_observation_seconds": 30,
  "maximum_rollback_bootout_attempts": 1,
  "maximum_rollback_bootstrap_attempts": 1,
  "rollback_requires_primary_health_failure": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_pre_canary_web_write_quiesce_v1:end -->

This historical Gate3+ prerequisite preserves the `72b1d50` control-plane
contract. The current resumable WEB_TARGET already starts with strategy-write
`0`; it must not rerun this flag-only gate.

## F464 immutable Release privileged materialize-and-install governance

This policy is an artifact-only `runtime_control` governance contract under
parent approval `N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION`. Creating,
testing, compiling, signing, or attesting the helper does not authorize this
governance session to install or invoke it, materialize a Release, change a
plist, operate a service, connect to a database, run the Evaluator, or operate
the Virtual Executor.

Only a later, independent `runtime_control` execution session may install the
exact attested helper once and invoke it once. A non-zero helper result is final:
the execution session must preserve that invocation's staging directory, stop,
and must not retry, overwrite, delete, or reuse any Release or staging path.

<!-- policy:n6_immutable_release_privileged_materialize_and_install_f464_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_privileged_materialize_and_install_f464_v1",
  "canonical_status": "superseded_noncanonical",
  "superseded_by_policy_id": "n6_f464_user_owned_immutable_release_install_v1",
  "historical_governance_commit": "90ff911f5692c50f373f5a11a9a2804d9a9e828c",
  "historical_governance_tree": "9a5717d945cd3b0f8f1720d7f942498aa5fcf1e0",
  "future_install_or_invocation_allowed": false,
  "future_retry_allowed": false,
  "future_privilege_elevation_allowed": false,
  "historical_failure_evidence_must_remain_append_only": true,
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_frozen_f464_privileged_materialize_install",
  "phase_mode": "installer_governance_and_helper_attestation_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "candidate_root": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "frozen_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar",
  "frozen_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.git-ls-tree.nul",
  "frozen_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release-attestation.json",
  "target_release_name": "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "staging_release_name": ".staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "staging_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "helper_install_path": "/usr/local/libexec/ashare-v3/n6-f464-immutable-release-materializer-v2",
  "compiled_helper_artifact_path": "/Users/chuanfuchen/.codex/artifacts/n6_f464_installer_governance_v1/20260726_102300__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/n6-f464-immutable-release-materializer-v2",
  "required_exact_values": {
    "release_commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "release_tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
    "implementation_commit": "5c2c38d184385a317afe69b6397f7d98393ff24f",
    "implementation_tree": "0a02ac53513946ca530d3420b2bd06c60630388e",
    "archive_sha256": "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
    "manifest_sha256": "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
    "filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "release_attestation_sha256": "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
    "helper_source_sha256": "0a65b324c17122f1ff7f8ac50403b95239c540d54ec8736f94899f7ac863c4f3",
    "helper_binary_sha256": "3db62fefad54d8b5eb19de51467510065183cf7aa715eb82835fc5fab468bf36",
    "helper_codesign_cdhash": "17e5cc8aeb7b1402d60981c3eb1494c588420477",
    "helper_architecture": "arm64",
    "helper_installed_owner": "root",
    "helper_installed_group": "wheel",
    "helper_installed_mode": "0500",
    "target_final_directory_mode": "0555",
    "target_final_regular_file_mode": "0444",
    "target_final_executable_file_mode": "0555"
  },
  "required_resource_fields": [
    "archive_path",
    "manifest_path",
    "release_attestation_path",
    "target_release_path",
    "staging_release_path",
    "helper_source_path",
    "helper_install_path",
    "compiled_helper_artifact_path"
  ],
  "required_singleton_counts": {
    "candidate_count": 1,
    "archive_count": 1,
    "manifest_count": 1,
    "release_attestation_count": 1,
    "target_release_count": 1,
    "new_staging_release_count": 1,
    "archive_hash_verification_count": 1,
    "manifest_hash_verification_count": 1,
    "archive_expected_file_count": 6240,
    "archive_expected_directory_count": 45,
    "archive_expected_writable_entry_count": 0,
    "archive_pax_global_header_count": 1,
    "archive_pax_extended_header_count": 108,
    "renameatx_np_count": 1,
    "governance_session_helper_install_count": 0,
    "governance_session_helper_invocation_count": 0,
    "later_execution_max_helper_install_count": 1,
    "later_execution_max_helper_invocation_count": 1,
    "retry_count": 0
  },
  "required_true_fields": [
    "explicit_parent_approval_inherited",
    "governance_commit_tree_baseline_verified",
    "l2_canonical_sha256_verified",
    "activation_state_checkpoint_verified",
    "candidate_archive_manifest_attestation_hashes_verified",
    "candidate_commit_tree_implementation_lineage_verified",
    "candidate_filesystem_hash_verified",
    "candidate_bundle_hashes_verified",
    "candidate_file_directory_counts_verified",
    "candidate_writable_entry_count_zero_verified",
    "helper_source_sha256_verified",
    "helper_binary_sha256_verified",
    "helper_codesign_cdhash_verified",
    "helper_architecture_arm64_verified",
    "helper_adhoc_signature_verified",
    "helper_effective_uid_root_required",
    "helper_zero_argument_interface_verified",
    "helper_fixed_paths_verified",
    "helper_same_parent_staging_verified",
    "helper_dirfd_only_target_mutation_verified",
    "archive_ustar_checksum_verified",
    "archive_pax_global_comment_commit_verified",
    "archive_pax_extended_path_only_verified",
    "archive_pax_strict_record_framing_verified",
    "archive_safe_paths_verified",
    "archive_no_symlink_hardlink_device_fifo_verified",
    "archive_mode_verified",
    "archive_git_blob_hashes_verified_against_manifest",
    "archive_file_directory_counts_verified",
    "renameatx_np_available_verified",
    "helper_rename_excl_verified",
    "helper_nofollow_verified",
    "helper_resolve_beneath_verified",
    "target_absent_verified",
    "staging_absent_verified",
    "target_name_binds_full_release_commit_verified",
    "failure_preserves_current_staging_defined",
    "success_seals_files_0444_0555_defined",
    "success_seals_directories_0555_defined",
    "existing_releases_unchanged_verified",
    "later_execution_nonzero_stop_without_retry_defined",
    "web_target_running_checkpoint_preserved",
    "evaluator_absent_runner_zero_preserved",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "governance_session_helper_install_requested",
    "governance_session_helper_invocation_requested",
    "release_install_requested_in_governance_session",
    "candidate_input_drift_detected",
    "archive_count_drift_detected",
    "archive_hash_drift_detected",
    "manifest_hash_drift_detected",
    "filesystem_hash_drift_detected",
    "release_attestation_hash_drift_detected",
    "bundle_hash_drift_detected",
    "target_release_exists_before_install",
    "staging_release_exists_before_install",
    "unknown_tar_type_requested",
    "invalid_tar_checksum_detected",
    "invalid_pax_record_detected",
    "unexpected_pax_key_detected",
    "unsafe_archive_path_detected",
    "archive_link_or_special_entry_detected",
    "helper_shell_execution_requested",
    "helper_arbitrary_path_requested",
    "helper_recursive_copy_requested",
    "helper_delete_requested",
    "helper_overwrite_requested",
    "helper_xattr_acl_requested",
    "non_atomic_fallback_requested",
    "partial_final_path_exposed",
    "release_content_modified_after_rename",
    "retry_requested",
    "old_release_delete_requested",
    "old_release_overwrite_requested",
    "launch_agent_touched",
    "plist_touched",
    "service_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "runner_requested",
    "canary_requested",
    "deepseek_requested",
    "n1_n5_business_mutation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "lot_touched",
    "cash_touched",
    "concurrent_runtime_change",
    "multiple_targets_requested",
    "authority_expansion_requested"
  ],
  "allowed_governance_mutation_resources": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py",
    "isolated_compiled_helper_artifact",
    "external_helper_attestation",
    "append_only_activation_state_evidence",
    "same_target_same_checkpoint_closeout_lease"
  ],
  "allowed_later_execution_mutation_resources": [
    "/usr/local/libexec/ashare-v3/n6-f464-immutable-release-materializer-v2",
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "append_only_runtime_control_execution_attestation"
  ],
  "allowed_governance_operations": [
    "read_only_verify_frozen_candidate_and_live_anchors",
    "compile_unsigned_source_in_isolated_artifact_directory",
    "adhoc_codesign_isolated_compiled_helper",
    "static_and_dry_fixture_validation",
    "write_external_helper_attestation_after_governance_commit",
    "append_installer_governance_planned_and_passed_evidence",
    "renew_same_web_target_same_checkpoint_closeout_lease"
  ],
  "allowed_later_execution_operations": [
    "install_exact_attested_helper_once",
    "invoke_exact_attested_helper_once",
    "stop_without_retry_on_nonzero",
    "preserve_failed_staging",
    "verify_exact_target_after_zero_exit"
  ],
  "forbidden_helper_functions": [
    "system",
    "popen",
    "posix_spawn",
    "execve",
    "execl",
    "execvp",
    "unlink",
    "unlinkat",
    "remove",
    "rmdir",
    "rename",
    "renameat"
  ],
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "virtual_executor_operations_allowed": false,
  "n1_n5_business_operations_allowed": false,
  "web_target_may_be_recorded_running_only": true,
  "evaluator_target_status": "blocked_pending_canary"
}
```
<!-- policy:n6_immutable_release_privileged_materialize_and_install_f464_v1:end -->

## F464 Release root owner remediation governance

This policy is a minimal, one-time, fail-closed `runtime_control` governance
contract. It does not change the failed `BOUNDED_REBIND_WEB_TARGET` checkpoint
to passed. This governance session may only compile, ad-hoc sign, attest, and
statically test the exact remediation helper. It may append governance evidence
and issue a same-target remediation-only checkpoint lease, but it may not
install or invoke either the remediation helper or the F464 installer helper.

Only a later independent `runtime_control` execution session holding the exact
unexpired remediation lease may install the attested remediation helper once
and invoke it once with zero arguments as root. Any precondition drift or
non-zero result is final and forbids retry.

<!-- policy:n6_f464_release_root_owner_remediation_v1:begin -->
```json
{
  "policy_id": "n6_f464_release_root_owner_remediation_v1",
  "canonical_status": "superseded_noncanonical",
  "superseded_by_policy_id": "n6_f464_user_owned_immutable_release_install_v1",
  "historical_governance_commit": "a29b064555027cd4bba7c4a833515b7adbbdd900",
  "historical_governance_tree": "d55ad7c15502f97a4ae3668fe576d7e6ff76ee3c",
  "future_install_or_invocation_allowed": false,
  "future_retry_allowed": false,
  "future_uid_501_to_0_change_allowed": false,
  "future_privilege_elevation_allowed": false,
  "historical_failure_evidence_must_remain_append_only": true,
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "scope_mode": "single_exact_f464_release_root_owner_remediation",
  "phase_mode": "governance_compile_codesign_attest_static_test_only",
  "base_governance_commit": "90ff911f5692c50f373f5a11a9a2804d9a9e828c",
  "base_governance_tree": "9a5717d945cd3b0f8f1720d7f942498aa5fcf1e0",
  "failed_stage3d_thread": "019f9c48-a6fd-7ce2-8b18-33dbf7c955a7",
  "failed_result": "BLOCKED_INSTALL_PRECONDITION_DRIFT_NO_HELPER_CALL",
  "failed_target": "BOUNDED_REBIND_WEB_TARGET",
  "failed_target_status_must_remain": "failed",
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "05702a86ded105705ca85f4c0b80e5409db3828847b57cde1ed2a967b9e358b1",
  "activation_state_before_event_count": 35,
  "activation_state_before_tail_event_sha256": "1c296c7d65b65db24837ae768a8a113cc75c8ec9fcc09ca20176fa2610a25064",
  "activation_checkpoint_sha256_corrected": "b017511d6f8d95e9c4c3b971c914a216987a671631415b285e5df84e164c6a57",
  "activation_checkpoint_transcription_correction_required": true,
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_parent": "/Users/chuanfuchen/.local/share/ashare-v3/releases",
  "release_root_basename": "n6-b-track",
  "release_root_before": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "release_root_after": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 0,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "f464_official_target_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "f464_official_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "f464_installer_helper_path": "/usr/local/libexec/ashare-v3/n6-f464-immutable-release-materializer-v2",
  "required_absent_before_and_after": [
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "/usr/local/libexec/ashare-v3/n6-f464-immutable-release-materializer-v2"
  ],
  "remediation_helper_source_path": "scripts/n6_f464_release_root_owner_remediation_v1.c",
  "remediation_helper_install_path": "/usr/local/libexec/ashare-v3/n6-f464-release-root-owner-remediation-v1",
  "compiled_helper_artifact_path": "/Users/chuanfuchen/.codex/artifacts/n6_f464_release_root_owner_remediation_governance_v1/20260726_025944__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/n6-f464-release-root-owner-remediation-v1",
  "helper_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_f464_release_root_owner_remediation_governance_v1/20260726_025944__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/f464-release-root-owner-remediation-helper-attestation.json",
  "required_helper_identity": {
    "source_sha256": "ff402d140179deab2549503cd487aaad3c1847e39fa63d6f0991e6c9fb7d39ef",
    "binary_sha256": "663ac6561469089eef02a505e80346219a2bbc490bf4289a618d93182d5c7968",
    "codesign_cdhash": "41671e1e984f498310b029ada2f4cbd412f7a18d",
    "signature": "adhoc",
    "architecture": "arm64",
    "compiled_mode": "0500",
    "installed_owner_uid": 0,
    "installed_group_gid": 0,
    "installed_mode": "0500",
    "argument_count": 0
  },
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "evaluator_job_state": "absent",
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "virtual_executor_mode": "read_only_freeze",
    "governance_session_runtime_operations": 0
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "base_commit_tree_verified",
    "activation_chain_validated",
    "activation_checkpoint_transcription_corrected_without_history_rewrite",
    "failed_web_target_preserved_failed",
    "release_root_exact_path_verified",
    "release_root_exact_device_inode_verified",
    "before_uid_gid_mode_verified",
    "before_acl_xattr_verified",
    "official_f464_target_absent",
    "official_f464_staging_absent",
    "official_f464_installer_helper_absent",
    "web_d85_plist_write_zero_verified",
    "evaluator_absent_verified",
    "virtual_executor_read_only_freeze_verified",
    "helper_source_sha256_verified",
    "helper_binary_sha256_verified",
    "helper_cdhash_verified",
    "helper_adhoc_signature_verified",
    "helper_arm64_verified",
    "helper_mode_0500_verified",
    "helper_root_only_verified",
    "helper_zero_argument_verified",
    "helper_fixed_path_verified",
    "helper_parent_dirfd_openat_nofollow_verified",
    "helper_exact_device_inode_verified",
    "helper_fchown_uid_only_verified",
    "helper_postcondition_metadata_verified",
    "helper_postcondition_acl_xattr_verified",
    "later_execution_requires_exact_attestation",
    "later_execution_requires_unexpired_remediation_lease",
    "later_execution_nonzero_is_final",
    "later_execution_second_call_is_forbidden",
    "append_only_governance_evidence_defined"
  ],
  "required_false_fields": [
    "governance_session_helper_install_requested",
    "governance_session_helper_invocation_requested",
    "f464_installer_helper_install_requested",
    "f464_installer_helper_invocation_requested",
    "release_install_requested",
    "release_root_symlink_detected",
    "recursive_chown_requested",
    "chmod_requested",
    "group_change_requested",
    "path_argument_requested",
    "shell_requested",
    "delete_requested",
    "overwrite_requested",
    "service_requested",
    "plist_requested",
    "database_connection_requested",
    "database_write_requested",
    "runner_requested",
    "canary_requested",
    "n1_n5_requested",
    "proposal_requested",
    "order_requested",
    "trade_requested",
    "position_requested",
    "cash_requested",
    "web_mutation_requested",
    "evaluator_requested",
    "virtual_executor_mutation_requested",
    "retry_requested",
    "second_call_requested",
    "authority_expansion_requested",
    "concurrent_governance_overwrite_requested"
  ],
  "required_singleton_counts": {
    "release_root_count": 1,
    "owner_uid_change_count": 1,
    "fchown_call_count": 1,
    "governance_modified_file_count": 3,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "later_execution_max_helper_install_count": 1,
    "later_execution_max_helper_invocation_count": 1,
    "retry_count": 0
  },
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_release_root_owner_remediation_v1.c",
    "tests/test_n6_f464_release_root_owner_remediation_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_validate_frozen_anchors",
    "compile_exact_helper_in_isolated_artifact_directory",
    "adhoc_codesign_exact_helper",
    "write_exact_helper_attestation",
    "run_static_tests_without_helper_invocation",
    "append_governance_evidence_to_existing_activation_hash_chain",
    "issue_same_web_target_remediation_only_checkpoint_lease"
  ],
  "allowed_later_execution_operations": [
    "validate_exact_activation_tail_and_unexpired_remediation_lease",
    "install_exact_attested_remediation_helper_once",
    "invoke_exact_attested_remediation_helper_once_with_zero_arguments_as_root",
    "stop_without_retry_on_any_nonzero",
    "verify_exact_release_root_postcondition"
  ],
  "forbidden_helper_functions": [
    "system",
    "popen",
    "posix_spawn",
    "execve",
    "execl",
    "execvp",
    "chmod",
    "fchmod",
    "chown",
    "lchown",
    "unlink",
    "unlinkat",
    "remove",
    "rmdir",
    "rename",
    "renameat",
    "renameatx_np"
  ],
  "remediation_mutation_primitive": "fchown(exact_open_dirfd,uid_0,gid_minus_1)",
  "remediation_checkpoint_contract": {
    "stage": "F464_RELEASE_ROOT_OWNER_REMEDIATION",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "failed_web_target_status": "failed",
    "permissions": [
      "install exact attested release-root-owner remediation helper once",
      "invoke exact helper once with zero arguments as root",
      "change exact release-root uid from 501 to 0 only"
    ],
    "forbids_f464_install_in_same_stage": true,
    "forbids_web_rebind_in_same_stage": true,
    "forbids_retry": true,
    "expires_after_seconds": 3600
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_execute_remediation": true,
  "governance_session_cannot_install_f464_release": true,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "web_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "virtual_executor_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_release_root_owner_remediation_v1:end -->

## F464 user-owned immutable Release installer governance supersession

This `runtime_control` governance contract corrects the historical root-owner
assumption without rewriting either failed attempt. User ownership
`uid=501,gid=20,mode=0555` is the canonical N6 B-track Release mode. The
historical privileged installer and the root-owner remediation are
`superseded_noncanonical`: neither may ever be installed, invoked, retried, or
used to request privilege elevation. The one-time parent approval remains
accepted and does not require reconfirmation.

This governance session may only update the three frozen repository files,
compile/ad-hoc-sign/attest the helper outside the Release root, and append
governance/checkpoint/lease evidence to the existing activation hash chain. It
must not invoke the helper, install a Release, operate a service, change a
plist, connect to a database, run the Evaluator or Virtual Executor, or touch
N1-N5/business/trading state.

<!-- policy:n6_f464_user_owned_immutable_release_install_v1:begin -->
```json
{
  "policy_id": "n6_f464_user_owned_immutable_release_install_v1",
  "canonical_status": "active_canonical",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "phase_mode": "governance_helper_test_attestation_only",
  "scope_mode": "single_exact_f464_user_owned_immutable_release_install",
  "governance_ancestry": [
    {
      "policy_id": "n6_immutable_release_privileged_materialize_and_install_f464_v1",
      "commit": "90ff911f5692c50f373f5a11a9a2804d9a9e828c",
      "tree": "9a5717d945cd3b0f8f1720d7f942498aa5fcf1e0",
      "status": "superseded_noncanonical",
      "future_execution_allowed": false,
      "future_retry_allowed": false
    },
    {
      "policy_id": "n6_f464_release_root_owner_remediation_v1",
      "commit": "a29b064555027cd4bba7c4a833515b7adbbdd900",
      "tree": "d55ad7c15502f97a4ae3668fe576d7e6ff76ee3c",
      "status": "superseded_noncanonical",
      "future_execution_allowed": false,
      "future_retry_allowed": false
    }
  ],
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "b13d8194b8a14807337ecf4b8e6f1cb6e3185d528c4a5d4579023b3efe47a036",
  "activation_state_before_event_count": 39,
  "activation_state_before_tail_event_sha256": "e43c6c81d1b8308bb194a86acb342d120b715d08dea48e81ca4bdf8c1ddf7d47",
  "historical_failed_events_preserved": true,
  "historical_failed_web_target_status": "failed",
  "historical_stage3d_helper_install_count": 0,
  "historical_stage3d_helper_invocation_count": 0,
  "historical_stage3f_remediation_helper_install_success_count": 0,
  "historical_stage3f_remediation_helper_invocation_count": 0,
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_root_exact": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "candidate_root": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "frozen_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar",
  "frozen_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.git-ls-tree.nul",
  "frozen_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release-attestation.json",
  "frozen_bundle_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release/config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
  "target_release_name": "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "staging_release_name": ".staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "staging_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "historical_privileged_helper_target": "/usr/local/libexec/ashare-v3/n6-f464-immutable-release-materializer-v2",
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "helper_filename_retained_for_lineage_only": true,
  "helper_privileged_semantics": false,
  "compiled_helper_artifact_path": "/Users/chuanfuchen/.codex/artifacts/n6_f464_user_owned_installer_governance_v1/20260726_040051__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/n6-f464-user-owned-immutable-release-installer-v1",
  "helper_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_f464_user_owned_installer_governance_v1/20260726_040051__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/f464-user-owned-installer-helper-attestation.json",
  "required_exact_values": {
    "release_commit": "f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "release_tree": "c654cbc03c0341c9b3490a02a432b136984c43ce",
    "implementation_commit": "5c2c38d184385a317afe69b6397f7d98393ff24f",
    "implementation_tree": "0a02ac53513946ca530d3420b2bd06c60630388e",
    "archive_sha256": "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
    "manifest_sha256": "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
    "filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "release_attestation_sha256": "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0",
    "helper_source_sha256": "293b7fbd83b57fd7e7b815dd2d5ff351d3989575b11c904ccac13a9acbc0a007",
    "helper_binary_sha256": "3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88",
    "helper_codesign_cdhash": "0e7eb005917039a5c0310a2a18eb588920321cea",
    "helper_architecture": "arm64",
    "helper_signature": "adhoc",
    "helper_compiled_mode": "0500",
    "helper_execution_uid": 501,
    "helper_execution_gid": 20,
    "helper_argument_count": 0,
    "root_mode_before": "0555",
    "root_mode_during": "0755",
    "root_mode_after": "0555",
    "target_root_mode": "0555",
    "target_regular_file_mode": "0444",
    "target_executable_file_mode": "0555"
  },
  "required_singleton_counts": {
    "candidate_count": 1,
    "archive_count": 1,
    "manifest_count": 1,
    "release_attestation_count": 1,
    "bundle_count": 1,
    "target_release_count": 1,
    "new_staging_release_count": 1,
    "archive_expected_file_count": 6240,
    "archive_expected_directory_count": 45,
    "root_owner_write_window_count": 1,
    "root_mode_0555_to_0755_count": 1,
    "root_mode_0755_to_0555_count": 1,
    "exclusive_rename_count": 1,
    "governance_modified_file_count": 3,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "later_execution_helper_install_count": 0,
    "later_execution_max_helper_invocation_count": 1,
    "retry_count": 0
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "governance_ancestry_verified",
    "historical_failure_events_preserved_without_rewrite",
    "historical_policies_superseded_noncanonical",
    "future_uid_501_to_0_forbidden",
    "release_root_exact_device_inode_verified",
    "release_root_uid_gid_mode_verified",
    "release_root_acl_xattr_verified",
    "official_target_absent",
    "official_staging_absent",
    "historical_privileged_helper_target_absent",
    "candidate_commit_tree_archive_manifest_attestation_verified",
    "candidate_filesystem_bundle_verified",
    "helper_source_binary_cdhash_attested",
    "helper_current_user_only",
    "helper_zero_argument_only",
    "helper_fixed_paths_only",
    "helper_dirfd_nofollow_beneath_exclusive",
    "root_owner_write_window_once",
    "root_finally_restored_0555",
    "group_other_never_writable",
    "staging_target_uid_gid_verified",
    "all_release_entries_nonwritable_verified",
    "target_modes_match_manifest",
    "existing_releases_preserved",
    "existing_orphan_staging_preserved",
    "failure_preserves_unique_new_staging",
    "second_call_fails_closed_on_target_exists",
    "retry_forbidden",
    "web_d85_plist_write_zero_preserved",
    "evaluator_absent_preserved",
    "virtual_executor_unchanged",
    "append_only_supersession_registration_defined",
    "new_install_checkpoint_and_lease_defined"
  ],
  "required_false_fields": [
    "governance_helper_install_requested",
    "governance_helper_invocation_requested",
    "release_install_requested_in_governance",
    "sudo_requested",
    "administrator_password_requested",
    "authorization_services_requested",
    "osascript_requested",
    "root_helper_requested",
    "uid_zero_requested",
    "fchown_uid_zero_requested",
    "release_root_symlink_detected",
    "target_exists_before_install",
    "staging_exists_before_install",
    "path_argument_requested",
    "shell_requested",
    "overwrite_requested",
    "delete_existing_release_requested",
    "delete_existing_staging_requested",
    "touch_existing_root_owned_orphan_staging_requested",
    "group_write_requested",
    "other_write_requested",
    "retry_requested",
    "second_call_requested",
    "launch_agent_touched",
    "plist_touched",
    "service_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "outbox_inbox_checkpoint_business_mutation_requested",
    "n1_n5_business_mutation_requested",
    "evaluator_requested",
    "virtual_executor_mutation_requested",
    "proposal_requested",
    "order_requested",
    "trade_requested",
    "position_requested",
    "lot_requested",
    "cash_requested"
  ],
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_verify_frozen_candidate_activation_and_live_anchors",
    "compile_helper_in_temporary_directory",
    "adhoc_codesign_helper_in_temporary_directory",
    "write_external_helper_attestation_after_governance_commit",
    "run_static_and_fixture_tests_without_helper_invocation",
    "append_supersession_governance_evidence_to_existing_activation_hash_chain",
    "issue_new_same_target_install_checkpoint_lease"
  ],
  "allowed_later_execution_operations": [
    "validate_exact_activation_tail_and_unexpired_install_lease",
    "invoke_exact_attested_user_owned_helper_once_with_zero_arguments_as_uid_501_gid_20",
    "stop_without_retry_on_any_nonzero",
    "verify_exact_immutable_f464_target",
    "rebind_exact_web_d85_to_exact_f464_only_after_install_success_with_strategy_write_zero",
    "keep_evaluator_absent_and_virtual_executor_unchanged"
  ],
  "failure_staging_policy": "preserve_exact_unique_new_staging_no_delete_no_retry",
  "forbidden_helper_functions": [
    "system",
    "popen",
    "posix_spawn",
    "execve",
    "execl",
    "execvp",
    "fchown",
    "chown",
    "lchown",
    "unlink",
    "unlinkat",
    "remove",
    "rmdir",
    "rename",
    "renameat"
  ],
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "evaluator_job_state": "absent",
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "virtual_executor_mode": "read_only_freeze",
    "governance_session_runtime_operations": 0,
    "business_side_effect_count": 0
  },
  "new_install_checkpoint_contract": {
    "stage": "F464_USER_OWNED_IMMUTABLE_INSTALL",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "historical_failed_web_target_status": "failed",
    "lease_scope": "same_target_exact_f464_install_then_exact_web_rebind",
    "expires_after_seconds": 3600,
    "forbids_privilege_elevation": true,
    "forbids_helper_install": true,
    "forbids_retry": true,
    "forbids_second_call": true,
    "requires_append_only_chain_tail_match": true
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "governance_session_cannot_operate_service": true,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "virtual_executor_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_user_owned_immutable_release_install_v1:end -->

## F464 no-extended-ACL ENOENT fix and one-shot recovery governance

The exact Stage 3H call is preserved as a failed historical event. It invoked
the old attested binary exactly once and returned
`67 / EXIT_ROOT_PREFLIGHT` before the Release-root owner-write window,
staging creation, target creation, or any Web operation. The root remained the
same `uid=501,gid=20,mode=0555` directory, the exact target and staging paths
remained absent, Web remained on `d85`, Evaluator remained absent, Virtual
Executor remained unchanged, and all business side-effect counts remained
zero.

The diagnosis is limited to one macOS API semantic: for
`acl_get_fd_np(fd, ACL_TYPE_EXTENDED)`, `NULL` with `errno=ENOENT` means that
the descriptor has no extended ACL. The old helper treated every `NULL` as a
preflight failure. The fixed helper clears `errno` before the call, accepts
only `NULL+ENOENT`, rejects every other `NULL` errno, and retains the existing
non-`NULL` requirement that `acl_to_text` return an empty ACL text.

This governance stage may only change the exact three repository files below
and compile, ad-hoc codesign, and attest the new binary in the exact temporary
directory. It must not install or invoke either helper, materialize the
Release, operate Web, connect to the database, run Evaluator or Virtual
Executor, or touch N1-N5/business/trading state. The old binary SHA
`3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88`
is permanently replay-forbidden. Root-owner remediation, privileged helper,
sudo, and authorization-service routes remain superseded.

<!-- policy:n6_f464_no_extended_acl_enoent_fix_recovery_v1:begin -->
```json
{
  "policy_id": "n6_f464_no_extended_acl_enoent_fix_recovery_v1",
  "canonical_status": "active_canonical_recovery",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "phase_mode": "governance_helper_test_temporary_attestation_only",
  "scope_mode": "single_exact_f464_enoent_acl_fix_and_one_shot_recovery",
  "base_governance_commit": "d281744840d404830d06fbaef7088524ed98885d",
  "base_governance_tree": "c4d482f0422b583d47b68e73f684e514f5528e79",
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "11e08be0e7d564a64a89b8d7593edb350136a5b1414cbde33ecf725b33ae6ef7",
  "activation_state_before_event_count": 44,
  "activation_state_before_tail_event_sha256": "4bd227a401b5b20860db043f5d4f59c8db0b8f9847beb7f7affa6ebe65b6411b",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_root_exact": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "staging_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "temporary_compiled_helper_path": "/private/tmp/n6_f464_enoent_fix.B8UQp3/n6-f464-user-owned-immutable-release-installer-enoent-fix-v1",
  "temporary_helper_attestation_path": "/private/tmp/n6_f464_enoent_fix.B8UQp3/f464-enoent-fix-helper-attestation.json",
  "old_binary": {
    "sha256": "3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88",
    "codesign_cdhash": "0e7eb005917039a5c0310a2a18eb588920321cea",
    "future_invocation_allowed": false,
    "future_replay_allowed": false,
    "future_retry_allowed": false
  },
  "new_binary": {
    "source_sha256": "b7531513a8daecad416fe7eb241604356439f5e7a20452ed0654b6c9f875cd90",
    "binary_sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d",
    "codesign_cdhash": "a2907f17e6d5c4b33751005804258298e4163a21",
    "signature": "adhoc",
    "architecture": "arm64",
    "mode": "0500",
    "uid": 501,
    "gid": 20,
    "argument_count": 0,
    "installed": false,
    "invoked": false
  },
  "acl_semantic_fix": {
    "call": "acl_get_fd_np(fd,ACL_TYPE_EXTENDED)",
    "errno_cleared_before_call": true,
    "null_with_enoent_means_no_extended_acl": true,
    "null_with_any_other_errno_means_preflight_failure": true,
    "non_null_acl_requires_acl_to_text_length_zero": true,
    "all_other_helper_install_semantics_unchanged": true
  },
  "stage3h_failure_contract": {
    "prior_helper_invocation_count": 1,
    "prior_helper_exit_code": 67,
    "prior_helper_exit_name": "EXIT_ROOT_PREFLIGHT",
    "failure_phase": "pre_mutation",
    "root_owner_write_window_open_count": 0,
    "root_mode_change_count": 0,
    "staging_create_count": 0,
    "target_create_count": 0,
    "web_operation_count": 0,
    "business_side_effect_count": 0,
    "root_metadata_unchanged": true,
    "root_xattr_fingerprint_unchanged": true,
    "target_absent_after": true,
    "staging_absent_after": true,
    "web_d85_unchanged": true,
    "evaluator_absent_unchanged": true,
    "virtual_executor_unchanged": true
  },
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "evaluator_job_state": "absent",
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "governance_session_runtime_operations": 0,
    "business_side_effect_count": 0
  },
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_verify_stage3h_failure_activation_and_live_anchors",
    "change_only_no_extended_acl_enoent_semantics",
    "compile_helper_in_exact_temporary_directory",
    "adhoc_codesign_helper_in_exact_temporary_directory",
    "write_temporary_helper_attestation_without_invocation",
    "run_static_fixture_and_runtime_control_n6_regressions",
    "append_diagnostic_recovery_checkpoint_and_lease_to_existing_activation_hash_chain"
  ],
  "forbidden_governance_operations": [
    "invoke_old_helper",
    "invoke_new_helper",
    "install_helper",
    "install_release",
    "open_release_root_owner_write_window",
    "create_staging_or_target",
    "operate_web_or_plist",
    "connect_or_write_database",
    "run_evaluator_or_virtual_executor",
    "touch_n1_n5_business_or_trading_state"
  ],
  "recovery_checkpoint_contract": {
    "stage": "F464_ENOENT_RECOVERY_INSTALL_AND_WEB_REBIND",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "recovery_attempt_ordinal": 1,
    "required_prior_helper_invocation_count": 1,
    "required_prior_helper_exit_code": 67,
    "required_prior_failure_phase": "pre_mutation",
    "required_old_binary_replay_forbidden": true,
    "required_new_binary_sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d",
    "required_new_binary_cdhash": "a2907f17e6d5c4b33751005804258298e4163a21",
    "new_binary_max_invocation_count": 1,
    "allowed_success_exit_code": 0,
    "any_other_exit_decision": "REJECT_NO_RETRY_NO_WEB",
    "any_side_effect_drift_decision": "REJECT_NO_RECOVERY",
    "second_recovery_decision": "REJECT",
    "requires_append_only_chain_tail_match": true,
    "forbids_helper_install": true,
    "forbids_privilege_elevation": true,
    "forbids_root_owner_remediation": true,
    "forbids_retry": true,
    "expires_after_seconds": 3600
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "base_commit_tree_verified",
    "activation_chain_44_events_validated",
    "stage3h_exactly_one_call_verified",
    "stage3h_exit_67_pre_mutation_verified",
    "root_mode_never_opened_verified",
    "target_staging_absent_verified",
    "web_not_operated_verified",
    "all_frozen_hashes_unchanged_verified",
    "business_side_effect_zero_verified",
    "acl_enoent_probe_verified",
    "only_no_extended_acl_semantics_changed",
    "old_binary_replay_forbidden_verified",
    "new_binary_source_sha_binary_sha_cdhash_verified",
    "new_binary_not_installed_not_invoked",
    "append_only_recovery_checkpoint_and_lease_defined"
  ],
  "required_false_fields": [
    "governance_helper_install_requested",
    "governance_helper_invocation_requested",
    "release_install_requested",
    "web_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "retry_requested",
    "second_recovery_requested",
    "old_binary_replay_requested",
    "root_owner_remediation_requested",
    "sudo_requested",
    "authority_expansion_requested"
  ],
  "required_singleton_counts": {
    "governance_modified_file_count": 3,
    "prior_helper_invocation_count": 1,
    "prior_helper_exit_code": 67,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "new_recovery_max_helper_invocation_count": 1,
    "new_recovery_max_count": 1,
    "retry_count": 0
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "web_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "virtual_executor_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_no_extended_acl_enoent_fix_recovery_v1:end -->

## F464 inherited-provenance staging recovery governance

Stage 3J remains an immutable failed historical execution. Its exact attested
binary was invoked once and returned `71 / EXIT_STAGING_CREATE` after the
single `mkdirat` created the historical staging directory but before Release
materialization. The directory inherited the only allowed extended attribute,
`com.apple.provenance`, from the Release root. The old helper then rejected the
directory because its staging and Release-entry gate incorrectly required zero
extended attributes.

This recovery changes that gate only: every staging or Release entry must have
exactly one `com.apple.provenance` attribute with the frozen fingerprint below.
Missing, extra, or different extended attributes fail closed. The helper has
no `setxattr` or `removexattr` path. The historical empty staging directory is
opened and verified before the owner-write window and verified again after the
window; it is never deleted, overwritten, renamed, populated, or reused. A
different exact recovery staging name is required.

This is an artifact-only `runtime_control` governance stage. It may compile,
ad-hoc sign, and attest the new helper in the named temporary directory, but it
must not install or invoke any helper, install the Release, operate Web or any
LaunchAgent, connect to the database, run Evaluator or Virtual Executor, run a
runner/canary/DeepSeek, or touch N1-N5/business/trading state. The one-time
recovery authority is available only to a later independent
`runtime_control` session with the exact append-only checkpoint and active
lease created after the final governance commit.

<!-- policy:n6_f464_inherited_provenance_staging_recovery_governance_v1:begin -->
```json
{
  "policy_id": "n6_f464_inherited_provenance_staging_recovery_governance_v1",
  "canonical_status": "active_canonical_recovery",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "phase_mode": "governance_helper_test_temporary_attestation_only",
  "scope_mode": "single_exact_f464_inherited_provenance_staging_recovery",
  "base_governance_commit": "ea6c2c372bd25ab42bf841b05b1f3f65a21dfbbb",
  "base_governance_tree": "34dbe5bd27fc60f802078e705cb66d34b51ea8dd",
  "governance_commit_binding": "external_post_commit_activation_event",
  "main_checkout_mode": "preserve_only",
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "adbe809a81693402b2a57eaa535a02f10faf5072fa711c28c040f7b881a7ff75",
  "activation_state_before_event_count": 49,
  "activation_state_before_tail_event_sha256": "63a6f18b95fdad5aa920e81b0e1f1f5896a82893901a55a4f599b9f328fd17c4",
  "activation_state_chain_valid": true,
  "stage3j_failure_evidence_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/f464-enoent-recovery-install-execute-failed.json",
  "stage3j_failure_evidence_sha256": "73cef474ea0589286c3e8f8ddddcaa08415292da8fd94a102c957d1385c9f67f",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_root_exact": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "historical_staging_exact": {
    "name": ".staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320375768,
    "uid": 501,
    "gid": 20,
    "mode": "0700",
    "entry_count": 0,
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea",
    "must_match_preflight_and_postflight": true,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "population_allowed": false
  },
  "target_release_name": "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_must_be_absent_before": true,
  "new_staging_name": ".staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_must_be_absent_before": true,
  "new_staging_relation": "unique_same_parent_not_historical_staging",
  "candidate_root": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "frozen_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar",
  "frozen_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.git-ls-tree.nul",
  "frozen_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release-attestation.json",
  "frozen_bundle_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release/config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
  "frozen_artifact_hashes": {
    "archive_sha256": "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
    "manifest_sha256": "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
    "filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "release_attestation_sha256": "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0"
  },
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "temporary_compiled_helper_path": "/private/tmp/n6_f464_provenance_recovery2.tbM4OG/n6-f464-user-owned-immutable-release-installer-provenance-recovery2-v1",
  "temporary_helper_attestation_path": "/private/tmp/n6_f464_provenance_recovery2.tbM4OG/f464-provenance-recovery2-helper-attestation.json",
  "old_stage3j_binary": {
    "sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d",
    "codesign_cdhash": "a2907f17e6d5c4b33751005804258298e4163a21",
    "prior_invocation_count": 1,
    "prior_exit_code": 71,
    "prior_exit_name": "EXIT_STAGING_CREATE",
    "prior_failure_phase": "post_staging_create_pre_materialize",
    "future_invocation_allowed": false,
    "future_replay_allowed": false,
    "future_retry_allowed": false
  },
  "new_binary": {
    "source_sha256": "bfe016ee93a57e15a9288bd00fa68868e2e8ab1b168b4b8270a24b9dc5d784e2",
    "binary_sha256": "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0",
    "codesign_cdhash": "2d0695005d62a1c86b2142c0330089fc558d4a2e",
    "signature": "adhoc",
    "architecture": "arm64",
    "mode": "0500",
    "uid": 501,
    "gid": 20,
    "argument_count": 0,
    "installed": false,
    "invoked": false,
    "max_future_invocation_count": 1
  },
  "provenance_gate": {
    "required_xattr_names": ["com.apple.provenance"],
    "required_raw_hex": "0100006457BBC065B81880",
    "required_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea",
    "applies_to": ["new_staging_work_directory", "materialized_regular_file", "materialized_directory", "sealed_staging_directory", "promoted_target_directory"],
    "missing_decision": "REJECT",
    "extra_decision": "REJECT",
    "different_decision": "REJECT",
    "setxattr_allowed": false,
    "removexattr_allowed": false,
    "inherited_value_must_match_release_root_and_healthy_release_entry": true
  },
  "stage3j_recovery_binding": {
    "required_prior_binary_sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d",
    "required_prior_invocation_count": 1,
    "required_prior_exit_code": 71,
    "required_prior_exit_name": "EXIT_STAGING_CREATE",
    "required_prior_failure_phase": "post_staging_create_pre_materialize",
    "required_prior_old_staging_preserved": true,
    "required_prior_target_absent": true,
    "any_prior_exit_other_than_71_decision": "REJECT",
    "second_recovery_decision": "REJECT",
    "old_binary_replay_decision": "REJECT"
  },
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "web_route_status": [302, 401, 302],
    "evaluator_job_state": "absent",
    "evaluator_runner_count": 0,
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "governance_session_runtime_operations": 0,
    "business_side_effect_count": 0
  },
  "unchanged_install_contract": {
    "candidate_archive_manifest_filesystem_bundle": true,
    "root_mode_window": "single_0555_to_0755_to_0555",
    "rename_flags": ["RENAME_EXCL", "RENAME_NOFOLLOW_ANY", "RENAME_RESOLVE_BENEATH"],
    "target_name_and_path": true,
    "web_rebind_contract": true,
    "helper_install_allowed": false,
    "privilege_elevation_allowed": false
  },
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_verify_stage3j_exit71_failure_activation_and_live_anchors",
    "change_staging_and_release_entry_no_xattrs_gate_to_exact_inherited_provenance",
    "bind_unique_recovery2_staging_and_preserve_historical_staging_pre_postflight",
    "compile_helper_in_exact_temporary_directory",
    "adhoc_codesign_helper_in_exact_temporary_directory",
    "write_temporary_helper_attestation_without_invocation",
    "run_static_fixture_and_runtime_control_n6_regressions",
    "append_diagnostic_recovery_checkpoint_and_lease_to_existing_activation_hash_chain"
  ],
  "forbidden_governance_operations": [
    "invoke_old_helper",
    "invoke_new_helper",
    "install_helper",
    "install_release",
    "create_or_modify_release_staging_or_target",
    "operate_web_or_launchagent",
    "connect_or_write_database",
    "run_evaluator_or_virtual_executor",
    "run_runner_canary_or_deepseek",
    "touch_n1_n5_business_or_trading_state"
  ],
  "recovery_checkpoint_contract": {
    "stage": "F464_INHERITED_PROVENANCE_RECOVERY_INSTALL_AND_WEB_REBIND",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "recovery_attempt_ordinal_for_exit71": 1,
    "required_prior_helper_invocation_count": 1,
    "required_prior_helper_exit_code": 71,
    "required_prior_failure_phase": "post_staging_create_pre_materialize",
    "required_old_binary_replay_forbidden": true,
    "required_new_binary_sha256": "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0",
    "required_new_binary_cdhash": "2d0695005d62a1c86b2142c0330089fc558d4a2e",
    "new_binary_max_invocation_count": 1,
    "allowed_success_exit_code": 0,
    "any_nonzero_exit_decision": "REJECT_NO_RETRY_NO_WEB",
    "any_side_effect_drift_decision": "REJECT_NO_RECOVERY",
    "second_recovery_decision": "REJECT",
    "requires_append_only_chain_tail_match": true,
    "forbids_helper_install": true,
    "forbids_privilege_elevation": true,
    "forbids_root_owner_remediation": true,
    "forbids_retry": true,
    "expires_after_seconds": 3600
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "base_commit_tree_verified",
    "activation_chain_49_events_validated",
    "stage3j_exactly_one_call_verified",
    "stage3j_exit71_post_staging_create_pre_materialize_verified",
    "historical_staging_exact_preflight_verified",
    "historical_staging_exact_postflight_defined",
    "historical_staging_never_delete_overwrite_reuse_verified",
    "new_staging_unique_and_absent_verified",
    "target_absent_verified",
    "release_root_restored_0555_verified",
    "web_not_operated_verified",
    "all_frozen_hashes_unchanged_verified",
    "business_side_effect_zero_verified",
    "enoent_acl_fix_retained",
    "exact_provenance_happy_path_verified",
    "missing_extra_different_provenance_fail_closed_verified",
    "setxattr_removexattr_absent_verified",
    "old_binary_replay_forbidden_verified",
    "new_binary_source_sha_binary_sha_cdhash_verified",
    "new_binary_not_installed_not_invoked",
    "append_only_diagnostic_checkpoint_and_lease_defined"
  ],
  "required_false_fields": [
    "governance_helper_install_requested",
    "governance_helper_invocation_requested",
    "release_install_requested",
    "release_staging_or_target_mutation_requested",
    "historical_staging_delete_overwrite_reuse_requested",
    "web_or_launchagent_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "runner_canary_deepseek_requested",
    "second_recovery_requested",
    "old_binary_replay_requested",
    "setxattr_requested",
    "removexattr_requested",
    "root_owner_remediation_requested",
    "sudo_requested",
    "authority_expansion_requested"
  ],
  "required_singleton_counts": {
    "governance_modified_file_count": 3,
    "stage3j_helper_invocation_count": 1,
    "stage3j_helper_exit_code": 71,
    "historical_staging_count": 1,
    "new_staging_name_count": 1,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "new_recovery_max_helper_invocation_count": 1,
    "new_recovery_max_count": 1,
    "retry_count": 0
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "web_or_launchagent_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "virtual_executor_operations_allowed": false,
  "runner_canary_deepseek_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_inherited_provenance_staging_recovery_governance_v1:end -->

## F464 full-width USTAR name recovery governance

Stage 3L is an immutable failed execution. Its exact recovery2 binary consumed
the only Stage 3L lease, was invoked exactly once, and returned
`72 / EXIT_MATERIALIZE`. The helper stopped at archive physical header 585,
which is manifest file index 573, before creating that file. The first 572
manifest files and their eight parent directories remain in the unique
recovery2 staging directory as a legal partial-materialization state. The
historical empty staging and the recovery2 staging are both immutable failure
evidence and must match exact read-only preflight and postflight checks.

The root cause is limited to `tar_path()`: a legal USTAR `name[100]` field may
use all 100 bytes without a trailing NUL. The old helper rejected that exact
case. This recovery removes only that rejection while retaining the full-width
bounded `snprintf`, prefix termination check, safe relative-path check, frozen
PAX behavior, checksum/type/mode/owner/provenance/ACL/blob/manifest gates,
root window, promotion flags, and candidate/archive/target/Web contracts. It
does not add GNU longname or new PAX support and does not permit a raw USTAR
name component longer than 100 bytes.

This is an artifact-only `runtime_control` governance stage. It may compile,
ad-hoc codesign, and attest the new helper in the exact temporary directory,
but it must not install or invoke any helper, install the Release, create or
modify any Release staging or target, operate Web/Evaluator/Virtual Executor
or any LaunchAgent, connect to the database, run a runner/canary/DeepSeek, or
touch N1-N5/business/trading state. The recovery3 authority is available only
to a later independent `runtime_control` session with the exact append-only
checkpoint and active single-use lease created after the final governance
commit.

<!-- policy:n6_f464_full_width_ustar_name_recovery_governance_v1:begin -->
```json
{
  "policy_id": "n6_f464_full_width_ustar_name_recovery_governance_v1",
  "canonical_status": "active_canonical_recovery",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "gate": "F464_FULL_WIDTH_USTAR_NAME_RECOVERY_GOVERNANCE",
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "phase_mode": "governance_helper_test_temporary_attestation_only",
  "scope_mode": "single_exact_f464_full_width_ustar_name_recovery3",
  "base_governance_commit": "47b9d2d959010e7c99ccca1ec713e6797d630ec7",
  "base_governance_tree": "13f063924b72dbc153aec4df55e03e51276fc40d",
  "governance_commit_binding": "external_post_commit_activation_event",
  "main_checkout_mode": "preserve_only",
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "fe0099e86001cca164d2df5c59d0e6f8435a1c4f4034114c65594ff43b0bcd1f",
  "activation_state_before_event_count": 55,
  "activation_state_before_tail_event_sha256": "b9ad5cc5d7395ce56a3e2ba1e2cb3eaaafd4fc2654e5e48c1d5c1c63740b6d5e",
  "activation_state_chain_valid": true,
  "stage3l_failure_contract": {
    "prior_policy_id": "n6_f464_inherited_provenance_staging_recovery_governance_v1",
    "prior_helper_binary_sha256": "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0",
    "prior_helper_codesign_cdhash": "2d0695005d62a1c86b2142c0330089fc558d4a2e",
    "prior_helper_invocation_count": 1,
    "prior_helper_exit_code": 72,
    "prior_helper_exit_name": "EXIT_MATERIALIZE",
    "prior_lease_consumed": true,
    "prior_retry_allowed": false,
    "failure_phase": "archive_physical_header_585_before_manifest_file_573_create",
    "failure_archive_physical_header_index": 585,
    "failure_manifest_file_index": 573,
    "materialized_manifest_file_count": 572,
    "materialized_directory_count": 8,
    "failed_path": "docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PARTIAL_WRITE_ROLLBACK_EXECUTE_REPORT.md",
    "failed_path_utf8_length_bytes": 100,
    "failed_ustar_name_field_length_bytes": 100,
    "failed_ustar_name_has_nul": false,
    "failed_ustar_prefix_length_bytes": 0,
    "failed_path_has_pax_override": false,
    "failed_file_created": false,
    "official_target_absent_after": true,
    "web_operation_count": 0,
    "business_trading_side_effect_count": 0
  },
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_root_exact": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "historical_staging_exact": {
    "name": ".staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320375768,
    "uid": 501,
    "gid": 20,
    "mode": "0700",
    "entry_count": 0,
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea",
    "must_match_preflight_and_postflight": true,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "population_allowed": false
  },
  "failed_recovery2_staging_exact": {
    "name": ".staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320422668,
    "uid": 501,
    "gid": 20,
    "mode": "0700",
    "staging_root_not_finally_sealed_0555": true,
    "file_count": 572,
    "directory_count": 8,
    "symlink_count": 0,
    "child_entry_count": 580,
    "owner_counts": {"501:20": 580},
    "child_mode_counts": {"directory:0755": 8, "file:0444": 572},
    "extended_acl_entry_count_root_and_children": 0,
    "provenance_entry_count_root_and_children": 581,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea",
    "ordered_paths_nul_sha256": "4c5102d0001d4721372243f0d3ab523df9ab44149cf109aaeef98b7c01c97a69",
    "entry_records_sha256": "0d7c85da4be58289d4e08cb44daf6471dc9444bb81d83f989084a04e50809db7",
    "recursive_xattr_listing_sha256": "e6ce294335e824e708da9fed66ec3b4a77c5b354627e7d1545c35d799aa5791a",
    "first_572_manifest_records_sha256": "d52e098e975c0772f6a8a7b4e6fd95628511f0b13a1dcb5ab658f95e7a58dbe5",
    "first_572_materialized_verification_sha256": "a8f725b39552497fe2480de6210464b04d55766b2c43455653a3981373442d6b",
    "first_materialized_path": ".codex/config.toml",
    "last_materialized_path": "docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PARTIAL_RUN_CLEANUP_POST_REVIEW_REGISTRATION.md",
    "must_match_preflight_and_postflight": true,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "population_allowed": false,
    "seal_or_mode_change_allowed": false
  },
  "target_release_name": "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_must_be_absent_before": true,
  "new_staging_name": ".staging_recovery3__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery3__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_must_be_absent_before": true,
  "new_staging_relation": "unique_same_parent_not_historical_or_recovery2_staging",
  "candidate_root": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "frozen_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar",
  "frozen_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.git-ls-tree.nul",
  "frozen_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release-attestation.json",
  "frozen_bundle_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release/config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
  "frozen_artifact_hashes": {
    "archive_sha256": "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
    "manifest_sha256": "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
    "filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "release_attestation_sha256": "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0"
  },
  "archive_traversal_contract": {
    "manifest_file_count": 6240,
    "archive_directory_count": 45,
    "pax_global_header_count": 1,
    "pax_extended_header_count": 108,
    "full_width_ustar_name_count": 17,
    "full_width_ustar_names_have_no_nul": true,
    "full_width_ustar_entries": [
      {"manifest_index": 573, "physical_header_index": 585, "prefix_length": 0, "path": "docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PARTIAL_WRITE_ROLLBACK_EXECUTE_REPORT.md"},
      {"manifest_index": 584, "physical_header_index": 596, "prefix_length": 0, "path": "docs/N3_20260611_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_EXECUTE_CONTRACT.md"},
      {"manifest_index": 758, "physical_header_index": 791, "prefix_length": 0, "path": "docs/N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_REBUILD_EXECUTE_GATE_POST_REVIEW.md"},
      {"manifest_index": 783, "physical_header_index": 819, "prefix_length": 0, "path": "docs/N3_A0_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREVIOUS_DAY_MINUTE_DRY_RUN.md"},
      {"manifest_index": 2225, "physical_header_index": 2270, "prefix_length": 4, "path": "docs/N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_SCHEDULER_REACTIVATION_AFTER_B2_MIDDAY_POLICY_REPAIR_REPORT.md"},
      {"manifest_index": 2244, "physical_header_index": 2295, "prefix_length": 0, "path": "docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_EXECUTE_REPORT.md"},
      {"manifest_index": 2993, "physical_header_index": 3070, "prefix_length": 4, "path": "docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_TRIGGER_TIME_ALIGNED_METRIC_AWARE_RETRY_EXECUTE_REPORT.md"},
      {"manifest_index": 2994, "physical_header_index": 3071, "prefix_length": 0, "path": "docs/N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_TRIGGER_TIME_ALIGNED_METRIC_AWARE_RETRY_READINESS.md"},
      {"manifest_index": 3344, "physical_header_index": 3434, "prefix_length": 0, "path": "docs/N6_PROJECTION_20260608_UNTIL_1500_FORMAL_SNAPSHOT_FALLBACK_METRIC_AWARE_RETRY_EXECUTE_REPORT.md"},
      {"manifest_index": 3728, "physical_header_index": 3828, "prefix_length": 4, "path": "docs/V3_20260615_N5_REPLAY_AFTER_N4_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_AND_N3_COVERAGE_REPAIR_CONTRACT.md"},
      {"manifest_index": 3778, "physical_header_index": 3883, "prefix_length": 4, "path": "docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_CONTROL_ROW_DRY_RUN.md"},
      {"manifest_index": 3784, "physical_header_index": 3893, "prefix_length": 0, "path": "docs/V3_20260616_N3_HISTORICAL_SOURCE_EXPANSION_FOR_CORRECTED_METRIC_ORDINARY_FULL_EXECUTE_REPORT.md"},
      {"manifest_index": 3806, "physical_header_index": 3917, "prefix_length": 0, "path": "docs/V3_20260616_N4_TRIGGER_REPLAY_AFTER_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_GUARD_REGENERATION_REPORT.md"},
      {"manifest_index": 3865, "physical_header_index": 3976, "prefix_length": 0, "path": "docs/V3_20260617_N4_TRIGGER_CONTEXT_AND_RUN_ONCE_AFTER_REPAIRED_N2_N3_FULL_SCOPE_PASS_POST_REVIEW.md"},
      {"manifest_index": 4603, "physical_header_index": 4736, "prefix_length": 0, "path": "sql/N2_condition_layer_20260714_source_20260714_for_20260715_directional_incremental_v1_rollback.sql"},
      {"manifest_index": 5225, "physical_header_index": 5359, "prefix_length": 3, "path": "sql/N4_20260611_market_snapshot_updated_production_trigger_semantic_replay_runner_generated_rollback.sql"},
      {"manifest_index": 5245, "physical_header_index": 5379, "prefix_length": 0, "path": "sql/N4_20260617_d_anchor_repair_full_day_trigger_replay_after_context_localization_pass_rollback.sql"}
    ]
  },
  "ustar_name_fix": {
    "function": "tar_path",
    "old_rejected_condition": "name_length == sizeof(header->name)",
    "old_condition_removed": true,
    "legal_name_length_100_without_nul_allowed": true,
    "bounded_precision_copy_retained": true,
    "prefix_full_width_without_nul_still_rejected": true,
    "safe_relative_path_gate_unchanged": true,
    "raw_name_component_over_100_without_existing_frozen_override_decision": "REJECT",
    "unsafe_path_decision": "REJECT",
    "new_pax_support_added": false,
    "gnu_longname_support_added": false,
    "checksum_type_manifest_blob_mode_owner_provenance_acl_contracts_unchanged": true,
    "root_window_rename_candidate_archive_target_web_contracts_unchanged": true
  },
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "temporary_compiled_helper_path": "/private/tmp/n6_f464_full_width_ustar_recovery3.K19yV8/n6-f464-user-owned-immutable-release-installer-full-width-ustar-recovery3-v1",
  "temporary_helper_attestation_path": "/private/tmp/n6_f464_full_width_ustar_recovery3.K19yV8/f464-full-width-ustar-recovery3-helper-attestation.json",
  "permanently_disabled_old_binaries": [
    {"purpose": "historical_privileged_materializer", "sha256": "3db62fefad54d8b5eb19de51467510065183cf7aa715eb82835fc5fab468bf36", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "release_root_owner_remediation", "sha256": "663ac6561469089eef02a505e80346219a2bbc490bf4289a618d93182d5c7968", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "user_owned_installer_stage3h", "sha256": "3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "enoent_fix_stage3j", "sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "provenance_recovery2_stage3l", "sha256": "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false}
  ],
  "new_binary": {
    "source_sha256": "fd349f4535f127b07948be761f009ddf025cd605400dc87835179f5cbdb8e1f8",
    "binary_sha256": "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c",
    "codesign_cdhash": "eb8f59be8017b1810f8d04c9f6411ae5b6946be9",
    "signature": "adhoc",
    "architecture": "arm64",
    "mode": "0500",
    "uid": 501,
    "gid": 20,
    "argument_count": 0,
    "installed": false,
    "invoked": false,
    "max_future_invocation_count": 1
  },
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "web_route_status": [302, 401, 302],
    "evaluator_job_state": "absent",
    "evaluator_runner_count": 0,
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "governance_session_runtime_operations": 0,
    "business_trading_side_effect_count": 0
  },
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_verify_stage3l_exit72_activation_live_anchors_and_two_old_stagings",
    "remove_only_full_width_name_rejection_in_tar_path",
    "bind_unique_recovery3_staging_and_preserve_historical_and_recovery2_stagings_pre_postflight",
    "compile_helper_in_exact_temporary_directory",
    "adhoc_codesign_helper_in_exact_temporary_directory",
    "write_temporary_helper_attestation_without_invocation",
    "run_static_fixture_and_runtime_control_n6_regressions",
    "append_exit72_diagnostic_recovery_checkpoint_and_single_use_lease"
  ],
  "forbidden_governance_operations": [
    "invoke_any_old_helper",
    "invoke_new_helper",
    "install_helper",
    "install_release",
    "create_delete_modify_seal_or_reuse_any_release_staging_or_target",
    "operate_web_evaluator_virtual_executor_or_launchagent",
    "connect_or_write_database",
    "run_runner_canary_or_deepseek",
    "touch_n1_n5_business_or_trading_state"
  ],
  "recovery_checkpoint_contract": {
    "stage": "F464_FULL_WIDTH_USTAR_RECOVERY_INSTALL_AND_WEB_REBIND",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "required_prior_helper_invocation_count": 1,
    "required_prior_helper_exit_code": 72,
    "required_prior_helper_exit_name": "EXIT_MATERIALIZE",
    "required_prior_failure_archive_physical_header_index": 585,
    "required_prior_failure_manifest_file_index": 573,
    "required_prior_materialized_file_count": 572,
    "required_prior_failed_file_created": false,
    "required_old_binaries_replay_forbidden": true,
    "required_new_binary_sha256": "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c",
    "required_new_binary_cdhash": "eb8f59be8017b1810f8d04c9f6411ae5b6946be9",
    "new_binary_max_invocation_count": 1,
    "allowed_success_exit_code": 0,
    "any_nonzero_exit_decision": "REJECT_NO_RETRY_NO_WEB",
    "any_history_mismatch_decision": "REJECT",
    "any_old_staging_drift_decision": "REJECT",
    "any_side_effect_drift_decision": "REJECT_NO_RECOVERY",
    "second_recovery3_decision": "REJECT",
    "requires_append_only_chain_tail_match": true,
    "forbids_helper_install": true,
    "forbids_privilege_elevation": true,
    "forbids_root_owner_remediation": true,
    "forbids_retry": true,
    "expires_after_seconds": 3600
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "base_commit_tree_verified",
    "activation_chain_55_events_validated",
    "stage3l_exactly_one_call_exit72_verified",
    "stage3l_lease_consumed_verified",
    "stage3l_header585_manifest573_precreate_verified",
    "historical_staging_exact_preflight_verified",
    "historical_staging_exact_postflight_defined",
    "recovery2_staging_exact_preflight_verified",
    "recovery2_staging_exact_postflight_defined",
    "both_old_stagings_never_delete_overwrite_reuse_verified",
    "recovery3_staging_unique_and_absent_verified",
    "target_absent_verified",
    "release_root_restored_0555_verified",
    "web_not_operated_verified",
    "business_trading_side_effect_zero_verified",
    "enoent_acl_and_provenance_fixes_retained",
    "full_width_100_byte_ustar_name_pass_verified",
    "raw_101_plus_and_unsafe_path_reject_verified",
    "archive_17_full_width_names_and_full_traversal_verified",
    "old_binaries_replay_forbidden_verified",
    "new_binary_source_sha_binary_sha_cdhash_verified",
    "new_binary_not_installed_not_invoked",
    "append_only_diagnostic_checkpoint_and_lease_defined"
  ],
  "required_false_fields": [
    "governance_helper_install_requested",
    "governance_helper_invocation_requested",
    "release_install_requested",
    "release_staging_or_target_mutation_requested",
    "historical_or_recovery2_staging_mutation_requested",
    "web_evaluator_virtual_executor_or_launchagent_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "runner_canary_deepseek_requested",
    "second_recovery3_requested",
    "old_binary_replay_requested",
    "new_pax_or_longname_support_requested",
    "root_owner_remediation_requested",
    "sudo_requested",
    "authority_expansion_requested"
  ],
  "required_singleton_counts": {
    "governance_modified_file_count": 3,
    "stage3l_helper_invocation_count": 1,
    "stage3l_helper_exit_code": 72,
    "historical_staging_count": 1,
    "failed_recovery2_staging_count": 1,
    "new_recovery3_staging_name_count": 1,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "new_recovery_max_helper_invocation_count": 1,
    "new_recovery_max_count": 1,
    "retry_count": 0
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "web_evaluator_virtual_executor_or_launchagent_operations_allowed": false,
  "database_operations_allowed": false,
  "runner_canary_deepseek_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_full_width_ustar_name_recovery_governance_v1:end -->

## F464 recovery4 promote and postcondition governance

Stage 3N consumed its only recovery3 lease and invoked the exact attested
helper once. Materialization, child sealing, the 6240-file manifest/blob
closure, and the 45-directory closure all passed. The first operational
failure was `renameatx_np() == -1`: the old helper had already sealed the
staging root to `0555`, so macOS rejected rename from the write-disabled
directory. The old helper then reused recovery2's directory descriptor through
`fdopendir(dup(dirfd))`; the duplicate shared the same open-file-description
offset, so the postcondition's second recursive scan observed `0/0` instead of
the physical `572/8` and overwrote the primary `73 / EXIT_PROMOTE` with
`75 / EXIT_POSTCONDITION`.

Recovery4 keeps every child seal and every content/metadata gate. Every
repeatable recursive scan now opens `"."` with
`O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, creating an independent
open-file-description. The new staging root remains exact owner-only `0700`
until the exclusive rename succeeds; the retained descriptor is then
immediately changed to `0555` and fsynced before full target acceptance.
Failure before rename seals and preserves the unique recovery4 staging root as
`0555` evidence. Primary and postcondition failures and their saved errno
values are reported separately, and a postcondition failure cannot replace a
nonzero primary exit.

The attested `filesystem_sha256` value remains frozen lineage. Its original
construction algorithm is not proven within this three-file gate, so this
policy does not claim to recompute it. The actual acceptance predicate remains
the stronger explicit full archive/manifest/path/blob/mode/owner/provenance/ACL
closure below; content acceptance is not relaxed.

This is an artifact-only `runtime_control` governance stage. It may compile,
ad-hoc codesign, and attest the new helper in the exact temporary directory,
but it must not install or invoke any helper, install or promote a Release,
create or modify any Release staging or target, operate Web/Evaluator/Virtual
Executor or any LaunchAgent, connect to the database, run a
runner/canary/DeepSeek, or touch N1-N5/business/trading state. Recovery4
execution authority is available only to a later independent
`runtime_control` session with the exact append-only checkpoint and active
single-use lease created after the final governance commit.

<!-- policy:n6_f464_recovery4_promote_and_postcondition_governance_v1:begin -->
```json
{
  "policy_id": "n6_f464_recovery4_promote_and_postcondition_governance_v1",
  "canonical_status": "active_canonical_recovery",
  "parent_approval_id": "N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION",
  "approval_status": "ONE_TIME_APPROVAL_ALREADY_ACCEPTED",
  "approval_reconfirmation_required": false,
  "gate": "F464_RECOVERY4_PROMOTE_AND_POSTCONDITION_GOVERNANCE",
  "layer_role": "runtime_control",
  "mode": "FULL MODE",
  "risk_level": "high",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision_for_governance": "ACCEPT",
  "default_execution_decision": "REJECT",
  "phase_mode": "governance_helper_test_temporary_attestation_only",
  "scope_mode": "single_exact_f464_recovery4_promote_and_postcondition_fix",
  "base_governance_commit": "d2e7d015f7180186d0f1c73d1843b5dad40c78a8",
  "base_governance_tree": "d82a0ea1b6825f6cd6eebb4953e2b722c69292ad",
  "governance_commit_binding": "external_post_commit_activation_event",
  "main_checkout_mode": "preserve_only",
  "activation_state_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_bounded_rebind_governance_repair_v1/20260726_091559__0d0b1c2e66c9b925c3f3ce971af037fa494a0b57/activation-state.jsonl",
  "activation_state_before_sha256": "ffc034539d0dc752b67b7fed90f0a106e4122ae2eed29ab65a03a52e616647b9",
  "activation_state_before_event_count": 61,
  "activation_state_before_tail_event_sha256": "f5b2e9c7c8d7f6dccb8feb399a18719c3e2edeaecd1ea95d149b1601931d4bae",
  "activation_state_chain_valid": true,
  "stage3n_failure_contract": {
    "prior_policy_id": "n6_f464_full_width_ustar_name_recovery_governance_v1",
    "prior_policy_canonical_sha256": "f56c6e00903b5acec4705db8c8a646330433d0439150971f00da85c7da7fcd1d",
    "prior_helper_binary_sha256": "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c",
    "prior_helper_codesign_cdhash": "eb8f59be8017b1810f8d04c9f6411ae5b6946be9",
    "prior_helper_invocation_count": 1,
    "prior_helper_reported_exit_code": 75,
    "prior_helper_reported_exit_name": "EXIT_POSTCONDITION",
    "prior_lease_consumed": true,
    "prior_retry_allowed": false,
    "primary_exit_code": 73,
    "primary_exit_name": "EXIT_PROMOTE",
    "primary_failure": "renameatx_np_returned_minus_one_with_staging_root_mode_0555",
    "primary_errno": "unavailable_old_binary_did_not_report_errno",
    "primary_proof": [
      "materialization_and_full_seal_completed",
      "old_source_fchmod_stagefd_0555_precedes_renameatx_np",
      "official_target_absent_after",
      "recovery3_present_same_inode_full_sealed_closure"
    ],
    "secondary_exit_code": 75,
    "secondary_exit_name": "EXIT_POSTCONDITION",
    "secondary_failure": "recovery2_shared_open_file_description_offset_false_negative",
    "secondary_proof": [
      "old_source_fdopendir_dup_dirfd",
      "same_recovery2_fd_preflight_scan_consumed_offset",
      "postcondition_scan_observed_0_files_0_directories",
      "physical_recovery2_tree_remained_572_files_8_directories"
    ],
    "secondary_overwrote_primary_in_old_binary": true,
    "official_target_absent_after": true,
    "web_operation_count": 0,
    "business_trading_side_effect_count": 0
  },
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "release_root_exact": {
    "device": 16777232,
    "inode": 307341897,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "extended_acl_entry_count": 0,
    "xattr_names": ["com.apple.provenance"],
    "provenance_raw_hex": "0100006457BBC065B81880",
    "xattr_fingerprint_sha256": "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea"
  },
  "historical_staging_exact": {
    "name": ".staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320375768,
    "uid": 501,
    "gid": 20,
    "mode": "0700",
    "entry_count": 0,
    "extended_acl_entry_count": 0,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "mode_change_allowed": false
  },
  "failed_recovery2_staging_exact": {
    "name": ".staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery2__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320422668,
    "uid": 501,
    "gid": 20,
    "mode": "0700",
    "file_count": 572,
    "directory_count": 8,
    "symlink_count": 0,
    "entry_records_sha256": "0d7c85da4be58289d4e08cb44daf6471dc9444bb81d83f989084a04e50809db7",
    "first_572_materialized_verification_sha256": "a8f725b39552497fe2480de6210464b04d55766b2c43455653a3981373442d6b",
    "extended_acl_entry_count_root_and_children": 0,
    "provenance_entry_count_root_and_children": 581,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "mode_change_allowed": false
  },
  "failed_recovery3_staging_exact": {
    "name": ".staging_recovery3__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery3__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
    "device": 16777232,
    "inode": 320439773,
    "uid": 501,
    "gid": 20,
    "mode": "0555",
    "file_count": 6240,
    "directory_count": 45,
    "symlink_count": 0,
    "writable_entry_count": 0,
    "child_entry_count": 6285,
    "entry_records_sha256": "48866a88c21f11efb5502320a982d74843c9947072134106543fd784d0f64671",
    "manifest_verification_sha256": "babe766dd6d03207c1f8631913ab22d1ae57d88beb54de420f3a14c412d75f91",
    "ordered_paths_nul_sha256": "2a5bc02bf0ec072a6f40f795b897f46ba7b3152e65d5410caffc65fc134826a7",
    "recursive_xattr_listing_sha256": "b5d5e207fe3052bc25eb1ab85c32d003f38c331213cf3df6041266e4ab59c9b1",
    "extended_acl_entry_count_root_and_children": 0,
    "provenance_entry_count_root_and_children": 6286,
    "full_blob_path_mode_closure": true,
    "delete_allowed": false,
    "overwrite_allowed": false,
    "reuse_allowed": false,
    "rename_allowed": false,
    "mode_change_allowed": false,
    "direct_promotion_allowed": false
  },
  "target_release_name": "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "target_release_must_be_absent_before": true,
  "new_staging_name": ".staging_recovery4__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.staging_recovery4__20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "new_staging_must_be_absent_before": true,
  "new_staging_relation": "unique_same_parent_not_any_of_three_failed_stagings",
  "candidate_root": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62",
  "frozen_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar",
  "frozen_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.git-ls-tree.nul",
  "frozen_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release-attestation.json",
  "frozen_bundle_path": "/Users/chuanfuchen/.codex/artifacts/n6_strategy_center_evaluator_resume_fix_v1/20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/release/config/n6_strategy_center/N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json",
  "frozen_artifact_hashes": {
    "archive_sha256": "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368",
    "manifest_sha256": "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f",
    "filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "release_attestation_sha256": "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3",
    "bundle_file_sha256": "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8",
    "bundle_internal_sha256": "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0"
  },
  "archive_traversal_contract": {
    "manifest_file_count": 6240,
    "archive_directory_count": 45,
    "pax_global_header_count": 1,
    "pax_extended_header_count": 108,
    "full_width_ustar_name_count": 17,
    "full_width_ustar_names_have_no_nul": true
  },
  "filesystem_acceptance_contract": {
    "attested_filesystem_sha256": "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa",
    "attested_filesystem_sha256_role": "lineage_only_not_recomputed_by_helper",
    "claims_attested_filesystem_sha256_recomputed": false,
    "content_acceptance_not_relaxed": true,
    "actual_acceptance_predicate": [
      "frozen_archive_sha256",
      "frozen_manifest_sha256",
      "full_archive_checksum_type_path_mode_traversal",
      "all_6240_manifest_paths_exact",
      "all_6240_git_blob_oids_recomputed",
      "all_file_modes_exact_0444_or_0555",
      "all_45_directories_exact_0555_after_promotion",
      "all_entries_uid501_gid20",
      "all_entries_exact_provenance_xattr",
      "all_entries_extended_acl_zero",
      "no_symlink_no_extra_file_or_directory"
    ]
  },
  "promote_order_contract": {
    "child_seal_behavior": "unchanged",
    "staging_root_mode_before_rename": "0700",
    "group_other_write_before_rename": false,
    "exclusive_rename_api": "renameatx_np",
    "exclusive_rename_flags": ["RENAME_EXCL", "RENAME_NOFOLLOW_ANY", "RENAME_RESOLVE_BENEATH"],
    "post_rename_order": ["fchmod_retained_stagefd_0555", "fsync_retained_stagefd", "full_target_acceptance"],
    "failure_before_rename_staging_root_mode": "0555",
    "release_root_window": "single_0555_to_0755_to_0555",
    "copy_fallback_allowed": false,
    "ordinary_rename_allowed": false,
    "delete_or_overwrite_allowed": false,
    "set_or_remove_xattr_allowed": false,
    "acl_change_allowed": false
  },
  "failure_reporting_contract": {
    "primary_result_saved_separately": true,
    "primary_errno_saved_separately": true,
    "postcondition_result_saved_separately": true,
    "postcondition_errno_saved_separately": true,
    "postcondition_may_override_nonzero_primary": false,
    "final_exit_precedence": "primary_nonzero_else_postcondition",
    "stderr_fields": ["primary_exit", "primary_errno", "postcondition_exit", "postcondition_errno"]
  },
  "helper_source_path": "scripts/n6_f464_privileged_materialize_and_install_v2.c",
  "temporary_compiled_helper_path": "/private/tmp/n6_f464_recovery4_promote_postcondition_final.FC3Cvn/n6-f464-user-owned-immutable-release-installer-recovery4-v1",
  "temporary_helper_attestation_path": "/private/tmp/n6_f464_recovery4_promote_postcondition_final.FC3Cvn/f464-recovery4-helper-attestation.json",
  "helper_attestation_binding": "external_after_policy_canonicalization",
  "permanently_disabled_old_binaries": [
    {"purpose": "historical_privileged_materializer", "sha256": "3db62fefad54d8b5eb19de51467510065183cf7aa715eb82835fc5fab468bf36", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "release_root_owner_remediation", "sha256": "663ac6561469089eef02a505e80346219a2bbc490bf4289a618d93182d5c7968", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "user_owned_installer_stage3h", "sha256": "3e935d03611c0a775a81f06160bc16af0e9d860f08836ef479d70a8cfbbe7c88", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "enoent_fix_stage3j", "sha256": "7d4a7f815e44d729558c79cbf47a0dc80b4f5be708fa4d87d49af43e3d31fe6d", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "provenance_recovery2_stage3l", "sha256": "4ecef31c10e99754a916beb7db1661e89cde5a3915323d5880be13ab8ddfddb0", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false},
    {"purpose": "full_width_recovery3_stage3n", "sha256": "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c", "future_invocation_allowed": false, "future_replay_allowed": false, "future_retry_allowed": false}
  ],
  "new_binary": {
    "source_sha256": "7d9b5b058e2dfaf24018795919ef640bcc4b846187afaf2f02e70ae86c32ab0e",
    "binary_sha256": "aecb084b4de66a172e91238c1f38b74d858f1c094a0938af9701193ea619e7a5",
    "codesign_cdhash": "830bd00c4ad9d65935c3c9628d1f5a339c0540ce",
    "signature": "adhoc",
    "architecture": "arm64",
    "mode": "0500",
    "uid": 501,
    "gid": 20,
    "argument_count": 0,
    "installed": false,
    "invoked": false,
    "max_future_invocation_count": 1
  },
  "live_freeze": {
    "web_release_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
    "web_plist_sha256": "ee2b1e451b5f0e85a74e5510233e5b4272af4daf9c525d1b736af360f4237bc7",
    "web_strategy_write": "0",
    "web_route_status": [302, 401, 302],
    "evaluator_job_state": "absent",
    "evaluator_runner_count": 0,
    "virtual_executor_plist_sha256": "bae58f9d30938f13a6d9d1d4d92daa2c6be3d7b244fa819b0d6ea6b2b9c7b469",
    "governance_session_runtime_operations": 0,
    "business_trading_side_effect_count": 0
  },
  "allowed_governance_files": [
    "docs/EXECUTION_KERNEL.md",
    "scripts/n6_f464_privileged_materialize_and_install_v2.c",
    "tests/test_n6_f464_immutable_release_installer_governance.py"
  ],
  "allowed_governance_operations": [
    "read_only_verify_stage3n_exactly_one_exit75_primary73_secondary_offset_false_negative",
    "read_only_verify_three_failed_stagings_and_target_absent",
    "replace_repeatable_recursive_scan_dup_with_independent_openat_dot",
    "retain_staging_root_0700_until_exclusive_rename_then_seal_0555",
    "preserve_primary_and_postcondition_result_errno_separately",
    "bind_unique_recovery4_staging_and_disable_old_binary_replay",
    "compile_codesign_and_attest_helper_in_exact_temporary_directory_without_invocation",
    "run_static_fixture_and_runtime_control_n6_regressions",
    "append_stage3n_diagnostic_recovery4_checkpoint_and_single_use_lease"
  ],
  "forbidden_governance_operations": [
    "invoke_any_old_helper",
    "invoke_new_helper",
    "install_helper",
    "install_or_promote_release",
    "create_delete_modify_seal_or_reuse_any_release_staging_or_target",
    "direct_promote_recovery3",
    "operate_web_evaluator_virtual_executor_or_launchagent",
    "connect_or_write_database",
    "run_runner_canary_or_deepseek",
    "touch_n1_n5_business_or_trading_state"
  ],
  "recovery_checkpoint_contract": {
    "stage": "F464_RECOVERY4_INSTALL_AND_WEB_REBIND",
    "target": "BOUNDED_REBIND_WEB_TARGET",
    "status": "ready",
    "required_prior_policy_id": "n6_f464_full_width_ustar_name_recovery_governance_v1",
    "required_prior_helper_invocation_count": 1,
    "required_prior_helper_reported_exit_code": 75,
    "required_prior_primary_exit_code": 73,
    "required_prior_secondary_exit_code": 75,
    "required_prior_lease_consumed": true,
    "required_three_failed_stagings_exact": true,
    "required_recovery3_full_closure": true,
    "required_target_absent": true,
    "required_old_binaries_replay_forbidden": true,
    "required_new_binary_sha256": "aecb084b4de66a172e91238c1f38b74d858f1c094a0938af9701193ea619e7a5",
    "required_new_binary_cdhash": "830bd00c4ad9d65935c3c9628d1f5a339c0540ce",
    "new_binary_max_invocation_count": 1,
    "allowed_success_exit_code": 0,
    "any_nonzero_exit_decision": "REJECT_NO_RETRY_NO_WEB",
    "any_history_mismatch_decision": "REJECT",
    "any_old_staging_drift_decision": "REJECT",
    "any_side_effect_drift_decision": "REJECT_NO_RECOVERY",
    "non_exact_stage3n_history_decision": "REJECT",
    "second_recovery4_decision": "REJECT",
    "requires_append_only_chain_tail_match": true,
    "forbids_helper_install": true,
    "forbids_privilege_elevation": true,
    "forbids_root_owner_remediation": true,
    "forbids_retry": true,
    "expires_after_seconds": 3600
  },
  "required_true_fields": [
    "parent_approval_inherited",
    "base_commit_tree_verified",
    "activation_chain_61_events_validated",
    "stage3n_exactly_one_call_exit75_verified",
    "stage3n_primary_exit73_verified",
    "stage3n_secondary_recovery2_offset_false_negative_verified",
    "stage3n_lease_consumed_verified",
    "historical_staging_exact_pre_postflight_defined",
    "recovery2_staging_exact_pre_postflight_defined",
    "recovery3_staging_exact_pre_postflight_defined",
    "three_failed_stagings_never_delete_overwrite_reuse_verified",
    "recovery4_staging_unique_and_absent_verified",
    "target_absent_verified",
    "release_root_restored_0555_verified",
    "web_not_operated_verified",
    "evaluator_absent_verified",
    "virtual_executor_unchanged_verified",
    "business_trading_side_effect_zero_verified",
    "independent_recursive_scan_open_description_verified",
    "same_recovery2_fd_two_scans_572_8_verified",
    "rename_before_staging_root_seal_verified",
    "failure_path_staging_root_0555_verified",
    "primary_exit_precedence_and_errno_reporting_verified",
    "full_6240_45_17_archive_manifest_blob_mode_metadata_closure_verified",
    "filesystem_sha_lineage_only_claim_accurate",
    "old_binaries_replay_forbidden_verified",
    "new_binary_source_sha_binary_sha_cdhash_verified",
    "new_binary_not_installed_not_invoked",
    "append_only_stage3n_diagnostic_checkpoint_and_lease_defined"
  ],
  "required_false_fields": [
    "governance_helper_install_requested",
    "governance_helper_invocation_requested",
    "release_install_or_promote_requested",
    "release_staging_or_target_mutation_requested",
    "historical_recovery2_or_recovery3_staging_mutation_requested",
    "direct_recovery3_promote_requested",
    "web_evaluator_virtual_executor_or_launchagent_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "runner_canary_deepseek_requested",
    "second_recovery4_requested",
    "old_binary_replay_requested",
    "set_or_remove_xattr_requested",
    "acl_change_requested",
    "copy_fallback_requested",
    "ordinary_rename_requested",
    "filesystem_sha_recomputed_claimed",
    "root_owner_remediation_requested",
    "sudo_requested",
    "authority_expansion_requested"
  ],
  "required_singleton_counts": {
    "governance_modified_file_count": 3,
    "stage3n_helper_invocation_count": 1,
    "stage3n_reported_exit_code": 75,
    "stage3n_primary_exit_code": 73,
    "historical_failed_staging_count": 3,
    "new_recovery4_staging_name_count": 1,
    "governance_helper_install_count": 0,
    "governance_helper_invocation_count": 0,
    "new_recovery_max_helper_invocation_count": 1,
    "new_recovery_max_count": 1,
    "retry_count": 0,
    "web_evaluator_virtual_executor_launchagent_operation_count": 0,
    "database_operation_count": 0,
    "runner_canary_deepseek_operation_count": 0,
    "n1_n5_business_trading_operation_count": 0
  },
  "governance_session_cannot_install_helper": true,
  "governance_session_cannot_invoke_helper": true,
  "governance_session_cannot_install_release": true,
  "web_evaluator_virtual_executor_or_launchagent_operations_allowed": false,
  "database_operations_allowed": false,
  "runner_canary_deepseek_operations_allowed": false,
  "n1_n5_business_operations_allowed": false
}
```
<!-- policy:n6_f464_recovery4_promote_and_postcondition_governance_v1:end -->
