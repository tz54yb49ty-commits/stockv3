import tempfile
import unittest
from pathlib import Path

from ashare_v3.condition.scope_policy import (
    condition_family,
    default_scope_policy,
    filter_scope_rows,
    load_scope_policy,
    normalize_scope_policy,
    scope_policy_warnings,
)


class ScopePolicyTest(unittest.TestCase):
    def test_default_policy_keeps_three_asset_sections(self) -> None:
        policy = default_scope_policy()

        self.assertEqual(policy["stock"]["market_value_compare"], ">=")
        self.assertIsNone(policy["stock"]["min_total_mv_wan"])
        self.assertEqual(policy["index"]["source"], "condition_pool")
        self.assertEqual(policy["board"]["source"], "condition_pool")
        self.assertEqual(policy["index"]["include_codes"], [])
        self.assertEqual(policy["board"]["board_code_prefix"], "")
        self.assertEqual(policy["board"]["board_code_prefixes"], [])
        self.assertEqual(policy["board"]["board_types"], ["tdx_industry", "tdx_concept", "tdx_region"])

    def test_condition_family_classifies_ordinary_full_and_hint(self) -> None:
        self.assertEqual(condition_family("BUY:Y,Q,M,W,D"), "ordinary")
        self.assertEqual(condition_family("SELL:D"), "ordinary")
        self.assertEqual(condition_family("BUY:FULL"), "full")
        self.assertEqual(condition_family("SELL_HINT"), "hint")

    def test_stock_policy_filters_by_direction_family_market_value_and_limit(self) -> None:
        policy = normalize_scope_policy(
            {
                "stock": {
                    "directions": ["buy"],
                    "include_condition_families": ["hint"],
                    "min_total_mv_wan": 3000000,
                    "limit": 1,
                }
            }
        )
        rows = [
            {"code": "600000", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "3000000"},
            {"code": "600001", "direction": "sell", "condition_key": "SELL_HINT", "total_mv": "5000000"},
            {"code": "600002", "direction": "buy", "condition_key": "BUY:FULL", "total_mv": "5000000"},
            {"code": "600003", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "2999999.99"},
            {"code": "600004", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "6000000"},
        ]

        result = filter_scope_rows("stock", rows, policy["stock"])

        self.assertEqual([row["code"] for row in result["selected_rows"]], ["600000"])
        self.assertEqual(result["excluded_reason_counts"]["direction"], 1)
        self.assertEqual(result["excluded_reason_counts"]["include_condition_families"], 1)
        self.assertEqual(result["excluded_reason_counts"]["min_total_mv_wan"], 1)
        self.assertEqual(result["excluded_reason_counts"]["limit"], 1)
        self.assertEqual(result["selected_samples"][0]["code"], "600000")
        self.assertEqual(result["excluded_samples"][0]["reasons"], ["direction"])

    def test_index_and_board_policy_filter_codes_independently(self) -> None:
        policy = normalize_scope_policy(
            {
                "index": {"include_codes": ["000300"], "directions": ["buy"]},
                "board": {"include_board_codes": ["881001"], "directions": ["sell"]},
            }
        )

        index_result = filter_scope_rows(
            "index",
            [
                {"code": "000300", "direction": "buy"},
                {"code": "000905", "direction": "buy"},
                {"code": "000300", "direction": "sell"},
            ],
            policy["index"],
        )
        board_result = filter_scope_rows(
            "board",
            [
                {"board_code": "881001", "board_type": "tdx_industry", "direction": "sell"},
                {"board_code": "881002", "board_type": "tdx_industry", "direction": "sell"},
                {"board_code": "991001", "board_type": "tdx_industry", "direction": "sell"},
            ],
            policy["board"],
        )

        self.assertEqual([row["code"] for row in index_result["selected_rows"]], ["000300"])
        self.assertEqual([row["board_code"] for row in board_result["selected_rows"]], ["881001"])

    def test_board_policy_filters_by_board_type_not_code_prefix(self) -> None:
        policy = normalize_scope_policy(
            {
                "board": {
                    "board_types": ["tdx_industry", "tdx_concept"],
                    "directions": ["buy"],
                }
            }
        )

        result = filter_scope_rows(
            "board",
            [
                {"board_code": "880001", "board_type": "tdx_industry", "direction": "buy"},
                {"board_code": "881001", "board_type": "tdx_concept", "direction": "buy"},
                {"board_code": "881999", "board_type": "tdx_region", "direction": "buy"},
            ],
            policy["board"],
        )

        self.assertEqual([row["board_code"] for row in result["selected_rows"]], ["880001", "881001"])
        self.assertEqual(result["excluded_reason_counts"], {"board_type": 1})

    def test_index_policy_can_filter_exchange_qualified_identity(self) -> None:
        policy = normalize_scope_policy(
            {
                "index": {
                    "include_identity_keys": ["index:SH:000001"],
                    "include_codes": [],
                }
            }
        )

        result = filter_scope_rows(
            "index",
            [
                {"identity_key": "index:SH:000001", "code": "000001", "direction": "buy"},
                {"identity_key": "index:SZ:000001", "code": "000001", "direction": "buy"},
            ],
            policy["index"],
        )

        self.assertEqual([row["identity_key"] for row in result["selected_rows"]], ["index:SH:000001"])
        self.assertEqual(result["excluded_reason_counts"], {"include_identity_keys": 1})

    def test_stock_policy_filters_min_score_and_recommendation_levels(self) -> None:
        policy = normalize_scope_policy(
            {
                "stock": {
                    "min_score": 80,
                    "recommendation_levels": ["A"],
                }
            }
        )

        result = filter_scope_rows(
            "stock",
            [
                {"code": "600000", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000", "score": "81", "recommendation_level": "A"},
                {"code": "600001", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000", "score": "79", "recommendation_level": "A"},
                {"code": "600002", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000", "score": "90", "recommendation_level": "B"},
            ],
            policy["stock"],
        )

        self.assertEqual([row["code"] for row in result["selected_rows"]], ["600000"])
        self.assertEqual(result["excluded_reason_counts"]["min_score"], 1)
        self.assertEqual(result["excluded_reason_counts"]["recommendation_level"], 1)

    def test_policy_filters_family_prev_strings_and_stock_quality_controls(self) -> None:
        policy = normalize_scope_policy(
            {
                "index": {"include_condition_families": ["hint"], "prev_up_str": "YQM--"},
                "stock": {
                    "exclude_st": True,
                    "require_official_daily_proof": True,
                    "require_financial_quality_passed": True,
                },
            }
        )

        index_result = filter_scope_rows(
            "index",
            [
                {"code": "000001", "direction": "buy", "condition_key": "BUY_HINT", "prev_up_str": "YQM--"},
                {"code": "000300", "direction": "buy", "condition_key": "BUY:FULL", "prev_up_str": "YQM--"},
                {"code": "000905", "direction": "buy", "condition_key": "BUY_HINT", "prev_up_str": "-----"},
            ],
            policy["index"],
        )
        stock_result = filter_scope_rows(
            "stock",
            [
                {
                    "code": "600000",
                    "name": "浦发银行",
                    "direction": "buy",
                    "condition_key": "BUY_HINT",
                    "total_mv": "1000000",
                    "official_daily_proof": True,
                    "financial_quality_status": "passed",
                },
                {
                    "code": "600001",
                    "name": "ST示例",
                    "direction": "buy",
                    "condition_key": "BUY_HINT",
                    "total_mv": "1000000",
                    "official_daily_proof": False,
                    "financial_quality_status": "warning",
                },
            ],
            policy["stock"],
        )

        self.assertEqual([row["code"] for row in index_result["selected_rows"]], ["000001"])
        self.assertEqual(index_result["excluded_reason_counts"]["include_condition_families"], 1)
        self.assertEqual(index_result["excluded_reason_counts"]["prev_up_str"], 1)
        self.assertEqual([row["code"] for row in stock_result["selected_rows"]], ["600000"])
        self.assertEqual(stock_result["excluded_reason_counts"]["st_or_risk_stock"], 1)
        self.assertEqual(stock_result["excluded_reason_counts"]["official_daily_missing"], 1)
        self.assertEqual(stock_result["excluded_reason_counts"]["financial_quality_not_passed"], 1)

    def test_stock_policy_can_exclude_bj_exchange_rows(self) -> None:
        policy = normalize_scope_policy({"stock": {"exclude_bj": True}})

        result = filter_scope_rows(
            "stock",
            [
                {"identity_key": "stock:SH:600000", "code": "600000", "exchange": "SH", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000"},
                {"identity_key": "stock:BJ:430001", "code": "430001", "exchange": "BJ", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000"},
                {"identity_key": "stock:SZ:300001", "code": "300001.BJ", "direction": "buy", "condition_key": "BUY_HINT", "total_mv": "1000000"},
            ],
            policy["stock"],
        )

        self.assertEqual([row["code"] for row in result["selected_rows"]], ["600000"])
        self.assertEqual(result["excluded_reason_counts"], {"bj_stock": 2})

    def test_policy_allows_optional_market_value_floor_but_rejects_negative_value(self) -> None:
        policy = normalize_scope_policy({"stock": {"min_total_mv_wan": 999999}})
        self.assertEqual(policy["stock"]["min_total_mv_wan"], 999999)
        with self.assertRaises(ValueError):
            normalize_scope_policy({"stock": {"min_total_mv_wan": -1}})

    def test_policy_warns_when_condition_keys_override_families(self) -> None:
        policy = normalize_scope_policy(
            {
                "stock": {
                    "include_condition_keys": ["BUY_HINT"],
                    "include_condition_families": ["ordinary", "hint"],
                }
            }
        )

        warnings = scope_policy_warnings(policy)

        self.assertEqual(warnings[0]["code"], "stock_condition_key_overrides_family")

    def test_load_scope_policy_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "policy.json"
            path.write_text('{"policy_name": "tmp", "stock": {"directions": ["buy"]}}', encoding="utf-8")

            policy = load_scope_policy(path)

        self.assertEqual(policy["policy_name"], "tmp")
        self.assertEqual(policy["stock"]["directions"], ["buy"])


if __name__ == "__main__":
    unittest.main()
