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

  affected_resources:
    description: "Exact non-file resources for a named bounded runtime policy."
    type: list[string]

  policy_id:
    description: "Named fail-closed exception policy, or null for default evaluation."
    type: string | null

  runtime_execution_requested:
    description: "Whether the request asks for a runtime action."
    type: boolean

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

The request is clear, scoped to the declared `layer_role`, affects only allowed files or resources, follows N1 -> N6 one-way data flow, and introduces no forbidden runtime execution. A runtime request is acceptable only when it satisfies a named fail-closed policy in full; partial policy matches never produce `ACCEPT`.

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
runtime execution = forbidden unless one applicable named fail-closed exception policy is satisfied in full
ambiguity = stop
```

Detailed rules:

1. If the request attempts to mutate another layer, the Kernel returns `REJECT`.
2. If `layer_role` is missing or unclear, the Kernel returns `BLOCK`.
3. If the request includes runtime execution, worker startup, database writes, rollback execution, outbox consumption, or real trading, the Kernel returns `REJECT` for this phase unless the request fully satisfies one applicable named exception below. Section 4.1 never permits worker startup or rollback execution. Section 4.2 permits only the exact N6 Web service restart and frozen-source Release recovery declared there. Section 4.3 permits only the exact N6 display-only scheduled run-once evaluator and its exact-label activation/rollback. Section 4.8 permits only one exact evaluator bootout with state-driven PID/job absence. Section 4.17 permits one archive-gated disk-governance phase only; it never permits archive creation, database writes, business-service operations, manual cleanup replay, or cross-layer mutation. None of the policies permits outbox consumption or real trading.
4. If the request is ambiguous, Codex must stop before modifying files.
5. If the request affects files outside `affected_files`, the Kernel returns `REJECT`.
6. If the request violates one-way N1 -> N6 data flow, the Kernel returns `REJECT`.

### 4.0A Strategy Center Operational-Policy Retirement Override

The lifecycle registry below has higher decision priority than every historical
Strategy Center policy block in this document. Historical blocks, SQL, traces,
and commits remain immutable audit evidence; they are not deleted or rewritten.
After this registry takes effect, any request naming a retired policy returns
`REJECT` before its historical contract is evaluated.

<!-- policy-lifecycle:n6_strategy_center_30_day_isolation_decommission_v1:begin -->
```json
{
  "lifecycle_id": "n6_strategy_center_30_day_isolation_decommission_v1",
  "decision_precedence": "retirement_override_before_historical_policy_evaluation",
  "retired_status": "RETIRED",
  "retired_policy_decision": "REJECT",
  "retired_policy_ids": [
    "n6_strategy_center_display_only_bounded_run_once_v1",
    "n6_strategy_center_display_only_scheduled_evaluator_v1",
    "n6_strategy_center_schema_migration_maintenance_window_v1",
    "n6_strategy_center_post_081_v2_web_bounded_rebind_v1",
    "n6_strategy_center_post_083_v2_web_bounded_rebind_v1",
    "n6_strategy_center_post_081_v2_catalog_migration_window_v1",
    "n6_strategy_center_post_083_single_user_pending_v2_revision_v1",
    "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1",
    "n6_strategy_center_pre_canary_web_write_quiesce_v1",
    "n6_strategy_center_reviewed_view_date_authority_084_v1",
    "n6_strategy_center_post_canary_web_write_restore_v1",
    "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1",
    "n6_strategy_center_v1_retirement_after_all_users_v2_v1"
  ],
  "active_decommission_policy_ids": [
    "n6_strategy_center_decommission_web_runtime_v1",
    "n6_strategy_center_decommission_schema_archive_v1"
  ],
  "historical_artifacts_preserved": true,
  "historical_policy_reactivation_allowed": false,
  "physical_deletion_automatically_scheduled": false,
  "physical_deletion_requires_new_independent_explicit_authorization_after_retention": true,
  "retention_days": 30,
  "canary_heartbeat_operation_authorized_by_governance_session": false,
  "governance_session_runtime_execution_authorized": false
}
```
<!-- policy-lifecycle:n6_strategy_center_30_day_isolation_decommission_v1:end -->

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
    "selection_revision_authority": "exact_current_scope_positive_revision_id",
    "trade_date_authority": "reviewed_n6_display_basis_consensus",
    "required_authority_views": [
      "v_n6_stock_condition_display_basis",
      "v_n6_index_condition_display_basis",
      "v_n6_board_condition_display_basis"
    ],
    "required_authority_fields": [
      "for_trade_date",
      "source_trade_date",
      "source_run_id",
      "row_count"
    ],
    "authority_rule": "latest_complete_single_batch_for_trade_date_consensus",
    "membership_rule": "max_trade_date_lte_source_trade_date",
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
      "reviewed_n6_authority_consensus_verified",
      "reviewed_n6_latest_complete_batches_verified",
      "reviewed_n6_projection_card_watermarks_frozen",
      "membership_asof_provenance_frozen",
      "natural_current_date_reviewed_events_present",
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
      "virtual_executor_strategy_center_code_reference_detected",
      "common_trade_calendar_authority_requested",
      "n1_n5_raw_table_authority_requested"
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
    "reviewed_n6_authority_consensus_verified",
    "reviewed_n6_latest_complete_batches_verified",
    "reviewed_n6_projection_card_watermarks_frozen",
    "membership_asof_provenance_frozen",
    "natural_current_date_reviewed_events_present",
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
    "common_trade_calendar_authority_requested",
    "n1_n5_raw_table_authority_requested",
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
   positive principal/user/revision scope on the current reviewed-N6
   `for_trade_date` consensus, with dry-run, primary, and replay attempts all
   verified zero before Gate2 begins. Its exact
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
  "required_integrated_implementation_commit": "d85df6328bde223e912dabc3bd65e16df984aa45",
  "required_integrated_implementation_tree": "d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1",
  "required_release_git_blobs": {
    "scripts/run_n6_strategy_center_auto_once.py": "fd5563fd80f7b57012d71025bfe0eeaed97df2c8",
    "scripts/plan_n6_strategy_center_launchd.py": "fc987b38cb17ae38884198421747ae65a8a02a97",
    "requirements/n6_strategy_evaluator_py311.lock.txt": "1365d5f667144149dcacc5e38d31b0c65d060759",
    "requirements/n6_strategy_evaluator_py311.wheel-manifest.v1.json": "05dd4dc5b87dc27fb00618fb77ba36b3e5aed2c6",
    "src/ashare_v3/web/n6_app_v1.py": "b8d2dd411f3d21f2dc30c3247147b9a480bab322",
    "src/ashare_v3/user/strategy_center_worker.py": "89710d5cdbfd1d3e5be520823107a885aa908813",
    "tests/test_n6_strategy_center_auto.py": "2f182c28f07b0664cc7477a40919d74965908143",
    "tests/test_n6_strategy_center_launchd_plan.py": "a8a3b221fc444eac9c72251e2241cb9728df0fa0",
    "tests/test_n6_strategy_center_worker.py": "19ad53d419962388f6a46fa1c398103a24ac32a5",
    "tests/test_n6_user_app.py": "be6a50c4e761c72f14c0a55b4176b7f0c6728793",
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
  "reviewed_trade_date_fields": {
    "stock": "stock_reviewed_for_trade_date",
    "index": "index_reviewed_for_trade_date",
    "board": "board_reviewed_for_trade_date"
  },
  "reviewed_authority_views": [
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis"
  ],
  "reviewed_authority_rule": "latest_complete_single_batch_for_trade_date_consensus",
  "membership_rule": "max_trade_date_lte_source_trade_date",
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
    "reviewed_n6_trade_date_consensus_verified",
    "reviewed_n6_latest_complete_single_batches_verified",
    "reviewed_n6_source_lineage_frozen",
    "reviewed_n6_projection_card_watermarks_frozen",
    "membership_asof_provenance_frozen",
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
    "virtual_executor_configuration_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "twelve_tick_observation_contract_frozen",
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
    "reviewed_n6_trade_date_consensus_missing_or_mismatched",
    "reviewed_n6_batch_ambiguity_detected",
    "reviewed_n6_source_lineage_drift_detected",
    "reviewed_n6_projection_card_watermark_drift_detected",
    "common_trade_calendar_authority_requested",
    "n1_n5_raw_table_authority_requested",
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
    "virtual_executor_operation_requested",
    "virtual_executor_strategy_center_write_privilege_detected",
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
  "required_post_activation_tick_observation_count": 12,
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
   20260722 artifact is historical evidence only and cannot authorize a later
   date. A historical PASS label without a fresh current-date exact-Release
   artifact hash is insufficient. The stock/index/board reviewed display-basis
   latest complete singleton batches must agree on `for_trade_date`; calendar
   rows and N1-N5 raw tables cannot satisfy this gate. Membership remains
   `max(trade_date) <= source_trade_date` as-of evidence only.
3. One direct child of the approved Release root must independently pass exact
   integrated commit `d85df6328bde223e912dabc3bd65e16df984aa45`, integrated
   tree `d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1`, archive, manifest,
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
   or scope argument. The planner accepts an immutable Release tree only when its
   root, every directory, and every file have one uniform owner: either the
   current uid or `uid=0`. Mixed ownership, any other uid, writable modes,
   symlinks, unexpected hardlinks, or an incomplete path/blob/mode/manifest
   closure fail closed.
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

### 4.5A Strategy Center Post-083 V2 Web Bounded Rebind Exception

This fail-closed policy authorizes one exact Web-only Release rebind after
081/082/083/084 have committed and strategy selection writes are enabled. It
exists only to move the exact N6 Web from the frozen legacy short-name Release
`20260724_042200__a1dc7350` to one formally named, fully attested 40-character
immutable Release. The legacy source is accepted once and only as the frozen
rollback source; it is never a valid target and cannot be reused by another
request.

<!-- policy:n6_strategy_center_post_083_v2_web_bounded_rebind_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_post_083_v2_web_bounded_rebind_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "scope_mode": "post_083_single_web_legacy_source_formal_target_release",
  "phase_mode": "post_083_v2_web_rebind_only",
  "launch_agent_label": "com.ashare-v3.n6.user-web",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
  "evaluator_launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "service_port": 8786,
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "source_release_name_exact": "20260724_042200__a1dc7350",
  "source_release_full_commit_sha_exact": "a1dc73503a07055f7bdb9cd29b378d1272642473",
  "source_release_short_commit_prefix_exact": "a1dc7350",
  "target_release_name_pattern": "^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$",
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
    "source_release_full_commit_sha": "^[0-9a-f]{40}$",
    "source_release_tree_sha": "^[0-9a-f]{40}$",
    "source_release_archive_sha256": "^[0-9a-f]{64}$",
    "source_release_git_ls_tree_sha256": "^[0-9a-f]{64}$",
    "source_release_manifest_sha256": "^[0-9a-f]{64}$",
    "source_release_filesystem_sha256": "^[0-9a-f]{64}$",
    "source_release_attestation_sha256": "^[0-9a-f]{64}$",
    "target_release_commit_sha": "^[0-9a-f]{40}$",
    "target_release_tree_sha": "^[0-9a-f]{40}$",
    "target_release_archive_sha256": "^[0-9a-f]{64}$",
    "target_release_git_ls_tree_sha256": "^[0-9a-f]{64}$",
    "target_release_manifest_sha256": "^[0-9a-f]{64}$",
    "target_release_filesystem_sha256": "^[0-9a-f]{64}$",
    "target_release_attestation_sha256": "^[0-9a-f]{64}$",
    "post_083_084_schema_catalog_evidence_sha256": "^[0-9a-f]{64}$",
    "web_before_plist_sha256": "^[0-9a-f]{64}$",
    "web_target_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_quiesce_gate_artifact_sha256": "^[0-9a-f]{64}$",
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
    "migration_082_committed_verified",
    "migration_083_committed_verified",
    "migration_084_committed_verified",
    "post_083_084_schema_catalog_evidence_verified",
    "legacy_source_exception_current_request_only",
    "legacy_source_exception_not_previously_consumed_verified",
    "legacy_source_exception_consumption_record_defined",
    "legacy_source_is_current_web_release_verified",
    "legacy_source_full_commit_matches_short_prefix_verified",
    "legacy_source_full_commit_tree_archive_manifest_filesystem_closed",
    "legacy_source_git_blob_mode_path_closed",
    "legacy_source_no_missing_extra_symlink_or_file_hardlink_verified",
    "legacy_source_owner_group_mode_acl_xattr_frozen",
    "legacy_source_immutable_verified",
    "legacy_source_rollback_only",
    "source_release_root_direct_child_verified",
    "target_release_immutable_verified",
    "target_release_root_direct_child_verified",
    "target_release_formal_name_matches_commit_verified",
    "target_git_blob_mode_path_closed",
    "target_no_missing_extra_symlink_or_file_hardlink_verified",
    "target_owner_group_mode_acl_xattr_verified",
    "target_no_lineage_regression_verified",
    "target_preserves_source_effective_n6_deltas_verified",
    "target_v2_web_api_ui_sse_verified",
    "target_observation_surface_verified",
    "target_direction_and_trading_minute_freshness_verified",
    "target_post_083_084_schema_compatible_verified",
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
    "web_strategy_write_before_one_verified",
    "web_strategy_write_target_one_verified",
    "web_strategy_write_after_one_required",
    "independent_evaluator_quiesce_gate_passed",
    "evaluator_plist_runner_release_frozen",
    "evaluator_job_absent_verified",
    "evaluator_pid_absent_verified",
    "evaluator_not_operated_by_this_policy_verified",
    "virtual_executor_loaded_start_interval_five_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_role_acl_frozen",
    "virtual_executor_object_boundary_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_web_rebind_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "state_driven_teardown_defined",
    "old_pid_exit_required_before_bootstrap",
    "job_absence_required_before_bootstrap",
    "readiness_contract_frozen",
    "route_contract_frozen",
    "stability_window_frozen",
    "automatic_rollback_contract_frozen",
    "rollback_restores_exact_legacy_source_only",
    "rollback_preserves_strategy_write_one",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "runtime_ownership_ambiguous",
    "multiple_services_requested",
    "release_drift_detected",
    "plist_drift_detected",
    "environment_drift_detected",
    "lineage_regression_detected",
    "post_083_084_schema_catalog_drift_detected",
    "legacy_source_reuse_requested",
    "legacy_source_target_requested",
    "non_exact_legacy_source_requested",
    "legacy_source_content_mutation_requested",
    "target_short_name_requested",
    "immutable_release_content_modification_requested",
    "extra_environment_change_requested",
    "other_launch_agent_touched",
    "fixed_sleep_bootstrap_requested",
    "primary_retry_requested",
    "signal_or_kill_requested",
    "strategy_write_disable_requested",
    "strategy_evaluator_execute_requested",
    "strategy_evaluator_stop_requested",
    "strategy_evaluator_start_requested",
    "strategy_evaluator_restore_requested",
    "evaluator_operation_requested_by_this_policy",
    "virtual_executor_operation_requested",
    "virtual_executor_stop_requested",
    "virtual_executor_start_requested",
    "virtual_executor_restart_requested",
    "virtual_executor_configuration_drift_detected",
    "virtual_executor_acl_or_object_boundary_drift_detected",
    "normal_virtual_executor_pid_runs_change_is_configuration_drift",
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
    "rollback_restore_exact_legacy_source_plist",
    "rollback_bootout_exact_web_label",
    "rollback_bootstrap_exact_web_plist"
  ],
  "primary_bootout_attempts": 1,
  "primary_bootstrap_attempts": 1,
  "maximum_primary_retries": 0,
  "maximum_rollback_attempts": 1,
  "rollback_requires_primary_failure": true,
  "rollback_requires_frozen_source": true,
  "evaluator_operation_attempts": 0,
  "virtual_executor_operation_attempts": 0,
  "teardown_timeout_seconds": 30,
  "readiness_timeout_seconds": 60,
  "stability_window_seconds": 30,
  "required_strategy_write_flag_value": "1",
  "required_virtual_executor_start_interval_seconds": 5,
  "required_login_redirect_path": "/n6/login",
  "required_route_expectations": {
    "/n6/app/strategy-center": 302,
    "/api/n6/app/v3/strategy-center": 401,
    "/n6/app/signals": 302
  },
  "normal_virtual_executor_pid_runs_change_is_configuration_drift": false
}
```
<!-- policy:n6_strategy_center_post_083_v2_web_bounded_rebind_v1:end -->

Evaluation is fail-closed and ordered:

1. A new independent `runtime_control` request must explicitly authorize this
   one post-083 Web rebind and select this policy. The governance session that
   adds the policy cannot execute it.
2. Fresh immutable artifacts must prove 081/082/083/084 committed and freeze
   their schema/catalog state. This policy grants no database connection,
   migration, or business DML authority.
3. The only accepted source basename is
   `20260724_042200__a1dc7350`. Its short suffix must close to full commit
   `a1dc73503a07055f7bdb9cd29b378d1272642473`, and its tree, archive,
   git-ls-tree, manifest, filesystem, path/blob/mode, ownership, and immutable
   attestation must close with no missing, extra, symlink, or regular-file
   hardlink. This one-time exception is rollback-only; another short source,
   reuse, mutation, or use as a target returns `REJECT`.
4. The one target must use the formal 40-character Release name, bind its name
   to the exact commit, close every immutable hash, preserve all effective N6
   source deltas, and prove no lineage or schema regression.
5. The exact Web is the only mutable service. Its strategy-write flag remains
   `1` before, in the target plist, after readiness, and after rollback. Only
   WorkingDirectory and PYTHONPATH may change.
6. A prior independent N6 quiesce gate must prove the exact Strategy Center
   evaluator job and PID absent. This policy performs zero evaluator
   operations and cannot stop, start, restore, bootstrap, or kickstart it.
7. The exact virtual executor may keep its existing `StartInterval=5`
   scheduling. Its label, plist, Release, runner, role/ACL, and object-boundary
   hashes remain frozen, and its write authority must be disjoint from the Web
   rebind and Strategy Center objects. This policy performs zero executor
   operations. Normal PID/runs cycling alone is not configuration drift.
8. The Web receives one state-driven primary bootout/bootstrap pair, zero
   retries, a 60-second readiness window, and a 30-second stability window.
   Fixed sleeps, signals, kill, kickstart, or a second primary attempt return
   `REJECT`.
9. A proven primary health failure permits one rollback pair restoring only the
   fully frozen legacy source plist/Release with strategy writes still `1`.
   Rollback is not a second target attempt and does not renew the legacy-source
   exception.
10. Database, migration, evaluator or virtual-executor operation, another
    LaunchAgent, mutable Release content, N1-N5, queues, selection/projection/
    change, proposal/order/trade/position/cash, broker, or missing/drifted
    evidence returns `REJECT`.

This policy neither replaces nor relaxes
`n6_user_web_immutable_release_bounded_rebind_v1` or
`n6_strategy_center_post_081_v2_web_bounded_rebind_v1`.

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

### 4.8 Strategy Center Evaluator Quiesce for Web Rebind Exception

This `runtime_control` exception exists only for the post-083 state where
Strategy Center selection writes are enabled and the exact scheduled evaluator
must be quiesced before a separately authorized Web Release rebind. It grants no
Web mutation, evaluator execution, database, migration, or business authority.
A governance task that creates or changes this policy cannot execute it in the
same session.

<!-- policy:n6_strategy_center_evaluator_quiesce_for_web_rebind_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_exact_evaluator_quiesce_only",
  "phase_mode": "post_083_write_enabled_prepare_web_rebind",
  "launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n6.strategy-center-evaluator-v1.plist",
  "web_launch_agent_label": "com.ashare-v3.n6.user-web",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "required_strategy_write_flag_value": "1",
  "required_hash_fields": {
    "evaluator_plist_sha256": "^[0-9a-f]{64}$",
    "evaluator_runner_sha256": "^[0-9a-f]{64}$",
    "evaluator_release_sha256": "^[0-9a-f]{64}$",
    "evaluator_role_acl_sha256": "^[0-9a-f]{64}$",
    "evaluator_before_state_sha256": "^[0-9a-f]{64}$",
    "evaluator_after_state_sha256": "^[0-9a-f]{64}$",
    "web_plist_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_plist_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_release_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_runner_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_role_acl_sha256": "^[0-9a-f]{64}$",
    "virtual_executor_object_boundary_sha256": "^[0-9a-f]{64}$"
  },
  "required_singleton_counts": {
    "service_count": 1,
    "launch_agent_count": 1,
    "evaluator_label_count": 1,
    "bootout_target_count": 1
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "post_083_state_verified",
    "strategy_write_flag_one_verified",
    "evaluator_launchd_ownership_verified",
    "evaluator_plist_path_frozen",
    "evaluator_plist_metadata_frozen",
    "evaluator_runner_frozen",
    "evaluator_release_frozen",
    "evaluator_role_acl_frozen",
    "evaluator_before_state_frozen",
    "state_driven_teardown_defined",
    "evaluator_pid_absence_required",
    "evaluator_job_absence_required",
    "evaluator_pid_absent_after",
    "evaluator_job_absent_after",
    "evaluator_after_state_frozen",
    "web_plist_and_state_frozen",
    "web_not_operated_verified",
    "virtual_executor_configuration_frozen",
    "virtual_executor_role_acl_frozen",
    "virtual_executor_object_boundary_frozen",
    "virtual_executor_strategy_center_write_disjoint_verified",
    "virtual_executor_not_operated_verified",
    "failure_evidence_retention_defined",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "authorization_missing",
    "runtime_ownership_ambiguous",
    "evaluator_label_drift_detected",
    "evaluator_plist_drift_detected",
    "evaluator_runner_drift_detected",
    "evaluator_release_drift_detected",
    "evaluator_role_acl_drift_detected",
    "evaluator_execute_requested",
    "evaluator_bootstrap_requested",
    "evaluator_kickstart_requested",
    "evaluator_kill_or_signal_requested",
    "evaluator_retry_requested",
    "evaluator_automatic_restore_requested",
    "web_operation_requested",
    "web_plist_modification_requested",
    "web_bootout_requested",
    "web_bootstrap_requested",
    "virtual_executor_operation_requested",
    "virtual_executor_configuration_drift_detected",
    "virtual_executor_role_acl_drift_detected",
    "virtual_executor_object_boundary_drift_detected",
    "normal_virtual_executor_pid_runs_change_treated_as_drift",
    "other_launch_agent_touched",
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
    "n1_n5_write_requested",
    "concurrent_runtime_change"
  ],
  "allowed_mutation_resources": [
    "gui/current-user/com.ashare-v3.n6.strategy-center-evaluator-v1"
  ],
  "allowed_runtime_operations": [
    "launchctl_bootout_exact_evaluator_label_once",
    "state_driven_wait_for_evaluator_pid_and_job_absence",
    "freeze_quiesce_result_and_failure_evidence"
  ],
  "evaluator_bootout_attempts": 1,
  "evaluator_bootstrap_attempts": 0,
  "maximum_retries": 0,
  "teardown_timeout_seconds": 30,
  "failure_auto_restore_evaluator": false,
  "normal_virtual_executor_pid_runs_change_is_configuration_drift": false
}
```
<!-- policy:n6_strategy_center_evaluator_quiesce_for_web_rebind_v1:end -->

Evaluation is fail-closed and ordered:

1. The current request must explicitly authorize this policy and declare
   `layer_role=runtime_control`, the exact evaluator label, and exactly one
   bootout target.
2. Fresh evidence must freeze the evaluator plist path and metadata, runner,
   immutable Release, role/ACL, launchd ownership, PID/job state, and hashes.
   Ambiguous ownership or configuration drift returns `REJECT`.
3. Strategy write must already equal `1` and remain unchanged. The Web label,
   plist, and runtime are evidence-only and must not be modified, restarted, or
   rebound.
4. The only runtime mutation is one `launchctl bootout` of the exact evaluator.
   Completion requires state-driven proof that both its PID and launchd job are
   absent. Bootstrap, kickstart, kill/signal, fixed-delay substitution, retry,
   or another LaunchAgent returns `REJECT`.
5. The virtual executor must not be operated. Its label, plist, Release,
   runner, role/ACL, and object boundary remain frozen and write-disjoint.
   Normal configured five-second PID/runs cycling alone is not drift.
6. Failure does not authorize automatic evaluator restore. Evidence is retained
   and a later recovery or Web rebind requires its own policy and current user
   authorization.
7. Any database connection, migration, evaluator execution, selection/
   projection/change, queue, N1-N5, business, broker, or trading effect returns
   `REJECT`.

### 4.10A Pre-Canary Web Strategy-Write Quiesce

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

This is a distinct runtime gate because the 081 maintenance-window policy
cannot be reused after 083: it owns evaluator bootout/token preparation, while
this policy requires the evaluator already absent and changes only the exact
Web flag on the same d85 Release. One primary bootout/bootstrap is allowed;
real health failure may restore only the frozen plist with flag `1` once.
Evaluator and virtual-executor operation, Release/path/environment drift,
database or N1-N5 access, canary execution, and trading all return `REJECT`.

### 4.11 Reviewed N6 Date Authority

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
  "required_authority_views": [
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis"
  ],
  "authority_rule": "latest_complete_single_batch_for_trade_date_consensus",
  "required_authority_fields": [
    "for_trade_date",
    "source_trade_date",
    "source_run_id",
    "row_count"
  ],
  "membership_rule": "max_trade_date_lte_source_trade_date",
  "attempts": 1,
  "retries": 0,
  "function_calls": 0,
  "evaluator_must_be_quiesced": true,
  "web_strategy_write": 0,
  "compensation_function_calls": 0,
  "forbidden_objects": [
    "common_trade_calendar",
    "n1_n5_raw_tables",
    "selection_revision",
    "selection_item",
    "match_projection",
    "observation_projection",
    "match_change",
    "catalog",
    "proposal",
    "order",
    "trade",
    "position",
    "cash"
  ]
}
```
<!-- policy:n6_strategy_center_reviewed_view_date_authority_084_v1:end -->

