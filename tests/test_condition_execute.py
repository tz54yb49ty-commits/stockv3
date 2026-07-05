import unittest
from datetime import datetime

from ashare_v3.condition.execute import (
    ConditionExecuteError,
    DISPLAY_COLUMNS,
    FULL_ROLLBACK_ORDER,
    build_execute_run_id,
    expected_rows_with_display,
    monitor_target_row,
    pool_preview_for_execute,
    scope_insert_row,
    to_jsonable,
    verify_row_counts,
)
from ashare_v3.condition.basis import active_versions_from_ready_check
from scripts.run_condition_layer_execute import (
    build_source_not_ready_preflight,
    condition_runner_report_metadata,
    load_condition_runner_policy,
    resolve_condition_runner_policy,
)


def write_policy_artifact(payload):
    import json
    import tempfile
    from pathlib import Path

    tmpdir = tempfile.TemporaryDirectory()
    path = Path(tmpdir.name) / "policy.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    write_policy_artifact._tmpdirs.append(tmpdir)
    return path


write_policy_artifact._tmpdirs = []


class ConditionExecuteTest(unittest.TestCase):
    def test_build_execute_run_id_uses_date_pair_and_execute_suffix(self) -> None:
        run_id = build_execute_run_id("20260522", "20260525", now=datetime(2026, 5, 23, 19, 30, 0))

        self.assertEqual(run_id, "condition_layer_20260522_to_20260525_20260523193000_execute")

    def test_build_execute_run_id_accepts_explicit_override(self) -> None:
        run_id = build_execute_run_id(
            "20260526",
            "20260527",
            now=datetime(2026, 5, 27, 10, 30, 0),
            run_id_override="condition_layer_20260526_source_20260526_v1",
        )

        self.assertEqual(run_id, "condition_layer_20260526_source_20260526_v1")

    def test_stock_monitor_target_row_uses_execute_run_id_as_rollback_anchor(self) -> None:
        row = monitor_target_row(
            "stock",
            "condition_layer_x",
            {
                "for_trade_date": "20260525",
                "source_trade_date": "20260522",
                "stock_identity_key": "stock:SH:600000",
                "code": "600000",
                "exchange": "SH",
                "name": "浦发银行",
                "lane": "stock_alert",
                "direction_scope": ["buy", "sell"],
            },
        )

        self.assertEqual(row["monitor_type"], "stock_hint_monitor")
        self.assertEqual(row["source_version"], "condition_layer_x")
        self.assertEqual(row["source"], "condition_execute_fact_universe")

    def test_verify_row_counts_raises_on_mismatch(self) -> None:
        with self.assertRaises(ConditionExecuteError):
            verify_row_counts(
                {"stock_condition_basis": 1},
                {"stock_condition_basis": {"row_count": 2}},
            )

    def test_to_jsonable_converts_decimal_like_values(self) -> None:
        payload = to_jsonable({"items": [{"value": object()}]})

        self.assertIsInstance(payload["items"][0]["value"], str)

    def test_scope_insert_row_maps_pool_ref_for_index_and_board(self) -> None:
        index_row = scope_insert_row(
            "index",
            "condition_layer_x",
            {
                "index_identity_key": "index:SH:000905",
                "identity_key": "index:SH:000905",
                "condition_periods": [],
                "allowed_signal_types": ["BUY_HINT"],
                "source_condition_pool_ref": "dry_run:index:pool:1",
                "raw_json": {},
            },
            {"dry_run:index:pool:1": 11},
        )
        board_row = scope_insert_row(
            "board",
            "condition_layer_x",
            {
                "board_identity_key": "board:TDX:881001",
                "identity_key": "board:TDX:881001",
                "condition_periods": [],
                "allowed_signal_types": ["SELL_HINT"],
                "source_condition_pool_ref": "dry_run:board:pool:1",
                "raw_json": {},
            },
            {"dry_run:board:pool:1": 12},
        )

        self.assertEqual(index_row["source_condition_pool_id"], 11)
        self.assertEqual(index_row["index_identity_key"], "index:SH:000905")
        self.assertEqual(board_row["source_condition_pool_id"], 12)
        self.assertEqual(board_row["board_identity_key"], "board:TDX:881001")

    def test_execute_expected_rows_includes_display_counts_and_quality_items(self) -> None:
        expected = expected_rows_with_display(
            {"common_condition_quality_item": {"row_count": 76}},
            display_quality_item_count=28,
            display_row_counts={"stock": 5504, "index": 81, "board": 428},
        )

        self.assertEqual(expected["common_condition_quality_item"]["row_count"], 104)
        self.assertEqual(expected["stock_condition_display_basis"]["row_count"], 5504)
        self.assertEqual(expected["index_condition_display_basis"]["row_count"], 81)
        self.assertEqual(expected["board_condition_display_basis"]["row_count"], 428)

    def test_display_tables_are_first_in_rollback_order(self) -> None:
        self.assertEqual(
            list(FULL_ROLLBACK_ORDER[:3]),
            [
                "stock_condition_display_basis",
                "index_condition_display_basis",
                "board_condition_display_basis",
            ],
        )

    def test_execute_display_columns_include_buy_expected_return_pct_for_all_domains(self) -> None:
        for domain in ("stock", "index", "board"):
            with self.subTest(domain=domain):
                self.assertIn("buy_expected_return_pct", DISPLAY_COLUMNS[domain])

    def test_execute_uses_policy_aware_pool_report_instead_of_rebuilding_default_pool(self) -> None:
        custom_preview = {
            "stock": {"pool_rows": [{"identity_key": "stock:SH:600000"}]},
            "index": {"pool_rows": []},
            "board": {"pool_rows": [{"identity_key": "board:TDX:885001"}]},
        }

        self.assertIs(
            pool_preview_for_execute({}, {"pool_preview": custom_preview}),
            custom_preview,
        )

    def test_runner_loads_web_policy_draft_as_scope_and_condition_pool_policy(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        policy_artifact = {
            "artifact_type": "n2_web_policy_default_draft",
            "web_policy": {
                "policy_name": "console_saved",
                "index": {
                    "selected_identity_key": "__all__",
                    "enabled_identities": [],
                    "directions": ["buy", "sell"],
                    "condition_family": ["ordinary", "full", "hint"],
                    "condition_keys": ["*"],
                },
                "board": {
                    "board_segments": ["industry", "concept", "region"],
                    "board_types": ["tdx_industry", "tdx_concept", "tdx_region"],
                    "directions": ["buy", "sell"],
                    "condition_family": ["ordinary", "full", "hint"],
                    "condition_keys": ["*"],
                },
                "stock": {
                    "min_total_mv_yi": 100,
                    "exclude_st": True,
                    "exclude_bj": True,
                    "directions": ["buy", "sell"],
                    "condition_family": ["ordinary", "full", "hint"],
                    "condition_keys": ["*"],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "default_policy_draft.json"
            path.write_text(json.dumps(policy_artifact, ensure_ascii=False), encoding="utf-8")

            bundle = load_condition_runner_policy(path)

        self.assertEqual(bundle.policy_name, "console_saved")
        self.assertEqual(bundle.scope_policy["board"]["board_types"], ["tdx_industry", "tdx_concept", "tdx_region"])
        self.assertEqual(
            bundle.condition_pool_policy["board"]["board_types"],
            ["tdx_industry", "tdx_concept", "tdx_region"],
        )
        self.assertTrue(bundle.condition_pool_policy["index"]["include_all_identities"])

    def test_runner_uses_saved_default_policy_draft_when_no_policy_argument(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            policy_path = Path(tmpdir) / "configs" / "n2_policy" / "default_policy_draft.json"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n2_web_policy_default_draft",
                        "web_policy": {
                            "policy_name": "saved_default",
                            "board": {
                                "board_segments": ["concept"],
                                "board_types": ["tdx_concept"],
                                "directions": ["buy", "sell"],
                                "condition_family": ["ordinary", "full", "hint"],
                                "condition_keys": ["*"],
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bundle = resolve_condition_runner_policy("", project_root=Path(tmpdir))

        self.assertEqual(bundle.policy_name, "saved_default")
        self.assertEqual(bundle.policy_source, "n2_web_policy_default_draft")
        self.assertEqual(bundle.condition_pool_policy["board"]["board_types"], ["tdx_concept"])

    def test_runner_report_metadata_includes_policy_version_and_scope_delta(self) -> None:
        bundle = load_condition_runner_policy(
            write_policy_artifact(
                {
                    "artifact_type": "n2_web_policy_default_draft",
                    "source": "8782_console",
                    "policy_id": "n2_default_policy",
                    "policy_version": "v7",
                    "policy_hash": "hash7",
                    "previous_policy_hash": "hash6",
                    "policy_diff_summary": {"index": {"changed": False}, "board": {"changed": True}, "stock": {"changed": False}},
                    "web_policy": {
                        "policy_name": "saved_default",
                        "board": {
                            "board_segments": ["industry"],
                            "board_types": ["tdx_industry"],
                            "directions": ["buy", "sell"],
                            "condition_family": ["ordinary", "full", "hint"],
                            "condition_keys": ["*"],
                        },
                    },
                }
            )
        )
        scope_report = {
            "scope_preview": {
                "stock": {"scope_row_count": 10, "object_count": 5},
                "index": {"scope_row_count": 2, "object_count": 1},
                "board": {"scope_row_count": 3, "object_count": 2},
            }
        }

        metadata = condition_runner_report_metadata(bundle, scope_report, execute_requested=False)

        self.assertEqual(metadata["policy_source"], "8782_console")
        self.assertEqual(metadata["policy_id"], "n2_default_policy")
        self.assertEqual(metadata["policy_version"], "v7")
        self.assertEqual(metadata["policy_hash"], "hash7")
        self.assertEqual(metadata["previous_policy_hash"], "hash6")
        self.assertFalse(metadata["n3_rebuild_required"])
        self.assertEqual(metadata["scope_delta_summary"]["stock"]["minute_target_scope_rows"], 10)
        self.assertFalse(metadata["active_lineage_plan"]["n3_lineage_auto_switch"])

    def test_ready_check_active_versions_excludes_missing_active_source_version(self) -> None:
        versions = active_versions_from_ready_check(
            {
                "checks": [
                    {
                        "data_type": "stock_daily",
                        "active_exists": True,
                        "active_source_version": "stock_daily_20260601_v1",
                    },
                    {
                        "data_type": "stock_daily_basic",
                        "active_exists": False,
                        "row_count": 0,
                    },
                ]
            }
        )

        self.assertEqual(versions["stock_daily"]["active_source_version"], "stock_daily_20260601_v1")
        self.assertNotIn("stock_daily_basic", versions)

    def test_runner_builds_source_not_ready_preflight_without_condition_dry_run(self) -> None:
        report = build_source_not_ready_preflight(
            ready={
                "passed": False,
                "source_trade_date": "20260601",
                "missing_data_types": [
                    "stock_daily_basic",
                    "stock_financial",
                    "index_membership",
                    "board_membership",
                ],
            },
            requested_run_id="condition_layer_20260601_source_20260601_v1",
            execute_requested=False,
            user_confirmed=False,
            overwrite=False,
        )

        self.assertEqual(report["stage"], "N2-source-readiness-preflight")
        self.assertEqual(report["result"], "PREFLIGHT_BLOCKED")
        self.assertFalse(report["source_ready"])
        self.assertEqual(report["blocked_reasons"][0], "source_not_ready")
        self.assertIn("stock_financial", report["missing_data_types"])
        self.assertFalse(report["writes_performed"])
        self.assertFalse(report["will_execute_sql"])


if __name__ == "__main__":
    unittest.main()
