#!/usr/bin/env python3
"""Contract wrapper for one N3 HINT proof preflight child step."""

import sys

from scripts.n3_n4_combined_child_contract import (
    DEFAULT_LAYER_RUNNER,
    MIDDAY_BRIDGE_HINT_PROOF_KIND,
    run_child_contract,
)
from scripts.n3_combined_child_real_runners import (
    DEFAULT_N3_REAL_IO_DEPENDENCIES,
    DEFAULT_N3_REAL_RUNNER_OPERATIONS,
    build_n3_real_layer_runner,
)

STEP_ID = "n3_hint_proof_preflight"
LAYER_RUNNER_NAME = "n3_hint_index_board_1m_proof_preflight_real_runner"


def _plan_only_artifact_materialization_requested(argv: list[str] | None) -> bool:
    tokens = list(sys.argv[1:] if argv is None else argv)
    return (
        "--execute" not in tokens
        and "--contract-path" in tokens
        and "--preflight-path" in tokens
    )


def main(
    argv: list[str] | None = None,
    *,
    layer_runner=DEFAULT_LAYER_RUNNER,
    real_runner_operations=DEFAULT_N3_REAL_RUNNER_OPERATIONS,
    real_io_dependencies=DEFAULT_N3_REAL_IO_DEPENDENCIES,
    target_absence_checker=None,
) -> int:
    resolved_runner = (
        build_n3_real_layer_runner(STEP_ID, operations=real_runner_operations, dependencies=real_io_dependencies)
        if layer_runner is DEFAULT_LAYER_RUNNER
        else layer_runner
    )
    return run_child_contract(
        argv=argv,
        step_id=STEP_ID,
        layer_role="N3_market_data",
        description="Plan one N3 HINT proof preflight child step.",
        layer_runner=resolved_runner,
        layer_runner_name=LAYER_RUNNER_NAME,
        audited_layer_capability="n3_hint_index_board_1m_proof_plan_only_preflight",
        target_absence_checker=target_absence_checker,
        required_hint_proof_kind=MIDDAY_BRIDGE_HINT_PROOF_KIND,
        output_contract={
            "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
            "metric_role": "hint_trigger_proof",
            "proof_consumer": "N4",
            "asset_scope": "index_board_only",
            "not_n5_final_proof": True,
        },
        run_layer_runner_in_plan_only=_plan_only_artifact_materialization_requested(argv),
    )


if __name__ == "__main__":
    raise SystemExit(main())