The Strategy Center business date is always the unique `for_trade_date`
consensus of the latest complete singleton stock/index/board reviewed N6
display-basis batches. Reviewed projections/cards prove current-date natural
event availability. Membership never selects the business date and is used
only as `max(trade_date) <= source_trade_date`. Any missing or ambiguous batch,
date disagreement, lineage/watermark drift, `common_trade_calendar`, or N1-N5
raw-table authority fails closed.

### 4.12 Post-Canary Web Strategy-Write Restore

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
  "required_evaluator_state": "loaded_stable_exact_release",
  "required_evaluator_scope_mode": "single_principal_user_revision_per_tick",
  "required_evaluator_order": "pending_first_active_round_robin",
  "max_bootout_attempts": 1,
  "max_bootstrap_attempts": 1,
  "max_retries": 0,
  "virtual_executor_operations": 0,
  "database_writes": 0,
  "trade_writes": 0
}
```
<!-- policy:n6_strategy_center_post_canary_web_write_restore_v1:end -->

Restore is one exact-Web `0 -> 1` flag-only rebind after a current reviewed-N6
date canary and at least twelve stable five-second evaluator ticks. It requires
pending zero, exact Release/plist/ACL/ownership stability, no overlap, deadline,
backoff, restart-loop, or cross-user write, and zero virtual-executor/database/
trade operation. Failure restores the frozen Web plist with flag `0`.

### 4.13 Remaining Users: One Pending V2 Revision per Gate

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
  "effective_trade_date_source": "reviewed_n6_display_basis_for_trade_date_consensus",
  "selection_creation_authority_mode": "official_owner_user_isolated_selection_function",
  "required_target_status": "pending",
  "required_target_replay_status": "pending",
  "required_package_version_transition": "same_active_v1_keys_to_v2",
  "expected_rollout_gate_count": 7,
  "required_mutation_statement_classes": [
    "BEGIN",
    "SET",
    "SELECT_ADVISORY_XACT_LOCK",
    "SELECT_OFFICIAL_SELECTION_FUNCTION",
    "SELECT_READ_ONLY_POSTFLIGHT",
    "COMMIT"
  ],
  "allowed_write_tables": [
    "n6_user_strategy_selection_revision",
    "n6_user_strategy_selection_item"
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
    "reviewed_n6_trade_date_consensus_verified",
    "reviewed_n6_latest_complete_single_batches_verified",
    "reviewed_n6_projection_card_watermarks_frozen",
    "membership_asof_provenance_frozen",
    "active_predecessor_exact_verified",
    "target_scope_pending_zero_verified",
    "same_package_keys_verified",
    "previous_revision_cas_verified",
    "selection_creation_authority_owner_verified",
    "selection_creation_authority_user_isolation_verified",
    "request_id_idempotence_defined",
    "fresh_read_only_preflight_verified",
    "strategy_write_flag_stable_verified",
    "scheduled_evaluator_stable_verified",
    "virtual_executor_not_operated_verified",
    "single_transaction_atomicity_defined",
    "other_users_unchanged_verified",
    "projection_change_unchanged_verified",
    "zero_forbidden_side_effects_verified"
  ],
  "required_false_fields": [
    "all_users_requested",
    "multi_scope_requested",
    "non_current_trade_date_requested",
    "common_trade_calendar_authority_requested",
    "n1_n5_raw_table_authority_requested",
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
    "concurrent_runtime_change",
    "scope_or_hash_drift"
  ],
  "revision_activation_authorized": false,
  "rollback_requires_separate_authorization": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1:end -->

Each of the seven remaining users requires its own current-request authority,
predecessor CAS, transaction, postflight, and trace. An all-users sweep,
hard-coded revision/date, package-key change, evaluator operation, second
attempt, or any projection/change/trading/N1-N5 write returns `REJECT`.

### 4.14 V1 Retirement after Complete V2 Rollout

<!-- policy:n6_strategy_center_v1_retirement_after_all_users_v2_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_v1_retirement_after_all_users_v2_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "N6_user",
  "scope_mode": "catalog_only_v1_retirement_after_all_users_v2",
  "required_strategy_write_flag_value": "1",
  "required_catalog_transition": "v1_grandfathered_to_retired_only",
  "required_pending_count": 0,
  "required_remaining_v1_active_user_count": 0,
  "required_v2_active_for_all_activity_scopes": true,
  "required_completed_remaining_user_gate_count": 7,
  "required_evaluator_tick_observation_count": 12,
  "allowed_write_tables": ["n6_strategy_package_catalog"],
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "reviewed_n6_trade_date_consensus_verified",
    "all_activity_scopes_active_v2_verified",
    "pending_zero_verified",
    "all_user_deterministic_replay_verified",
    "cross_user_isolation_verified",
    "projection_hashes_frozen_and_verified",
    "sse_reconnect_and_correction_verified",
    "scheduled_evaluator_stable_verified",
    "rollback_contract_frozen",
    "zero_forbidden_side_effects_verified"
  ],
  "required_false_fields": [
    "any_active_v1_user_detected",
    "any_pending_revision_detected",
    "v2_projection_dependency_missing",
    "common_trade_calendar_authority_requested",
    "n1_n5_raw_table_authority_requested",
    "selection_revision_write_requested",
    "selection_item_write_requested",
    "projection_write_requested",
    "change_write_requested",
    "evaluator_operation_requested",
    "virtual_executor_operation_requested",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "real_broker_connected",
    "retry_requested",
    "concurrent_runtime_change"
  ],
  "attempts": 1,
  "retries": 0,
  "rollback_requires_separate_authorization": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_v1_retirement_after_all_users_v2_v1:end -->

V1 retirement is a final, independent catalog-only gate. It cannot run until
every active scope is V2, pending is zero, all seven remaining-user gates and
full-user replay/isolation/projection/SSE verification pass, and the evaluator
is stable. Existing revisions and historical projection/change evidence remain
immutable.

### 4.15 Strategy Center Web Runtime Decommission Exception

This independent `runtime_control` policy permits one bounded deployment of one
immutable N6 Web Release whose attested delta removes Strategy Center runtime
surfaces. It does not authorize this governance-definition session to execute
the policy.

<!-- policy:n6_strategy_center_decommission_web_runtime_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_decommission_web_runtime_v1",
  "policy_status": "ACTIVE",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "runtime_control",
  "scope_mode": "single_n6_user_web_strategy_center_decommission_release",
  "web_launch_agent_label": "com.ashare-v3.n6.user-web",
  "evaluator_launch_agent_label": "com.ashare-v3.n6.strategy-center-evaluator-v1",
  "virtual_executor_launch_agent_label": "com.ashare-v3.n6.virtual-executor-v1",
  "web_strategy_write_flag": "ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED",
  "web_strategy_write_flag_before": "0",
  "web_strategy_write_flag_after": "0",
  "web_strategy_write_flag_rollback": "0",
  "target_release_name_pattern": "^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$",
  "required_target_release_delta": "removes_all_strategy_center_web_routes_ui_sse_functions_and_runtime_references",
  "web_teardown_timeout_seconds": 30,
  "web_readiness_timeout_seconds": 60,
  "web_stability_window_seconds": 30,
  "required_operation_counts": {
    "web_primary_bootout_attempts": 1,
    "web_primary_bootstrap_attempts": 1,
    "evaluator_operation_attempts": 0,
    "evaluator_restore_attempts": 0,
    "virtual_executor_operation_attempts": 0,
    "database_connection_attempts": 0,
    "database_mutation_attempts": 0,
    "other_service_operation_attempts": 0
  },
  "maximum_conditional_rollback_counts": {
    "web_rollback_bootout_attempts": 1,
    "web_rollback_bootstrap_attempts": 1
  },
  "allowed_runtime_operations": [
    "exact_web_bootout_once",
    "exact_web_bootstrap_once",
    "exact_web_readiness_probe",
    "exact_web_stability_observation",
    "conditional_exact_web_restore_frozen_source_release",
    "post_stability_evaluator_artifact_archive"
  ],
  "evaluator_archive_contract": {
    "archive_after_web_stability_only": true,
    "allowed_artifact_classes": ["plist", "state", "log", "history"],
    "archive_root_must_be_new": true,
    "archive_root_must_be_read_only": true,
    "archive_manifest_and_hashes_required": true,
    "evaluator_job_and_pid_must_remain_absent": true,
    "evaluator_restore_forbidden": true
  },
  "required_hash_fields": [
    "source_release_commit_sha",
    "source_release_tree_sha",
    "source_release_manifest_sha256",
    "source_release_filesystem_sha256",
    "target_release_commit_sha",
    "target_release_tree_sha",
    "target_release_manifest_sha256",
    "target_release_filesystem_sha256",
    "target_strategy_center_removal_diff_sha256",
    "source_plist_sha256",
    "target_plist_sha256",
    "evaluator_before_state_sha256",
    "virtual_executor_boundary_sha256"
  ],
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "source_release_frozen",
    "target_release_immutable_attestation_verified",
    "target_release_is_strict_non_regression_for_non_strategy_n6",
    "target_strategy_center_routes_absent",
    "target_strategy_center_ui_absent",
    "target_strategy_center_sse_absent",
    "target_strategy_center_runtime_references_absent",
    "web_strategy_write_zero_before_verified",
    "web_strategy_write_zero_after_verified",
    "evaluator_job_absent_before_verified",
    "evaluator_pid_absent_before_verified",
    "evaluator_job_absent_after_verified",
    "evaluator_pid_absent_after_verified",
    "virtual_executor_frozen_unchanged_verified",
    "rollback_source_release_frozen",
    "historical_artifacts_preserved",
    "governance_contract_preexisted_execution_request"
  ],
  "required_false_fields": [
    "database_access_requested",
    "database_write_requested",
    "schema_change_requested",
    "evaluator_bootstrap_requested",
    "evaluator_kickstart_requested",
    "evaluator_restore_requested",
    "virtual_executor_operation_requested",
    "other_launch_agent_operation_requested",
    "n1_n5_mutation_requested",
    "proposal_order_trade_position_cash_touched",
    "real_broker_connected",
    "canary_heartbeat_operation_requested",
    "second_primary_attempt_requested",
    "concurrent_configuration_drift_detected"
  ],
  "rollback_only_on_primary_failure": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_decommission_web_runtime_v1:end -->

### 4.16 Strategy Center Schema Archive Exception

This independent `N6_user` policy permits one transaction that isolates the six
Strategy Center core tables and their owned sequences/indexes in a new
owner-only archive schema. It is archival DDL, not deletion, and cannot be
combined with Web decommission, heartbeat work, or physical retirement.

<!-- policy:n6_strategy_center_decommission_schema_archive_v1:begin -->
```json
{
  "policy_id": "n6_strategy_center_decommission_schema_archive_v1",
  "policy_status": "ACTIVE",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "layer_role": "N6_user",
  "scope_mode": "single_transaction_six_table_owner_only_archive",
  "archive_schema": "n6_strategy_center_archive_v1",
  "retention_days": 30,
  "core_tables": [
    "n6_user_strategy_selection_revision",
    "n6_user_strategy_selection_item",
    "n6_strategy_package_catalog",
    "n6_strategy_match_projection",
    "n6_strategy_observation_projection",
    "n6_strategy_match_change"
  ],
  "owned_dependent_object_types": ["sequence", "index"],
  "archive_schema_usage_revoked_from": [
    "frozen_web_runtime_role",
    "n6_strategy_worker",
    "PUBLIC"
  ],
  "protected_objects": [
    "role:n6_strategy_worker",
    "acl:079_canonical_reviewed_view",
    "table:n6_strategy",
    "table_family:n6_ai_strategy",
    "service:virtual_executor",
    "layer:N1",
    "layer:N2",
    "layer:N3",
    "layer:N4",
    "layer:N5",
    "object_family:trading"
  ],
  "allowed_ddl_operations": [
    "create_new_owner_only_archive_schema",
    "alter_six_core_tables_set_schema",
    "alter_owned_sequences_set_schema",
    "retain_owned_indexes_with_archived_tables",
    "revoke_archive_schema_usage_from_web_worker_public",
    "drop_strategy_center_exclusive_triggers",
    "drop_strategy_center_exclusive_functions"
  ],
  "required_operation_counts": {
    "database_transactions": 1,
    "archive_schema_creations": 1,
    "core_table_moves": 6,
    "data_drop_statements": 0,
    "core_table_drop_statements": 0,
    "n6_strategy_worker_role_operations": 0,
    "reviewed_view_079_acl_operations": 0,
    "virtual_executor_operations": 0,
    "n1_n5_operations": 0,
    "trading_object_operations": 0
  },
  "required_evidence_per_table": [
    "before_row_count",
    "after_row_count",
    "before_content_hash",
    "after_content_hash",
    "before_ddl",
    "after_ddl",
    "before_acl",
    "after_acl",
    "before_dependency_inventory",
    "after_dependency_inventory"
  ],
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "web_runtime_decommission_gate_passed",
    "web_strategy_write_zero_verified",
    "evaluator_job_absent_verified",
    "evaluator_pid_absent_verified",
    "archive_schema_absent_before",
    "archive_schema_owner_is_current_database_owner",
    "archive_schema_owner_only_acl_verified",
    "all_six_tables_present_before",
    "all_owned_sequences_and_indexes_frozen",
    "strategy_center_exclusive_trigger_inventory_complete",
    "strategy_center_exclusive_function_inventory_complete",
    "per_table_evidence_complete",
    "row_counts_unchanged",
    "content_hashes_unchanged",
    "rollback_sql_hash_bound",
    "rollback_restores_original_schema_ddl_acl_dependencies",
    "rollback_valid_until_retention_deadline",
    "physical_deletion_requires_new_independent_explicit_authorization",
    "historical_documents_sql_commits_preserved",
    "governance_contract_preexisted_execution_request"
  ],
  "required_false_fields": [
    "data_drop_requested",
    "core_table_drop_requested",
    "truncate_requested",
    "row_update_delete_insert_requested",
    "n6_strategy_worker_role_change_requested",
    "reviewed_view_079_acl_change_requested",
    "base_n6_strategy_table_touched",
    "n6_ai_strategy_table_family_touched",
    "virtual_executor_operation_requested",
    "n1_n5_mutation_requested",
    "trading_object_touched",
    "web_or_other_service_operation_requested",
    "canary_heartbeat_operation_requested",
    "automatic_physical_deletion_requested",
    "combined_web_and_schema_gate_requested",
    "second_transaction_or_retry_requested"
  ],
  "physical_deletion_automatically_scheduled": false,
  "physical_deletion_before_retention_deadline_allowed": false,
  "rollback_requires_dedicated_authorization": true,
  "governance_session_cannot_execute": true
}
```
<!-- policy:n6_strategy_center_decommission_schema_archive_v1:end -->

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
  -> if and only if requested, evaluate the complete named exception policy
  -> detect ambiguity

decision gate
  -> ACCEPT: continue
  -> REJECT: stop
  -> BLOCK: stop and request missing information
  -> ESCALATE: stop and hand off to the correct gate or layer

execute only if ACCEPT
  -> perform only the approved action
  -> touch only approved files
  -> for a named exception, touch only that policy's approved resources
  -> otherwise do not introduce runtime behavior
```

## 6. Golden Rule

No execution without kernel approval.

### 4.9 N6 Immutable Release Install (Artifact-Only) Exception

The following policy permits materializing exactly one already-attested N6
immutable Release. It does not permit service rebind, LaunchAgent operations,
database access, evaluator execution, or any N1-N6 business mutation.

