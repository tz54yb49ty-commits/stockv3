from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import unittest

from ashare_v3.market.windows_n3_minute_context import (
    MinuteContextBatch,
    build_minute_context,
    normalize_minute_bars,
)
from ashare_v3.market.windows_n3_previous_day_context import (
    MinuteContextFetchBatch,
    PreviousDayContextPreloadSummary,
    PostgresPreviousDayContextLoader,
    TQStockMinuteContextProvider,
    TQWithEltdxMinuteContextProvider,
    UnavailableTQMinuteContextProvider,
    WindowsN3PreviousDayContextPreloader,
    context_record_sha256,
    make_context_record,
)
from ashare_v3.market.windows_n3_read_model import (
    N2ObjectRuntimeInput,
    N3ActiveReadModel,
)
from ashare_v3.market.windows_n3_snapshot import StockSnapshotRequest
from scripts.run_windows_n3_previous_day_context import summary_to_dict


def request(index: int) -> StockSnapshotRequest:
    code = f"{600000 + index:06d}"
    return StockSnapshotRequest(f"stock:SH:{code}", "SH", code, code)


def minute_rows(trade_date: str, count: int = 240):
    day = datetime.strptime(trade_date, "%Y%m%d")
    result = []
    for index in range(count):
        point = (
            day.replace(hour=9, minute=30) + timedelta(minutes=index)
            if index < 120
            else day.replace(hour=13, minute=0) + timedelta(minutes=index - 120)
        )
        result.append(
            {
                "time": point,
                "open": "10",
                "high": "12",
                "low": "9",
                "close": "11",
                "amount": "100",
            }
        )
    return result


def minute_context(identity_key: str, trade_date: str, count: int = 240):
    bars = normalize_minute_bars(identity_key, trade_date, minute_rows(trade_date, count))
    return build_minute_context(identity_key, trade_date, bars)


class TQClient:
    def __init__(self, missing=(), fail=False):
        self.calls = []
        self.missing = set(missing)
        self.fail = fail

    def get_market_data(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("tq unavailable")
        return {
            code: minute_rows("20260827", 1)
            for code in kwargs["stock_list"]
            if code not in self.missing
        }


class Series(dict):
    pass


class Frame:
    def __init__(self, values):
        self._values = values
        self.columns = list(values)

    def __getitem__(self, key):
        return Series(self._values[key])


class MatrixTQClient:
    def get_market_data(self, **kwargs):
        code = kwargs["stock_list"][0]
        rows = minute_rows("20260827")
        return {
            field: Frame({code: {row["time"]: row[field] for row in rows}})
            for field in ("open", "high", "low", "close", "amount")
        }


class EltdxProvider:
    provider_name = "eltdx.test"

    def __init__(self, counts=None):
        self.calls = []
        self.counts = counts or {}

    def fetch_many(self, requests, trade_date, *, require_complete=False):
        self.calls.append(tuple(row.identity_key for row in requests))
        contexts = {
            row.identity_key: minute_context(
                row.identity_key,
                trade_date,
                self.counts.get(row.identity_key, 1),
            )
            for row in requests
            if self.counts.get(row.identity_key, 1) > 0
        }
        missing = tuple(
            row.identity_key for row in requests if row.identity_key not in contexts
        )
        return MinuteContextBatch(contexts, missing, (), self.provider_name)


class FixedPrimary:
    provider_name = "tq.test"

    def __init__(self, counts):
        self.counts = counts
        self.calls = []

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        self.calls.append(tuple(row.identity_key for row in requests))
        contexts = {
            row.identity_key: minute_context(
                row.identity_key,
                trade_date,
                self.counts.get(row.identity_key, 0),
            )
            for row in requests
            if self.counts.get(row.identity_key, 0) > 0
        }
        missing = tuple(
            row.identity_key
            for row in requests
            if row.identity_key not in contexts
            or (require_complete and len(contexts[row.identity_key].bars) != 240)
        )
        return MinuteContextFetchBatch(
            contexts,
            {key: self.provider_name for key in contexts},
            missing,
            (),
            (),
        )


class EmptyPrimary:
    def __init__(self):
        self.calls = []

    def fetch_many(self, requests, trade_date):
        self.calls.append(tuple(row.identity_key for row in requests))
        return MinuteContextFetchBatch({}, {}, (), (), ())


class FailedBatchPrimary:
    def fetch_many(self, requests, _trade_date):
        keys = tuple(row.identity_key for row in requests)
        return MinuteContextFetchBatch(
            {},
            {},
            keys,
            keys,
            ("stock:tq_batch_failed",),
        )


class Repository:
    def __init__(self, terminal=()):
        self.saved = []
        self.terminal = set(terminal)

    def begin_run(self, _model):
        return "context-1", False

    def terminal_identity_keys(self, _run, _kind):
        return set(self.terminal)

    def save_records(self, _run, _model, records):
        self.saved.extend(records)
        return len(records)

    def complete_run(self, _run, model):
        expected = {kind: len(getattr(model, kind)) for kind in ("stock", "index", "board")}
        counts = {kind: expected[kind] for kind in expected}
        status = {kind: ({"unavailable": expected[kind]} if expected[kind] else {}) for kind in expected}
        return PreviousDayContextPreloadSummary(
            "N3_PREVIOUS_DAY_CONTEXT_COMPLETE",
            "context-1",
            model.run_id,
            model.source_trade_date,
            model.for_trade_date,
            expected,
            counts,
            status,
            0,
        )


class LoaderCursor:
    def __init__(self):
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _params):
        if "FROM common_n3_previous_day_context_run" in query:
            self.rows = [("context-1", "wrong-run", "20260827", "20260828")]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None


class LoaderConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return LoaderCursor()


class WindowsN3PreviousDayContextTest(unittest.TestCase):
    def test_preload_summary_serializes_mapping_proxies_as_json_objects(self):
        summary = PreviousDayContextPreloadSummary(
            result="N3_PREVIOUS_DAY_CONTEXT_COMPLETE",
            context_run_id="context-1",
            source_condition_run_id="condition-1",
            source_trade_date="20260828",
            for_trade_date="20260831",
            expected_counts=MappingProxyType({"stock": 1}),
            terminal_counts=MappingProxyType({"stock": 1}),
            status_counts=MappingProxyType(
                {"stock": MappingProxyType({"ready": 1})}
            ),
            inserted_count=1,
        )
        payload = summary_to_dict(summary)
        self.assertEqual(payload["expected_counts"], {"stock": 1})
        self.assertEqual(payload["status_counts"], {"stock": {"ready": 1}})
        json.dumps(payload)

    def test_unavailable_tq_marks_every_identity_for_eltdx(self):
        requested = (request(0), request(1))
        primary = UnavailableTQMinuteContextProvider(
            ModuleNotFoundError("tqcenter")
        ).fetch_many(requested, "20260827")
        self.assertEqual(
            primary.missing_identity_keys,
            tuple(row.identity_key for row in requested),
        )
        self.assertEqual(
            primary.failed_batch_identity_keys,
            tuple(row.identity_key for row in requested),
        )

        eltdx = EltdxProvider()
        result = TQWithEltdxMinuteContextProvider(
            UnavailableTQMinuteContextProvider("not installed"),
            eltdx,
        ).fetch_many(requested, "20260827")
        self.assertEqual(
            eltdx.calls,
            [tuple(row.identity_key for row in requested)],
        )
        self.assertEqual(result.missing_identity_keys, ())

    def test_tq_uses_500_object_outer_batches_and_exact_options(self):
        client = TQClient()
        provider = TQStockMinuteContextProvider(client, sleep=lambda _value: None)
        result = provider.fetch_many(tuple(request(i) for i in range(1201)), "20260827")
        self.assertEqual(
            [len(call["stock_list"]) for call in client.calls],
            [500, 500, 500, 500, 500, 500, 201, 201, 201],
        )
        self.assertEqual(len(result.contexts), 1201)
        self.assertEqual(len(result.missing_identity_keys), 1201)
        self.assertTrue(all(call["period"] == "1m" for call in client.calls))
        self.assertTrue(all(call["fill_data"] is False for call in client.calls))
        self.assertTrue(all(call["dividend_type"] == "none" for call in client.calls))

    def test_tq_retries_with_30_and_120_second_delays(self):
        delays = []
        client = TQClient(fail=True)
        provider = TQStockMinuteContextProvider(client, sleep=delays.append)
        result = provider.fetch_many((request(0),), "20260827")
        self.assertEqual(delays, [30.0, 120.0])
        self.assertEqual(result.failed_batch_identity_keys, (request(0).identity_key,))

    def test_tq_field_matrix_with_code_columns_is_normalized(self):
        provider = TQStockMinuteContextProvider(
            MatrixTQClient(),
            sleep=lambda _value: None,
        )
        result = provider.fetch_many((request(0),), "20260827")
        self.assertEqual(len(result.contexts[request(0).identity_key].bars), 240)

    def test_eltdx_receives_only_missing_identity_from_successful_tq_batch(self):
        missing = request(1)
        client = TQClient(missing=(f"{missing.code}.SH",))
        eltdx = EltdxProvider()
        hybrid = TQWithEltdxMinuteContextProvider(
            TQStockMinuteContextProvider(client, sleep=lambda _value: None),
            eltdx,
        )
        result = hybrid.fetch_many((request(0), missing), "20260827")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(eltdx.calls, [(missing.identity_key,)])
        self.assertEqual(set(result.contexts), {request(0).identity_key, missing.identity_key})

    def test_whole_failed_tq_batch_is_replayed_through_eltdx(self):
        eltdx = EltdxProvider()
        hybrid = TQWithEltdxMinuteContextProvider(
            TQStockMinuteContextProvider(TQClient(fail=True), sleep=lambda _value: None),
            eltdx,
        )
        result = hybrid.fetch_many((request(0), request(1)), "20260827")
        self.assertEqual(
            eltdx.calls,
            [(request(0).identity_key, request(1).identity_key)],
        )
        self.assertEqual(result.missing_identity_keys, ())

    def test_complete_tq_context_does_not_call_eltdx(self):
        identity = request(0)
        eltdx = EltdxProvider({identity.identity_key: 240})
        result = TQWithEltdxMinuteContextProvider(
            FixedPrimary({identity.identity_key: 240}),
            eltdx,
        ).fetch_many((identity,), "20260827", require_complete=True)
        self.assertEqual(eltdx.calls, [])
        self.assertEqual(len(result.contexts[identity.identity_key].bars), 240)

    def test_partial_tq_uses_longer_complete_eltdx_without_merging(self):
        identity = request(0)
        result = TQWithEltdxMinuteContextProvider(
            FixedPrimary({identity.identity_key: 180}),
            EltdxProvider({identity.identity_key: 240}),
        ).fetch_many((identity,), "20260827", require_complete=True)
        self.assertEqual(len(result.contexts[identity.identity_key].bars), 240)

    def test_two_partial_sources_choose_longer_eltdx_without_merging(self):
        identity = request(0)
        result = TQWithEltdxMinuteContextProvider(
            FixedPrimary({identity.identity_key: 180}),
            EltdxProvider({identity.identity_key: 200}),
        ).fetch_many((identity,), "20260827", require_complete=True)
        self.assertEqual(len(result.contexts[identity.identity_key].bars), 200)
        self.assertEqual(result.missing_identity_keys, (identity.identity_key,))

    def test_equal_partial_sources_prefer_tq(self):
        identity = request(0)
        result = TQWithEltdxMinuteContextProvider(
            FixedPrimary({identity.identity_key: 180}),
            EltdxProvider({identity.identity_key: 180}),
        ).fetch_many((identity,), "20260827", require_complete=True)
        self.assertEqual(
            result.contexts[identity.identity_key].full_day_amount,
            minute_context(identity.identity_key, "20260827", 180).full_day_amount,
        )

    def test_preloader_persists_selected_provider_and_both_source_counts(self):
        identity = request(0)
        row = N2ObjectRuntimeInput(
            "stock",
            identity.identity_key,
            "SH",
            identity.code,
            identity.name,
            {},
            "20260827",
        )
        repository = Repository()
        WindowsN3PreviousDayContextPreloader(
            repository=repository,
            tq_stock=FixedPrimary({identity.identity_key: 180}),
            tq_index=FixedPrimary({}),
            tq_board=FixedPrimary({}),
            eltdx_stock=EltdxProvider({identity.identity_key: 200}),
            eltdx_index=EltdxProvider(),
            eltdx_board=EltdxProvider(),
        ).execute(
            N3ActiveReadModel(
                "condition-1",
                "20260827",
                "20260828",
                (row,),
                (),
                (),
            )
        )
        record = repository.saved[0]
        self.assertEqual(record.provider, "eltdx.test")
        self.assertEqual(record.status, "partial")
        self.assertEqual(record.minute_count, 200)
        self.assertEqual(record.tq_minute_count, 180)
        self.assertEqual(record.eltdx_minute_count, 200)

    def test_preloader_records_failed_when_both_sources_are_empty(self):
        identity = request(0)
        row = N2ObjectRuntimeInput(
            "stock",
            identity.identity_key,
            "SH",
            identity.code,
            identity.name,
            {},
            "20260827",
        )
        repository = Repository()
        WindowsN3PreviousDayContextPreloader(
            repository=repository,
            tq_stock=FixedPrimary({}),
            tq_index=FixedPrimary({}),
            tq_board=FixedPrimary({}),
            eltdx_stock=EltdxProvider({identity.identity_key: 0}),
            eltdx_index=EltdxProvider(),
            eltdx_board=EltdxProvider(),
        ).execute(
            N3ActiveReadModel(
                "condition-1",
                "20260827",
                "20260828",
                (row,),
                (),
                (),
            )
        )
        record = repository.saved[0]
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.minute_count, 0)
        self.assertEqual(record.tq_minute_count, 0)
        self.assertEqual(record.eltdx_minute_count, 0)

    def test_preloader_eltdx_takes_over_whole_failed_tq_batch(self):
        identity = request(0)
        row = N2ObjectRuntimeInput(
            "stock",
            identity.identity_key,
            "SH",
            identity.code,
            identity.name,
            {},
            "20260827",
        )
        repository = Repository()
        WindowsN3PreviousDayContextPreloader(
            repository=repository,
            tq_stock=FailedBatchPrimary(),
            tq_index=FixedPrimary({}),
            tq_board=FixedPrimary({}),
            eltdx_stock=EltdxProvider({identity.identity_key: 240}),
            eltdx_index=EltdxProvider(),
            eltdx_board=EltdxProvider(),
        ).execute(
            N3ActiveReadModel(
                "condition-1",
                "20260827",
                "20260828",
                (row,),
                (),
                (),
            )
        )
        record = repository.saved[0]
        self.assertEqual(record.status, "ready")
        self.assertEqual(record.provider, "eltdx.test")
        self.assertIn("tq=[batch_failed]", record.error_summary)

    def test_stale_n2_basis_skips_all_minute_providers(self):
        row = N2ObjectRuntimeInput(
            "stock",
            request(0).identity_key,
            "SH",
            request(0).code,
            "停牌股",
            {},
            "20260101",
        )
        model = N3ActiveReadModel(
            "condition-1",
            "20260827",
            "20260828",
            (row,),
            (),
            (),
        )
        primary = EmptyPrimary()
        repository = Repository()
        summary = WindowsN3PreviousDayContextPreloader(
            repository=repository,
            tq_stock=primary,
            tq_index=primary,
            tq_board=primary,
            eltdx_stock=EltdxProvider(),
            eltdx_index=EltdxProvider(),
            eltdx_board=EltdxProvider(),
        ).execute(model)
        self.assertEqual(primary.calls[0], ())
        self.assertEqual(repository.saved[0].status, "unavailable")
        self.assertEqual(summary.inserted_count, 1)

    def test_resume_skips_existing_terminal_identity(self):
        first = request(0)
        second = request(1)
        rows = tuple(
            N2ObjectRuntimeInput(
                "stock",
                item.identity_key,
                "SH",
                item.code,
                item.name,
                {},
                "20260101",
            )
            for item in (first, second)
        )
        model = N3ActiveReadModel(
            "condition-1", "20260827", "20260828", rows, (), ()
        )
        repository = Repository(terminal=(first.identity_key,))
        primary = EmptyPrimary()
        WindowsN3PreviousDayContextPreloader(
            repository=repository,
            tq_stock=primary,
            tq_index=primary,
            tq_board=primary,
            eltdx_stock=EltdxProvider(),
            eltdx_index=EltdxProvider(),
            eltdx_board=EltdxProvider(),
        ).execute(model)
        self.assertEqual(
            tuple(row.identity_key for row in repository.saved),
            (second.identity_key,),
        )

    def test_ready_context_has_240_points_eight_windows_and_stable_sha(self):
        row = N2ObjectRuntimeInput(
            "stock", request(0).identity_key, "SH", request(0).code, "浦发", {}, "20260827"
        )
        record = make_context_record(
            row,
            provider="tq",
            status="ready",
            context=minute_context(row.identity_key, "20260827"),
            error_summary=None,
            tq_minute_count=180,
            eltdx_minute_count=240,
        )
        self.assertEqual(record.minute_count, 240)
        self.assertEqual(len(record.cumulative_amounts), 240)
        self.assertEqual(len(record.windows), 8)
        self.assertEqual(record.tq_minute_count, 180)
        self.assertEqual(record.eltdx_minute_count, 240)
        self.assertEqual(record.content_sha256, context_record_sha256(record))

    def test_database_loader_rejects_mismatched_n2_lineage(self):
        model = N3ActiveReadModel(
            "condition-1", "20260827", "20260828", (), (), ()
        )
        loader = PostgresPreviousDayContextLoader(
            "postgresql://example",
            connect=lambda _dsn: LoaderConnection(),
        )
        with self.assertRaisesRegex(RuntimeError, "lineage mismatch"):
            loader.load(model)

    def test_schema_is_compressed_context_only(self):
        root = Path(__file__).parents[1]
        schema = (root / "sql/040_windows_n3_previous_day_context_schema.sql").read_text()
        for table in (
            "common_n3_previous_day_context_run",
            "stock_n3_previous_day_context",
            "index_n3_previous_day_context",
            "board_n3_previous_day_context",
        ):
            self.assertIn(f"CREATE TABLE {table}", schema)
        self.assertNotIn("minute_bar_1m", schema)
        self.assertNotIn("runtime_state", schema)
        self.assertEqual(schema.count("tq_minute_count INTEGER"), 3)
        self.assertEqual(schema.count("eltdx_minute_count INTEGER"), 3)
        self.assertIn("TO ashare_v3_user", schema)
        self.assertNotIn("GRANT DELETE", schema)

    def test_intraday_path_has_no_full_market_minute_pull_or_boundary_refresh(self):
        root = Path(__file__).parents[1]
        source = (root / "src/ashare_v3/market/windows_n3_intraday.py").read_text()
        self.assertNotIn("bars.get", source)
        self.assertNotIn("refresh_current_day", source)
        self.assertIn("context_loader.load(model)", source)

    def test_postclose_eltdx_uses_one_shared_pool_size_16_client(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts/run_windows_n3_previous_day_context.py").read_text()
        minute_source = (
            root / "src/ashare_v3/market/windows_n3_minute_context.py"
        ).read_text()
        self.assertEqual(script.count("TdxClient.from_hosts("), 1)
        self.assertIn("pool_size=16", script)
        self.assertNotIn("threading.local", minute_source)


if __name__ == "__main__":
    unittest.main()
