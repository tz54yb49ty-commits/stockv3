"""Command and rollback registries for the runtime control plane.

The registry records reviewed commands and rollback SQL paths. It never runs
commands, opens database connections, or modifies N1-N6 execute contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ExecuteCommandRegistryEntry:
    stage_id: str
    layer_role: str
    command: tuple[str, ...]
    description: str
    requires_manual_confirm: bool = True
    modifies_execute_contract: bool = False
    starts_worker: bool = False
    executes_nightly_run: bool = False

    @property
    def has_side_effects_in_registry(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "layer_role": self.layer_role,
            "command": list(self.command),
            "description": self.description,
            "requires_manual_confirm": self.requires_manual_confirm,
            "modifies_execute_contract": self.modifies_execute_contract,
            "starts_worker": self.starts_worker,
            "executes_nightly_run": self.executes_nightly_run,
            "has_side_effects_in_registry": self.has_side_effects_in_registry,
        }


@dataclass(frozen=True)
class RollbackRegistryEntry:
    stage_id: str
    layer_role: str
    rollback_sql_path: str
    description: str
    executes_rollback: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "layer_role": self.layer_role,
            "rollback_sql_path": self.rollback_sql_path,
            "description": self.description,
            "executes_rollback": self.executes_rollback,
        }


def build_default_execute_command_registry(*, trade_date: str) -> dict[str, ExecuteCommandRegistryEntry]:
    return {
        "calendar": ExecuteCommandRegistryEntry(
            stage_id="calendar",
            layer_role="N1_ingestion",
            command=(
                "python3",
                "scripts/run_trade_calendar_patch_20260527_once.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N1 trade calendar patch command registered for operator review.",
        ),
        "n1_official_daily": ExecuteCommandRegistryEntry(
            stage_id="n1_official_daily",
            layer_role="N1_ingestion",
            command=(
                "python3",
                "scripts/run_official_daily_ingestion_20260525_once.py",
                "--trade-date",
                trade_date,
                "--execute",
                "--user-confirmed",
            ),
            description="N1 official daily ingestion command template registered for operator review.",
        ),
        "n1_condition_source": ExecuteCommandRegistryEntry(
            stage_id="n1_condition_source",
            layer_role="N1_ingestion",
            command=(
                "python3",
                "scripts/run_condition_source_activation_20260526_v2_once.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N1 condition source activation command registered for operator review.",
        ),
        "n2_condition_layer": ExecuteCommandRegistryEntry(
            stage_id="n2_condition_layer",
            layer_role="N2_condition",
            command=(
                "python3",
                "scripts/run_condition_layer_execute.py",
                "--source-trade-date",
                "<source_trade_date>",
                "--execute",
                "--user-confirmed",
            ),
            description="N2 condition layer execute command template registered for operator review.",
        ),
        "n3_subscription": ExecuteCommandRegistryEntry(
            stage_id="n3_subscription",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_market_data_subscription_execute.py",
                "--run-id",
                "<condition_run_id>",
                "--source-trade-date",
                "<source_trade_date>",
                "--for-trade-date",
                trade_date,
            ),
            description="N3 subscription execute command template registered for operator review.",
        ),
        "a1_previous_day_preload": ExecuteCommandRegistryEntry(
            stage_id="a1_previous_day_preload",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_previous_day_minute_preload_execute.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N3-A1 previous-day preload command registered for operator review.",
        ),
        "b1_realtime_snapshot_fact_only": ExecuteCommandRegistryEntry(
            stage_id="b1_realtime_snapshot_fact_only",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_realtime_daily_snapshot_once.py",
                "--for-trade-date",
                trade_date,
                "--snapshot-run-id",
                f"realtime_snapshot_{trade_date}_manual_gate",
                "--no-outbox",
                "--execute",
                "--user-confirmed",
            ),
            description="N3-B1 realtime snapshot fact-only command registered for operator review.",
        ),
    }


def build_default_rollback_registry(*, trade_date: str) -> dict[str, RollbackRegistryEntry]:
    return {
        "calendar": RollbackRegistryEntry(
            stage_id="calendar",
            layer_role="N1_ingestion",
            rollback_sql_path=f"sql/N1_trade_calendar_{trade_date}_patch_rollback.sql",
            description="Rollback SQL for N1 trade calendar patch.",
        ),
        "n1_official_daily": RollbackRegistryEntry(
            stage_id="n1_official_daily",
            layer_role="N1_ingestion",
            rollback_sql_path=f"sql/N1_official_daily_{trade_date}_ingestion_rollback.sql",
            description="Rollback SQL for N1 official daily ingestion.",
        ),
        "n1_condition_source": RollbackRegistryEntry(
            stage_id="n1_condition_source",
            layer_role="N1_ingestion",
            rollback_sql_path=f"sql/N1_condition_source_{trade_date}_activation_rollback.sql",
            description="Rollback SQL for N1 condition source activation.",
        ),
        "n2_condition_layer": RollbackRegistryEntry(
            stage_id="n2_condition_layer",
            layer_role="N2_condition",
            rollback_sql_path=f"sql/N2_condition_layer_{trade_date}_rollback.sql",
            description="Rollback SQL for N2 condition layer run.",
        ),
        "n3_subscription": RollbackRegistryEntry(
            stage_id="n3_subscription",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_subscription_{trade_date}_rollback.sql",
            description="Rollback SQL for N3 subscription run.",
        ),
        "a1_previous_day_preload": RollbackRegistryEntry(
            stage_id="a1_previous_day_preload",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_A1_previous_day_minute_{trade_date}_rollback.sql",
            description="Rollback SQL for N3-A1 previous-day minute preload.",
        ),
        "b1_realtime_snapshot_fact_only": RollbackRegistryEntry(
            stage_id="b1_realtime_snapshot_fact_only",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_B1_realtime_snapshot_{trade_date}_rollback.sql",
            description="Rollback SQL for N3-B1 realtime snapshot fact-only run.",
        ),
    }


def build_action_confirmation_execute_command_registry(*, trade_date: str) -> dict[str, ExecuteCommandRegistryEntry]:
    source_trade_date = "20260601" if trade_date == "20260602" else "<source_trade_date>"
    condition_run_id = f"condition_layer_{source_trade_date}_source_{source_trade_date}_v1"
    subscription_run_id = f"market_data_subscription_{trade_date}_{condition_run_id}"
    snapshot_run_id = f"realtime_snapshot_{trade_date}_live3_outbox_{subscription_run_id}"
    projection_run_id = f"action_confirmation_projection_metric_{trade_date}_1105__{snapshot_run_id}"
    trigger_run_id = f"trigger_action_confirmation_metric_execute_{trade_date}_1105__{condition_run_id}"
    action_run_id = f"action_consumer_action_confirmation_metric_execute_{trade_date}_1105__{trigger_run_id}"
    return {
        "n2_condition_layer_active": ExecuteCommandRegistryEntry(
            stage_id="n2_condition_layer_active",
            layer_role="N2_condition",
            command=(
                "python3",
                "scripts/run_condition_layer_execute.py",
                "--source-trade-date",
                source_trade_date,
                "--for-trade-date",
                trade_date,
                "--execute",
                "--user-confirmed",
            ),
            description="N2 active condition layer command text for reviewed action-confirmation lineage.",
        ),
        "n3_subscription": ExecuteCommandRegistryEntry(
            stage_id="n3_subscription",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_market_data_subscription_execute.py",
                "--run-id",
                condition_run_id,
                "--source-trade-date",
                source_trade_date,
                "--for-trade-date",
                trade_date,
                "--execute",
                "--user-confirmed",
            ),
            description="N3 subscription command text for reviewed action-confirmation lineage.",
        ),
        "n3_a1_previous_day_preload": ExecuteCommandRegistryEntry(
            stage_id="n3_a1_previous_day_preload",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_previous_day_minute_preload_execute.py",
                "--source-run-id",
                subscription_run_id,
                "--execute",
                "--user-confirmed",
            ),
            description="N3-A1 previous-day preload command text for reviewed action-confirmation lineage.",
        ),
        "n3_b1_live3_snapshot": ExecuteCommandRegistryEntry(
            stage_id="n3_b1_live3_snapshot",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_realtime_daily_snapshot_once.py",
                "--for-trade-date",
                trade_date,
                "--snapshot-run-id",
                snapshot_run_id,
                "--execute",
                "--user-confirmed",
            ),
            description="N3-B1 live3 outbox snapshot command text for reviewed action-confirmation lineage.",
        ),
        "n3_c1_today_minute": ExecuteCommandRegistryEntry(
            stage_id="n3_c1_today_minute",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_today_minute_bar_1m_once.py",
                "--source-run-id",
                subscription_run_id,
                "--until-minute",
                "1105",
                "--execute",
                "--user-confirmed",
            ),
            description="N3-C1 today minute command text for reviewed action-confirmation lineage.",
        ),
        "n3_action_confirmation_projection": ExecuteCommandRegistryEntry(
            stage_id="n3_action_confirmation_projection",
            layer_role="N3_market_data",
            command=(
                "python3",
                "scripts/run_action_confirmation_projection_metric_once.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N3 action-confirmation projection metric command text.",
        ),
        "n4_action_confirmation_metric_execute": ExecuteCommandRegistryEntry(
            stage_id="n4_action_confirmation_metric_execute",
            layer_role="N4_trigger",
            command=(
                "python3",
                "scripts/run_trigger_action_confirmation_metric_once.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N4 action-confirmation metric trigger command text.",
        ),
        "n5_action_confirmation_metric_execute": ExecuteCommandRegistryEntry(
            stage_id="n5_action_confirmation_metric_execute",
            layer_role="N5_action",
            command=(
                "python3",
                "scripts/run_action_consumer_once.py",
                "--execute",
                "--user-confirmed",
            ),
            description="N5 action-confirmation metric action consumer command text.",
        ),
        "n6_shadow_projection": ExecuteCommandRegistryEntry(
            stage_id="n6_shadow_projection",
            layer_role="N6_user",
            command=(
                "python3",
                "scripts/run_n6_projection_once.py",
                "--source-action-run-id",
                action_run_id,
                "--projection-run-id",
                f"user_projection_shadow_{trade_date}_1105__{action_run_id}",
                "--expected-n5-outbox-count",
                "ActionExecuted:pending=4",
                "--expected-n5-outbox-count",
                "ActionBlocked:pending=1",
                "--execute",
                "--user-confirmed",
            ),
            description="N6 shadow projection command text for reviewed action-confirmation lineage.",
        ),
    }


def build_action_confirmation_rollback_registry(*, trade_date: str) -> dict[str, RollbackRegistryEntry]:
    source_trade_date = "20260601" if trade_date == "20260602" else "<source_trade_date>"
    return {
        "n2_condition_layer_active": RollbackRegistryEntry(
            stage_id="n2_condition_layer_active",
            layer_role="N2_condition",
            rollback_sql_path=f"sql/N2_condition_layer_{source_trade_date}_to_{trade_date}_rollback.sql",
            description="Rollback SQL for N2 active condition layer lineage.",
        ),
        "n3_subscription": RollbackRegistryEntry(
            stage_id="n3_subscription",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_subscription_{trade_date}_rollback.sql",
            description="Rollback SQL for N3 subscription run.",
        ),
        "n3_a1_previous_day_preload": RollbackRegistryEntry(
            stage_id="n3_a1_previous_day_preload",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_A1_previous_day_minute_{trade_date}_rollback.sql",
            description="Rollback SQL for N3-A1 previous-day minute preload.",
        ),
        "n3_b1_live3_snapshot": RollbackRegistryEntry(
            stage_id="n3_b1_live3_snapshot",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_B1_realtime_snapshot_{trade_date}_live3_outbox_rollback.sql",
            description="Rollback SQL for N3-B1 live3 outbox snapshot.",
        ),
        "n3_c1_today_minute": RollbackRegistryEntry(
            stage_id="n3_c1_today_minute",
            layer_role="N3_market_data",
            rollback_sql_path=f"sql/N3_C1_today_minute_bar_1m_{trade_date}_until_1105_rollback.sql",
            description="Rollback SQL for N3-C1 today minute run.",
        ),
        "n3_action_confirmation_projection": RollbackRegistryEntry(
            stage_id="n3_action_confirmation_projection",
            layer_role="N3_market_data",
            rollback_sql_path="sql/N3_action_confirmation_projection_metric_business_rollback.sql",
            description="Rollback SQL for N3 action-confirmation projection metric run.",
        ),
        "n4_action_confirmation_metric_execute": RollbackRegistryEntry(
            stage_id="n4_action_confirmation_metric_execute",
            layer_role="N4_trigger",
            rollback_sql_path="sql/N4_action_confirmation_metric_business_execute_rollback.sql",
            description="Rollback SQL for N4 action-confirmation metric trigger run.",
        ),
        "n5_action_confirmation_metric_execute": RollbackRegistryEntry(
            stage_id="n5_action_confirmation_metric_execute",
            layer_role="N5_action",
            rollback_sql_path=f"sql/N5_{trade_date}_action_confirmation_metric_execute_rollback.sql",
            description="Rollback SQL for N5 action-confirmation metric action run.",
        ),
        "n6_shadow_projection": RollbackRegistryEntry(
            stage_id="n6_shadow_projection",
            layer_role="N6_user",
            rollback_sql_path="sql/N6_projection_business_rollback.sql",
            description="Rollback SQL for N6 shadow projection run.",
        ),
    }


def registry_to_dict(registry: Mapping[str, ExecuteCommandRegistryEntry | RollbackRegistryEntry]) -> dict[str, object]:
    return {key: value.to_dict() for key, value in registry.items()}