<!-- policy:n6_immutable_release_install_bounded_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_install_bounded_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_attested_n6_release_artifact",
  "phase_mode": "install_artifact_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": ["target_release_path", "staging_release_path"],
  "required_hash_fields": {
    "source_commit": "^[0-9a-f]{40}$",
    "source_tree": "^[0-9a-f]{40}$",
    "archive_sha256": "^[0-9a-f]{64}$",
    "manifest_sha256": "^[0-9a-f]{64}$",
    "filesystem_validation_sha256": "^[0-9a-f]{64}$",
    "attestation_sha256": "^[0-9a-f]{64}$"
  },
  "required_singleton_counts": {
    "target_release_count": 1,
    "staging_release_count": 1,
    "source_artifact_count": 1,
    "release_root_owner_write_enable_count": 1,
    "release_root_mode_restore_count": 1,
    "rename_count": 1,
    "install_attempt_count": 1,
    "retry_count": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "target_release_path_is_direct_child",
    "target_release_path_is_new",
    "staging_path_is_under_same_release_root",
    "staging_path_is_unique",
    "release_root_before_mode_0555_verified",
    "release_root_owner_group_acl_xattr_frozen",
    "temporary_release_root_mode_0755_owner_only_verified",
    "release_root_after_mode_0555_verified",
    "failure_restores_release_root_mode_defined",
    "source_artifact_is_git_archive_or_attested_materialization",
    "source_commit_tree_hashes_verified",
    "archive_manifest_filesystem_hashes_verified",
    "attestation_hash_verified",
    "target_contents_verified_before_rename",
    "target_owner_group_verified",
    "target_mode_0555_verified",
    "target_acl_xattr_verified",
    "target_no_symlink_verified",
    "target_no_unexpected_hardlink_verified",
    "existing_releases_unchanged_verified",
    "atomic_same_parent_rename_defined",
    "failure_cleanup_new_paths_only_defined",
    "rollback_does_not_delete_existing_release_defined",
    "before_after_manifest_trace_defined"
  ],
  "required_false_fields": [
    "target_release_exists_before_install",
    "existing_release_modified",
    "release_root_left_writable",
    "release_root_owner_group_acl_xattr_changed",
    "release_root_group_or_other_write_enabled",
    "multiple_release_root_mode_changes",
    "staging_outside_release_root",
    "non_atomic_copy_into_final_path",
    "partial_final_path_exposed",
    "release_content_modified_after_rename",
    "launch_agent_touched",
    "service_restarted",
    "launchctl_bootout_requested",
    "launchctl_bootstrap_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "selection_projection_change_touched",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "n1_n6_business_mutation_requested",
    "concurrent_runtime_change",
    "target_hash_drift",
    "authorization_missing",
    "multiple_targets_requested",
    "retry_requested",
    "existing_release_delete_requested"
  ],
  "allowed_mutation_resources": [
    "release_root_owner_write_mode_bit_only",
    "new_staging_release_path",
    "new_target_release_path",
    "install_manifest_artifact",
    "install_validation_artifact"
  ],
  "allowed_operations": [
    "temporarily_enable_owner_write_on_release_root",
    "materialize_from_verified_archive",
    "set_staging_modes_and_metadata",
    "validate_staging_contents",
    "atomic_rename_staging_to_new_target",
    "restore_release_root_mode_0555",
    "write_install_attestation",
    "remove_new_staging_on_failure",
    "remove_new_target_on_failed_validation"
  ],
  "release_root_mode": "0555",
  "temporary_release_root_mode": "0755",
  "required_final_file_modes": ["0444", "0555"],
  "max_rollback_cleanup_attempts": 1,
  "rollback_cleanup_new_paths_only": true,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "governance_session_cannot_execute_business_runtime": true
}
```
<!-- policy:n6_immutable_release_install_bounded_v1:end -->

<!-- policy:n6_immutable_release_install_pre_rename_validator_recovery_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_install_pre_rename_validator_recovery_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_frozen_aa6d19c_pre_rename_validator_recovery",
  "phase_mode": "recover_install_artifact_only_with_validator_capability_first",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": [
    "target_release_path",
    "staging_release_path",
    "preserved_failed_staging_path",
    "blocked_install_attestation_path",
    "blocked_install_attestation_sidecar_path",
    "source_archive_path",
    "source_manifest_path",
    "source_filesystem_validation_path",
    "source_release_content_manifest_path",
    "source_release_attestation_path",
    "validator_capability_artifact_root",
    "validator_capability_artifact_directory",
    "validator_capability_attestation_path",
    "validator_capability_attestation_sidecar_path",
    "validator_executable_path",
    "recovery_output_artifact_root",
    "recovery_output_artifact_directory",
    "recovery_validation_artifact_path",
    "recovery_install_attestation_path",
    "recovery_install_attestation_sidecar_path"
  ],
  "validator_protocol_contract": {
    "contract_version": "macos_xattr_value_validator_capability_v1",
    "executable_path": "/usr/bin/xattr",
    "environment": {
      "LC_ALL": "C"
    },
    "path_source": "frozen_release_content_manifest_tsv_fourth_field_plus_derived_directories",
    "path_source_parser": "lf_records_split_first_3_tabs_utf8_strict_path_reject_tab_cr_lf_nul_duplicate",
    "list_names_argv": [
      "/usr/bin/xattr",
      "<path>"
    ],
    "list_names_stdout": "one_expected_utf8_xattr_name_per_lf_line_no_prefix",
    "read_value_argv": [
      "/usr/bin/xattr",
      "-px",
      "<xattr_name>",
      "<path>"
    ],
    "read_value_stdout": "ascii_hex_octets_with_ascii_whitespace_only",
    "hex_normalization": "strip_ascii_whitespace_reject_nonhex_or_odd_nibbles_decode_raw_bytes",
    "relative_path_encoding": "root_empty_bytes_else_utf8_posix_relative_path",
    "record_framing": "u64be_path_len_path_u64be_name_len_name_u64be_value_len_raw_value",
    "record_order": "path_bytes_then_xattr_name_bytes",
    "fingerprint": "sha256_concatenated_length_prefixed_records",
    "mutation_operations_allowed": false,
    "unexpected_stdout_stderr_or_nonzero_exit": "stop_before_release_root_write_or_staging_creation",
    "probe_boundary": "preserved_staging_v1_read_only_with_before_after_metadata_acl_xattr_fingerprint"
  },
  "required_hash_fields": {
    "source_commit": "^aa6d19c169df3837b3115d975587686cc726b87b$",
    "source_parent": "^081bd74ae07c327452b2a1fc67bf7df3d73a4b6c$",
    "source_tree": "^e8c5b1b883304f5499c1ff399165cb1c122a38c4$",
    "source_patch_sha256": "^1c20e1ca674bdf4576c82c3f2f4a39a8103f61d556f69b260f7e2a0f0c1cf708$",
    "archive_sha256": "^40e3756f37f64a8b4e31ff259814b0240fe77bff8b379e4f9428aac307ebd841$",
    "manifest_sha256": "^8acb70c772a3472819bd78304808e23658e954a3ae000020ba41cd9b33d7c341$",
    "filesystem_validation_sha256": "^4beb0a988a2798473641d260ef09dc6bcd6e1aa8ac8fefe15599464508be11b3$",
    "release_content_manifest_sha256": "^ee7df8ca7ead0633679f9d8b6c3046788f27f99b1a5c3929db9dc4105f1b4881$",
    "attestation_sha256": "^efdeb2e4ba8244041005d402bd153b7df4de5d0803f5f026aa3e1c2f797fbdee$",
    "blocked_install_attestation_sha256": "^9594308305ff68a217d51f6071ded07e4c01892a3ed91227abea9f1586b2edf1$",
    "blocked_install_attestation_sidecar_sha256": "^a5529027670687327180be5384f13aea6cd26c20a433950562f8767693cd6945$",
    "preserved_staging_metadata_contract_sha256": "^72c6f1cae5394888bb883f78177c4bd848d9f18adb56ab155228397d958950c5$",
    "preserved_staging_xattr_fingerprint_sha256": "^d712c33be3c78b7b80b82428a9ce6a3b6d880b1ec4bd1aed71b951b3536ab7fa$",
    "release_root_provenance_value_sha256": "^29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487$",
    "existing_release_stat_fingerprint_sha256": "^e7cfcea8c1a45739339f494d1280c1a4c3c6d00e25d5ec7c8b4925da09214a70$",
    "existing_release_acl_xattr_listing_sha256": "^d480154fef8919d725298b88bddc8bd0c48285ef62aff59c01d7991c097ef29f$",
    "existing_release_xattr_value_fingerprint_sha256": "^f63a05355758ab6388b20fba818ab0b048fc653cffce18b0b009bd70b941844f$",
    "validator_capability_attestation_sha256": "^[0-9a-f]{64}$",
    "validator_capability_attestation_sidecar_recorded_sha256": "^[0-9a-f]{64}$",
    "validator_capability_attestation_sidecar_sha256": "^[0-9a-f]{64}$",
    "validator_executable_sha256": "^a4891287e560225be676dc3eb9e32f058ab55a705fc6ff0d388b6e75802d63cc$",
    "validator_capability_attestation_embedded_executable_sha256": "^[0-9a-f]{64}$",
    "validator_protocol_sha256": "^d46af344eab78629252d1dc35b3a16d0c5cf129aff35d8ce0d724626293709b4$",
    "validator_capability_attestation_embedded_protocol_sha256": "^[0-9a-f]{64}$",
    "recovery_validation_artifact_sha256": "^[0-9a-f]{64}$",
    "recovery_install_attestation_sha256": "^[0-9a-f]{64}$",
    "recovery_install_attestation_sidecar_recorded_sha256": "^[0-9a-f]{64}$",
    "recovery_install_attestation_sidecar_sha256": "^[0-9a-f]{64}$"
  },
  "required_equal_field_pairs": [
    [
      "validator_capability_attestation_sha256",
      "validator_capability_attestation_sidecar_recorded_sha256"
    ],
    [
      "validator_executable_sha256",
      "validator_capability_attestation_embedded_executable_sha256"
    ],
    [
      "validator_protocol_sha256",
      "validator_capability_attestation_embedded_protocol_sha256"
    ],
    [
      "recovery_install_attestation_sha256",
      "recovery_install_attestation_sidecar_recorded_sha256"
    ]
  ],
  "required_exact_values": {
    "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b",
    "staging_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.install-staging-v2",
    "preserved_failed_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.install-staging-v1",
    "blocked_install_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_bounded_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/install-attestation.json",
    "blocked_install_attestation_sidecar_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_bounded_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/install-attestation.sha256",
    "source_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.tar",
    "source_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.git-ls-tree.nul",
    "source_filesystem_validation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/filesystem-validation.tsv",
    "source_release_content_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/release-content-manifest.tsv",
    "source_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/release-attestation.json",
    "validator_capability_artifact_root": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_xattr_validator_capability_v1",
    "validator_capability_artifact_directory": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_xattr_validator_capability_v1/aa6d19c169df3837b3115d975587686cc726b87b",
    "validator_capability_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_xattr_validator_capability_v1/aa6d19c169df3837b3115d975587686cc726b87b/validator-capability-attestation.json",
    "validator_capability_attestation_sidecar_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_xattr_validator_capability_v1/aa6d19c169df3837b3115d975587686cc726b87b/validator-capability-attestation.sha256",
    "recovery_output_artifact_root": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_pre_rename_validator_recovery_v1",
    "recovery_output_artifact_directory": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_pre_rename_validator_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b",
    "recovery_validation_artifact_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_pre_rename_validator_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-validation.json",
    "recovery_install_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_pre_rename_validator_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-install-attestation.json",
    "recovery_install_attestation_sidecar_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_pre_rename_validator_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-install-attestation.sha256",
    "validator_capability_artifact_file_mode": "0444",
    "validator_capability_artifact_directory_mode": "0555",
    "recovery_output_artifact_file_mode": "0444",
    "recovery_output_artifact_directory_mode": "0555",
    "recovery_output_artifact_temporary_directory_mode": "0700",
    "recovery_output_file_create_flags": "O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW",
    "recovery_output_artifact_creation_stage": "finalize_after_release_root_confirmed_0555_and_selected_recovery_outcome_branch_finalized",
    "recovery_output_failure_points_covered": [
      "artifact_root_create",
      "artifact_directory_create",
      "recovery_validation_write",
      "recovery_install_attestation_write",
      "recovery_install_attestation_sidecar_write",
      "recovery_output_final_seal"
    ],
    "validator_executable_path": "/usr/bin/xattr",
    "validator_executable_device": 16777232,
    "validator_executable_inode": 1152921500312569043,
    "validator_executable_uid": 0,
    "validator_executable_gid": 0,
    "validator_executable_mode": "0755",
    "validator_executable_size": 118896,
    "validator_capability_contract_version": "macos_xattr_value_validator_capability_v1",
    "validator_protocol_canonicalization": "json_sort_keys_compact_utf8_v1",
    "prior_failure_status": "BLOCKED_PRE_RENAME_VALIDATION_TOOL_UNAVAILABLE",
    "prior_failure_stage": "staging_full_validation_before_atomic_rename",
    "prior_failure_type": "validation_tool_capability_missing",
    "prior_failure_exception": "AttributeError",
    "prior_failure_message": "module 'os' has no attribute 'listxattr'",
    "prior_validator_python": "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
    "prior_target_absent": true,
    "prior_release_root_mode_after": "0555",
    "preserved_staging_device": 16777232,
    "preserved_staging_inode": 322967321,
    "preserved_staging_uid": 501,
    "preserved_staging_gid": 20,
    "preserved_staging_mode": "0555",
    "preserved_staging_file_count": 6243,
    "preserved_staging_directory_count_including_root": 45,
    "preserved_staging_file_mode_counts": "0444:6239,0555:4",
    "preserved_staging_directory_mode_counts": "0555:45",
    "preserved_staging_writable_or_symlink_entry_count": 0,
    "preserved_staging_provenance_xattr_entry_count": 6288,
    "preserved_staging_other_xattr_entry_count": 0,
    "preserved_staging_full_content_validation_completed": false,
    "preserved_staging_xattr_fingerprint_semantics": "opaque_read_only_evidence_identity_not_new_staging_value_authority",
    "release_root_device": 16777232,
    "release_root_inode": 307341897,
    "release_root_uid": 501,
    "release_root_gid": 20,
    "release_root_mode_before_recovery": "0555",
    "new_staging_expected_file_count": 6243,
    "new_staging_expected_directory_count_including_root": 45,
    "new_staging_expected_uid": 501,
    "new_staging_expected_gid": 20,
    "new_target_expected_uid": 501,
    "new_target_expected_gid": 20,
    "new_staging_expected_file_modes": "0444:6239,0555:4",
    "new_staging_expected_directory_modes": "0555:45",
    "new_staging_xattr_path_source_file_count": 6243,
    "new_staging_xattr_path_source_file_set_sha256": "ed3e7016cc2e41ed8fee7363be4b89ea8f14ab959987447cf7cc3b3dd8741cdb",
    "new_staging_xattr_derived_directory_count_including_root": 45,
    "new_staging_xattr_closure_path_count": 6288,
    "new_staging_xattr_closure_path_set_sha256": "b77ce626022f2ade199fb1f46fc62a6a600bb81b91d8843692d69d18cb279ea6",
    "new_staging_xattr_path_source_parser_contract_version": "release_content_manifest_tsv_fourth_field_utf8_no_controls_v1",
    "new_staging_expected_xattr_record_count": 6288,
    "new_staging_expected_xattr_name": "com.apple.provenance",
    "new_staging_expected_other_xattr_record_count": 0,
    "new_staging_expected_xattr_raw_value_length": 11,
    "new_staging_expected_xattr_raw_value_sha256": "29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487",
    "new_staging_expected_xattr_canonical_fingerprint_sha256": "92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee",
    "xattr_canonical_fingerprint_contract_version": "length_prefixed_path_name_raw_value_sha256_v1",
    "atomic_rename_primitive": "renameatx_np",
    "atomic_rename_symbol_source": "process_default_libsystem_dyld_shared_cache",
    "atomic_rename_flags": "RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH",
    "atomic_rename_flag_mask_decimal": 52,
    "atomic_rename_source_dirfd": "exact_release_root_dirfd",
    "atomic_rename_target_dirfd": "same_exact_release_root_dirfd",
    "atomic_rename_path_form": "direct_child_basenames_only",
    "atomic_rename_unsupported_or_flag_rejected_behavior": "REJECT_NO_FALLBACK"
  },
  "required_singleton_counts": {
    "prior_install_attempt_count": 1,
    "prior_atomic_rename_attempt_count": 0,
    "prior_fallback_attempt_count": 0,
    "prior_retry_attempt_count": 0,
    "prior_cleanup_attempt_count": 0,
    "source_artifact_count": 1,
    "validator_capability_attestation_count": 1,
    "validator_capability_artifact_directory_create_count": 2,
    "validator_capability_generation_count": 1,
    "validator_capability_probe_count": 1,
    "validator_capability_attestation_write_count": 1,
    "validator_capability_attestation_sidecar_write_count": 1,
    "recovery_output_artifact_directory_create_count": 2,
    "recovery_validation_artifact_write_count": 1,
    "recovery_install_attestation_write_count": 1,
    "recovery_install_attestation_sidecar_write_count": 1,
    "new_staging_release_count": 1,
    "new_target_release_count": 1,
    "release_root_owner_write_enable_count": 1,
    "release_root_mode_restore_count": 1,
    "rename_count": 1,
    "renameatx_np_attempt_count": 1,
    "ordinary_rename_attempt_count": 0,
    "rename_fallback_count": 0,
    "recovery_attempt_count": 1,
    "retry_count": 0,
    "policy_fallback_count": 0,
    "preserved_staging_cleanup_count": 0,
    "second_recovery_count": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "governance_definition_gate_separate_from_recovery_execution_verified",
    "blocked_install_attestation_readable_verified",
    "blocked_install_attestation_no_duplicate_keys_verified",
    "blocked_install_attestation_hash_verified",
    "blocked_install_attestation_sidecar_hash_verified",
    "prior_failure_shape_exact_verified",
    "prior_atomic_rename_zero_verified",
    "prior_target_absent_verified",
    "prior_release_root_restored_0555_verified",
    "source_artifact_unchanged_verified",
    "source_commit_tree_patch_hashes_verified",
    "source_archive_manifest_filesystem_attestation_hashes_verified",
    "preserved_staging_exists_verified",
    "preserved_staging_exact_identity_verified",
    "preserved_staging_metadata_contract_verified",
    "preserved_staging_acl_xattr_fingerprint_verified",
    "preserved_staging_unmodified_verified",
    "preserved_staging_evidence_only_verified",
    "existing_releases_unchanged_verified",
    "validator_capability_artifact_paths_absent_before_recovery_verified",
    "validator_capability_artifact_exact_new_directories_verified",
    "validator_capability_attestation_path_absent_before_recovery_verified",
    "validator_capability_attestation_sidecar_path_absent_before_recovery_verified",
    "validator_capability_attestation_created_in_current_recovery_verified",
    "validator_capability_attestation_sidecar_created_in_current_recovery_verified",
    "validator_capability_probe_completed_before_attestation_write_verified",
    "validator_capability_attestation_sha_bound_verified",
    "validator_capability_attestation_hash_verified",
    "validator_capability_attestation_sidecar_binding_verified",
    "validator_capability_attestation_no_duplicate_keys_verified",
    "validator_capability_attestation_and_sidecar_frozen_before_root_write_verified",
    "validator_capability_attestation_and_sidecar_unchanged_after_recovery_verified",
    "validator_capability_artifacts_sealed_0444_directories_0555_before_root_write_verified",
    "validator_capability_failure_preserves_sealed_artifacts_before_stop_defined",
    "validator_executable_hash_verified",
    "validator_executable_identity_verified",
    "validator_protocol_hash_verified",
    "validator_lists_xattr_names_and_values_verified",
    "validator_fails_closed_on_unsupported_capability_verified",
    "validator_does_not_mutate_xattr_acl_mode_verified",
    "validator_capability_phase_completed_before_release_root_write_verified",
    "validator_capability_phase_completed_before_new_staging_creation_verified",
    "validator_capability_failure_stops_before_release_root_write_or_staging_creation_defined",
    "validator_capability_failure_finalizes_sealed_recovery_output_before_stop_defined",
    "recovery_output_artifact_paths_absent_before_recovery_verified",
    "recovery_output_artifact_exact_new_directories_verified",
    "recovery_output_artifact_hashes_verified",
    "recovery_output_artifact_no_duplicate_keys_verified",
    "recovery_install_attestation_sidecar_binding_verified",
    "recovery_output_artifact_creation_deferred_until_release_root_confirmed_0555_and_selected_recovery_outcome_branch_finalized_verified",
    "recovery_output_files_created_exclusive_nofollow_verified",
    "recovery_output_artifacts_sealed_0444_directories_0555_verified",
    "recovery_output_failure_path_seals_created_files_0444_directories_0555_defined",
    "recovery_output_failure_path_records_partial_outcome_identity_hash_defined",
    "recovery_output_failure_preserves_paths_as_evidence_defined",
    "recovery_install_attestation_status_matches_outcome_verified",
    "target_release_path_is_direct_child",
    "target_release_path_is_new",
    "staging_path_is_under_same_release_root",
    "staging_path_is_unique",
    "staging_path_is_new",
    "staging_path_differs_from_preserved_staging",
    "release_root_before_mode_0555_verified",
    "release_root_owner_group_acl_xattr_frozen",
    "temporary_release_root_mode_0755_owner_only_verified",
    "release_root_after_mode_0555_verified",
    "release_root_restored_0555_before_target_postflight_verified",
    "release_root_restored_0555_before_recovery_attestation_write_verified",
    "failure_restores_release_root_mode_defined",
    "new_staging_materialized_from_verified_archive",
    "new_staging_owner_group_501_20_verified",
    "new_staging_full_blob_path_mode_acl_xattr_value_validation_verified",
    "new_staging_xattr_path_set_matches_release_content_manifest_and_derived_directories_verified",
    "new_staging_xattr_record_count_verified",
    "new_staging_xattr_only_expected_name_verified",
    "new_staging_xattr_every_raw_value_sha256_verified",
    "new_staging_xattr_canonical_fingerprint_verified",
    "new_staging_xattr_parser_and_record_framing_lossless_verified",
    "new_staging_contents_verified_before_rename",
    "target_contents_verified_after_rename",
    "target_owner_group_verified_after_rename",
    "target_owner_group_501_20_verified_after_rename",
    "target_mode_0555_verified_after_rename",
    "target_acl_xattr_verified_after_rename",
    "target_no_symlink_verified_after_rename",
    "target_no_unexpected_hardlink_verified_after_rename",
    "atomic_same_parent_rename_defined",
    "renameatx_np_symbol_resolved_verified",
    "renameatx_np_exact_flags_verified",
    "release_root_dirfd_opened_nofollow_verified",
    "release_root_dirfd_fstat_identity_verified",
    "rename_source_target_direct_child_basenames_verified",
    "target_absence_rechecked_immediately_before_renameatx_np_verified",
    "rename_excl_prevents_overwrite_at_syscall_verified",
    "rename_nofollow_and_beneath_boundaries_verified",
    "new_staging_failure_path_recursive_seal_0444_0555_defined",
    "new_staging_failure_path_identity_metadata_attestation_defined",
    "post_rename_failure_preserves_immutable_target_evidence_defined",
    "recovery_failure_preserves_new_paths_for_evidence_defined",
    "before_after_recovery_trace_defined"
  ],
  "required_false_fields": [
    "current_request_is_policy_definition_gate",
    "recovery_output_artifact_path_preexisted",
    "recovery_output_artifact_overwrite_requested",
    "recovery_output_artifact_or_sidecar_drift",
    "recovery_output_artifact_created_before_release_root_confirmed_0555_or_selected_recovery_outcome_branch_finalized",
    "nonexclusive_recovery_output_file_create_requested",
    "recovery_output_failure_cleanup_requested",
    "failure_returns_with_writable_or_unattested_recovery_output_artifact",
    "validator_capability_attestation_preexisted",
    "validator_capability_attestation_sidecar_preexisted",
    "validator_capability_artifact_path_reuse_requested",
    "validator_capability_attestation_overwrite_requested",
    "validator_capability_attestation_sidecar_overwrite_requested",
    "validator_capability_attestation_or_sidecar_drift",
    "release_root_write_before_validator_capability_pass",
    "staging_creation_before_validator_capability_pass",
    "validator_uses_missing_os_listxattr_api",
    "validator_capability_partial",
    "target_release_exists_before_recovery",
    "preserved_staging_reused",
    "preserved_staging_modified",
    "preserved_staging_renamed",
    "preserved_staging_deleted",
    "preserved_staging_cleanup_requested",
    "preserved_staging_metadata_touched",
    "source_drift",
    "existing_release_modified",
    "existing_release_delete_requested",
    "release_root_left_writable",
    "release_root_owner_group_acl_xattr_changed",
    "release_root_group_or_other_write_enabled",
    "multiple_release_root_mode_changes",
    "target_postflight_or_attestation_before_release_root_restore",
    "staging_outside_release_root",
    "staging_preexisted",
    "new_staging_reused",
    "new_staging_or_target_owner_group_drift",
    "new_staging_xattr_name_count_or_value_drift",
    "new_staging_xattr_parser_ambiguity_or_loss",
    "failure_returns_with_writable_new_staging",
    "post_rename_failure_target_modified_or_deleted",
    "ordinary_rename_requested",
    "rename_replace_or_overwrite_semantics_requested",
    "renameatx_np_missing_flag_or_fallback_requested",
    "renameatx_np_absolute_or_parent_traversal_path_requested",
    "non_atomic_copy_into_final_path",
    "partial_final_path_exposed",
    "release_content_modified_after_rename",
    "automatic_retry_requested",
    "second_recovery_requested",
    "policy_fallback_requested",
    "eacces_retry_policy_requested",
    "host_remediation_policy_requested",
    "privileged_helper_requested",
    "new_staging_cleanup_requested",
    "launch_agent_touched",
    "service_restarted",
    "launchctl_bootout_requested",
    "launchctl_bootstrap_requested",
    "port_operation_requested",
    "git_operation_requested",
    "test_execution_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "selection_projection_change_touched",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "n1_n6_business_mutation_requested",
    "concurrent_runtime_change",
    "authorization_missing",
    "multiple_targets_requested"
  ],
  "allowed_mutation_resources": [
    "validator_capability_artifact_root",
    "validator_capability_artifact_directory",
    "validator_capability_attestation_path",
    "validator_capability_attestation_sidecar_path",
    "release_root_owner_write_mode_bit_only",
    "new_staging_v2_path",
    "new_target_release_path",
    "recovery_output_artifact_root",
    "recovery_output_artifact_directory",
    "recovery_validation_artifact_path",
    "recovery_install_attestation_path",
    "recovery_install_attestation_sidecar_path"
  ],
  "allowed_operations": [
    "read_and_verify_frozen_failure_evidence",
    "create_exact_validator_capability_artifact_directories",
    "probe_readonly_xattr_name_and_value_capability",
    "generate_macos_xattr_validator_capability_attestation",
    "hash_and_write_validator_capability_attestation_sidecar",
    "seal_validator_capability_artifacts_0444_0555",
    "verify_validator_capability_before_release_root_write",
    "temporarily_enable_owner_write_on_release_root",
    "materialize_new_staging_v2_from_verified_archive",
    "set_new_staging_v2_modes_and_metadata",
    "validate_new_staging_v2_blob_path_mode_acl_xattr_values",
    "seal_and_attest_incomplete_new_staging_v2_on_failure",
    "atomic_renameatx_np_excl_nofollow_beneath_new_staging_v2_to_new_target",
    "restore_release_root_mode_0555",
    "verify_new_target_after_atomic_rename",
    "attest_immutable_target_on_post_rename_failure",
    "create_exact_recovery_output_artifact_directories",
    "write_exact_recovery_validation_artifact",
    "write_exact_recovery_install_attestation",
    "hash_and_write_recovery_install_attestation_sidecar",
    "seal_recovery_output_artifacts_0444_0555",
    "seal_and_attest_partial_recovery_output_artifacts_on_failure"
  ],
  "release_root_mode": "0555",
  "temporary_release_root_mode": "0755",
  "required_final_file_modes": ["0444", "0555"],
  "max_recovery_attempts": 1,
  "preserved_staging_evidence_only": true,
  "preserved_staging_cleanup_allowed": false,
  "new_staging_cleanup_allowed": false,
  "policy_fallback_allowed": false,
  "second_recovery_allowed": false,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "reject_unknown_request_fields": true,
  "governance_definition_session_can_execute_policy": false
}
```
<!-- policy:n6_immutable_release_install_pre_rename_validator_recovery_v1:end -->

