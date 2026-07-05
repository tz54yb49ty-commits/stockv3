# N5 Dry-Run N4 Projection Execute Baseline Compatibility Fix

Result: `FIX_PASS`

Root cause: `compare_n4_projection_execute_preflight_baseline` was truncated and returned `None` for current N4 production replay execute reports. The N5 dry-run then crashed when quality checks accessed `baseline_comparison.get(...)`.

Fix: restored the N4 projection execute baseline comparison logic and added a regression test for `execute_plan_summary` reports.

Proof: refreshed N5 dry-run now passes with `P0/P1/P2=0/0/0`, read count `799`, and baseline read count `799`.
