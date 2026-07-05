import json
from pathlib import Path
from hashlib import sha256
import tempfile
import unittest

from ashare_v3.ingestion.runtime_archive_restore import (
    convert_archive_value,
    ordered_restore_files,
    count_sql_for_archive_spec,
    validate_restore_manifest,
)


class RuntimeArchiveRestoreTest(unittest.TestCase):
    def test_ordered_restore_files_restore_parents_before_children(self) -> None:
        files = [
            {"layer": "n4", "table": "common_trigger_match", "path": "/tmp/match.parquet", "row_count": 1},
            {"layer": "n3", "table": "stock_minute_bar_1m", "path": "/tmp/minute.parquet", "row_count": 1},
            {"layer": "n4", "table": "common_trigger_state", "path": "/tmp/state.parquet", "row_count": 1},
            {"layer": "n3", "table": "common_market_data_run", "path": "/tmp/run.parquet", "row_count": 1},
            {"layer": "n4", "table": "common_event_inbox", "path": "/tmp/inbox.parquet", "row_count": 1},
            {"layer": "n4", "table": "common_event_outbox", "path": "/tmp/outbox.parquet", "row_count": 1},
        ]

        ordered = ordered_restore_files(files)
        keys = [(item["layer"], item["table"]) for item in ordered]

        self.assertLess(keys.index(("n3", "common_market_data_run")), keys.index(("n3", "stock_minute_bar_1m")))
        self.assertLess(keys.index(("n4", "common_trigger_state")), keys.index(("n4", "common_trigger_match")))
        self.assertLess(keys.index(("n4", "common_event_outbox")), keys.index(("n4", "common_event_inbox")))

    def test_convert_archive_value_rehydrates_jsonb_and_arrays(self) -> None:
        self.assertEqual(convert_archive_value("[1, 2]", udt_name="_int8"), [1, 2])
        self.assertEqual(convert_archive_value('["buy", "sell"]', udt_name="_text"), ["buy", "sell"])
        self.assertEqual(convert_archive_value(81504.0, udt_name="int8"), 81504)
        jsonb_value = convert_archive_value('{"a": [1]}', udt_name="jsonb")
        self.assertEqual(jsonb_value.obj, {"a": [1]})

    def test_validate_restore_manifest_requires_verified_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "archive_manifest.json"
            parquet_path = Path(tmp) / "x.parquet"
            parquet_path.write_bytes(b"fixture")
            manifest_path.write_text(
                json.dumps(
                    {
                        "result": "ARCHIVED_VERIFIED",
                        "trade_date": "20260612",
                        "file_count": 1,
                        "total_rows": 1,
                        "row_count_match": True,
                        "files": [
                            {
                                "layer": "n3",
                                "table": "common_market_data_run",
                                "path": str(parquet_path),
                                "row_count": 1,
                                "checksum": f"sha256:{sha256(parquet_path.read_bytes()).hexdigest()}",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = validate_restore_manifest(manifest_path, trade_date="20260612")

        self.assertEqual(manifest["result"], "ARCHIVED_VERIFIED")

    def test_restore_uses_overriding_system_value_for_identity_primary_keys(self) -> None:
        source = Path("src/ashare_v3/ingestion/runtime_archive_restore.py").read_text(encoding="utf-8")

        self.assertIn("overriding system value", source.lower())

    def test_count_sql_for_archive_spec_removes_order_by(self) -> None:
        sql = "select * from common_event_inbox where source_layer = %s order by inbox_id"

        count_sql = count_sql_for_archive_spec(sql)

        self.assertEqual(count_sql, "select count(*) from (select * from common_event_inbox where source_layer = %s) s")


if __name__ == "__main__":
    unittest.main()
