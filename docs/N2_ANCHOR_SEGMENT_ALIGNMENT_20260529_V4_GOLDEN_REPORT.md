# N2 Anchor Segment Alignment 20260529 V4 Golden Report

Status: PASS

Boundary:

```text
layer_role=N2_condition
execute=false
writes_performed=false
minute_kline_pulled=false
downstream_layers_touched=false
```

Target run_id: `condition_layer_20260529_source_20260529_v4`
Previous active run_id: `condition_layer_20260529_source_20260529_v3`

## Golden Results

| identity_key | expected target | dry-run target | active-before target | dry-run A segment | pass |
|---|---:|---:|---:|---|---|
| `stock:SZ:000600` | 12.93 | 12.93 | 13.03 | 20260518 -> 20260529 | True |
| `stock:SZ:000543` | 10.82 | 10.82 | 10.82 | 20260506 -> 20260529 | True |
| `stock:SZ:000027` | 8.45 | 8.45 | 8.45 | 20260506 -> 20260529 | True |


## Change Summary

```text
target_price_changed_count_vs_active_run = 3803
P0/P1/P2 = 0/6/3
```

## Notes

000600 proves the key fix: W anchor A segment is now the current continuous weekly `volume_up` segment, not the enclosing monthly current window.
