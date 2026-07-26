"""Function-only N6 virtual executor persistence client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


CLAIM_SQL = "SELECT public.n6_executor_claim_proposal(%s, %s) AS result"
CLAIM_NEXT_SQL = "SELECT public.n6_executor_claim_next_proposal(%s) AS result"
FUNCTION_SQL = "SELECT public.n6_executor_apply_claimed_proposal(%s, %s) AS result"


class VirtualExecutorConnection(Protocol):
    def cursor(self): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@dataclass(frozen=True)
class VirtualExecutorRequest:
    proposal_id: int | None
    executor_run_id: str


def validate_request(request: VirtualExecutorRequest) -> None:
    if request.proposal_id is not None and request.proposal_id <= 0:
        raise ValueError("proposal_id_must_be_positive")
    if not request.executor_run_id.strip() or len(request.executor_run_id) > 200:
        raise ValueError("invalid_executor_run_id")


def _call_json_function(cursor: Any, sql: str, params: tuple[object, ...]) -> dict[str, Any]:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("executor_function_returned_no_row")
    value = row["result"] if isinstance(row, Mapping) else row[0]
    if not isinstance(value, Mapping):
        raise RuntimeError("executor_function_returned_invalid_payload")
    return dict(value)


def execute_proposal(
    connection: VirtualExecutorConnection,
    request: VirtualExecutorRequest,
) -> dict[str, Any]:
    """Claim and apply in one outer transaction; failure always rolls back claim."""
    validate_request(request)
    try:
        with connection.cursor() as cursor:
            if request.proposal_id is None:
                claim = _call_json_function(
                    cursor, CLAIM_NEXT_SQL, (request.executor_run_id,)
                )
            else:
                claim = _call_json_function(
                    cursor,
                    CLAIM_SQL,
                    (request.proposal_id, request.executor_run_id),
                )
            if not claim.get("ok"):
                connection.rollback()
                return claim
            proposal_id = claim.get("proposal_id")
            if not isinstance(proposal_id, int) or proposal_id <= 0:
                raise RuntimeError("claim_returned_invalid_proposal_id")
            result = _call_json_function(
                cursor, FUNCTION_SQL, (proposal_id, request.executor_run_id)
            )
        if result.get("ok"):
            connection.commit()
        else:
            connection.rollback()
        return result
    except Exception:
        connection.rollback()
        raise
