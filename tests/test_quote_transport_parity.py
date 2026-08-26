from __future__ import annotations

import copy
import json
import unittest

from ashare_v3.mootdx_client import EndpointSelection
from ashare_v3.quote_transport import MootdxQuoteTransport, TdxpyQuoteTransport
from ashare_v3.quote_transport_parity import (
    PARITY_SCHEMA_VERSION,
    QuoteTransportParityError,
    SentinelRequest,
    compare_sentinel_parity,
    deterministic_sentinel_requests,
    evaluate_quote_transport_rollout_eligibility,
)


def endpoint_selection(transport):
    return EndpointSelection(
        endpoint_pool_version="test-pool-v1",
        endpoint_id="primary",
        host="115.238.56.198",
        port=7709,
        transport=transport,
        health_state="healthy",
        health_checked_at="2026-07-19T00:00:00+00:00",
        probe_summary={"passed": True},
        attempt_id="attempt-1",
        selection_reason="test",
        failover_mode="observe",
        selectable=True,
    )


class FakeTdxpyParityApi:
    def __init__(self, rows):
        self.rows = rows

    def connect(self, host, port, *, time_out):
        return self

    def get_index_bars(self, frequency, market, code, start, count):
        return list(self.rows)


class FakeTransport:
    def __init__(self, name, rows_by_call=None, error=None):
        self.transport_name = name
        self.rows_by_call = rows_by_call or {}
        self.error = error
        self.calls = []

    def bars(self, **kwargs):
        return self._call("bars", kwargs)

    def index(self, **kwargs):
        return self._call("index", kwargs)

    def index_bars(self, **kwargs):
        return self._call("index_bars", kwargs)

    def _call(self, method, kwargs):
        self.calls.append((method, kwargs))
        if self.error is not None:
            raise self.error
        return self.rows_by_call.get(
            (method, kwargs["symbol"]),
            [
                {
                    "code": kwargs["symbol"],
                    "datetime": "2026-07-17",
                    "open": "10.0",
                    "high": "11",
                    "low": "9",
                    "close": "10.5",
                }
            ],
        )


def daily_report(
    trade_date,
    *,
    passed=True,
    sentinel_count=3,
    schema_version=PARITY_SCHEMA_VERSION,
    baseline_transport="mootdx",
    candidate_transport="tdxpy",
):
    normalized_trade_date = "".join(
        character for character in str(trade_date) if character.isdigit()
    )
    if sentinel_count <= 0:
        return {
            "schema_version": schema_version,
            "trade_date": trade_date,
            "scope_policy": "deterministic_first_middle_last_sentinels_only",
            "baseline_transport": baseline_transport,
            "candidate_transport": candidate_transport,
            "sentinel_count": sentinel_count,
            "asset_kind_counts": {},
            "results": [],
            "passed": passed,
        }

    requests = [
        SentinelRequest(
            asset_kind="stock",
            identity_key=f"stock:SH:60000{index}",
            symbol=f"60000{index}",
            method="bars",
        )
        for index in range(sentinel_count)
    ]
    baseline_rows = {}
    candidate_rows = {}
    for request in requests:
        baseline_row = {
            "code": request.symbol,
            "trade_date": normalized_trade_date,
            "open": "1",
            "high": "2",
            "low": "1",
            "close": "2",
        }
        candidate_row = dict(baseline_row)
        if not passed:
            candidate_row["close"] = "3"
        baseline_rows[("bars", request.symbol)] = [baseline_row]
        candidate_rows[("bars", request.symbol)] = [candidate_row]
    report = compare_sentinel_parity(
        trade_date=normalized_trade_date,
        requests=requests,
        baseline=FakeTransport("mootdx", baseline_rows),
        candidate=FakeTransport("tdxpy", candidate_rows),
    )
    report["schema_version"] = schema_version
    report["baseline_transport"] = baseline_transport
    report["candidate_transport"] = candidate_transport
    return report


