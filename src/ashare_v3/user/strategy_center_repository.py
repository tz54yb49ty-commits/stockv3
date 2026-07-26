from __future__ import annotations

from typing import Any, Protocol


class ReadCursor(Protocol):
    def execute(self, query: str, params: dict[str, Any]) -> Any: ...

    def fetchall(self) -> list[dict[str, Any]]: ...


SCOPE_ROWS_SQL = """
WITH current_stock_approved_batch AS MATERIALIZED (
  SELECT min(approved.source_trade_date::text) AS source_trade_date,
         min(approved.for_trade_date::text) AS for_trade_date,
         min(approved.run_id::text) AS source_run_id
  FROM v_n6_stock_condition_display_basis approved
  WHERE approved.for_trade_date::text = %(trade_date)s
  HAVING count(*) > 0
     AND count(approved.source_trade_date) = count(*)
     AND count(approved.for_trade_date) = count(*)
     AND count(approved.run_id) = count(*)
     AND count(DISTINCT (
       approved.source_trade_date::text,
       approved.for_trade_date::text,
       approved.run_id::text
     )) = 1
), monitor_scope AS (
  SELECT DISTINCT m.identity_key AS stock_identity_key,
         'monitor'::text AS scope_source
  FROM user_monitor_stock m
  JOIN current_stock_approved_batch batch
    ON m.valid_source_trade_date::text = batch.source_trade_date
   AND m.valid_for_trade_date::text = batch.for_trade_date
   AND m.valid_source_run_id::text = batch.source_run_id
   AND m.source_run_id::text = batch.source_run_id
  WHERE m.principal_id = %(principal_id)s
    AND m.principal_type = %(principal_type)s
    AND m.user_id = %(user_id)s
    AND m.asset_kind = 'stock'
    AND m.status = 'active'
    AND EXISTS (
      SELECT 1
      FROM v_n6_stock_condition_display_basis approved
      WHERE approved.identity_key = m.identity_key
        AND approved.source_trade_date::text = batch.source_trade_date
        AND approved.for_trade_date::text = batch.for_trade_date
        AND approved.run_id::text = batch.source_run_id
    )
), realtime_scope AS (
  SELECT DISTINCT s.identity_key AS stock_identity_key,
         'realtime_scope'::text AS scope_source
  FROM user_realtime_monitor_scope s
  WHERE s.principal_id = %(principal_id)s
    AND s.principal_type = %(principal_type)s
    AND s.user_id = %(user_id)s
    AND s.asset_kind = 'stock'
    AND s.status = 'active'
), virtual_position_scope AS (
  SELECT DISTINCT p.identity_key AS stock_identity_key,
         'virtual_position'::text AS scope_source
  FROM n6_virtual_account a
  JOIN n6_virtual_position p
    ON p.virtual_account_id = a.virtual_account_id
   AND p.principal_id = a.principal_id
   AND p.principal_type = a.principal_type
  WHERE a.principal_id = %(principal_id)s
    AND a.principal_type = %(principal_type)s
    AND a.virtual_account_status = 'active'
    AND p.asset_kind = 'stock'
    AND p.position_status = 'open_virtual'
    AND p.quantity > 0
)
SELECT %(trade_date)s::text AS trade_date,
       scope.stock_identity_key,
       scope.scope_source
FROM (
  SELECT * FROM monitor_scope
  UNION ALL
  SELECT * FROM realtime_scope
  UNION ALL
  SELECT * FROM virtual_position_scope
) scope
WHERE scope.stock_identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
ORDER BY scope.stock_identity_key, scope.scope_source
"""


PARENT_EXECUTED_SIGNAL_IDS_SQL = """
SELECT p.user_signal_projection_id
FROM user_signal_projection p
JOIN user_projection_run r
  ON r.user_projection_run_id = p.user_projection_run_id
 AND r.status IN ('passed', 'ready')
WHERE p.user_id = %(user_id)s
  AND p.projection_status = 'visible'
  AND p.asset_kind IN ('index', 'board')
  AND p.action_state = 'executed'
  AND p.for_trade_date = pg_catalog.to_date(%(trade_date)s, 'YYYYMMDD')
ORDER BY p.user_signal_projection_id
"""


