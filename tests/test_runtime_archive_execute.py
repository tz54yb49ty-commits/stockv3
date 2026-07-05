import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from ashare_v3.ingestion.runtime_archive_execute import (
    RuntimeArchiveQuerySpec,
    build_runtime_archive_query_specs,
    execute_runtime_archive,
    runtime_table_specs,
    should_partition_table,
    write_runtime_archive_frames,
)


CLOSED_30M_TABLES = {
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
}
EOD_SNAPSHOT_TABLES = {
    "stock_eod_snapshot",
    "index_eod_snapshot",
    "board_eod_snapshot",
}
EOD_RECONCILIATION_ITEM_TABLES = {
    "stock_eod_reconciliation_item",
    "index_eod_reconciliation_item",
    "board_eod_reconciliation_item",
}
PROJECTION_ENRICHMENT_V4_TABLES = {
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
}
REALTIME_HINT_PROJECTION_METRIC_TABLES = {
    "index_realtime_hint_projection_metric",
    "board_realtime_hint_projection_metric",
}


class RuntimeArchiveExecuteTest(unittest.TestCase):
    def test_query_specs_cover_runtime_layers_and_event_infra(self) -> None:
        specs = build_runtime_archive_query_specs("20260612")
        by_key = {(spec.layer, spec.table): spec for spec in specs}

        self.assertIn(("n3", "stock_minute_bar_1m"), by_key)
        self.assertIn(("n3", "stock_previous_day_minute_preload_status"), by_key)
        self.assertIn(("n3", "index_previous_day_minute_preload_status"), by_key)
        self.assertIn(("n3", "board_previous_day_minute_preload_status"), by_key)
        self.assertIn(("n4", "common_trigger_match"), by_key)
        self.assertIn(("n5", "common_action_event"), by_key)
        self.assertIn(("n6", "user_signal_projection"), by_key)
        self.assertIn(("n4", "common_event_outbox"), by_key)
        self.assertIn(("n4", "common_event_inbox"), by_key)
        self.assertIn(("n4", "common_event_consumer_checkpoint"), by_key)
        self.assertIn("trade_date", by_key[("n3", "stock_minute_bar_1m")].sql)
        self.assertIn("for_trade_date", by_key[("n3", "stock_previous_day_minute_preload_status")].sql)
        self.assertIn("exists (select 1 from common_event_outbox", by_key[("n4", "common_event_inbox")].sql)
        self.assertEqual(by_key[("n5", "common_action_event")].params, ("20260612",))

    def test_runtime_table_specs_include_closed_30m_n3_tables(self) -> None:
        by_table = {table: (layer, date_column) for layer, table, date_column in runtime_table_specs()}

        for table in CLOSED_30M_TABLES:
            self.assertEqual(by_table[table], ("n3", "trade_date"))

    def test_runtime_table_specs_include_eod_snapshot_n3_tables(self) -> None:
        by_table = {table: (layer, date_column) for layer, table, date_column in runtime_table_specs()}

        for table in EOD_SNAPSHOT_TABLES:
            self.assertEqual(by_table[table], ("n3", "trade_date"))

    def test_runtime_table_specs_include_projection_enrichment_v4_n3_tables(self) -> None:
        by_table = {table: (layer, date_column) for layer, table, date_column in runtime_table_specs()}

        for table in PROJECTION_ENRICHMENT_V4_TABLES:
            self.assertEqual(by_table[table], ("n3", "trade_date"))

    def test_runtime_table_specs_include_realtime_hint_projection_metric_n3_tables(self) -> None:
        by_table = {table: (layer, date_column) for layer, table, date_column in runtime_table_specs()}

        for table in REALTIME_HINT_PROJECTION_METRIC_TABLES:
            self.assertEqual(by_table[table], ("n3", "trade_date"))

    def test_query_specs_include_eod_reconciliation_items_scoped_by_parent_snapshot_date(self) -> None:
        specs = build_runtime_archive_query_specs("20260612")
        by_table = {spec.table: spec for spec in specs if spec.layer == "n3"}

        for table in EOD_RECONCILIATION_ITEM_TABLES:
            spec = by_table[table]
            asset = table.removesuffix("_eod_reconciliation_item")
            parent_table = f"{asset}_eod_snapshot"
            self.assertEqual(spec.params, ("20260612",))
            self.assertIn(f"from {table}", spec.sql.lower())
            self.assertIn(f"join {parent_table}", spec.sql.lower())
            self.assertIn("parent.trade_date = %s", spec.sql.lower())

    def test_large_runtime_tables_are_partitioned_for_archive(self) -> None:
        self.assertTrue(should_partition_table(layer="n3", table="stock_minute_bar_1m"))
        self.assertTrue(should_partition_table(layer="n3", table="stock_action_confirmation_projection_metric"))
        self.assertTrue(should_partition_table(layer="n4", table="common_trigger_state"))
        self.assertFalse(should_partition_table(layer="n3", table="common_market_data_run"))

    def test_write_runtime_archive_frames_writes_manifest_and_verified_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_runtime_archive_frames(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                frames={
                    ("n3", "stock_minute_bar_1m"): pd.DataFrame(
                        [{"trade_date": "20260612", "identity_key": "stock:SZ:000001", "raw_json": {"a": 1}}]
                    ),
                    ("n4", "common_trigger_match"): pd.DataFrame(
                        [{"for_trade_date": "20260612", "identity_key": "stock:SZ:000001"}]
                    ),
                },
            )

            manifest_path = Path(result["manifest_path"])
            report_path = Path(result["report_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(manifest_path.exists())
            self.assertTrue(report_path.exists())
            self.assertEqual(manifest["trade_date"], "20260612")
            self.assertEqual(manifest["file_count"], 2)
            self.assertEqual(manifest["total_rows"], 2)
            for file in manifest["files"]:
                self.assertTrue(Path(file["path"]).exists())
                self.assertRegex(file["checksum"], r"^sha256:[a-f0-9]{64}$")
                self.assertEqual(file["verified_row_count"], file["row_count"])
            self.assertFalse(manifest["side_effects"]["writes_database"])
            self.assertTrue(manifest["side_effects"]["writes_archive_files"])
            self.assertFalse(manifest["side_effects"]["cleanup_local_runtime"])

    def test_execute_runtime_archive_skips_existing_verified_manifest(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_minute_bar_1m",
                sql="select 1",
                params=(),
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = (
                Path(tmp)
                / "v3_runtime"
                / "trade_date=20260612"
                / "manifests"
                / "archive_manifest.json"
            )
            report_path = (
                Path(tmp)
                / "v3_runtime"
                / "trade_date=20260612"
                / "reports"
                / "archive_report.json"
            )
            manifest_path.parent.mkdir(parents=True)
            report_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_version": "v3-runtime-archive.v1",
                        "result": "ARCHIVED_VERIFIED",
                        "trade_date": "20260612",
                        "manifest_path": str(manifest_path),
                        "report_path": str(report_path),
                        "row_count_match": True,
                        "checksum_algorithm": "sha256",
                        "cleanup_eligible": False,
                        "cleanup_blockers": ["manual_cleanup_required"],
                        "file_count": 1,
                        "total_rows": 7,
                        "files": [
                            {
                                "layer": "n3",
                                "table": "stock_minute_bar_1m",
                                "row_count": 7,
                                "verified_row_count": 7,
                                "checksum": "sha256:" + "0" * 64,
                                "path": "unused",
                                "format": "parquet",
                            }
                        ],
                        "side_effects": {
                            "writes_database": False,
                            "writes_archive_files": True,
                            "cleanup_local_runtime": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(*args, **kwargs):
                raise AssertionError("archive should not query DB when manifest is verified")

            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=fail_if_called,
                query_specs=specs,
            )

            self.assertEqual(result["result"], "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED")
            self.assertEqual(result["manifest_path"], str(manifest_path))
            self.assertEqual(result["total_rows"], 7)
            self.assertFalse(result["side_effects"]["writes_archive_files"])
            self.assertFalse(result["side_effects"]["writes_database"])
            self.assertFalse(result["side_effects"]["cleanup_local_runtime"])

    def test_execute_runtime_archive_refreshes_verified_manifest_missing_required_table(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_minute_bar_1m",
                sql="select 1",
                params=(),
            ),
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_closed_30m_summary",
                sql="select 2",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = (
                Path(tmp)
                / "v3_runtime"
                / "trade_date=20260612"
                / "manifests"
                / "archive_manifest.json"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "result": "ARCHIVED_VERIFIED",
                        "row_count_match": True,
                        "checksum_algorithm": "sha256",
                        "cleanup_eligible": False,
                        "files": [
                            {
                                "layer": "n3",
                                "table": "stock_minute_bar_1m",
                                "row_count": 1,
                                "verified_row_count": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            reads: list[str] = []

            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                frame_reader=lambda _conn, spec: reads.append(spec.table)
                or pd.DataFrame([{"trade_date": "20260612"}]),
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(reads, ["stock_minute_bar_1m", "stock_closed_30m_summary"])

    def test_execute_runtime_archive_manifest_scope_uses_layer_and_table(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n4",
                table="common_event_outbox",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = (
                Path(tmp)
                / "v3_runtime"
                / "trade_date=20260612"
                / "manifests"
                / "archive_manifest.json"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "result": "ARCHIVED_VERIFIED",
                        "row_count_match": True,
                        "checksum_algorithm": "sha256",
                        "cleanup_eligible": False,
                        "files": [
                            {
                                "layer": "n3",
                                "table": "common_event_outbox",
                                "row_count": 1,
                                "verified_row_count": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            reads: list[tuple[str, str]] = []

            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                frame_reader=lambda _conn, spec: reads.append((spec.layer, spec.table))
                or pd.DataFrame([{"trade_date": "20260612"}]),
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(reads, [("n4", "common_event_outbox")])

    def test_execute_runtime_archive_does_not_skip_corrupt_manifest(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_minute_bar_1m",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = (
                Path(tmp)
                / "v3_runtime"
                / "trade_date=20260612"
                / "manifests"
                / "archive_manifest.json"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "result": "ARCHIVED_VERIFIED",
                        "row_count_match": False,
                        "checksum_algorithm": "sha256",
                        "cleanup_eligible": False,
                    }
                ),
                encoding="utf-8",
            )
            reads: list[str] = []

            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                frame_reader=lambda _conn, spec: reads.append(spec.table)
                or pd.DataFrame([{"trade_date": "20260612"}]),
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(reads, ["stock_minute_bar_1m"])

    def test_execute_runtime_archive_streams_one_spec_at_a_time(self) -> None:
        active_frames: list[str] = []
        max_active_frames = 0

        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_minute_bar_1m",
                sql="select * from stock_minute_bar_1m where trade_date = %s",
                params=("20260612",),
            ),
            RuntimeArchiveQuerySpec(
                layer="n4",
                table="common_trigger_match",
                sql="select * from common_trigger_match where for_trade_date = %s",
                params=("20260612",),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def connection_factory(_dsn):
            return FakeConnection()

        def frame_reader(_conn, spec):
            nonlocal max_active_frames
            active_frames.append(spec.table)
            max_active_frames = max(max_active_frames, len(active_frames))
            return pd.DataFrame([{"trade_date": "20260612", "table_name": spec.table}])

        def frame_writer(*, trade_date, archive_root, layer, table, frame):
            self.assertEqual(active_frames, [table])
            active_frames.pop()
            output_path = Path(archive_root) / f"trade_date={trade_date}" / layer / f"{table}.parquet"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(output_path, index=False)
            return {
                "layer": layer,
                "table": table,
                "row_count": int(len(frame)),
                "verified_row_count": int(len(pd.read_parquet(output_path))),
                "checksum": "sha256:" + "0" * 64,
                "path": str(output_path),
                "format": "parquet",
            }

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=connection_factory,
                query_specs=specs,
                frame_reader=frame_reader,
                frame_writer=frame_writer,
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(max_active_frames, 1)
            self.assertEqual(active_frames, [])

    def test_execute_runtime_archive_blocks_on_row_count_mismatch(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="common_market_data_run",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def frame_writer(*, trade_date, archive_root, layer, table, frame):
            output_path = Path(archive_root) / f"trade_date={trade_date}" / layer / f"{table}.parquet"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(output_path, index=False)
            return {
                "layer": layer,
                "table": table,
                "row_count": 1,
                "verified_row_count": 0,
                "checksum": "sha256:" + "0" * 64,
                "path": str(output_path),
                "format": "parquet",
            }

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                frame_reader=lambda _conn, _spec: pd.DataFrame([{"trade_date": "20260612"}]),
                frame_writer=frame_writer,
            )

            self.assertEqual(result["result"], "BLOCKED")
            self.assertFalse(result["row_count_match"])
            self.assertIn("manual_cleanup_required", result["cleanup_blockers"])
            self.assertFalse(result["cleanup_eligible"])

    def test_execute_runtime_archive_records_table_timing_for_success(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_minute_bar_1m",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=lambda _conn, _spec, _chunksize: iter(
                    [pd.DataFrame([{"trade_date": "20260612"}])]
                ),
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(len(result["table_timings"]), 1)
            timing = result["table_timings"][0]
            self.assertEqual(timing["layer"], "n3")
            self.assertEqual(timing["table"], "stock_minute_bar_1m")
            self.assertEqual(timing["status"], "passed")
            self.assertIsInstance(timing["read_duration_ms"], (int, float))
            self.assertIsInstance(timing["write_duration_ms"], (int, float))
            self.assertEqual(timing["row_count"], 1)
            self.assertEqual(timing["verified_row_count"], 1)

    def test_execute_runtime_archive_chunk_reader_processes_multiple_chunks(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_action_confirmation_projection_metric",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        chunk_sizes: list[int] = []

        def chunk_reader(_conn, _spec, chunksize):
            chunk_sizes.append(chunksize)
            return iter(
                [
                    pd.DataFrame([{"trade_date": "20260612", "seq": 1}]),
                    pd.DataFrame([{"trade_date": "20260612", "seq": 2}]),
                    pd.DataFrame([{"trade_date": "20260612", "seq": 3}]),
                ]
            )

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=chunk_reader,
                chunksize=2,
            )

            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(chunk_sizes, [2])
            self.assertEqual(result["total_rows"], 3)
            self.assertEqual(result["files"][0]["chunk_count"], 3)
            self.assertEqual(result["files"][0]["row_count"], 3)
            self.assertEqual(result["files"][0]["verified_row_count"], 3)

    def test_execute_runtime_archive_large_table_writes_partitioned_parts(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="stock_action_confirmation_projection_metric",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def chunk_reader(_conn, _spec, _chunksize):
            return iter(
                [
                    pd.DataFrame([{"trade_date": "20260612", "seq": 1}]),
                    pd.DataFrame([{"trade_date": "20260612", "seq": 2}]),
                ]
            )

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=chunk_reader,
            )

            file_entry = result["files"][0]
            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(file_entry["format"], "parquet_partitioned")
            self.assertEqual(file_entry["chunk_count"], 2)
            self.assertEqual(file_entry["row_count"], 2)
            self.assertEqual(file_entry["verified_row_count"], 2)
            self.assertRegex(file_entry["checksum"], r"^sha256:[a-f0-9]{64}$")
            self.assertEqual(len(file_entry["part_files"]), 2)
            self.assertTrue(Path(file_entry["path"]).is_dir())
            for idx, part in enumerate(file_entry["part_files"]):
                self.assertEqual(part["part_index"], idx)
                self.assertTrue(Path(part["path"]).exists())
                self.assertRegex(part["checksum"], r"^sha256:[a-f0-9]{64}$")
                self.assertEqual(part["row_count"], 1)
                self.assertEqual(part["verified_row_count"], 1)
            self.assertEqual(result["table_timings"][0]["status"], "passed")

    def test_execute_runtime_archive_n4_trigger_state_writes_partitioned_parts(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n4",
                table="common_trigger_state",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def chunk_reader(_conn, _spec, _chunksize):
            return iter(
                [
                    pd.DataFrame([{"for_trade_date": "20260612", "seq": 1}]),
                    pd.DataFrame([{"for_trade_date": "20260612", "seq": 2}]),
                ]
            )

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=chunk_reader,
            )

            file_entry = result["files"][0]
            self.assertEqual(result["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(file_entry["format"], "parquet_partitioned")
            self.assertEqual(file_entry["chunk_count"], 2)
            self.assertEqual(file_entry["row_count"], 2)
            self.assertEqual(file_entry["verified_row_count"], 2)
            self.assertEqual(len(file_entry["part_files"]), 2)
            self.assertTrue(Path(file_entry["path"]).is_dir())

    def test_execute_runtime_archive_small_table_still_writes_single_parquet(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(
                layer="n3",
                table="common_market_data_run",
                sql="select 1",
                params=(),
            ),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=lambda _conn, _spec, _chunksize: iter(
                    [pd.DataFrame([{"trade_date": "20260612"}])]
                ),
            )

            file_entry = result["files"][0]
            self.assertEqual(file_entry["format"], "parquet")
            self.assertTrue(Path(file_entry["path"]).is_file())
            self.assertNotIn("part_files", file_entry)

    def test_execute_runtime_archive_records_blocked_current_table(self) -> None:
        specs = (
            RuntimeArchiveQuerySpec(layer="n3", table="ok_table", sql="select 1", params=()),
            RuntimeArchiveQuerySpec(layer="n3", table="bad_table", sql="select 2", params=()),
        )

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def chunk_reader(_conn, spec, _chunksize):
            if spec.table == "bad_table":
                raise RuntimeError("synthetic read failure")
            return iter([pd.DataFrame([{"trade_date": "20260612"}])])

        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_archive(
                trade_date="20260612",
                archive_root=Path(tmp) / "v3_runtime",
                connection_factory=lambda _dsn: FakeConnection(),
                query_specs=specs,
                chunk_reader=chunk_reader,
            )

            self.assertEqual(result["result"], "BLOCKED")
            self.assertEqual(result["current_table"], {"layer": "n3", "table": "bad_table"})
            self.assertIn("RuntimeError: synthetic read failure", result["blocked_reason"])
            self.assertEqual(result["table_timings"][-1]["status"], "blocked")
            self.assertTrue(Path(result["report_path"]).exists())
            self.assertFalse(result["cleanup_eligible"])


if __name__ == "__main__":
    unittest.main()