class QuoteTransportParityTest(unittest.TestCase):
    def test_deterministic_scope_is_first_middle_last_only(self) -> None:
        requests = deterministic_sentinel_requests(
            {
                "stock": [
                    {"identity_key": f"stock:SH:60000{index}", "code": f"60000{index}"}
                    for index in range(5)
                ],
                "index": [
                    {"identity_key": "index:SH:000001", "code": "000001"},
                    {"identity_key": "index:SZ:399006", "code": "399006"},
                ],
                "board": [
                    {"identity_key": "board:TDX:881001", "code": "881001"}
                ],
            }
        )

        self.assertEqual(
            [(row.asset_kind, row.symbol, row.method) for row in requests],
            [
                ("stock", "600000", "bars"),
                ("stock", "600002", "bars"),
                ("stock", "600004", "bars"),
                ("index", "000001", "index"),
                ("index", "399006", "index"),
                ("board", "881001", "index"),
            ],
        )

    def test_two_transport_normalized_parity_passes_without_runtime_eligibility(self) -> None:
        baseline = FakeTransport("mootdx")
        candidate = FakeTransport(
            "tdxpy",
            {
                ("index", "000001"): [
                    {
                        "code": "000001",
                        "trade_date": "20260717",
                        "open": 10,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.50,
                    }
                ]
            },
        )
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="index",
                    identity_key="index:SH:000001",
                    symbol="000001",
                    method="index",
                )
            ],
            baseline=baseline,
            candidate=candidate,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["sentinel_count"], 1)
        self.assertEqual(report["consecutive_trading_days_proven"], 0)
        self.assertFalse(report["runtime_switch_eligible"])
        self.assertEqual(len(baseline.calls), 1)
        self.assertEqual(len(candidate.calls), 1)

    def test_real_wrappers_add_missing_raw_bar_identity_and_parity_passes(self) -> None:
        rows_without_code = [
            {
                "datetime": "2026-07-17",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
            }
        ]

        class MootdxClient:
            def index(self, **kwargs):
                return list(rows_without_code)

        baseline = MootdxQuoteTransport(
            selection=endpoint_selection("mootdx"),
            client=MootdxClient(),
        )
        candidate = TdxpyQuoteTransport(
            selection=endpoint_selection("tdxpy"),
            api_factory=lambda **kwargs: FakeTdxpyParityApi(rows_without_code),
        )
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="index",
                    identity_key="index:SH:000001",
                    symbol="000001",
                    method="index",
                )
            ],
            baseline=baseline,
            candidate=candidate,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(
            report["results"][0]["baseline"]["identity"],
            ["index:SH:000001"],
        )
        self.assertEqual(
            report["results"][0]["candidate"]["identity"],
            ["index:SH:000001"],
        )

    def test_real_wrapper_wrong_code_is_not_overwritten_and_parity_fails(self) -> None:
        class MootdxClient:
            def index(self, **kwargs):
                return [
                    {
                        "code": "000002",
                        "datetime": "2026-07-17",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                    }
                ]

        correct_rows = [
            {
                "datetime": "2026-07-17",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
            }
        ]
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="index",
                    identity_key="index:SH:000001",
                    symbol="000001",
                    method="index",
                )
            ],
            baseline=MootdxQuoteTransport(
                selection=endpoint_selection("mootdx"),
                client=MootdxClient(),
            ),
            candidate=TdxpyQuoteTransport(
                selection=endpoint_selection("tdxpy"),
                api_factory=lambda **kwargs: FakeTdxpyParityApi(correct_rows),
            ),
        )

        self.assertFalse(report["passed"])
        self.assertIn("identity", report["results"][0]["mismatches"])

    def test_beijing_stock_920_and_index_899_identity_contract_passes(self) -> None:
        rows = {
            ("bars", "920211"): [
                {
                    "code": "920211",
                    "datetime": "2026-07-17",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                }
            ],
            ("index", "899050"): [
                {
                    "code": "899050",
                    "datetime": "2026-07-17",
                    "open": 20,
                    "high": 21,
                    "low": 19,
                    "close": 20.5,
                }
            ],
        }
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="stock",
                    identity_key="stock:BJ:920211",
                    symbol="920211",
                    method="bars",
                ),
                SentinelRequest(
                    asset_kind="index",
                    identity_key="index:BJ:899050",
                    symbol="899050",
                    method="index",
                ),
            ],
            baseline=FakeTransport("mootdx", rows),
            candidate=FakeTransport("tdxpy", rows),
        )

        self.assertTrue(report["passed"])
        self.assertEqual(
            report["results"][0]["baseline"]["identity"],
            ["stock:BJ:920211"],
        )
        self.assertEqual(
            report["results"][1]["baseline"]["identity"],
            ["index:BJ:899050"],
        )

    def test_none_false_and_empty_fail_non_empty(self) -> None:
        request = SentinelRequest(
            asset_kind="stock",
            identity_key="stock:SH:600036",
            symbol="600036",
            method="bars",
        )
        for empty in (None, False, []):
            with self.subTest(empty=empty):
                baseline = FakeTransport(
                    "mootdx",
                    {("bars", "600036"): empty},
                )
                report = compare_sentinel_parity(
                    trade_date="20260717",
                    requests=[request],
                    baseline=baseline,
                    candidate=FakeTransport("tdxpy"),
                )
                self.assertFalse(report["passed"])
                self.assertIn("non_empty", report["results"][0]["mismatches"])

    def test_identity_date_ohlc_row_count_and_hash_mismatch_are_visible(self) -> None:
        baseline = FakeTransport("mootdx")
        candidate = FakeTransport(
            "tdxpy",
            {
                ("bars", "600036"): [
                    {
                        "code": "600037",
                        "datetime": "2026-07-17",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 99,
                    },
                    {
                        "code": "600037",
                        "datetime": "2026-07-17",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 99,
                    },
                ]
            },
        )
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="stock",
                    identity_key="stock:SH:600036",
                    symbol="600036",
                    method="bars",
                )
            ],
            baseline=baseline,
            candidate=candidate,
        )

        mismatches = report["results"][0]["mismatches"]
        self.assertIn("identity", mismatches)
        self.assertIn("ohlc", mismatches)
        self.assertIn("row_count", mismatches)
        self.assertIn("normalized_hash", mismatches)

    def test_same_wrong_identity_on_both_transports_cannot_pass_canonical_request(self) -> None:
        wrong_rows = {
            ("bars", "600036"): [
                {
                    "code": "600037",
                    "datetime": "2026-07-17",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                }
            ]
        }
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="stock",
                    identity_key="stock:SH:600036",
                    symbol="600036",
                    method="bars",
                )
            ],
            baseline=FakeTransport("mootdx", wrong_rows),
            candidate=FakeTransport("tdxpy", wrong_rows),
        )

        self.assertFalse(report["passed"])
        self.assertEqual(report["results"][0]["mismatches"], ["identity"])

    def test_missing_identity_on_both_transports_cannot_fallback_to_request_symbol(self) -> None:
        missing_identity_rows = {
            ("bars", "600036"): [
                {
                    "datetime": "2026-07-17",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                }
            ]
        }
        report = compare_sentinel_parity(
            trade_date="20260717",
            requests=[
                SentinelRequest(
                    asset_kind="stock",
                    identity_key="stock:SH:600036",
                    symbol="600036",
                    method="bars",
                )
            ],
            baseline=FakeTransport("mootdx", missing_identity_rows),
            candidate=FakeTransport("tdxpy", missing_identity_rows),
        )

        self.assertFalse(report["passed"])
        self.assertEqual(report["results"][0]["mismatches"], ["identity"])
        self.assertEqual(report["results"][0]["baseline"]["identity"], [""])
        self.assertEqual(report["results"][0]["candidate"]["identity"], [""])

    def test_full_scope_attempt_is_rejected_before_any_transport_call(self) -> None:
        baseline = FakeTransport("mootdx")
        candidate = FakeTransport("tdxpy")
        requests = [
            SentinelRequest(
                asset_kind="stock",
                identity_key=f"stock:SH:60000{index}",
                symbol=f"60000{index}",
                method="bars",
            )
            for index in range(4)
        ]

        with self.assertRaisesRegex(QuoteTransportParityError, "more than three"):
            compare_sentinel_parity(
                trade_date="20260717",
                requests=requests,
                baseline=baseline,
                candidate=candidate,
            )

        self.assertEqual(baseline.calls, [])
        self.assertEqual(candidate.calls, [])

    def test_unsupported_and_missing_authority_fail_closed(self) -> None:
        with self.assertRaisesRegex(QuoteTransportParityError, "must not be empty"):
            compare_sentinel_parity(
                trade_date="20260717",
                requests=[],
                baseline=FakeTransport("mootdx"),
                candidate=FakeTransport("tdxpy"),
            )
        with self.assertRaisesRegex(QuoteTransportParityError, "distinct"):
            compare_sentinel_parity(
                trade_date="20260717",
                requests=[
                    SentinelRequest(
                        asset_kind="stock",
                        identity_key="stock:SH:600036",
                        symbol="600036",
                        method="bars",
                    )
                ],
                baseline=FakeTransport("mootdx"),
                candidate=FakeTransport("mootdx"),
            )
        with self.assertRaisesRegex(QuoteTransportParityError, "unsupported sentinel method"):
            compare_sentinel_parity(
                trade_date="20260717",
                requests=[
                    SentinelRequest(
                        asset_kind="stock",
                        identity_key="stock:SH:600036",
                        symbol="600036",
                        method="quotes",
                    )
                ],
                baseline=FakeTransport("mootdx"),
                candidate=FakeTransport("tdxpy"),
            )

    def test_transport_exception_is_not_silently_empty(self) -> None:
        with self.assertRaisesRegex(
            QuoteTransportParityError,
            "mootdx sentinel call failed",
        ):
            compare_sentinel_parity(
                trade_date="20260717",
                requests=[
                    SentinelRequest(
                        asset_kind="stock",
                        identity_key="stock:SH:600036",
                        symbol="600036",
                        method="bars",
                    )
                ],
                baseline=FakeTransport("mootdx", error=TimeoutError("fake")),
                candidate=FakeTransport("tdxpy"),
            )

    def test_rollout_evaluator_three_open_days_pass(self) -> None:
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260715"),
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertEqual(report["used_trade_dates"], ["20260715", "20260716", "20260717"])
        self.assertEqual(report["consecutive_trading_days_proven"], 3)
        self.assertTrue(report["runtime_switch_eligible"])
        json.dumps(report, sort_keys=True)

    def test_rollout_evaluator_duplicate_report_date_does_not_accumulate(self) -> None:
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260715"),
                daily_report("20260716"),
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertEqual(report["consecutive_trading_days_proven"], 0)
        self.assertIn("duplicate_report_trade_date", report["reasons"])

    def test_rollout_evaluator_missing_recent_open_day_is_ineligible(self) -> None:
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260715"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertEqual(report["missing_trade_dates"], ["20260716"])
        self.assertIn("missing_recent_open_trade_date", report["reasons"])

    def test_rollout_evaluator_failed_or_empty_daily_report_is_ineligible(self) -> None:
        for override in ({"passed": False}, {"sentinel_count": 0}):
            with self.subTest(override=override):
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        daily_report("20260715"),
                        daily_report("20260716", **override),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertEqual(report["failed_trade_dates"], ["20260716"])
                self.assertIn("recent_open_trade_date_failed", report["reasons"])

    def test_rollout_evaluator_requires_consecutive_dates_in_open_calendar(self) -> None:
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260715"),
                daily_report("20260717"),
                daily_report("20260720"),
            ],
            ordered_open_trade_dates=[
                "20260715",
                "20260716",
                "20260717",
                "20260720",
            ],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertEqual(report["used_trade_dates"], ["20260716", "20260717", "20260720"])
        self.assertEqual(report["missing_trade_dates"], ["20260716"])

    def test_rollout_evaluator_schema_and_transport_mismatch_fail_closed(self) -> None:
        invalid_reports = (
            daily_report("20260715", schema_version="wrong"),
            daily_report("20260715", baseline_transport="tdxpy"),
            daily_report("20260715", candidate_transport="mootdx"),
        )
        expected_reasons = (
            "schema_version_mismatch",
            "transport_authority_mismatch",
            "transport_authority_mismatch",
        )
        for invalid_report, expected_reason in zip(invalid_reports, expected_reasons):
            with self.subTest(expected_reason=expected_reason):
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        invalid_report,
                        daily_report("20260716"),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertEqual(report["consecutive_trading_days_proven"], 0)
                self.assertIn(expected_reason, report["reasons"])

    def test_rollout_evaluator_four_day_window_ignores_earlier_failure(self) -> None:
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260714", passed=False),
                daily_report("20260715"),
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=[
                "20260714",
                "20260715",
                "20260716",
                "20260717",
            ],
        )

        self.assertEqual(report["used_trade_dates"], ["20260715", "20260716", "20260717"])
        self.assertEqual(report["consecutive_trading_days_proven"], 3)
        self.assertTrue(report["runtime_switch_eligible"])
        self.assertEqual(report["earlier_failed_trade_dates"], ["20260714"])
        self.assertEqual(report["audit_reasons"], ["earlier_failed_trade_dates_ignored"])

    def test_rollout_evaluator_rejects_out_of_order_and_non_open_reports(self) -> None:
        for daily_reports, expected_reason in (
            (
                [
                    daily_report("20260716"),
                    daily_report("20260715"),
                    daily_report("20260717"),
                ],
                "daily_reports_out_of_order",
            ),
            (
                [
                    daily_report("20260715"),
                    daily_report("20260716"),
                    daily_report("20260718"),
                ],
                "report_trade_date_not_open",
            ),
        ):
            with self.subTest(expected_reason=expected_reason):
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=daily_reports,
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertEqual(report["consecutive_trading_days_proven"], 0)
                self.assertIn(expected_reason, report["reasons"])

        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                daily_report("20260715"),
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260717", "20260716"],
        )
        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("ordered_open_trade_dates_out_of_order", report["reasons"])

    def test_rollout_evaluator_rejects_missing_results(self) -> None:
        invalid = daily_report("20260715")
        invalid.pop("results")
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("results_missing_or_invalid", report["reasons"])

    def test_rollout_evaluator_rejects_sentinel_count_mismatch(self) -> None:
        invalid = daily_report("20260715")
        invalid["sentinel_count"] = 2
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("sentinel_count_mismatch", report["reasons"])

    def test_rollout_evaluator_rejects_child_failure_hidden_by_top_pass(self) -> None:
        invalid = daily_report("20260715")
        invalid["results"][0]["passed"] = False
        invalid["results"][0]["mismatches"] = ["identity"]
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("child_result_failed", report["reasons"])
        self.assertIn("child_mismatches_not_empty", report["reasons"])
        self.assertIn("top_level_passed_mismatch", report["reasons"])

    def test_rollout_evaluator_rejects_duplicate_sentinel(self) -> None:
        invalid = daily_report("20260715")
        invalid["results"][1] = copy.deepcopy(invalid["results"][0])
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("duplicate_sentinel", report["reasons"])

    def test_rollout_evaluator_rejects_wrong_scope_policy(self) -> None:
        invalid = daily_report("20260715")
        invalid["scope_policy"] = "full_scope"
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("scope_policy_mismatch", report["reasons"])

    def test_rollout_evaluator_rejects_asset_kind_counts_mismatch(self) -> None:
        invalid = daily_report("20260715")
        invalid["asset_kind_counts"] = {"index": 3}
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("asset_kind_counts_result_mismatch", report["reasons"])

    def test_rollout_evaluator_rejects_invalid_normalized_identity_date_and_hash(self) -> None:
        mutations = (
            ("identity", [], "baseline_identity_mismatch"),
            ("dates", ["20260716"], "baseline_dates_mismatch"),
            ("normalized_hash", "", "baseline_normalized_hash_invalid"),
        )
        for field_name, value, expected_reason in mutations:
            with self.subTest(field_name=field_name):
                invalid = daily_report("20260715")
                invalid["results"][0]["baseline"][field_name] = value
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        invalid,
                        daily_report("20260716"),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertIn(expected_reason, report["reasons"])

        invalid = daily_report("20260715")
        invalid["results"][0]["baseline"].pop("normalized_hash")
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )
        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("baseline_normalized_fields_missing", report["reasons"])

        invalid = daily_report("20260715")
        invalid["results"][0]["candidate"]["normalized_hash"] = "0" * 64
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )
        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("normalized_parity_mismatch", report["reasons"])

    def test_rollout_evaluator_rejects_noncanonical_ohlc_and_short_hash(self) -> None:
        mutations = (
            ([None], None, "baseline_ohlc_invalid"),
            (
                [{"open": "bad", "high": "2", "low": "1", "close": "2"}],
                None,
                "baseline_ohlc_invalid",
            ),
            (None, "x", "baseline_normalized_hash_invalid"),
        )
        for ohlc, normalized_hash, expected_reason in mutations:
            with self.subTest(expected_reason=expected_reason):
                invalid = daily_report("20260715")
                if ohlc is not None:
                    invalid["results"][0]["baseline"]["ohlc"] = ohlc
                if normalized_hash is not None:
                    invalid["results"][0]["baseline"][
                        "normalized_hash"
                    ] = normalized_hash
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        invalid,
                        daily_report("20260716"),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertIn(expected_reason, report["reasons"])

    def test_rollout_evaluator_rejects_symbol_identity_mismatch(self) -> None:
        invalid = daily_report("20260715")
        invalid["results"][0]["request"]["symbol"] = "600999"
        report = evaluate_quote_transport_rollout_eligibility(
            daily_reports=[
                invalid,
                daily_report("20260716"),
                daily_report("20260717"),
            ],
            ordered_open_trade_dates=["20260715", "20260716", "20260717"],
        )

        self.assertFalse(report["runtime_switch_eligible"])
        self.assertIn("sentinel_request_contract_invalid", report["reasons"])

    def test_rollout_evaluator_requires_complete_request_execution_fields(self) -> None:
        for field_name in ("frequency", "start", "offset"):
            with self.subTest(field_name=field_name):
                invalid = daily_report("20260715")
                invalid["results"][0]["request"].pop(field_name)
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        invalid,
                        daily_report("20260716"),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertIn("sentinel_request_contract_invalid", report["reasons"])

    def test_rollout_evaluator_rejects_invalid_request_ranges_and_types(self) -> None:
        mutations = (
            ("frequency", 12),
            ("frequency", True),
            ("start", -1),
            ("offset", 0),
            ("offset", 801),
        )
        for field_name, value in mutations:
            with self.subTest(field_name=field_name, value=value):
                invalid = daily_report("20260715")
                invalid["results"][0]["request"][field_name] = value
                report = evaluate_quote_transport_rollout_eligibility(
                    daily_reports=[
                        invalid,
                        daily_report("20260716"),
                        daily_report("20260717"),
                    ],
                    ordered_open_trade_dates=["20260715", "20260716", "20260717"],
                )

                self.assertFalse(report["runtime_switch_eligible"])
                self.assertIn("sentinel_request_contract_invalid", report["reasons"])


if __name__ == "__main__":
    unittest.main()
