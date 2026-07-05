from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.market import historical_closed_minute_source_expansion as runner


def _candidate(asset_kind: str, sequence: int, expected_rows: int = 181) -> dict:
    code = f"{sequence:06d}"
    exchange = "SH" if asset_kind != "board" else "TDX"
    return {
        "candidate_sequence": sequence,
        "asset_kind": asset_kind,
        "identity_key": f"{asset_kind}:{exchange}:{code}",
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": f"name-{sequence}",
        "source_subscription_id": sequence,
        "source_subscription_run_id": "market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_condition_run_id": "condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_previous_day_minute_run_id": "previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_scope_ids": [sequence],
        "source_condition_pool_ids": [sequence + 1000],
        "data_trade_date": "20260616",
        "expected_minute_rows": expected_rows,
        "target_expansion_run_id": "historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4",
    }


def _payload() -> dict:
    candidates = []
    sequence = 1
    for asset, count in runner.EXPECTED_MISSING_BY_ASSET.items():
        for _ in range(count):
            candidates.append(_candidate(asset, sequence))
            sequence += 1
    return {
        "target_expansion_run_id": "historical_closed_minute_source_expansion_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_condition_run_id": "condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_trade_date": "20260615",
        "for_trade_date": "20260616",
        "data_trade_date": "20260616",
        "latest_closed_minute": "2026-06-16 14:01:00+08:00",
        "bar_count_per_object_until_latest_closed_minute": 181,
        "missing_scope": {
            "by_asset": {
                "stock": {"missing_objects": 415},
                "index": {"missing_objects": 13},
                "board": {"missing_objects": 39},
            },
            "total": {"missing_objects": 467},
        },
        "planned_write_scope": {
            "stock_minute_rows": 75115,
            "index_minute_rows": 2353,
            "board_minute_rows": 7059,
            "total_minute_rows": 84527,
        },
        "source_policy": {
            "stale_v1_b1_c1_reuse_allowed": False,
            "fake_realtime_snapshot_allowed": False,
        },
        "missing_candidates": candidates,
    }


class EmptyAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_minute_bars(self, candidate: dict, trade_date: str) -> list[dict]:
        self.calls += 1
        return []


class RecordingAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def fetch_minute_bars(self, candidate: dict, trade_date: str) -> list[dict]:
        self.calls.append((candidate["required_data_kind"], trade_date))
        expected = int(candidate["expected_minute_rows"])
        if trade_date == "20260615":
            start = "2026-06-15"
        else:
            start = "2026-06-16"
        rows = []
        for index in range(expected):
            minute = 31 + index
            hour = 9 + minute // 60
            minute = minute % 60
            rows.append(
                {
                    "bar_time": f"{start} {hour:02d}:{minute:02d}:00",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 10,
                    "amount": 20,
                }
            )
        return rows


def _combined_payload(subscription_control_row_present: bool = True) -> dict:
    target = "historical_source_expansion_combined_scope"
    base_candidate = _candidate("stock", 1, expected_rows=240)
    previous_day_candidate = {
        **base_candidate,
        "target_expansion_run_id": target,
        "required_data_kind": "previous_day_minute_bar_1m",
        "data_trade_date": "20260615",
        "is_previous_day_preload": True,
        "latest_closed_minute": "2026-06-15 15:00:00+08:00",
        "subscription_control_row_present": subscription_control_row_present,
    }
    current_candidate = {
        **base_candidate,
        "candidate_sequence": 2,
        "target_expansion_run_id": target,
        "required_data_kind": "minute_bar_1m",
        "data_trade_date": "20260616",
        "expected_minute_rows": 181,
        "is_previous_day_preload": False,
        "latest_closed_minute": "2026-06-16 14:01:00+08:00",
        "subscription_control_row_present": subscription_control_row_present,
    }
    return {
        "target_expansion_run_id": target,
        "source_condition_run_id": "condition_layer_20260615_source_20260615_for_20260616_v4",
        "source_trade_date": "20260615",
        "for_trade_date": "20260616",
        "latest_closed_minute": "2026-06-16 14:01:00+08:00",
        "planned_write_scope": {
            "planned_rows_by_asset": {
                "stock": {
                    "previous_day_missing_objects": 1,
                    "current_closed_minute_missing_objects": 1,
                    "combined_planned_rows": 421,
                },
                "index": {
                    "previous_day_missing_objects": 0,
                    "current_closed_minute_missing_objects": 0,
                    "combined_planned_rows": 0,
                },
                "board": {
                    "previous_day_missing_objects": 0,
                    "current_closed_minute_missing_objects": 0,
                    "combined_planned_rows": 0,
                },
            },
            "total_minute_rows": 421,
        },
        "source_policy": {
            "stale_v1_b1_c1_reuse_allowed": False,
            "fake_realtime_snapshot_allowed": False,
        },
        "missing_candidates": [previous_day_candidate, current_candidate],
    }


