import unittest

from ashare_v3.market.realtime_snapshot_execute_readiness import (
    build_readiness_from_inputs,
    derive_preload_run_id,
    first_blocked_reason,
)


class RealtimeSnapshotExecuteReadinessTest(unittest.TestCase):
    def test_blocks_when_current_date_is_before_for_trade_date(self) -> None:
        report = build_sample_readiness(current_date="20260524", calendar_rows=[])

        self.assertFalse(report["ready"])
        self.assertEqual(report["blocked_reason"], "current_date_before_for_trade_date")
        failed_codes = failed_p0_codes(report)
        self.assertIn("n3_b1_current_date_equals_for_trade_date", failed_codes)
        self.assertIn("n3_b1_trade_calendar_row_exists", failed_codes)

    def test_ready_when_all_gates_pass(self) -> None:
        report = build_sample_readiness()

        self.assertTrue(report["ready"])
        self.assertIsNone(report["blocked_reason"])
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_calendar_missing_is_p0_when_date_matches(self) -> None:
        report = build_sample_readiness(calendar_rows=[])

        self.assertFalse(report["ready"])
        self.assertEqual(report["blocked_reason"], "trade_calendar_missing")
        self.assertIn("n3_b1_trade_calendar_row_exists", failed_p0_codes(report))

    def test_calendar_closed_is_p0(self) -> None:
        report = build_sample_readiness(calendar_rows=[calendar_row(is_open=False)])

        self.assertFalse(report["ready"])
        self.assertEqual(report["blocked_reason"], "for_trade_date_not_open")
        self.assertIn("n3_b1_trade_calendar_is_open", failed_p0_codes(report))

    def test_preload_missing_is_warning_not_blocker_when_recorded(self) -> None:
        preload_counts = sample_preload_status_counts()
        preload_counts["stock"]["missing"] = 9
        preload_counts["stock"]["passed"] = 2043
        report = build_sample_readiness(preload_status_counts=preload_counts)

        self.assertTrue(report["ready"])
        self.assertEqual(report["quality"]["p1_count"], 1)
        warning_codes = {item["gate_code"] for item in report["quality"]["items"] if item["status"] == "warning"}
        self.assertIn("n3_b1_previous_day_preload_missing_carried", warning_codes)

    def test_repeated_snapshot_run_blocks_by_default(self) -> None:
        report = build_sample_readiness(
            snapshot_run=sample_snapshot_run(),
            snapshot_row_counts={"stock": 1, "index": 0, "board": 0},
            outbox_status_counts={"pending": 1},
        )

        self.assertFalse(report["ready"])
        self.assertEqual(report["blocked_reason"], "snapshot_run_id_already_executed")
        self.assertIn("n3_b1_snapshot_run_id_not_previously_executed", failed_p0_codes(report))

    def test_repeated_snapshot_run_can_be_explicit_idempotent_warning(self) -> None:
        report = build_sample_readiness(
            snapshot_run=sample_snapshot_run(),
            snapshot_row_counts={"stock": 1, "index": 0, "board": 0},
            outbox_status_counts={"pending": 1},
            allow_repeat_idempotent=True,
        )

        self.assertTrue(report["ready"])
        warning_codes = {item["gate_code"] for item in report["quality"]["items"] if item["status"] == "warning"}
        self.assertIn("n3_b1_repeat_requires_idempotent_review", warning_codes)

    def test_runner_not_ready_blocks_final_execute_gate(self) -> None:
        contract = sample_contract()
        contract["execute_runner_readiness"] = {
            "runner_exists": True,
            "execute_final_gate_allowed": False,
            "blocked_reason": "existing runner writes common_event_outbox",
        }
        report = build_sample_readiness(contract=contract)

        self.assertFalse(report["ready"])
        self.assertEqual(report["blocked_reason"], "execute_runner_not_ready_for_contract")
        self.assertIn("n3_b1_execute_runner_ready_for_contract", failed_p0_codes(report))

    def test_writes_outbox_runner_ready_passes_final_gate(self) -> None:
        contract = sample_contract()
        contract["writes_outbox"] = True
        contract["execute_runner_readiness"] = {
            "runner_exists": True,
            "runner_requires_execute_flag": True,
            "runner_requires_user_confirmed_flag": True,
            "runner_requires_explicit_outbox_policy": True,
            "runner_requires_writes_outbox_true_flag": True,
            "runner_supports_writes_outbox_true": True,
            "execute_final_gate_allowed": True,
            "blocked_reason": None,
        }

        report = build_sample_readiness(contract=contract)

        self.assertTrue(report["ready"])
        self.assertNotIn("n3_b1_execute_runner_ready_for_contract", failed_p0_codes(report))

    def test_preload_run_id_derives_from_contract(self) -> None:
        self.assertEqual(
            derive_preload_run_id(sample_contract(), "market_data_subscription_20260525_test_execute"),
            "previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_test_execute",
        )

    def test_first_blocked_reason_maps_date_direction(self) -> None:
        items = [
            {
                "severity": "P0",
                "status": "failed",
                "gate_code": "n3_b1_current_date_equals_for_trade_date",
            }
        ]

        self.assertEqual(first_blocked_reason(items, "20260526", "20260525"), "current_date_after_for_trade_date")


