import unittest
from datetime import datetime

from ashare_v3.market.board_snapshot_probe import (
    BOARD_SUBSCRIPTION_COUNT_SQL,
    BOARD_SUBSCRIPTION_SQL,
    build_board_snapshot_probe_report,
    select_probe_subscriptions,
)


def sample_subscriptions() -> list[dict[str, object]]:
    return [
        {
            "subscription_id": 1,
            "identity_key": "board:TDX:881002",
            "asset_kind": "board",
            "exchange": "TDX",
            "code": "881002",
            "name": "煤炭开采",
        },
        {
            "subscription_id": 2,
            "identity_key": "board:TDX:881005",
            "asset_kind": "board",
            "exchange": "TDX",
            "code": "881005",
            "name": "焦炭加工",
        },
        {
            "subscription_id": 3,
            "identity_key": "board:TDX:881007",
            "asset_kind": "board",
            "exchange": "TDX",
            "code": "881007",
            "name": "油气开采",
        },
    ]


class FakeBoardAdapter:
    adapter_name = "BoardMarketDataAdapter"

    def __init__(self, snapshots: dict[str, dict[str, object] | None]) -> None:
        self.snapshots = snapshots
        self.calls: list[tuple[str, str]] = []

    def fetch_snapshot(self, subscription: dict[str, object], trade_date: str) -> dict[str, object] | None:
        code = str(subscription["code"])
        self.calls.append((code, trade_date))
        return self.snapshots.get(code)


class BoardSnapshotProbeTest(unittest.TestCase):
    def test_ready_when_all_sampled_board_snapshots_match_trade_date(self) -> None:
        adapter = FakeBoardAdapter(
            {
                "881002": {"snapshot_time": datetime(2026, 5, 28, 9, 30)},
                "881005": {"snapshot_time": datetime(2026, 5, 28, 9, 31)},
            }
        )

        report = build_board_snapshot_probe_report(
            run_id="market_data_subscription_test",
            trade_date="20260528",
            subscriptions=sample_subscriptions(),
            adapter=adapter,
            limit=2,
            timeout_seconds=30,
        )

        self.assertEqual(report["probe_status"], "READY_FOR_B1_RETRY")
        self.assertEqual(report["summary"]["total_checked"], 2)
        self.assertEqual(report["summary"]["ready_count"], 2)
        self.assertEqual(report["summary"]["missing_count"], 0)
        self.assertEqual(report["summary"]["stale_count"], 0)
        self.assertTrue(report["summary"]["all_ready"])
        self.assertEqual(adapter.calls, [("881002", "20260528"), ("881005", "20260528")])

    def test_waits_when_board_snapshot_is_stale(self) -> None:
        adapter = FakeBoardAdapter({"881002": {"snapshot_time": datetime(2026, 5, 27, 15, 0)}})

        report = build_board_snapshot_probe_report(
            run_id="market_data_subscription_test",
            trade_date="20260528",
            subscriptions=sample_subscriptions(),
            adapter=adapter,
            limit=1,
            timeout_seconds=30,
        )

        self.assertEqual(report["probe_status"], "WAIT_MARKET_DATA")
        self.assertEqual(report["summary"]["ready_count"], 0)
        self.assertEqual(report["summary"]["stale_count"], 1)
        self.assertEqual(report["samples"][0]["snapshot_trade_date"], "20260527")
        self.assertEqual(report["samples"][0]["reason"], "stale_snapshot_trade_date")

    def test_waits_when_board_snapshot_is_missing(self) -> None:
        adapter = FakeBoardAdapter({"881002": None})

        report = build_board_snapshot_probe_report(
            run_id="market_data_subscription_test",
            trade_date="20260528",
            subscriptions=sample_subscriptions(),
            adapter=adapter,
            limit=1,
            timeout_seconds=30,
        )

        self.assertEqual(report["probe_status"], "WAIT_MARKET_DATA")
        self.assertEqual(report["summary"]["ready_count"], 0)
        self.assertEqual(report["summary"]["missing_count"], 1)
        self.assertEqual(report["samples"][0]["returned"], False)
        self.assertEqual(report["samples"][0]["reason"], "adapter_returned_none")

    def test_limit_zero_checks_all_subscriptions(self) -> None:
        adapter = FakeBoardAdapter(
            {
                "881002": {"snapshot_time": datetime(2026, 5, 28, 9, 30)},
                "881005": {"snapshot_time": datetime(2026, 5, 28, 9, 31)},
                "881007": {"snapshot_time": datetime(2026, 5, 28, 9, 32)},
            }
        )

        report = build_board_snapshot_probe_report(
            run_id="market_data_subscription_test",
            trade_date="20260528",
            subscriptions=sample_subscriptions(),
            adapter=adapter,
            limit=0,
            timeout_seconds=30,
        )

        self.assertEqual(report["summary"]["total_checked"], 3)
        self.assertEqual(len(adapter.calls), 3)

    def test_select_probe_subscriptions_limit_zero_returns_all(self) -> None:
        rows = sample_subscriptions()

        self.assertEqual(len(select_probe_subscriptions(rows, limit=0)), 3)
        self.assertEqual(len(select_probe_subscriptions(rows, limit=2)), 2)

    def test_probe_query_is_read_only_and_does_not_reference_event_tables(self) -> None:
        combined_sql = f"{BOARD_SUBSCRIPTION_SQL}\n{BOARD_SUBSCRIPTION_COUNT_SQL}".lower()

        for forbidden in ("insert ", "update ", "delete ", "truncate ", "common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
            self.assertNotIn(forbidden, combined_sql)
        self.assertIn("from common_market_data_subscription", combined_sql)


if __name__ == "__main__":
    unittest.main()
