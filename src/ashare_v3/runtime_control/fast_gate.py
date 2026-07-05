"""Fast gate primitives for runtime_control.

Fast gates are deliberately narrow. They decide only PASS / FAIL / BLOCK and
serialize no analysis, lineage explanation, or repair strategy. Full reports
belong to deferred analysis modules; rollback/supersession planning belongs to
manual repair follow-up modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PASS = "PASS"
FAIL = "FAIL"
BLOCK = "BLOCK"

FAST_GATE_RESULT_VALUES = frozenset({PASS, FAIL, BLOCK})
FAST_GATE_ALLOWED_KEYS = frozenset({"result"})


@dataclass(frozen=True)
class FastGateDecision:
    result: str

    def __post_init__(self) -> None:
        if self.result not in FAST_GATE_RESULT_VALUES:
            raise ValueError(f"invalid fast gate result: {self.result}")

    def to_dict(self) -> dict[str, str]:
        return {"result": self.result}


def build_fast_gate_decision(*, blockers: list[str] | tuple[str, ...], failures: list[str] | tuple[str, ...]) -> FastGateDecision:
    if blockers:
        return FastGateDecision(BLOCK)
    if failures:
        return FastGateDecision(FAIL)
    return FastGateDecision(PASS)


def assert_fast_gate_payload(payload: Mapping[str, Any]) -> None:
    extra_keys = set(payload) - FAST_GATE_ALLOWED_KEYS
    if extra_keys:
        raise ValueError(f"fast gate payload contains non-decision keys: {sorted(extra_keys)}")
    result = payload.get("result")
    if result not in FAST_GATE_RESULT_VALUES:
        raise ValueError(f"invalid fast gate result: {result}")


def mark_deferred_analysis(report: Mapping[str, Any]) -> dict[str, Any]:
    marked = dict(report)
    marked["module_role"] = "DEFERRED_ANALYSIS"
    return marked


def mark_repair_follow_up(next_gate: str) -> dict[str, Any]:
    return {
        "module_role": "REPAIR_FOLLOW_UP",
        "next_gate": next_gate,
        "execute_in_fast_gate": False,
    }
