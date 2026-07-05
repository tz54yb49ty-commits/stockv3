"""Reviewed stale lineage registry for active N6 user-message reads.

Historical facts remain queryable for audit. Active user-message paths must not
project or display source runs registered here.
"""

from __future__ import annotations

from typing import Any, Mapping


HINT_30M_STALE_TARGET = {
    "trade_date": "20260615",
    "asset_kind": "board",
    "identity_key": "board:TDX:881470",
    "event_time": "2026-06-15T09:31:00+08:00",
    "condition_key": "BUY_HINT",
    "stale_action_mark": "30m_volume",
}

HINT_30M_CORRECTED_METRIC = {
    "projection_run_id": "v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_policy_fix_v1",
    "current_30m_virtual_amount": "2348930635.56391",
    "previous_day_same_window_amount": "2613103496",
    "policy_version": "previous_day_same_window_elapsed_ratio_v1",
}

HINT_30M_STALE_METRIC_RUN_IDS = (
    "v3_n3_action_confirmation_metric_20260615_full_universe_replay_v1",
    "v3_n3_action_confirmation_metric_20260615_full_universe_formal_proof_enriched_v1",
    "v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1",
)

HINT_30M_STALE_SOURCE_TRIGGER_RUN_IDS = (
    "v3_n4_trigger_replay_20260615_after_n3_full_universe_metric_v1",
    "v3_n4_trigger_replay_20260615_after_formal_proof_enrichment_v1",
    "v3_n4_trigger_replay_20260615_attachment_rule_canonical_v1",
)

HINT_30M_STALE_SOURCE_ACTION_RUN_IDS = (
    "v3_n5_action_replay_20260615_after_n4_full_universe_trigger_v1",
    "v3_n5_action_replay_20260615_after_n4_formal_proof_enrichment_v1",
    "v3_n5_action_replay_20260615_attachment_rule_canonical_v1",
)

N2_D_ANCHOR_STALE_SOURCE_TRIGGER_RUN_IDS = (
    "trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
)

N2_D_ANCHOR_STALE_SOURCE_ACTION_RUN_IDS = (
    "action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1",
)

PHASE2D_20260622_ACTIVE_SOURCE_TRIGGER_RUN_ID = (
    "trigger_replay_phase2d_20260622_formal_unitfix_dseed_periodguard_until_1500__"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)

PHASE2D_20260622_STALE_SOURCE_TRIGGER_RUN_IDS = (
    "trigger_replay_phase2d_20260622_formal_until_1500__"
    "condition_layer_20260618_source_20260618_for_20260622_v1",
    "trigger_replay_phase2d_20260622_formal_unitfix_until_1500__"
    "condition_layer_20260618_source_20260618_for_20260622_v1",
    "trigger_replay_phase2d_20260622_formal_unitfix_dseed_until_1500__"
    "condition_layer_20260618_source_20260618_for_20260622_v1",
)


def stale_source_action_run_ids() -> tuple[str, ...]:
    return HINT_30M_STALE_SOURCE_ACTION_RUN_IDS + N2_D_ANCHOR_STALE_SOURCE_ACTION_RUN_IDS


def stale_source_trigger_run_ids() -> tuple[str, ...]:
    return (
        HINT_30M_STALE_SOURCE_TRIGGER_RUN_IDS
        + N2_D_ANCHOR_STALE_SOURCE_TRIGGER_RUN_IDS
        + PHASE2D_20260622_STALE_SOURCE_TRIGGER_RUN_IDS
    )


def is_stale_source_action_run_id(run_id: str | None) -> bool:
    return bool(run_id) and str(run_id) in stale_source_action_run_ids()


def is_stale_user_signal_row(row: Mapping[str, Any]) -> bool:
    return is_stale_source_action_run_id(
        row.get("source_action_run_id") or row.get("source_run_id")
    )


def stale_active_lineage_registry() -> dict[str, Any]:
    return {
        "registry": "V3_20260615_HINT_30M_STALE_ACTIVE_LINEAGE",
        "target": dict(HINT_30M_STALE_TARGET),
        "classification": "STALE",
        "delete_historical_rows": False,
        "active_user_message_policy": "exclude_stale_source_action_run_ids",
        "stale_metric_run_ids": list(HINT_30M_STALE_METRIC_RUN_IDS),
        "stale_source_trigger_run_ids": list(stale_source_trigger_run_ids()),
        "stale_source_action_run_ids": list(stale_source_action_run_ids()),
        "corrected_metric": dict(HINT_30M_CORRECTED_METRIC),
        "additional_stale_lineages": [
            {
                "registry": "V3_20260617_N2_D_ANCHOR_REPAIR_SUPERSEDED_UI_LINEAGE",
                "trade_date": "20260617",
                "reason": "superseded_by_d_anchor_repair_and_proof_alias_lineage",
                "delete_historical_rows": False,
                "stale_source_trigger_run_ids": list(N2_D_ANCHOR_STALE_SOURCE_TRIGGER_RUN_IDS),
                "stale_source_action_run_ids": list(N2_D_ANCHOR_STALE_SOURCE_ACTION_RUN_IDS),
            },
            {
                "registry": "PHASE2D_20260622_FORMAL_DSEED_SUPERSEDED_UI_LINEAGE",
                "trade_date": "20260622",
                "reason": "superseded_by_formal_unitfix_dseed_periodguard_repair",
                "active_source_trigger_run_id": PHASE2D_20260622_ACTIVE_SOURCE_TRIGGER_RUN_ID,
                "delete_historical_rows": False,
                "stale_source_trigger_run_ids": list(PHASE2D_20260622_STALE_SOURCE_TRIGGER_RUN_IDS),
                "stale_source_action_run_ids": [],
            }
        ],
    }
