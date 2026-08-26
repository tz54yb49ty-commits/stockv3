from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import unittest

from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_real_daily_incremental.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("real_daily_bundle_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeManager:
    def __init__(self, mode: str):
        self.n1_failover_mode = mode


class FakeSource:
    def __init__(
        self,
        endpoint_id,
        attempt_id,
        calls,
        *,
        fail_index=False,
        close_error=False,
    ):
        self.endpoint_id = endpoint_id
        self.attempt_id = attempt_id
        self.calls = calls
        self.fail_index = fail_index
        self.close_error = close_error
        self.close_count = 0
        self.endpoint_provenance = {
            "endpoint_pool_version": "test-pool-v1",
            "endpoint_id": endpoint_id,
            "transport": "mootdx",
            "health_state": "healthy",
            "health_checked_at": "2026-07-19T00:00:00+00:00",
            "probe_summary": {"passed": True},
            "attempt_id": attempt_id,
            "selection_reason": "test",
            "failover_from": "primary" if endpoint_id == "secondary" else None,
            "failover_reason": "source_fetch_transport_exception" if endpoint_id == "secondary" else None,
            "failover_performed": endpoint_id == "secondary",
            "would_retry": False,
            "retry_reason": None,
        }

    def fetch_board_daily_bars(self, **kwargs):
        self.calls.append((self.endpoint_id, "board"))
        return [self._row(board.board_code) for board in kwargs["boards"]]

    def fetch_index_daily_bars(self, **kwargs):
        self.calls.append((self.endpoint_id, "index"))
        if self.fail_index:
            self.endpoint_provenance["would_retry"] = True
            self.endpoint_provenance["retry_reason"] = "source_fetch_transport_exception"
            raise TimeoutError("fake runtime failure")
        return [self._row(index.code) for index in kwargs["indexes"]]

    def _row(self, code):
        return {
            "code": code,
            "mootdx_endpoint_provenance": dict(self.endpoint_provenance),
        }

    def close(self):
        self.close_count += 1
        if self.close_error:
            self.endpoint_provenance["business_client_close_error"] = "RuntimeError"
            raise RuntimeError("fake close failure")


class RealDailyMootdxBundleTest(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.indexes = [IndexDailySymbol(code="000001", exchange="SH", name="上证")]
        self.boards = [
            BoardDailySymbol(
                board_code="881001",
                board_name="行业",
                board_type="tdx_industry",
            )
        ]

    def test_active_discards_partial_attempt_and_replays_board_and_index_once(self):
        calls = []
        created = []

        def factory(**kwargs):
            endpoint_id = "primary" if not created else "secondary"
            source = FakeSource(
                endpoint_id,
                kwargs["attempt_id"],
                calls,
                fail_index=endpoint_id == "primary",
            )
            created.append(source)
            return source

        bundle = self.runner.prepare_mootdx_daily_bundle(
            indexes=self.indexes,
            boards=self.boards,
            trade_date="20260719",
            mootdx_offset=800,
            endpoint_manager=FakeManager("active"),
            source_factory=factory,
            attempt_id="real-bundle",
        )

        self.assertEqual(
            calls,
            [
                ("primary", "board"),
                ("primary", "index"),
                ("secondary", "board"),
                ("secondary", "index"),
            ],
        )
        self.assertEqual(bundle["mootdx_endpoint_provenance"]["endpoint_id"], "secondary")
        self.assertEqual([source.close_count for source in created], [1, 1])
        self.assertEqual(bundle["mootdx_endpoint_provenance"]["replay_count"], 1)
        self.assertEqual(
            [row["status"] for row in bundle["mootdx_endpoint_provenance"]["attempts"]],
            ["failed", "winning"],
        )
        self.assertEqual(
            bundle["mootdx_endpoint_provenance"]["winning_attempt_id"],
            "real-bundle__retry_1",
        )
        self.assertEqual(
            {
                row["mootdx_endpoint_provenance"]["endpoint_id"]
                for row in [*bundle["board"], *bundle["index"]]
            },
            {"secondary"},
        )

    def test_observe_records_retryable_failure_without_secondary_business_fetch(self):
        calls = []
        created = []

        def factory(**kwargs):
            source = FakeSource(
                "primary",
                kwargs["attempt_id"],
                calls,
                fail_index=True,
            )
            created.append(source)
            return source

        with self.assertRaisesRegex(TimeoutError, "fake runtime failure") as raised:
            self.runner.prepare_mootdx_daily_bundle(
                indexes=self.indexes,
                boards=self.boards,
                trade_date="20260719",
                mootdx_offset=800,
                endpoint_manager=FakeManager("observe"),
                source_factory=factory,
                attempt_id="real-bundle-observe",
            )

        self.assertEqual(calls, [("primary", "board"), ("primary", "index")])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].close_count, 1)
        self.assertTrue(created[0].endpoint_provenance["would_retry"])
        trace = raised.exception.mootdx_endpoint_provenance
        self.assertIsNone(trace["winning_attempt_id"])
        self.assertEqual(trace["attempts"][0]["status"], "failed")
        self.assertEqual(trace["attempts"][0]["endpoint_id"], "primary")

    def test_success_closes_winning_client_once_before_return(self):
        calls = []
        created = []

        def factory(**kwargs):
            source = FakeSource("primary", kwargs["attempt_id"], calls)
            created.append(source)
            return source

        bundle = self.runner.prepare_mootdx_daily_bundle(
            indexes=self.indexes,
            boards=self.boards,
            trade_date="20260719",
            mootdx_offset=800,
            endpoint_manager=FakeManager("observe"),
            source_factory=factory,
            attempt_id="real-bundle-success",
        )

        self.assertEqual(bundle["mootdx_endpoint_provenance"]["endpoint_id"], "primary")
        self.assertEqual(created[0].close_count, 1)

    def test_success_close_failure_blocks_bundle(self):
        calls = []

        with self.assertRaisesRegex(RuntimeError, "fake close failure"):
            self.runner.prepare_mootdx_daily_bundle(
                indexes=self.indexes,
                boards=self.boards,
                trade_date="20260719",
                mootdx_offset=800,
                endpoint_manager=FakeManager("observe"),
                source_factory=lambda **kwargs: FakeSource(
                    "primary",
                    kwargs["attempt_id"],
                    calls,
                    close_error=True,
                ),
                attempt_id="real-bundle-close-fail",
            )

    def test_network_row_missing_provenance_is_rejected(self):
        provenance = {
            "endpoint_id": "primary",
            "attempt_id": "attempt-1",
            "transport": "mootdx",
        }
        self.assertFalse(
            self.runner._rows_match_endpoint_provenance(
                [{"code": "881001"}],
                provenance,
            )
        )

    def test_network_row_mixed_transport_is_rejected(self):
        provenance = {
            "endpoint_id": "primary",
            "attempt_id": "attempt-1",
            "transport": "mootdx",
        }
        self.assertFalse(
            self.runner._rows_match_endpoint_provenance(
                [
                    {
                        "mootdx_endpoint_provenance": {
                            **provenance,
                            "transport": "other",
                        }
                    }
                ],
                provenance,
            )
        )

    def test_phase_all_prefetch_precedes_stock_fact_load(self):
        main_source = inspect.getsource(self.runner.main)
        self.assertLess(
            main_source.index("prepare_mootdx_daily_bundle("),
            main_source.index("load_stock_daily_day("),
        )

    def test_single_index_and_board_phases_close_business_client_once(self):
        for phase in ("index", "board"):
            with self.subTest(phase=phase):
                calls = []
                source = FakeSource("primary", f"{phase}-attempt", calls)
                if phase == "index":
                    fetch = lambda: source.fetch_index_daily_bars(indexes=self.indexes)
                else:
                    fetch = lambda: source.fetch_board_daily_bars(boards=self.boards)

                rows, provenance = self.runner._fetch_and_close_mootdx_phase(
                    source,
                    fetch,
                )

                self.assertEqual(len(rows), 1)
                self.assertEqual(source.close_count, 1)
                self.assertEqual(provenance["endpoint_id"], "primary")

        self.assertIn(
            "_fetch_and_close_mootdx_phase(",
            inspect.getsource(self.runner.load_index_daily_day),
        )
        self.assertIn(
            "_fetch_and_close_mootdx_phase(",
            inspect.getsource(self.runner.load_board_daily_day),
        )

    def test_single_phase_close_failure_is_fail_closed_and_traced(self):
        source = FakeSource(
            "primary",
            "single-close-fail",
            [],
            close_error=True,
        )

        with self.assertRaisesRegex(RuntimeError, "fake close failure") as raised:
            self.runner._fetch_and_close_mootdx_phase(
                source,
                lambda: source.fetch_index_daily_bars(indexes=self.indexes),
            )

        self.assertEqual(source.close_count, 1)
        self.assertEqual(
            raised.exception.mootdx_endpoint_provenance[
                "business_client_close_error"
            ],
            "RuntimeError",
        )


if __name__ == "__main__":
    unittest.main()
