import unittest

from ashare_v3.user.stale_active_lineage import (
    stale_active_lineage_registry,
    stale_source_trigger_run_ids,
)


class StaleActiveLineageTest(unittest.TestCase):
    def test_20260622_formal_runs_are_registered_as_superseded_by_periodguard_lineage(self) -> None:
        old_formal_run_id = (
            "trigger_replay_phase2d_20260622_formal_until_1500__"
            "condition_layer_20260618_source_20260618_for_20260622_v1"
        )
        old_formal_unitfix_run_id = (
            "trigger_replay_phase2d_20260622_formal_unitfix_until_1500__"
            "condition_layer_20260618_source_20260618_for_20260622_v1"
        )
        active_dseed_run_id = (
            "trigger_replay_phase2d_20260622_formal_unitfix_dseed_until_1500__"
            "condition_layer_20260618_source_20260618_for_20260622_v1"
        )
        active_periodguard_run_id = (
            "trigger_replay_phase2d_20260622_formal_unitfix_dseed_periodguard_until_1500__"
            "condition_layer_20260618_source_20260618_for_20260622_v1"
        )

        stale_trigger_run_ids = stale_source_trigger_run_ids()
        self.assertIn(old_formal_run_id, stale_trigger_run_ids)
        self.assertIn(old_formal_unitfix_run_id, stale_trigger_run_ids)
        self.assertIn(active_dseed_run_id, stale_trigger_run_ids)
        self.assertNotIn(active_periodguard_run_id, stale_trigger_run_ids)

        registry = stale_active_lineage_registry()
        matching_entries = [
            entry
            for entry in registry["additional_stale_lineages"]
            if entry.get("active_source_trigger_run_id") == active_periodguard_run_id
        ]
        self.assertEqual(len(matching_entries), 1)
        self.assertEqual(matching_entries[0]["trade_date"], "20260622")
        self.assertEqual(
            matching_entries[0]["stale_source_trigger_run_ids"],
            [old_formal_run_id, old_formal_unitfix_run_id, active_dseed_run_id],
        )
        self.assertEqual(matching_entries[0]["stale_source_action_run_ids"], [])
        self.assertFalse(matching_entries[0]["delete_historical_rows"])


if __name__ == "__main__":
    unittest.main()