def build_sample_readiness(
    *,
    contract: dict[str, object] | None = None,
    current_date: str = "20260525",
    calendar_rows: list[dict[str, object]] | None = None,
    source_run: dict[str, object] | None = None,
    preload_run: dict[str, object] | None = None,
    preload_status_counts: dict[str, dict[str, int]] | None = None,
    snapshot_run: dict[str, object] | None = None,
    snapshot_row_counts: dict[str, int] | None = None,
    outbox_status_counts: dict[str, int] | None = None,
    allow_repeat_idempotent: bool = False,
) -> dict[str, object]:
    return build_readiness_from_inputs(
        contract=contract or sample_contract(),
        market_data_run_id="market_data_subscription_20260525_test_execute",
        preload_run_id="previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_test_execute",
        current_date=current_date,
        calendar_rows=[calendar_row()] if calendar_rows is None else calendar_rows,
        source_run=source_run or sample_source_run(),
        preload_run=preload_run or sample_preload_run(),
        preload_status_counts=preload_status_counts or sample_preload_status_counts(),
        snapshot_run=snapshot_run,
        snapshot_row_counts=snapshot_row_counts or {"stock": 0, "index": 0, "board": 0},
        outbox_status_counts=outbox_status_counts or {},
        allow_repeat_idempotent=allow_repeat_idempotent,
    )


def sample_contract() -> dict[str, object]:
    return {
        "stage": "N3-B1-preflight",
        "source_run_id": "market_data_subscription_20260525_test_execute",
        "snapshot_run_id": "realtime_daily_snapshot_20260525__market_data_subscription_20260525_test_execute",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
    }


def calendar_row(is_open: bool = True) -> dict[str, object]:
    return {
        "trade_date": "20260525",
        "exchange": "SSE",
        "is_open": is_open,
        "prev_trade_date": "20260522",
        "next_trade_date": "20260526",
    }


def sample_source_run() -> dict[str, object]:
    return {
        "run_id": "market_data_subscription_20260525_test_execute",
        "status": "passed",
        "p0_count": 0,
    }


def sample_preload_run() -> dict[str, object]:
    return {
        "run_id": "previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_test_execute",
        "status": "passed",
        "p0_count": 0,
    }


def sample_snapshot_run() -> dict[str, object]:
    return {
        "run_id": "realtime_daily_snapshot_20260525__market_data_subscription_20260525_test_execute",
        "status": "passed",
        "p0_count": 0,
    }


def sample_preload_status_counts() -> dict[str, dict[str, int]]:
    return {
        "stock": {"passed": 2052, "partial": 0, "missing": 0, "failed": 0, "total": 2052},
        "index": {"passed": 9, "partial": 0, "missing": 0, "failed": 0, "total": 9},
        "board": {"passed": 127, "partial": 0, "missing": 0, "failed": 0, "total": 127},
    }


def failed_p0_codes(report: dict[str, object]) -> set[str]:
    quality = report["quality"]
    return {
        item["gate_code"]
        for item in quality["items"]
        if item["severity"] == "P0" and item["status"] == "failed"
    }


if __name__ == "__main__":
    unittest.main()
