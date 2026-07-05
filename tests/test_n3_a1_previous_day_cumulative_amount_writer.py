import unittest

from ashare_v3.market.previous_day_cumulative_amount_writer import (
    A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS,
    A1CumulativeAmountWriterBlocked,
    build_previous_day_cumulative_amount_rollback_sql,
    build_previous_day_cumulative_amount_write_plan,
    fetch_existing_cumulative_target_summary,
    write_previous_day_cumulative_amount_rows,
)


def canonical_trade_minute_labels(trade_date: str) -> list[str]:
    labels: list[str] = []
    for hour, minute_start, minute_end in (
        (9, 31, 59),
        (10, 0, 59),
        (11, 0, 29),
        (13, 0, 59),
        (14, 0, 59),
        (15, 0, 0),
    ):
        for minute in range(minute_start, minute_end + 1):
            labels.append(f"{trade_date} {hour:02d}:{minute:02d}")
    return labels


def raw_rows(asset_kind: str, identity_key: str, code: str, *, amount: float = 10.0) -> list[dict]:
    exchange = identity_key.split(":")[1] if ":" in identity_key else ""
    return [
        {
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": exchange,
            "code": code,
            "bar_time": label,
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "amount": amount,
        }
        for label in canonical_trade_minute_labels("2026-06-26")
    ]


