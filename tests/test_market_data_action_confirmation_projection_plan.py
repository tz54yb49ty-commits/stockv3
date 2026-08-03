import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ashare_v3.market.action_confirmation_projection_plan import (
    ALLOWED_FUTURE_EXECUTE_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES,
    add_price_amount_flags,
    body_high,
    body_low,
    build_action_confirmation_projection_dry_run_report,
    build_action_confirmation_projection_readiness_report,
    build_metric_candidate_row,
    build_metric_candidate_rows_from_sources,
    build_preflight_report,
    simulate_metric_ready_db_check,
    write_report_files,
)
from ashare_v3.market.c1_scoped_artifact import canonical_ashare_1m_labels, resolve_fixed_period_windows


class MarketDataActionConfirmationProjectionPlanTest(unittest.TestCase):
    def test_fixed_period_body_and_strict_amount_comparison(self) -> None:
        rows = [
            {"open": 10.0, "close": 11.0},
            {"open": 100.0, "close": 1.0},
            {"open": 12.0, "close": 9.0},
        ]
        metric = {
            "current_price": 10.0,
            "is_first_5m_of_day": False,
            "is_first_1m_of_day": False,
            "current_5m_virtual_amount": 100.0,
            "previous_5m_full_amount": 100.0,
            "current_1m_amount": 50.0,
            "previous_1m_amount": 50.0,
        }

        add_price_amount_flags(metric)

        self.assertEqual(body_high(rows), 10.0)
        self.assertEqual(body_low(rows), 9.0)
        self.assertFalse(metric["buy_5m_amount_pass"])
        self.assertFalse(metric["sell_5m_amount_pass"])
        self.assertFalse(metric["buy_1m_amount_pass"])
        self.assertFalse(metric["sell_1m_amount_pass"])

    def _minute_iso(self, date: str, index: int) -> str:
        base = datetime(int(date[:4]), int(date[4:6]), int(date[6:]), 9, 31, tzinfo=timezone(timedelta(hours=8)))
        return (base + timedelta(minutes=index - 1)).isoformat()

    def _fixed_row(
        self,
        *,
        date: str,
        ordinal: int,
        physical_label: str,
        raw_label: str | None = None,
        open_value: float | None = None,
        close_value: float | None = None,
        amount: float | None = None,
    ) -> dict[str, object]:
        return {
            "bar_id": ordinal,
            "identity_key": "index:SH:000688",
            "bar_time": f"{date[:4]}-{date[4:6]}-{date[6:]}T{physical_label}:00+08:00",
            "physical_c1_label": physical_label,
            "raw_source_label": raw_label or physical_label,
            "open": 1700.0 if open_value is None else open_value,
            "close": 1700.0 if close_value is None else close_value,
            "amount": 100.0 if amount is None else amount,
            "source_row_ref": f"fixture:{date}:{ordinal}:{raw_label or physical_label}",
        }

    def _intraday_fixed_rows(self, date: str, end_label: str) -> list[dict[str, object]]:
        labels = [
            label
            for label in canonical_ashare_1m_labels(date)
            if label != "09:30" and label <= end_label
        ]
        return [
            self._fixed_row(date=date, ordinal=ordinal, physical_label=label)
            for ordinal, label in enumerate(labels, start=1)
        ]

    def _candidate(
        self,
        *,
        today_rows: list[dict[str, object]],
        previous_rows: list[dict[str, object]],
        current_price: float = 1724.515,
    ) -> dict[str, object]:
        return build_metric_candidate_row(
            asset_kind="index",
            projection_run_id="projection",
            projection_schema_version="n3.action_confirmation_metric.v1",
            for_trade_date="20260720",
            source_condition_run_id="condition",
            source_subscription_run_id="subscription",
            source_snapshot_run_id="snapshot",
            source_today_minute_run_id="today",
            source_previous_day_minute_run_id="previous",
            snapshot_row={
                "source_snapshot_id": 501,
                "identity_key": "index:SH:000688",
                "exchange": "SH",
                "code": "000688",
                "display_code": "000688.SH",
                "name": "STAR 50",
                "trade_date": "20260720",
                "snapshot_time": "2026-07-20T14:50:30+08:00",
                "current_price": current_price,
            },
            today_rows=today_rows,
            previous_day_rows=previous_rows,
        )

    def test_projection_planner_uses_canonical_fixed_periods_for_000688_20260720_1450(self) -> None:
        today_rows = self._intraday_fixed_rows("20260720", "14:50")
        rows_by_label = {str(row["physical_c1_label"]): row for row in today_rows}
        rows_by_label["09:31"].update(open=1764.593, close=1754.868)
        rows_by_label["13:00"].update(open=1713.161, close=1712.121)
        rows_by_label["14:01"].update(open=1663.027)
        rows_by_label["14:30"].update(close=1662.847)
        rows_by_label["14:41"].update(open=1664.568, amount=1_000_000_000)
        rows_by_label["14:42"].update(amount=1_000_000_000)
        rows_by_label["14:43"].update(amount=1_000_000_000)
        rows_by_label["14:44"].update(amount=1_000_000_000)
        rows_by_label["14:45"].update(close=1695.061, amount=1_425_289_024)
        rows_by_label["14:46"].update(amount=1_490_729_216)
        rows_by_label["14:47"].update(amount=1_000_000_000)
        rows_by_label["14:48"].update(amount=1_000_000_000)
        rows_by_label["14:49"].update(open=1709.527, close=1701.758, amount=1_090_295_296)
        rows_by_label["14:50"].update(open=1711.055, close=1724.515, amount=1_901_952_384)
        previous_rows = self._intraday_fixed_rows("20260717", "14:59")[-30:]

        with patch(
            "ashare_v3.market.action_confirmation_projection_plan.resolve_fixed_period_windows",
            wraps=resolve_fixed_period_windows,
        ) as resolver:
            row = self._candidate(today_rows=today_rows, previous_rows=previous_rows)

        resolver.assert_called_once()
        self.assertEqual(row["previous_120m_body_high"], 1764.593)
        windows = resolve_fixed_period_windows(current_rows=today_rows, previous_rows=previous_rows)
        for size in (5, 30, 120):
            previous_ids = {item["bar_id"] for item in windows["previous_period_rows"][size]}
            current_ids = {item["bar_id"] for item in windows["current_period_rows"][size]}
            self.assertTrue(previous_ids)
            self.assertTrue(current_ids)
            self.assertTrue(previous_ids.isdisjoint(current_ids))
            self.assertLess(max(previous_ids), min(current_ids))

    def test_projection_planner_normalizes_intraday_and_postclose_lunch_layouts(self) -> None:
        intraday_rows = self._intraday_fixed_rows("20260720", "13:01")
        for ordinal, row in enumerate(intraday_rows, start=1):
            row.update(open=1000.0 + ordinal, close=1000.5 + ordinal, amount=100.0 * ordinal)
        postclose_rows = [
            *[dict(row) for row in intraday_rows],
            self._fixed_row(
                date="20260720",
                ordinal=120,
                physical_label="13:00",
                raw_label="11:30",
                open_value=1120.0,
                close_value=1120.5,
                amount=12_000.0,
            ),
        ]
        previous_rows = self._intraday_fixed_rows("20260717", "14:59")

        intraday = self._candidate(today_rows=intraday_rows, previous_rows=previous_rows, current_price=1200.0)
        postclose = self._candidate(today_rows=postclose_rows, previous_rows=previous_rows, current_price=1200.0)

        comparable_fields = (
            "previous_120m_body_high",
            "previous_120m_body_low",
            "previous_30m_body_high",
            "previous_30m_body_low",
            "previous_5m_body_high",
            "previous_5m_body_low",
            "previous_1m_body_high",
            "previous_1m_body_low",
            "current_5m_virtual_amount",
            "current_30m_virtual_amount",
            "previous_1m_period_source",
            "previous_5m_period_source",
            "previous_30m_period_source",
            "previous_120m_period_source",
        )
        self.assertEqual(
            {field: intraday[field] for field in comparable_fields},
            {field: postclose[field] for field in comparable_fields},
        )

    def test_projection_planner_fails_closed_for_missing_or_duplicate_ordinal(self) -> None:
        previous_rows = self._intraday_fixed_rows("20260717", "14:59")
        missing_rows = [
            self._fixed_row(date="20260720", ordinal=1, physical_label="09:31"),
            self._fixed_row(date="20260720", ordinal=3, physical_label="09:33"),
        ]
        missing = self._candidate(today_rows=missing_rows, previous_rows=previous_rows)
        self.assertFalse(missing["metric_ready"])
        self.assertEqual(missing["previous_1m_period_source"], "not_available")
        self.assertEqual(missing["previous_120m_period_source"], "not_available")

        duplicate_rows = [
            self._fixed_row(date="20260720", ordinal=1, physical_label="09:31"),
            self._fixed_row(date="20260720", ordinal=2, physical_label="09:31"),
        ]
        duplicate = self._candidate(today_rows=duplicate_rows, previous_rows=previous_rows)
        self.assertFalse(duplicate["metric_ready"])
        self.assertEqual(duplicate["metric_quality_status"], "blocked")

    def test_projection_planner_blocks_not_available_previous_period_source(self) -> None:
        current_rows = [self._fixed_row(date="20260720", ordinal=1, physical_label="09:31")]
        partial_previous_rows = self._intraday_fixed_rows("20260717", "13:29")[-30:]

        row = self._candidate(today_rows=current_rows, previous_rows=partial_previous_rows)

        self.assertFalse(row["metric_ready"])
        self.assertEqual(row["metric_quality_status"], "blocked")
        self.assertEqual(row["previous_120m_period_source"], "not_available")
        self.assertEqual(
            row["raw_json"]["blocked_reason"],
            "BLOCKED_N3T_PREVIOUS_PERIOD_SOURCE_UNAVAILABLE",
        )

    def test_first_bucket_uses_only_last_complete_previous_day_fixed_period(self) -> None:
        current_rows = [self._fixed_row(date="20260720", ordinal=1, physical_label="09:31")]
        previous_through_1305 = self._intraday_fixed_rows("20260717", "13:05")
        resolved = resolve_fixed_period_windows(
            current_rows=current_rows,
            previous_rows=previous_through_1305,
        )

        previous_120m_ids = [row["bar_id"] for row in resolved["previous_period_rows"][120]]
        self.assertEqual(previous_120m_ids, list(range(1, 121)))
        self.assertEqual(resolved["previous_period_sources"][120], "previous_trade_date_last_period")

        incomplete_previous = resolve_fixed_period_windows(
            current_rows=current_rows,
            previous_rows=previous_through_1305[:119],
        )
        self.assertEqual(incomplete_previous["previous_period_rows"][120], [])
        self.assertEqual(incomplete_previous["previous_period_sources"][120], "not_available")

    def _base_report(
        self,
        *,
        source_snapshot_run: dict | None = None,
        input_summary: dict | None = None,
        trace_summary: dict | None = None,
    ) -> dict:
        default_input_summary = {
            "snapshot_objects": {"stock": 10, "index": 2, "board": 1},
            "today_minute_objects": {"stock": 8, "index": 2, "board": 1},
            "previous_day_minute_objects": {"stock": 8, "index": 2, "board": 1},
            "candidate_objects": {"stock": 8, "index": 2, "board": 1},
            "latest_today_minute_label": "11:05",
            "latest_snapshot_time": "2026-06-02T10:53:00+08:00",
        }
        if input_summary:
            default_input_summary.update(input_summary)
        default_trace_summary = {
            "snapshot_event_refs": {"expected": 11, "actual": 11},
            "source_fact_ids_ready": {"stock": 8, "index": 2, "board": 1},
            "source_minute_refs_ready": {"stock": 8, "index": 2, "board": 1},
            "previous_day_minute_refs_ready": {"stock": 8, "index": 2, "board": 1},
        }
        if trace_summary:
            default_trace_summary.update(trace_summary)
        snapshot_run = {"status": "passed"}
        if source_snapshot_run:
            snapshot_run.update(source_snapshot_run)
        return build_action_confirmation_projection_readiness_report(
            projection_run_id="action_confirmation_projection_metric_20260602_1105__snapshot",
            for_trade_date="20260602",
            source_condition_run_id="condition_layer_20260601_source_20260601_v1",
            source_subscription_run_id="market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            source_snapshot_run_id="snapshot",
            source_today_minute_run_id="today_minute",
            source_previous_day_minute_run_id="previous_day_minute",
            schema_status={
                "tables_exist": {"stock": True, "index": True, "board": True},
                "metric_ready_trace_check_constraints": 3,
                "row_counts": {"stock": 0, "index": 0, "board": 0},
            },
            source_runs={
                "source_snapshot_run": snapshot_run,
                "source_today_minute_run": {"status": "passed"},
                "source_previous_day_minute_run": {"status": "passed"},
            },
            input_summary=default_input_summary,
            trace_summary=default_trace_summary,
            boundary_summary={
                "first_period_policy_ready": True,
                "previous_1m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
                "previous_5m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
                "previous_30m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
                "previous_120m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
            },
            baseline_summary={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "stock_action_confirmation_projection_metric": 0,
                "index_action_confirmation_projection_metric": 0,
                "board_action_confirmation_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
        )

    def _gate(self, report: dict, gate_code: str) -> dict:
        return next(item for item in report["quality"]["items"] if item["gate_code"] == gate_code)

    def test_readiness_report_passes_with_complete_sources_and_trace(self) -> None:
        report = self._base_report()

        self.assertEqual(report["result"], "DRAFT_PASS")
        self.assertFalse(report["blocked"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["candidate_summary"]["total"], 11)
        self.assertFalse(report["write_scope"]["writes_outbox"])
        self.assertIn("stock_action_confirmation_projection_metric", ALLOWED_FUTURE_EXECUTE_WRITE_TABLES)
        self.assertIn("common_event_outbox", FORBIDDEN_WRITE_TABLES)

    def test_fact_only_snapshot_run_does_not_require_snapshot_event_refs(self) -> None:
        report = self._base_report(
            source_snapshot_run={"writes_outbox": False},
            trace_summary={"snapshot_event_refs": {"expected": 11, "actual": 0}},
        )

        self.assertEqual(report["result"], "DRAFT_PASS")
        self.assertFalse(report["blocked"])
        gate = self._gate(report, "n3_action_confirmation_snapshot_event_trace_complete")
        self.assertEqual(gate["status"], "passed")
        self.assertIn("fact-only", gate["expected_value"])

    def test_writes_outbox_snapshot_run_requires_snapshot_event_refs(self) -> None:
        report = self._base_report(
            source_snapshot_run={"writes_outbox": True},
            trace_summary={"snapshot_event_refs": {"expected": 11, "actual": 0}},
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("n3_action_confirmation_snapshot_event_trace_complete", report["blockers"])

    def test_fact_only_snapshot_run_still_blocks_when_fact_trace_is_missing(self) -> None:
        report = self._base_report(
            source_snapshot_run={"writes_outbox": False},
            trace_summary={
                "snapshot_event_refs": {"expected": 11, "actual": 0},
                "source_fact_ids_ready": {"stock": 7, "index": 2, "board": 1},
            },
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertNotIn("n3_action_confirmation_snapshot_event_trace_complete", report["blockers"])
        self.assertIn("n3_action_confirmation_trace_refs_complete", report["blockers"])

    def test_20260617_fact_only_lineage_passes_without_snapshot_event_refs(self) -> None:
        counts = {"stock": 1840, "index": 81, "board": 127}
        report = self._base_report(
            source_snapshot_run={"writes_outbox": "false"},
            input_summary={"candidate_objects": counts},
            trace_summary={
                "snapshot_event_refs": {"expected": sum(counts.values()), "actual": 0},
                "source_fact_ids_ready": counts,
                "source_minute_refs_ready": counts,
                "previous_day_minute_refs_ready": counts,
            },
        )

        self.assertEqual(report["result"], "DRAFT_PASS")
        self.assertEqual(report["candidate_summary"]["total"], 2048)

    def test_missing_source_run_blocks_with_p0(self) -> None:
        report = build_action_confirmation_projection_readiness_report(
            projection_run_id="projection",
            for_trade_date="20260602",
            source_condition_run_id="condition",
            source_subscription_run_id="subscription",
            source_snapshot_run_id="snapshot",
            source_today_minute_run_id="today",
            source_previous_day_minute_run_id="previous",
            schema_status={
                "tables_exist": {"stock": True, "index": True, "board": True},
                "metric_ready_trace_check_constraints": 3,
                "row_counts": {"stock": 0, "index": 0, "board": 0},
            },
            source_runs={
                "source_snapshot_run": {"status": "passed"},
                "source_today_minute_run": {"status": "missing"},
                "source_previous_day_minute_run": {"status": "passed"},
            },
            input_summary={"candidate_objects": {"stock": 0, "index": 0, "board": 0}},
            trace_summary={"snapshot_event_refs": {"expected": 0, "actual": 0}},
            boundary_summary={"first_period_policy_ready": True},
            baseline_summary={
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "stock_action_confirmation_projection_metric": 0,
                "index_action_confirmation_projection_metric": 0,
                "board_action_confirmation_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertTrue(report["blocked"])
        self.assertGreater(report["quality"]["p0_count"], 0)
        self.assertIn("n3_action_confirmation_source_runs_passed", report["blockers"])

    def test_trace_strategy_aligns_with_metric_ready_db_check(self) -> None:
        report = self._base_report()
        strategy = report["metric_ready_trace_refs_strategy"]

        self.assertEqual(strategy["mode"], "db_hard_guard_plus_preflight_p0")
        self.assertEqual(strategy["source_fact_ids"], "non_empty_json_object")
        self.assertEqual(strategy["source_minute_refs"], "non_empty_json_array")
        self.assertIn("previous_trade_date_last_period", strategy["previous_day_minute_refs_required_when"])
        self.assertTrue(report["n4_n5_boundary"]["n4_must_not_recompute_from_raw_minutes"])
        self.assertTrue(report["n4_n5_boundary"]["n5_must_not_trust_opaque_payload"])

    def test_preflight_preserves_source_lineage(self) -> None:
        report = self._base_report()
        preflight = build_preflight_report(report)

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["source_condition_run_id"], report["source_condition_run_id"])
        self.assertEqual(preflight["source_subscription_run_id"], report["source_subscription_run_id"])
        self.assertEqual(preflight["source_snapshot_run_id"], report["source_snapshot_run_id"])
        self.assertEqual(preflight["source_today_minute_run_id"], report["source_today_minute_run_id"])
        self.assertEqual(preflight["source_previous_day_minute_run_id"], report["source_previous_day_minute_run_id"])

    def test_report_files_are_json_and_markdown(self) -> None:
        report = self._base_report()
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "report.json"
            markdown_path = Path(tmp) / "report.md"
            write_report_files(report, json_path=json_path, markdown_path=markdown_path)

            self.assertEqual(json.loads(json_path.read_text())["result"], "DRAFT_PASS")
            self.assertIn("N3 Action-Confirmation Projection Writer Readiness", markdown_path.read_text())

    def test_dry_run_builds_metric_ready_candidate_with_trace_refs(self) -> None:
        snapshot_rows = {
            "stock": [
                {
                    "source_snapshot_id": 501,
                    "identity_key": "stock:SH:600000",
                    "exchange": "SH",
                    "code": "600000",
                    "display_code": "600000.SH",
                    "name": "PF Bank",
                    "trade_date": "20260602",
                    "snapshot_time": "2026-06-02T09:36:30+08:00",
                    "current_price": 10.5,
                }
            ],
            "index": [],
            "board": [],
        }
        today_rows = {
            "stock": [
                {
                    "bar_id": i,
                    "identity_key": "stock:SH:600000",
                    "bar_time": self._minute_iso("20260602", i),
                    "open": 10.0 + i / 100,
                    "close": 10.1 + i / 100,
                    "amount": 1000 + i,
                }
                for i in range(1, 7)
            ],
            "index": [],
            "board": [],
        }
        previous_rows = {
            "stock": [
                {
                    "bar_id": 1000 + i,
                    "identity_key": "stock:SH:600000",
                    "bar_time": self._minute_iso("20260601", i),
                    "open": 9.0 + i / 1000,
                    "close": 9.1 + i / 1000,
                    "amount": 900 + i,
                }
                for i in range(1, 241)
            ],
            "index": [],
            "board": [],
        }

        rows = build_metric_candidate_rows_from_sources(
            projection_run_id="projection",
            projection_schema_version="n3.action_confirmation_metric.v1",
            for_trade_date="20260602",
            source_condition_run_id="condition",
            source_subscription_run_id="subscription",
            source_snapshot_run_id="snapshot",
            source_today_minute_run_id="today",
            source_previous_day_minute_run_id="previous",
            snapshot_rows_by_asset=snapshot_rows,
            today_minute_rows_by_asset=today_rows,
            previous_day_minute_rows_by_asset=previous_rows,
        )

        self.assertEqual(len(rows["stock"]), 1)
        row = rows["stock"][0]
        self.assertTrue(row["metric_ready"])
        self.assertEqual(row["previous_5m_period_source"], "same_trade_date_previous_period")
        self.assertEqual(row["previous_30m_period_source"], "previous_trade_date_last_period")
        self.assertEqual(row["previous_120m_period_source"], "previous_trade_date_last_period")
        self.assertGreater(len(row["source_minute_refs"]), 0)
        self.assertGreater(len(row["previous_day_minute_refs"]), 0)
        self.assertTrue(simulate_metric_ready_db_check(row)["passes"])

    def test_metric_candidate_uses_elapsed_ratio_calibrated_30m_virtual_amount(self) -> None:
        snapshot_rows = {
            "stock": [
                {
                    "source_snapshot_id": 501,
                    "identity_key": "stock:SH:600000",
                    "exchange": "SH",
                    "code": "600000",
                    "display_code": "600000.SH",
                    "name": "PF Bank",
                    "trade_date": "20260602",
                    "snapshot_time": "2026-06-02T09:31:30+08:00",
                    "current_price": 10.5,
                }
            ],
            "index": [],
            "board": [],
        }
        today_rows = {
            "stock": [
                {
                    "bar_id": 1,
                    "identity_key": "stock:SH:600000",
                    "bar_time": self._minute_iso("20260602", 1),
                    "open": 10.0,
                    "close": 10.1,
                    "amount": 281_104_512,
                }
            ],
            "index": [],
            "board": [],
        }
        previous_amounts = [312_718_976, *([79_323_604] * 29)]
        previous_rows = {
            "stock": [
                {
                    "bar_id": 1000 + i,
                    "identity_key": "stock:SH:600000",
                    "bar_time": self._minute_iso("20260601", i),
                    "open": 9.0,
                    "close": 9.1,
                    "amount": amount,
                }
                for i, amount in enumerate(previous_amounts, start=1)
            ],
            "index": [],
            "board": [],
        }

        rows = build_metric_candidate_rows_from_sources(
            projection_run_id="projection",
            projection_schema_version="n3.action_confirmation_metric.v1",
            for_trade_date="20260602",
            source_condition_run_id="condition",
            source_subscription_run_id="subscription",
            source_snapshot_run_id="snapshot",
            source_today_minute_run_id="today",
            source_previous_day_minute_run_id="previous",
            snapshot_rows_by_asset=snapshot_rows,
            today_minute_rows_by_asset=today_rows,
            previous_day_minute_rows_by_asset=previous_rows,
        )

        row = rows["stock"][0]
        expected = 281_104_512 / 312_718_976 * sum(previous_amounts)
        self.assertAlmostEqual(float(row["current_30m_virtual_amount"]), expected, places=2)
        self.assertLess(row["current_30m_virtual_amount"], row["previous_day_same_window_amount"])
        self.assertNotEqual(row["current_30m_virtual_amount"], row["current_1m_amount"])
        proof = row["raw_json"]["virtual_amount_policy"]["periods"]["30m"]
        self.assertEqual(proof["current_elapsed_amount"], 281_104_512)
        self.assertEqual(proof["previous_day_same_elapsed_amount"], 312_718_976)
        self.assertEqual(proof["previous_day_same_full_amount"], sum(previous_amounts))

    def test_dry_run_report_counts_would_write_rows_and_metric_ready(self) -> None:
        report = self._base_report()
        report["candidate_summary"] = {"stock": 1, "index": 0, "board": 0, "total": 1}
        report["input_summary"]["candidate_objects"] = {"stock": 1, "index": 0, "board": 0}
        rows_by_asset = {
            "stock": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "metric_ready": True,
                    "metric_quality_status": "passed",
                    "current_price_source": "realtime_daily_snapshot",
                    "is_first_1m_of_day": False,
                    "is_first_5m_of_day": False,
                    "is_first_30m_of_day": True,
                    "is_first_120m_of_day": True,
                    "previous_1m_period_source": "same_trade_date_previous_period",
                    "previous_5m_period_source": "same_trade_date_previous_period",
                    "previous_30m_period_source": "previous_trade_date_last_period",
                    "previous_120m_period_source": "previous_trade_date_last_period",
                    "source_fact_ids": {"source_snapshot_id": 1},
                    "source_minute_refs": [{"bar_id": 2}],
                    "previous_day_minute_refs": [{"bar_id": 3}],
                    "current_price": 10,
                    "current_price_time": "2026-06-02T09:36:00+08:00",
                    "previous_120m_body_high": 9,
                    "previous_120m_body_low": 8,
                    "previous_30m_body_high": 9,
                    "previous_30m_body_low": 8,
                    "previous_5m_body_high": 10,
                    "previous_5m_body_low": 9,
                    "previous_1m_body_high": 10,
                    "previous_1m_body_low": 9,
                    "current_1m_amount": 100,
                    "previous_1m_amount": 90,
                    "current_5m_virtual_amount": 100,
                    "previous_5m_full_amount": 450,
                    "current_30m_virtual_amount": 100,
                    "previous_day_same_window_amount": 4500,
                }
            ],
            "index": [],
            "board": [],
        }

        dry_run = build_action_confirmation_projection_dry_run_report(
            readiness_report=report,
            rows_by_asset=rows_by_asset,
        )

        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["would_write_rows"]["stock"], 1)
        self.assertEqual(dry_run["metric_ready_distribution"]["ready_total"], 1)
        self.assertEqual(dry_run["trace_refs_proof"]["db_check_pass_total"], 1)
        self.assertEqual(dry_run["quality"]["p0_count"], 0)


if __name__ == "__main__":
    unittest.main()