<!-- policy:n6_immutable_release_install_preflight_git_violation_recovery_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_install_preflight_git_violation_recovery_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_frozen_aa6d19c_preflight_git_violation_recovery",
  "phase_mode": "recover_pre_mutation_procedural_failure_without_git_or_tests",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": [
    "session_trace_path",
    "target_release_path",
    "staging_release_path",
    "preserved_failed_staging_path",
    "source_archive_path",
    "source_manifest_path",
    "source_filesystem_validation_path",
    "source_release_content_manifest_path",
    "source_release_attestation_path",
    "validator_capability_artifact_root",
    "validator_capability_artifact_directory",
    "validator_capability_attestation_path",
    "validator_capability_attestation_sidecar_path",
    "validator_executable_path",
    "recovery_output_artifact_root",
    "recovery_output_artifact_directory",
    "recovery_validation_artifact_path",
    "recovery_install_attestation_path",
    "recovery_install_attestation_sidecar_path"
  ],
  "required_hash_fields": {
    "prior_governance_commit": "^627b7fe2a144db20fe2a040c41e9f90408418cdb$",
    "prior_governance_tree": "^40c3e286a056d969eecbbf062f7a40ea3495d60c$",
    "prior_governance_patch_sha256": "^ac6273261900fc28a582021945d4f9376bfeb136e7fdb2b2f1e09f670bb72113$",
    "prior_governance_agents_raw_sha256": "^0c653e5dcc6a03306ca8f45d10f8159fc84651ed107c1af4f87a7c8f7aea35b6$",
    "prior_policy_block_raw_sha256": "^141536c0c3b47463107ee354c95233e932f3a3bf2c422f5dbd64ee90f5ba5ce1$",
    "prior_policy_canonical_json_sha256": "^6bbcd9fd16d9028115e65c434d919dc7e1f1a2bfd7a03461737ed7c7f1abb6e5$",
    "governance_agents_raw_sha256": "^[0-9a-f]{64}$",
    "authorized_governance_agents_raw_sha256": "^[0-9a-f]{64}$",
    "governance_policy_block_raw_sha256": "^[0-9a-f]{64}$",
    "authorized_governance_policy_block_raw_sha256": "^[0-9a-f]{64}$",
    "session_turn_segment_sha256": "^844c5ab3d98d8aa75fa1e9cb4931be9bfa709672efa4ca7661c768eace709877$",
    "session_prefix_through_turn_sha256": "^f49976d6a867b7608f9621798c0306666e018d184b101f7080323188ac6d4149$",
    "session_task_started_raw_line_sha256": "^75775ebfb6173aa10cde0325cc0ac993e830062c08d7f8ac4f856712fd5f3247$",
    "session_turn_context_raw_line_sha256": "^7eb660f51461358da2d36131d96b16b6906119c27caced6f4f0d6960557c4c0e$",
    "session_user_message_raw_line_sha256": "^77de9096e288ced612a6df374a034ae21b5f9f2069aa4216f2c8ef6e11cf0e61$",
    "git_tool_call_arguments_sha256": "^a01c7fd0e9090f6ba7e3a5d0bebca2afb68852b91e7e441ee02b111590f0840e$",
    "git_tool_call_raw_line_sha256": "^fb52fa96aa59f911e538e626daaa026a1e8f0e5ff01cbd26f9381d8e55c0d5a9$",
    "git_tool_output_sha256": "^09489751e4206e6ae588563526bda169bbfe1d76d3e1526e9ce8243f0adf2c39$",
    "git_tool_output_raw_line_sha256": "^60873c080fdd05399dec77373213e038fa352060f2911a1431554767868074aa$",
    "fail_closed_message_raw_line_sha256": "^d1be1cef2b2d8dd5db075bceea7936b9622321f17ad8b48f7265b2cdac90bf1c$",
    "filesystem_postcheck_arguments_sha256": "^2fdbe12ce5cf526df63d914b807e188e69a951f11a75d0cbe96c8de616021086$",
    "filesystem_postcheck_raw_line_sha256": "^a43d3f6374bf9653f0cfbe0c8c17e70388fb2fa193547ef720b1d43fd2e9a7b6$",
    "filesystem_postcheck_output_sha256": "^229726f08e8742da36adaace8e03180a2883c1e60c03647c42df24558228ff82$",
    "filesystem_postcheck_output_raw_line_sha256": "^0e559292f8bfa3cfd8a62548d0eea201f9d7ee5341f82bcdfe2b487b241005a3$",
    "final_response_raw_line_sha256": "^53b570fb4e2797738801b251e94f2795eb9efba22f46806fd4a66d9f9f4ae312$",
    "task_complete_raw_line_sha256": "^688f2b7aee6b361d355c995a18d7ba0fe987643af91fabf866715c2a48cd6aad$",
    "source_commit": "^aa6d19c169df3837b3115d975587686cc726b87b$",
    "source_tree": "^e8c5b1b883304f5499c1ff399165cb1c122a38c4$",
    "archive_sha256": "^40e3756f37f64a8b4e31ff259814b0240fe77bff8b379e4f9428aac307ebd841$",
    "manifest_sha256": "^8acb70c772a3472819bd78304808e23658e954a3ae000020ba41cd9b33d7c341$",
    "filesystem_validation_sha256": "^4beb0a988a2798473641d260ef09dc6bcd6e1aa8ac8fefe15599464508be11b3$",
    "release_content_manifest_sha256": "^ee7df8ca7ead0633679f9d8b6c3046788f27f99b1a5c3929db9dc4105f1b4881$",
    "release_attestation_sha256": "^efdeb2e4ba8244041005d402bd153b7df4de5d0803f5f026aa3e1c2f797fbdee$",
    "blocked_install_attestation_sha256": "^9594308305ff68a217d51f6071ded07e4c01892a3ed91227abea9f1586b2edf1$",
    "blocked_install_attestation_sidecar_sha256": "^a5529027670687327180be5384f13aea6cd26c20a433950562f8767693cd6945$",
    "preserved_staging_metadata_contract_sha256": "^72c6f1cae5394888bb883f78177c4bd848d9f18adb56ab155228397d958950c5$",
    "preserved_staging_xattr_canonical_fingerprint_sha256": "^92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee$",
    "validator_capability_attestation_sha256": "^[0-9a-f]{64}$",
    "validator_capability_attestation_sidecar_recorded_sha256": "^[0-9a-f]{64}$",
    "validator_executable_sha256": "^a4891287e560225be676dc3eb9e32f058ab55a705fc6ff0d388b6e75802d63cc$",
    "recovery_validation_artifact_sha256": "^[0-9a-f]{64}$",
    "recovery_install_attestation_sha256": "^[0-9a-f]{64}$",
    "recovery_install_attestation_sidecar_recorded_sha256": "^[0-9a-f]{64}$"
  },
  "required_equal_field_pairs": [
    ["governance_agents_raw_sha256", "authorized_governance_agents_raw_sha256"],
    ["governance_policy_block_raw_sha256", "authorized_governance_policy_block_raw_sha256"],
    ["validator_capability_attestation_sha256", "validator_capability_attestation_sidecar_recorded_sha256"],
    ["recovery_install_attestation_sha256", "recovery_install_attestation_sidecar_recorded_sha256"]
  ],
  "required_exact_values": {
    "prior_policy_id": "n6_immutable_release_install_pre_rename_validator_recovery_v1",
    "prior_failure_status": "BLOCKED_PRE_MUTATION",
    "prior_failure_type": "forbidden_read_only_git_preflight_operation",
    "session_trace_path": "/Users/chuanfuchen/.codex/sessions/2026/07/27/rollout-2026-07-27T22-32-51-019fa3fe-2bec-72b1-92cb-2b9bcc29a0ba.jsonl",
    "session_id": "019fa3fe-2bec-72b1-92cb-2b9bcc29a0ba",
    "turn_id": "019fa5eb-66c2-78d3-8cb4-cd5af7eaac74",
    "user_message_id": "msg_019fa5eb-66ea-7000-83b2-9cdaa2fae22f",
    "git_tool_call_item_id": "ctc_02f54ec256f3baff016a67ea774a0081918802dd98bff38020",
    "git_tool_call_id": "call_aN6OmHeGtOMFxunytY43jC8G",
    "git_tool_output_item_id": "ctco_019fa5ec-2434-7413-9b38-927dd6307533",
    "filesystem_postcheck_tool_call_item_id": "ctc_02f54ec256f3baff016a67eca7fd5c819195768caaf0aaf028",
    "filesystem_postcheck_tool_call_id": "call_dElUhZoyrdCOvJjZZRqLKsac",
    "filesystem_postcheck_output_item_id": "ctco_019fa5f4-866d-7763-9fba-b0ff3b853424",
    "session_turn_start_line": 3672,
    "session_turn_end_line_inclusive": 3833,
    "session_turn_start_byte": 21636363,
    "session_turn_end_byte_exclusive": 21989026,
    "session_turn_segment_size_bytes": 352663,
    "session_prefix_size_bytes": 21989026,
    "session_whole_file_sha_authority": "forbidden_append_drifting",
    "historical_git_subcommands": ["rev-parse", "diff", "show"],
    "historical_git_operations_read_only": true,
    "target_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b",
    "staging_release_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.install-staging-v2",
    "preserved_failed_staging_path": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track/.20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.install-staging-v1",
    "source_archive_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.tar",
    "source_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b.git-ls-tree.nul",
    "source_filesystem_validation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/filesystem-validation.tsv",
    "source_release_content_manifest_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/release-content-manifest.tsv",
    "source_release_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_build_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/release-attestation.json",
    "validator_capability_artifact_root": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_preflight_git_violation_recovery_v1_xattr_validator_capability",
    "validator_capability_artifact_directory": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_preflight_git_violation_recovery_v1_xattr_validator_capability/aa6d19c169df3837b3115d975587686cc726b87b",
    "validator_capability_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_preflight_git_violation_recovery_v1_xattr_validator_capability/aa6d19c169df3837b3115d975587686cc726b87b/validator-capability-attestation.json",
    "validator_capability_attestation_sidecar_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_preflight_git_violation_recovery_v1_xattr_validator_capability/aa6d19c169df3837b3115d975587686cc726b87b/validator-capability-attestation.sha256",
    "validator_executable_path": "/usr/bin/xattr",
    "recovery_output_artifact_root": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_preflight_git_violation_recovery_v1",
    "recovery_output_artifact_directory": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_preflight_git_violation_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b",
    "recovery_validation_artifact_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_preflight_git_violation_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-validation.json",
    "recovery_install_attestation_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_preflight_git_violation_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-install-attestation.json",
    "recovery_install_attestation_sidecar_path": "/Users/chuanfuchen/.codex/artifacts/n6_filter_center_market_state_v1_immutable_release_install_preflight_git_violation_recovery_v1/20260728_002901__aa6d19c169df3837b3115d975587686cc726b87b/recovery-install-attestation.sha256",
    "preserved_staging_device": 16777232,
    "preserved_staging_inode": 322967321,
    "preserved_staging_uid": 501,
    "preserved_staging_gid": 20,
    "preserved_staging_mode": "0555",
    "preserved_staging_file_count": 6243,
    "preserved_staging_directory_count_including_root": 45,
    "release_root_device": 16777232,
    "release_root_inode": 307341897,
    "release_root_uid": 501,
    "release_root_gid": 20,
    "release_root_mode_before_recovery": "0555",
    "expected_file_count": 6243,
    "expected_directory_count_including_root": 45,
    "expected_xattr_record_count": 6288,
    "expected_xattr_name": "com.apple.provenance",
    "expected_xattr_raw_value_sha256": "29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487",
    "expected_xattr_canonical_fingerprint_sha256": "92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee",
    "atomic_rename_primitive": "renameatx_np",
    "atomic_rename_flags": "RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH",
    "release_root_mode": "0555",
    "temporary_release_root_mode": "0755"
  },
  "required_singleton_counts": {
    "historical_tool_call_count": 20,
    "historical_function_call_count": 17,
    "historical_custom_tool_call_count": 3,
    "historical_git_tool_call_count": 1,
    "historical_git_subcommand_count": 3,
    "historical_apply_patch_call_count": 0,
    "prior_recovery_attempt_count": 1,
    "prior_capability_artifact_create_attempt_count": 0,
    "prior_recovery_artifact_create_attempt_count": 0,
    "prior_release_root_mode_change_attempt_count": 0,
    "prior_staging_v2_create_attempt_count": 0,
    "prior_atomic_rename_attempt_count": 0,
    "prior_target_create_attempt_count": 0,
    "prior_cleanup_attempt_count": 0,
    "prior_fallback_attempt_count": 0,
    "prior_runtime_operation_attempt_count": 0,
    "prior_database_operation_attempt_count": 0,
    "prior_service_operation_attempt_count": 0,
    "execution_git_operation_count": 0,
    "execution_test_execution_count": 0,
    "validator_capability_generation_count": 1,
    "new_staging_release_count": 1,
    "new_target_release_count": 1,
    "release_root_owner_write_enable_count": 1,
    "release_root_mode_restore_count": 1,
    "renameatx_np_attempt_count": 1,
    "ordinary_rename_attempt_count": 0,
    "recovery_attempt_count": 1,
    "retry_count": 0,
    "policy_fallback_count": 0,
    "preserved_staging_cleanup_count": 0,
    "second_recovery_count": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "independent_governance_review_attestation_verified",
    "governance_agents_verified_from_raw_bytes_without_git",
    "governance_policy_block_verified_from_raw_bytes_without_git",
    "session_trace_segment_verified_from_raw_bytes",
    "session_trace_prefix_verified_from_raw_bytes",
    "session_trace_unique_turn_verified",
    "complete_historical_tool_timeline_verified",
    "historical_git_operations_read_only_verified",
    "historical_git_worktree_unchanged_verified",
    "all_prior_zero_mutation_counters_verified",
    "direct_filesystem_preflight_verified",
    "release_root_0555_verified",
    "target_absent_verified",
    "staging_v2_absent_verified",
    "validator_capability_artifact_paths_absent_verified",
    "recovery_output_artifact_paths_absent_verified",
    "preserved_staging_exact_identity_verified",
    "preserved_staging_evidence_only_verified",
    "source_artifact_hashes_verified",
    "validator_capability_completed_before_root_write_or_staging_creation_verified",
    "capability_failure_finalize_a_then_stop_defined",
    "fresh_staging_v2_materialized_from_frozen_archive",
    "full_blob_path_mode_owner_acl_xattr_value_validation_verified",
    "single_release_root_owner_write_window_verified",
    "single_exclusive_same_dirfd_rename_verified",
    "release_root_restored_0555_before_postflight_verified",
    "preserved_staging_unmodified_verified",
    "no_git_or_tests_in_execution_verified",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "current_request_is_policy_definition_gate",
    "session_summary_used_as_primary_evidence",
    "append_drifting_whole_session_sha_used_as_authority",
    "git_operation_requested",
    "test_execution_requested",
    "prior_policy_reuse_requested",
    "validator_capability_bypassed",
    "target_release_exists_before_recovery",
    "staging_v2_preexisted",
    "preserved_staging_reused",
    "preserved_staging_modified",
    "preserved_staging_renamed",
    "preserved_staging_deleted",
    "preserved_staging_cleanup_requested",
    "release_root_left_writable",
    "release_root_group_or_other_write_enabled",
    "ordinary_rename_requested",
    "rename_fallback_requested",
    "automatic_retry_requested",
    "second_recovery_requested",
    "policy_fallback_requested",
    "cleanup_requested",
    "launch_agent_touched",
    "service_restarted",
    "runtime_operation_requested",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "n1_n6_business_mutation_requested",
    "trade_touched",
    "authorization_missing",
    "unknown_evidence_or_request_field_present"
  ],
  "allowed_mutation_resources": [
    "validator_capability_artifact_root",
    "validator_capability_artifact_directory",
    "validator_capability_attestation_path",
    "validator_capability_attestation_sidecar_path",
    "release_root_owner_write_mode_bit_only",
    "new_staging_v2_path",
    "new_target_release_path",
    "recovery_output_artifact_root",
    "recovery_output_artifact_directory",
    "recovery_validation_artifact_path",
    "recovery_install_attestation_path",
    "recovery_install_attestation_sidecar_path"
  ],
  "allowed_operations": [
    "verify_frozen_session_segment_and_direct_filesystem_evidence_without_git_or_tests",
    "generate_and_seal_xattr_validator_capability_attestation",
    "temporarily_enable_owner_write_on_release_root",
    "materialize_fresh_staging_v2_from_frozen_archive",
    "validate_full_blob_path_mode_owner_acl_xattr_values",
    "atomic_renameatx_np_excl_nofollow_beneath_once",
    "restore_release_root_mode_0555",
    "verify_immutable_target_postflight",
    "write_and_seal_exact_recovery_evidence"
  ],
  "release_root_mode": "0555",
  "temporary_release_root_mode": "0755",
  "required_final_file_modes": ["0444", "0555"],
  "max_recovery_attempts": 1,
  "preserved_staging_evidence_only": true,
  "preserved_staging_cleanup_allowed": false,
  "new_staging_cleanup_allowed": false,
  "policy_fallback_allowed": false,
  "git_operations_allowed": false,
  "test_execution_allowed": false,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "reject_unknown_request_fields": true,
  "governance_definition_session_can_execute_policy": false
}
```
<!-- policy:n6_immutable_release_install_preflight_git_violation_recovery_v1:end -->

<!-- policy:n4_lifecycle_deactivation_state_columns_controlled_promotion_v1:begin -->
```json
{
  "policy_id": "n4_lifecycle_deactivation_state_columns_controlled_promotion_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_n4_lifecycle_deactivation_state_columns_controlled_promotion",
  "phase_mode": "fixed_source_evidence_then_execution_time_exact_final_lineage",
  "source_evidence_mode": "verified_non_executable_source_only",
  "final_commit_binding_mode": "execution_time_exact_after_independent_n4_trigger_preparation",
  "required_hash_fields": {
    "policy_definition_parent_commit": "^8229124a7c770e10793d65f937f79dc9ab6ca42c$",
    "source_base_commit": "^8229124a7c770e10793d65f937f79dc9ab6ca42c$",
    "source_endpoint_commit": "^6d1b7a24f2f6d6fa6ef5a4d675995c943703101e$",
    "source_rollback_commit": "^a1ff8b0e0dbda579dd2cece1c5b84a10879293bc$",
    "source_base_tree": "^3261a6fe08094f6c3adfcd89ccdda06ad94fcfe0$",
    "source_endpoint_tree": "^a898686a444af254853b20d9d12df96db09aa487$",
    "source_rollback_tree": "^3261a6fe08094f6c3adfcd89ccdda06ad94fcfe0$",
    "source_combined_patch_sha256": "^7de6b1a94b08f4fa2ebc84443dd528e1a9d6f5a9c28d1ab0f7af89a938aedefe$",
    "source_rollback_patch_sha256": "^fbffe7733183d0c3234b7d6c050781c43524f551d9728fcbcb9febc87ebed777$",
    "ordinary_plist_sha256": "^7c2f996985a5fb915f0dcd228c8cdd85e42cd79824af36eb0c2f8d6be13341c8$",
    "hint_plist_sha256": "^8b7a824c23639be8c39788b835da854746e94820de0f6aad23f9b58f75c081d7$",
    "policy_definition_commit": "^[0-9a-f]{40}$",
    "policy_definition_tree": "^[0-9a-f]{40}$",
    "active_head_commit": "^[0-9a-f]{40}$",
    "final_promotion_commit_1": "^[0-9a-f]{40}$",
    "final_promotion_commit_1_parent": "^[0-9a-f]{40}$",
    "final_promotion_tip": "^[0-9a-f]{40}$",
    "final_promotion_tip_parent": "^[0-9a-f]{40}$",
    "final_promotion_tip_tree": "^[0-9a-f]{40}$",
    "final_rollback_commit": "^[0-9a-f]{40}$",
    "final_rollback_parent": "^[0-9a-f]{40}$",
    "final_rollback_tree": "^[0-9a-f]{40}$",
    "final_combined_patch_sha256": "^7de6b1a94b08f4fa2ebc84443dd528e1a9d6f5a9c28d1ab0f7af89a938aedefe$",
    "final_rollback_patch_sha256": "^fbffe7733183d0c3234b7d6c050781c43524f551d9728fcbcb9febc87ebed777$",
    "merge_target_commit": "^[0-9a-f]{40}$",
    "reported_rollback_target": "^[0-9a-f]{40}$"
  },
  "required_equal_field_pairs": [
    ["active_head_commit", "policy_definition_commit"],
    ["final_promotion_commit_1_parent", "policy_definition_commit"],
    ["final_promotion_tip_parent", "final_promotion_commit_1"],
    ["final_rollback_parent", "final_promotion_tip"],
    ["final_rollback_tree", "policy_definition_tree"],
    ["merge_target_commit", "final_promotion_tip"],
    ["reported_rollback_target", "final_rollback_commit"]
  ],
  "required_exact_values": {
    "active_checkout_path": "/Users/chuanfuchen/Documents/A股监控系统v3",
    "source_evidence_role": "verified_non_executable_source_only",
    "final_commit_authority": "independent_execution_gate_exact_freeze",
    "n4_file_allowlist": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py",
      "src/ashare_v3/trigger/provisional_projection_execute.py",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_ordinary_matcher.py",
      "tests/test_provisional_projection_execute.py",
      "tests/test_provisional_trigger_lifecycle.py"
    ],
    "final_changed_paths": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py",
      "src/ashare_v3/trigger/provisional_projection_execute.py",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_ordinary_matcher.py",
      "tests/test_provisional_projection_execute.py",
      "tests/test_provisional_trigger_lifecycle.py"
    ],
    "source_endpoint_blob_sha1_by_path": {
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md": "1cf0240a12f980be5a26fe8658059ef9f9098f4e",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py": "c3904f68cbdb3bae9ffb12612f64bb4e99fd4124",
      "src/ashare_v3/trigger/provisional_projection_execute.py": "aee7fd9d6c1d663df53d3c57d732126ca2ef2281",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py": "7266954d0f2fb30f99ffb2aaa8e2ee4590f0ffd9",
      "tests/test_provisional_ordinary_execute.py": "5f7b99f33157cb2f850a05a40b75ddb4cf4afbe4",
      "tests/test_provisional_ordinary_matcher.py": "ddb0aac9ec102657265126fd9b1d6545605ec214",
      "tests/test_provisional_projection_execute.py": "8adef86de3f9a65f8e439a07ed8225b305c0d1ab",
      "tests/test_provisional_trigger_lifecycle.py": "0579e65ffeda0e84bfa79e0c0d9339fcfa757bc4"
    },
    "final_blob_sha1_by_path": {
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md": "1cf0240a12f980be5a26fe8658059ef9f9098f4e",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py": "c3904f68cbdb3bae9ffb12612f64bb4e99fd4124",
      "src/ashare_v3/trigger/provisional_projection_execute.py": "aee7fd9d6c1d663df53d3c57d732126ca2ef2281",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py": "7266954d0f2fb30f99ffb2aaa8e2ee4590f0ffd9",
      "tests/test_provisional_ordinary_execute.py": "5f7b99f33157cb2f850a05a40b75ddb4cf4afbe4",
      "tests/test_provisional_ordinary_matcher.py": "ddb0aac9ec102657265126fd9b1d6545605ec214",
      "tests/test_provisional_projection_execute.py": "8adef86de3f9a65f8e439a07ed8225b305c0d1ab",
      "tests/test_provisional_trigger_lifecycle.py": "0579e65ffeda0e84bfa79e0c0d9339fcfa757bc4"
    },
    "launchd_labels": [
      "com.ashare-v3.n4.proof-discovery-poller",
      "com.ashare-v3.n4.proof-discovery-poller.hint"
    ],
    "plist_path_by_label": {
      "com.ashare-v3.n4.proof-discovery-poller": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.plist",
      "com.ashare-v3.n4.proof-discovery-poller.hint": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.hint.plist"
    },
    "merge_strategy": "ff-only",
    "merge_command_argv_prefix": ["git", "merge", "--ff-only"],
    "absence_wait_mode": "state_driven_no_fixed_sleep",
    "failure_action": "report_frozen_rollback_target_only"
  },
  "required_singleton_counts": {
    "source_promotion_commit_count": 2,
    "final_promotion_commit_count": 2,
    "final_rollback_commit_count": 1,
    "ff_only_merge_attempt_count": 1,
    "ordinary_bootout_attempt_count": 1,
    "hint_bootout_attempt_count": 1,
    "job_pid_child_absence_wait_count": 2,
    "ordinary_bootstrap_attempt_count": 1,
    "hint_bootstrap_attempt_count": 1,
    "kickstart_attempt_count": 0,
    "manual_execute_attempt_count": 0,
    "retry_count": 0,
    "automatic_rollback_attempt_count": 0,
    "rollback_execution_attempt_count": 0,
    "push_attempt_count": 0,
    "checkout_rebase_cherry_pick_attempt_count": 0,
    "plist_write_attempt_count": 0,
    "other_launchagent_operation_count": 0,
    "database_dml_attempt_count": 0,
    "message_queue_operation_count": 0,
    "historical_event_mutation_count": 0,
    "n2_n3_n5_n6_operation_count": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "independent_runtime_control_execution_session_verified",
    "policy_definition_parent_is_frozen_base_verified",
    "policy_definition_commit_is_current_active_head_verified",
    "policy_definition_commit_contains_exact_named_policy_verified",
    "source_evidence_commits_and_trees_verified",
    "source_patch_hashes_verified",
    "source_rollback_direct_child_and_tree_equal_base_verified",
    "final_commit_set_frozen_before_any_bootout_verified",
    "final_first_commit_direct_child_of_policy_commit_verified",
    "final_tip_direct_child_of_final_first_commit_verified",
    "final_rollback_direct_child_of_final_tip_verified",
    "final_rollback_tree_equals_policy_commit_tree_verified",
    "final_patch_hashes_equal_source_evidence_verified",
    "final_changed_paths_exact_allowlist_verified",
    "final_blobs_equal_source_endpoint_verified",
    "active_tracked_worktree_clean_verified",
    "active_index_clean_verified",
    "untracked_paths_preserved_verified",
    "exact_labels_verified",
    "original_plist_paths_and_hashes_verified",
    "ordinary_launchd_job_loaded_verified",
    "hint_launchd_job_loaded_verified",
    "ordinary_worker_and_child_idle_verified",
    "hint_worker_and_child_idle_verified",
    "both_exact_labels_booted_out_before_merge_verified",
    "job_pid_child_absence_before_merge_verified",
    "single_ff_only_merge_to_exact_final_tip_verified",
    "original_plists_only_bootstrap_verified",
    "both_exact_labels_postflight_verified",
    "failure_reports_frozen_rollback_target_without_execution_verified",
    "before_after_trace_defined"
  ],
  "required_false_fields": [
    "current_request_is_policy_definition_gate",
    "source_endpoint_used_as_execution_target",
    "source_rollback_used_as_execution_target",
    "unprepared_final_commit_sha_used",
    "dynamic_file_allowlist_requested",
    "dynamic_patch_scope_requested",
    "dynamic_plist_or_label_scope_requested",
    "active_tracked_worktree_dirty",
    "active_index_dirty",
    "plist_drift_detected",
    "worker_or_child_busy_detected",
    "merge_before_job_pid_child_absence_requested",
    "fixed_sleep_requested",
    "non_ff_merge_requested",
    "kickstart_requested",
    "manual_execute_requested",
    "retry_requested",
    "automatic_rollback_requested",
    "rollback_execution_requested",
    "push_requested",
    "checkout_rebase_or_cherry_pick_requested",
    "plist_write_requested",
    "other_launchagent_requested",
    "n2_operation_requested",
    "n3_operation_requested",
    "n5_operation_requested",
    "n6_operation_requested",
    "database_dml_requested",
    "message_or_queue_operation_requested",
    "historical_event_mutation_requested",
    "trade_operation_requested",
    "unknown_evidence_or_request_field_present"
  ],
  "allowed_mutation_resources": [
    "active_checkout_head",
    "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
    "src/ashare_v3/trigger/provisional_ordinary_execute.py",
    "src/ashare_v3/trigger/provisional_projection_execute.py",
    "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
    "tests/test_provisional_ordinary_execute.py",
    "tests/test_provisional_ordinary_matcher.py",
    "tests/test_provisional_projection_execute.py",
    "tests/test_provisional_trigger_lifecycle.py",
    "launchd_job:com.ashare-v3.n4.proof-discovery-poller",
    "launchd_job:com.ashare-v3.n4.proof-discovery-poller.hint"
  ],
  "allowed_operations": [
    "verify_fixed_source_and_execution_time_final_lineage",
    "bootout_exact_two_n4_labels_once",
    "wait_state_driven_for_exact_job_pid_child_absence",
    "git_merge_ff_only_exact_final_tip_once",
    "bootstrap_exact_two_original_plists_once",
    "verify_exact_two_n4_labels_postflight",
    "report_frozen_rollback_target_without_execution"
  ],
  "source_evidence_commits_executable": false,
  "final_commit_shas_fixed_in_policy": false,
  "execution_time_exact_final_commit_freeze_required": true,
  "git_merge_ff_only_allowed": true,
  "git_push_allowed": false,
  "rollback_execution_allowed": false,
  "plist_write_allowed": false,
  "manual_worker_execute_allowed": false,
  "reject_unknown_request_fields": true,
  "governance_definition_session_can_execute_policy": false
}
```
<!-- policy:n4_lifecycle_deactivation_state_columns_controlled_promotion_v1:end -->

<!-- policy:n4_lifecycle_inactive_mark_recovery_v1:begin -->
```json
{
  "policy_id": "n4_lifecycle_inactive_mark_recovery_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_n4_lifecycle_inactive_mark_permission_recovery",
  "policy_revision": "git_permission_failure_recovery_v2",
  "phase_mode": "one_explicit_phase_per_independent_request",
  "allowed_execution_phases": [
    "rollback_restore",
    "corrected_promotion",
    "corrected_code_only_rollback"
  ],
  "required_hash_fields": {
    "policy_definition_parent_commit": "^3786528a96f2a0489c8021fdffb528dbf88335c6$",
    "prior_policy_definition_commit": "^3786528a96f2a0489c8021fdffb528dbf88335c6$",
    "prior_policy_definition_tree": "^8a78f59a4e379258dd76be6e671a6a89195e56b3$",
    "prior_rollback_restore_commit": "^195ac3f30cbb30bfaaf971b0dc8b4bb22d279920$",
    "prior_fixed_lifecycle_commit": "^5bd53e75412540c173dc47e8c9bd58d4725d89fd$",
    "prior_typed_columns_commit": "^14786f73ac672608aeecbff2d0fff28002ced622$",
    "prior_fixed_code_rollback_commit": "^0f62f592e0af21a1d5b20a38d84ba668fc5b7850$",
    "prior_merge_failure_output_sha256": "^0865f37bfc0163ec826e3d624077bfc412de1e20761dba3c1b8e4ce36c2d7536$",
    "failed_active_commit": "^49fd0a6576d3f3f04c28c0ce65da95d6472931d7$",
    "stable_n4_commit": "^ae05d7f8c365d3d0ed807235ab124e0d4cdae28e$",
    "frozen_content_rollback_commit": "^cadbe91c1d400a803dd678710a2733ac0e0d9f92$",
    "failed_active_tree": "^ca9846a075bc42750e384131dd6d4980c475502a$",
    "stable_n4_tree": "^99bb571975da00754aa28e775f45781a42c0403e$",
    "frozen_content_rollback_tree": "^99bb571975da00754aa28e775f45781a42c0403e$",
    "frozen_content_rollback_patch_sha256": "^fbffe7733183d0c3234b7d6c050781c43524f551d9728fcbcb9febc87ebed777$",
    "ordinary_plist_sha256": "^7c2f996985a5fb915f0dcd228c8cdd85e42cd79824af36eb0c2f8d6be13341c8$",
    "hint_plist_sha256": "^8b7a824c23639be8c39788b835da854746e94820de0f6aad23f9b58f75c081d7$",
    "policy_definition_commit": "^[0-9a-f]{40}$",
    "policy_definition_tree": "^[0-9a-f]{40}$",
    "rollback_restore_commit": "^[0-9a-f]{40}$",
    "rollback_restore_parent": "^[0-9a-f]{40}$",
    "rollback_restore_tree": "^[0-9a-f]{40}$",
    "fixed_lifecycle_commit": "^[0-9a-f]{40}$",
    "fixed_lifecycle_parent": "^[0-9a-f]{40}$",
    "typed_columns_commit": "^[0-9a-f]{40}$",
    "typed_columns_parent": "^[0-9a-f]{40}$",
    "typed_columns_tree": "^[0-9a-f]{40}$",
    "fixed_code_rollback_commit": "^[0-9a-f]{40}$",
    "fixed_code_rollback_parent": "^[0-9a-f]{40}$",
    "fixed_code_rollback_tree": "^[0-9a-f]{40}$",
    "active_head_commit": "^[0-9a-f]{40}$",
    "phase_merge_target_commit": "^[0-9a-f]{40}$",
    "reported_rollback_target": "^[0-9a-f]{40}$"
  },
  "required_equal_field_pairs": [
    ["rollback_restore_parent", "policy_definition_commit"],
    ["fixed_lifecycle_parent", "rollback_restore_commit"],
    ["typed_columns_parent", "fixed_lifecycle_commit"],
    ["fixed_code_rollback_parent", "typed_columns_commit"],
    ["fixed_code_rollback_tree", "rollback_restore_tree"],
    ["reported_rollback_target", "fixed_code_rollback_commit"]
  ],
  "required_exact_values": {
    "active_checkout_path": "/Users/chuanfuchen/Documents/A股监控系统v3",
    "frozen_rollback_role": "verified_content_evidence_only",
    "failed_target_run_id": "trigger_provisional_ordinary_20260804_until_0934__realtime_action_confirmation_metric_20260804_until_0934__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1",
    "failed_identity": "stock:SH:600292",
    "failed_target_zero_write_counts": {
      "run": 0,
      "state": 0,
      "match": 0,
      "outbox": 0,
      "inbox": 0
    },
    "n4_file_allowlist": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py",
      "src/ashare_v3/trigger/provisional_projection_execute.py",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_ordinary_matcher.py",
      "tests/test_provisional_projection_execute.py",
      "tests/test_provisional_trigger_lifecycle.py"
    ],
    "rollback_restore_changed_paths": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py",
      "src/ashare_v3/trigger/provisional_projection_execute.py",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_ordinary_matcher.py",
      "tests/test_provisional_projection_execute.py",
      "tests/test_provisional_trigger_lifecycle.py"
    ],
    "fixed_lifecycle_changed_paths": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_ordinary_matcher.py",
      "tests/test_provisional_trigger_lifecycle.py"
    ],
    "typed_columns_changed_paths": [
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py",
      "src/ashare_v3/trigger/provisional_projection_execute.py",
      "tests/test_provisional_ordinary_execute.py",
      "tests/test_provisional_projection_execute.py"
    ],
    "stable_blob_sha1_by_path": {
      "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md": "6526ca4d248dfd5611bd34a690d33ac7fe8ef588",
      "src/ashare_v3/trigger/provisional_ordinary_execute.py": "f177e23baf7c5ba5e62d70f35b2faf6a722566f4",
      "src/ashare_v3/trigger/provisional_projection_execute.py": "ba9cc2606ea7dd9b18f7765bcbc5bc787007a811",
      "src/ashare_v3/trigger/provisional_trigger_lifecycle.py": "9cce9cbb633edbb5aa8d6854a8d7422b378d8e33",
      "tests/test_provisional_ordinary_execute.py": "d897ef4e268d450aff1507f5b5f1e051f9130ddb",
      "tests/test_provisional_ordinary_matcher.py": "ed69e59036ce9d4590669dc8a36c8363c56a9b88",
      "tests/test_provisional_projection_execute.py": "94bcabbf395cfcdf154db72459ce4003c4c1568e",
      "tests/test_provisional_trigger_lifecycle.py": "62fc53d661f46f6ebd222f8dbaae5e70316771ce"
    },
    "corrected_inactive_contract": {
      "trigger_mark_candidate": "normal",
      "previous_trigger_mark_candidate_field": "previous_trigger_mark_candidate",
      "projection_30m_flag": false,
      "projection_30m_type": "none"
    },
    "allowed_trigger_mark_candidate_values": [
      "normal",
      "30m_volume",
      "30m_shrink"
    ],
    "launchd_labels": [
      "com.ashare-v3.n4.proof-discovery-poller",
      "com.ashare-v3.n4.proof-discovery-poller.hint"
    ],
    "plist_path_by_label": {
      "com.ashare-v3.n4.proof-discovery-poller": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.plist",
      "com.ashare-v3.n4.proof-discovery-poller.hint": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.proof-discovery-poller.hint.plist"
    },
    "merge_strategy": "ff-only",
    "absence_wait_mode": "state_driven_no_fixed_sleep",
    "required_natural_stability_between_restore_and_fix": "ordinary_hint_exit_0_p0_0",
    "failure_action": "report_frozen_phase_rollback_target_only",
    "prior_permission_failure": {
      "phase": "rollback_restore",
      "failure_class": "git_metadata_write_permission_denied_before_ref_or_tree_change",
      "failed_command": "git merge --ff-only 195ac3f30cbb30bfaaf971b0dc8b4bb22d279920",
      "failed_path": "/Users/chuanfuchen/Documents/A股监控系统v3/.git/ORIG_HEAD.lock",
      "active_head_before_and_after": "3786528a96f2a0489c8021fdffb528dbf88335c6",
      "zero_mutation_counts": {
        "head": 0,
        "ref": 0,
        "tree": 0,
        "index": 0,
        "tracked_file": 0,
        "database": 0,
        "message_queue": 0
      },
      "completed_operation_counts": {
        "ordinary_bootout": 1,
        "hint_bootout": 1,
        "ff_only_merge_attempt": 1,
        "ordinary_original_plist_bootstrap": 1,
        "hint_original_plist_bootstrap": 1
      }
    },
    "required_regenerated_patch_sha256_by_phase": {
      "rollback_restore": "fbffe7733183d0c3234b7d6c050781c43524f551d9728fcbcb9febc87ebed777",
      "fixed_lifecycle": "85ba1c0d22ad27d06377b90e7119c1453b66f11c7df34d41ea53e928369d425d",
      "typed_columns": "595cebff1ad4732f330b1ec81562c6a0aa08e385ab17fa172cea4e1f23dfa560",
      "fixed_code_rollback": "3011c679c47ce8ae38d386800948fa004ee0bd5046568f0bdb1c52e3bcbf72a4"
    },
    "git_write_authority_mode": "escalated_and_verified_before_first_new_bootout"
  },
  "phase_head_and_target_fields": {
    "rollback_restore": {
      "active_head_field": "policy_definition_commit",
      "merge_target_field": "rollback_restore_commit"
    },
    "corrected_promotion": {
      "active_head_field": "rollback_restore_commit",
      "merge_target_field": "typed_columns_commit"
    },
    "corrected_code_only_rollback": {
      "active_head_field": "typed_columns_commit",
      "merge_target_field": "fixed_code_rollback_commit"
    }
  },
  "phase_required_flags": {
    "rollback_restore": {
      "natural_stability_after_restore_verified": false,
      "severe_corrected_contract_failure_verified": false
    },
    "corrected_promotion": {
      "natural_stability_after_restore_verified": true,
      "severe_corrected_contract_failure_verified": false
    },
    "corrected_code_only_rollback": {
      "natural_stability_after_restore_verified": true,
      "severe_corrected_contract_failure_verified": true
    }
  },
  "required_singleton_counts": {
    "selected_phase_count": 1,
    "ff_only_merge_attempt_count": 1,
    "ordinary_bootout_attempt_count": 1,
    "hint_bootout_attempt_count": 1,
    "job_pid_child_absence_wait_count": 2,
    "ordinary_bootstrap_attempt_count": 1,
    "hint_bootstrap_attempt_count": 1,
    "prior_failed_ff_only_merge_attempt_count": 1,
    "prior_ordinary_bootout_attempt_count": 1,
    "prior_hint_bootout_attempt_count": 1,
    "prior_ordinary_bootstrap_attempt_count": 1,
    "prior_hint_bootstrap_attempt_count": 1,
    "kickstart_attempt_count": 0,
    "manual_execute_attempt_count": 0,
    "retry_count": 0,
    "automatic_phase_progression_count": 0,
    "automatic_rollback_attempt_count": 0,
    "database_dml_attempt_count": 0,
    "message_queue_operation_count": 0,
    "historical_target_mutation_count": 0,
    "schema_or_constraint_change_count": 0,
    "n2_n3_n5_n6_operation_count": 0
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "independent_runtime_control_execution_session_verified",
    "complete_post_policy_chain_frozen_before_bootout_verified",
    "direct_parent_chain_verified",
    "rollback_restore_stable_blobs_verified",
    "corrected_contract_verified",
    "fixed_code_rollback_n4_tree_equals_restore_n4_tree_verified",
    "active_tracked_worktree_clean_verified",
    "active_index_clean_verified",
    "untracked_paths_preserved_verified",
    "original_plist_paths_and_hashes_verified",
    "ordinary_worker_and_child_idle_verified",
    "hint_worker_and_child_idle_verified",
    "job_pid_child_absence_before_merge_verified",
    "single_ff_only_merge_to_phase_target_verified",
    "original_plists_only_bootstrap_verified",
    "before_after_trace_defined",
    "prior_permission_failure_evidence_verified",
    "prior_attempt_active_head_index_tree_unchanged_verified",
    "prior_original_plists_restored_verified",
    "git_write_authority_verified_before_any_new_bootout"
  ],
  "required_false_fields": [
    "current_request_is_policy_definition_gate",
    "frozen_content_rollback_used_as_execution_target",
    "multiple_phases_requested",
    "automatic_phase_progression_requested",
    "automatic_rollback_requested",
    "fixed_sleep_requested",
    "non_ff_merge_requested",
    "kickstart_requested",
    "manual_execute_requested",
    "retry_requested",
    "prior_policy_execution_reused",
    "prior_failed_merge_target_used_as_execution_target",
    "non_escalated_git_merge_probe_requested",
    "prior_permission_failure_hidden_or_reclassified",
    "schema_or_constraint_change_requested",
    "event_structure_change_requested",
    "database_dml_requested",
    "message_or_queue_operation_requested",
    "historical_target_mutation_requested",
    "n2_operation_requested",
    "n3_operation_requested",
    "n5_operation_requested",
    "n6_operation_requested",
    "trade_operation_requested",
    "unknown_evidence_or_request_field_present"
  ],
  "allowed_mutation_resources": [
    "active_checkout_head",
    "docs/V3_N4_TRIGGER_LAYER_DEVELOPMENT_DESIGN.md",
    "src/ashare_v3/trigger/provisional_ordinary_execute.py",
    "src/ashare_v3/trigger/provisional_projection_execute.py",
    "src/ashare_v3/trigger/provisional_trigger_lifecycle.py",
    "tests/test_provisional_ordinary_execute.py",
    "tests/test_provisional_ordinary_matcher.py",
    "tests/test_provisional_projection_execute.py",
    "tests/test_provisional_trigger_lifecycle.py",
    "launchd_job:com.ashare-v3.n4.proof-discovery-poller",
    "launchd_job:com.ashare-v3.n4.proof-discovery-poller.hint"
  ],
  "allowed_operations_by_phase": {
    "rollback_restore": [
      "verify_prior_permission_failure_attestation",
      "verify_escalated_git_write_authority_before_bootout",
      "verify_exact_recovery_chain",
      "bootout_exact_two_n4_labels_once",
      "wait_state_driven_for_exact_job_pid_child_absence",
      "git_merge_ff_only_rollback_restore_once",
      "bootstrap_exact_two_original_plists_once",
      "verify_natural_stability_before_any_corrected_promotion"
    ],
    "corrected_promotion": [
      "verify_prior_permission_failure_attestation",
      "verify_escalated_git_write_authority_before_bootout",
      "verify_exact_recovery_chain_and_natural_stability",
      "bootout_exact_two_n4_labels_once",
      "wait_state_driven_for_exact_job_pid_child_absence",
      "git_merge_ff_only_corrected_tip_once",
      "bootstrap_exact_two_original_plists_once",
      "wait_for_natural_corrected_acceptance"
    ],
    "corrected_code_only_rollback": [
      "verify_prior_permission_failure_attestation",
      "verify_escalated_git_write_authority_before_bootout",
      "verify_exact_recovery_chain_and_severe_failure",
      "bootout_exact_two_n4_labels_once",
      "wait_state_driven_for_exact_job_pid_child_absence",
      "git_merge_ff_only_fixed_code_rollback_once",
      "bootstrap_exact_two_original_plists_once",
      "verify_restored_n4_tree"
    ]
  },
  "frozen_content_rollback_commit_executable": false,
  "prior_failed_merge_target_commit_executable": false,
  "phase_combination_allowed": false,
  "automatic_phase_progression_allowed": false,
  "automatic_rollback_allowed": false,
  "schema_or_constraint_change_allowed": false,
  "historical_target_replay_or_mutation_allowed": false,
  "git_merge_ff_only_allowed": true,
  "reject_unknown_request_fields": true,
  "governance_definition_session_can_execute_policy": false
}
```
<!-- policy:n4_lifecycle_inactive_mark_recovery_v1:end -->

<!-- policy:n6_immutable_release_install_eacces_retry_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_install_eacces_retry_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_attested_n6_release_eacces_retry",
  "phase_mode": "retry_install_artifact_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": ["target_release_path", "staging_release_path", "prior_failed_staging_path"],
  "required_hash_fields": {
    "source_commit": "^[0-9a-f]{40}$",
    "source_tree": "^[0-9a-f]{40}$",
    "archive_sha256": "^[0-9a-f]{64}$",
    "manifest_sha256": "^[0-9a-f]{64}$",
    "filesystem_validation_sha256": "^[0-9a-f]{64}$",
    "attestation_sha256": "^[0-9a-f]{64}$",
    "prior_failure_trace_sha256": "^[0-9a-f]{64}$"
  },
  "required_singleton_counts": {
    "prior_eacces_rename_failure_count": 1,
    "prior_install_attempt_count": 1,
    "new_staging_release_count": 1,
    "new_target_release_count": 1,
    "release_root_owner_write_enable_count": 1,
    "release_root_mode_restore_count": 1,
    "staging_root_owner_write_enable_count": 1,
    "staging_root_mode_restore_count": 1,
    "rename_count": 1,
    "install_attempt_count": 1,
    "retry_count": 1
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "prior_failure_errno_eacces_verified",
    "prior_failure_target_absent_verified",
    "prior_failure_no_attestation_verified",
    "prior_failure_release_root_restored_0555_verified",
    "prior_failed_staging_exists_and_is_immutable_verified",
    "prior_failed_staging_unmodified_verified",
    "target_release_path_is_direct_child",
    "target_release_path_is_new",
    "staging_path_is_under_same_release_root",
    "staging_path_is_unique",
    "staging_path_differs_from_prior_failed_staging",
    "release_root_before_mode_0555_verified",
    "release_root_owner_group_acl_xattr_frozen",
    "temporary_release_root_mode_0755_owner_only_verified",
    "release_root_after_mode_0555_verified",
    "staging_root_before_mode_0555_verified",
    "temporary_staging_root_mode_0755_owner_only_verified",
    "staging_root_after_mode_0555_verified",
    "source_artifact_is_git_archive_or_attested_materialization",
    "source_commit_tree_hashes_verified",
    "archive_manifest_filesystem_hashes_verified",
    "attestation_hash_verified",
    "target_contents_verified_before_rename",
    "target_owner_group_verified",
    "target_mode_0555_verified",
    "target_acl_xattr_verified",
    "target_no_symlink_verified",
    "target_no_unexpected_hardlink_verified",
    "existing_releases_unchanged_verified",
    "atomic_same_parent_rename_defined",
    "failure_restores_all_modes_defined",
    "failure_cleanup_new_paths_only_defined",
    "rollback_does_not_delete_existing_release_defined",
    "before_after_manifest_trace_defined"
  ],
  "required_false_fields": [
    "target_release_exists_before_install",
    "prior_failed_staging_reused",
    "prior_failed_staging_modified",
    "existing_release_modified",
    "release_root_left_writable",
    "staging_root_left_writable",
    "release_root_owner_group_acl_xattr_changed",
    "staging_root_owner_group_acl_xattr_changed",
    "release_root_group_or_other_write_enabled",
    "staging_root_group_or_other_write_enabled",
    "multiple_release_root_mode_changes",
    "multiple_staging_root_mode_changes",
    "staging_outside_release_root",
    "non_atomic_copy_into_final_path",
    "partial_final_path_exposed",
    "release_content_modified_after_rename",
    "launch_agent_touched",
    "service_restarted",
    "launchctl_bootout_requested",
    "launchctl_bootstrap_requested",
    "evaluator_requested",
    "virtual_executor_requested",
    "database_connection_requested",
    "database_write_requested",
    "migration_requested",
    "selection_projection_change_touched",
    "proposal_touched",
    "order_touched",
    "trade_touched",
    "position_touched",
    "cash_touched",
    "n1_n6_business_mutation_requested",
    "concurrent_runtime_change",
    "target_hash_drift",
    "authorization_missing",
    "multiple_targets_requested",
    "second_retry_requested",
    "existing_release_delete_requested"
  ],
  "allowed_mutation_resources": [
    "release_root_owner_write_mode_bit_only",
    "new_staging_release_path",
    "new_target_release_path",
    "new_staging_root_owner_write_mode_bit_only",
    "install_manifest_artifact",
    "install_validation_artifact"
  ],
  "allowed_operations": [
    "temporarily_enable_owner_write_on_release_root",
    "materialize_from_verified_archive",
    "set_staging_modes_and_metadata",
    "validate_staging_contents",
    "temporarily_enable_owner_write_on_new_staging_root_for_rename",
    "atomic_rename_staging_to_new_target",
    "restore_target_root_mode_0555",
    "restore_release_root_mode_0555",
    "write_install_attestation",
    "remove_new_staging_on_failure",
    "remove_new_target_on_failed_validation"
  ],
  "release_root_mode": "0555",
  "temporary_release_root_mode": "0755",
  "required_final_file_modes": ["0444", "0555"],
  "max_rollback_cleanup_attempts": 1,
  "rollback_cleanup_new_paths_only": true,
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "governance_session_cannot_execute_business_runtime": true
}
```
<!-- policy:n6_immutable_release_install_eacces_retry_v1:end -->

