from __future__ import annotations

import unittest
from unittest.mock import patch

from ashare_v3.mootdx_client import EndpointSelection
from scripts.probe_board_market_data_adapter import (
    DIAGNOSTIC_ONLY,
    probe_ext_paths,
    probe_std_paths,
    recommended_board_probe_path,
)


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def quotes(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def index(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def index_bars(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def bars(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def minute(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def markets(self):  # noqa: ANN201
        return []

    def quote(self, **kwargs):  # noqa: ANN003, ANN201
        return []

    def close(self) -> None:
        self.closed = True


class BoardDiagnosticProbeTest(unittest.TestCase):
    def test_tdxpy_ext_profile_fails_closed_without_constructing_client(self) -> None:
        selection = EndpointSelection(
            endpoint_pool_version="test",
            endpoint_id="primary",
            host="127.0.0.1",
            port=7709,
            transport="tdxpy",
            health_state="healthy",
            health_checked_at=None,
            probe_summary={"passed": True},
            attempt_id="attempt-1",
            selection_reason="test",
            failover_mode="observe",
            selectable=True,
        )
        calls: list[str] = []

        results = probe_ext_paths(
            "881002",
            selection,
            lambda selected, profile: calls.append(profile),
        )

        self.assertEqual(calls, [])
        self.assertEqual(results[0]["path"], "ext.transport_profile")
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["transport"], "tdxpy")
        self.assertEqual(results[0]["capability_reason"], "transport_profile_unsupported")
        self.assertIn("pinned tdxpy transport", recommended_board_probe_path(selection))

    def test_default_business_factory_uses_resolved_selection_transport(self) -> None:
        selection = EndpointSelection(
            endpoint_pool_version="test",
            endpoint_id="primary",
            host="127.0.0.1",
            port=7709,
            transport="tdxpy",
            health_state="healthy",
            health_checked_at=None,
            probe_summary={"passed": True},
            attempt_id="attempt-1",
            selection_reason="test",
            failover_mode="observe",
            selectable=True,
        )
        client = FakeClient()
        with patch(
            "scripts.probe_board_market_data_adapter.create_quote_transport",
            return_value=client,
        ) as factory:
            probe_std_paths([{"code": "881002"}], selection)

        factory.assert_called_once_with(selection, "std", transport="tdxpy")
        self.assertTrue(client.closed)

    def test_diagnostic_probe_uses_supplied_pinned_selection_for_std_and_ext(self) -> None:
        self.assertTrue(DIAGNOSTIC_ONLY)
        selection = object()
        calls: list[tuple[object, str]] = []
        clients: list[FakeClient] = []

        def factory(value, profile):  # noqa: ANN001, ANN202
            calls.append((value, profile))
            client = FakeClient()
            clients.append(client)
            return client

        probe_std_paths([{"code": "881002"}], selection, factory)
        probe_ext_paths("881002", selection, factory)

        self.assertEqual(calls, [(selection, "std"), (selection, "ext")])
        self.assertTrue(all(client.closed for client in clients))


if __name__ == "__main__":
    unittest.main()
