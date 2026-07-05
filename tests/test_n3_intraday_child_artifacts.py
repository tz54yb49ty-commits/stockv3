import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.market.intraday_child_artifacts import (
    IntradayChildArtifactConflictError,
    IntradayChildArtifactRequest,
    build_intraday_child_artifact_plan,
    write_intraday_child_artifact_report,
    write_intraday_child_artifacts,
)
from ashare_v3.market.realtime_projection_execute import validate_projection_rows_against_contract
import scripts.run_n3_intraday_child_artifacts_once as child_artifact_cli


SUBSCRIPTION_RUN_ID = "market_data_subscription_20260611_condition_layer_x"
PRELOAD_RUN_ID = "previous_day_minute_preload_20260610_for_20260611__market_data_subscription_x"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260610_source_20260610_for_20260611_v1"


def make_request(
    tmp: str,
    *,
    projection_input_mode: str = "closed_minute",
    latest_closed_minute_hhmm: str = "0931",
    latest_closed_minute: str | None = "2026-06-11T09:31:00+08:00",
    subscription_summary: dict[str, object] | None = None,
) -> IntradayChildArtifactRequest:
    return IntradayChildArtifactRequest(
        for_trade_date="20260611",
        latest_closed_minute_hhmm=latest_closed_minute_hhmm,
        latest_closed_minute=latest_closed_minute,
        subscription_run_id=SUBSCRIPTION_RUN_ID,
        preload_run_id=PRELOAD_RUN_ID,
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        docs_root=str(Path(tmp) / "docs"),
        sql_root=str(Path(tmp) / "sql"),
        projection_input_mode=projection_input_mode,
        subscription_summary=subscription_summary,
    )


def make_20260612_request(
    tmp: str,
    *,
    projection_input_mode: str = "closed_minute",
) -> IntradayChildArtifactRequest:
    return IntradayChildArtifactRequest(
        for_trade_date="20260612",
        latest_closed_minute_hhmm="0931" if projection_input_mode == "closed_minute" else "0925",
        latest_closed_minute="2026-06-12T09:31:00+08:00" if projection_input_mode == "closed_minute" else None,
        subscription_run_id="market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        preload_run_id=(
            "previous_day_minute_preload_20260611_for_20260612__"
            "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
        ),
        source_condition_run_id="condition_layer_20260611_source_20260611_for_20260612_v1",
        docs_root=str(Path(tmp) / "docs"),
        sql_root=str(Path(tmp) / "sql"),
        projection_input_mode=projection_input_mode,
        subscription_summary=live_subscription_summary_20260612(),
    )


def live_subscription_summary_20260612() -> dict[str, object]:
    return {
        "source": "live_subscription_counts",
        "source_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
        "snapshot_object_count_by_asset_kind": {"stock": 1872, "index": 83, "board": 127},
        "today_minute_object_count_by_asset_kind": {"stock": 250, "index": 19, "board": 14},
    }


