from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    EltdxBoardSnapshotProvider,
    EltdxStockSnapshotProvider,
    RealtimeQuote,
    StockSnapshotBatch,
    StockSnapshotProviderChain,
    StockSnapshotRequest,
    TQBoardSnapshotProvider,
)


NOW = datetime(2026, 8, 28, 9, 35, tzinfo=timezone.utc)


class FakeEltdx:
    def __init__(self):
        self.quotes = self
        self.calls = []

    def get_snapshots(self, codes):
        self.calls.append(tuple(codes))
        return [
            SimpleNamespace(
                full_code=code,
                last_price="10.5",
                open_price="10",
                high_price="11",
                low_price="9.8",
                prev_close="9.9",
                volume="100",
                amount="12345",
            )
            for code in codes
        ]


class FakeTQ:
    def __init__(self):
        self.calls = []

    def get_market_snapshot(self, code):
        self.calls.append(code)
        return {
            "Now": 3380.86,
            "Open": 3300,
            "High": 3400,
            "Low": 3290,
            "LastClose": 3280,
            "Volume": 100,
            "Amount": 121390000000,
        }


def quote(identity_key):
    return RealtimeQuote(
        asset_kind="stock",
        identity_key=identity_key,
        exchange="SH",
        code=identity_key.rsplit(":", 1)[-1],
        name=identity_key,
        current_price=None,
        open=None,
        high=None,
        low=None,
        pre_close=None,
        volume=None,
        amount=None,
        source_time=NOW,
        observed_at=NOW,
        provider="fake",
    )


class WindowsN3SnapshotProviderTest(unittest.TestCase):
    def test_eltdx_stock_provider_batches_at_80_and_normalizes_amount(self):
        client = FakeEltdx()
        provider = EltdxStockSnapshotProvider(client, max_workers=1, clock=lambda: NOW)
        requests = tuple(
            StockSnapshotRequest(f"stock:SH:{index:06d}", "SH", f"{index:06d}", str(index))
            for index in range(161)
        )
        batch = provider.fetch_many(requests)
        self.assertEqual([len(codes) for codes in client.calls], [80, 80, 1])
        self.assertEqual(len(batch.rows), 161)
        self.assertEqual(str(batch.rows[0].current_price), "10.5")
        self.assertEqual(str(batch.rows[0].amount), "12345")
        self.assertEqual(batch.missing_identity_keys, ())

    def test_board_provider_owns_sh88_code_translation_for_eltdx_and_tq(self):
        request = BoardSnapshotRequest("board:TDX:881333", "SH", "881333", "元器件")
        eltdx = FakeEltdx()
        eltdx_batch = EltdxBoardSnapshotProvider(eltdx, max_workers=1, clock=lambda: NOW).fetch_many((request,))
        self.assertEqual(eltdx.calls, [("sh881333",)])
        self.assertEqual(eltdx_batch.rows[0].identity_key, request.identity_key)

        tq = FakeTQ()
        tq_batch = TQBoardSnapshotProvider(tq, max_workers=1, clock=lambda: NOW).fetch_many((request,))
        self.assertEqual(tq.calls, ["881333.SH"])
        self.assertEqual(str(tq_batch.rows[0].amount), "121390000000")

    def test_stock_fallback_only_receives_primary_missing_requests(self):
        requests = (
            StockSnapshotRequest("stock:SH:600000", "SH", "600000", "浦发"),
            StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安"),
        )

        class Primary:
            def fetch_many(self, received):
                self.received = tuple(received)
                return StockSnapshotBatch((quote(received[0].identity_key),), (received[1].identity_key,), "primary", NOW)

        class Fallback:
            def fetch_many(self, received):
                self.received = tuple(received)
                return StockSnapshotBatch((quote(received[0].identity_key),), (), "fallback", NOW)

        primary = Primary()
        fallback = Fallback()
        batch = StockSnapshotProviderChain(primary, fallback).fetch_many(requests)
        self.assertEqual(primary.received, requests)
        self.assertEqual(fallback.received, (requests[1],))
        self.assertEqual([row.identity_key for row in batch.rows], [request.identity_key for request in requests])
        self.assertEqual(batch.provider, "primary+fallback")


if __name__ == "__main__":
    unittest.main()
