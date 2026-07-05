# N4 Projection Matcher 20260608 Baseline For N5

Result: `BASELINE_PASS`

This is a docs-only runtime-control baseline bridge for N5 dry-run/preflight. It does not write DB rows and does not supersede the N4 execute report.

Source run:

`trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`

Baseline distribution:

| event_type | rows |
|---|---:|
| TriggerMatched | 320 |
| TriggerPendingMarketData | 3600 |

Signal distribution:

| event_type | B_BUY | S_SELL |
|---|---:|---:|
| TriggerMatched | 313 | 7 |
| TriggerPendingMarketData | 1803 | 1797 |

N5 policy:

- `TriggerMatched` may enter action confirmation.
- `TriggerPendingMarketData` is quality-only/state-gate and must not create action confirmation.
- `TriggerStateChanged` is not present in this run and remains forbidden as an action entry.
