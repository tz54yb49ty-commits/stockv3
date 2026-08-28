from __future__ import annotations

from decimal import Decimal
import unittest

from ashare_v3.market.windows_n3_read_model import (
    ActiveN2RunUnavailable,
    WindowsN3ReadOnlyRepository,
)


def baseline():
    return {
        "periods": {
            period: {
                "trigger_previous_entity_high": "12",
                "trigger_previous_entity_low": "10",
                "trigger_previous_amount_baseline": "100",
                "current_amount_total_seed": "600",
                "current_trade_days_seed": 3,
            }
            for period in ("Y", "Q", "M", "W", "D")
        }
    }


def basis_row(asset_kind, identity_key, exchange, code, name):
    row = {
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "name": name,
        "basis_trade_date": "20260826",
        "period_trigger_baseline_json": baseline(),
    }
    for period in ("y", "q", "m", "w", "d"):
        row[f"period_grade_{period}"] = "volume_up"
        row[f"period_transition_{period}"] = "flat->volume_up"
    return row


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        normalized = " ".join(query.split())
        self.connection.queries.append((normalized, params))
        if "FROM common_trade_calendar" in normalized:
            self.rows = [{"is_open": self.connection.is_open}]
        elif "FROM common_condition_run" in normalized:
            self.rows = list(self.connection.run_rows)
        elif "FROM stock_condition_basis" in normalized:
            self.rows = list(self.connection.stock_rows)
        elif "FROM index_condition_basis" in normalized:
            self.rows = list(self.connection.index_rows)
        elif "FROM board_condition_basis" in normalized:
            self.rows = list(self.connection.board_rows)
        else:
            raise AssertionError(normalized)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self):
        self.is_open = True
        self.run_rows = [{"run_id": "condition-1", "source_trade_date": "20260827", "for_trade_date": "20260828"}]
        self.stock_rows = [basis_row("stock", "stock:SH:600000", "SH", "600000", "浦发")]
        self.index_rows = [basis_row("index", "index:SH:000001", "SH", "000001", "上证")]
        self.board_rows = [basis_row("board", "board:TDX:881333", "SH", "881333", "元器件")]
        self.queries = []
        self.closed = False

    def cursor(self):
        return Cursor(self)

    def close(self):
        self.closed = True


class WindowsN3ReadModelTest(unittest.TestCase):
    def test_loads_full_three_channel_n2_basis_without_scope_filter(self):
        connections = []

        def connect(_dsn):
            value = Connection()
            connections.append(value)
            return value

        repository = WindowsN3ReadOnlyRepository("postgresql://example", connect=connect)
        model = repository.load_active("20260828")
        self.assertEqual(model.run_id, "condition-1")
        self.assertEqual(model.source_trade_date, "20260827")
        self.assertEqual(model.stock_requests()[0].identity_key, "stock:SH:600000")
        self.assertEqual(model.index_requests()[0].identity_key, "index:SH:000001")
        self.assertEqual(model.board_requests()[0].identity_key, "board:TDX:881333")
        self.assertEqual(model.higher_amount_baselines("stock")["stock:SH:600000"]["W"].completed_amount_sum, Decimal("600"))
        self.assertEqual(model.stock[0].periods["D"].previous_entity_high, Decimal("12"))
        self.assertEqual(model.stock[0].basis_trade_date, "20260826")
        queries = [query for query, _params in connections[0].queries]
        self.assertTrue(all(query.startswith("SELECT") for query in queries))
        self.assertTrue(all("minute_target_scope" not in query for query in queries))
        self.assertTrue(connections[0].closed)

    def test_missing_active_run_fails_closed(self):
        connection = Connection()
        connection.run_rows = []
        repository = WindowsN3ReadOnlyRepository("postgresql://example", connect=lambda _dsn: connection)
        with self.assertRaises(ActiveN2RunUnavailable):
            repository.load_active("20260828")
        self.assertTrue(connection.closed)

    def test_conflicting_active_runs_fail_closed(self):
        connection = Connection()
        connection.run_rows.append(
            {"run_id": "condition-2", "source_trade_date": "20260826", "for_trade_date": "20260828"}
        )
        repository = WindowsN3ReadOnlyRepository("postgresql://example", connect=lambda _dsn: connection)
        with self.assertRaisesRegex(ActiveN2RunUnavailable, "conflicting"):
            repository.load_active("20260828")
        self.assertTrue(connection.closed)

    def test_trade_calendar_check_is_read_only(self):
        connection = Connection()
        connection.is_open = False
        repository = WindowsN3ReadOnlyRepository("postgresql://example", connect=lambda _dsn: connection)
        self.assertFalse(repository.is_open_trade_date("20260829"))
        self.assertEqual(len(connection.queries), 1)
        self.assertTrue(connection.queries[0][0].startswith("SELECT"))


if __name__ == "__main__":
    unittest.main()
