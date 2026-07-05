#!/usr/bin/env python3
"""Contract wrapper for one N3 HINT index/board 1m source fetch child step."""

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

STEP_ID = "n3_hint_source_fetch"
LAYER_RUNNER_NAME = "n3_hint_index_board_1m_source_fetch_real_runner"


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
        description="Plan one N3 HINT index/board 1m source fetch child step.",
        layer_runner=resolved_runner,
        layer_runner_name=LAYER_RUNNER_NAME,
        audited_layer_capability="n3_hint_index_board_frequency8_source_fetch",
        target_absence_checker=target_absence_checker,
        required_hint_proof_kind=MIDDAY_BRIDGE_HINT_PROOF_KIND,
        output_contract={
            "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
            "asset_scope": "index_board_only",
            "stock_rows_allowed": False,
            "writes_outbox": False,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
