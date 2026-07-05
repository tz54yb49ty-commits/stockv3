import unittest

from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient="records"):
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return list(self._rows)


class FakeMootdxClient:
    def __init__(self):
        self.index_calls = []

    def index(self, **kwargs):
        self.index_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "datetime": "2026-05-20 00:00:00",
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "2",
                    "vol": "10",
                    "amount": "20",
                },
                {
                    "datetime": "2026-05-21 00:00:00",
                    "open": "3",
                    "high": "4",
                    "low": "3",
                    "close": "4",
                    "vol": "30",
                    "amount": "40",
                },
            ]
        )


class MootdxDailySourceTest(unittest.TestCase):
    def test_fetch_index_and_board_daily_bars_enriches_and_filters_rows(self) -> None:
        client = FakeMootdxClient()
        source = MootdxDailyBarSource(client=client, frequency=9, offset=800)

        index_rows = source.fetch_index_daily_bars(
            indexes=[IndexDailySymbol(code="000001", exchange="SH", name="上证指数")],
            start_date="20260521",
            end_date="20260521",
        )
        board_rows = source.fetch_board_daily_bars(
            boards=[BoardDailySymbol(board_code="881002", board_name="煤炭开采", board_type="tdx_industry")],
            start_date="20260521",
            end_date="20260521",
        )

        self.assertEqual(len(index_rows), 1)
        self.assertEqual(len(board_rows), 1)
        self.assertEqual(index_rows[0]["code"], "000001")
        self.assertEqual(index_rows[0]["exchange"], "SH")
        self.assertEqual(board_rows[0]["board_code"], "881002")
        self.assertEqual(board_rows[0]["board_type"], "tdx_industry")
        self.assertEqual([call["symbol"] for call in client.index_calls], ["000001", "881002"])
        self.assertEqual(client.index_calls[0]["frequency"], 9)


if __name__ == "__main__":
    unittest.main()
