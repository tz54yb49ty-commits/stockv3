import tempfile
import unittest
from pathlib import Path

from ashare_v3.market.artifact_blob import (
    ArtifactBlobBlocked,
    N3P_OVERLAY_BLOB_FIELDS,
    externalize_payload_fields,
    hydrate_payload_blob_refs,
    write_artifact_blob,
    write_n3p_overlay_blob,
)
from ashare_v3.market import v3_realtime_virtual_metric_writer as writer


class N3ArtifactBlobTest(unittest.TestCase):
    def test_blob_is_canonical_deterministic_and_content_addressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = write_artifact_blob(value=[{"b": 2, "a": 1}], blob_root=Path(tmp) / "artifact_blobs")
            second = write_artifact_blob(value=[{"a": 1, "b": 2}], blob_root=Path(tmp) / "artifact_blobs")
            self.assertEqual(first, second)
            self.assertEqual(first["row_count"], 1)
            self.assertEqual(len(list((Path(tmp) / "artifact_blobs").glob("*.json.gz"))), 1)

    def test_intraday_ref_closure_hydrates_active_retained_and_archive_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            payload = externalize_payload_fields(
                {"stock_quote_rows": [{"identity_key": "stock:SH:600000"}]},
                fields=("stock_quote_rows",), blob_root=base / "artifact_blobs",
            )
            ref = payload["artifact_blob_refs"]["stock_quote_rows"]
            payload["retained_artifact_blob_refs"] = {"retained_rows": ref}
            payload["archive_artifact_blob_refs"] = {"archive_rows": ref}
            payload["active_artifact_blob_refs"] = {"active_rows": ref}
            hydrated = hydrate_payload_blob_refs(payload, base_path=base)
            self.assertEqual(hydrated["stock_quote_rows"], [{"identity_key": "stock:SH:600000"}])
            self.assertEqual(hydrated["retained_rows"], hydrated["archive_rows"])
            Path(base / ref["path"]).unlink()
            with self.assertRaisesRegex(ArtifactBlobBlocked, "artifact_blob_path_unavailable"):
                hydrate_payload_blob_refs(payload, base_path=base)

    def test_n3p_v1_inline_and_v2_ref_replay_are_equal(self):
        overlay = {
            "candidates": [{"identity_key": "stock:SH:600000"}],
            "n4_context_snapshot_rows": [{"identity_key": "stock:SH:600000"}],
            "previous_day_cumulative_rows": [{"identity_key": "stock:SH:600000", "canonical_minute_label": "09:46"}],
        }
        self.assertEqual(set(N3P_OVERLAY_BLOB_FIELDS), set(overlay))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reference = write_n3p_overlay_blob(overlay=overlay, blob_root=base / "artifact_blobs")
            source_payload = {"stock_quote_rows": [{"identity_key": "stock:SH:600000"}]}
            legacy = writer.materialize_source_payload_from_contract(
                {"materialized_source_payload_overlay": overlay}, source_payload
            )
            v2 = writer.materialize_source_payload_from_contract(
                {
                    "materialized_source_payload_overlay_ref": reference,
                    "materialized_source_payload_overlay_ref_base_path": str(base),
                }, source_payload,
            )
            self.assertEqual(v2, legacy)
            with self.assertRaisesRegex(writer.VirtualMetricWriterBlocked, "v1_v2_mismatch"):
                writer.materialize_source_payload_from_contract(
                    {
                        "materialized_source_payload_overlay": {"candidates": []},
                        "materialized_source_payload_overlay_ref": reference,
                        "materialized_source_payload_overlay_ref_base_path": str(base),
                    }, source_payload,
                )
            with self.assertRaisesRegex(ArtifactBlobBlocked, "n3p_overlay_blob_fields_invalid"):
                write_n3p_overlay_blob(overlay={"candidates": []}, blob_root=base / "artifact_blobs")


if __name__ == "__main__":
    unittest.main()