SIGNAL_AUTHORITY_ROWS_SQL = """
SELECT p.user_signal_projection_id,
       p.user_id,
       COALESCE(NULLIF(p.source_action_event_type, ''), p.source_event_type)
         AS event_type,
       pg_catalog.to_char(p.for_trade_date, 'YYYYMMDD') AS trade_date,
       NULLIF(p.source_payload_json->>'event_time', '')
         AS source_event_time,
       NULLIF(p.list_payload_json->>'event_time', '')
         AS projection_event_time,
       p.source_layer,
       p.asset_kind,
       p.identity_key,
       p.code,
       p.name,
       p.action_state,
       NULLIF(p.source_payload_json->'payload_json'->>'direction', '')
         AS source_direction,
       NULLIF(p.direction, '') AS projection_direction,
       p.source_event_id AS event_id,
       p.source_action_run_id AS source_run_id,
       p.source_event_schema_version AS event_schema_version,
       COALESCE(
         NULLIF(
           p.source_payload_json->'payload_json'
             ->'action_entry_trigger_matched_ref'
             ->>'source_trigger_event_id',
           ''
         ),
         NULLIF(
           p.trace_json->'action_entry_trigger_matched_ref'
             ->>'source_trigger_event_id',
           ''
         )
       ) AS action_episode_key
FROM user_signal_projection p
WHERE p.user_id = %(user_id)s
  AND p.projection_status = 'visible'
  AND p.for_trade_date = pg_catalog.to_date(%(trade_date)s, 'YYYYMMDD')
  AND p.user_signal_projection_id = ANY(%(projection_ids)s)
  AND (
    (p.asset_kind = 'stock' AND p.action_state IN ('eligible', 'executed'))
    OR
    (p.asset_kind IN ('index', 'board') AND p.action_state = 'executed')
  )
ORDER BY p.user_signal_projection_id
"""


INDEX_MEMBERSHIP_ROWS_SQL = """
SELECT membership.trade_date,
       membership.stock_identity_key,
       'index'::text AS parent_asset_kind,
       membership.index_identity_key AS parent_identity_key,
       membership.index_code AS parent_code,
       membership.index_name AS parent_name,
       membership.source_version,
       membership.source_batch_id,
       membership.created_at::text AS created_at,
       ''::text AS board_type
FROM v_n6_index_membership_fact membership
WHERE membership.trade_date = %(trade_date)s
  AND membership.stock_identity_key = ANY(%(stock_identity_keys)s)
ORDER BY membership.stock_identity_key,
         membership.index_identity_key,
         membership.created_at,
         membership.source_version
"""


BOARD_MEMBERSHIP_ROWS_SQL = """
SELECT membership.trade_date,
       membership.stock_identity_key,
       'board'::text AS parent_asset_kind,
       membership.board_identity_key AS parent_identity_key,
       membership.board_code AS parent_code,
       membership.board_name AS parent_name,
       membership.source_version,
       membership.source_batch_id,
       membership.created_at::text AS created_at,
       membership.board_type
FROM v_n6_board_membership_fact membership
WHERE membership.trade_date = %(trade_date)s
  AND membership.stock_identity_key = ANY(%(stock_identity_keys)s)
  AND membership.board_type IN (
    'tdx_industry', 'tdx_concept', 'tdx_region'
  )
ORDER BY membership.stock_identity_key,
         membership.board_type,
         membership.board_identity_key,
         membership.created_at,
         membership.source_version
"""


class N6StrategyCenterReadRepository:
    @staticmethod
    def fetch_scope_rows(
        cursor: ReadCursor,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        trade_date: str,
    ) -> list[dict[str, Any]]:
        cursor.execute(
            SCOPE_ROWS_SQL,
            {
                "principal_id": principal_id,
                "principal_type": principal_type,
                "user_id": user_id,
                "trade_date": trade_date,
            },
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def fetch_parent_executed_signal_ids(
        cursor: ReadCursor, *, user_id: int, trade_date: str
    ) -> list[int]:
        cursor.execute(
            PARENT_EXECUTED_SIGNAL_IDS_SQL,
            {"user_id": user_id, "trade_date": trade_date},
        )
        return [int(row["user_signal_projection_id"]) for row in cursor.fetchall()]

    @staticmethod
    def fetch_signal_authority_rows(
        cursor: ReadCursor,
        *,
        user_id: int,
        trade_date: str,
        projection_ids: list[int],
    ) -> list[dict[str, Any]]:
        requested_ids = sorted(set(projection_ids))
        if not requested_ids:
            return []
        cursor.execute(
            SIGNAL_AUTHORITY_ROWS_SQL,
            {
                "user_id": user_id,
                "trade_date": trade_date,
                "projection_ids": requested_ids,
            },
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def fetch_index_membership_rows(
        cursor: ReadCursor,
        *,
        trade_date: str,
        stock_identity_keys: list[str],
    ) -> list[dict[str, Any]]:
        if not stock_identity_keys:
            return []
        cursor.execute(
            INDEX_MEMBERSHIP_ROWS_SQL,
            {
                "trade_date": trade_date,
                "stock_identity_keys": sorted(set(stock_identity_keys)),
            },
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def fetch_board_membership_rows(
        cursor: ReadCursor,
        *,
        trade_date: str,
        stock_identity_keys: list[str],
    ) -> list[dict[str, Any]]:
        if not stock_identity_keys:
            return []
        cursor.execute(
            BOARD_MEMBERSHIP_ROWS_SQL,
            {
                "trade_date": trade_date,
                "stock_identity_keys": sorted(set(stock_identity_keys)),
            },
        )
        return [dict(row) for row in cursor.fetchall()]
