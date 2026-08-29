from __future__ import annotations

from types import SimpleNamespace
import unittest

from scripts.run_windows_postclose_fastlane import (
    run_postclose_fastlane,
    validate_n4_readiness,
)


SOURCE_DATE = "20260828"
FOR_DATE = "20260831"
RUN_ID = "condition_layer_20260828_to_20260831_v1"
CONTEXT_VERSION = "pretrade_4e20cf5_v1"


def n2_result(result="N2_AFTER_N1_PASS"):
    return {
        "result": result,
        "source_trade_date": SOURCE_DATE,
        "for_trade_date": FOR_DATE,
        "active_run_id": RUN_ID,
    }


def n3_result(result="N3_PREVIOUS_DAY_CONTEXT_COMPLETE"):
    counts = {"stock": 2, "index": 1, "board": 1}
    return {
        "result": result,
        "context_run_id": "windows_n3_previous_day_context_1",
        "context_version": CONTEXT_VERSION,
        "expected_counts": counts,
        "terminal_counts": counts,
        "status_counts": {
            "stock": {"ready": 2},
            "index": {"ready": 1},
            "board": {"ready": 1},
        },
    }


def model():
    return SimpleNamespace(
        run_id=RUN_ID,
        source_trade_date=SOURCE_DATE,
        for_trade_date=FOR_DATE,
        stock=(object(), object()),
        index=(object(),),
        board=(object(),),
    )


def context():
    return SimpleNamespace(
        context_run_id="windows_n3_previous_day_context_1",
        source_condition_run_id=RUN_ID,
        source_trade_date=SOURCE_DATE,
        for_trade_date=FOR_DATE,
        context_version=CONTEXT_VERSION,
        status_counts={
            "stock": {"ready": 2},
            "index": {"ready": 1},
            "board": {"ready": 1},
        },
    )


def runtime_builder(active_model):
    def snapshot(asset_kind):
        return SimpleNamespace(
            states={str(index): object() for index, _ in enumerate(getattr(active_model, asset_kind))},
            version=0,
            channel_status="warming",
        )

    return SimpleNamespace(
        get_stock_states=lambda: snapshot("stock"),
        get_index_states=lambda: snapshot("index"),
        get_board_states=lambda: snapshot("board"),
    )