class N3IntradayChildArtifactTest(unittest.TestCase):
    def test_generator_builds_stable_paths_and_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = build_intraday_child_artifact_plan(make_request(tmp))
            second = build_intraday_child_artifact_plan(make_request(tmp))

            self.assertEqual(first["stage_run_ids"], second["stage_run_ids"])
            self.assertEqual(first["generated_artifacts"], second["generated_artifacts"])
            self.assertIn("realtime_daily_snapshot_20260611_until_0931__", first["stage_run_ids"]["B1"])
            self.assertIn("today_minute_bar_1m_20260611_until_0931__", first["stage_run_ids"]["C1"])
            self.assertIn("realtime_projection_metric_20260611_until_0931__", first["stage_run_ids"]["B2"])

    def test_generator_writes_required_child_artifacts_without_db_or_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            result = write_intraday_child_artifacts(plan)

            self.assertEqual(result["status"], "written")
            required_paths = [
                plan["generated_artifacts"]["B1"]["execute_contract_json"],
                plan["generated_artifacts"]["B1"]["execute_readiness_json"],
                plan["generated_artifacts"]["B1"]["rollback_sql"],
                plan["generated_artifacts"]["C1"]["c0_dry_run_json"],
                plan["generated_artifacts"]["C1"]["rollback_sql"],
                plan["generated_artifacts"]["B2"]["dry_run_json"],
                plan["generated_artifacts"]["B2"]["execute_contract_json"],
                plan["generated_artifacts"]["B2"]["execute_preflight_json"],
                plan["generated_artifacts"]["B2"]["rollback_sql"],
            ]
            for path in required_paths:
                self.assertTrue(Path(path).exists(), path)

            for section in plan["side_effects"].values():
                self.assertFalse(section)

    def test_generator_uses_subscription_dry_run_artifact_counts_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            docs_root.mkdir()
            (docs_root / "N3_A1_20260611_MARKET_DATA_SUBSCRIPTION_DRY_RUN.json").write_text(
                json.dumps(
                    {
                        "object_count_by_asset_kind": {"stock": 3, "index": 2, "board": 1},
                        "previous_day_minute_required_object_count_by_asset_kind": {
                            "stock": 2,
                            "index": 1,
                            "board": 1,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            plan = build_intraday_child_artifact_plan(make_request(tmp))
            b1_contract = json.loads(plan["artifact_payloads"]["B1"]["execute_contract_json"])
            c1_plan = json.loads(plan["artifact_payloads"]["C1"]["c0_dry_run_json"])

            self.assertEqual(b1_contract["expected_asset_counts"]["stock"]["subscription_count"], 3)
            self.assertEqual(b1_contract["expected_asset_counts"]["index"]["expected_snapshot_rows"], 2)
            self.assertEqual(c1_plan["today_minute_object_count_by_asset_kind"], {"board": 1, "index": 1, "stock": 2})
            self.assertEqual(c1_plan["expected_bar_count_per_object"], 1)
            self.assertEqual(c1_plan["expected_minute_rows_by_asset_kind"], {"board": 1, "index": 1, "stock": 2})

    def test_c1_generated_artifact_uses_intraday_expected_bar_count(self) -> None:
        cases = [
            ("1000", "2026-06-11T10:00:00+08:00", 30),
            ("1130", "2026-06-11T11:30:00+08:00", 120),
            ("1500", "2026-06-11T15:00:00+08:00", 240),
        ]
        for hhmm, latest_closed_minute, expected_bars in cases:
            with self.subTest(hhmm=hhmm), tempfile.TemporaryDirectory() as tmp:
                request = make_request(
                    tmp,
                    latest_closed_minute_hhmm=hhmm,
                    latest_closed_minute=latest_closed_minute,
                    subscription_summary={
                        "today_minute_object_count_by_asset_kind": {"stock": 2, "index": 1, "board": 1}
                    },
                )

                plan = build_intraday_child_artifact_plan(request)
                c1_plan = json.loads(plan["artifact_payloads"]["C1"]["c0_dry_run_json"])

                self.assertEqual(c1_plan["expected_bar_count_per_object"], expected_bars)
                self.assertEqual(
                    c1_plan["expected_minute_rows_by_asset_kind"],
                    {"board": expected_bars, "index": expected_bars, "stock": expected_bars * 2},
                )

    def test_b1_closed_minute_contract_and_readiness_use_live_subscription_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_20260612_request(tmp))
            b1_contract = json.loads(plan["artifact_payloads"]["B1"]["execute_contract_json"])
            b1_readiness = json.loads(plan["artifact_payloads"]["B1"]["execute_readiness_json"])

            expected = {
                "board": {"expected_snapshot_rows": 127, "object_count": 127, "subscription_count": 127},
                "index": {"expected_snapshot_rows": 83, "object_count": 83, "subscription_count": 83},
                "stock": {"expected_snapshot_rows": 1872, "object_count": 1872, "subscription_count": 1872},
            }
            self.assertEqual(b1_contract["expected_asset_counts"], expected)
            self.assertEqual(b1_readiness["expected_asset_counts"], expected)
            self.assertEqual(b1_contract["expected_row_count"], 2082)
            self.assertEqual(plan["subscription_summary"]["source"], "live_subscription_counts")

    def test_b1_fact_only_contract_uses_reviewed_untrusted_label_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_20260612_request(tmp))
            b1_contract = json.loads(plan["artifact_payloads"]["B1"]["execute_contract_json"])
            b1_readiness = json.loads(plan["artifact_payloads"]["B1"]["execute_readiness_json"])

            expected_policy = {
                "mode": "strict_live",
                "source_time_future_guard_enabled": True,
                "future_tolerance_seconds": 120,
                "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
                "untrusted_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
                "board_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
                "index_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
                "normalize_to_observed_at_enabled": True,
                "event_time_policy": "observed_at_for_untrusted_period_label",
                "fact_only_quality_policy": "quality_visible_source_time_label_normalized",
            }
            self.assertEqual(b1_contract["source_time_policy"], expected_policy)
            self.assertEqual(b1_readiness["source_time_policy"], expected_policy)
            self.assertTrue(b1_contract["fact_only_source_time_semantics_policy"]["reviewed_policy_enabled"])
            self.assertEqual(
                b1_contract["fact_only_source_time_semantics_policy"]["untrusted_period_label_handling"],
                "NORMALIZE_TO_OBSERVED_AT",
            )

    def test_b1_auction_contract_and_readiness_use_live_subscription_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(
                make_20260612_request(tmp, projection_input_mode="auction_or_snapshot_only")
            )
            b1_contract = json.loads(plan["artifact_payloads"]["B1"]["execute_contract_json"])
            b1_readiness = json.loads(plan["artifact_payloads"]["B1"]["execute_readiness_json"])

            self.assertEqual(b1_contract["expected_asset_counts"]["stock"]["subscription_count"], 1872)
            self.assertEqual(b1_contract["expected_asset_counts"]["index"]["subscription_count"], 83)
            self.assertEqual(b1_contract["expected_asset_counts"]["board"]["subscription_count"], 127)
            self.assertEqual(b1_readiness["expected_asset_counts"], b1_contract["expected_asset_counts"])
            self.assertIn("realtime_daily_snapshot_20260612_auction_0925__", b1_contract["snapshot_run_id"])

    def test_c1_generated_artifact_has_runner_compatible_source_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            c1_plan = json.loads(plan["artifact_payloads"]["C1"]["c0_dry_run_json"])

            self.assertEqual(c1_plan["source_market_data_run_id"], SUBSCRIPTION_RUN_ID)
            self.assertEqual(c1_plan["source_run_id"], SUBSCRIPTION_RUN_ID)
            self.assertEqual(c1_plan["source_condition_run_id"], SOURCE_CONDITION_RUN_ID)
            self.assertEqual(c1_plan["source_trade_date"], "20260610")
            self.assertEqual(c1_plan["prev_trade_date"], "20260610")
            self.assertEqual(c1_plan["latest_closed_minute"], "2026-06-11T09:31:00+08:00")
            self.assertEqual(c1_plan["execute_contract"]["source_market_data_run_id"], SUBSCRIPTION_RUN_ID)
            self.assertEqual(c1_plan["execute_contract"]["source_run_id"], SUBSCRIPTION_RUN_ID)

    def test_written_c1_artifact_keeps_runner_compatible_source_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            write_intraday_child_artifacts(plan)

            c1_artifact = Path(plan["generated_artifacts"]["C1"]["c0_dry_run_json"])
            c1_plan = json.loads(c1_artifact.read_text(encoding="utf-8"))

            self.assertEqual(c1_plan["source_market_data_run_id"], SUBSCRIPTION_RUN_ID)
            self.assertEqual(c1_plan["source_condition_run_id"], SOURCE_CONDITION_RUN_ID)
            self.assertEqual(c1_plan["latest_closed_minute"], "2026-06-11T09:31:00+08:00")

    def test_b2_auction_mode_uses_snapshot_only_and_does_not_require_or_forge_c1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(
                make_request(tmp, projection_input_mode="auction_or_snapshot_only")
            )

            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])
            b2_dry_run = json.loads(plan["artifact_payloads"]["B2"]["dry_run_json"])
            b2_preflight = json.loads(plan["artifact_payloads"]["B2"]["execute_preflight_json"])

            self.assertEqual(b2_contract["projection_input_mode"], "auction_or_snapshot_only")
            self.assertIsNone(b2_contract["source_runs"]["today_minute_run_id"])
            self.assertFalse(b2_contract["source_requirements"]["requires_today_minute_run"])
            self.assertTrue(b2_contract["source_requirements"]["requires_snapshot_run"])
            self.assertTrue(b2_contract["source_requirements"]["requires_previous_day_minute_run"])
            self.assertFalse(b2_dry_run["source_requirements"]["requires_today_minute_run"])
            self.assertEqual(b2_dry_run["result"], "DRY_RUN_PASS")
            self.assertFalse(b2_dry_run["blocked"])
            self.assertEqual(b2_preflight["result"], "PREFLIGHT_PASS")
            self.assertFalse(b2_preflight["blocked"])
            self.assertEqual(b2_preflight["blockers"], [])
            self.assertTrue(b2_contract["snapshot_only_execution_policy"]["noop_pass_no_write_allowed"])
            self.assertTrue(b2_contract["snapshot_only_execution_policy"]["is_auction_virtual"])
            self.assertEqual(
                b2_contract["snapshot_only_execution_policy"]["quality_status"],
                "pending_market_data",
            )
            self.assertFalse(b2_contract["snapshot_only_execution_policy"]["minute_bar_closed_written"])

    def test_b2_closed_minute_contract_has_runner_compatible_calculation_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])

            self.assertEqual(
                b2_contract["calculation_config"]["calculation_method"],
                "active_30m_bucket_projection_v1_strict_current_lineage",
            )
            self.assertEqual(
                b2_contract["calculation_config"]["calculation_config_hash"],
                "c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d",
            )
            self.assertEqual(b2_contract["calculation_config"]["window_total_seconds"], 1800)
            self.assertEqual(b2_contract["calculation_config"]["completion_ratio_min_ready"], "0.2")
            self.assertEqual(b2_contract["calculation_config"]["amount_projection_expand_threshold"], "1.2")
            self.assertEqual(b2_contract["calculation_config"]["amount_projection_shrink_threshold"], "0.8")
            self.assertEqual(b2_contract["calculation_config"]["price_flat_abs_pct_threshold"], "0.001")

    def test_b2_closed_minute_contract_has_runner_compatible_expected_distribution_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            docs_root.mkdir()
            (docs_root / "N3_A1_20260611_MARKET_DATA_SUBSCRIPTION_DRY_RUN.json").write_text(
                json.dumps(
                    {
                        "object_count_by_asset_kind": {"stock": 1, "index": 1, "board": 1},
                        "previous_day_minute_required_object_count_by_asset_kind": {
                            "stock": 1,
                            "index": 1,
                            "board": 1,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])
            b2_dry_run = json.loads(plan["artifact_payloads"]["B2"]["dry_run_json"])
            b2_preflight = json.loads(plan["artifact_payloads"]["B2"]["execute_preflight_json"])

            for payload in (b2_contract, b2_dry_run, b2_preflight):
                distribution = payload["expected_distribution"]
                self.assertIn("ready_rows", distribution)
                self.assertIn("not_ready_rows", distribution)
                self.assertIn("ready_by_asset", distribution)
                self.assertIn("not_ready_by_asset", distribution)
                self.assertIn("projection_signal_status", distribution)
                self.assertIn("board_not_ready", distribution)
                self.assertIn("bj_920xxx_not_ready", distribution)
                self.assertEqual(
                    payload["expected_distribution_policy"]["mode"],
                    "derive_from_projection_rows",
                )

            rows = [
                projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
                projection_row("index", "index:SH:000905", "not_ready", "unknown"),
                projection_row("board", "board:TDX:881001", "not_ready", "unknown"),
            ]
            validate_projection_rows_against_contract(rows, b2_contract)
            self.assertEqual(b2_contract["expected_distribution"]["ready_rows"], 1)
            self.assertEqual(b2_contract["expected_distribution"]["not_ready_rows"], 2)
            self.assertEqual(b2_contract["expected_distribution"]["ready_by_asset"], {"stock": 1})
            self.assertEqual(b2_contract["expected_distribution"]["not_ready_by_asset"], {"board": 1, "index": 1})
            self.assertEqual(b2_contract["expected_distribution"]["projection_signal_status"], {"unknown": 2, "up_volume_expanding": 1})
            self.assertEqual(b2_contract["expected_distribution"]["board_not_ready"], 1)

    def test_b2_closed_minute_contract_has_midday_defer_projection_time_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_20260612_request(tmp))
            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])
            b2_dry_run = json.loads(plan["artifact_payloads"]["B2"]["dry_run_json"])
            b2_preflight = json.loads(plan["artifact_payloads"]["B2"]["execute_preflight_json"])

            for payload in (b2_contract, b2_dry_run, b2_preflight):
                policy = payload["projection_time_policy"]
                self.assertEqual(policy["mode"], "fact_only_defer_off_bucket_source_snapshot_time")
                self.assertEqual(policy["bucket_time_source"], "source_snapshot_time")
                self.assertEqual(policy["off_bucket_source_snapshot_time_handling"], "NOOP_PASS_NO_WRITE")
                self.assertTrue(policy["no_closed_data_forged"])
                self.assertFalse(policy["maps_midday_to_trading_bucket"])

    def test_b2_closed_minute_contract_enables_fact_only_snapshot_trace_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_20260612_request(tmp))
            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])
            b2_dry_run = json.loads(plan["artifact_payloads"]["B2"]["dry_run_json"])
            b2_preflight = json.loads(plan["artifact_payloads"]["B2"]["execute_preflight_json"])

            expected_policy = {
                "allow_missing_snapshot_event_id": True,
                "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
            }
            for payload in (b2_contract, b2_dry_run, b2_preflight):
                self.assertEqual(payload["fact_only_snapshot_trace_policy"], expected_policy)

    def test_b2_auction_contract_has_runner_compatible_calculation_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(
                make_request(tmp, projection_input_mode="auction_or_snapshot_only")
            )
            b2_contract = json.loads(plan["artifact_payloads"]["B2"]["execute_contract_json"])

            self.assertEqual(
                b2_contract["calculation_config"]["calculation_method"],
                "active_30m_bucket_projection_v1_strict_current_lineage",
            )
            self.assertEqual(b2_contract["calculation_config"]["window_total_seconds"], 1800)
            self.assertIsNone(b2_contract["source_runs"]["today_minute_run_id"])
            self.assertFalse(b2_contract["source_requirements"]["requires_today_minute_run"])
            self.assertEqual(b2_contract["expected_distribution_policy"]["mode"], "derive_from_projection_rows")

    def test_generator_blocks_existing_conflicting_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            conflict_path = Path(plan["generated_artifacts"]["B1"]["execute_contract_json"])
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_text('{"different": true}\n', encoding="utf-8")

            with self.assertRaises(IntradayChildArtifactConflictError):
                write_intraday_child_artifacts(plan)

    def test_generator_allows_identical_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            first = write_intraday_child_artifacts(plan)
            second = write_intraday_child_artifacts(plan)

            self.assertEqual(first["status"], "written")
            self.assertEqual(second["status"], "unchanged")
            self.assertGreater(second["unchanged_artifact_count"], 0)

    def test_generated_rollback_sql_hard_fails_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_request(tmp))
            write_intraday_child_artifacts(plan)

            for stage in ("B1", "C1", "B2"):
                sql = Path(plan["generated_artifacts"][stage]["rollback_sql"]).read_text(encoding="utf-8")
                self.assertIn("RAISE EXCEPTION", sql)
                self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
                self.assertNotIn("DROP ", sql.upper())
                self.assertNotIn("TRUNCATE", sql.upper())
                self.assertNotIn("CASCADE", sql.upper())
                self.assertIn("common_event_outbox", sql)
                self.assertIn("common_event_inbox", sql)
                self.assertIn("common_event_consumer_checkpoint", sql)
                self.assertIn("common_trigger_state", sql)

    def test_generated_b1_rollback_uses_runtime_schema_run_id_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_intraday_child_artifact_plan(make_20260612_request(tmp))
            write_intraday_child_artifacts(plan)

            sql = Path(plan["generated_artifacts"]["B1"]["rollback_sql"]).read_text(encoding="utf-8")

            self.assertIn("DELETE FROM stock_realtime_daily_snapshot WHERE run_id =", sql)
            self.assertIn("DELETE FROM index_realtime_daily_snapshot WHERE run_id =", sql)
            self.assertIn("DELETE FROM board_realtime_daily_snapshot WHERE run_id =", sql)
            self.assertIn("DELETE FROM common_market_data_quality_item WHERE run_id =", sql)
            self.assertNotIn("source_run_id = 'realtime_daily_snapshot", sql)
            self.assertNotIn("snapshot_run_id = 'realtime_daily_snapshot", sql)

    def test_cli_defaults_to_plan_only_and_does_not_write_child_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            sql_root = Path(tmp) / "sql"
            report_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"

            with contextlib.redirect_stdout(io.StringIO()):
                rc = child_artifact_cli.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--latest-closed-minute-hhmm",
                        "0931",
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--docs-root",
                        str(docs_root),
                        "--sql-root",
                        str(sql_root),
                        "--json-report-path",
                        str(report_path),
                        "--markdown-report-path",
                        str(md_path),
                        "--json",
                    ]
                )

            self.assertEqual(rc, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertFalse(Path(report["generated_artifacts"]["B1"]["execute_contract_json"]).exists())
            self.assertTrue(md_path.exists())

    def test_cli_write_artifacts_requires_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"

            with contextlib.redirect_stdout(io.StringIO()):
                rc = child_artifact_cli.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--latest-closed-minute-hhmm",
                        "0931",
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--docs-root",
                        str(Path(tmp) / "docs"),
                        "--sql-root",
                        str(Path(tmp) / "sql"),
                        "--json-report-path",
                        str(report_path),
                        "--markdown-report-path",
                        str(md_path),
                        "--write-artifacts",
                        "--json",
                    ]
                )

            self.assertEqual(rc, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["result"], "ARTIFACT_WRITE_PASS")
            self.assertTrue(Path(report["generated_artifacts"]["B2"]["execute_preflight_json"]).exists())


def projection_row(asset_kind: str, identity_key: str, status: str, signal: str) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "projection_status": status,
        "projection_quality_status": "passed" if status == "ready" else "blocked",
        "trace_status": "passed" if status == "ready" else "blocked",
        "projection_signal_status": signal,
    }


if __name__ == "__main__":
    unittest.main()
