from __future__ import annotations

import unittest

from scripts.plan_runtime_disk_governance_retained_dates import (
    read_retained_trade_dates,
)


class FakeCursor:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[str, ...] = ()

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[str, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[str]]:
        return self.rows


class FakeConnection:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.cursor_value = FakeCursor(rows)
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


class RuntimeDiskGovernanceRetainedDatesTest(unittest.TestCase):
    def test_reads_exact_six_open_dates_with_read_only_connection(self) -> None:
        rows = [
            ("20260821",),
            ("20260820",),
            ("20260819",),
            ("20260818",),
            ("20260817",),
            ("20260814",),
        ]
        captured: dict[str, object] = {}

        def connection_factory(dsn: str, **kwargs: object) -> FakeConnection:
            captured.update({"dsn": dsn, **kwargs})
            connection = FakeConnection(rows)
            captured["connection"] = connection
            return connection

        result = read_retained_trade_dates(
            "postgresql://example",
            current_date="20260821",
            connection_factory=connection_factory,
        )

        self.assertEqual(result, [row[0] for row in rows])
        self.assertEqual(
            captured["options"], "-c default_transaction_read_only=on"
        )
        connection = captured["connection"]
        assert isinstance(connection, FakeConnection)
        self.assertIn("is_open IS TRUE", connection.cursor_value.query)
        self.assertIn("LIMIT 6", connection.cursor_value.query)
        self.assertEqual(connection.cursor_value.params, ("20260821",))
        self.assertTrue(connection.closed)

    def test_rejects_invalid_current_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYYMMDD"):
            read_retained_trade_dates(
                "postgresql://example",
                current_date="2026-08-21",
                connection_factory=lambda *_args, **_kwargs: None,
            )

    def test_requires_six_calendar_rows(self) -> None:
        connection = FakeConnection([("20260821",)])
        with self.assertRaisesRegex(RuntimeError, "five predecessors"):
            read_retained_trade_dates(
                "postgresql://example",
                current_date="20260821",
                connection_factory=lambda *_args, **_kwargs: connection,
            )
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
