import unittest

from ashare_v3.trigger.canonical_signal import (
    CanonicalSignalMappingError,
    canonical_payload_errors,
    canonicalize_condition_key,
    canonicalize_condition_row,
    canonicalize_trigger_candidate,
)


class TriggerCanonicalSignalTest(unittest.TestCase):
    def test_b_buy_maps_to_normal_buy_signal(self) -> None:
        mapping = canonicalize_condition_key("B_BUY")

        self.assertEqual(mapping.signal_type, "B_BUY")
        self.assertEqual(mapping.action_mark, "normal")
        self.assertEqual(mapping.original_condition_key, "B_BUY")

    def test_s_sell_maps_to_normal_sell_signal(self) -> None:
        mapping = canonicalize_condition_key("S_SELL")

        self.assertEqual(mapping.signal_type, "S_SELL")
        self.assertEqual(mapping.action_mark, "normal")
        self.assertEqual(mapping.original_condition_key, "S_SELL")

    def test_b_buy_30m_vol_maps_to_buy_signal_with_volume_mark(self) -> None:
        mapping = canonicalize_condition_key("B_BUY_30M_VOL")

        self.assertEqual(mapping.signal_type, "B_BUY")
        self.assertEqual(mapping.action_mark, "30m_volume")
        self.assertEqual(mapping.original_condition_key, "B_BUY_30M_VOL")

    def test_s_sell_30m_shrink_maps_to_sell_signal_with_shrink_mark(self) -> None:
        mapping = canonicalize_condition_key("S_SELL_30M_SHRINK")

        self.assertEqual(mapping.signal_type, "S_SELL")
        self.assertEqual(mapping.action_mark, "30m_shrink")
        self.assertEqual(mapping.original_condition_key, "S_SELL_30M_SHRINK")

    def test_buy_hint_with_volume_projection_maps_to_buy_signal_and_volume_candidate(self) -> None:
        mapping = canonicalize_condition_key("BUY_HINT", projection_30m_type="volume_up")

        self.assertEqual(mapping.signal_type, "B_BUY")
        self.assertEqual(mapping.trigger_mark_candidate, "30m_volume")
        self.assertEqual(mapping.original_condition_key, "BUY_HINT")

    def test_sell_hint_with_shrink_projection_maps_to_sell_signal_and_shrink_candidate(self) -> None:
        mapping = canonicalize_condition_key("SELL_HINT", projection_30m_type="shrink_down")

        self.assertEqual(mapping.signal_type, "S_SELL")
        self.assertEqual(mapping.trigger_mark_candidate, "30m_shrink")
        self.assertEqual(mapping.original_condition_key, "SELL_HINT")

    def test_hint_without_projection_maps_to_normal_mark(self) -> None:
        self.assertEqual(canonicalize_condition_key("BUY_HINT").trigger_mark_candidate, "normal")
        self.assertEqual(canonicalize_condition_key("SELL_HINT", projection_30m_type="none").trigger_mark_candidate, "normal")
        self.assertEqual(canonicalize_condition_key("SELL_HINT", projection_30m_type=None).trigger_mark_candidate, "normal")

    def test_unknown_condition_key_raises(self) -> None:
        with self.assertRaises(CanonicalSignalMappingError):
            canonicalize_condition_key("FOO")

    def test_condition_key_is_preserved_as_original_condition_key_in_payload_fields(self) -> None:
        payload = canonicalize_condition_key("B_BUY_30M_VOL").as_payload_fields()

        self.assertEqual(
            payload,
            {
                "original_condition_key": "B_BUY_30M_VOL",
                "signal_type": "B_BUY",
                "trigger_mark_candidate": "30m_volume",
            },
        )

    def test_condition_row_preserves_original_condition_key_without_rewriting_n2_key(self) -> None:
        row = {
            "identity_key": "stock:SH:600000",
            "condition_key": "S_SELL_30M_SHRINK",
            "source_condition_run_id": "condition_layer_example",
        }

        output = canonicalize_condition_row(row)

        self.assertEqual(output["condition_key"], "S_SELL_30M_SHRINK")
        self.assertEqual(output["original_condition_key"], "S_SELL_30M_SHRINK")
        self.assertEqual(output["signal_type"], "S_SELL")
        self.assertEqual(output["trigger_mark_candidate"], "30m_shrink")
        self.assertEqual(output["source_condition_run_id"], "condition_layer_example")

    def test_incompatible_hint_projection_raises(self) -> None:
        with self.assertRaises(CanonicalSignalMappingError):
            canonicalize_condition_key("BUY_HINT", projection_30m_type="shrink_down")
        with self.assertRaises(CanonicalSignalMappingError):
            canonicalize_condition_key("SELL_HINT", projection_30m_type="volume_up")

    def test_trigger_candidate_preserves_n2_condition_key_and_maps_candidate_semantic(self) -> None:
        mapping = canonicalize_trigger_candidate("BUY:D", candidate_signal_type="B_BUY_30M_VOL")

        self.assertEqual(mapping.original_condition_key, "BUY:D")
        self.assertEqual(mapping.signal_type, "B_BUY")
        self.assertEqual(mapping.trigger_mark_candidate, "30m_volume")

    def test_condition_row_can_canonicalize_candidate_signal_type(self) -> None:
        row = {"condition_key": "SELL:Y,D", "identity_key": "stock:SH:600000"}

        output = canonicalize_condition_row(row, candidate_signal_type="S_SELL_30M_SHRINK")

        self.assertEqual(output["condition_key"], "SELL:Y,D")
        self.assertEqual(output["original_condition_key"], "SELL:Y,D")
        self.assertEqual(output["signal_type"], "S_SELL")
        self.assertEqual(output["trigger_mark_candidate"], "30m_shrink")

    def test_payload_validator_rejects_legacy_runtime_signal_type(self) -> None:
        self.assertEqual(
            canonical_payload_errors(
                {
                    "signal_type": "B_BUY_30M_VOL",
                    "trigger_mark_candidate": "normal",
                    "original_condition_key": "BUY:D",
                }
            ),
            ["invalid_signal_type"],
        )

    def test_buy_sell_condition_keys_map_directly_to_runtime_buy_sell(self) -> None:
        self.assertEqual(canonicalize_condition_key("BUY:D").signal_type, "B_BUY")
        self.assertEqual(canonicalize_condition_key("BUY:FULL").signal_type, "B_BUY")
        self.assertEqual(canonicalize_condition_key("SELL:M,W,D").signal_type, "S_SELL")
        self.assertEqual(canonicalize_condition_key("SELL:FULL").signal_type, "S_SELL")

    def test_payload_validator_rejects_hint_as_runtime_signal_type(self) -> None:
        self.assertEqual(
            canonical_payload_errors(
                {
                    "signal_type": "BUY_HINT",
                    "trigger_mark_candidate": "normal",
                    "original_condition_key": "BUY_HINT",
                }
            ),
            ["invalid_signal_type"],
        )


if __name__ == "__main__":
    unittest.main()
