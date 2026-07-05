import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ashare_v3.market.action_confirmation_projection_plan import (
    build_action_confirmation_projection_dry_run_report,
    build_metric_candidate_rows_from_sources,
)
from ashare_v3.market.projection_enrichment import (
    PROJECTION_ENRICHMENT_REQUIRED_FIELDS,
    build_projection_enrichment_v1,
    build_trigger_amount_chain_pass,
)


class N3ProjectionEnrichmentImplementationTest(unittest.TestCase):
    def test_implementation_report_artifact_records_no_execute_boundary(self) -> None:
        report_path = Path("docs/N3_projection_enrichment_implementation_report.json")
        markdown_path = Path("docs/N3_PROJECTION_ENRICHMENT_IMPLEMENTATION_REPORT.md")

        self.assertTrue(report_path.exists())
        self.assertTrue(markdown_path.exists())
        report = json.loads(report_path.read_text())

        self.assertEqual(report["result"], "IMPLEMENTATION_PASS")
        self.assertEqual(report["storage_path"], "raw_json.enrichment_v1")
        self.assertFalse(report["side_effects"]["database_written"])
        self.assertFalse(report["side_effects"]["outbox_consumed"])
        self.assertFalse(report["side_effects"]["downstream_layers_touched"])
        self.assertTrue(report["runtime_control_v4_readiness_review"]["allowed"])
        self.assertIn("raw_json.enrichment_v1", markdown_path.read_text())

    def _minute_iso(self, date: str, index: int) -> str:
        base = datetime(int(date[:4]), int(date[4:6]), int(date[6:]), 9, 31, tzinfo=timezone(timedelta(hours=8)))
        return (base + timedelta(minutes=index - 1)).isoformat()

    def _n2_context(self, *, direction: str = "buy") -> dict:
        return {
            "direction": direction,
            "period_trigger_baseline_json": {
                "context_enrichment": {"context_enrichment_version": "N2-context-enrichment-v1"},
                "periods": {
                    "Y": {"period_baseline_ready": True, "previous_amount_baseline": "400"},
                    "Q": {"period_baseline_ready": True, "previous_amount_baseline": "300"},
                    "M": {"period_baseline_ready": True, "previous_amount_baseline": "200"},
                    "W": {"period_baseline_ready": True, "previous_amount_baseline": "100"},
                    "D": {"period_baseline_ready": True, "previous_amount_baseline": "50"},
                },
            },
        }

    def _current_chain_metrics(self) -> dict:
        return {
            "today_virt_amount": 130,
            "weekly_avg_with_today": 120,
            "weekly_virt_amount": 230,
            "monthly_avg_with_today": 220,
            "monthly_virt_amount": 330,
            "quarterly_avg_with_today": 320,
            "quarterly_virt_amount": 430,
            "yearly_avg_with_today": 420,
        }

    def test_trigger_amount_chain_pass_uses_n2_baseline_and_n3_current_metrics(self) -> None:
        chain = build_trigger_amount_chain_pass(
            n2_context=self._n2_context(direction="buy"),
            current_chain_metrics=self._current_chain_metrics(),
            projection_30m_pass=True,
        )

        self.assertEqual(
            {key: chain[key] for key in ("Y", "Q", "M", "W", "D", "projection_30m")},
            {"Y": True, "Q": True, "M": True, "W": True, "D": True, "projection_30m": True},
        )
        self.assertEqual(chain["_trace"]["owner"], "N3_market_data")
        self.assertFalse(chain["_trace"]["n4_recompute_allowed"])
        self.assertIn("N2 period_trigger_baseline_json", chain["_trace"]["inputs"])
        self.assertIn("N3 current_chain_metrics", chain["_trace"]["inputs"])

    def test_candidate_rows_store_enrichment_v1_inside_raw_json(self) -> None:
        snapshot_rows = {
            "stock": [
                {
                    "source_snapshot_id": 501,
                    "source_snapshot_event_id": "event-501",
                    "identity_key": "stock:SH:600000",
                    "exchange": "SH",
                    "code": "600000",
                    "display_code": "600000.SH",
                    "name": "PF Bank",
                    "trade_date": "20260602",
                    "snapshot_time": "2026-06-02T10:05:30+08:00",
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
                    "amount": 6000 if i >= 31 else 1000,
                }
                for i in range(1, 36)
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
                    "open": 9.0,
                    "close": 9.1,
                    "amount": 900,
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
            n2_context_by_asset={"stock": {"stock:SH:600000": self._n2_context(direction="buy")}},
            current_chain_metrics_by_asset={"stock": {"stock:SH:600000": self._current_chain_metrics()}},
        )

        row = rows["stock"][0]
        enrichment = row["raw_json"]["enrichment_v1"]
        self.assertEqual(set(PROJECTION_ENRICHMENT_REQUIRED_FIELDS), set(enrichment))
        self.assertNotIn("current_price_or_close", row)
        self.assertEqual(enrichment["current_price_or_close"], "10.5")
        self.assertEqual(enrichment["projection_period"], "30m")
        self.assertTrue(enrichment["projection_30m_flag"])
        self.assertEqual(enrichment["projection_30m_type"], "volume_up")
        self.assertEqual(enrichment["source_snapshot_run_id"], "snapshot")
        self.assertEqual(enrichment["source_minute_run_id"], "today")
        self.assertEqual(enrichment["source_previous_day_minute_run_id"], "previous")
        self.assertTrue(enrichment["trigger_amount_chain_pass"]["D"])
        self.assertFalse(enrichment["projection_lineage_json"]["n4_recompute_allowed"])

    def test_live_current_1m_lineage_is_preserved_without_c1_dependency(self) -> None:
        live_source_run_id = (
            "live_current_1m_source_20260602_until_1005__"
            "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"
        )
        enrichment = build_projection_enrichment_v1(
            metric_row={
                "current_price": 10.5,
                "source_condition_run_id": "condition",
                "source_subscription_run_id": "subscription",
                "source_snapshot_run_id": "snapshot",
                "source_today_minute_run_id": live_source_run_id,
                "source_previous_day_minute_run_id": "previous",
                "metric_quality_status": "passed",
                "metric_time": "2026-06-02T10:05:00+08:00",
                "source_fact_ids": {
                    "source_mode": "live_current_1m",
                    "source_live_minute_run_id": live_source_run_id,
                    "c1_dependency": False,
                },
                "trace_json": {
                    "source_mode": "live_current_1m",
                    "c1_dependency": False,
                },
            },
            n2_context=self._n2_context(direction="buy"),
            current_chain_metrics=self._current_chain_metrics(),
            current_30m_virtual_amount=800,
            reference_30m_amount=700,
            reference_30m_entity_high=10,
            reference_30m_entity_low=9,
        )

        lineage = enrichment["projection_lineage_json"]
        self.assertEqual(enrichment["source_minute_run_id"], live_source_run_id)
        self.assertEqual(lineage["source_minute_run_id"], live_source_run_id)
        self.assertEqual(lineage["source_mode"], "live_current_1m")
        self.assertEqual(lineage["source_live_minute_run_id"], live_source_run_id)
        self.assertFalse(lineage["c1_dependency"])

    def test_dry_run_report_exposes_projection_enrichment_coverage(self) -> None:
        readiness = {
            "result": "DRAFT_PASS",
            "projection_run_id": "projection",
            "projection_schema_version": "n3.action_confirmation_metric.v1",
            "for_trade_date": "20260602",
            "source_condition_run_id": "condition",
            "source_subscription_run_id": "subscription",
            "source_snapshot_run_id": "snapshot",
            "source_today_minute_run_id": "today",
            "source_previous_day_minute_run_id": "previous",
            "candidate_summary": {"stock": 1, "index": 0, "board": 0, "total": 1},
            "baseline_summary": {
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "stock_action_confirmation_projection_metric": 0,
                "index_action_confirmation_projection_metric": 0,
                "board_action_confirmation_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
        }
        rows_by_asset = {
            "stock": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "metric_ready": True,
                    "metric_quality_status": "passed",
                    "current_price_source": "realtime_daily_snapshot",
                    "source_fact_ids": {"source_snapshot_id": 1},
                    "source_minute_refs": [{"bar_id": 2}],
                    "previous_day_minute_refs": [{"bar_id": 3}],
                    "current_price": 10,
                    "current_price_time": "2026-06-02T09:36:00+08:00",
                    "previous_120m_body_high": 9,
                    "previous_120m_body_low": 8,
                    "previous_30m_body_high": 9,
                    "previous_30m_body_low": 8,
                    "previous_5m_body_high": 9,
                    "previous_5m_body_low": 8,
                    "previous_1m_body_high": 9,
                    "previous_1m_body_low": 8,
                    "current_1m_amount": 100,
                    "current_5m_virtual_amount": 500,
                    "current_30m_virtual_amount": 500,
                    "previous_day_same_window_amount": 450,
                    "previous_1m_period_source": "previous_trade_date_last_period",
                    "previous_5m_period_source": "previous_trade_date_last_period",
                    "previous_30m_period_source": "previous_trade_date_last_period",
                    "previous_120m_period_source": "previous_trade_date_last_period",
                    "is_first_1m_of_day": True,
                    "is_first_5m_of_day": True,
                    "first_1m_amount_default_pass": True,
                    "first_5m_amount_default_pass": True,
                    "raw_json": {
                        "enrichment_v1": {field: "present" for field in PROJECTION_ENRICHMENT_REQUIRED_FIELDS}
                    },
                }
            ],
            "index": [],
            "board": [],
        }

        dry_run = build_action_confirmation_projection_dry_run_report(
            readiness_report=readiness,
            rows_by_asset=rows_by_asset,
        )

        self.assertEqual(dry_run["result"], "DRY_RUN_PASS")
        self.assertEqual(dry_run["projection_enrichment_summary"]["rows_with_enrichment_v1"], 1)
        self.assertEqual(dry_run["projection_enrichment_summary"]["missing_required_field_rows"], 0)
        self.assertFalse(dry_run["projection_enrichment_summary"]["n4_recompute_allowed"])


if __name__ == "__main__":
    unittest.main()