<!-- policy:n6_immutable_release_install_host_eacces_remediation_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_install_host_eacces_remediation_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_attested_n6_release_host_eacces_remediation",
  "phase_mode": "remediate_install_artifact_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": ["target_release_path", "staging_release_path", "orphaned_staging_path", "host_eacces_trace_path"],
  "required_hash_fields": {"source_commit":"^[0-9a-f]{40}$","source_tree":"^[0-9a-f]{40}$","archive_sha256":"^[0-9a-f]{64}$","manifest_sha256":"^[0-9a-f]{64}$","filesystem_validation_sha256":"^[0-9a-f]{64}$","attestation_sha256":"^[0-9a-f]{64}$","host_eacces_trace_sha256":"^[0-9a-f]{64}$","orphaned_staging_validation_sha256":"^[0-9a-f]{64}$"},
  "required_singleton_counts": {"host_eacces_failure_count":1,"new_staging_release_count":1,"new_target_release_count":1,"release_root_owner_write_enable_count":1,"release_root_mode_restore_count":1,"staging_root_owner_write_enable_count":1,"staging_root_mode_restore_count":1,"rename_count":1,"remediation_attempt_count":1,"retry_count":0},
  "required_true_fields": ["explicit_user_authorization_current_request","host_eacces_trace_readable_verified","host_eacces_errno_verified","host_eacces_same_root_verified","host_eacces_same_parent_and_tmp_failure_verified","orphaned_staging_exists_verified","orphaned_staging_unmodified_verified","orphaned_target_absent_verified","target_release_path_is_direct_child","target_release_path_is_new","staging_path_is_under_same_release_root","staging_path_is_unique","staging_path_differs_from_orphaned_staging","release_root_before_mode_0555_verified","release_root_owner_group_acl_xattr_frozen","temporary_release_root_mode_0755_owner_only_verified","release_root_after_mode_0555_verified","staging_root_before_mode_0555_verified","temporary_staging_root_mode_0755_owner_only_verified","staging_root_after_mode_0555_verified","source_artifact_is_git_archive_or_attested_materialization","source_commit_tree_hashes_verified","archive_manifest_filesystem_hashes_verified","attestation_hash_verified","target_contents_verified_before_rename","target_owner_group_verified","target_mode_0555_verified","target_acl_xattr_verified","target_no_symlink_verified","target_no_unexpected_hardlink_verified","existing_releases_unchanged_verified","atomic_same_parent_rename_defined","failure_restores_all_modes_defined","failure_cleanup_new_paths_only_defined","before_after_manifest_trace_defined"],
  "required_false_fields": ["orphaned_staging_reused","orphaned_staging_modified","target_release_exists_before_install","existing_release_modified","release_root_left_writable","staging_root_left_writable","release_root_owner_group_acl_xattr_changed","staging_root_owner_group_acl_xattr_changed","release_root_group_or_other_write_enabled","staging_root_group_or_other_write_enabled","multiple_release_root_mode_changes","multiple_staging_root_mode_changes","staging_outside_release_root","non_atomic_copy_into_final_path","partial_final_path_exposed","release_content_modified_after_rename","launch_agent_touched","service_restarted","launchctl_bootout_requested","launchctl_bootstrap_requested","evaluator_requested","virtual_executor_requested","database_connection_requested","database_write_requested","migration_requested","selection_projection_change_touched","proposal_touched","order_touched","trade_touched","position_touched","cash_touched","n1_n6_business_mutation_requested","concurrent_runtime_change","target_hash_drift","authorization_missing","multiple_targets_requested","retry_requested","existing_release_delete_requested"],
  "allowed_mutation_resources": ["release_root_owner_write_mode_bit_only","new_staging_release_path","new_target_release_path","new_staging_root_owner_write_mode_bit_only","install_manifest_artifact","install_validation_artifact"],
  "allowed_operations": ["temporarily_enable_owner_write_on_release_root","materialize_from_verified_archive","set_staging_modes_and_metadata","validate_staging_contents","temporarily_enable_owner_write_on_new_staging_root_for_rename","atomic_rename_staging_to_new_target","restore_target_root_mode_0555","restore_release_root_mode_0555","write_install_attestation","remove_new_staging_on_failure","remove_new_target_on_failed_validation"],
  "release_root_mode":"0555","temporary_release_root_mode":"0755","required_final_file_modes":["0444","0555"],"max_rollback_cleanup_attempts":1,"rollback_cleanup_new_paths_only":true,"service_operations_allowed":false,"database_operations_allowed":false,"evaluator_operations_allowed":false,"governance_session_cannot_execute_business_runtime":true
}
```
<!-- policy:n6_immutable_release_install_host_eacces_remediation_v1:end -->

<!-- policy:n6_immutable_release_privileged_atomic_install_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_privileged_atomic_install_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_attested_n6_release_privileged_atomic_install",
  "phase_mode": "privileged_artifact_install_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "required_resource_fields": ["target_release_path", "staging_release_path", "orphaned_staging_path", "helper_path"],
  "required_hash_fields": {"source_commit":"^[0-9a-f]{40}$","source_tree":"^[0-9a-f]{40}$","archive_sha256":"^[0-9a-f]{64}$","manifest_sha256":"^[0-9a-f]{64}$","filesystem_validation_sha256":"^[0-9a-f]{64}$","attestation_sha256":"^[0-9a-f]{64}$","helper_sha256":"^[0-9a-f]{64}$","orphaned_staging_validation_sha256":"^[0-9a-f]{64}$"},
  "required_singleton_counts": {"privileged_helper_invocation_count":1,"new_staging_release_count":1,"new_target_release_count":1,"renameatx_np_count":1,"attestation_write_count":1,"retry_count":0},
  "required_true_fields": ["explicit_user_authorization_current_request","helper_signature_attested_verified","helper_sha256_verified","helper_effective_uid_root_verified","helper_fixed_release_root_verified","helper_dirfd_only_verified","helper_renameatx_np_available_verified","helper_rename_excl_verified","helper_nofollow_verified","helper_resolve_beneath_verified","staging_target_direct_children_verified","staging_immutable_verified","target_absent_verified","orphaned_staging_exists_verified","orphaned_staging_unmodified_verified","source_artifact_is_git_archive_or_attested_materialization","source_commit_tree_hashes_verified","archive_manifest_filesystem_hashes_verified","target_contents_verified_before_rename","target_mode_0555_verified","target_no_symlink_verified","target_no_unexpected_hardlink_verified","target_contents_verified_after_rename","attestation_immutable_verified","existing_releases_unchanged_verified","before_after_manifest_trace_defined"],
  "required_false_fields": ["orphaned_staging_reused","orphaned_staging_modified","target_release_exists_before_install","helper_shell_execution_requested","helper_arbitrary_path_requested","helper_recursive_copy_requested","helper_delete_requested","helper_overwrite_requested","helper_xattr_acl_chmod_requested","non_atomic_fallback_requested","partial_final_path_exposed","release_content_modified_after_rename","launch_agent_touched","service_restarted","evaluator_requested","virtual_executor_requested","database_connection_requested","database_write_requested","migration_requested","selection_projection_change_touched","proposal_touched","order_touched","trade_touched","position_touched","cash_touched","n1_n6_business_mutation_requested","concurrent_runtime_change","target_hash_drift","authorization_missing","multiple_targets_requested","retry_requested"],
  "allowed_mutation_resources": ["new_staging_release_path","new_target_release_path","install_manifest_artifact","install_validation_artifact","immutable_attestation_artifact"],
  "allowed_operations": ["materialize_from_verified_archive","set_staging_modes_and_metadata","validate_staging_contents","invoke_attested_privileged_helper_once","renameatx_np_same_parent_exclusive_nofollow_beneath","verify_target_contents","write_immutable_attestation"],
  "required_final_file_modes": ["0444", "0555"],
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "governance_session_cannot_execute_business_runtime": true
}
```
<!-- policy:n6_immutable_release_privileged_atomic_install_v1:end -->

