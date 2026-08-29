from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "scripts", ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_n6_b_track_signal_projection_poller_once as poller  # noqa: E402


class FakeCursor:
    def __init__(self, rows=None, rowcount=0):
        self.rows = list(rows or [])
        self.rowcount = rowcount
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params

    def fetchall(self):
        return list(self.rows)


def event(event_type: str):
    return SimpleNamespace(
        event_type=event_type,
        asset_kind="stock",
        identity_key="stock:SZ:000001",
        trade_date="20260831",
        outbox_id=9001,
        event_id=f"event-{event_type}",
        payload_json={
            "direction": "buy",
            "condition_key": "BUY:STATE_V1",
            "episode_entry_event_id": "trigger-entry-1",
        },
    )


SCOPED_USERS = [
    {"principal_id": 1, "principal_type": "admin", "user_id": 1},
    {"principal_id": 2, "principal_type": "human_user", "user_id": 2},
]


class WindowsN6ProjectionContractTests(unittest.TestCase):
    def test_scope_query_is_principal_and_trade_date_bounded(self):
        cursor = FakeCursor(SCOPED_USERS)
        rows = poller._fetch_windows_scoped_users(cursor, event("ActionEligible"))
        self.assertEqual(SCOPED_USERS, rows)
        self.assertIn("user_realtime_monitor_scope", cursor.sql)
        self.assertIn("user_monitor_stock", cursor.sql)
        self.assertIn("valid_for_trade_date", cursor.sql)
        self.assertIn("u.status = 'active'", cursor.sql)
        self.assertEqual("20260831", cursor.params[4])

    def test_action_eligible_creates_one_card_per_scoped_user(self):
        cursor = FakeCursor()
        projection_row = {"display_payload_json": {}}
        card_row = {"card_payload_json": {}}
        with (
            patch.object(poller, "_fetch_windows_scoped_users", return_value=SCOPED_USERS),
            patch.object(poller, "_windows_user_snapshot", return_value=SimpleNamespace()),
            patch.object(poller, "build_projection_row", return_value=projection_row),
            patch.object(poller, "build_card_row", return_value=card_row),
            patch.object(poller, "_enforce_n6_display_payload_contract"),
            patch.object(poller, "insert_signal_projection", side_effect=[101, 102]) as insert_projection,
            patch.object(poller, "insert_signal_card") as insert_card,
            patch.object(poller, "_update_windows_episode_card") as update_card,
        ):
            counts = poller._project_windows_event_for_scoped_users(
                cursor, event("ActionEligible"), projection_run_id="projection-run"
            )
        self.assertEqual((2, 2), counts)
        self.assertEqual(2, insert_projection.call_count)
        self.assertEqual(2, insert_card.call_count)
        update_card.assert_not_called()

    def test_blocked_and_skipped_update_without_new_card(self):
        for event_type in ("ActionBlocked", "ActionSkipped"):
            cursor = FakeCursor()
            with self.subTest(event_type=event_type):
                with (
                    patch.object(poller, "_fetch_windows_scoped_users", return_value=SCOPED_USERS),
                    patch.object(poller, "_windows_user_snapshot", return_value=SimpleNamespace()),
                    patch.object(poller, "build_projection_row", return_value={"display_payload_json": {}}),
                    patch.object(poller, "_enforce_n6_display_payload_contract"),
                    patch.object(poller, "insert_signal_projection", side_effect=[201, 202]),
                    patch.object(poller, "insert_signal_card") as insert_card,
                    patch.object(poller, "_update_windows_episode_card", return_value=1) as update_card,
                ):
                    counts = poller._project_windows_event_for_scoped_users(
                        cursor, event(event_type), projection_run_id="projection-run"
                    )
                self.assertEqual((2, 2), counts)
                insert_card.assert_not_called()
                self.assertEqual(2, update_card.call_count)

    def test_card_update_is_episode_bounded(self):
        cursor = FakeCursor(rowcount=1)
        snapshot = SimpleNamespace(projection_run_id="projection-run")
        card = {
            "card_status": "action_confirmed", "display_priority": 20, "title": "t", "summary": "s",
            "current_price": 12, "source_event_id": "executed", "source_action_event_id": "executed",
            "source_action_event_type": "ActionExecuted", "action_state": "executed", "action_mark": "normal",
            "trace_json": {}, "projection_policy": "windows", "card_payload_json": {}, "user_id": 1,
            "asset_kind": "stock", "identity_key": "stock:SZ:000001", "direction": "buy",
        }
        with patch.object(poller, "build_card_row", return_value=card):
            count = poller._update_windows_episode_card(cursor, event("ActionExecuted"), snapshot, "trigger-entry-1")
        self.assertEqual(1, count)
        self.assertIn("episode_entry_event_id", cursor.sql)
        self.assertEqual("trigger-entry-1", cursor.params["episode_entry_event_id"])


if __name__ == "__main__":
    unittest.main()