class HistoricalClosedMinuteSourceExpansionTests(unittest.TestCase):
    def test_execute_flags_allow_plan_only_and_block_half_confirmed(self) -> None:
        runner.require_execute_flags(execute=False, user_confirmed=False)
        with self.assertRaisesRegex(runner.HistoricalClosedMinuteSourceExpansionBlocked, "missing --user-confirmed"):
            runner.require_execute_flags(execute=True, user_confirmed=False)
        with self.assertRaisesRegex(runner.HistoricalClosedMinuteSourceExpansionBlocked, "missing --execute"):
            runner.require_execute_flags(execute=False, user_confirmed=True)

    def test_validate_payload_rejects_stale_v1_reuse_policy(self) -> None:
        payload = _payload()
        payload["source_policy"]["stale_v1_b1_c1_reuse_allowed"] = True
        with self.assertRaisesRegex(runner.HistoricalClosedMinuteSourceExpansionBlocked, "stale v1"):
            runner.validate_payload(payload)

    def test_validate_payload_rejects_missing_required_lineage_field(self) -> None:
        payload = _payload()
        del payload["source_condition_run_id"]
        with self.assertRaisesRegex(runner.HistoricalClosedMinuteSourceExpansionBlocked, "source_condition_run_id"):
            runner.validate_payload(payload)

    def test_plan_only_writes_report_without_adapter_or_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.json"
            report_path = Path(tmp) / "report.json"
            report_md_path = Path(tmp) / "report.md"
            payload_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

            report = runner.run_historical_closed_minute_source_expansion(
                dsn="postgresql://must-not-be-used",
                payload_path=payload_path,
                json_report_path=report_path,
                markdown_report_path=report_md_path,
            )

            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertFalse(report["database_written"])
            self.assertFalse(report["adapter_called"])
            self.assertEqual(json.loads(report_path.read_text())["result"], "PLAN_ONLY")

    def test_validate_payload_accepts_combined_previous_day_and_current_scope(self) -> None:
        runner.validate_payload(_combined_payload())

    def test_combined_payload_fetches_each_candidate_trade_date(self) -> None:
        payload = _combined_payload()
        adapter = RecordingAdapter()

        rows_by_identity, fetch_results = runner.build_adapter_rows(payload=payload, adapter=adapter)

        self.assertEqual(
            adapter.calls,
            [("previous_day_minute_bar_1m", "20260615"), ("minute_bar_1m", "20260616")],
        )
        self.assertEqual(len(rows_by_identity), 2)
        self.assertEqual([item["status"] for item in fetch_results], ["fetched", "fetched"])

    def test_combined_payload_preserves_previous_day_and_current_flags(self) -> None:
        payload = _combined_payload()
        adapter = RecordingAdapter()
        rows_by_identity, _ = runner.build_adapter_rows(payload=payload, adapter=adapter)

        records, results = runner.build_minute_records_for_candidates(
            payload=payload,
            adapter_rows_by_identity=rows_by_identity,
        )

        self.assertEqual([item["status"] for item in results], ["passed", "passed"])
        self.assertEqual(len(records["stock"]), 421)
        previous_rows = [row for row in records["stock"] if row["trade_date"] == "20260615"]
        current_rows = [row for row in records["stock"] if row["trade_date"] == "20260616"]
        self.assertEqual(len(previous_rows), 240)
        self.assertEqual(len(current_rows), 181)
        self.assertTrue(all(row["is_previous_day_preload"] for row in previous_rows))
        self.assertTrue(all(not row["is_previous_day_preload"] for row in current_rows))
        self.assertEqual(previous_rows[0]["raw_json"]["required_data_kind"], "previous_day_minute_bar_1m")
        self.assertEqual(current_rows[0]["raw_json"]["required_data_kind"], "minute_bar_1m")

    def test_build_records_filters_to_latest_closed_minute_and_preserves_scope(self) -> None:
        payload = {
            "target_expansion_run_id": "expansion_run",
            "source_condition_run_id": "condition_run",
            "for_trade_date": "20260616",
            "latest_closed_minute": "2026-06-16 09:32:00+08:00",
            "bar_count_per_object_until_latest_closed_minute": 2,
            "missing_candidates": [_candidate("stock", 1, expected_rows=2)],
        }
        identity = payload["missing_candidates"][0]["identity_key"]
        records, results = runner.build_minute_records_for_candidates(
            payload=payload,
            adapter_rows_by_identity={
                identity: [
                    {"bar_time": "2026-06-16 09:31:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10, "amount": 20},
                    {"bar_time": "2026-06-16 09:32:00", "open": 2, "high": 3, "low": 2, "close": 3, "volume": 11, "amount": 33},
                    {"bar_time": "2026-06-16 09:33:00", "open": 3, "high": 4, "low": 3, "close": 4, "volume": 12, "amount": 48},
                ]
            },
        )

        self.assertEqual(results[0]["status"], "passed")
        self.assertEqual(len(records["stock"]), 2)
        self.assertEqual(records["stock"][0]["run_id"], "expansion_run")
        self.assertEqual(records["stock"][0]["source_adapter"], runner.SOURCE_ADAPTER)
        self.assertFalse(records["stock"][0]["raw_json"]["stale_v1_b1_c1_reused"])
        self.assertFalse(records["stock"][0]["raw_json"]["fake_realtime_snapshot"])

    def test_execute_blocks_before_db_write_when_adapter_rows_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.json"
            report_path = Path(tmp) / "report.json"
            report_md_path = Path(tmp) / "report.md"
            payload_path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            adapter = EmptyAdapter()

            report = runner.run_historical_closed_minute_source_expansion(
                dsn="postgresql://must-not-be-used",
                payload_path=payload_path,
                json_report_path=report_path,
                markdown_report_path=report_md_path,
                execute=True,
                user_confirmed=True,
                adapter=adapter,
            )

            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(report["blocked_reason"], "object_minute_rows_incomplete_before_db_write")
            self.assertFalse(report["database_written"])
            self.assertEqual(adapter.calls, 467)

    def test_execute_blocks_before_adapter_when_subscription_control_rows_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.json"
            report_path = Path(tmp) / "report.json"
            report_md_path = Path(tmp) / "report.md"
            payload_path.write_text(json.dumps(_combined_payload(False), ensure_ascii=False), encoding="utf-8")
            adapter = RecordingAdapter()

            report = runner.run_historical_closed_minute_source_expansion(
                dsn="postgresql://must-not-be-used",
                payload_path=payload_path,
                json_report_path=report_path,
                markdown_report_path=report_md_path,
                execute=True,
                user_confirmed=True,
                adapter=adapter,
            )

            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(report["blocked_reason"], "subscription_control_rows_missing_before_adapter_fetch")
            self.assertFalse(report["database_written"])
            self.assertFalse(report["adapter_called"])
            self.assertEqual(adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
