# N2-R2 Static Reference Period Remediation Report

Date: 2026-05-24
Layer: N2_condition
Status: code/docs/schema draft completed, no migration executed, no overwrite executed

## Problem

N2 previously used `clear_sell_ref_period` as a static condition-layer field paired with `buy_target_price`.
This mixed a N5 position/action-layer concept into N2 and lacked a symmetric reference period for `sell_target_price`.

## Target Machine Reference

Target machine position fallback rule:

```text
clear_sell_ref_period_for_position = clear_ref or reference_period or D
```

Target machine clear threshold rule:

```text
D < W < M < Q < Y
sell_trigger_period_rank >= clear_sell_ref_period_rank
```

## New N2 Canonical Fields

```text
buy_target_price  + up_sell_reference_period
sell_target_price + down_buy_reference_period
```

Compatibility alias:

```text
clear_sell_ref_period = up_sell_reference_period
```

`clear_sell_ref_period` is retained only as a legacy alias until N5 consumes `up_sell_reference_period` directly.

## Computation Rules

```text
up_sell_reference_period:
  from main_up_anchor lower periods, find first risk grade
  risk grade = flat / low_volume_down / volume_down
  fallback = computed_up_sell_ref or up_reference_period or main_up_anchor or D

down_buy_reference_period:
  from main_down_anchor lower periods, find first opportunity grade
  opportunity grade = flat / low_volume_up / volume_up
  fallback = computed_down_buy_ref or down_reference_period or main_down_anchor or D
```

Both fields must be non-empty. Missing reference periods are P0.

## Changed Files

```text
AGENTS.md
docs/V3_CONDITION_LAYER_DEVELOPMENT_DESIGN.md
docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md
docs/N2_WEB_POLICY_FILTER_DESIGN.md
sql/002_condition_layer_schema.sql
sql/011_condition_static_reference_period_migration.sql
src/ashare_v3/condition/basis.py
src/ashare_v3/condition/pool.py
src/ashare_v3/condition/scope.py
src/ashare_v3/condition/execute.py
src/ashare_v3/condition/scope_policy.py
src/ashare_v3/condition/web_policy.py
src/ashare_v3/condition/schema_migration_readiness.py
src/ashare_v3/web/templates/n2_policy_console.html
tests/test_condition_basis.py
```

## Verification

```text
python3 -m compileall scripts src tests: passed
PYTHONPATH=/tmp/v3_py_stubs:src python3 -m unittest tests.test_condition_basis tests.test_scope_policy tests.test_n2_web_policy: passed, 43 tests
git diff --check: passed
```

Full unittest with system python is blocked by missing local packages (`psycopg`, `tomllib`) in this shell. No database migration or overwrite was attempted.

## Boundary

```text
Touched old system: no
Executed migration: no
Wrote condition_basis/condition_pool/minute_target_scope: no
Overwrite active condition run: no
Entered N3/N4/N5/N6: no
Started worker/service: no
```

## Next Step

N2-R2 migration/overwrite should remain blocked until explicit confirmation.
Suggested next steps:

1. Review `sql/011_condition_static_reference_period_migration.sql`.
2. Run schema gap/migration review for N2-R2.
3. Execute additive migration only after confirmation.
4. Re-run N2 full dry-run.
5. If P0=0 and reference coverage is 100%, execute overwrite to create a new active condition run.