class RecordingCursor:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []
        self.executemany_calls: list[tuple[str, list[tuple]]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.execute_calls.append((" ".join(sql.split()), tuple(params)))

    def executemany(self, sql: str, params_seq) -> None:
        self.executemany_calls.append((" ".join(sql.split()), list(params_seq)))


class TupleFetchCursor(RecordingCursor):
    def __init__(self, rows_by_call: list[list[tuple]]) -> None:
        super().__init__()
        self._rows_by_call = rows_by_call
        self._fetch_index = -1

    def execute(self, sql: str, params: tuple = ()) -> None:
        super().execute(sql, params)
        self._fetch_index += 1

    def fetchall(self) -> list[tuple]:
        return self._rows_by_call[self._fetch_index]


class N3A1PreviousDayCumulativeAmountWriterTest(unittest.TestCase):
    def _source_rows(self) -> dict[str, list[dict]]:
        return {
            "stock": raw_rows("stock", "stock:SH:600000", "600000"),
            "index": raw_rows("index", "index:SH:000001", "000001"),
            "board": raw_rows("board", "board:TDX:881001", "881001"),
        }

    def test_writer_inserts_physical_cumulative_tables_without_event_sql(self) -> None:
        cursor = RecordingCursor()

        report = write_previous_day_cumulative_amount_rows(
            cursor,
            self._source_rows(),
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
            existing_target_summary={
                "stock": {"row_count": 0, "row_hash": ""},
                "index": {"row_count": 0, "row_hash": ""},
                "board": {"row_count": 0, "row_hash": ""},
            },
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["write_action"], "inserted")
        self.assertEqual(report["inserted_row_count_by_asset"], {"stock": 240, "index": 240, "board": 240})
        sql = "\n".join(call[0] for call in cursor.executemany_calls)
        self.assertIn("INSERT INTO stock_previous_day_minute_cumulative", sql)
        self.assertIn("INSERT INTO index_previous_day_minute_cumulative", sql)
        self.assertIn("INSERT INTO board_previous_day_minute_cumulative", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)
        self.assertNotIn("common_event_consumer_checkpoint", sql)
        stock_params = cursor.executemany_calls[0][1]
        self.assertEqual(len(stock_params), 240)
        self.assertIn("stock:SH:600000", stock_params[0])

    def test_writer_noops_when_existing_target_count_and_hash_match(self) -> None:
        plan = build_previous_day_cumulative_amount_write_plan(
            self._source_rows(),
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )
        cursor = RecordingCursor()

        report = write_previous_day_cumulative_amount_rows(
            cursor,
            self._source_rows(),
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
            existing_target_summary={
                asset_kind: {
                    "row_count": plan["expected_row_count_by_asset"][asset_kind],
                    "row_hash": plan["expected_row_hash_by_asset"][asset_kind],
                }
                for asset_kind in ("stock", "index", "board")
            },
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["write_action"], "idempotent_noop")
        self.assertEqual(cursor.executemany_calls, [])

    def test_existing_target_summary_accepts_tuple_rows_from_plain_cursor(self) -> None:
        plan = build_previous_day_cumulative_amount_write_plan(
            self._source_rows(),
            source_previous_day_minute_run_id="a1_run",
            for_trade_date="20260629",
            source_trade_date="20260626",
        )
        cursor_rows = [
            [
                tuple(row.get(column) for column in A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS)
                for row in plan["rows_by_asset"][asset_kind]
            ]
            for asset_kind in ("stock", "index", "board")
        ]
        cursor = TupleFetchCursor(cursor_rows)

        summary = fetch_existing_cumulative_target_summary(cursor, "a1_run")

        self.assertEqual(summary["stock"]["row_count"], 240)
        self.assertEqual(summary["stock"]["row_hash"], plan["expected_row_hash_by_asset"]["stock"])
        self.assertEqual(summary["index"]["row_hash"], plan["expected_row_hash_by_asset"]["index"])
        self.assertEqual(summary["board"]["row_hash"], plan["expected_row_hash_by_asset"]["board"])

    def test_writer_blocks_dirty_existing_target(self) -> None:
        with self.assertRaisesRegex(A1CumulativeAmountWriterBlocked, "BLOCKED_A1_CUMULATIVE_TARGET_DIRTY"):
            write_previous_day_cumulative_amount_rows(
                RecordingCursor(),
                self._source_rows(),
                source_previous_day_minute_run_id="a1_run",
                for_trade_date="20260629",
                source_trade_date="20260626",
                existing_target_summary={
                    "stock": {"row_count": 240, "row_hash": "different"},
                    "index": {"row_count": 0, "row_hash": ""},
                    "board": {"row_count": 0, "row_hash": ""},
                },
            )

    def test_writer_blocks_expected_object_count_mismatch(self) -> None:
        with self.assertRaisesRegex(A1CumulativeAmountWriterBlocked, "expected_object_count_mismatch"):
            write_previous_day_cumulative_amount_rows(
                RecordingCursor(),
                self._source_rows(),
                source_previous_day_minute_run_id="a1_run",
                for_trade_date="20260629",
                source_trade_date="20260626",
                expected_object_counts_by_asset={"stock": 2, "index": 1, "board": 1},
                existing_target_summary={
                    "stock": {"row_count": 0, "row_hash": ""},
                    "index": {"row_count": 0, "row_hash": ""},
                    "board": {"row_count": 0, "row_hash": ""},
                },
            )

    def test_writer_fail_closed_on_bad_source_rows(self) -> None:
        rows = self._source_rows()
        rows["stock"] = rows["stock"][:-1]
        with self.assertRaisesRegex(A1CumulativeAmountWriterBlocked, "previous_day_cumulative_full_window_incomplete"):
            write_previous_day_cumulative_amount_rows(
                RecordingCursor(),
                rows,
                source_previous_day_minute_run_id="a1_run",
                for_trade_date="20260629",
                source_trade_date="20260626",
                existing_target_summary={
                    "stock": {"row_count": 0, "row_hash": ""},
                    "index": {"row_count": 0, "row_hash": ""},
                    "board": {"row_count": 0, "row_hash": ""},
                },
            )

    def test_rollback_sql_is_scoped_to_cumulative_tables_only(self) -> None:
        sql = build_previous_day_cumulative_amount_rollback_sql("a1_run")

        self.assertIn("DELETE FROM stock_previous_day_minute_cumulative", sql)
        self.assertIn("DELETE FROM index_previous_day_minute_cumulative", sql)
        self.assertIn("DELETE FROM board_previous_day_minute_cumulative", sql)
        self.assertIn("source_previous_day_minute_run_id = 'a1_run'", sql)
        self.assertNotIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM stock_previous_day_minute_bar_1m", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)


if __name__ == "__main__":
    unittest.main()
