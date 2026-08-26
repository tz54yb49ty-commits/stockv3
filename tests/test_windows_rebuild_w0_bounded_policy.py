from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "windows_rebuild_w0_bounded_v1"
AGENTS_PATH = ROOT / "AGENTS.md"
COMPILER_PATH = ROOT / "docs" / "EXECUTION_COMPILER.md"
KERNEL_PATH = ROOT / "docs" / "EXECUTION_KERNEL.md"
RUNTIME_GATE_PATH = ROOT / "docs" / "EXECUTION_RUNTIME_GATE.md"
SANDBOX_PATH = ROOT / "docs" / "EXECUTION_SANDBOX.md"
TRACE_PATH = ROOT / "docs" / "EXECUTION_TRACE_SYSTEM.md"
TEST_SUITE_PATH = ROOT / "docs" / "EXECUTION_TEST_SUITE.md"


def load_policy_from(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    begin = f"<!-- policy:{POLICY_ID}:begin -->"
    end = f"<!-- policy:{POLICY_ID}:end -->"
    block = text[text.index(begin) + len(begin) : text.index(end)]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        raise AssertionError("W0 policy must contain exactly one valid JSON fence")
    return json.loads(match.group(1))


def load_control_contracts(
    agents_path: Path = AGENTS_PATH,
    compiler_path: Path = COMPILER_PATH,
    kernel_path: Path = KERNEL_PATH,
    runtime_gate_path: Path = RUNTIME_GATE_PATH,
    sandbox_path: Path = SANDBOX_PATH,
    trace_path: Path = TRACE_PATH,
    test_suite_path: Path = TEST_SUITE_PATH,
) -> tuple[dict[str, Any], str, str, str, str, str]:
    for path in (
        agents_path,
        compiler_path,
        kernel_path,
        runtime_gate_path,
        sandbox_path,
        trace_path,
        test_suite_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    agents_policy = load_policy_from(agents_path)
    kernel_policy = load_policy_from(kernel_path)
    if agents_policy != kernel_policy:
        raise AssertionError("AGENTS and Kernel W0 policies must be identical")
    compiler = compiler_path.read_text(encoding="utf-8")
    if POLICY_ID not in compiler:
        raise AssertionError("Compiler must recognize the W0 policy")
    runtime_gate = runtime_gate_path.read_text(encoding="utf-8")
    if POLICY_ID not in runtime_gate:
        raise AssertionError("Runtime Gate must recognize the W0 policy")
    sandbox = sandbox_path.read_text(encoding="utf-8")
    if POLICY_ID not in sandbox:
        raise AssertionError("Sandbox must recognize the W0 policy")
    trace = trace_path.read_text(encoding="utf-8")
    if POLICY_ID not in trace:
        raise AssertionError("Trace must recognize the W0 policy")
    test_suite = test_suite_path.read_text(encoding="utf-8")
    if POLICY_ID not in test_suite:
        raise AssertionError("Test Suite must recognize the W0 policy")
    return agents_policy, compiler, runtime_gate, sandbox, trace, test_suite


def canonical_request(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": policy["policy_id"],
        "layer_role": policy["layer_role"],
        "phase_mode": "w0_prepare_and_mutate",
        "phase_attempts": 1,
        "explicit_current_request_authorization": True,
        "independent_execution_session": True,
        "pre_evidence_complete": True,
        "identity_acl_effective_access_proven": True,
        "existing_target_path_conflict": False,
        "routine_native_account": policy["identity_acl_contract"][
            "routine_codex_native_identity"
        ]["account"],
        "routine_native_sid": policy["identity_acl_contract"][
            "routine_codex_native_identity"
        ]["sid"],
        "routine_integrity": "Medium",
        "routine_administrators_member": False,
        "routine_native_ssh_login": True,
        "routine_group_memberships": ["Users", "Authenticated Users"],
        "elevated_operator_account": policy["identity_acl_contract"][
            "elevated_operator_identity"
        ]["account"],
        "elevated_operator_sid": policy["identity_acl_contract"][
            "elevated_operator_identity"
        ]["sid"],
        "elevated_operator_administrators_member": True,
        "identities_distinct": True,
        "elevated_admin_mutation_requested": True,
        "elevated_admin_operations": policy["identity_acl_contract"][
            "elevated_operator_identity"
        ]["allowed_admin_operations"],
        "operator_d_access_used_as_routine_acl_failure": False,
        "routine_d_denials_complete": True,
        "routine_normal_access_loopback_db_and_c_only": True,
        "wsl_after_restart_only_explicit_c": True,
        "wsl_after_restart_automount_d": False,
        "wsl_after_restart_mnt_d_exists": False,
        "wsl_interop_enabled_after_restart": False,
        "wsl_append_windows_path_after_restart": False,
        "wsl_ashare_codex_mnt_c_code_access": True,
        "native_operations_via_ashare_ops_ssh": True,
        "uac_install_via_independent_47894_channel": True,
        "scheduler_dynamic_inventory_frozen": True,
        "scheduler_fixed_count_used_as_authority": False,
        "scheduler_prior_count_delta_quality_evidence_complete": True,
        "scheduler_after_every_frozen_task_disabled": True,
        "scheduler_current_count": 9,
        "python311_preflight_state": "missing_native_3_11",
        "python311_package_id": policy["python311_contract"]["package_id"],
        "python311_install_root": policy["python311_contract"]["install_root"],
        "python311_python_executable": policy["python311_contract"][
            "python_executable"
        ],
        "python311_resolved_version": "3.11.9",
        "python311_current_safe_patch_resolved": True,
        "python311_official_publisher_signer_sha256_frozen": True,
        "python311_machine_wide_x64": True,
        "python311_install_or_repair_attempts": 1,
        "python311_post_verify_complete": True,
        "postgresql_package_id": policy["exact_allowlist"][
            "postgresql_installer_package_id"
        ],
        "postgresql_installer_version": policy["exact_allowlist"][
            "postgresql_installer_version"
        ],
        "postgresql_installer_sha256": policy["exact_allowlist"][
            "postgresql_installer_sha256"
        ],
        "postgresql_installer_path": policy["exact_allowlist"][
            "postgresql_installer_path"
        ],
        "postgresql_installation_mode": "interactive_gui_from_exact_staged_installer",
        "postgresql_winget_unattended_execution": False,
        "postgresql_authenticode_status": "Valid",
        "postgresql_installer_signer": "EnterpriseDB Corporation",
        "postgresql_service_name": "postgresql-x64-16",
        "postgresql_transient_installer_identity": r"NT AUTHORITY\NetworkService",
        "postgresql_service_account": r"NT SERVICE\postgresql-x64-16",
        "postgresql_service_stopped_before_transition": True,
        "postgresql_service_identity_transition_attempts": 1,
        "postgresql_service_sid_type": "UNRESTRICTED",
        "postgresql_networkservice_acl_count_final": 0,
        "postgresql_empty_business_db": True,
        "postgresql_loopback_5432_verified": True,
        "postgresql_service_logon_only": True,
        "postgresql_interactive_logons_denied": True,
        "postgresql_networkservice_final_identity": False,
        "postgresql_secret_entered_only_in_elevated_gui": True,
        "postgresql_secret_redaction_audit_passed": True,
        "postgresql_secret_value_or_hash_recorded": False,
        **{name: 0 for name in policy["required_zero_attempts"]},
    }


def evaluate(policy: dict[str, Any], request: dict[str, Any]) -> str:
    reject = policy["default_runtime_execution_decision"]
    if request.get("policy_id") != policy["policy_id"]:
        return reject
    if request.get("layer_role") != "runtime_control":
        return reject
    if request.get("phase_mode") not in policy["phase_contract"]["allowed_phase_modes"]:
        return reject
    if request.get("phase_attempts") != policy["phase_contract"]["attempts_per_phase"]:
        return reject
    for field in (
        "explicit_current_request_authorization",
        "independent_execution_session",
        "pre_evidence_complete",
        "identity_acl_effective_access_proven",
    ):
        if request.get(field) is not True:
            return reject
    if request.get("existing_target_path_conflict") is not False:
        return reject
    identity = policy["identity_acl_contract"]
    routine = identity["routine_codex_native_identity"]
    elevated = identity["elevated_operator_identity"]
    exact_identity_values = {
        "routine_native_account": routine["account"],
        "routine_native_sid": routine["sid"],
        "routine_integrity": routine["integrity"],
        "routine_administrators_member": routine["administrators_member"],
        "routine_native_ssh_login": routine["native_ssh_login_required"],
        "routine_group_memberships": routine["required_group_memberships"],
        "elevated_operator_account": elevated["account"],
        "elevated_operator_sid": elevated["sid"],
        "elevated_operator_administrators_member": elevated[
            "administrators_member"
        ],
    }
    if any(request.get(k) != v for k, v in exact_identity_values.items()):
        return reject
    if request.get("routine_native_sid") == request.get("elevated_operator_sid"):
        return reject
    for field in (
        "identities_distinct",
        "routine_d_denials_complete",
        "routine_normal_access_loopback_db_and_c_only",
        "wsl_after_restart_only_explicit_c",
        "wsl_ashare_codex_mnt_c_code_access",
        "native_operations_via_ashare_ops_ssh",
        "uac_install_via_independent_47894_channel",
    ):
        if request.get(field) is not True:
            return reject
    for field in (
        "operator_d_access_used_as_routine_acl_failure",
        "wsl_after_restart_automount_d",
        "wsl_after_restart_mnt_d_exists",
        "wsl_interop_enabled_after_restart",
        "wsl_append_windows_path_after_restart",
    ):
        if request.get(field) is not False:
            return reject
    if request.get("elevated_admin_mutation_requested") is True:
        if request.get("phase_mode") not in elevated["allowed_phase_modes"]:
            return reject
        if request.get("elevated_admin_operations") != elevated[
            "allowed_admin_operations"
        ]:
            return reject
    for field in (
        "scheduler_dynamic_inventory_frozen",
        "scheduler_prior_count_delta_quality_evidence_complete",
        "scheduler_after_every_frozen_task_disabled",
    ):
        if request.get(field) is not True:
            return reject
    if request.get("scheduler_fixed_count_used_as_authority") is not False:
        return reject
    if not isinstance(request.get("scheduler_current_count"), int):
        return reject
    if request["scheduler_current_count"] < 0:
        return reject
    python_contract = policy["python311_contract"]
    python_state = request.get("python311_preflight_state")
    python_attempts = request.get("python311_install_or_repair_attempts")
    if python_state == "valid_native_3_11_x64":
        if python_attempts != 0:
            return reject
    elif python_state in python_contract["install_or_repair_allowed_only_for_states"]:
        if python_attempts != python_contract["install_or_repair_attempts"]:
            return reject
    else:
        return reject
    if python_attempts == 1:
        if request.get("python311_package_id") != python_contract["package_id"]:
            return reject
        if request.get("python311_install_root") != python_contract["install_root"]:
            return reject
        if (
            request.get("python311_python_executable")
            != python_contract["python_executable"]
        ):
            return reject
        if re.fullmatch(
            r"3\.11\.\d+", request.get("python311_resolved_version", "")
        ) is None:
            return reject
        for field in (
            "python311_official_publisher_signer_sha256_frozen",
            "python311_current_safe_patch_resolved",
            "python311_machine_wide_x64",
            "python311_post_verify_complete",
        ):
            if request.get(field) is not True:
                return reject
    pg = policy["postgresql16_installer_contract"]
    allowlist = policy["exact_allowlist"]
    exact_pg_values = {
        "postgresql_package_id": allowlist["postgresql_installer_package_id"],
        "postgresql_installer_version": allowlist["postgresql_installer_version"],
        "postgresql_installer_sha256": allowlist["postgresql_installer_sha256"],
        "postgresql_installer_path": allowlist["postgresql_installer_path"],
        "postgresql_installation_mode": pg["installation_mode"],
        "postgresql_authenticode_status": allowlist[
            "postgresql_installer_authenticode_status"
        ],
        "postgresql_installer_signer": allowlist["postgresql_installer_signer"],
        "postgresql_service_name": pg["service_name"],
        "postgresql_transient_installer_identity": pg["transient_installer_identity"],
        "postgresql_service_account": pg["final_service_account"],
    }
    if any(request.get(key) != value for key, value in exact_pg_values.items()):
        return reject
    if request.get("postgresql_service_identity_transition_attempts") != 1:
        return reject
    if request.get("postgresql_service_sid_type") != "UNRESTRICTED":
        return reject
    if request.get("postgresql_networkservice_acl_count_final") != 0:
        return reject
    for field in (
        "postgresql_service_logon_only",
        "postgresql_interactive_logons_denied",
        "postgresql_service_stopped_before_transition",
        "postgresql_empty_business_db",
        "postgresql_loopback_5432_verified",
        "postgresql_secret_entered_only_in_elevated_gui",
        "postgresql_secret_redaction_audit_passed",
    ):
        if request.get(field) is not True:
            return reject
    for field in (
        "postgresql_networkservice_final_identity",
        "postgresql_secret_value_or_hash_recorded",
        "postgresql_winget_unattended_execution",
    ):
        if request.get(field) is not False:
            return reject
    if any(request.get(name) != 0 for name in policy["required_zero_attempts"]):
        return reject
    return policy["accept_decision"]


class WindowsRebuildW0BoundedPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            cls.policy,
            cls.compiler,
            cls.runtime_gate,
            cls.sandbox,
            cls.trace,
            cls.test_suite,
        ) = load_control_contracts()
        cls.request = canonical_request(cls.policy)

    def decision(self, **overrides: Any) -> str:
        request = copy.deepcopy(self.request)
        request.update(overrides)
        return evaluate(self.policy, request)

    def test_exact_independent_contract_accepts(self) -> None:
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertTrue(self.policy["governance_session_cannot_execute"])
        self.assertEqual(self.policy["policy_state"], "POLICY_READY_NOT_EXECUTED")

    def test_general_or_same_governance_session_rejects(self) -> None:
        self.assertEqual(
            self.policy["default_runtime_execution_decision"], "REJECT"
        )
        self.assertEqual(self.decision(policy_id="general_windows_setup"), "REJECT")
        self.assertEqual(self.decision(independent_execution_session=False), "REJECT")
        self.assertEqual(self.decision(phase_attempts=2), "REJECT")

    def test_every_forbidden_attempt_is_fail_closed(self) -> None:
        for field in self.policy["required_zero_attempts"]:
            with self.subTest(field=field):
                self.assertEqual(self.decision(**{field: 1}), "REJECT")

    def test_identity_acl_and_path_authority_fail_closed(self) -> None:
        self.assertEqual(self.decision(pre_evidence_complete=False), "REJECT")
        self.assertEqual(
            self.decision(identity_acl_effective_access_proven=False), "REJECT"
        )
        self.assertEqual(self.decision(existing_target_path_conflict=True), "REJECT")
        acl = self.policy["identity_acl_contract"]
        self.assertTrue(acl["application_identity_must_be_non_admin"])
        self.assertTrue(acl["codex_identity_must_be_non_admin"])
        self.assertIn("take_ownership", acl["application_and_codex_denied_rights"])

    def test_exact_dual_identity_prepare_contract_accepts(self) -> None:
        acl = self.policy["identity_acl_contract"]
        routine = acl["routine_codex_native_identity"]
        elevated = acl["elevated_operator_identity"]
        self.assertEqual(routine["account"], r"TDX-STOCK\ashare-ops")
        self.assertEqual(
            routine["sid"], "S-1-5-21-2072264739-3883739137-88032818-1006"
        )
        self.assertEqual(routine["integrity"], "Medium")
        self.assertFalse(routine["administrators_member"])
        self.assertEqual(elevated["account"], r"TDX-STOCK\47894")
        self.assertEqual(
            elevated["sid"], "S-1-5-21-2072264739-3883739137-88032818-1002"
        )
        self.assertTrue(elevated["administrators_member"])
        self.assertEqual(elevated["allowed_phase_modes"], ["w0_prepare_and_mutate"])
        self.assertEqual(acl["routine_d_denial_scope"], r"D:\PostgreSQL\16")
        wsl = self.policy["wsl_isolation_contract"]
        self.assertFalse(wsl["after_restart_automount_d"])
        self.assertFalse(wsl["after_restart_mnt_d_exists"])
        self.assertEqual(wsl["after_restart_only_explicit_drive"], "C")
        self.assertFalse(wsl["wsl_conf_interop_enabled"])
        self.assertFalse(wsl["wsl_conf_append_windows_path"])
        self.assertTrue(wsl["linux_identity_must_access_mnt_c_code"])
        self.assertEqual(self.decision(), "ACCEPT")

    def test_swapped_equal_admin_or_interop_identity_boundaries_reject(self) -> None:
        routine_sid = self.request["routine_native_sid"]
        elevated_sid = self.request["elevated_operator_sid"]
        for overrides in (
            {
                "routine_native_sid": elevated_sid,
                "elevated_operator_sid": routine_sid,
            },
            {"elevated_operator_sid": routine_sid},
            {"routine_administrators_member": True},
            {"routine_integrity": "High"},
            {"routine_native_ssh_login": False},
            {"wsl_interop_enabled_after_restart": True},
            {"wsl_append_windows_path_after_restart": True},
            {"wsl_after_restart_automount_d": True},
            {"wsl_after_restart_mnt_d_exists": True},
            {"operator_d_access_used_as_routine_acl_failure": True},
            {"elevated_admin_operations": ["arbitrary_admin_action"]},
            {"phase_mode": "wsl_shutdown_native_control"},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.decision(**overrides), "REJECT")

    def test_empty_cluster_and_windows_only_n1_sources_are_frozen(self) -> None:
        empty = self.policy["empty_cluster_contract"]
        for field, value in empty.items():
            if field.endswith("_attempts"):
                self.assertEqual(value, 0)
        handoff = self.policy["n1_handoff"]
        self.assertEqual(
            handoff["allowed_sources"],
            ["TQ", "eltdx_finance", "self_built_trade_calendar"],
        )
        self.assertIn("Tushare", handoff["forbidden_sources"])
        self.assertIn("Mootdx", handoff["forbidden_sources"])

    def test_scheduler_service_and_shutdown_boundaries_are_exact(self) -> None:
        allowlist = self.policy["exact_allowlist"]
        self.assertEqual(
            allowlist["scheduler_operations"],
            ["export_exact_definition", "disable_exact_task"],
        )
        self.assertEqual(allowlist["legacy_service_name"], "postgresql-x64-18")
        self.assertEqual(
            allowlist["software_package_ids"],
            ["Git.Git", "PostgreSQL.PostgreSQL.16", "Python.Python.3.11"],
        )
        self.assertEqual(
            allowlist["postgresql_backup_staging"],
            r"D:\PostgreSQL\backup-staging",
        )
        self.assertEqual(
            self.policy["phase_contract"]["shutdown_phase_requires_prior_result"],
            "RESTART_REQUIRED",
        )
        self.assertIn(
            "wsl_shutdown_attempts_in_prepare_phase",
            self.policy["required_zero_attempts"],
        )

    def test_exact_edb_postgresql_installer_and_dedicated_identity_accepts(self) -> None:
        allowlist = self.policy["exact_allowlist"]
        pg = self.policy["postgresql16_installer_contract"]
        self.assertEqual(self.policy["policy_version"], 5)
        self.assertEqual(allowlist["postgresql_installer_version"], "16.15-1")
        self.assertEqual(
            allowlist["postgresql_installer_sha256"],
            "DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2",
        )
        self.assertEqual(allowlist["postgresql_installer_signer"], "EnterpriseDB Corporation")
        self.assertEqual(
            allowlist["postgresql_installer_path"],
            r"C:\AshareV3\staging\installers\postgresql-16.15-1-windows-x64-download-v1.exe",
        )
        self.assertEqual(pg["service_name"], "postgresql-x64-16")
        self.assertEqual(pg["transient_installer_identity"], r"NT AUTHORITY\NetworkService")
        self.assertEqual(pg["final_service_account"], r"NT SERVICE\postgresql-x64-16")
        self.assertTrue(pg["networkservice_final_identity_forbidden"])
        self.assertEqual(pg["gui_password_scope"], "postgresql_database_superuser_only")
        self.assertEqual(allowlist["postgresql_port"], 5432)
        self.assertEqual(self.decision(), "ACCEPT")

    def test_postgresql_wrong_identity_attempt_or_secret_boundary_rejects(self) -> None:
        for overrides in (
            {"postgresql_package_id": "PostgreSQL.PostgreSQL.15"},
            {"postgresql_installer_version": "16.14-1"},
            {"postgresql_installer_sha256": "0" * 64},
            {"postgresql_installer_path": r"C:\Temp\postgresql.exe"},
            {"postgresql_installation_mode": "unattended"},
            {"postgresql_winget_unattended_execution": True},
            {"postgresql_authenticode_status": "UnknownError"},
            {"postgresql_installer_signer": "Unknown"},
            {"postgresql_service_name": "AshareV3-PostgreSQL-16"},
            {"postgresql_service_account": r"NT AUTHORITY\NetworkService"},
            {"postgresql_networkservice_final_identity": True},
            {"postgresql_transient_installer_identity": r"LocalSystem"},
            {"postgresql_service_identity_transition_attempts": 2},
            {"postgresql_service_stopped_before_transition": False},
            {"postgresql_service_sid_type": "NONE"},
            {"postgresql_networkservice_acl_count_final": 1},
            {"postgresql_empty_business_db": False},
            {"postgresql_loopback_5432_verified": False},
            {"postgresql_service_logon_only": False},
            {"postgresql_interactive_logons_denied": False},
            {"postgresql_secret_entered_only_in_elevated_gui": False},
            {"postgresql_secret_redaction_audit_passed": False},
            {"postgresql_secret_value_or_hash_recorded": True},
            {"postgres_local_account_create_attempts": 1},
            {"postgres_secret_command_line_or_process_argv_attempts": 1},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.decision(**overrides), "REJECT")

    def test_python311_missing_or_damaged_allows_one_exact_repair(self) -> None:
        contract = self.policy["python311_contract"]
        self.assertEqual(contract["package_id"], "Python.Python.3.11")
        self.assertEqual(contract["install_root"], r"C:\Program Files\Python311")
        self.assertEqual(contract["scope"], "machine_wide_x64")
        self.assertEqual(contract["version_constraint"], "3.11.x")
        self.assertEqual(self.decision(), "ACCEPT")
        self.assertEqual(
            self.decision(python311_preflight_state="damaged_native_3_11"),
            "ACCEPT",
        )
        self.assertEqual(
            self.decision(
                python311_preflight_state="valid_native_3_11_x64",
                python311_install_or_repair_attempts=0,
            ),
            "ACCEPT",
        )

    def test_python311_wrong_boundary_or_multiple_attempts_rejects(self) -> None:
        for overrides in (
            {"python311_preflight_state": "valid_native_3_11_x64"},
            {"python311_preflight_state": "unknown"},
            {"python311_package_id": "Python.Python.3.12"},
            {"python311_install_root": r"C:\Users\47894\Python311"},
            {"python311_python_executable": r"C:\Windows\python.exe"},
            {"python311_resolved_version": "3.12.0"},
            {"python311_install_or_repair_attempts": 2},
            {"python311_official_publisher_signer_sha256_frozen": False},
            {"python311_current_safe_patch_resolved": False},
            {"python311_machine_wide_x64": False},
            {"python311_post_verify_complete": False},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.decision(**overrides), "REJECT")

    def test_scheduler_inventory_is_dynamic_and_all_frozen_tasks_disable(self) -> None:
        inventory = self.policy["exact_allowlist"]["scheduler_inventory_contract"]
        self.assertTrue(inventory["dynamic_preflight_exact_inventory_required"])
        self.assertTrue(inventory["fixed_task_count_as_execution_authority_forbidden"])
        self.assertEqual(self.decision(scheduler_current_count=9), "ACCEPT")
        self.assertEqual(self.decision(scheduler_current_count=10), "ACCEPT")
        self.assertEqual(
            self.decision(scheduler_dynamic_inventory_frozen=False), "REJECT"
        )
        self.assertEqual(
            self.decision(scheduler_fixed_count_used_as_authority=True), "REJECT"
        )
        self.assertEqual(
            self.decision(scheduler_after_every_frozen_task_disabled=False),
            "REJECT",
        )

    def test_compiler_matches_exact_policy_phases_resources_and_forbidden(self) -> None:
        compiler = self.compiler
        for phase in self.policy["phase_contract"]["allowed_phase_modes"]:
            self.assertIn(phase, compiler)
        allowlist = self.policy["exact_allowlist"]
        for value in (
            allowlist["legacy_service_name"],
            *allowlist["software_package_ids"],
            allowlist["postgresql_install_root"],
            allowlist["postgresql_backup_staging"],
            allowlist["postgresql_service_account"],
            self.policy["python311_contract"]["install_root"],
        ):
            self.assertIn(value, compiler)
        for value in self.policy["n1_handoff"]["forbidden_sources"][:2]:
            self.assertIn(value, compiler)
        self.assertIn("PLAN exact phase", compiler)
        self.assertIn("-> VALIDATE", compiler)
        self.assertIn("-> MODIFY", compiler)
        self.assertIn("-> VERIFY", compiler)
        self.assertIn("-> FINALIZE", compiler)
        self.assertIn("Compiler success alone does not authorize W0", compiler)

    def test_missing_any_mandatory_control_document_fails(self) -> None:
        missing = ROOT / "docs" / "__missing_w0_control_document__.md"
        for field in (
            "agents_path",
            "compiler_path",
            "kernel_path",
            "runtime_gate_path",
            "sandbox_path",
            "trace_path",
            "test_suite_path",
        ):
            kwargs = {field: missing}
            with self.subTest(field=field), self.assertRaises(FileNotFoundError):
                load_control_contracts(**kwargs)

    def test_full_chain_freezes_dual_sids_and_wsl_interop_isolation(self) -> None:
        plan = (ROOT / "docs" / "WINDOWS_REBUILD_V1_TEST_PLAN.md").read_text(
            encoding="utf-8"
        )
        for name, document in (
            ("Compiler", self.compiler),
            ("RuntimeGate", self.runtime_gate),
            ("Sandbox", self.sandbox),
            ("Trace", self.trace),
            ("TestSuite", self.test_suite),
            ("W0Plan", plan),
        ):
            with self.subTest(document=name):
                self.assertIn(
                    "S-1-5-21-2072264739-3883739137-88032818-1006", document
                )
                self.assertIn(
                    "S-1-5-21-2072264739-3883739137-88032818-1002", document
                )
                self.assertIn("enabled=false", document)
                self.assertIn("appendWindowsPath=false", document)
                self.assertIn("/mnt/d", document)

    def test_runtime_gate_matches_policy_and_general_runtime_rejects(self) -> None:
        gate = self.runtime_gate
        self.assertIn("general Windows setup request to `REJECT`", gate)
        self.assertIn("named_policy_evaluated=true", gate)
        self.assertIn("named_policy_passed=true", gate)
        self.assertIn("semantically equal", gate)
        self.assertIn("w0_prepare_and_mutate", gate)
        self.assertIn("wsl_shutdown_native_control", gate)
        self.assertIn("RESTART_REQUIRED", gate)
        for value in (
            self.policy["exact_allowlist"]["legacy_service_name"],
            *self.policy["exact_allowlist"]["software_package_ids"],
            *self.policy["n1_handoff"]["forbidden_sources"][:2],
        ):
            self.assertIn(value, gate)
        self.assertTrue(self.policy["governance_session_cannot_execute"])

    def test_trace_matches_phases_counts_and_incomplete_evidence_rejects(self) -> None:
        trace = self.trace
        for value in (
            "append-only",
            "before/after evidence hashes",
            "attempt number (exactly one)",
            "counts by exact resource",
            "RESTART_REQUIRED",
            "reconnect",
            "forbidden count is zero",
            "incomplete evidence",
            "fail-closed",
            "C is visible and D is absent",
        ):
            self.assertIn(value, trace)
        for phase in self.policy["phase_contract"]["allowed_phase_modes"]:
            self.assertIn(phase, trace)
        for value in (
            self.policy["exact_allowlist"]["legacy_service_name"],
            *self.policy["n1_handoff"]["forbidden_sources"][:2],
            self.policy["python311_contract"]["package_id"],
            self.policy["python311_contract"]["install_root"],
        ):
            self.assertIn(value, trace)

    def test_test_suite_registers_full_chain_and_exact_negative_boundaries(
        self,
    ) -> None:
        suite = self.test_suite
        for value in (
            "five-way AGENTS/Compiler/Kernel/RuntimeGate/Sandbox consistency",
            "six-way consistency when Trace is included",
            "seventh full-chain control document",
            "Missing",
            "any document",
            "mutually exclusive",
            "one attempt each",
            "Exact negative-boundary tests",
            "zero N1-N6 runtime or data",
            "zero Mac dump/record/source_version/evidence import",
            "zero Tushare or",
            "Mootdx install/import/call",
            "current WSL/SSH self-disconnect",
            "never executes W0",
            "Python.Python.3.11",
            "C:\\Program Files\\Python311",
            "10-to-9",
        ):
            self.assertIn(value, suite)
        for phase in self.policy["phase_contract"]["allowed_phase_modes"]:
            self.assertIn(phase, suite)
        self.assertTrue(self.policy["governance_session_cannot_execute"])

    def test_postgresql_v5_semantics_are_present_across_full_chain(self) -> None:
        plan = (ROOT / "docs" / "WINDOWS_REBUILD_V1_TEST_PLAN.md").read_text(
            encoding="utf-8"
        )
        documents = {
            "Compiler": self.compiler,
            "RuntimeGate": self.runtime_gate,
            "Sandbox": self.sandbox,
            "Trace": self.trace,
            "TestSuite": self.test_suite,
            "W0Plan": plan,
        }
        for name, document in documents.items():
            with self.subTest(document=name):
                for value in (
                    "16.15-1",
                    "postgresql-x64-16",
                    r"NT SERVICE\postgresql-x64-16",
                    "DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2",
                    "EnterpriseDB Corporation",
                    "Valid",
                    r"NT AUTHORITY\NetworkService",
                    "UNRESTRICTED",
                    r"C:\AshareV3\staging\installers\postgresql-16.15-1-windows-x64-download-v1.exe",
                ):
                    self.assertIn(value, document)
                self.assertRegex(document, r"(?i)GUI")
                self.assertRegex(document, r"(?i)secret|password")
                self.assertRegex(document, r"(?i)log|evidence")

    def test_sandbox_matches_policy_and_simulation_never_executes(self) -> None:
        sandbox = self.sandbox
        self.assertIn("Sandbox Simulation", sandbox)
        self.assertIn("mutation count zero before simulation", sandbox)
        self.assertIn("a simulation `PASS` is not execution", sandbox)
        self.assertIn("policy-definition governance", sandbox)
        self.assertIn("session always predicts `REJECT`", sandbox)
        self.assertIn("fail-closed `REJECT`", sandbox)
        self.assertIn("RESTART_REQUIRED", sandbox)
        self.assertIn(
            "current WSL/SSH session attempting to disconnect itself", sandbox
        )
        for phase in self.policy["phase_contract"]["allowed_phase_modes"]:
            self.assertIn(phase, sandbox)
        allowlist = self.policy["exact_allowlist"]
        for value in (
            allowlist["legacy_service_name"],
            *allowlist["software_package_ids"],
            allowlist["postgresql_install_root"],
            allowlist["postgresql_data_directory"],
            allowlist["postgresql_backup_staging"],
            allowlist["postgresql_service_name"],
            allowlist["postgresql_service_account"],
            allowlist["postgresql_listen_addresses"],
            self.policy["python311_contract"]["install_root"],
        ):
            self.assertIn(value, sandbox)
        for path in allowlist["c_directories"]:
            self.assertIn(path.rsplit("\\", 1)[-1], sandbox)
        for value in self.policy["n1_handoff"]["forbidden_sources"][:2]:
            self.assertIn(value, sandbox)
        self.assertTrue(self.policy["governance_session_cannot_execute"])

    def test_control_plan_references_policy_and_new_empty_cluster(self) -> None:
        plan = (ROOT / "docs" / "WINDOWS_REBUILD_V1_TEST_PLAN.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(POLICY_ID, plan)
        self.assertRegex(plan, r"new empty\s+cluster")
        self.assertIn("Tushare, Mootdx", plan)
        self.assertIn("otherwise fail closed", plan)
        self.assertIn("Build the three-year daily-bar base from zero", plan)
        self.assertIn("never use a Mac database dump", plan)
        self.assertIn("Python.Python.3.11", plan)
        self.assertIn(r"C:\Program Files\Python311", plan)
        self.assertIn("never use a fixed", plan)


if __name__ == "__main__":
    unittest.main()
