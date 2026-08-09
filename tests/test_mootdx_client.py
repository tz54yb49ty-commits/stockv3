from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import patch

from ashare_v3.mootdx_client import (
    DEFAULT_ENDPOINT_POOL_PATH,
    EndpointConfig,
    MootdxEndpointConfigError,
    MootdxEndpointManager,
    MootdxEndpointSelectionError,
    build_n1_protocol_probe,
    create_mootdx_client,
)


PASSING_CHECKS = {
    "stock_quote": True,
    "stock_daily_bars": True,
    "index_daily_bars": True,
    "scope_sentinels": True,
}


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class FakeCreatedClient:
    def __init__(self, server):
        self.server = server
        self.closed = False

    def close(self):
        self.closed = True


class CountingProbeClient(FakeCreatedClient):
    def __init__(self, server, *, close_error=False):
        super().__init__(server)
        self.close_count = 0
        self.close_error = close_error

    def close(self):
        self.close_count += 1
        self.closed = True
        if self.close_error:
            raise RuntimeError("fake close failure")


def endpoint(
    endpoint_id: str,
    host: str,
    priority: int,
    *,
    enabled: bool = True,
    quarantined: bool = False,
) -> EndpointConfig:
    return EndpointConfig(
        endpoint_id=endpoint_id,
        host=host,
        port=7709,
        priority=priority,
        enabled=enabled,
        quarantined=quarantined,
        provenance_url="https://example.invalid/frozen",
        provenance_commit="3b7ce97f2a6942cf9f39e25ee29c4e113bcfc69f",
        local_validation_status="protocol_passed",
    )


def manager(
    cache_path: Path,
    *,
    clock=None,
    primary_host: str = "115.238.56.198",
    mode: str = "observe",
) -> MootdxEndpointManager:
    return MootdxEndpointManager(
        endpoint_pool_version="test-pool-v1",
        transport="mootdx",
        endpoints=(
            endpoint("primary", primary_host, 10),
            endpoint("secondary", "180.153.18.170", 20),
            endpoint("quarantined", "124.71.187.122", 90, enabled=False, quarantined=True),
        ),
        n1_failover_mode=mode,
        n3_failover_mode=mode,
        circuit_open_seconds=300,
        required_empty_object_threshold=3,
        health_cache_path=cache_path,
        clock=clock,
    )


