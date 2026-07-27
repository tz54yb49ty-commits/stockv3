import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from ashare_v3.web import n6_user_app
from ashare_v3.web.n6_app_v1 import (
    app_signal_item,
    scrub_retired_strategy_center_private_fields,
)
from ashare_v3.web.n6_user_app import N6UserWebConfig, create_app
from tests.test_n6_user_app import build_client


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/ashare_v3/web/templates/n6_app_shell.html"
CONTRACT = (
    ROOT
    / "config/n6_strategy_center/"
    "N6_STRATEGY_CENTER_30D_ARCHIVE_RETENTION_CONTRACT_V1.json"
)
HISTORICAL_CLI = (
    "scripts/run_n6_strategy_center_once.py",
    "scripts/run_n6_strategy_center_auto_once.py",
    "scripts/plan_n6_strategy_center_launchd.py",
    "scripts/build_n6_strategy_center_temporal_confluence_v2_bundle.py",
)
PRIVATE_FIELDS = {
    "strategy_center_temporal_confluence",
    "strategy_match_projection_id",
    "strategy_observation_projection_id",
    "strategy_match_change_id",
    "selection_revision_id",
    "selected_package_keys",
    "selected_packages",
    "matched_packages",
    "observed_packages",
    "package_evidence",
    "confluence",
    "coherence_episode_key",
    "coherence_level",
    "coherence_span_trading_minutes",
    "evaluator_policy_hash",
    "freshness_status",
    "market_heat_evidence",
    "market_heat_state",
    "observation_reason",
    "strategy_version",
    "surface_kind",
}


class ExplodingRepository:
    def __init__(self) -> None:
        self.call_count = 0

    def __getattr__(self, name: str):
        self.call_count += 1
        raise AssertionError(f"retired route touched repository attribute: {name}")


class StrategyCenterWebRetirementTests(unittest.TestCase):
    def test_redirect_navigation_removal_and_core_page_regression(self) -> None:
        client, _, _, _ = build_client()
        login = client.post(
            "/api/n6/auth/login",
            json={"login_name": "admin", "password": "correct-password"},
        )
        self.assertEqual(login.status_code, 302)

        redirect = client.get(
            "/n6/app/strategy-center",
            follow_redirects=False,
        )
        self.assertEqual(redirect.status_code, 307)
        self.assertEqual(
            redirect.headers["location"],
            "/n6/app/signals?notice=strategy_center_retired",
        )
        for route in (
            "/n6/app/dashboard",
            "/n6/app/signals",
            "/n6/app/my-monitor",
            "/n6/app/realtime-scope",
            "/n6/app/account",
        ):
            with self.subTest(route=route):
                response = client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("/n6/app/strategy-center", response.text)
                self.assertNotIn(">策略中心<", response.text)

    def test_all_retired_apis_are_stable_410_without_repository_access(self) -> None:
        repository = ExplodingRepository()
        client = TestClient(
            create_app(
                repository=repository,
                config=N6UserWebConfig(cookie_secure=False),
            ),
            follow_redirects=False,
        )
        requests = (
            ("get", "/api/n6/app/v3/strategy-center", None),
            (
                "put",
                "/api/n6/app/v3/strategy-center/selection",
                {"selected_package_keys": ["package_1"]},
            ),
            ("get", "/api/n6/app/v3/strategy-center/stream", None),
        )
        for method, route, payload in requests:
            with self.subTest(method=method, route=route):
                response = (
                    getattr(client, method)(route)
                    if payload is None
                    else getattr(client, method)(route, json=payload)
                )
                self.assertEqual(response.status_code, 410)
                self.assertEqual(
                    response.json(),
                    {"ok": False, "code": "strategy_center_retired"},
                )
                self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(repository.call_count, 0)

    def test_signals_scrubber_removes_only_retired_private_fields(self) -> None:
        private_payload = {
            "strategy_center_temporal_confluence": {"secret": True},
            "confluence": {"coherence_level": "STRONG"},
            "matched_packages": ["package_1"],
            "surface_kind": "qualified_match",
            "ordinary_future_field": {"kept": True},
        }
        row = {
            "user_signal_projection_id": 1,
            "event_type": "ActionExecuted",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "code": "600000",
            "name": "浦发银行",
            "direction": "buy",
            "signal_type": "B_BUY",
            "action_state": "executed",
            "card_payload_json": {
                "condition_projection_context": {
                    "source": private_payload,
                    "allowed_trace": "kept",
                }
            },
            "display_payload_json": private_payload,
            **private_payload,
        }

        scrubbed = scrub_retired_strategy_center_private_fields(row)
        item = app_signal_item(row)
        encoded = json.dumps(item, ensure_ascii=False, sort_keys=True)

        self.assertEqual(scrubbed["ordinary_future_field"], {"kept": True})
        self.assertEqual(
            scrubbed["card_payload_json"]["condition_projection_context"][
                "allowed_trace"
            ],
            "kept",
        )
        self.assertIn("allowed_trace", encoded)
        for key in PRIVATE_FIELDS:
            self.assertNotIn(f'"{key}"', encoded)
        self.assertNotIn("策略包", encoded)

    def test_active_runtime_and_deploy_paths_are_fail_closed(self) -> None:
        module_source = inspect.getsource(n6_user_app)
        runtime_factory = inspect.getsource(n6_user_app.create_runtime_app)
        template_source = TEMPLATE.read_text()
        contract = json.loads(CONTRACT.read_text())

        self.assertNotIn(
            "ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED",
            module_source,
        )
        self.assertNotIn("build_runtime_strategy_center_repository", module_source)
        self.assertNotIn("strategy_center_repository", runtime_factory)
        self.assertNotIn("data-n6-strategy-center", template_source)
        self.assertNotIn("/api/n6/app/v3/strategy-center", template_source)
        self.assertEqual(contract["active_strategy_center_entrypoints"], [])

        for relative_path in HISTORICAL_CLI:
            with self.subTest(path=relative_path):
                source = (ROOT / relative_path).read_text()
                guard_position = source.index(
                    'raise SystemExit("strategy_center_retired")'
                )
                strategy_import_positions = [
                    position
                    for marker in (
                        "from ashare_v3.user.strategy_center",
                        "from ashare_v3.user.strategy_center_worker",
                        "from scripts.run_n6_strategy_center_once",
                    )
                    if (position := source.find(marker)) >= 0
                ]
                if strategy_import_positions:
                    self.assertLess(guard_position, min(strategy_import_positions))
                result = subprocess.run(
                    [sys.executable, str(ROOT / relative_path)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("strategy_center_retired", result.stderr)


if __name__ == "__main__":
    unittest.main()
