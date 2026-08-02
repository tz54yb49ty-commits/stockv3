"""Independent N6 current trigger-status episode consumer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row


CONTRACT_VERSION = "N5-N6-trigger-status-forward-v1"
MESSAGE_ROLE = "n6_trigger_status_projection_only"
CONSUMER_NAME = "n6_trigger_status_projection_v1"
CHECKPOINT_SOURCE_LAYER = "N5_action"
CONSUMED_EVENT_TYPES = (
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
    "TriggerStatusUpdated",
    "TriggerStatusInvalidated",
)
ACTION_EVENT_TYPES = (
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
)
STATUS_EVENT_TYPES = ("TriggerStatusUpdated", "TriggerStatusInvalidated")
FORMAL_PERIOD_ORDER = ("Y", "Q", "M", "W", "D")
VALID_ASSET_KINDS = frozenset({"stock", "index", "board"})
VALID_DIRECTIONS = frozenset({"buy", "sell"})
VALID_SIGNAL_TYPES = frozenset({"B_BUY", "S_SELL"})


class TriggerStatusProjectionError(RuntimeError):
    """Raised before commit when a batch cannot be applied exactly."""


@dataclass(frozen=True)
class TriggerStatusConsumeResult:
    consumer_name: str
    trade_date: str
    projection_run_id: str
    selected: int
    inserted: int
    updated: int
    invalidated: int
    ignored_action_outcomes: int
    replay_skipped: int
    last_outbox_id: int | None
    outbox_status_updates: int = 0


def canonical_triggered_periods(value: Any, *, condition_key: str) -> list[str]:
    if condition_key in {"BUY_HINT", "SELL_HINT"} or condition_key.startswith(("BUY_HINT:", "SELL_HINT:")):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, (list, tuple)):
        value = []
    selected = {str(period) for period in value}
    if not selected.issubset(FORMAL_PERIOD_ORDER):
        raise TriggerStatusProjectionError("invalid_triggered_periods")
    return [period for period in FORMAL_PERIOD_ORDER if period in selected]


def _required_text(source: Mapping[str, Any], field: str) -> str:
    value = str(source.get(field) or "").strip()
    if not value:
        raise TriggerStatusProjectionError(f"missing_{field}")
    return value


def _optional_decimal(value: Any, field: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TriggerStatusProjectionError(f"invalid_{field}") from exc
    if not parsed.is_finite():
        raise TriggerStatusProjectionError(f"invalid_{field}")
    return parsed.quantize(Decimal("0.000001"))


def _eligible_trade_date(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    entry_snapshot: Mapping[str, Any],
) -> str:
    values: list[str] = []
    for source in (row, payload, entry_snapshot):
        value = str(source.get("trade_date") or "").strip()
        if not value:
            continue
        if len(value) != 8 or not value.isdigit():
            raise TriggerStatusProjectionError("invalid_trade_date")
        values.append(value)
    if not values:
        raise TriggerStatusProjectionError("missing_trade_date")
    if len(set(values)) != 1:
        raise TriggerStatusProjectionError("eligible_trade_date_conflict")
    return values[0]


def _validate_grain(payload: Mapping[str, Any]) -> dict[str, str]:
    grain = {
        field: _required_text(payload, field)
        for field in (
            "trade_date",
            "asset_kind",
            "identity_key",
            "direction",
            "signal_type",
            "condition_key",
        )
    }
    if len(grain["trade_date"]) != 8 or not grain["trade_date"].isdigit():
        raise TriggerStatusProjectionError("invalid_trade_date")
    if grain["asset_kind"] not in VALID_ASSET_KINDS:
        raise TriggerStatusProjectionError("invalid_asset_kind")
    if grain["direction"] not in VALID_DIRECTIONS:
        raise TriggerStatusProjectionError("invalid_direction")
    if grain["signal_type"] not in VALID_SIGNAL_TYPES:
        raise TriggerStatusProjectionError("invalid_signal_type")
    return grain


def episode_from_action_eligible(
    row: Mapping[str, Any],
    *,
    projection_run_id: str,
) -> dict[str, Any]:
    payload = row.get("payload_json")
    if not isinstance(payload, Mapping):
        raise TriggerStatusProjectionError("eligible_payload_not_object")
    if str(row.get("source_layer") or "") != "N5_action":
        raise TriggerStatusProjectionError("eligible_source_layer_invalid")
    if str(payload.get("projection_message_status") or "") != "ready":
        raise TriggerStatusProjectionError("eligible_projection_not_ready")
    entry_ref = payload.get("action_entry_trigger_matched_ref")
    if not isinstance(entry_ref, Mapping):
        raise TriggerStatusProjectionError("eligible_entry_ref_missing")
    if str(entry_ref.get("source_trigger_event_type") or "") != "TriggerMatched":
        raise TriggerStatusProjectionError("eligible_entry_ref_not_trigger_matched")
    entry_snapshot = entry_ref.get("source_n4_payload")
    if not isinstance(entry_snapshot, Mapping):
        entry_snapshot = {}
    grain_source = {
        **entry_snapshot,
        **payload,
        "trade_date": _eligible_trade_date(row, payload, entry_snapshot),
    }
    grain = _validate_grain(grain_source)
    entry_trigger_event_id = _required_text(entry_ref, "source_trigger_event_id")
    if str(payload.get("source_trigger_event_id") or entry_trigger_event_id) != entry_trigger_event_id:
        raise TriggerStatusProjectionError("eligible_entry_event_id_mismatch")
    trace = payload.get("trace_json")
    trace = trace if isinstance(trace, Mapping) else {}
    tracking_state_key = str(trace.get("tracking_state_key") or payload.get("action_key") or "").strip()
    if not tracking_state_key:
        raise TriggerStatusProjectionError("missing_tracking_state_key")
    condition_key = grain["condition_key"]
    trigger_period = str(
        payload.get("trigger_period")
        or payload.get("primary_trigger_period")
        or entry_snapshot.get("trigger_period")
        or entry_snapshot.get("primary_trigger_period")
        or ""
    ).strip() or None
    if condition_key in {"BUY_HINT", "SELL_HINT"} or condition_key.startswith(("BUY_HINT:", "SELL_HINT:")):
        trigger_period = "30m"
    if trigger_period not in {*FORMAL_PERIOD_ORDER, "30m", None}:
        raise TriggerStatusProjectionError("invalid_trigger_period")
    triggered_periods = canonical_triggered_periods(
        payload.get("triggered_periods", payload.get("all_trigger_periods", entry_snapshot.get("triggered_periods", []))),
        condition_key=condition_key,
    )
    trigger_time = str(payload.get("trigger_time") or entry_ref.get("source_trigger_event_time") or "").strip()
    if not trigger_time:
        raise TriggerStatusProjectionError("missing_trigger_time")
    return {
        "contract_version": CONTRACT_VERSION,
        "consumer_name": CONSUMER_NAME,
        "projection_run_id": projection_run_id,
        **grain,
        "tracking_state_key": tracking_state_key,
        "entry_trigger_event_id": entry_trigger_event_id,
        "action_eligible_event_id": _required_text(row, "event_id"),
        "asset_code": _required_text(grain_source, "asset_code"),
        "asset_name": _required_text(grain_source, "asset_name"),
        "trigger_time": trigger_time,
        "trigger_price": _optional_decimal(payload.get("trigger_price"), "trigger_price"),
        "trigger_period": trigger_period,
        "triggered_periods": triggered_periods,
        "action_eligible_outbox_id": int(row["outbox_id"]),
        "last_status_outbox_id": int(row["outbox_id"]),
        "last_event_id": _required_text(row, "event_id"),
        "last_event_type": "ActionEligible",
        "source_action_run_id": _required_text(row, "source_run_id"),
        "source_trigger_event_id": entry_trigger_event_id,
    }


def status_mutation_from_event(row: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(row.get("event_type") or "")
    payload = row.get("payload_json")
    if event_type not in STATUS_EVENT_TYPES or not isinstance(payload, Mapping):
        raise TriggerStatusProjectionError("invalid_status_event")
    if str(row.get("source_layer") or "") != "N5_action":
        raise TriggerStatusProjectionError("status_source_layer_invalid")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise TriggerStatusProjectionError("status_contract_version_invalid")
    if payload.get("message_role") != MESSAGE_ROLE:
        raise TriggerStatusProjectionError("status_message_role_invalid")
    if payload.get("action_eligible_entry_allowed") is not False:
        raise TriggerStatusProjectionError("status_action_entry_boundary_invalid")
    expected_operation = "update" if event_type == "TriggerStatusUpdated" else "invalidate"
    if payload.get("operation") != expected_operation:
        raise TriggerStatusProjectionError("status_operation_invalid")
    grain = _validate_grain(payload)
    mutation = {
        **grain,
        "tracking_state_key": _required_text(payload, "tracking_state_key"),
        "entry_trigger_event_id": _required_text(payload, "entry_trigger_event_id"),
        "action_eligible_event_id": _required_text(payload, "action_eligible_event_id"),
        "last_status_outbox_id": int(row["outbox_id"]),
        "last_event_id": _required_text(row, "event_id"),
        "last_event_type": event_type,
        "source_trigger_event_id": _required_text(payload, "source_trigger_event_id"),
    }
    if event_type == "TriggerStatusInvalidated":
        return mutation
    trigger_price = _optional_decimal(payload.get("trigger_price"), "trigger_price")
    if trigger_price is None or trigger_price <= 0:
        raise TriggerStatusProjectionError("invalid_trigger_price")
    condition_key = grain["condition_key"]
    trigger_period = _required_text(payload, "trigger_period")
    if trigger_period not in {*FORMAL_PERIOD_ORDER, "30m"}:
        raise TriggerStatusProjectionError("invalid_trigger_period")
    if "triggered_periods" not in payload:
        raise TriggerStatusProjectionError("missing_triggered_periods")
    if not isinstance(payload["triggered_periods"], (list, tuple)):
        raise TriggerStatusProjectionError("invalid_triggered_periods")
    mutation.update(
        {
            "trigger_price": trigger_price,
            "trigger_period": trigger_period,
            "triggered_periods": canonical_triggered_periods(
                payload["triggered_periods"], condition_key=condition_key
            ),
        }
    )
    return mutation


class PostgresTriggerStatusProjectionConsumer:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def consume_once(
        self,
        *,
        trade_date: str,
        projection_run_id: str,
        limit: int = 500,
    ) -> TriggerStatusConsumeResult:
        if len(trade_date) != 8 or not trade_date.isdigit():
            raise TriggerStatusProjectionError("invalid_trade_date")
        if not projection_run_id.strip():
            raise TriggerStatusProjectionError("missing_projection_run_id")
        partition_key = f"trigger-status:{trade_date}"
        counts = {
            "inserted": 0,
            "updated": 0,
            "invalidated": 0,
            "ignored_action_outcomes": 0,
            "replay_skipped": 0,
        }
        last_outbox_id: int | None = None
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s, 0))",
                    (f"{CONSUMER_NAME}:{trade_date}",),
                )
                cur.execute(
                    """
                    SELECT last_outbox_id
                    FROM common_event_consumer_checkpoint
                    WHERE consumer_name = %s AND partition_key = %s AND source_layer = %s
                    FOR UPDATE
                    """,
                    (CONSUMER_NAME, partition_key, CHECKPOINT_SOURCE_LAYER),
                )
                checkpoint = cur.fetchone()
                after_outbox_id = int(checkpoint["last_outbox_id"] or 0) if checkpoint else 0
                cur.execute(
                    """
                    SELECT outbox_id, event_id, event_type, event_schema_version,
                           trade_date, asset_kind, identity_key, event_time,
                           source_layer, source_run_id, dedup_key, partition_key,
                           payload_json, status
                    FROM common_event_outbox
                    WHERE outbox_id > %s
                      AND trade_date = %s
                      AND source_layer = 'N5_action'
                      AND event_type = ANY(%s)
                    ORDER BY outbox_id ASC
                    LIMIT %s
                    """,
                    (after_outbox_id, trade_date, list(CONSUMED_EVENT_TYPES), max(1, min(int(limit), 5000))),
                )
                rows = [dict(row) for row in cur.fetchall()]
                for row in rows:
                    last_outbox_id = int(row["outbox_id"])
                    if self._already_processed(cur, row):
                        counts["replay_skipped"] += 1
                        continue
                    event_type = str(row["event_type"])
                    if event_type == "ActionEligible":
                        inserted = self._insert_episode(
                            cur,
                            episode_from_action_eligible(row, projection_run_id=projection_run_id),
                        )
                        counts["inserted"] += int(inserted)
                    elif event_type == "TriggerStatusUpdated":
                        self._update_episode(cur, status_mutation_from_event(row))
                        counts["updated"] += 1
                    elif event_type == "TriggerStatusInvalidated":
                        counts["invalidated"] += self._invalidate_episode(
                            cur, status_mutation_from_event(row)
                        )
                    else:
                        counts["ignored_action_outcomes"] += 1
                    self._record_inbox(cur, row)
                if last_outbox_id is not None:
                    last = rows[-1]
                    cur.execute(
                        """
                        INSERT INTO common_event_consumer_checkpoint (
                          consumer_name, partition_key, source_layer, last_event_id,
                          last_event_time, last_outbox_id, checkpoint_payload, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, pg_catalog.clock_timestamp())
                        ON CONFLICT (consumer_name, partition_key, source_layer) DO UPDATE SET
                          last_event_id = EXCLUDED.last_event_id,
                          last_event_time = EXCLUDED.last_event_time,
                          last_outbox_id = EXCLUDED.last_outbox_id,
                          checkpoint_payload = EXCLUDED.checkpoint_payload,
                          updated_at = pg_catalog.clock_timestamp()
                        """,
                        (
                            CONSUMER_NAME,
                            partition_key,
                            CHECKPOINT_SOURCE_LAYER,
                            last["event_id"],
                            last["event_time"],
                            last_outbox_id,
                            json.dumps(
                                {
                                    "contract_version": CONTRACT_VERSION,
                                    "projection_run_id": projection_run_id,
                                    "trade_date": trade_date,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        ),
                    )
        return TriggerStatusConsumeResult(
            consumer_name=CONSUMER_NAME,
            trade_date=trade_date,
            projection_run_id=projection_run_id,
            selected=len(rows),
            last_outbox_id=last_outbox_id,
            **counts,
        )

    @staticmethod
    def _already_processed(cur: Any, row: Mapping[str, Any]) -> bool:
        cur.execute(
            """
            SELECT status FROM common_event_inbox
            WHERE consumer_name = %s AND event_id = %s
            """,
            (CONSUMER_NAME, row["event_id"]),
        )
        existing = cur.fetchone()
        if not existing:
            return False
        if existing["status"] != "processed":
            raise TriggerStatusProjectionError("existing_inbox_not_processed")
        return True

    @staticmethod
    def _insert_episode(cur: Any, episode: Mapping[str, Any]) -> bool:
        cur.execute(
            """
            INSERT INTO n6_trigger_status_current (
              contract_version, consumer_name, projection_run_id, trade_date,
              tracking_state_key, entry_trigger_event_id, action_eligible_event_id,
              asset_kind, identity_key, asset_code, asset_name, direction,
              signal_type, condition_key, trigger_time, trigger_price,
              trigger_period, triggered_periods, action_eligible_outbox_id,
              last_status_outbox_id, last_event_id, last_event_type,
              source_action_run_id, source_trigger_event_id
            ) VALUES (
              %(contract_version)s, %(consumer_name)s, %(projection_run_id)s, %(trade_date)s,
              %(tracking_state_key)s, %(entry_trigger_event_id)s, %(action_eligible_event_id)s,
              %(asset_kind)s, %(identity_key)s, %(asset_code)s, %(asset_name)s, %(direction)s,
              %(signal_type)s, %(condition_key)s, %(trigger_time)s,
              %(trigger_price)s, %(trigger_period)s, %(triggered_periods)s,
              %(action_eligible_outbox_id)s, %(last_status_outbox_id)s,
              %(last_event_id)s, %(last_event_type)s, %(source_action_run_id)s,
              %(source_trigger_event_id)s
            )
            ON CONFLICT (tracking_state_key, entry_trigger_event_id) DO NOTHING
            """,
            dict(episode),
        )
        if cur.rowcount == 1:
            return True
        cur.execute(
            """
            SELECT action_eligible_event_id, trade_date, asset_kind, identity_key,
                   direction, signal_type, condition_key
            FROM n6_trigger_status_current
            WHERE tracking_state_key = %s AND entry_trigger_event_id = %s
            """,
            (episode["tracking_state_key"], episode["entry_trigger_event_id"]),
        )
        existing = cur.fetchone()
        expected = {
            key: episode[key]
            for key in (
                "action_eligible_event_id",
                "trade_date",
                "asset_kind",
                "identity_key",
                "direction",
                "signal_type",
                "condition_key",
            )
        }
        if existing is None or dict(existing) != expected:
            raise TriggerStatusProjectionError("eligible_episode_conflict")
        return False

    @staticmethod
    def _episode_where(mutation: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
        fields = (
            "trade_date",
            "asset_kind",
            "identity_key",
            "direction",
            "signal_type",
            "condition_key",
            "tracking_state_key",
            "entry_trigger_event_id",
            "action_eligible_event_id",
        )
        return " AND ".join(f"{field} = %s" for field in fields), tuple(mutation[field] for field in fields)

    @classmethod
    def _update_episode(cls, cur: Any, mutation: Mapping[str, Any]) -> None:
        where, params = cls._episode_where(mutation)
        cur.execute(
            f"""
            UPDATE n6_trigger_status_current
            SET trigger_price = %s,
                trigger_period = %s,
                triggered_periods = %s,
                last_status_outbox_id = %s,
                last_event_id = %s,
                last_event_type = %s,
                source_trigger_event_id = %s,
                updated_at = pg_catalog.clock_timestamp()
            WHERE {where}
            """,
            (
                mutation["trigger_price"],
                mutation["trigger_period"],
                mutation["triggered_periods"],
                mutation["last_status_outbox_id"],
                mutation["last_event_id"],
                mutation["last_event_type"],
                mutation["source_trigger_event_id"],
                *params,
            ),
        )
        if cur.rowcount != 1:
            raise TriggerStatusProjectionError("missing_status_update_target")

    @classmethod
    def _invalidate_episode(cls, cur: Any, mutation: Mapping[str, Any]) -> int:
        where, params = cls._episode_where(mutation)
        cur.execute(f"DELETE FROM n6_trigger_status_current WHERE {where}", params)
        return int(cur.rowcount)

    @staticmethod
    def _record_inbox(cur: Any, row: Mapping[str, Any]) -> None:
        raw_json = dict(row)
        raw_json["event_time"] = str(raw_json.get("event_time") or "")
        cur.execute(
            """
            INSERT INTO common_event_inbox (
              consumer_name, event_id, event_type, event_schema_version,
              source_layer, source_run_id, dedup_key, partition_key,
              payload_json, status, attempt_count, received_at, processed_at, raw_json
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s,
              %s::jsonb, 'processed', 1, pg_catalog.clock_timestamp(),
              pg_catalog.clock_timestamp(), %s::jsonb
            )
            """,
            (
                CONSUMER_NAME,
                row["event_id"],
                row["event_type"],
                row["event_schema_version"],
                row["source_layer"],
                row["source_run_id"],
                row["dedup_key"],
                row["partition_key"],
                json.dumps(row["payload_json"], ensure_ascii=False, sort_keys=True),
                json.dumps(raw_json, ensure_ascii=False, sort_keys=True, default=str),
            ),
        )