class MootdxEndpointManagerTest(unittest.TestCase):
    def test_canonical_config_freezes_pool_authority_and_ignores_tempting_external_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = MootdxEndpointManager.from_toml(
                DEFAULT_ENDPOINT_POOL_PATH,
                health_cache_path=Path(tmp) / "health.json",
            )

        self.assertEqual(endpoint_manager.endpoint_pool_version, "mootdx-endpoint-pool-v1")
        enabled = [row for row in endpoint_manager.endpoints if row.enabled]
        self.assertEqual(
            [(row.host, row.port) for row in enabled],
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )
        self.assertNotIn("218.6.170.47", [row.host for row in enabled])
        self.assertTrue(
            all(
                row.provenance_commit == "3b7ce97f2a6942cf9f39e25ee29c4e113bcfc69f"
                for row in endpoint_manager.endpoints
            )
        )

    def test_missing_canonical_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(MootdxEndpointConfigError, "config missing"):
                MootdxEndpointManager.from_toml(
                    Path(tmp) / "missing.toml",
                    health_cache_path=Path(tmp) / "health.json",
                )

    def test_invalid_duplicate_server_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(MootdxEndpointConfigError, "duplicate endpoint server"):
                MootdxEndpointManager(
                    endpoint_pool_version="test",
                    transport="mootdx",
                    endpoints=(
                        endpoint("one", "115.238.56.198", 10),
                        endpoint("two", "115.238.56.198", 20),
                    ),
                    n1_failover_mode="observe",
                    n3_failover_mode="observe",
                    circuit_open_seconds=300,
                    required_empty_object_threshold=3,
                    health_cache_path=Path(tmp) / "health.json",
                )

    def test_enabled_endpoint_without_protocol_passed_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            invalid = replace(
                endpoint("primary", "115.238.56.198", 10),
                local_validation_status="pending",
            )
            with self.assertRaisesRegex(
                MootdxEndpointConfigError,
                "local_validation_status=protocol_passed",
            ):
                MootdxEndpointManager(
                    endpoint_pool_version="test",
                    transport="mootdx",
                    endpoints=(invalid,),
                    n1_failover_mode="observe",
                    n3_failover_mode="observe",
                    circuit_open_seconds=300,
                    required_empty_object_threshold=3,
                    health_cache_path=Path(tmp) / "health.json",
                )

    def test_stable_priority_selects_primary_when_both_protocol_probes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            endpoint_manager = manager(Path(tmp) / "health.json")

            selection = endpoint_manager.select_for_run(
                run_id="n1-test",
                attempt_id="attempt-1",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(calls, ["primary", "secondary"])
        self.assertEqual(selection.endpoint_id, "primary")
        self.assertTrue(selection.selectable)
        self.assertEqual(selection.selection_reason, "stable_priority_primary_healthy")
        self.assertFalse(selection.failover_performed)
        provenance = selection.to_provenance()
        self.assertEqual(provenance["attempt_id"], "attempt-1")
        self.assertEqual(
            [row["endpoint_id"] for row in provenance["endpoint_probe_results"]],
            ["primary", "secondary", "quarantined"],
        )
        self.assertTrue(
            all(
                row["passed"] is True
                for row in provenance["endpoint_probe_results"][:2]
            )
        )
        self.assertEqual(
            provenance["endpoint_probe_results"][2]["excluded_reason"],
            "quarantined",
        )
        self.assertEqual(
            provenance["pool_probe_summary"]["passed_endpoint_ids"],
            ["primary", "secondary"],
        )

    def test_observe_mode_records_would_switch_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")

            selection = endpoint_manager.select_for_run(
                run_id="n1-test",
                attempt_id="attempt-observe",
                probe=lambda row, make_client: {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**PASSING_CHECKS, "scope_sentinels": False}
                    )
                },
            )

        self.assertEqual(selection.endpoint_id, "primary")
        self.assertFalse(selection.selectable)
        self.assertEqual(selection.would_switch_to, "secondary")
        self.assertFalse(selection.failover_performed)
        self.assertEqual(selection.failover_reason, "primary_mandatory_probe_failed")
        probe_results = selection.to_provenance()["endpoint_probe_results"]
        self.assertFalse(probe_results[0]["passed"])
        self.assertTrue(probe_results[1]["passed"])
        with self.assertRaisesRegex(MootdxEndpointSelectionError, "fail-closed"):
            create_mootdx_client(
                selection,
                quotes_factory=lambda **kwargs: FakeCreatedClient(kwargs["server"]),
            )

    def test_secondary_unhealthy_is_authoritative_even_when_primary_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selection = manager(Path(tmp) / "health.json").select_for_run(
                run_id="secondary-unhealthy",
                probe=lambda row, make_client: {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "primary"
                        else {**PASSING_CHECKS, "index_daily_bars": False}
                    )
                },
            )

        provenance = selection.to_provenance()
        self.assertTrue(selection.selectable)
        self.assertEqual(selection.endpoint_id, "primary")
        self.assertEqual(
            provenance["pool_probe_summary"]["failed_endpoint_ids"],
            ["secondary"],
        )
        secondary = provenance["endpoint_probe_results"][1]
        self.assertEqual(secondary["state"], "degraded")
        self.assertEqual(secondary["failure_kind"], "mandatory_probe_failed")

    def test_enabled_quarantined_endpoint_is_recorded_without_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            endpoint_manager = manager(Path(tmp) / "health.json")
            selection = endpoint_manager.select_for_run(
                run_id="quarantine",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(calls, ["primary", "secondary"])
        excluded = selection.to_provenance()["endpoint_probe_results"][2]
        self.assertEqual(excluded["endpoint_id"], "quarantined")
        self.assertEqual(excluded["excluded_reason"], "quarantined")
        self.assertFalse(excluded["passed"])
        self.assertFalse(excluded["enabled"])

    def test_disabled_and_quarantined_pool_rows_are_excluded_without_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            endpoint_manager = MootdxEndpointManager(
                endpoint_pool_version="test-pool-v1",
                transport="mootdx",
                endpoints=(
                    endpoint("primary", "115.238.56.198", 10),
                    endpoint(
                        "disabled",
                        "180.153.18.171",
                        20,
                        enabled=False,
                    ),
                    endpoint(
                        "quarantined",
                        "124.71.187.122",
                        30,
                        enabled=False,
                        quarantined=True,
                    ),
                ),
                n1_failover_mode="observe",
                n3_failover_mode="observe",
                circuit_open_seconds=300,
                required_empty_object_threshold=3,
                health_cache_path=Path(tmp) / "health.json",
            )
            selection = endpoint_manager.select_for_run(
                run_id="disabled-pool-row",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(calls, ["primary"])
        results = selection.to_provenance()["endpoint_probe_results"]
        self.assertEqual(
            [(row["endpoint_id"], row["excluded_reason"]) for row in results],
            [
                ("primary", None),
                ("disabled", "disabled"),
                ("quarantined", "quarantined"),
            ],
        )

    def test_pool_without_enabled_non_quarantined_endpoint_fails_before_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []
            endpoint_manager = MootdxEndpointManager(
                endpoint_pool_version="test-pool-v1",
                transport="mootdx",
                endpoints=(
                    endpoint("disabled", "180.153.18.171", 10, enabled=False),
                    endpoint(
                        "quarantined",
                        "124.71.187.122",
                        20,
                        enabled=False,
                        quarantined=True,
                    ),
                ),
                n1_failover_mode="observe",
                n3_failover_mode="active",
                circuit_open_seconds=300,
                required_empty_object_threshold=3,
                health_cache_path=Path(tmp) / "health.json",
            )
            with self.assertRaisesRegex(
                MootdxEndpointConfigError,
                "no enabled non-quarantined endpoint",
            ):
                endpoint_manager.select_for_run(
                    run_id="no-usable-endpoint",
                    probe=lambda row, make_client: calls.append(row.endpoint_id)
                    or {"checks": dict(PASSING_CHECKS)},
                )

        self.assertEqual(calls, [])

    def test_n1_and_n3_failover_modes_are_selected_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = MootdxEndpointManager(
                endpoint_pool_version="test-pool-v1",
                transport="mootdx",
                endpoints=(
                    endpoint("primary", "115.238.56.198", 10),
                    endpoint("secondary", "180.153.18.170", 20),
                ),
                n1_failover_mode="observe",
                n3_failover_mode="active",
                circuit_open_seconds=300,
                required_empty_object_threshold=3,
                health_cache_path=Path(tmp) / "health.json",
            )

            def probe(row, make_client):
                return {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**PASSING_CHECKS, "stock_quote": False}
                    )
                }

            n1_selection = endpoint_manager.select_for_run(
                run_id="n1-observe",
                probe=probe,
            )
            n3_selection = endpoint_manager.select_for_batch(
                batch_id="n3-active",
                probe=probe,
            )

        self.assertEqual(n1_selection.failover_mode, "observe")
        self.assertFalse(n1_selection.selectable)
        self.assertEqual(n1_selection.would_switch_to, "secondary")
        self.assertEqual(n3_selection.failover_mode, "active")
        self.assertTrue(n3_selection.selectable)
        self.assertEqual(n3_selection.endpoint_id, "secondary")

    def test_batch_failover_mode_override_does_not_change_manager_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="observe")

            def probe(row, make_client):
                return {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**PASSING_CHECKS, "stock_quote": False}
                    )
                }

            default_selection = endpoint_manager.select_for_batch(
                batch_id="default-observe",
                probe=probe,
            )
            override_selection = endpoint_manager.select_for_batch(
                batch_id="fastlane-active",
                probe=probe,
                failover_mode="active",
            )

        self.assertEqual(default_selection.failover_mode, "observe")
        self.assertFalse(default_selection.selectable)
        self.assertEqual(override_selection.failover_mode, "active")
        self.assertTrue(override_selection.selectable)
        self.assertEqual(override_selection.endpoint_id, "secondary")
        self.assertEqual(endpoint_manager.n3_failover_mode, "observe")

    def test_batch_failover_mode_override_rejects_unknown_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            with self.assertRaisesRegex(
                MootdxEndpointConfigError,
                "failover_mode must be one of",
            ):
                endpoint_manager.select_for_batch(
                    batch_id="invalid-override",
                    probe=lambda row, make_client: {
                        "checks": dict(PASSING_CHECKS)
                    },
                    failover_mode="unexpected",
                )

    def test_active_mode_primary_probe_failure_selects_stable_secondary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")

            selection = endpoint_manager.select_for_run(
                run_id="n1-active",
                attempt_id="active-attempt-1",
                probe=lambda row, make_client: {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**PASSING_CHECKS, "stock_quote": False}
                    )
                },
            )

        self.assertEqual(selection.endpoint_id, "secondary")
        self.assertTrue(selection.selectable)
        self.assertTrue(selection.failover_performed)
        self.assertEqual(selection.failover_from, "primary")
        self.assertEqual(selection.selection_reason, "active_failover_to_stable_secondary")

    def test_runtime_transport_failure_keeps_primary_open_for_next_active_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            first = endpoint_manager.select_for_run(
                run_id="first",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            self.assertEqual(first.endpoint_id, "primary")
            endpoint_manager.record_transport_failure(
                "primary",
                failure_kind="source_fetch_transport_exception",
            )
            probe_calls: list[str] = []
            second = endpoint_manager.select_for_run(
                run_id="second",
                probe=lambda row, make_client: probe_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(probe_calls, ["secondary"])
        self.assertEqual(second.endpoint_id, "secondary")
        self.assertTrue(second.failover_performed)
        self.assertEqual(second.failover_from, "primary")

    def test_transport_failures_are_isolated_for_same_endpoint_in_both_directions(self) -> None:
        for failed_transport, rollback_transport in (
            ("tdxpy", "mootdx"),
            ("mootdx", "tdxpy"),
        ):
            with self.subTest(failed_transport=failed_transport):
                with tempfile.TemporaryDirectory() as tmp:
                    endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
                    endpoint_manager.record_transport_failure(
                        "primary",
                        transport=failed_transport,
                        failure_kind="isolated_runtime_failure",
                    )
                    rollback_calls: list[str] = []
                    rollback = endpoint_manager.select_for_run(
                        run_id=f"rollback-{rollback_transport}",
                        transport=rollback_transport,
                        probe=lambda row, make_client: rollback_calls.append(row.endpoint_id)
                        or {"checks": dict(PASSING_CHECKS)},
                    )
                    failed_calls: list[str] = []
                    failed = endpoint_manager.select_for_run(
                        run_id=f"failed-{failed_transport}",
                        transport=failed_transport,
                        probe=lambda row, make_client: failed_calls.append(row.endpoint_id)
                        or {"checks": dict(PASSING_CHECKS)},
                    )

                self.assertEqual(rollback_calls, ["primary", "secondary"])
                self.assertEqual(rollback.endpoint_id, "primary")
                self.assertEqual(failed_calls, ["secondary"])
                self.assertEqual(failed.endpoint_id, "secondary")
                open_result = failed.to_provenance()["endpoint_probe_results"][0]
                self.assertEqual(open_result["state"], "open")
                self.assertEqual(open_result["excluded_reason"], "circuit_open")
                self.assertTrue(
                    all(value is None for value in open_result["checks"].values())
                )

    def test_empty_object_circuit_is_transport_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            for suffix in ("001", "002", "003"):
                endpoint_manager.record_required_object_result(
                    "primary",
                    transport="tdxpy",
                    empty=True,
                    object_identity=f"board:881{suffix}",
                )
            mootdx_calls: list[str] = []
            mootdx_selection = endpoint_manager.select_for_run(
                run_id="mootdx-rollback",
                transport="mootdx",
                probe=lambda row, make_client: mootdx_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )
            tdxpy_calls: list[str] = []
            tdxpy_selection = endpoint_manager.select_for_run(
                run_id="tdxpy-open",
                transport="tdxpy",
                probe=lambda row, make_client: tdxpy_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(mootdx_calls, ["primary", "secondary"])
        self.assertEqual(mootdx_selection.endpoint_id, "primary")
        self.assertEqual(tdxpy_calls, ["secondary"])
        self.assertEqual(tdxpy_selection.endpoint_id, "secondary")

    def test_half_open_lease_is_transport_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            endpoint_manager = manager(Path(tmp) / "health.json", clock=clock, mode="active")
            endpoint_manager.record_transport_failure(
                "primary",
                transport="tdxpy",
                failure_kind="prime_tdxpy_open",
            )
            clock.value += timedelta(seconds=301)
            with self.assertRaises(KeyboardInterrupt):
                endpoint_manager._probe_endpoint(
                    endpoint_manager.endpoints[0],
                    transport="tdxpy",
                    probe=lambda row, make_client: (_ for _ in ()).throw(
                        KeyboardInterrupt()
                    ),
                    required_checks=tuple(PASSING_CHECKS),
                )
            mootdx_calls: list[str] = []
            mootdx_selection = endpoint_manager.select_for_run(
                run_id="mootdx-during-tdxpy-lease",
                transport="mootdx",
                probe=lambda row, make_client: mootdx_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )
            tdxpy_calls: list[str] = []
            tdxpy_selection = endpoint_manager.select_for_run(
                run_id="tdxpy-lease-held",
                transport="tdxpy",
                probe=lambda row, make_client: tdxpy_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(mootdx_calls, ["primary", "secondary"])
        self.assertEqual(mootdx_selection.endpoint_id, "primary")
        self.assertEqual(tdxpy_calls, ["secondary"])
        self.assertEqual(
            tdxpy_selection.to_provenance()["endpoint_probe_results"][0]["excluded_reason"],
            "half_open_lease_held",
        )

    def test_observe_probes_secondary_but_never_constructs_secondary_business_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            probe_calls: list[str] = []
            business_calls: list[dict] = []
            selection = endpoint_manager.select_for_run(
                run_id="observe",
                probe=lambda row, make_client: probe_calls.append(row.endpoint_id)
                or {
                    "checks": (
                        dict(PASSING_CHECKS)
                        if row.endpoint_id == "secondary"
                        else {**PASSING_CHECKS, "scope_sentinels": False}
                    )
                },
            )
            with self.assertRaises(MootdxEndpointSelectionError):
                create_mootdx_client(
                    selection,
                    quotes_factory=lambda **kwargs: business_calls.append(kwargs)
                    or FakeCreatedClient(kwargs["server"]),
                )

        self.assertEqual(probe_calls, ["primary", "secondary"])
        self.assertEqual(business_calls, [])

    def test_missing_mandatory_probe_authority_is_not_treated_as_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")

            selection = endpoint_manager.select_for_batch(
                batch_id="n3-test",
                probe=lambda row, make_client: {"checks": {"stock_quote": True}},
            )

        self.assertFalse(selection.selectable)
        self.assertEqual(selection.selection_reason, "all_enabled_endpoints_unhealthy")

    def test_circuit_opens_then_allows_one_half_open_probe_and_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            endpoint_manager = manager(Path(tmp) / "health.json", clock=clock)
            failing = lambda row, make_client: {
                "checks": {**PASSING_CHECKS, "stock_quote": False}
            }
            endpoint_manager.select_for_run(run_id="first", probe=failing)
            endpoint_manager.select_for_run(run_id="second", probe=failing)
            probe_calls: list[str] = []
            endpoint_manager.select_for_run(
                run_id="still-open",
                probe=lambda row, make_client: probe_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )
            self.assertEqual(probe_calls, [])

            clock.value += timedelta(seconds=301)
            recovered = endpoint_manager.select_for_run(
                run_id="half-open",
                probe=lambda row, make_client: probe_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(probe_calls, ["primary", "secondary"])
        self.assertTrue(recovered.selectable)
        self.assertEqual(recovered.health_state, "healthy")

    def test_two_managers_share_one_half_open_claim_after_cache_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            cache_path = Path(tmp) / "health.json"
            first_manager = manager(cache_path, clock=clock)
            second_manager = manager(cache_path, clock=clock)
            failing = lambda row, make_client: {
                "checks": {**PASSING_CHECKS, "stock_quote": False}
            }
            first_manager.select_for_run(run_id="first", probe=failing)
            first_manager.select_for_run(run_id="second", probe=failing)
            clock.value += timedelta(seconds=301)
            primary_probe_calls: list[str] = []
            nested_probe_calls: list[str] = []

            def first_probe(row, make_client):
                primary_probe_calls.append(row.endpoint_id)
                if row.endpoint_id == "primary":
                    second_manager.select_for_run(
                        run_id="nested",
                        probe=lambda nested_row, nested_client: nested_probe_calls.append(
                            nested_row.endpoint_id
                        )
                        or {"checks": dict(PASSING_CHECKS)},
                    )
                return {"checks": dict(PASSING_CHECKS)}

            recovered = first_manager.select_for_run(
                run_id="half-open-owner",
                probe=first_probe,
            )

        self.assertEqual(primary_probe_calls.count("primary"), 1)
        self.assertNotIn("primary", nested_probe_calls)
        self.assertTrue(recovered.selectable)
        self.assertEqual(recovered.endpoint_id, "primary")

    def test_crashed_half_open_claim_expires_and_allows_one_new_claimant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            cache_path = Path(tmp) / "health.json"
            crashed_manager = manager(cache_path, clock=clock, mode="active")
            crashed_manager.record_transport_failure(
                "primary",
                failure_kind="prime_open_state",
            )
            clock.value += timedelta(seconds=301)

            with self.assertRaises(KeyboardInterrupt):
                crashed_manager._probe_endpoint(
                    crashed_manager.endpoints[0],
                    probe=lambda row, make_client: (_ for _ in ()).throw(
                        KeyboardInterrupt()
                    ),
                    required_checks=tuple(PASSING_CHECKS),
                )

            waiting_manager = manager(cache_path, clock=clock, mode="active")
            waiting_calls: list[str] = []
            waiting_manager.select_for_run(
                run_id="lease-still-live",
                probe=lambda row, make_client: waiting_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )
            self.assertNotIn("primary", waiting_calls)

            clock.value += timedelta(seconds=301)
            recovering_manager = manager(cache_path, clock=clock, mode="active")
            recovery_calls: list[str] = []
            recovered = recovering_manager.select_for_run(
                run_id="lease-expired",
                probe=lambda row, make_client: recovery_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(recovery_calls.count("primary"), 1)
        self.assertEqual(recovered.endpoint_id, "primary")
        self.assertTrue(recovered.selectable)

    def test_expired_old_claim_result_cannot_overwrite_new_claim_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            cache_path = Path(tmp) / "health.json"
            old_manager = manager(cache_path, clock=clock, mode="active")
            new_manager = manager(cache_path, clock=clock, mode="active")
            old_manager.record_transport_failure(
                "primary",
                failure_kind="prime_open_state",
            )
            clock.value += timedelta(seconds=301)

            def old_probe(row, make_client):
                clock.value += timedelta(seconds=301)
                new_result = new_manager._probe_endpoint(
                    new_manager.endpoints[0],
                    probe=lambda new_row, new_client: {
                        "checks": dict(PASSING_CHECKS),
                        "claimant": "new",
                    },
                    required_checks=tuple(PASSING_CHECKS),
                )
                self.assertTrue(new_result)
                return {
                    "checks": {**PASSING_CHECKS, "stock_quote": False},
                    "claimant": "old",
                }

            old_result = old_manager._probe_endpoint(
                old_manager.endpoints[0],
                probe=old_probe,
                required_checks=tuple(PASSING_CHECKS),
            )
            payload = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertFalse(old_result)
        primary = payload["transports"]["mootdx"]["primary"]
        self.assertEqual(primary["state"], "healthy")
        self.assertEqual(primary["probe_summary"]["claimant"], "new")
        self.assertIsNone(primary["half_open_token"])
        self.assertIsNone(primary["half_open_until"])

    def test_manager_reloads_transport_failure_written_by_another_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "health.json"
            first_manager = manager(cache_path, mode="active")
            stale_manager = manager(cache_path, mode="active")
            first_manager.record_transport_failure(
                "primary",
                failure_kind="other_process_transport_failure",
            )
            calls: list[str] = []

            selected = stale_manager.select_for_run(
                run_id="reload-before-select",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(calls, ["secondary"])
        self.assertEqual(selected.endpoint_id, "secondary")
        self.assertTrue(selected.failover_performed)

    def test_inflight_probe_does_not_overwrite_newer_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "health.json"
            probing_manager = manager(cache_path, mode="active")
            failing_manager = manager(cache_path, mode="active")

            def probe(row, make_client):
                if row.endpoint_id == "primary":
                    failing_manager.record_transport_failure(
                        "primary",
                        failure_kind="concurrent_runtime_failure",
                    )
                return {"checks": dict(PASSING_CHECKS)}

            selected = probing_manager.select_for_run(
                run_id="compare-after-probe",
                probe=probe,
            )

        self.assertEqual(selected.endpoint_id, "secondary")
        self.assertTrue(selected.failover_performed)

    def test_three_consecutive_required_empty_objects_open_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")

            self.assertFalse(
                endpoint_manager.record_required_object_result(
                    "primary", empty=True, object_identity="board:881001"
                )
            )
            self.assertFalse(
                endpoint_manager.record_required_object_result(
                    "primary", empty=True, object_identity="board:881002"
                )
            )
            self.assertTrue(
                endpoint_manager.record_required_object_result(
                    "primary", empty=True, object_identity="board:881003"
                )
            )
            selection = endpoint_manager.select_for_run(
                run_id="blocked-open",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )

        self.assertFalse(selection.selectable)
        self.assertEqual(selection.would_switch_to, "secondary")

    def test_endpoint_wide_empty_incident_is_recorded_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "health.json"
            clock = MutableClock()
            endpoint_manager = manager(cache_path, clock=clock)
            write_health = endpoint_manager._write_health_cache_unlocked
            with patch.object(
                endpoint_manager,
                "_write_health_cache_unlocked",
                wraps=write_health,
            ) as write_health_mock:
                results = [
                    endpoint_manager.record_required_object_result(
                        "primary",
                        empty=True,
                        object_identity=f"board:88100{index}",
                    )
                    for index in range(1, 4)
                ]
                opened_payload = json.loads(cache_path.read_text(encoding="utf-8"))
                clock.value += timedelta(seconds=30)
                results.extend(
                    endpoint_manager.record_required_object_result(
                        "primary",
                        empty=True,
                        object_identity=f"board:88100{index}",
                    )
                    for index in range(4, 6)
                )
                successful_inflight = (
                    endpoint_manager.record_required_object_result(
                        "primary",
                        empty=False,
                        object_identity="board:881006",
                    )
                )
                final_payload = json.loads(cache_path.read_text(encoding="utf-8"))

        opened_health = opened_payload["transports"]["mootdx"]["primary"]
        final_health = final_payload["transports"]["mootdx"]["primary"]
        self.assertEqual(results, [False, False, True, True, True])
        self.assertFalse(successful_inflight)
        self.assertEqual(write_health_mock.call_count, 3)
        self.assertEqual(final_health["consecutive_failures"], 1)
        self.assertEqual(
            final_health["consecutive_required_empty_objects"],
            3,
        )
        self.assertEqual(final_health["open_until"], opened_health["open_until"])
        self.assertEqual(final_health["checked_at"], opened_health["checked_at"])

    def test_success_without_empty_streak_does_not_rewrite_health_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json", mode="active")
            with patch.object(
                endpoint_manager,
                "_write_health_cache_unlocked",
            ) as write_health:
                endpoint_wide_failure = (
                    endpoint_manager.record_required_object_result(
                        "primary",
                        empty=False,
                        object_identity="stock:SZ:300001",
                    )
                )

        self.assertFalse(endpoint_wide_failure)
        write_health.assert_not_called()

    def test_repeating_same_empty_object_does_not_open_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            results = [
                endpoint_manager.record_required_object_result(
                    "primary",
                    empty=True,
                    object_identity="board:881001",
                )
                for _ in range(3)
            ]
            calls: list[str] = []
            selection = endpoint_manager.select_for_run(
                run_id="same-object-not-endpoint-wide",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(results, [False, False, False])
        self.assertEqual(calls, ["primary", "secondary"])
        self.assertTrue(selection.selectable)
        self.assertEqual(selection.endpoint_id, "primary")

    def test_empty_result_without_identity_fails_before_circuit_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "health.json"
            endpoint_manager = manager(cache_path)

            with self.assertRaisesRegex(MootdxEndpointConfigError, "object_identity is required"):
                endpoint_manager.record_required_object_result(
                    "primary",
                    empty=True,
                    object_identity=None,
                )

            self.assertFalse(cache_path.exists())
            calls: list[str] = []
            selection = endpoint_manager.select_for_run(
                run_id="missing-identity-did-not-open",
                probe=lambda row, make_client: calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(calls, ["primary", "secondary"])
        self.assertEqual(selection.endpoint_id, "primary")
        self.assertTrue(selection.selectable)

    def test_protocol_probe_requires_exact_identity_dates_and_valid_values(self) -> None:
        class ProtocolClient:
            def __init__(self, mutation):
                self.mutation = mutation

            def quotes(self, **kwargs):
                row = {"code": kwargs["symbol"], "price": "10"}
                if self.mutation == "quote_missing_code":
                    row.pop("code")
                return [row]

            def bars(self, **kwargs):
                return self._bars(kwargs["symbol"], stock=True)

            def index(self, **kwargs):
                return self._bars(kwargs["symbol"], stock=False)

            def _bars(self, symbol, *, stock):
                dates = ["2026-05-19", "2026-05-20", "2026-05-21"]
                rows = [
                    {
                        "code": symbol,
                        "datetime": value,
                        "open": "10",
                        "high": "12",
                        "low": "9",
                        "close": "11",
                        "vol": "100",
                        "amount": "1000",
                    }
                    for value in dates
                ]
                if self.mutation == "bar_missing_code" and stock:
                    rows[0].pop("code")
                if self.mutation == "index_wrong_identity" and not stock and symbol == "000001":
                    rows[0]["code"] = "399001"
                if self.mutation == "sentinel_wrong_identity" and symbol == "881001":
                    rows[0]["code"] = "881999"
                if self.mutation == "sentinel_wrong_symbol" and symbol == "881001":
                    rows[0].pop("code")
                    rows[0]["symbol"] = "881999"
                if self.mutation == "sentinel_conflicting_identity" and symbol == "881001":
                    rows[0]["symbol"] = "881999"
                if self.mutation == "sentinel_missing_target" and symbol == "881001":
                    rows = rows[:2]
                if self.mutation == "non_monotonic" and stock:
                    rows[0], rows[1] = rows[1], rows[0]
                if self.mutation == "invalid_ohlc" and stock:
                    rows[0]["high"] = "8"
                return rows

        probe = build_n1_protocol_probe(
            scope_kind="board",
            symbols=("881001",),
            target_trade_date="20260521",
        )
        expected_failed_check = {
            "quote_missing_code": "stock_quote",
            "index_wrong_identity": "index_daily_bars",
            "sentinel_wrong_identity": "scope_sentinels",
            "sentinel_wrong_symbol": "scope_sentinels",
            "sentinel_conflicting_identity": "scope_sentinels",
            "sentinel_missing_target": "scope_sentinels",
            "non_monotonic": "stock_daily_bars",
            "invalid_ohlc": "stock_daily_bars",
        }

        for mutation, failed_check in expected_failed_check.items():
            with self.subTest(mutation=mutation):
                result = probe(
                    endpoint("primary", "115.238.56.198", 10),
                    lambda profile: ProtocolClient(mutation),
                )
                self.assertFalse(result["checks"][failed_check])

        missing_identity_result = probe(
            endpoint("primary", "115.238.56.198", 10),
            lambda profile: ProtocolClient("bar_missing_code"),
        )
        self.assertTrue(missing_identity_result["checks"]["stock_daily_bars"])

    def test_protocol_probe_attaches_requested_identity_to_copied_mootdx_bar_rows(self) -> None:
        class MootdxShapeFrame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                self.orient = orient
                return self.rows

        class MissingIdentityProtocolClient:
            def __init__(self, response_kind):
                self.response_kind = response_kind
                self.source_rows = []

            def quotes(self, **kwargs):
                return [{"code": kwargs["symbol"], "price": "10"}]

            def bars(self, **kwargs):
                return self._response()

            def index(self, **kwargs):
                return self._response()

            def _response(self):
                rows = [
                    {
                        "datetime": value,
                        "open": "10",
                        "high": "12",
                        "low": "9",
                        "close": "11",
                        "vol": "100",
                        "amount": "1000",
                    }
                    for value in ("2026-05-19", "2026-05-20", "2026-05-21")
                ]
                self.source_rows.append(rows)
                if self.response_kind == "frame":
                    return MootdxShapeFrame(rows)
                return rows

        probe = build_n1_protocol_probe(
            scope_kind="board",
            symbols=("881001",),
            target_trade_date="20260521",
        )
        for response_kind in ("frame", "list"):
            with self.subTest(response_kind=response_kind):
                client = MissingIdentityProtocolClient(response_kind)
                result = probe(
                    endpoint("primary", "115.238.56.198", 10),
                    lambda profile: client,
                )

                self.assertEqual(result["checks"], PASSING_CHECKS)
                self.assertTrue(
                    all(
                        "code" not in row and "symbol" not in row
                        for rows in client.source_rows
                        for row in rows
                    )
                )

    def test_probe_close_error_blocks_endpoint_and_is_preserved_in_pool_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            clients = [
                CountingProbeClient(("115.238.56.198", 7709)),
                CountingProbeClient(("115.238.56.198", 7709), close_error=True),
                CountingProbeClient(("180.153.18.170", 7709)),
                CountingProbeClient(("180.153.18.170", 7709)),
            ]

            def probe(row, make_client):
                make_client()
                make_client()
                return {"checks": dict(PASSING_CHECKS)}

            client_index = 0

            def create(selection, profile):
                nonlocal client_index
                client = clients[client_index]
                client_index += 1
                return client

            with patch(
                "ashare_v3.mootdx_client.create_mootdx_client",
                side_effect=create,
            ):
                selection = endpoint_manager.select_for_run(
                    run_id="probe-close-success",
                    probe=probe,
                )

        self.assertFalse(selection.selectable)
        self.assertEqual(selection.would_switch_to, "secondary")
        self.assertEqual([client.close_count for client in clients], [1, 1, 1, 1])
        provenance = selection.to_provenance()
        primary = provenance["endpoint_probe_results"][0]
        secondary = provenance["endpoint_probe_results"][1]
        self.assertEqual(primary["probe_close_errors"], ["RuntimeError"])
        self.assertEqual(primary["failure_kind"], "probe_client_close_failed")
        self.assertFalse(primary["passed"])
        self.assertTrue(secondary["passed"])

    def test_secondary_probe_close_runtime_error_is_authoritative_and_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            clients = [
                CountingProbeClient(("115.238.56.198", 7709)),
                CountingProbeClient(("115.238.56.198", 7709)),
                CountingProbeClient(("180.153.18.170", 7709)),
                CountingProbeClient(("180.153.18.170", 7709), close_error=True),
            ]
            client_index = 0

            def create(selection, profile):
                nonlocal client_index
                client = clients[client_index]
                client_index += 1
                return client

            with patch(
                "ashare_v3.mootdx_client.create_mootdx_client",
                side_effect=create,
            ):
                selection = endpoint_manager.select_for_run(
                    run_id="secondary-close-error",
                    probe=lambda row, make_client: (
                        make_client(),
                        make_client(),
                        {"checks": dict(PASSING_CHECKS)},
                    )[-1],
                )

        self.assertTrue(selection.selectable)
        self.assertEqual(selection.endpoint_id, "primary")
        secondary = selection.to_provenance()["endpoint_probe_results"][1]
        self.assertEqual(secondary["probe_close_errors"], ["RuntimeError"])
        self.assertEqual(secondary["failure_kind"], "probe_client_close_failed")
        self.assertFalse(secondary["passed"])
        self.assertEqual(secondary["state"], "degraded")

    def test_selection_lineage_is_deeply_immutable_and_provenance_is_detached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selection = manager(Path(tmp) / "health.json").select_for_run(
                run_id="deep-freeze",
                probe=lambda row, make_client: {
                    "checks": dict(PASSING_CHECKS),
                    "nested": {"values": ["authoritative"]},
                },
            )

        with self.assertRaises(TypeError):
            selection.probe_summary["nested"]["values"][0] = "mutated"
        with self.assertRaises(TypeError):
            selection.endpoint_probe_results[0]["checks"]["stock_quote"] = False
        first = selection.to_provenance()
        first["probe_summary"]["nested"]["values"][0] = "external"
        first["endpoint_probe_results"][0]["checks"]["stock_quote"] = False
        second = selection.to_provenance()
        self.assertEqual(
            second["probe_summary"]["nested"]["values"],
            ["authoritative"],
        )
        self.assertTrue(
            second["endpoint_probe_results"][0]["checks"]["stock_quote"]
        )

    def test_final_selection_rechecks_health_after_secondary_probe_race(self) -> None:
        for mode in ("observe", "active"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as tmp:
                    cache_path = Path(tmp) / "health.json"
                    selecting_manager = manager(cache_path, mode=mode)
                    racing_manager = manager(cache_path, mode=mode)

                    def probe(row, make_client):
                        if row.endpoint_id == "secondary":
                            racing_manager.record_transport_failure(
                                "primary",
                                transport="mootdx",
                                failure_kind="race_after_primary_probe",
                            )
                        return {"checks": dict(PASSING_CHECKS)}

                    selection = selecting_manager.select_for_run(
                        run_id=f"race-{mode}",
                        probe=probe,
                    )

                primary = selection.to_provenance()["endpoint_probe_results"][0]
                self.assertEqual(primary["state"], "open")
                self.assertFalse(primary["passed"])
                self.assertEqual(
                    primary["failure_kind"],
                    "health_changed_after_probe",
                )
                if mode == "observe":
                    self.assertFalse(selection.selectable)
                    self.assertEqual(selection.health_state, "open")
                    self.assertEqual(selection.would_switch_to, "secondary")
                else:
                    self.assertTrue(selection.selectable)
                    self.assertEqual(selection.endpoint_id, "secondary")
                    self.assertEqual(selection.health_state, "healthy")

    def test_probe_factory_client_closes_when_probe_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            clients = []

            def probe(row, make_client):
                clients.append(make_client())
                raise ValueError("fake probe failure")

            with patch(
                "ashare_v3.mootdx_client.create_mootdx_client",
                side_effect=lambda selection, profile: CountingProbeClient(selection.server),
            ):
                selection = endpoint_manager.select_for_run(
                    run_id="probe-close-exception",
                    probe=probe,
                )

        self.assertFalse(selection.selectable)
        self.assertTrue(clients)
        self.assertTrue(all(client.close_count == 1 for client in clients))

    def test_half_open_probe_client_closes_on_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            endpoint_manager = manager(Path(tmp) / "health.json", clock=clock)
            endpoint_manager.record_transport_failure(
                "primary",
                failure_kind="prime_half_open",
            )
            clock.value += timedelta(seconds=301)
            client = CountingProbeClient(("115.238.56.198", 7709))

            with patch(
                "ashare_v3.mootdx_client.create_mootdx_client",
                return_value=client,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    endpoint_manager._probe_endpoint(
                        endpoint_manager.endpoints[0],
                        probe=lambda row, make_client: (
                            make_client(),
                            (_ for _ in ()).throw(KeyboardInterrupt()),
                        )[1],
                        required_checks=tuple(PASSING_CHECKS),
                    )

        self.assertEqual(client.close_count, 1)

    def test_health_cache_is_atomic_json_and_corruption_rebuilds_from_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "nested" / "health.json"
            endpoint_manager = manager(cache_path)
            endpoint_manager.select_for_run(
                run_id="write-cache",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["cache_schema_version"], "mootdx_endpoint_health_v2")
            self.assertEqual(sorted(payload["transports"]), ["mootdx"])
            self.assertEqual(list(cache_path.parent.glob("*.tmp")), [])

            cache_path.write_text("{broken", encoding="utf-8")
            rebuilt = manager(cache_path).select_for_run(
                run_id="rebuild-cache",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )

        self.assertTrue(rebuilt.selectable)
        self.assertEqual(rebuilt.health_state, "healthy")

    def test_v1_cache_migrates_only_to_mootdx_partition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock()
            cache_path = Path(tmp) / "health.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "cache_schema_version": "mootdx_endpoint_health_v1",
                        "endpoint_pool_version": "test-pool-v1",
                        "endpoints": {
                            "primary": {
                                "endpoint_id": "primary",
                                "state": "open",
                                "checked_at": "2026-07-19T00:00:00Z",
                                "open_until": "2026-07-19T00:05:00Z",
                                "consecutive_failures": 1,
                                "consecutive_required_empty_objects": 0,
                                "consecutive_required_empty_object_ids": [],
                                "probe_summary": {
                                    "passed": False,
                                    "failure_kind": "legacy_failure",
                                },
                                "half_open_token": None,
                                "half_open_until": None,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            endpoint_manager = manager(cache_path, clock=clock, mode="active")
            tdxpy_calls: list[str] = []
            tdxpy_selection = endpoint_manager.select_for_run(
                run_id="tdxpy-does-not-inherit-v1",
                transport="tdxpy",
                probe=lambda row, make_client: tdxpy_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )
            mootdx_calls: list[str] = []
            mootdx_selection = endpoint_manager.select_for_run(
                run_id="mootdx-inherits-v1",
                transport="mootdx",
                probe=lambda row, make_client: mootdx_calls.append(row.endpoint_id)
                or {"checks": dict(PASSING_CHECKS)},
            )

        self.assertEqual(tdxpy_calls, ["primary", "secondary"])
        self.assertEqual(tdxpy_selection.endpoint_id, "primary")
        self.assertEqual(mootdx_calls, ["secondary"])
        self.assertEqual(mootdx_selection.endpoint_id, "secondary")

    def test_unknown_cache_schema_and_pool_version_rebuild_from_probe(self) -> None:
        for payload in (
            {
                "cache_schema_version": "mootdx_endpoint_health_future",
                "endpoint_pool_version": "test-pool-v1",
                "transports": {"tdxpy": {"primary": {"state": "open"}}},
            },
            {
                "cache_schema_version": "mootdx_endpoint_health_v2",
                "endpoint_pool_version": "wrong-pool",
                "transports": {"tdxpy": {"primary": {"state": "open"}}},
            },
        ):
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as tmp:
                    cache_path = Path(tmp) / "health.json"
                    cache_path.write_text(json.dumps(payload), encoding="utf-8")
                    calls: list[str] = []
                    selection = manager(cache_path).select_for_run(
                        run_id="rebuild-invalid-cache",
                        transport="tdxpy",
                        probe=lambda row, make_client: calls.append(row.endpoint_id)
                        or {"checks": dict(PASSING_CHECKS)},
                    )

                self.assertEqual(calls, ["primary", "secondary"])
                self.assertEqual(selection.endpoint_id, "primary")

    def test_factory_pins_server_and_uses_exact_safe_arguments_without_multithread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selection = manager(Path(tmp) / "health.json").select_for_run(
                run_id="factory-test",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            calls: list[dict] = []

            client = create_mootdx_client(
                selection,
                "std",
                quotes_factory=lambda **kwargs: calls.append(kwargs)
                or FakeCreatedClient(kwargs["server"]),
                lock_path=Path(tmp) / "factory.lock",
            )

        self.assertIsNotNone(client)
        self.assertEqual(
            calls,
            [
                {
                    "market": "std",
                    "server": ("115.238.56.198", 7709),
                    "timeout": 5,
                    "raise_exception": True,
                    "auto_retry": False,
                    "heartbeat": False,
                }
            ],
        )
        self.assertNotIn("multithread", calls[0])

    def test_resolved_transport_factory_is_shared_by_preflight_and_business_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            factory_calls: list[tuple[str, str, str]] = []

            def transport_factory(selection, profile):
                factory_calls.append(
                    (
                        selection.transport,
                        selection.selection_reason,
                        selection.endpoint_id,
                    )
                )
                return {"profile": profile}

            selected = endpoint_manager.select_for_run(
                run_id="tdxpy-attempt",
                transport="tdxpy",
                client_factory=transport_factory,
                probe=lambda endpoint, make_client: {
                    "checks": dict(PASSING_CHECKS),
                    "client": make_client("std"),
                },
            )
            business_client = transport_factory(selected, "std")

        self.assertEqual(
            factory_calls,
            [
                ("tdxpy", "mandatory_protocol_preflight_probe", "primary"),
                ("tdxpy", "mandatory_protocol_preflight_probe", "secondary"),
                ("tdxpy", "stable_priority_primary_healthy", "primary"),
            ],
        )
        self.assertEqual(selected.transport, "tdxpy")
        self.assertEqual(selected.to_provenance()["transport"], "tdxpy")
        self.assertEqual(selected.to_provenance()["source_transport"], "tdxpy")
        self.assertEqual(business_client, {"profile": "std"})
        self.assertNotIn("mootdx", [call[0] for call in factory_calls])

    def test_missing_transport_authority_fails_before_probe_client_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint_manager = manager(Path(tmp) / "health.json")
            factory_calls = []
            with self.assertRaisesRegex(
                MootdxEndpointConfigError,
                "transport is required",
            ):
                endpoint_manager.select_for_run(
                    run_id="missing-transport",
                    transport="",
                    client_factory=lambda selection, profile: factory_calls.append(
                        (selection, profile)
                    ),
                    probe=lambda endpoint, make_client: {
                        "checks": dict(PASSING_CHECKS)
                    },
                )

        self.assertEqual(factory_calls, [])

    def test_two_selections_always_pass_their_own_server_to_factory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = manager(Path(tmp) / "health.json").select_for_run(
                run_id="primary",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            secondary = replace(
                primary,
                endpoint_id="secondary",
                host="180.153.18.170",
                selection_reason="test_explicit_secondary",
            )
            calls: list[dict] = []
            create_mootdx_client(
                primary,
                quotes_factory=lambda **kwargs: calls.append(kwargs)
                or FakeCreatedClient(kwargs["server"]),
                lock_path=Path(tmp) / "factory.lock",
            )
            create_mootdx_client(
                secondary,
                quotes_factory=lambda **kwargs: calls.append(kwargs)
                or FakeCreatedClient(kwargs["server"]),
                lock_path=Path(tmp) / "factory.lock",
            )

        self.assertEqual(
            [call["server"] for call in calls],
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )

    def test_factory_serializes_concurrent_creation_for_process_global_bestip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = manager(Path(tmp) / "health.json").select_for_run(
                run_id="primary",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            secondary = replace(
                primary,
                endpoint_id="secondary",
                host="180.153.18.170",
                selection_reason="test_explicit_secondary",
            )
            state_lock = threading.Lock()
            active = 0
            max_active = 0

            def factory(**kwargs):
                nonlocal active, max_active
                with state_lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.02)
                with state_lock:
                    active -= 1
                return FakeCreatedClient(kwargs["server"])

            with ThreadPoolExecutor(max_workers=2) as executor:
                clients = list(
                    executor.map(
                        lambda selection: create_mootdx_client(
                            selection,
                            quotes_factory=factory,
                            lock_path=Path(tmp) / "factory.lock",
                        ),
                        (primary, secondary),
                    )
                )

        self.assertEqual(max_active, 1)
        self.assertEqual(
            [client.server for client in clients],
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )

    def test_factory_closes_polluted_client_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selection = manager(Path(tmp) / "health.json").select_for_run(
                run_id="polluted",
                probe=lambda row, make_client: {"checks": dict(PASSING_CHECKS)},
            )
            polluted = FakeCreatedClient(("218.6.170.47", 7709))

            with self.assertRaisesRegex(
                MootdxEndpointSelectionError,
                "client server mismatch",
            ):
                create_mootdx_client(
                    selection,
                    quotes_factory=lambda **kwargs: polluted,
                    lock_path=Path(tmp) / "factory.lock",
                )

        self.assertTrue(polluted.closed)

    def test_invalid_toml_shape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "pool.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    endpoint_pool_version = "bad"
                    transport = "mootdx"
                    n1_failover_mode = "observe"
                    n3_failover_mode = "observe"
                    circuit_open_seconds = 300
                    required_empty_object_threshold = 3
                    """
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MootdxEndpointConfigError, "config invalid"):
                MootdxEndpointManager.from_toml(
                    config_path,
                    health_cache_path=Path(tmp) / "health.json",
                )


if __name__ == "__main__":
    unittest.main()