<!-- policy:n6_immutable_release_privileged_materialize_and_install_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_privileged_materialize_and_install_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_frozen_d85df632_privileged_materialize_install",
  "phase_mode": "privileged_materialize_promote_artifact_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "frozen_archive_path": "/tmp/n6_release_d85_20260726/source.tar",
  "frozen_manifest_path": "/tmp/n6_release_d85_20260726/release-manifest.json",
  "frozen_attestation_suffix": "__d85df632-materialize-install.json",
  "required_exact_values": {"attestation_filename_suffix":"__d85df632-materialize-install.json"},
  "required_resource_fields": ["archive_path", "manifest_path", "target_release_path", "staging_release_path", "orphaned_staging_path", "materializer_helper_path"],
  "required_hash_fields": {"source_commit":"^d85df6328bde223e912dabc3bd65e16df984aa45$","source_tree":"^d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1$","archive_sha256":"^49fb8729e6648f2b15e20d699d5f0f10a97bc1cbd5935cc31f5bb90a9de859ac$","manifest_sha256":"^df698d8208977cd5a1d24c144260eb6ef0604f39be1f33f0b08af387027b6106$","filesystem_validation_sha256":"^5f600a1e1fbb7905968312387c0fc17acee09968a6dfb7d238a22d8d49152ad4$","materializer_helper_sha256":"^[0-9a-f]{64}$","orphaned_staging_validation_sha256":"^[0-9a-f]{64}$"},
  "required_singleton_counts": {"materializer_helper_invocation_count":1,"new_staging_release_count":1,"new_target_release_count":1,"archive_hash_verification_count":1,"manifest_hash_verification_count":1,"archive_entry_validation_count":1,"archive_expected_file_count":6240,"archive_expected_directory_count":45,"archive_pax_global_header_count":1,"archive_pax_extended_header_count":108,"renameatx_np_count":1,"attestation_write_count":1,"retry_count":0},
  "required_true_fields": ["explicit_user_authorization_current_request","materializer_helper_signature_attested_verified","materializer_helper_sha256_verified","materializer_helper_effective_uid_root_verified","materializer_helper_fixed_paths_verified","materializer_helper_dirfd_only_verified","archive_manifest_source_tree_filesystem_hashes_verified","staging_target_direct_children_verified","target_name_binds_source_commit_verified","target_absent_verified","orphaned_staging_exists_verified","orphaned_staging_unmodified_verified","archive_safe_paths_verified","archive_no_symlink_verified","archive_no_hardlink_verified","archive_file_mode_verified","archive_file_count_verified","archive_directory_count_verified","pax_global_comment_commit_verified","pax_extended_path_only_verified","pax_strict_record_framing_verified","staging_post_extract_verified","renameatx_np_available_verified","helper_rename_excl_verified","helper_nofollow_verified","helper_resolve_beneath_verified","target_mode_0555_verified","target_post_promote_verified","attestation_d85df632_name_verified","attestation_immutable_verified","existing_releases_unchanged_verified","before_after_manifest_trace_defined"],
  "required_false_fields": ["orphaned_staging_reused","orphaned_staging_modified","target_release_exists_before_install","former_f2b1_input_requested","frozen_input_drift_detected","archive_count_drift_detected","unknown_tar_type_requested","invalid_pax_record_detected","unexpected_pax_key_detected","attestation_legacy_name_requested","helper_shell_execution_requested","helper_arbitrary_path_requested","helper_recursive_copy_requested","helper_delete_requested","helper_overwrite_requested","helper_xattr_acl_requested","non_atomic_fallback_requested","partial_final_path_exposed","release_content_modified_after_rename","launch_agent_touched","service_restarted","evaluator_requested","virtual_executor_requested","database_connection_requested","database_write_requested","migration_requested","selection_projection_change_touched","proposal_touched","order_touched","trade_touched","position_touched","cash_touched","n1_n6_business_mutation_requested","concurrent_runtime_change","target_hash_drift","authorization_missing","multiple_targets_requested","retry_requested"],
  "allowed_mutation_resources": ["new_staging_release_path","new_target_release_path","immutable_attestation_artifact"],
  "allowed_operations": ["invoke_attested_materializer_helper_once","verify_fixed_archive_and_manifest","create_new_staging_inside_fixed_release_root","safe_archive_extract_into_new_staging","verify_archive_entry_count_mode_and_link_rules","renameatx_np_same_parent_exclusive_nofollow_beneath","verify_target_contents","write_immutable_attestation"],
  "required_final_file_modes": ["0444", "0555"],
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "governance_session_cannot_execute_business_runtime": true
}
```
<!-- policy:n6_immutable_release_privileged_materialize_and_install_v1:end -->

<!-- policy:n6_immutable_release_privileged_materialize_and_install_f67_v1:begin -->
```json
{
  "policy_id": "n6_immutable_release_privileged_materialize_and_install_f67_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_frozen_f67be0f5_privileged_materialize_install",
  "phase_mode": "privileged_materialize_promote_artifact_only",
  "release_root": "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track",
  "frozen_archive_path": "/tmp/n6_release_f67_20260727/source.tar",
  "frozen_manifest_path": "/tmp/n6_release_f67_20260727/release-manifest.json",
  "frozen_helper_path": "/usr/local/libexec/ashare-v3/n6-immutable-release-materializer-f67",
  "frozen_attestation_suffix": "__f67be0f5-materialize-install.json",
  "required_exact_values": {"attestation_filename_suffix":"__f67be0f5-materialize-install.json"},
  "required_resource_fields": ["archive_path", "manifest_path", "target_release_path", "staging_release_path", "orphaned_staging_path", "materializer_helper_path"],
  "required_hash_fields": {"source_commit":"^f67be0f538f7fdc0fe413ac98bbdc5b32a29661a$","source_tree":"^997e12766f806cedf046484463d19318fb9e4a69$","archive_sha256":"^88ea81e1fda5b1f4b6864c959e91de798bf95272184877c36b32cfd77d12fcd5$","git_ls_tree_sha256":"^e49924357270ac612e6c50da510f10a4bdd069bc983adca6928e5948342745e1$","manifest_sha256":"^4976e9510da6792274e63ce168acecb3ef4e16b893547b2b5fb813953f97c494$","filesystem_validation_sha256":"^ae6aed7d6fd3fa17ecb8362b3b28c1ed95c0113c05ac7841842797aeb4488004$","bundle_payload_sha256":"^36d1a1e874583316d63be36d0135ea07fd88dbfa5902baf63d3001f29736a9cd$","bundle_file_sha256":"^e9b8fa599a6af3d90cc7f8ba38c3299a0fa25c18ae0539a95b8ca9f218842789$","materializer_helper_sha256":"^[0-9a-f]{64}$","orphaned_staging_validation_sha256":"^[0-9a-f]{64}$"},
  "required_singleton_counts": {"materializer_helper_invocation_count":1,"new_staging_release_count":1,"new_target_release_count":1,"archive_hash_verification_count":1,"manifest_hash_verification_count":1,"git_ls_tree_hash_verification_count":1,"bundle_hash_verification_count":1,"archive_entry_validation_count":1,"archive_expected_file_count":6240,"archive_expected_directory_count":45,"archive_pax_global_header_count":1,"archive_pax_extended_header_count":108,"renameatx_np_count":1,"attestation_write_count":1,"retry_count":0},
  "required_true_fields": ["explicit_user_authorization_current_request","materializer_helper_signature_attested_verified","materializer_helper_sha256_verified","materializer_helper_effective_uid_root_verified","materializer_helper_fixed_paths_verified","materializer_helper_dirfd_only_verified","archive_manifest_source_tree_filesystem_hashes_verified","git_ls_tree_hash_verified","bundle_hashes_verified","staging_target_direct_children_verified","target_name_binds_source_commit_verified","target_absent_verified","orphaned_staging_exists_verified","orphaned_staging_unmodified_verified","archive_safe_paths_verified","archive_no_symlink_verified","archive_no_hardlink_verified","archive_file_mode_verified","archive_file_count_verified","archive_directory_count_verified","pax_global_comment_commit_verified","pax_extended_path_only_verified","pax_strict_record_framing_verified","staging_post_extract_verified","renameatx_np_available_verified","helper_rename_excl_verified","helper_nofollow_verified","helper_resolve_beneath_verified","target_mode_0555_verified","target_post_promote_verified","attestation_f67_name_verified","attestation_immutable_verified","existing_releases_unchanged_verified","before_after_manifest_trace_defined"],
  "required_false_fields": ["orphaned_staging_reused","orphaned_staging_modified","target_release_exists_before_install","non_f67_input_requested","frozen_input_drift_detected","archive_count_drift_detected","unknown_tar_type_requested","invalid_pax_record_detected","unexpected_pax_key_detected","attestation_legacy_name_requested","helper_shell_execution_requested","helper_arbitrary_path_requested","helper_recursive_copy_requested","helper_delete_requested","helper_overwrite_requested","helper_xattr_acl_requested","non_atomic_fallback_requested","partial_final_path_exposed","release_content_modified_after_rename","launch_agent_touched","service_restarted","evaluator_requested","virtual_executor_requested","database_connection_requested","database_write_requested","migration_requested","selection_projection_change_touched","proposal_touched","order_touched","trade_touched","position_touched","cash_touched","n1_n6_business_mutation_requested","concurrent_runtime_change","target_hash_drift","authorization_missing","multiple_targets_requested","retry_requested"],
  "allowed_mutation_resources": ["new_staging_release_path","new_target_release_path","immutable_attestation_artifact"],
  "allowed_operations": ["invoke_attested_f67_materializer_helper_once","verify_fixed_archive_manifest_and_bundle","create_new_staging_inside_fixed_release_root","safe_archive_extract_into_new_staging","verify_archive_entry_count_mode_link_and_pax_rules","renameatx_np_same_parent_exclusive_nofollow_beneath","verify_target_contents","write_immutable_attestation"],
  "required_final_file_modes": ["0444", "0555"],
  "service_operations_allowed": false,
  "database_operations_allowed": false,
  "evaluator_operations_allowed": false,
  "governance_session_cannot_execute_business_runtime": true
}
```
<!-- policy:n6_immutable_release_privileged_materialize_and_install_f67_v1:end -->

This d85df632-specific policy supersedes no prior policy. It is needed only because
the fixed Release root is immutable to the ordinary process: root-only V2 must
materialize the one new staging itself from the hash-bound archive, retain that
staging on failure, then promote it exactly once. It must not invoke a shell,
accept arbitrary paths or alter any existing Release.

The f67 policy is independent of the d85 helper and does not alter or supersede
it. Only the dedicated f67 helper path may consume the exact frozen f67
archive/manifest and create a fresh staging/target pair. Its fixed input,
git-ls-tree, bundle, count and PAX contract must close before one promotion;
this governance-definition session cannot install or invoke it.

This policy does not authorize the current governance session to install a
Release. A later, separately authorized execution gate must independently
attest the helper binary and may invoke it exactly once. The helper may only
rename an already sealed direct-child staging directory to one absent
direct-child target by parent-dirfd `renameatx_np` with exclusive, no-follow
and beneath-resolution flags; unsupported flags fail closed.

This policy is not a generic retry. The trace must prove a host-level `EACCES`
for a read-only staging both within the Release root and when moved to `/tmp`.
The current source's orphaned staging is evidence-only. Only a fresh staging
root gains owner-write for the single rename; every other runtime, database,
business and trading path remains `REJECT`.

This retry policy is deliberately narrower than the initial installer. It
permits exactly one fresh attempt only after a recorded `EACCES` failure. The
prior staging remains immutable evidence. The only additional transition is a
temporary owner-only `0555 -> 0755 -> 0555` change on the *new staging root*
immediately surrounding its one rename; no file content may change after
validation. Any other errno, drift, second retry, service, database, worker,
business, or trading operation returns `REJECT`.

Evaluation is fail-closed: the target must be a new direct child of the
approved Release root, staging must be unique and in the same parent, and all
hash/owner/mode/ACL/xattr/content checks must pass before one atomic rename.
An existing Release is never overwritten or deleted. A failed install may
remove only paths created by that attempt. Any service, LaunchAgent, database,
evaluator, migration, business or trading operation returns `REJECT`.

### 4.17 Runtime Hot-Cleanup Archive-Gated Disk Governance Exception

This is a `runtime_control` filesystem-governance exception. It does not
authorize the N1 archive itself, database cleanup, business runtime, or a
combined end-to-end execution. The governance task that defines or changes
this policy cannot execute any phase in the same session. Each later request
must explicitly authorize exactly one phase and must re-freeze all live
evidence before mutation.

`direct-delete-no-archive` is revoked as an admissible cleanup mode. Existing
historical reports and the currently installed plist remain evidence of prior
behavior, but cannot be used to restore the scheduler. Scheduler restoration
is legal only after its exact plist has switched to verified-archive-required
semantics and passed the restore-phase checks below.

<!-- policy:runtime_hot_cleanup_archive_gated_disk_governance_v1:begin -->
```json
{
  "policy_id": "runtime_hot_cleanup_archive_gated_disk_governance_v1",
  "accept_decision": "ACCEPT",
  "runtime_gate_decision": "ACCEPT",
  "default_runtime_execution_decision": "REJECT",
  "decision_states": ["ACCEPT", "REJECT", "BLOCK", "ESCALATE"],
  "layer_role": "runtime_control",
  "scope_mode": "single_archive_gated_disk_governance_phase",
  "allowed_phase_modes": [
    "cleanup_scheduler_quiesce",
    "archive_verified_local_reclaim",
    "time_machine_snapshot_fallback",
    "cleanup_scheduler_archive_gated_restore"
  ],
  "phase_cardinality": 1,
  "cleanup_launch_agent_label": "com.ashare-v3.runtime-hot-cleanup-keep5-daily",
  "cleanup_launch_agent_plist_path": "/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.runtime-hot-cleanup-keep5-daily.plist",
  "local_artifact_archive_root": "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
  "database_archive_root": "/Volumes/MacRaid/stock_db_archive/v3_runtime",
  "data_volume_free_target_bytes": 268435456000,
  "retention_policy": "current_trade_date_plus_previous_5_completed_trade_dates_v1",
  "trade_calendar_authority": "common_trade_calendar",
  "retained_date_count_rule": {
    "current_trade_date": 1,
    "previous_completed_trade_dates": 5,
    "maximum_total_dates": 6
  },
  "artifact_family_order": [
    "n3p_trigger_proof_contract",
    "intraday_live_current",
    "post_close_fastlane",
    "runtime_date_directory"
  ],
  "local_artifact_archive_manifest_contract": {
    "schema": "LocalArtifactArchiveManifest.v1",
    "format": "jsonl_one_regular_file_per_entry",
    "required_entry_fields": [
      "source_path",
      "trade_date",
      "artifact_family",
      "source_device",
      "source_inode",
      "source_mode",
      "source_mtime_ns",
      "source_logical_bytes",
      "source_allocated_bytes",
      "source_sha256",
      "archive_path",
      "archive_sha256",
      "reference_classification",
      "restore_proof_id"
    ],
    "required_batch_fields": [
      "batch_id",
      "manifest_sha256",
      "entry_count",
      "source_logical_bytes_total",
      "source_allocated_bytes_total",
      "archive_logical_bytes_total",
      "source_archive_hash_equality_count",
      "retained_trade_dates",
      "restore_proof_result"
    ],
    "required_restore_proof_result": "RESTORE_PROOF_PASS",
    "restore_scope": "at_least_one_complete_frozen_trade_date_per_artifact_family",
    "archive_writer_layer_role": "N1_ingestion",
    "glob_or_directory_inference_allowed": false
  },
  "archive_evidence_requirements": {
    "manifest_sha256_pattern": "^[0-9a-f]{64}$",
    "batch_summary_sha256_pattern": "^[0-9a-f]{64}$",
    "source_archive_sha256_equality_required": true,
    "entry_count_must_equal_allowlist_count": true,
    "allocated_bytes_must_equal_allowlist_total": true,
    "restore_proof_required_for_every_present_family": true,
    "archive_batch_must_be_immutable": true
  },
  "execution_revalidation_requirements": [
    "exact_source_path",
    "regular_file_not_symlink",
    "source_device",
    "source_inode",
    "source_mode",
    "source_mtime_ns",
    "source_logical_bytes",
    "source_allocated_bytes",
    "source_sha256",
    "archive_path",
    "archive_sha256",
    "source_archive_sha256_equality",
    "retained_date_exclusion",
    "active_lineage_exclusion",
    "active_writer_absence"
  ],
  "allowed_operations_by_phase": {
    "cleanup_scheduler_quiesce": [
      "freeze_git_head_worktree_plist_process_capacity_and_retained_dates",
      "launchctl_bootout_exact_cleanup_label_once",
      "state_driven_wait_for_exact_cleanup_job_and_pid_absence",
      "write_immutable_phase_evidence"
    ],
    "archive_verified_local_reclaim": [
      "verify_frozen_n1_archive_manifest_and_restore_proofs",
      "revalidate_each_exact_allowlist_entry",
      "unlink_exact_manifest_regular_file",
      "rmdir_exact_manifest_empty_directory",
      "measure_data_volume_after_each_trade_date_batch",
      "stop_when_free_target_reached",
      "write_immutable_phase_evidence"
    ],
    "time_machine_snapshot_fallback": [
      "freeze_exact_purgeable_time_machine_local_snapshots",
      "delete_exact_frozen_time_machine_local_snapshot",
      "measure_data_volume_after_each_snapshot",
      "stop_when_free_target_reached",
      "write_immutable_phase_evidence"
    ],
    "cleanup_scheduler_archive_gated_restore": [
      "verify_cleanup_plist_archive_required_semantics",
      "launchctl_bootstrap_exact_cleanup_plist_once",
      "verify_exact_cleanup_job_loaded_without_kickstart",
      "write_immutable_phase_evidence"
    ]
  },
  "phase_requirements": {
    "cleanup_scheduler_quiesce": {
      "bootout_count": 1,
      "bootstrap_count": 0,
      "cleanup_job_and_pid_absent_after_wait": true
    },
    "archive_verified_local_reclaim": {
      "bootout_count": 0,
      "bootstrap_count": 0,
      "database_delete_count": 0,
      "snapshot_delete_count": 0,
      "delete_scope": "exact_manifest_entries_only",
      "delete_batch_order": "artifact_family_order_then_oldest_trade_date",
      "stop_at_free_target": true
    },
    "time_machine_snapshot_fallback": {
      "bootout_count": 0,
      "bootstrap_count": 0,
      "database_delete_count": 0,
      "local_artifact_delete_count": 0,
      "requires_completed_local_reclaim": true,
      "requires_free_bytes_below_target": true,
      "allowed_snapshot_prefix": "com.apple.TimeMachine.",
      "required_snapshot_suffix": ".local",
      "required_snapshot_purgeable": true,
      "forbidden_snapshot_prefix": "com.apple.os.update"
    },
    "cleanup_scheduler_archive_gated_restore": {
      "bootout_count": 0,
      "bootstrap_count": 1,
      "kickstart_count": 0,
      "archive_required_configuration_verified": true,
      "natural_0100_acceptance_only": true
    }
  },
  "required_true_fields": [
    "explicit_user_authorization_current_request",
    "independent_execution_session",
    "git_head_frozen",
    "tracked_worktree_and_index_clean",
    "cleanup_plist_sha256_frozen",
    "process_snapshot_frozen",
    "data_volume_capacity_frozen",
    "macraid_capacity_frozen",
    "calendar_authoritative_retained_dates_frozen",
    "only_exact_cleanup_label_targeted",
    "immutable_phase_evidence_defined"
  ],
  "required_false_fields": [
    "policy_definition_session",
    "direct_delete_no_archive_requested",
    "direct_delete_confirmation_token_present",
    "glob_delete_requested",
    "broad_recursive_delete_requested",
    "symlink_follow_requested",
    "retained_date_overlap",
    "active_lineage_overlap",
    "active_writer_present",
    "unknown_manifest_entry_present",
    "manifest_hash_drift",
    "archive_hash_mismatch",
    "restore_proof_missing",
    "automatic_retry_requested",
    "combined_phase_requested",
    "database_connection_requested",
    "database_write_requested",
    "business_launch_agent_touched",
    "n3p_launch_agent_touched",
    "n4_launch_agent_touched",
    "n5_launch_agent_touched",
    "n6_web_launch_agent_touched",
    "release_touched",
    "codex_session_touched",
    "old_repository_touched",
    "n1_n6_business_mutation_requested",
    "outbox_inbox_checkpoint_consumption_requested",
    "worker_requested",
    "real_trade_requested"
  ],
  "forbidden_cleanup_modes": [
    "direct-delete-no-archive",
    "unverified-archive",
    "directory-inferred-delete",
    "glob-delete",
    "active-lineage-delete"
  ],
  "forbidden_snapshot_prefixes": ["com.apple.os.update"],
  "forbidden_resource_families": [
    "old_dirty_repositories",
    "immutable_releases",
    "codex_sessions",
    "postgresql_business_facts",
    "n3_n4_n5_n6_business_services"
  ],
  "retry_count": 0,
  "database_operations_allowed": false,
  "business_service_operations_allowed": false,
  "archive_execution_allowed": false,
  "manual_cleanup_replay_allowed": false,
  "governance_definition_session_execution_allowed": false
}
```
<!-- policy:runtime_hot_cleanup_archive_gated_disk_governance_v1:end -->

The four phases are intentionally independent. Quiescing the exact cleanup
job does not authorize archive creation; archive creation belongs to a later
`N1_ingestion` request. Local reclaim does not authorize PostgreSQL deletion.
Snapshot fallback is admissible only after the archived local allowlist has
been exhausted without reaching the target, and it can touch only exact frozen
purgeable Time Machine local snapshots. Restore does not authorize a manual
cleanup run: acceptance must come from subsequent natural 01:00 schedules.

### 4.18 Windows Rebuild W0 Bounded Exception

This is the only named Runtime Gate exception for Windows rebuild W0 host
governance. General Windows setup remains `REJECT`. The governance session
that defines or changes this policy cannot execute it. A later independent
`runtime_control` request must explicitly authorize exactly one phase and
satisfy every field below; missing evidence, unknown fields/resources, drift,
phase combination, retry or excess attempt returns `REJECT`.

<!-- policy:windows_rebuild_w0_bounded_v1:begin -->
```json
{
  "policy_id": "windows_rebuild_w0_bounded_v1",
  "policy_version": 10,
  "policy_state": "POLICY_READY_NOT_EXECUTED",
  "layer_role": "runtime_control",
  "scope_mode": "windows_w0_bounded_once",
  "default_runtime_execution_decision": "REJECT",
  "accept_decision": "ACCEPT",
  "governance_session_cannot_execute": true,
  "execution_session_must_be_independent": true,
  "explicit_current_request_authorization_required": true,
  "baseline": {
    "branch": "codex/windows-rebuild-v1",
    "commit": "027b03d3ca16c554491b7a21bc840acaec869571",
    "tree": "cdba2aafb8b1b87c6dc33b4af301398f8e42491d"
  },
  "phase_contract": {
    "allowed_phase_modes": [
      "w0_prepare_and_mutate",
      "w0_postgresql_virtual_identity_1639_recovery",
      "w0_postgresql_virtual_identity_22_recovery",
      "w0_python311_per_user_scope_collision_recovery",
      "w0_python311_isolated_uv_managed_install",
      "wsl_shutdown_native_control"
    ],
    "attempts_per_phase": 1,
    "automatic_retry_attempts": 0,
    "phase_combination_allowed": false,
    "phase_order": [
      "w0_prepare_and_mutate",
      "w0_postgresql_virtual_identity_1639_recovery",
      "w0_postgresql_virtual_identity_22_recovery",
      "w0_python311_per_user_scope_collision_recovery",
      "w0_python311_isolated_uv_managed_install",
      "wsl_shutdown_native_control"
    ],
    "shutdown_phase_requires_prior_result": "RESTART_REQUIRED",
    "shutdown_phase_requires_frozen_pre_shutdown_evidence": true
  },
  "exact_allowlist": {
    "scheduler_operations": [
      "export_exact_definition",
      "disable_exact_task"
    ],
    "scheduler_match_authority": [
      "TaskName",
      "TaskPath",
      "Actions"
    ],
    "scheduler_match_expression": "(?i)AshareV3|Ashare[-_ ]?V3",
    "scheduler_inventory_contract": {
      "dynamic_preflight_exact_inventory_required": true,
      "membership_authority": "current_TaskName_or_TaskPath_belongs_to_AshareV3",
      "fixed_task_count_as_execution_authority_forbidden": true,
      "historical_inventory_count_is_quality_evidence_only": true,
      "before_inventory_count_and_prior_evidence_delta_required": true,
      "export_every_frozen_definition_before_disable": true,
      "after_every_frozen_task_must_be_disabled": true
    },
    "legacy_service_name": "postgresql-x64-18",
    "legacy_service_operations": [
      "stop_once_if_running",
      "set_startup_disabled_once"
    ],
    "software_products": [
      "Git for Windows",
      "PostgreSQL 16 x64",
      "CPython 3.11 x64"
    ],
    "software_package_ids": [
      "Git.Git",
      "PostgreSQL.PostgreSQL.16",
      "Python.Python.3.11"
    ],
    "installer_version_hash_signature_must_be_frozen_before_install": true,
    "postgresql_minimum_version": "16.14",
    "postgresql_installer_package_id": "PostgreSQL.PostgreSQL.16",
    "postgresql_installer_version": "16.15-1",
    "postgresql_installer_filename": "postgresql-16.15-1-windows-x64-download-v1.exe",
    "postgresql_installer_path": "C:\\AshareV3\\staging\\installers\\postgresql-16.15-1-windows-x64-download-v1.exe",
    "postgresql_installer_url": "https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64.exe",
    "postgresql_installer_sha256": "DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2",
    "postgresql_installer_authenticode_status": "Valid",
    "postgresql_installer_signer": "EnterpriseDB Corporation",
    "postgresql_install_root": "D:\\PostgreSQL\\16",
    "postgresql_data_directory": "D:\\PostgreSQL\\16\\data",
    "postgresql_backup_staging": "D:\\PostgreSQL\\backup-staging",
    "postgresql_listen_addresses": "127.0.0.1",
    "postgresql_port": 5432,
    "postgresql_service_name": "postgresql-x64-16",
    "postgresql_transient_installer_identity": "NT AUTHORITY\\NetworkService",
    "postgresql_service_account": "NT SERVICE\\postgresql-x64-16",
    "c_directories": [
      "C:\\AshareV3\\app",
      "C:\\AshareV3\\config",
      "C:\\AshareV3\\runtime",
      "C:\\AshareV3\\logs",
      "C:\\AshareV3\\seed-inbox",
      "C:\\AshareV3\\evidence",
      "C:\\AshareV3\\staging"
    ],
    "wsl_visible_drive_after_restart": "C",
    "wsl_hidden_drive_after_restart": "D",
    "read_only_capability_checks": [
      "native_cpython_3_11_x64",
      "TdxW_process_present",
      "127.0.0.1:17709_listening"
    ]
  },
  "python311_contract": {
    "read_only_preflight_states": [
      "valid_native_3_11_x64",
      "missing_native_3_11",
      "damaged_native_3_11"
    ],
    "install_or_repair_allowed_only_for_states": [
      "missing_native_3_11",
      "damaged_native_3_11"
    ],
    "package_id": "Python.Python.3.11",
    "install_or_repair_attempts": 1,
    "automatic_retry_attempts": 0,
    "scope": "machine_wide_x64",
    "install_root": "C:\\Program Files\\Python311",
    "python_executable": "C:\\Program Files\\Python311\\python.exe",
    "version_constraint": "3.11.x",
    "secure_patch_selection": "highest_current_official_winget_3_11_x_at_preflight",
    "resolved_version_publisher_signer_sha256_frozen_before_install": true,
    "official_source_only": true,
    "verify_pe_x64": true,
    "verify_pip_available": true,
    "verify_venv_module_available": true,
    "microsoft_store_alias_forbidden": true,
    "python_3_12_or_3_14_substitution_forbidden": true,
    "source_build_forbidden": true,
    "third_party_distribution_forbidden": true,
    "business_venv_create_attempts": 0,
    "project_package_install_attempts": 0
  },
  "python311_per_user_scope_collision_recovery": {
    "policy_id": "w0_python311_per_user_scope_collision_recovery_v1",
    "phase_mode": "w0_python311_per_user_scope_collision_recovery",
    "parent_policy_commit": "9c8f80f9ca726fd00bdd30a625a4c5ed49cfddc1",
    "parent_policy_tree": "df8cbc4b01040542e2909b381014789f1d3b329b",
    "attempts": 1,
    "automatic_retry_attempts": 0,
    "operator_identity": "TDX-STOCK\\47894",
    "same_elevated_session_required": true,
    "required_fresh_read_only_pre_state": {
      "git_for_windows_version": "2.55.0.windows.5",
      "git_mutation_attempts": 0,
      "installer_path": "C:\\AshareV3\\staging\\installers\\python-3.11.9-amd64.exe",
      "installer_sha256": "5EE42C4EEE1E6B4464BB23722F90B45303F79442DF63083F05322F1785F5FDDE",
      "authenticode_status": "Valid",
      "signer": "Python Software Foundation",
      "prior_machine_wide_install_attempts": 1,
      "prior_exit_code_decimal": 1603,
      "prior_exit_code_hex": "0x643",
      "machine_python_executable_exists": false,
      "burn_bundle_scope": "PerUser",
      "burn_core_and_exe_allusers_rolled_back": true,
      "burn_dev_allusers_failure": "0x80070643",
      "burn_final_result": "0x643",
      "dev_main_engine_thread_exit": 1603,
      "old_justforme_components": "Present",
      "old_install_source_root": "C:\\Users\\47894\\AppData\\Local\\Package Cache",
      "py_launcher_reported_versions": ["Astral", "CPython 3.12.12"],
      "msiexec_or_python_installer_processes_present": false
    },
    "exact_uninstall": {
      "program": "C:\\AshareV3\\staging\\installers\\python-3.11.9-amd64.exe",
      "argument_vector": ["/uninstall", "/quiet"],
      "attempts": 1,
      "scope": "old_per_user_cpython_3_11_bundle_only",
      "acceptable_exit_codes": [0, 3010]
    },
    "required_between_steps_read_only_state": {
      "old_per_user_cpython311_bundle_and_components": "absent",
      "standalone_python_launcher_may_remain": true,
      "machine_python_executable_exists": false
    },
    "exact_machine_install": {
      "program": "C:\\AshareV3\\staging\\installers\\python-3.11.9-amd64.exe",
      "argument_vector": ["/quiet", "InstallAllUsers=1", "TargetDir=C:\\Program Files\\Python311", "PrependPath=1", "Include_pip=1", "Include_launcher=1", "InstallLauncherAllUsers=1", "Include_test=0", "Include_doc=0", "Shortcuts=0"],
      "attempts": 1,
      "acceptable_exit_codes": [0, 3010]
    },
    "required_post_state": {
      "python_executable": "C:\\Program Files\\Python311\\python.exe",
      "version": "3.11.9",
      "pe_architecture": "x64",
      "pip_available": true,
      "venv_module_available": true,
      "py_launcher_contains_exact_machine_python": true,
      "microsoft_store_alias_is_authority": false,
      "python_3_12_is_business_substitute": false
    },
    "manual_msiexec_component_operations": 0,
    "registry_delete_attempts": 0,
    "package_cache_or_directory_delete_attempts": 0,
    "cleanup_attempts": 0,
    "business_venv_create_attempts": 0,
    "project_dependency_install_attempts": 0,
    "failure_result": "BLOCKED_EVIDENCE_PRESERVED",
    "n1_handoff_allowed": false
  },
  "python311_orphaned_dependency_appsearch_cycle_recovery": {
    "policy_id": "w0_python311_orphaned_dependency_appsearch_cycle_recovery_v1",
    "phase_mode": "w0_python311_orphaned_dependency_appsearch_cycle_recovery",
    "parent_policy_commit": "de7fc6ca0b2bed6a59b2130ddba8bcd67d7065d6",
    "parent_policy_tree": "cf247378267f8f47ddaf0a82a64fe4fcc6ad3c0c",
    "policy_state": "BLOCKED_MISSING_OFFICIAL_DIRECT_MSI_CONTRACT",
    "runtime_execution_allowed": false,
    "default_runtime_execution_decision": "REJECT",
    "governance_session_cannot_execute": true,
    "maximum_attempts_after_future_reauthorization": 1,
    "currently_authorized_attempts": 0,
    "automatic_retry_attempts": 0,
    "v8_uninstall_attempts_consumed": 1,
    "v8_machine_install_attempts": 0,
    "required_frozen_evidence": {
      "installer_path": "C:\\AshareV3\\staging\\installers\\python-3.11.9-amd64.exe",
      "installer_sha256": "5EE42C4EEE1E6B4464BB23722F90B45303F79442DF63083F05322F1785F5FDDE",
      "authenticode_status": "Valid",
      "signer": "Python Software Foundation",
      "burn_log_path": "C:\\Users\\47894\\AppData\\Local\\Temp\\Python 3.11.9 (64-bit)_20260826195158.log",
      "burn_log_sha256": "466865F69D8C291FC299A0BEA36E6B1E45B116DF4D506672AB158D401E1B78B9",
      "path_log_path": "C:\\Users\\47894\\AppData\\Local\\Temp\\Python 3.11.9 (64-bit)_20260826195158_000_path_JustForMe.log",
      "path_log_sha256": "E4E8095B71B20C36DADC67384FF7FBDC989AE76FE429351E9F39615A4139CA08",
      "burn_scope": "PerUser",
      "burn_state_rsm_failure": "0x80070003",
      "path_first_execute_failure": "0x80070643",
      "path_internal_exception": "0xc00000fd",
      "final_result": "0x643",
      "product_code": "{CD925D17-C20C-441B-AAE2-4FA5B78C978F}",
      "package_code": "{A4DAA3C9-56DB-489D-9328-BC374CD2E3DE}",
      "component_id": "{38C34B30-BDE1-5985-9CB6-DD1712EEB4E2}",
      "product_name": "Python 3.11.9 Add to Path (64-bit)",
      "product_version": "3.11.9150.0",
      "assignment_type": 0,
      "local_package": "C:\\WINDOWS\\Installer\\15c7d68.msi",
      "local_package_sha256": "8A5C585D2A718BA73A4D1BB7A675DDBF56C016B6B851F2D32E07FF5DA48B1A4C",
      "install_source_exists": false,
      "old_target_exists": false,
      "machine_python_exists": false,
      "installer_or_msiexec_process_count": 0,
      "appsearch_sequence": 50,
      "appsearch_condition": "unconditional",
      "appsearch_property": "TARGETDIR",
      "drlocator_bidirectional_cycle": true,
      "remaining_hkcu_bundle": "{1da2e09b-199c-4def-9a99-93a8c1b8ddf2}",
      "remaining_msi_product_codes": [
        "{1D653E80-09B2-40AB-9530-7DF12E632F8A}",
        "{29CEC70F-9D96-472B-B6A1-AE7578376985}",
        "{425B36E9-4EA6-47B4-88C3-E798BA903188}",
        "{57AC2A86-EC99-4E9C-9FF9-15DAA88D1FAE}",
        "{9AFDC691-40E5-4B15-835F-9A524AC4672C}",
        "{A9F91BE3-1B3B-4CB4-A169-19E13DD70BEA}",
        "{CD925D17-C20C-441B-AAE2-4FA5B78C978F}",
        "{CEE03ABD-D5F9-4104-BFA5-520711B8D71F}"
      ],
      "stale_user_path_entries": [
        "C:\\Users\\47894\\AppData\\Local\\Programs\\Python\\Python311\\Scripts",
        "C:\\Users\\47894\\AppData\\Local\\Programs\\Python\\Python311"
      ]
    },
    "officially_supported_bundle_interfaces": [
      "/layout [optional target directory]",
      "/uninstall /quiet",
      "bundle name=value unattended options"
    ],
    "missing_authority": [
      "PSF-supported direct installation or repair of an internal layout MSI",
      "exact payload public properties, features, install context and command line",
      "bundle dependency-provider and registration coherence after direct payload use",
      "proof that unconditional cyclic AppSearch is bypassed without modifying the MSI"
    ],
    "runtime_mutation_allowlist": [],
    "layout_attempts": 0,
    "direct_msi_attempts": 0,
    "bundle_uninstall_attempts": 0,
    "machine_wide_install_attempts": 0,
    "manual_path_edit_attempts": 0,
    "registry_or_cache_delete_attempts": 0,
    "msi_transform_or_modification_attempts": 0,
    "business_venv_or_dependency_attempts": 0,
    "postgresql_d_wsl_scheduler_git_n1_n6_nas_mac_mutations": 0,
    "only_terminal_state": "BLOCKED_EVIDENCE_PRESERVED",
    "n1_handoff_allowed": false
  },
  "python311_isolated_uv_managed_install": {
    "policy_id": "w0_python311_isolated_uv_managed_install_v1",
    "phase_mode": "w0_python311_isolated_uv_managed_install",
    "parent_policy_commit": "95af7b50c7032a74c5a196b1acaa935e89b29f60",
    "parent_policy_tree": "337c92c3db7d1cf591b7d1143a2385d27eb1be5f",
    "attempts": 1,
    "automatic_retry_attempts": 0,
    "governance_session_cannot_execute": true,
    "execution_session_must_be_independent": true,
    "operator": {
      "account": "TDX-STOCK\\ashare-ops",
      "sid": "S-1-5-21-2072264739-3883739137-88032818-1006",
      "administrators_member": false,
      "integrity": "Medium",
      "admin_or_uac_attempts": 0
    },
    "required_fresh_read_only_pre_state": {
      "os_product_name": "Windows 10 Pro",
      "os_display_version": "25H2",
      "os_build": 26200,
      "os_ubr": 9168,
      "os_architecture": "x64",
      "git_for_windows_version": "2.55.0.windows.5",
      "asharev3_acl_authenticated_users_create_write_children": true,
      "where_uv_found": false,
      "py_launcher_result": "No installed Pythons found",
      "program_files_python311_exists": false,
      "installer_or_msiexec_process_count": 0,
      "exact_absent_targets": [
        "C:\\AshareV3\\tools",
        "C:\\AshareV3\\tools\\uv-0.12.1",
        "C:\\AshareV3\\tools\\python",
        "C:\\AshareV3\\.venv",
        "C:\\AshareV3\\staging\\installers\\uv-x86_64-pc-windows-msvc-0.12.1.zip"
      ]
    },
    "legacy_python_immutable_contract": {
      "v9_policy_id": "w0_python311_orphaned_dependency_appsearch_cycle_recovery_v1",
      "v9_runtime_decision": "REJECT",
      "old_hkcu_bundle_and_eight_msi_registrations_unchanged": true,
      "old_user_path_bytes_unchanged": true,
      "windows_installer_cache_path": "C:\\WINDOWS\\Installer\\15c7d68.msi",
      "windows_installer_cache_unchanged": true,
      "old_logs_unchanged": true,
      "old_package_cache_and_target_unchanged": true,
      "bundle_or_msi_repair_uninstall_attempts": 0
    },
    "uv_distribution": {
      "version": "0.12.1",
      "release_commit": "329541a",
      "url": "https://releases.astral.sh/github/uv/releases/download/0.12.1/uv-x86_64-pc-windows-msvc.zip",
      "zip_path": "C:\\AshareV3\\staging\\installers\\uv-x86_64-pc-windows-msvc-0.12.1.zip",
      "sha256": "8fcb0cb46e1229065e344758980924e569bef5882ef45f46fada8fb24e06b74a",
      "download_attempts": 1,
      "download_method": "Invoke-WebRequest -Uri exact_url -OutFile exact_zip_path",
      "pipe_to_iex_forbidden": true,
      "expand_method": "Expand-Archive -LiteralPath exact_zip_path -DestinationPath exact_uv_dir",
      "expand_overwrite_or_force": false,
      "install_dir": "C:\\AshareV3\\tools\\uv-0.12.1",
      "executable": "C:\\AshareV3\\tools\\uv-0.12.1\\uv.exe",
      "required_version_output": "uv 0.12.1",
      "required_pe_architecture": "x64",
      "uv_executable_sha256_frozen_after_expand": true,
      "self_update_attempts": 0
    },
    "exact_directories_created": [
      "C:\\AshareV3\\tools",
      "C:\\AshareV3\\tools\\uv-0.12.1",
      "C:\\AshareV3\\runtime\\uv-cache"
    ],
    "process_environment": {
      "UV_PYTHON_INSTALL_DIR": "C:\\AshareV3\\tools\\python",
      "UV_PYTHON_INSTALL_BIN": "0",
      "UV_PYTHON_NO_REGISTRY": "1",
      "UV_CACHE_DIR": "C:\\AshareV3\\runtime\\uv-cache",
      "UV_NO_PROGRESS": "1",
      "UV_MANAGED_PYTHON": "1"
    },
    "managed_python_install": {
      "program": "C:\\AshareV3\\tools\\uv-0.12.1\\uv.exe",
      "argument_vector": [
        "--no-progress",
        "python",
        "install",
        "--managed-python",
        "--install-dir",
        "C:\\AshareV3\\tools\\python",
        "cpython@3.11"
      ],
      "attempts": 1,
      "artifact_authority": "uv-0.12.1-built-in-python-download-metadata-and-checksum",
      "distribution_family": "python-build-standalone",
      "platform": "x86_64-pc-windows-msvc",
      "default_force_reinstall_upgrade_system_store_registry_forbidden": true,
      "python_3_12_substitution_forbidden": true,
      "failure_preserves_partial_and_stops": true
    },
    "managed_python_discovery": {
      "program": "C:\\AshareV3\\tools\\uv-0.12.1\\uv.exe",
      "argument_vector": [
        "python",
        "find",
        "--managed-python",
        "3.11"
      ],
      "result_must_be_under": "C:\\AshareV3\\tools\\python",
      "exactly_one_stable_cpython311_x64_root": true,
      "minimum_version": "3.11.9",
      "prerelease_forbidden": true,
      "freeze_fields": [
        "patch_version",
        "sys.executable",
        "sys.base_prefix",
        "struct_pointer_bits_64",
        "sys.implementation",
        "python_executable_sha256"
      ],
      "required_stdlib_modules": [
        "ssl",
        "sqlite3",
        "ctypes",
        "venv",
        "ensurepip"
      ]
    },
    "empty_venv": {
      "target": "C:\\AshareV3\\.venv",
      "command": "exact_managed_python.exe -m venv C:\\AshareV3\\.venv",
      "attempts": 1,
      "required_python": "C:\\AshareV3\\.venv\\Scripts\\python.exe",
      "required_version_family": "3.11",
      "required_architecture": "x64",
      "base_prefix_must_equal_managed_root": true,
      "pip_required": true,
      "allowed_packages": "ensurepip_default_bootstrap_only",
      "project_dependency_install_attempts": 0
    },
    "required_post_state": {
      "success_state": "ISOLATED_NATIVE_CPYTHON311_READY",
      "user_and_machine_path_bytes_unchanged": true,
      "python_registry_inventory_additions": 0,
      "legacy_python_state_unchanged": true,
      "program_files_python311_exists": false,
      "git_for_windows_version": "2.55.0.windows.5",
      "installer_or_msiexec_process_count": 0,
      "exact_paths_versions_and_hashes_recorded": true,
      "n1_handoff_allowed": false
    },
    "required_zero_mutations": {
      "admin_or_uac": 0,
      "d_drive": 0,
      "postgresql": 0,
      "wsl": 0,
      "scheduler": 0,
      "git": 0,
      "n1_n6": 0,
      "nas": 0,
      "mac": 0,
      "winget": 0,
      "psf_installer_rerun": 0,
      "registry_or_path": 0,
      "old_msi_bundle_cache_or_target": 0,
      "uv_self_update": 0,
      "business_dependencies": 0
    },
    "failure_state": "BLOCKED_EVIDENCE_PRESERVED",
    "cleanup_attempts": 0,
    "n1_handoff_allowed": false
  },
  "postgresql16_installer_contract": {
    "publisher_supported_defaults_required": true,
    "installation_mode": "interactive_gui_from_exact_staged_installer",
    "winget_unattended_execution_forbidden": true,
    "service_name": "postgresql-x64-16",
    "transient_installer_identity": "NT AUTHORITY\\NetworkService",
    "transient_identity_allowed_only_during_gui_install_and_empty_cluster_bootstrap": true,
    "final_service_account": "NT SERVICE\\postgresql-x64-16",
    "local_account_create_attempts": 0,
    "service_identity_transition_attempts": 1,
    "service_must_be_stopped_before_identity_or_acl_transition": true,
    "service_sid_type": "UNRESTRICTED",
    "scm_virtual_account_password": "none",
    "networkservice_acl_count_final": 0,
    "final_gate_requires_service_name_startname_sid_acl_loopback_empty_business_and_zero_imports": true,
    "networkservice_final_identity_forbidden": true,
    "service_logon_only": true,
    "interactive_local_rdp_network_batch_logon_forbidden": true,
    "account_group_membership_change_forbidden": true,
    "gui_secret_entry_required": true,
    "unattended_install_with_secret_forbidden": true,
    "gui_password_scope": "postgresql_database_superuser_only",
    "secret_forbidden_locations": [
      "command_line",
      "process_argv",
      "environment",
      "response_file",
      "shell_history",
      "transcript",
      "log",
      "evidence",
      "screenshot"
    ],
    "secret_value_or_hash_recording_forbidden": true,
    "evidence_records_only_redacted_gui_entry_and_redaction_audit": true,
    "automatic_retry_attempts": 0,
    "failed_install_preserved_as_evidence": true
  },
  "postgresql_virtual_identity_1639_recovery": {
    "prior_policy_commit": "3160c7bee824a5cadcd7f63c78235a8b5c24c038",
    "prior_policy_tree": "08959a4190ca4d2dafe67cf7062625541657f171",
    "prior_failed_program": "sc.exe config",
    "prior_exit_code": 1639,
    "prior_startname_unchanged": "NT AUTHORITY\\NetworkService",
    "phase_mode": "w0_postgresql_virtual_identity_1639_recovery",
    "attempts": 1,
    "required_pre_state": {
      "service_state": "Stopped",
      "start_name": "NT AUTHORITY\\NetworkService",
      "service_sid_type": "UNRESTRICTED",
      "virtual_account_acl_present": true,
      "networkservice_acl_count_full_tree": 0,
      "listen_addresses": "127.0.0.1",
      "port": 5432,
      "listener_5432_present": false
    },
    "only_mutation_method": "Invoke-CimMethod Win32_Service.Change",
    "change_arguments": {
      "StartName": "NT SERVICE\\postgresql-x64-16",
      "StartPassword": "empty_string"
    },
    "required_return_value": 0,
    "configuration_acl_install_mutation_attempts": 0,
    "service_start_attempts_after_verified_change": 1,
    "required_post_state": {
      "service_state": "Running",
      "start_name": "NT SERVICE\\postgresql-x64-16",
      "service_sid_type": "UNRESTRICTED",
      "listen_endpoint": "127.0.0.1:5432",
      "pg_isready": "accepting",
      "networkservice_acl_count_full_tree": 0
    },
    "failure_service_state": "Stopped",
    "automatic_retry_attempts": 0,
    "networkservice_restore_attempts": 0,
    "n1_handoff_allowed": false
  },
  "postgresql_virtual_identity_22_recovery": {
    "policy_id": "w0_postgresql_virtual_identity_22_recovery_v1",
    "prior_policy_commit": "0a64eb665433483a69e9134c222a1dabc03c1da2",
    "prior_policy_tree": "0f97f27c5a43d976e73f025e20d6b355f6ece494",
    "prior_phase": "w0_postgresql_virtual_identity_1639_recovery",
    "prior_mutation_method": "Invoke-CimMethod Win32_Service.Change",
    "prior_change_start_name": "NT SERVICE\\postgresql-x64-16",
    "prior_change_start_password": "empty_string",
    "prior_return_value": 22,
    "prior_service_start_attempts": 0,
    "prior_identity_change_proven": false,
    "phase_mode": "w0_postgresql_virtual_identity_22_recovery",
    "attempts": 1,
    "required_fresh_read_only_pre_state": {
      "service_state": "Stopped",
      "start_name": "NT AUTHORITY\\NetworkService",
      "service_sid_type": "UNRESTRICTED",
      "listener_5432_present": false
    },
    "only_mutation_program": "sc.exe",
    "exact_argument_vector": [
      "config",
      "postgresql-x64-16",
      "obj=",
      "NT SERVICE\\postgresql-x64-16"
    ],
    "password_argument": "OMITTED",
    "changeserviceconfig_lpPassword": "NULL",
    "required_exit_code": 0,
    "read_only_startname_check_before_start": true,
    "service_start_attempts_after_verified_change": 1,
    "required_post_state": {
      "service_state": "Running",
      "start_name": "NT SERVICE\\postgresql-x64-16",
      "service_sid_type": "UNRESTRICTED",
      "listen_endpoint": "127.0.0.1:5432",
      "pg_isready": "accepting",
      "networkservice_acl_count_full_tree": 0
    },
    "configuration_acl_install_or_logon_right_mutation_attempts": 0,
    "v6_rerun_attempts": 0,
    "automatic_retry_attempts": 0,
    "networkservice_restore_attempts": 0,
    "failure_service_state": "Stopped",
    "n1_handoff_allowed": false
  },
  "empty_cluster_contract": {
    "initdb_new_empty_cluster_only": true,
    "mac_dump_import_attempts": 0,
    "mac_record_import_attempts": 0,
    "mac_source_version_import_attempts": 0,
    "mac_evidence_import_attempts": 0,
    "ashare_v3_business_database_create_attempts": 0,
    "business_schema_create_or_migrate_attempts": 0,
    "n1_n6_data_write_attempts": 0
  },
  "identity_acl_contract": {
    "routine_codex_native_identity": {
      "account": "TDX-STOCK\\ashare-ops",
      "sid": "S-1-5-21-2072264739-3883739137-88032818-1006",
      "integrity": "Medium",
      "administrators_member": false,
      "required_group_memberships": [
        "Users",
        "Authenticated Users"
      ],
      "native_ssh_login_required": true
    },
    "elevated_operator_identity": {
      "account": "TDX-STOCK\\47894",
      "sid": "S-1-5-21-2072264739-3883739137-88032818-1002",
      "administrators_member": true,
      "allowed_phase_modes": [
        "w0_prepare_and_mutate",
        "w0_postgresql_virtual_identity_1639_recovery",
        "w0_postgresql_virtual_identity_22_recovery",
        "w0_python311_per_user_scope_collision_recovery"
      ],
      "allowed_admin_operations": [
        "exact_frozen_installer_once",
        "disable_dynamically_frozen_scheduler_inventory",
        "stop_and_disable_postgresql_x64_18",
        "create_exact_d_postgresql_directories",
      "apply_exact_c_and_d_acl",
      "create_or_configure_exact_postgresql_16_service",
      "restrict_exact_postgres_service_account_logon",
      "stage_exact_wsl_configuration",
      "invoke_exact_postgresql_1639_cim_change_and_verified_start",
      "invoke_exact_postgresql_22_sc_config_null_password_and_verified_start",
      "invoke_exact_python311_per_user_uninstall_then_machine_install"
      ]
    },
    "routine_and_elevated_identities_must_be_distinct": true,
    "elevated_operator_is_not_routine_codex_or_application": true,
    "operator_d_access_must_not_be_used_as_routine_acl_failure": true,
    "unknown_sid_rejected": true,
    "account_create_password_group_or_privilege_change_forbidden": true,
    "postgresql_identity_non_interactive": true,
    "postgresql_identity_access_scope": [
      "D:\\PostgreSQL\\16",
      "D:\\PostgreSQL\\backup-staging"
    ],
    "application_identity_must_be_non_admin": true,
    "codex_identity_must_be_non_admin": true,
    "operator_identity_must_be_distinct_from_application_and_codex": true,
    "application_and_codex_denied_rights": [
      "read",
      "list",
      "write",
      "create",
      "delete",
      "change_permissions",
      "take_ownership"
    ],
    "routine_d_denial_scope": "D:\\PostgreSQL\\16",
    "routine_normal_access_channels": [
      "loopback_database_connection",
      "C_drive_application_paths"
    ],
    "fail_if_identity_or_effective_access_is_unproven": true
  },
  "wsl_isolation_contract": {
    "after_restart_automount_d": false,
    "after_restart_mnt_d_exists": false,
    "after_restart_only_explicit_drive": "C",
    "wsl_conf_interop_enabled": false,
    "wsl_conf_append_windows_path": false,
    "linux_identity": "ashare-codex",
    "linux_identity_must_access_mnt_c_code": true,
    "native_operations_channel": "TDX-STOCK\\ashare-ops SSH",
    "uac_install_channel": "TDX-STOCK\\47894 independent native channel",
    "current_wsl_native_interop_operator_inheritance_forbidden": true
  },
  "required_pre_evidence": [
    "native_and_wsl_identity",
    "routine_and_elevated_account_sid_integrity_group_and_channel_evidence",
    "windows_build_and_architecture",
    "c_and_d_directory_inventory_without_recursive_delete",
    "c_and_d_owner_acl_sddl_and_effective_access",
    "dynamic_current_exact_asharev3_scheduler_inventory_definitions_and_states",
    "scheduler_current_count_and_prior_evidence_count_delta_as_quality_evidence",
    "legacy_postgresql_18_service_config_state_and_binary_data_paths",
    "installed_git_python_postgresql_versions_and_paths",
    "native_python311_registry_launcher_alias_executable_pe_version_pip_venv_state",
    "installer_package_ids_versions_sha256_and_signatures",
    "postgresql_16_15_1_exact_hash_authenticode_signer_and_official_authority",
    "local_postgres_account_presence_sid_groups_and_logon_rights",
    "postgresql_gui_secret_redaction_plan",
    "TdxW_process_and_127_0_0_1_17709_owner",
    "wsl_mounts_and_wsl_conf",
    "process_and_service_inventory",
    "baseline_commit_tree_and_policy_hash"
  ],
  "required_post_evidence": [
    "all_dynamically_frozen_exact_asharev3_scheduler_definitions_preserved_and_disabled",
    "scheduler_before_inventory_delta_quality_evidence",
    "legacy_postgresql_18_service_stopped_and_disabled_with_files_untouched",
    "git_for_windows_version",
    "native_python311_executable_pe_x64_version_3_11_x_pip_and_venv",
    "postgresql_16_version_at_least_16_14",
    "postgresql_16_install_and_data_paths_on_d",
    "postgresql_x64_16_service_runs_as_exact_local_postgres_account",
    "postgres_service_account_service_logon_only_and_exact_d_acl",
    "postgres_secret_absent_from_command_line_environment_logs_evidence_and_screenshots",
    "new_cluster_identity_and_zero_business_objects",
    "listen_addresses_exactly_127_0_0_1",
    "postgresql_port_exactly_5432",
    "c_and_d_owner_acl_sddl_and_effective_access",
    "application_and_codex_d_access_denials",
    "TdxW_process_and_127_0_0_1_17709_owner",
    "mac_import_attempt_counts_all_zero",
    "n1_n6_nas_and_business_write_attempt_counts_all_zero",
    "wsl_c_visible_and_d_absent_after_native_restart",
    "wsl_interop_disabled_append_windows_path_false_and_mnt_d_absent",
    "routine_ashare_ops_medium_non_admin_ssh_and_d_denials",
    "phase_attempt_counts_and_final_verdict"
  ],
  "required_zero_attempts": [
    "scheduler_delete_attempts",
    "scheduler_enable_attempts",
    "legacy_postgresql_18_uninstall_attempts",
    "legacy_postgresql_18_program_delete_attempts",
    "legacy_postgresql_18_data_delete_attempts",
    "recursive_delete_attempts",
    "overwrite_existing_path_attempts",
    "git_reset_hard_attempts",
    "git_clean_attempts",
    "tushare_install_import_call_attempts",
    "mootdx_install_import_call_attempts",
    "mac_worktree_write_attempts",
    "mac_data_import_attempts",
    "n1_n6_runtime_attempts",
    "nas_operation_attempts",
    "business_database_write_attempts",
    "wsl_shutdown_attempts_in_prepare_phase",
    "python311_install_or_repair_attempts_without_missing_or_damaged_preflight",
    "python311_second_install_or_repair_attempts",
    "python311_microsoft_store_alias_attempts",
    "python311_3_12_or_3_14_substitution_attempts",
    "python311_source_build_attempts",
    "python311_third_party_distribution_attempts",
    "business_venv_create_attempts",
    "project_package_install_attempts",
    "non_postgresql_identity_account_create_attempts",
    "postgres_local_account_create_attempts",
    "postgres_service_identity_second_transition_attempts",
    "postgres_service_start_before_final_identity_acl_attempts",
    "postgres_secret_command_line_or_process_argv_attempts",
    "postgres_secret_environment_or_response_file_attempts",
    "postgres_secret_log_history_transcript_evidence_or_screenshot_attempts",
    "postgres_interactive_logon_enable_attempts",
    "identity_password_change_attempts_outside_single_edb_gui_creation",
    "identity_group_membership_change_attempts",
    "identity_privilege_change_attempts",
    "elevated_operator_outside_prepare_attempts",
    "current_wsl_native_interop_attempts",
    "postgresql_1639_recovery_second_attempts",
    "postgresql_1639_recovery_sc_exe_attempts",
    "postgresql_1639_recovery_acl_or_config_attempts",
    "postgresql_1639_recovery_networkservice_restore_attempts",
    "postgresql_22_recovery_second_attempts",
    "postgresql_22_recovery_v6_rerun_attempts",
    "postgresql_22_recovery_cim_attempts",
    "postgresql_22_recovery_password_argument_attempts",
    "postgresql_22_recovery_acl_config_install_or_logon_right_attempts",
    "postgresql_22_recovery_networkservice_restore_attempts",
    "python311_scope_collision_second_uninstall_attempts",
    "python311_scope_collision_second_install_attempts",
    "python311_scope_collision_manual_msiexec_attempts",
    "python311_scope_collision_registry_delete_attempts",
    "python311_scope_collision_package_cache_or_directory_delete_attempts",
    "python311_scope_collision_cleanup_attempts",
    "python311_scope_collision_git_mutation_attempts",
    "python311_scope_collision_windows_resource_mutation_attempts"
  ],
  "forbidden": [
    "Tushare",
    "Mootdx",
    "Mac dump restore",
    "Mac records or source_version import",
    "Mac evidence reuse",
    "N1-N6 runtime",
    "NAS operations",
    "Task Scheduler enable or creation",
    "fixed historical Scheduler task count as execution authority",
    "Microsoft Store Python alias",
    "Python 3.12 or 3.14 substitution",
    "Python source build or third-party distribution",
    "W0 business venv or project package install",
    "new Windows local account or account password/group/privilege mutation",
    "PostgreSQL secret in command line, argv, environment, response file, history, transcript, log, evidence or screenshot",
    "NT AUTHORITY\\NetworkService after bounded installer bootstrap",
    "final PostgreSQL 16 identity other than NT SERVICE\\postgresql-x64-16",
    "unknown or swapped routine/elevated SID",
    "routine identity in Administrators",
    "WSL interop enabled or appendWindowsPath true after restart",
    "business schema or business data",
    "recursive delete",
    "overwrite existing paths",
    "git reset --hard",
    "git clean"
  ],
  "rollback_and_recovery": {
    "automatic_rollback": false,
    "automatic_cleanup": false,
    "scheduler_tasks_must_never_be_deleted": true,
    "disabled_scheduler_tasks_remain_disabled_on_failure": true,
    "legacy_postgresql_18_files_and_data_remain_untouched": true,
    "new_postgresql_16_files_and_failed_cluster_are_preserved_as_evidence": true,
    "failed_python311_install_or_repair_is_preserved_as_evidence": true,
    "unknown_existing_python_must_not_be_uninstalled": true,
    "failed_python311_directory_must_not_be_automatically_cleaned": true,
    "no_existing_path_may_be_replaced": true,
    "restore_or_recovery_requires_new_independent_authorization": true,
    "failure_result": "BLOCKED_EVIDENCE_PRESERVED"
  },
  "n1_handoff": {
    "requires_w0_pass": true,
    "next_layer_role": "N1_ingestion",
    "allowed_sources": [
      "TQ",
      "eltdx_finance",
      "self_built_trade_calendar"
    ],
    "forbidden_sources": [
      "Tushare",
      "Mootdx",
      "Mac_dump",
      "Mac_records",
      "Mac_source_version",
      "Mac_evidence"
    ],
    "nas_deferred_until_after_n1": true
  }
}
```
<!-- policy:windows_rebuild_w0_bounded_v1:end -->

The two phases are ordered and mutually exclusive. `w0_prepare_and_mutate`
must stop with sealed evidence and `RESTART_REQUIRED`; it may not invoke
`wsl --shutdown`. Only a subsequent independently authorized native Windows
`wsl_shutdown_native_control` phase may invoke shutdown once and then prove
that WSL explicitly sees C and cannot see D. W0 PASS is required before a
separate `N1_ingestion` task may build Windows N1 from zero.

PostgreSQL installation is frozen to official EDB 16.15-1 x64: package
`PostgreSQL.PostgreSQL.16`, URL
`https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64.exe`,
SHA-256 `DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2`,
Authenticode `Valid`, signer `EnterpriseDB Corporation`, service
`postgresql-x64-16`. `NT AUTHORITY\NetworkService` is allowed only transiently
during the official GUI install and empty-cluster bootstrap. Before any business
connection/schema/N1-N6 action, the service must be stopped and changed once to
passwordless virtual account `NT SERVICE\postgresql-x64-16`; SID type must be
`UNRESTRICTED`. Only that SID receives the exact D-root ACLs and every
NetworkService ACE on those roots must be removed. No local account is created.

The EDB GUI password is only the PostgreSQL database-superuser secret, never a
Windows service-account password. It must be entered only by the elevated operator in GUI
password controls. It may never appear in command lines, process argv,
environment variables, response files, shell history, transcripts, logs,
evidence or screenshots; neither its value nor a hash may be retained.
Evidence records only redacted GUI-entry completion and a redaction audit.
Missing, leaked, reset, unattended or unverifiable secret handling returns
`REJECT/BLOCKED_EVIDENCE_PRESERVED` without retry, uninstall or cleanup.
