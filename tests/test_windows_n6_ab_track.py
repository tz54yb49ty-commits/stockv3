from __future__ import annotations

from pathlib import Path
import sys
import unittest

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ashare_v3.web.windows_n6_runtime import (  # noqa: E402
    InMemoryWindowsRuntimeFixture,
    OfflineWindowsRuntimeBridge,
    read_runtime_page,
    windows_archive_status,
    windows_postclose_status,
)


class WindowsN6RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = InMemoryWindowsRuntimeFixture()

    def test_fixture_covers_three_assets_and_quality_states(self) -> None:
        page = read_runtime_page(self.fixture, "n4", {"limit": 100})
        self.assertEqual({"stock", "index", "board"}, {row["asset_kind"] for row in page["items"]})
        self.assertEqual({"available", "stale", "unavailable"}, {row["live_status"] for row in page["items"]})
        self.assertTrue(page["simulation"])
        self.assertEqual("SIMULATED / NOT PRODUCTION", page["simulation_label"])

    def test_n4_page_has_stable_cursor_pagination(self) -> None:
        first = read_runtime_page(self.fixture, "n4", {"limit": 2})
        second = read_runtime_page(self.fixture, "n4", {"limit": 2, "cursor": first["next_cursor"]})
        self.assertEqual(12, first["version"])
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(2, first["item_count"])
        self.assertEqual(1, second["item_count"])

    def test_n5_exposes_active_episodes_only(self) -> None:
        page = read_runtime_page(self.fixture, "n5", {"limit": 100})
        self.assertEqual(2, page["item_count"])
        self.assertTrue(all(row["trigger_live"] is True for row in page["items"]))
        self.assertEqual({"eligible", "executed"}, {row["action_state"] for row in page["items"]})

    def test_runtime_offline_never_falls_back_to_old_state(self) -> None:
        for layer in ("n4", "n5"):
            page = read_runtime_page(OfflineWindowsRuntimeBridge(), layer, {})
            self.assertEqual("runtime_offline", page["runtime_status"])
            self.assertEqual([], page["items"])
            self.assertIsNone(page["version"])

    def test_offline_runtime_bridge_page_template_renders_without_500(self) -> None:
        page = read_runtime_page(OfflineWindowsRuntimeBridge(), "n4", {})
        environment = Environment(
            loader=FileSystemLoader(SRC / "ashare_v3/web/templates"),
            autoescape=select_autoescape(("html",)),
        )

        rendered = environment.get_template(
            "n6_windows_runtime_states.html"
        ).render(
            title="N4实时内存状态",
            layer="n4",
            page=page,
            filters={},
            nav={"links": (), "active": "n4_runtime_states", "is_admin": True},
        )

        self.assertIn("runtime_offline", rendered)
        self.assertIn("暂无当前内存状态", rendered)

    def test_status_models_are_windows_specific(self) -> None:
        postclose = windows_postclose_status(self.fixture)
        archive = windows_archive_status(self.fixture)
        self.assertEqual(["16:30", "16:35", "09:15"], [item["time"] for item in postclose["timeline"]])
        self.assertEqual("pretrade_c2f55d9_v1", postclose["context_version"])
        self.assertIn("240点累计金额", archive["retention"])
        self.assertFalse(archive["actions_allowed"])

    def test_fixture_has_zero_external_side_effects(self) -> None:
        self.assertEqual(0, self.fixture.database_connection_count)
        self.assertEqual(0, self.fixture.database_write_count)
        self.assertEqual(0, self.fixture.outbox_write_count)


class WindowsN6StaticContractTests(unittest.TestCase):
    def test_b_track_navigation_is_exact_and_has_no_ai(self) -> None:
        source = (SRC / "ashare_v3/web/n6_app_v1.py").read_text(encoding="utf-8")
        nav_block = source[source.index("def app_nav_context"):source.index("def _component_label")]
        for label in ("dashboard", "filter-center", "my-monitor", "realtime-scope", "status-monitor", "signals", "messages", "account", "trade-log"):
            self.assertIn(f'"{label}"', nav_block)
        self.assertNotIn('"ai-users"', nav_block)
        self.assertNotIn('"buy-messages"', nav_block)

    def test_a_track_navigation_uses_runtime_state_pages(self) -> None:
        source = (SRC / "ashare_v3/web/n6_user_app.py").read_text(encoding="utf-8")
        nav_block = source[source.index("def nav_context"):source.index("def n2_condition_basis_asset_meta")]
        self.assertIn("/n6/n4-runtime-states", nav_block)
        self.assertIn("/n6/n5-runtime-states", nav_block)
        self.assertNotIn("N3消息", nav_block)
        self.assertIn("virtual_executor_disabled", source)

    def test_windows_projection_wrapper_has_no_outbox_status_update(self) -> None:
        source = (ROOT / "scripts/run_windows_n6_projection_once.py").read_text(encoding="utf-8").lower()
        self.assertIn("postgres_advisory_xact_lock", source)
        self.assertIn("n5_outbox_status_update_count", source)
        self.assertNotIn("update common_event_outbox", source)
        self.assertNotIn("notification_queue", source)

    def test_windows_projection_creates_only_eligible_cards(self) -> None:
        source = (ROOT / "scripts/run_n6_b_track_signal_projection_poller_once.py").read_text(encoding="utf-8")
        self.assertIn('if event_type == "ActionEligible":\n        return "create"', source)
        self.assertIn('if event_type in {"ActionExecuted", "ActionBlocked", "ActionSkipped"}:\n        return "update"', source)
        self.assertIn("_fetch_windows_scoped_users", source)
        self.assertIn("user_realtime_monitor_scope", source)
        self.assertIn("_update_windows_episode_card", source)
        schema = (ROOT / "sql/043_windows_n6_projection_idempotency.sql").read_text(encoding="utf-8")
        self.assertIn("source_outbox_id", schema)
        self.assertIn("source_event_id", schema)
        self.assertIn("user_id", schema)
        self.assertTrue(schema.rstrip().endswith("COMMIT;"))

    def test_fixture_is_explicitly_non_production(self) -> None:
        source = (SRC / "ashare_v3/web/windows_n6_fixture_app.py").read_text(encoding="utf-8")
        self.assertIn("SIMULATION_LABEL", source)
        self.assertIn("ActionEligible", source)
        self.assertIn("ActionExecuted", source)
        self.assertIn("ActionSkipped", source)
        self.assertIn("database_write_count", source)
        self.assertNotIn("psycopg", source)

    def test_windows_files_have_no_mac_dependency(self) -> None:
        paths = (
            SRC / "ashare_v3/web/windows_n6_runtime.py",
            SRC / "ashare_v3/web/windows_n6_fixture_app.py",
            ROOT / "scripts/run_windows_n6_projection_once.py",
            ROOT / "scripts/run_windows_n6_fixture_web.py",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/", source, path.name)
            self.assertNotIn("/Volumes/", source, path.name)


if __name__ == "__main__":
    unittest.main()
