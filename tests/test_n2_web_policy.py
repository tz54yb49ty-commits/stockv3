import inspect
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs
from zipfile import ZipFile

import ashare_v3.condition.web_policy as web_policy_module
from ashare_v3.condition.web_policy import (
    BOARD_SEGMENT_OPTIONS,
    DEFAULT_INDEX_IDENTITIES,
    N2PolicyConsoleConfig,
    N2PolicyConsoleService,
    build_detail_export_xlsx,
    default_project_root,
    default_web_policy,
    detail_baseline_summary,
    detail_filter_model,
    detail_query_parts,
    detail_visible_columns,
    dry_run_response_from_scope_report,
    normalize_detail_filters,
    parse_policy_json,
    policy_form_model,
    policy_from_control_payload,
    policy_json_text,
    stable_policy_hash,
    web_policy_to_condition_pool_policy,
    web_policy_to_scope_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_TEMPLATE = PROJECT_ROOT / "src" / "ashare_v3" / "web" / "templates" / "n2_policy_console.html"
DETAIL_TEMPLATE = PROJECT_ROOT / "src" / "ashare_v3" / "web" / "templates" / "n2_policy_details.html"


class N2WebPolicyTest(unittest.TestCase):
    def test_default_policy_uses_full_object_universe(self) -> None:
        policy = default_web_policy()

        self.assertEqual(policy["index"]["enabled_identities"], [])
        self.assertEqual(policy["index"]["selected_identity_key"], "__all__")
        self.assertEqual(policy["board"]["board_segments"], ["industry", "concept", "region"])
        self.assertEqual(policy["board"]["board_types"], ["tdx_industry", "tdx_concept", "tdx_region"])
        self.assertIsNone(policy["stock"]["min_total_mv_yi"])
        self.assertFalse(policy["stock"]["exclude_bj"])
        self.assertEqual(policy["stock"]["allowed_monitor_types"], [])
        self.assertTrue(policy["stock"]["allow_financial_key_fields_missing"])
        self.assertEqual(policy["stock"]["condition_family"], ["ordinary", "full", "hint"])
        self.assertEqual(policy["index"]["condition_family"], ["ordinary", "full", "hint"])
        self.assertEqual(policy["board"]["condition_family"], ["ordinary", "full", "hint"])

    def test_policy_form_model_generates_three_tab_control_metadata(self) -> None:
        model = policy_form_model()

        self.assertEqual(list(model["domains"]), ["index", "board", "stock"])
        self.assertEqual(model["domains"]["index"]["label"], "指数筛选")
        self.assertEqual(model["domains"]["board"]["label"], "板块筛选")
        self.assertEqual(model["domains"]["stock"]["label"], "个股筛选")
        self.assertEqual(model["board_segment_options"], list(BOARD_SEGMENT_OPTIONS))
        self.assertEqual(model["periods"], ["y", "q", "m", "w", "d"])
        self.assertIn("BUY_HINT", model["condition_key_options"])
        self.assertIn("volume_up", model["grade_options"])

    def test_period_controls_use_checkbox_chips_not_native_multiselect(self) -> None:
        template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")

        self.assertNotIn("<select multiple", template)
        self.assertNotIn("selectedOptions", template)
        self.assertIn('class="chip-group"', template)
        self.assertIn('data-chip-action="all"', template)
        self.assertIn('data-chip-action="clear"', template)
        self.assertIn('name="{{ domain }}.period_grade.{{ period }}"', template)
        self.assertIn('name="{{ domain }}.period_transition.{{ period }}"', template)
        self.assertIn('checkedValues(`${domain}.${prefix}.${period}`)', template)
        self.assertIn('class="period-details"', template)
        self.assertIn("周期分级 / 过渡筛选", template)

    def test_console_contains_full_detail_browser_and_stock_pagination(self) -> None:
        template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")
        detail_template = DETAIL_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn('href="#policy-panel"', template)
        self.assertIn('href="#dry-run-result"', template)
        self.assertIn('href="#condition-details"', template)
        self.assertIn("[hidden] { display: none !important; }", template)
        self.assertIn("全量明细", template)
        self.assertIn("index", template)
        self.assertIn("board", template)
        self.assertIn("stock", template)
        self.assertIn("display_basis", template)
        self.assertIn("data-detail-table", template)
        self.assertIn('name="table_kind"', template)
        self.assertIn("/details-fragment", template)
        self.assertIn('name="page_size"', template)
        self.assertIn("data-detail-page", detail_template)
        self.assertIn("当前表全量展示", detail_template)
        self.assertIn("focused_columns", detail_template)
        self.assertIn("隐藏", detail_template)
        self.assertIn("semantic=trigger_target_scope", detail_template)

    def test_console_contains_detail_excel_export_button(self) -> None:
        template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")
        route_source = (
            PROJECT_ROOT / "src" / "ashare_v3" / "web" / "n2_policy_console.py"
        ).read_text(encoding="utf-8")

        self.assertIn('id="export-detail-excel"', template)
        self.assertIn("/details-export.xlsx", template)
        self.assertIn('params.delete("page")', template)
        self.assertIn('@app.get("/details-export.xlsx")', route_source)
        self.assertIn("condition_detail_export", route_source)

    def test_detail_filter_model_lists_three_domains_and_tables(self) -> None:
        model = detail_filter_model()

        self.assertEqual([item["key"] for item in model["domains"]], ["index", "board", "stock"])
        self.assertEqual([item["key"] for item in model["table_kinds"]], ["basis", "pool", "scope", "display"])
        self.assertIn("volume_up", model["period_transition_options"])
        self.assertIn("baseline_status_options", model)
        self.assertIn("required_period_not_ready_options", model)
        self.assertEqual(model["stock_page_size"], 100)

    def test_stock_detail_query_is_paginated_and_filters_via_basis_join(self) -> None:
        filters = normalize_detail_filters(
            {
                "page": "2",
                "page_size": "500",
                "code_query": "600",
                "period_transition": ["volume_up", "flat"],
                "target_status": "present",
                "baseline_status": "partial",
                "required_period_not_ready": "yes",
                "min_total_mv_yi": "100",
                "up_sell_reference_period": "D",
                "down_buy_reference_period": "missing",
                "clear_ref_period": "present",
                "min_score": "80",
            },
            domain="stock",
        )
        query = detail_query_parts("stock", "scope", filters, run_id="active")

        self.assertTrue(query["pagination_enabled"])
        self.assertIn("FROM stock_minute_target_scope t", query["data_sql"])
        self.assertIn("LEFT JOIN stock_condition_pool p", query["data_sql"])
        self.assertIn("LEFT JOIN stock_condition_basis b", query["data_sql"])
        self.assertIn("b.period_transition_d", query["data_sql"])
        self.assertIn("IN (%s, %s)", query["data_sql"])
        self.assertIn("period_trigger_baseline_json", query["data_sql"])
        self.assertIn("condition_key", query["data_sql"])
        self.assertIn("LIKE '%%,Y,%%'", query["data_sql"])
        self.assertIn("b.buy_target_price", query["data_sql"])
        self.assertIn("COALESCE(t.up_sell_reference_period, b.up_sell_reference_period)", query["data_sql"])
        self.assertIn("COALESCE(t.down_buy_reference_period, b.down_buy_reference_period)", query["data_sql"])
        self.assertIn("LIMIT %s OFFSET %s", query["data_sql"])
        self.assertIn("volume_up", query["data_params"])
        self.assertIn("flat", query["data_params"])
        self.assertEqual(query["data_params"][-2:], [300, 300])

    def test_detail_filters_accept_repeated_query_values_for_period_transition(self) -> None:
        class QueryLike(dict):
            def getlist(self, key: str) -> list[str]:
                return ["volume_up", "flat"] if key == "period_transition" else []

        filters = normalize_detail_filters(QueryLike(), domain="index")
        query = detail_query_parts("index", "basis", filters, run_id="active")

        self.assertEqual(filters["period_transitions"], ["volume_up", "flat"])
        self.assertIn("IN (%s, %s)", query["data_sql"])
        self.assertIn("volume_up", query["data_params"])
        self.assertIn("flat", query["data_params"])

    def test_stock_detail_export_query_uses_filters_without_pagination(self) -> None:
        filters = normalize_detail_filters(
            {
                "page": "3",
                "page_size": "100",
                "condition_key": "BUY",
                "min_total_mv_yi": "100",
                "min_score": "80",
            },
            domain="stock",
        )
        query = detail_query_parts("stock", "pool", filters, run_id="active", paginate=False)

        self.assertFalse(query["pagination_enabled"])
        self.assertIn("FROM stock_condition_pool t", query["data_sql"])
        self.assertIn("LEFT JOIN stock_condition_basis b", query["data_sql"])
        self.assertIn("t.condition_key ILIKE %s", query["data_sql"])
        self.assertNotIn("LIMIT %s OFFSET %s", query["data_sql"])
        self.assertEqual(query["data_params"], query["count_params"])

    def test_detail_export_xlsx_contains_metadata_headers_and_rows(self) -> None:
        content = build_detail_export_xlsx(
            metadata={
                "domain": "stock",
                "table_kind": "scope",
                "table_name": "stock_minute_target_scope",
                "run_id": "run-1",
                "total_count": 1,
                "exported_count": 1,
                "filters": {"condition_key": "BUY:*"},
                "writes_performed": False,
                "minute_kline_pulled": False,
            },
            columns=["code", "name", "condition_key", "note"],
            rows=[
                {
                    "code": "600000",
                    "name": "Sample Bank",
                    "condition_key": "BUY:*",
                    "note": {"value": "<edge>"},
                }
            ],
        )

        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            workbook = archive.read("xl/workbook.xml").decode("utf-8")

        self.assertIn("[Content_Types].xml", names)
        self.assertIn("xl/worksheets/sheet1.xml", names)
        self.assertIn("N2_detail", workbook)
        self.assertIn("N2 condition detail", sheet)
        self.assertIn("stock_minute_target_scope", sheet)
        self.assertIn("condition_key", sheet)
        self.assertIn("600000", sheet)
        self.assertIn("&lt;edge&gt;", sheet)
        self.assertIn("autoFilter", sheet)

    def test_detail_visible_columns_focuses_identity_and_condition_fields(self) -> None:
        columns = [
            "raw_json",
            "stock_minute_target_scope_id",
            "run_id",
            "stock_identity_key",
            "code",
            "name",
            "direction",
            "condition_key",
            "required_data_kind",
            "basis_period_transition_d",
            "basis_buy_target_price",
            "basis_score",
            "source_condition_pool_id",
            "created_at",
            "low_value_debug_column",
        ]

        visible = detail_visible_columns("stock", "scope", columns)

        self.assertEqual(visible[:5], [
            "stock_minute_target_scope_id",
            "stock_identity_key",
            "code",
            "name",
            "direction",
        ])
        self.assertIn("condition_key", visible)
        self.assertIn("basis_score", visible)
        self.assertNotIn("period_trigger_baseline_json", visible)
        self.assertNotIn("raw_json", visible)
        self.assertNotIn("low_value_debug_column", visible)

    def test_detail_visible_columns_surfaces_baseline_fields_when_present(self) -> None:
        visible = detail_visible_columns(
            "stock",
            "scope",
            [
                "stock_minute_target_scope_id",
                "stock_identity_key",
                "code",
                "name",
                "direction",
                "condition_key",
                "period_trigger_baseline_summary",
                "baseline_ready",
                "required_period_not_ready",
                "period_trigger_baseline_json",
            ],
        )

        self.assertIn("period_trigger_baseline_summary", visible)
        self.assertIn("baseline_ready", visible)
        self.assertIn("required_period_not_ready", visible)
        self.assertIn("period_trigger_baseline_json", visible)

    def test_detail_baseline_summary_marks_required_period_not_ready(self) -> None:
        baseline = {
            "periods": {
                period: {
                    "baseline_ready": period != "Y",
                    "previous_entity_high": 10,
                    "previous_entity_low": 9,
                    "previous_amount": 100,
                    "previous_avg_amount": 100,
                    "current_open_seed": 1,
                    "current_close_seed": 1,
                    "current_amount_seed": 1,
                    "current_trade_days_seed": 1,
                    "previous_open": 1,
                    "previous_close": 1,
                    "amount_metric": "avg_amount",
                    "current_window_start": "20260101",
                    "current_window_end": "20260102",
                    "previous_window_start": "20250101",
                    "previous_window_end": "20250102",
                }
                for period in ("Y", "Q", "M", "W", "D")
            }
        }

        summary = detail_baseline_summary(
            {"condition_key": "BUY:Y,D", "period_trigger_baseline_json": baseline},
            table_kind="scope",
        )

        self.assertEqual(summary["baseline_status"], "partial")
        self.assertEqual(summary["baseline_not_ready_periods"], "Y")
        self.assertEqual(summary["baseline_required_periods"], "Y,D")
        self.assertTrue(summary["required_period_not_ready"])

    def test_index_board_detail_queries_are_full_run_not_paginated(self) -> None:
        filters = normalize_detail_filters({"direction": "buy", "condition_key": "BUY"}, domain="index")
        index_query = detail_query_parts("index", "basis", filters, run_id="active")
        board_query = detail_query_parts("board", "pool", filters, run_id="active")

        self.assertFalse(index_query["pagination_enabled"])
        self.assertFalse(board_query["pagination_enabled"])
        self.assertNotIn("LIMIT %s OFFSET %s", index_query["data_sql"])
        self.assertNotIn("LIMIT %s OFFSET %s", board_query["data_sql"])
        self.assertIn("direction_scope::text", index_query["data_sql"])
        self.assertIn("board_condition_pool", board_query["data_sql"])

    def test_web_policy_converts_to_scope_policy_units_and_identity_keys(self) -> None:
        scope_policy = web_policy_to_scope_policy(
            {
                "policy_name": "manual",
                "index": {
                    "enabled_identities": ["index:SH:000001"],
                    "selected_identity_key": "index:SZ:399006",
                    "directions": ["buy"],
                },
                "board": {
                    "board_segments": ["industry", "concept"],
                },
                "stock": {
                    "min_total_mv_yi": 300,
                    "condition_keys": ["BUY_HINT"],
                    "exclude_bj": True,
                    "recommendation_levels": ["A", "B"],
                    "min_score": 75,
                    "limit": 10,
                },
            }
        )

        self.assertEqual(scope_policy["policy_name"], "manual")
        self.assertEqual(scope_policy["index"]["include_identity_keys"], ["index:SZ:399006"])
        self.assertEqual(scope_policy["index"]["include_codes"], ["399006"])
        self.assertEqual(scope_policy["index"]["directions"], ["buy"])
        self.assertEqual(scope_policy["board"]["board_types"], ["tdx_industry", "tdx_concept"])
        self.assertEqual(scope_policy["stock"]["min_total_mv_wan"], "3000000")
        self.assertEqual(scope_policy["stock"]["include_condition_keys"], ["BUY_HINT"])
        self.assertTrue(scope_policy["stock"]["exclude_bj"])
        self.assertEqual(scope_policy["stock"]["recommendation_levels"], ["A", "B"])
        self.assertEqual(scope_policy["stock"]["min_score"], 75)
        self.assertEqual(scope_policy["stock"]["limit"], 10)
        self.assertEqual(scope_policy["stock"]["allowed_monitor_types"], [])
        self.assertFalse(scope_policy["stock"]["require_financial_key_field"])

    def test_stock_financial_key_scope_flag_is_inverse_of_web_allow_flag(self) -> None:
        strict = web_policy_to_scope_policy(
            {"stock": {"allow_financial_key_fields_missing": False}}
        )
        permissive = web_policy_to_scope_policy(
            {"stock": {"allow_financial_key_fields_missing": True}}
        )

        self.assertTrue(strict["stock"]["require_financial_key_field"])
        self.assertFalse(permissive["stock"]["require_financial_key_field"])

    def test_stock_scope_explicit_require_financial_key_field_takes_precedence(self) -> None:
        scope_policy = web_policy_to_scope_policy(
            {
                "stock": {
                    "allow_financial_key_fields_missing": True,
                    "require_financial_key_field": True,
                }
            }
        )

        self.assertTrue(scope_policy["stock"]["require_financial_key_field"])

    def test_index_all_selection_removes_fixed_index_whitelist(self) -> None:
        scope_policy = web_policy_to_scope_policy(
            {
                "index": {
                    "selected_identity_key": "__all__",
                    "enabled_identities": ["index:SH:000001"],
                    "directions": ["buy"],
                }
            }
        )

        self.assertEqual(scope_policy["index"]["include_identity_keys"], [])
        self.assertEqual(scope_policy["index"]["include_codes"], [])
        self.assertEqual(scope_policy["index"]["directions"], ["buy"])

    def test_web_policy_builds_condition_pool_policy_for_expanded_indexes_and_board_types(self) -> None:
        pool_policy = web_policy_to_condition_pool_policy(
            {
                "index": {
                    "selected_identity_key": "__all__",
                    "enabled_identities": ["index:SH:000001"],
                },
                "board": {
                    "board_segments": ["industry", "concept", "region"],
                },
            }
        )

        self.assertTrue(pool_policy["index"]["include_all_identities"])
        self.assertEqual(pool_policy["index"]["include_identity_keys"], [])
        self.assertEqual(pool_policy["index"]["include_codes"], [])
        self.assertEqual(
            pool_policy["board"]["board_types"],
            ["tdx_industry", "tdx_concept", "tdx_region"],
        )

    def test_star_condition_keys_do_not_override_condition_family(self) -> None:
        scope_policy = web_policy_to_scope_policy({"stock": {"condition_keys": ["*"]}})

        self.assertEqual(scope_policy["stock"]["include_condition_keys"], [])
        self.assertEqual(scope_policy["stock"]["include_condition_families"], ["ordinary", "full", "hint"])

    def test_period_dicts_expand_to_scope_policy_fields(self) -> None:
        scope_policy = web_policy_to_scope_policy(
            {
                "index": {
                    "condition_family": ["hint"],
                    "prev_up_str": "YQM--",
                },
                "stock": {
                    "period_grade": {"d": ["flat"]},
                    "period_transition": {"w": ["volume_up"]},
                    "prev_dn_str": "---w-",
                }
            }
        )

        self.assertEqual(scope_policy["index"]["include_condition_families"], ["hint"])
        self.assertEqual(scope_policy["index"]["prev_up_str"], "YQM--")
        self.assertEqual(scope_policy["stock"]["period_grade_d"], ["flat"])
        self.assertEqual(scope_policy["stock"]["period_transition_w"], ["volume_up"])
        self.assertEqual(scope_policy["stock"]["prev_dn_str"], "---w-")

    def test_transition_control_payload_accepts_two_values(self) -> None:
        policy = policy_from_control_payload(
            {
                "index.period_transition.d": ["volume_up", "flat"],
                "index.condition_keys": ["*"],
            }
        )
        scope_policy = web_policy_to_scope_policy(policy)

        self.assertEqual(policy["index"]["period_transition"]["d"], ["volume_up", "flat"])
        self.assertEqual(scope_policy["index"]["period_transition_d"], ["volume_up", "flat"])

    def test_grade_control_payload_accepts_two_values(self) -> None:
        policy = policy_from_control_payload(
            {
                "board.period_grade.w": ["volume_down", "flat"],
                "board.condition_keys": ["*"],
            }
        )
        parsed = parse_policy_json(policy_json_text(policy))
        scope_policy = web_policy_to_scope_policy(parsed)

        self.assertEqual(parsed["board"]["period_grade"]["w"], ["volume_down", "flat"])
        self.assertEqual(scope_policy["board"]["period_grade_w"], ["volume_down", "flat"])

    def test_dry_run_form_payload_preserves_repeated_period_fields(self) -> None:
        template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")
        form = parse_qs(
            "policy_name=manual"
            "&stock.period_grade.d=volume_up"
            "&stock.period_grade.d=flat"
            "&stock.period_transition.d=volume_down"
            "&stock.period_transition.d=flat",
            keep_blank_values=True,
        )
        policy = policy_from_control_payload(form)

        self.assertIn("new URLSearchParams(new FormData(policyForm))", template)
        self.assertEqual(policy["stock"]["period_grade"]["d"], ["volume_up", "flat"])
        self.assertEqual(policy["stock"]["period_transition"]["d"], ["volume_down", "flat"])

    def test_reference_requirement_controls_round_trip_to_scope_policy(self) -> None:
        policy = policy_from_control_payload(
            {
                "stock.condition_keys": ["*"],
                "stock.require_up_sell_reference_period": ["on"],
                "stock.require_down_buy_reference_period": ["on"],
                "stock.require_clear_sell_ref_period": ["on"],
            }
        )
        scope_policy = web_policy_to_scope_policy(policy)

        self.assertTrue(policy["stock"]["require_up_sell_reference_period"])
        self.assertTrue(policy["stock"]["require_down_buy_reference_period"])
        self.assertTrue(scope_policy["stock"]["require_up_sell_reference_period"])
        self.assertTrue(scope_policy["stock"]["require_down_buy_reference_period"])

    def test_control_payload_round_trips_to_policy_json(self) -> None:
        policy = policy_from_control_payload(
            {
                "policy_name": ["manual_ui"],
                "index.directions": ["buy"],
                "index.condition_family": ["hint"],
                "index.condition_keys": ["BUY_HINT"],
                "index.enabled_identities": ["index:SH:000001"],
                "index.selected_identity_key": ["__all__"],
                "index.period_grade.d": ["flat", "volume_up"],
                "index.period_transition.d": ["volume_up", "flat"],
                "index.prev_up_str": ["YQM--"],
                "board.directions": ["sell"],
                "board.condition_family": ["ordinary", "full"],
                "board.condition_keys": ["SELL:*"],
                "board.board_segments": ["industry", "region"],
                "board.include_codes": ["881001\n881002"],
                "stock.directions": ["buy"],
                "stock.condition_family": ["ordinary"],
                "stock.condition_keys": ["BUY:*"],
                "stock.min_total_mv_yi": ["300"],
                "stock.exclude_st": ["on"],
                "stock.exclude_bj": ["on"],
                "stock.require_official_daily_proof": ["on"],
                "stock.require_financial_quality_passed": ["on"],
                "stock.min_score": ["80"],
                "stock.recommendation_levels": ["A,B"],
                "stock.include_codes": ["600000,600001"],
            }
        )
        parsed = parse_policy_json(policy_json_text(policy))

        self.assertEqual(parsed["policy_name"], "manual_ui")
        self.assertEqual(parsed["index"]["selected_identity_key"], "__all__")
        self.assertEqual(parsed["index"]["enabled_identities"], [])
        self.assertEqual(parsed["index"]["condition_family"], ["hint"])
        self.assertEqual(parsed["index"]["period_grade"]["d"], ["flat", "volume_up"])
        self.assertEqual(parsed["index"]["period_transition"]["d"], ["volume_up", "flat"])
        self.assertEqual(parsed["board"]["board_segments"], ["industry", "region"])
        self.assertEqual(parsed["board"]["board_types"], ["tdx_industry", "tdx_region"])
        self.assertEqual(parsed["board"]["include_codes"], ["881001", "881002"])
        self.assertEqual(parsed["stock"]["min_total_mv_yi"], 300)
        self.assertTrue(parsed["stock"]["exclude_st"])
        self.assertTrue(parsed["stock"]["exclude_bj"])
        self.assertTrue(parsed["stock"]["require_financial_quality_passed"])
        self.assertEqual(parsed["stock"]["recommendation_levels"], ["A", "B"])

    def test_policy_console_template_exposes_requested_strategy_controls(self) -> None:
        template = CONSOLE_TEMPLATE.read_text(encoding="utf-8")
        route_source = (
            PROJECT_ROOT / "src" / "ashare_v3" / "web" / "n2_policy_console.py"
        ).read_text(encoding="utf-8")

        self.assertIn('name="index.selected_identity_key"', template)
        self.assertIn("全部指数对象单选", template)
        self.assertIn('value="__all__"', template)
        self.assertIn("全部指数对象", template)
        self.assertIn('name="board.board_segments"', template)
        self.assertIn("行业", template)
        self.assertIn("概念", template)
        self.assertIn("地区", template)
        self.assertIn('name="stock.exclude_bj"', template)
        self.assertIn("排除 BJ", template)
        self.assertIn('id="save-default-policy-draft"', template)
        self.assertIn('id="generate-execute-gate"', template)
        self.assertIn("/api/n2/policy/save-default-draft", route_source)
        self.assertIn("/api/n2/policy/generate-execute-gate", route_source)

    def test_save_default_policy_draft_writes_runner_compatible_artifact_without_database(self) -> None:
        policy = default_web_policy()
        policy["board"]["board_segments"] = ["industry", "concept", "region"]
        policy["board"]["board_types"] = ["tdx_industry", "tdx_concept", "tdx_region"]
        policy["index"]["selected_identity_key"] = "__all__"
        policy["index"]["enabled_identities"] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            service = N2PolicyConsoleService(
                N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False)
            )

            result = service.save_default_policy_draft(policy_json_text(policy))
            artifact = json.loads(Path(result["policy_path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["database_written"])
        self.assertEqual(artifact["artifact_type"], "n2_web_policy_default_draft")
        self.assertEqual(artifact["web_policy"]["board"]["board_types"], ["tdx_industry", "tdx_concept", "tdx_region"])
        self.assertEqual(artifact["scope_policy"]["board"]["board_types"], ["tdx_industry", "tdx_concept", "tdx_region"])
        self.assertEqual(
            artifact["condition_pool_policy"]["board"]["board_types"],
            ["tdx_industry", "tdx_concept", "tdx_region"],
        )
        self.assertTrue(artifact["condition_pool_policy"]["index"]["include_all_identities"])
        self.assertEqual(
            artifact["scope_policy"]["stock"]["allowed_monitor_types"],
            artifact["web_policy"]["stock"]["allowed_monitor_types"],
        )
        self.assertFalse(artifact["scope_policy"]["stock"]["require_financial_key_field"])
        pool_stock = artifact["condition_pool_policy"]["stock"]
        self.assertIsNone(pool_stock["min_total_mv_wan"])
        self.assertFalse(pool_stock["exclude_st_or_risk_name"])
        self.assertEqual(pool_stock["allowed_stock_statuses"], [])
        self.assertFalse(pool_stock["require_official_daily_proof"])
        self.assertFalse(pool_stock["require_financial_snapshot"])
        self.assertFalse(pool_stock["require_financial_key_field"])
        self.assertEqual(pool_stock["blocked_financial_quality_statuses"], [])

    def test_save_default_policy_draft_adds_version_metadata_and_policy_diff(self) -> None:
        policy = default_web_policy()
        with tempfile.TemporaryDirectory() as tmpdir:
            service = N2PolicyConsoleService(
                N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False)
            )

            first = service.save_default_policy_draft(policy_json_text(policy))
            first_artifact = json.loads(Path(first["policy_path"]).read_text(encoding="utf-8"))
            policy["stock"]["min_total_mv_yi"] = 300
            second = service.save_default_policy_draft(policy_json_text(policy))
            second_artifact = json.loads(Path(second["policy_path"]).read_text(encoding="utf-8"))

        self.assertEqual(first_artifact["policy_id"], "n2_default_policy")
        self.assertEqual(first_artifact["policy_version"], "v1")
        self.assertEqual(first_artifact["source"], "8782_console")
        self.assertEqual(first_artifact["created_by"], "8782_console")
        self.assertIsNone(first_artifact["previous_policy_hash"])
        self.assertEqual(set(first_artifact["policy_diff_summary"]), {"index", "board", "stock"})
        self.assertEqual(second_artifact["policy_version"], "v2")
        self.assertEqual(second_artifact["previous_policy_hash"], first_artifact["policy_hash"])
        self.assertIn("min_total_mv_yi", second_artifact["policy_diff_summary"]["stock"]["changed_keys"])
        self.assertIn("index", second_artifact["policy_diff_summary"])
        self.assertIn("board", second_artifact["policy_diff_summary"])

    def test_console_default_policy_prefers_saved_default_draft(self) -> None:
        policy = default_web_policy()
        policy["stock"]["directions"] = ["buy"]
        policy["stock"]["min_total_mv_yi"] = 100
        policy["board"]["board_types"] = ["tdx_industry"]

        with tempfile.TemporaryDirectory() as tmpdir:
            service = N2PolicyConsoleService(
                N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False)
            )
            saved = service.save_default_policy_draft(policy_json_text(policy))
            context = service.console_context()

        self.assertTrue(saved["ok"])
        self.assertEqual(context["default_policy"]["stock"]["directions"], ["buy"])
        self.assertIn('"directions": [\n      "buy"\n    ]', context["default_policy_json"])
        self.assertEqual(context["form_model"]["domains"]["stock"]["policy"]["directions"], ["buy"])

    def test_generate_execute_gate_draft_requires_database_but_never_writes_when_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = N2PolicyConsoleService(
                N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False)
            )

            result = service.generate_execute_gate_draft(policy_json_text(default_web_policy()), source_trade_date="20260528")

        self.assertFalse(result["ok"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["database_written"])
        self.assertEqual(result["artifact_type"], "n2_web_policy_execute_gate_draft")
        self.assertIn("--policy configs/n2_policy/default_policy_draft.json", result["execute_command"])

    def test_generate_execute_gate_draft_writes_formal_gate_package(self) -> None:
        class FakeGateService(N2PolicyConsoleService):
            def active_run(self) -> dict[str, object]:
                return {
                    "run_id": "condition_layer_20260528_source_20260528_v3",
                    "status": "passed_active",
                    "source_trade_date": "20260528",
                    "for_trade_date": "20260529",
                    "prev_trade_date": "20260528",
                }

            def dry_run_policy(self, policy_payload: str, source_trade_date: str | None = None) -> dict[str, object]:
                return {
                    "ok": True,
                    "source_trade_date": "20260528",
                    "for_trade_date": "20260529",
                    "prev_trade_date": "20260528",
                    "p0_count": 0,
                    "p1_count": 1,
                    "p2_count": 0,
                    "domains": {
                        "stock": {"pool": {"row_count": 10}, "scope": {"row_count": 8, "object_count": 5}},
                        "index": {"pool": {"row_count": 2}, "scope": {"row_count": 2, "object_count": 1}},
                        "board": {"pool": {"row_count": 3}, "scope": {"row_count": 3, "object_count": 2}},
                    },
                    "writes_performed": False,
                    "minute_kline_pulled": False,
                }

            def _execute_gate_expected_rows(self, *, policy, scope_policy, condition_pool_policy, source_trade_date):
                return {
                    "condition_basis": {"stock": 20, "index": 4, "board": 6},
                    "condition_pool": {"stock": 10, "index": 2, "board": 3},
                    "minute_target_scope": {"stock": 8, "index": 2, "board": 3},
                    "condition_display_basis": {"stock": 5, "index": 1, "board": 2},
                    "monitor_target": {"stock": 20, "index": 4, "board": 6},
                    "quality_item": 12,
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            service = FakeGateService(
                N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False)
            )

            result = service.generate_execute_gate_draft(policy_json_text(default_web_policy()), source_trade_date="20260528")
            gate_json = json.loads(Path(result["gate_json_path"]).read_text(encoding="utf-8"))
            rollback_sql = Path(result["rollback_sql_path"]).read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertEqual(result["gate_result"], "PASS")
        self.assertEqual(result["proposed_run_id"], "condition_layer_20260528_source_20260528_v4")
        self.assertEqual(result["active_lineage_plan"]["current_active_run_id"], "condition_layer_20260528_source_20260528_v3")
        self.assertEqual(result["active_lineage_plan"]["overwrite_semantics"], "lineage_supersede_only")
        self.assertFalse(result["active_lineage_plan"]["n3_lineage_auto_switch"])
        self.assertEqual(result["overwrite_semantics"], "lineage_supersede_only")
        self.assertFalse(result["n3_lineage_auto_switch"])
        self.assertEqual(result["expected_row_counts"]["condition_display_basis"]["stock"], 5)
        self.assertEqual(result["expected_rows"]["condition_display_basis"]["stock"], 5)
        self.assertEqual(result["expected_row_counts"]["quality_item"], 12)
        self.assertEqual(result["policy_path"], "configs/n2_policy/default_policy_draft.json")
        self.assertEqual(result["previous_policy_hash"], result["policy_diff_summary"].get("previous_policy_hash"))
        self.assertEqual(result["scope_delta_summary"]["stock"]["minute_target_scope_rows"], 8)
        self.assertFalse(result["execute_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["database_written"])
        self.assertTrue(result["n3_rebuild_required"])
        self.assertFalse(result["n3_lineage_auto_switch"])
        self.assertIn("--run-id condition_layer_20260528_source_20260528_v4", result["execute_command_candidate"])
        self.assertIn("common_event_outbox", result["forbidden_scopes"])
        self.assertIn("active passed run count = 1", result["post_review_checklist"])
        self.assertEqual(gate_json["policy_hash"], result["policy_hash"])
        self.assertEqual(gate_json["policy_path"], "configs/n2_policy/default_policy_draft.json")
        self.assertEqual(gate_json["expected_rows"], result["expected_rows"])
        self.assertFalse(gate_json["execute_authorized"])
        self.assertFalse(gate_json["database_written"])
        self.assertEqual(gate_json["rollback_sql_path"], result["rollback_sql_path"])
        self.assertIn("condition_layer_20260528_source_20260528_v4", rollback_sql)
        self.assertIn("condition_layer_20260528_source_20260528_v3", rollback_sql)
        self.assertIn("downstream N3/N4/N5/N6 refs", rollback_sql)
        self.assertIn("common_market_data_run", rollback_sql)
        self.assertIn("common_trigger_run", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)
        self.assertIn("UPDATE common_condition_run", rollback_sql)
        self.assertIn("status = 'passed_active'", rollback_sql)
        self.assertNotIn("DELETE FROM common_condition_run WHERE run_id = 'condition_layer_20260528_source_20260528_v3'", rollback_sql)
        self.assertNotIn("condition_layer_20260528_source_20260528_v2", rollback_sql)
        self.assertNotIn("condition_layer_20260528_source_20260528_v1", rollback_sql)

    def test_regenerate_execute_gate_from_default_draft_uses_current_source_lineage_without_bumping_policy(self) -> None:
        class FakeRegenerationService(N2PolicyConsoleService):
            def active_run(self) -> dict[str, object]:
                return {
                    "run_id": "condition_layer_20260604_source_20260604_v1",
                    "status": "passed_active",
                    "source_trade_date": "20260604",
                }

            def active_run_for_source_trade_date(self, source_trade_date: str | None) -> dict[str, object]:
                assert source_trade_date == "20260528"
                return {
                    "run_id": "condition_layer_20260528_source_20260528_v5",
                    "status": "passed_active",
                    "source_trade_date": "20260528",
                    "for_trade_date": "20260529",
                    "prev_trade_date": "20260528",
                }

            def dry_run_policy(self, policy_payload: str, source_trade_date: str | None = None) -> dict[str, object]:
                return {
                    "ok": True,
                    "source_trade_date": "20260528",
                    "for_trade_date": "20260529",
                    "prev_trade_date": "20260528",
                    "p0_count": 0,
                    "p1_count": 1,
                    "p2_count": 0,
                    "domains": {
                        "stock": {"pool": {"row_count": 4271}, "scope": {"row_count": 4251, "object_count": 2011}},
                        "index": {"pool": {"row_count": 169}, "scope": {"row_count": 169, "object_count": 83}},
                        "board": {"pool": {"row_count": 875}, "scope": {"row_count": 875, "object_count": 428}},
                    },
                    "writes_performed": False,
                    "minute_kline_pulled": False,
                }

            def _execute_gate_expected_rows(self, *, policy, scope_policy, condition_pool_policy, source_trade_date):
                return {
                    "condition_basis": {"stock": 5506, "index": 83, "board": 428},
                    "condition_pool": {"stock": 4271, "index": 169, "board": 875},
                    "minute_target_scope": {"stock": 4251, "index": 169, "board": 875},
                    "condition_display_basis": {"stock": 2011, "index": 83, "board": 428},
                    "monitor_target": {"stock": 5506, "index": 83, "board": 428},
                    "quality_item": 103,
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            service = FakeRegenerationService(N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False))
            saved = service.save_default_policy_draft(policy_json_text(default_web_policy()))
            result = service.regenerate_execute_gate_from_default_draft(source_trade_date="20260528")
            gate_json = json.loads(Path(result["gate_json_path"]).read_text(encoding="utf-8"))
            rollback_sql = Path(result["rollback_sql_path"]).read_text(encoding="utf-8")
            saved_after = json.loads(Path(saved["policy_path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["gate_result"], "PASS")
        self.assertEqual(result["proposed_run_id"], "condition_layer_20260528_source_20260528_v6")
        self.assertEqual(result["active_lineage_plan"]["current_active_run_id"], "condition_layer_20260528_source_20260528_v5")
        self.assertEqual(result["policy_version"], saved["policy_version"])
        self.assertEqual(result["policy_hash"], saved["policy_hash"])
        self.assertEqual(result["policy_path"], "configs/n2_policy/default_policy_draft.json")
        self.assertEqual(result["expected_rows"], result["expected_row_counts"])
        self.assertEqual(gate_json["expected_rows"], result["expected_rows"])
        self.assertFalse(result["execute_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["database_written"])
        self.assertTrue(result["n3_rebuild_required"])
        self.assertFalse(result["n3_lineage_auto_switch"])
        self.assertEqual(saved_after["policy_version"], saved["policy_version"])
        self.assertIn("condition_layer_20260528_source_20260528_v6", rollback_sql)
        self.assertIn("condition_layer_20260528_source_20260528_v5", rollback_sql)
        self.assertNotIn("condition_layer_20260528_source_20260528_v4", rollback_sql)
        guard_block = rollback_sql.split("DELETE FROM", 1)[0]
        self.assertIn("common_event_outbox", guard_block)
        self.assertIn("common_event_inbox", guard_block)
        self.assertIn("common_event_consumer_checkpoint", guard_block)
        self.assertIn("event_refs > 0", guard_block)

    def test_overwrite_confirmation_requires_passed_matching_gate_and_manual_token(self) -> None:
        class FakeGateService(N2PolicyConsoleService):
            def active_run(self) -> dict[str, object]:
                return {
                    "run_id": "condition_layer_20260528_source_20260528_v3",
                    "status": "passed_active",
                    "source_trade_date": "20260528",
                    "for_trade_date": "20260529",
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            service = FakeGateService(N2PolicyConsoleConfig(project_root=Path(tmpdir), use_database=False))
            saved = service.save_default_policy_draft(policy_json_text(default_web_policy()))
            gate_path = Path(tmpdir) / "docs" / "N2_web_policy_execute_gate_draft.json"
            gate_path.parent.mkdir(parents=True)
            gate_path.write_text(
                json.dumps(
                    {
                        "gate_result": "PASS",
                        "source_trade_date": "20260528",
                        "proposed_run_id": "condition_layer_20260528_source_20260528_v4",
                        "policy_version": saved["policy_version"],
                        "policy_hash": saved["policy_hash"],
                        "policy_diff_summary": saved["policy_diff_summary"],
                        "expected_rows": {"condition_pool": {"stock": 1, "index": 2, "board": 3}},
                        "rollback_sql_path": "sql/N2_web_policy_rollback.sql",
                        "execute_command_candidate": "PYTHONPATH=src python3 scripts/run_condition_layer_execute.py --execute",
                        "active_lineage_plan": {
                            "current_active_run_id": "condition_layer_20260528_source_20260528_v3",
                            "proposed_next_run_id": "condition_layer_20260528_source_20260528_v4",
                            "n3_lineage_auto_switch": False,
                        },
                        "n3_rebuild_required": True,
                        "n3_lineage_auto_switch": False,
                        "writes_performed": False,
                        "database_written": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            model = service.overwrite_confirmation_model(source_trade_date="20260528")
            confirmed_by_run = service.confirm_overwrite_gate(
                source_trade_date="20260528",
                confirmation_text="condition_layer_20260528_source_20260528_v4",
            )
            confirmed_by_hash = service.confirm_overwrite_gate(
                source_trade_date="20260528",
                confirmation_text=saved["policy_hash"],
            )
            blocked_wrong_token = service.confirm_overwrite_gate(
                source_trade_date="20260528",
                confirmation_text="wrong",
            )
            blocked_wrong_date = service.overwrite_confirmation_model(source_trade_date="20260527")

        self.assertTrue(model["confirmation_enabled"])
        self.assertEqual(model["gate_result"], "PASS")
        self.assertEqual(model["current_active_run_id"], "condition_layer_20260528_source_20260528_v3")
        self.assertEqual(model["proposed_run_id"], "condition_layer_20260528_source_20260528_v4")
        self.assertIn("condition_pool", model["expected_rows"])
        self.assertTrue(model["n3_rebuild_required"])
        self.assertFalse(model["n3_lineage_auto_switch"])
        self.assertFalse(model["n4_n5_n6_auto_replay"])
        self.assertEqual(confirmed_by_run["manual_confirm_status"], "WAIT_MANUAL_CONFIRM")
        self.assertEqual(confirmed_by_hash["manual_confirm_status"], "WAIT_MANUAL_CONFIRM")
        self.assertFalse(confirmed_by_run["writes_performed"])
        self.assertFalse(confirmed_by_run["database_written"])
        self.assertFalse(confirmed_by_run["execute_authorized"])
        self.assertFalse(blocked_wrong_token["ok"])
        self.assertIn("confirmation_text", blocked_wrong_token["blocked_reasons"])
        self.assertFalse(blocked_wrong_date["confirmation_enabled"])
        self.assertIn("source_trade_date_mismatch", blocked_wrong_date["blocked_reasons"])

    def test_overwrite_confirmation_routes_are_manual_only(self) -> None:
        route_source = (PROJECT_ROOT / "src" / "ashare_v3" / "web" / "n2_policy_console.py").read_text(encoding="utf-8")
        template = (PROJECT_ROOT / "src" / "ashare_v3" / "web" / "templates" / "n2_policy_overwrite_confirm.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('@app.get("/execute-overwrite"', route_source)
        self.assertIn('@app.post("/api/n2/policy/confirm-overwrite"', route_source)
        self.assertIn("WAIT_MANUAL_CONFIRM", route_source)
        self.assertIn("proposed_run_id", template)
        self.assertIn("policy_hash", template)
        self.assertIn("N3 不自动 rebuild", template)
        self.assertIn("N4/N5/N6 不自动重放", template)
        self.assertNotIn("run_condition_layer_execute", route_source.split("confirm_overwrite")[1])

    def test_daily_runner_policy_audit_uses_default_draft_and_blocks_registry_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "run_condition_layer_execute.py").write_text(
                "DEFAULT_POLICY_DRAFT_RELATIVE_PATH = 'configs/n2_policy/default_policy_draft.json'\n"
                "def resolve_condition_runner_policy(policy_path):\n"
                "    return policy_path or DEFAULT_POLICY_DRAFT_RELATIVE_PATH\n",
                encoding="utf-8",
            )
            (root / "configs" / "n2_policy").mkdir(parents=True)
            (root / "configs" / "n2_policy" / "default_policy_draft.json").write_text(
                json.dumps({"policy_hash": "abc", "policy_version": "v1"}, ensure_ascii=False),
                encoding="utf-8",
            )

            clean = web_policy_module.daily_runner_policy_audit(root)
            registry = root / "docs" / "runtime_registry" / "n2_daily_command.md"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                "PYTHONPATH=src python3 scripts/run_condition_layer_execute.py --source-trade-date 20260602 --policy configs/other.json",
                encoding="utf-8",
            )
            blocked = web_policy_module.daily_runner_policy_audit(root)

        self.assertEqual(clean["audit_result"], "PASS")
        self.assertTrue(clean["runner_uses_default_policy_draft_when_policy_missing"])
        self.assertEqual(clean["default_policy_path"], "configs/n2_policy/default_policy_draft.json")
        self.assertEqual(clean["default_policy_hash"], "abc")
        self.assertEqual(blocked["audit_result"], "BLOCKED")
        self.assertTrue(blocked["scheduler_registry_policy_override_detected"])
        self.assertIn("configs/other.json", blocked["blocked_reasons"][0])

    def test_policy_hash_is_stable_for_reordered_dicts(self) -> None:
        left = {"policy_name": "x", "stock": {"limit": 1, "directions": ["buy"]}}
        right = {"stock": {"directions": ["buy"], "limit": 1}, "policy_name": "x"}

        self.assertEqual(stable_policy_hash(left), stable_policy_hash(right))

    def test_parse_policy_rejects_non_object(self) -> None:
        with self.assertRaises(ValueError):
            parse_policy_json("[]")

    def test_fixed_old_report_replay_is_disabled(self) -> None:
        service = N2PolicyConsoleService(
            N2PolicyConsoleConfig(project_root=default_project_root(), use_database=False)
        )

        active = service.active_run()
        summary = service.pool_scope_summaries(None)
        result = service.dry_run_policy(policy_json_text(default_web_policy()), source_trade_date="20260522")
        source = inspect.getsource(web_policy_module)

        self.assertEqual(active["source"], "postgres_unavailable")
        self.assertEqual(summary["source"], "no_active_run")
        self.assertFalse(result["ok"])
        self.assertIn("fixed local report", result["error"])
        self.assertNotIn("N2_E9", source)
        self.assertNotIn("local_report_replay", source)

    def test_detail_browser_has_no_fixed_report_fallback_when_database_disabled(self) -> None:
        service = N2PolicyConsoleService(
            N2PolicyConsoleConfig(project_root=default_project_root(), use_database=False)
        )

        detail = service.condition_detail("index", "basis", {})

        self.assertFalse(detail["ok"])
        self.assertEqual(detail["rows"], [])
        self.assertIn("fixed local report fallback is disabled", detail["source"])

    def test_dry_run_response_exposes_reason_counts_and_pool_scope_counts(self) -> None:
        response = dry_run_response_from_scope_report(
            report={
                "run_id": "dry",
                "source_trade_date": "20260522",
                "for_trade_date": "20260525",
                "prev_trade_date": "20260522",
                "scope_policy": {
                    "diagnostics": {
                        "stock": {
                            "candidate_count": 3,
                            "selected_count": 1,
                            "excluded_count": 2,
                            "excluded_reason_counts": {
                                "direction": 1,
                                "min_score": 1,
                                "missing_period_trigger_baseline": 1,
                            },
                            "selected_reason_counts": {"policy_matched": 1},
                            "selected_samples": [{"code": "600000"}],
                            "excluded_samples": [{"reasons": ["direction"]}],
                            "distribution": {"direction_counts": {"buy": 1}},
                        }
                    }
                },
                "scope_preview": {
                    "stock": {
                        "condition_pool_row_count": 3,
                        "scope_row_count": 1,
                        "object_count": 1,
                    }
                },
                "quality": {
                    "p0_count": 0,
                    "p1_count": 1,
                    "p2_count": 2,
                    "items": [
                        {
                            "gate_code": "period_trigger_baseline_required_periods_scope",
                            "status": "failed",
                        }
                    ],
                },
            },
            policy={"policy_name": "manual"},
            policy_hash="hash",
            source="postgres_read_only",
        )

        stock = response["domains"]["stock"]
        self.assertEqual(response["p0_count"], 0)
        self.assertEqual(response["p1_count"], 1)
        self.assertEqual(response["p2_count"], 2)
        self.assertEqual(
            stock["reason_counts"],
            {"direction": 1, "min_score": 1, "missing_period_trigger_baseline": 1},
        )
        self.assertEqual(stock["pool"]["row_count"], 3)
        self.assertEqual(stock["scope"]["row_count"], 1)
        self.assertEqual(stock["baseline_gate"]["required_period_not_ready_count"], 1)
        self.assertEqual(response["baseline_gate"]["status"], "needs_review")
        self.assertEqual(response["baseline_gate"]["required_period_not_ready_count"], 1)
        self.assertEqual(response["baseline_gate"]["failed_quality_count"], 1)
        self.assertEqual(stock["selected_samples"], [{"code": "600000"}])


if __name__ == "__main__":
    unittest.main()