class WindowsPostcloseFastlaneTest(unittest.TestCase):
    def test_runs_n2_n3_then_validates_n4_readiness(self):
        calls = []
        result = run_postclose_fastlane(
            run_n2=lambda: calls.append("n2") or n2_result(),
            run_n3=lambda for_date: calls.append(("n3", for_date)) or n3_result(),
            load_model=lambda for_date: calls.append(("model", for_date)) or model(),
            load_context=lambda active: calls.append(("context", active.run_id)) or context(),
            runtime_builder=runtime_builder,
        )
        self.assertEqual(
            calls,
            ["n2", ("n3", FOR_DATE), ("model", FOR_DATE), ("context", RUN_ID)],
        )
        self.assertEqual(result["result"], "WINDOWS_POSTCLOSE_FASTLANE_PASS")
        self.assertEqual(result["n3_context_version"], CONTEXT_VERSION)
        self.assertEqual(result["n3_expected_total"], 4)
        self.assertEqual(result["n3_ready_total"], 4)
        self.assertEqual(result["n3_missing_total"], 0)
        self.assertEqual(result["n3_missing_threshold"], 0.2)
        self.assertEqual(result["n3_coverage_gate"], "passed")
        self.assertEqual(result["n4_readiness"]["state_counts"], {"stock": 2, "index": 1, "board": 1})
        self.assertEqual(result["n4_database_write_count"], 0)
        self.assertEqual(result["trigger_event_count"], 0)

    def test_accepts_idempotent_n2_and_n3_results(self):
        result = run_postclose_fastlane(
            run_n2=lambda: n2_result("SKIPPED_IDENTICAL_PASSED_ACTIVE"),
            run_n3=lambda _date: n3_result("N3_PREVIOUS_DAY_CONTEXT_SKIPPED_COMPLETE"),
            load_model=lambda _date: model(),
            load_context=lambda _active: context(),
            runtime_builder=runtime_builder,
        )
        self.assertEqual(result["result"], "WINDOWS_POSTCLOSE_FASTLANE_PASS")

    def test_non_trading_day_stops_before_n3(self):
        called = False

        def run_n3(_date):
            nonlocal called
            called = True
            return n3_result()

        result = run_postclose_fastlane(
            run_n2=lambda: {
                "result": "SKIPPED_NON_TRADING_DAY",
                "source_trade_date": "20260829",
            },
            run_n3=run_n3,
            load_model=lambda _date: model(),
            load_context=lambda _active: context(),
            runtime_builder=runtime_builder,
        )
        self.assertEqual(
            result["result"],
            "WINDOWS_POSTCLOSE_FASTLANE_SKIPPED_NON_TRADING_DAY",
        )
        self.assertFalse(called)

    def test_n2_failure_stops_before_n3(self):
        with self.assertRaisesRegex(RuntimeError, "N2 post-close stage"):
            run_postclose_fastlane(
                run_n2=lambda: n2_result("N2_EXECUTE_FAILED"),
                run_n3=lambda _date: self.fail("N3 must not run"),
                load_model=lambda _date: model(),
                load_context=lambda _active: context(),
                runtime_builder=runtime_builder,
            )

    def test_context_version_mismatch_blocks_n4_readiness(self):
        broken = context()
        broken.context_version = "v1"
        with self.assertRaisesRegex(RuntimeError, "context version"):
            run_postclose_fastlane(
                run_n2=lambda: n2_result(),
                run_n3=lambda _date: n3_result(),
                load_model=lambda _date: model(),
                load_context=lambda _active: broken,
                runtime_builder=runtime_builder,
            )

    def test_context_count_mismatch_blocks_n4_readiness(self):
        broken = context()
        broken.status_counts = {
            "stock": {"ready": 1},
            "index": {"ready": 1},
            "board": {"partial": 1},
        }
        with self.assertRaisesRegex(RuntimeError, "terminal counts"):
            run_postclose_fastlane(
                run_n2=lambda: n2_result(),
                run_n3=lambda _date: n3_result(),
                load_model=lambda _date: model(),
                load_context=lambda _active: broken,
                runtime_builder=runtime_builder,
            )

    def test_exactly_twenty_percent_missing_still_passes(self):
        active_model = SimpleNamespace(
            run_id=RUN_ID,
            source_trade_date=SOURCE_DATE,
            for_trade_date=FOR_DATE,
            stock=tuple(object() for _ in range(5)),
            index=(),
            board=(),
        )
        loaded = SimpleNamespace(
            source_condition_run_id=RUN_ID,
            source_trade_date=SOURCE_DATE,
            for_trade_date=FOR_DATE,
            status_counts={
                "stock": {"ready": 4, "failed": 1},
                "index": {},
                "board": {},
            },
        )
        readiness = validate_n4_readiness(
            active_model,
            loaded,
            runtime_builder=runtime_builder,
        )
        self.assertEqual(readiness.state_counts["stock"], 5)

    def test_missing_ratio_above_twenty_percent_blocks(self):
        failed = context()
        failed.status_counts = {
            "stock": {"ready": 1, "failed": 1},
            "index": {"ready": 1},
            "board": {"failed": 1},
        }
        with self.assertRaisesRegex(RuntimeError, "missing ratio exceeds threshold"):
            run_postclose_fastlane(
                run_n2=lambda: n2_result(),
                run_n3=lambda _date: n3_result(),
                load_model=lambda _date: model(),
                load_context=lambda _active: failed,
                runtime_builder=runtime_builder,
            )

    def test_small_missing_channel_is_degraded_without_global_block(self):
        active_model = SimpleNamespace(
            run_id=RUN_ID,
            source_trade_date=SOURCE_DATE,
            for_trade_date=FOR_DATE,
            stock=tuple(object() for _ in range(10)),
            index=(object(),),
            board=(object(),),
        )
        loaded = SimpleNamespace(
            source_condition_run_id=RUN_ID,
            source_trade_date=SOURCE_DATE,
            for_trade_date=FOR_DATE,
            status_counts={
                "stock": {"ready": 10},
                "index": {"failed": 1},
                "board": {"ready": 1},
            },
        )
        readiness = validate_n4_readiness(
            active_model,
            loaded,
            runtime_builder=runtime_builder,
        )
        self.assertEqual(
            readiness.state_counts,
            {"stock": 10, "index": 1, "board": 1},
        )
        self.assertEqual(readiness.channel_statuses["index"], "degraded")
        self.assertEqual(readiness.channel_statuses["stock"], "warming")


if __name__ == "__main__":
    unittest.main()
