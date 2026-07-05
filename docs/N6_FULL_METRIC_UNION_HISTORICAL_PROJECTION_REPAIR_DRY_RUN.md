# N6 Full Metric-Union Historical Projection Repair Dry Run

Status: `DRY_RUN_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This dry-run materializes the row-level repair payload for syncing N6 projection/card metadata to the already repaired N5 full metric-union metadata. It did not execute any database update.

## Planned Metadata Updates

| target | planned rows |
|---|---:|
| user_signal_projection metadata update | 289 |
| user_signal_card metadata update | 289 |
| user_notification_queue update | 0 |
| projection/card row delete | 0 |
| N5/N4/N3 update | 0 |

## User Visible Delta

The UI will no longer show `metric_missing` for these 289 cards after a future execute:

| old visible reason | new visible reason | rows |
|---|---|---:|
| `metric_missing` | `price_confirmation_failed` | 282 |
| `metric_missing` | `amount_confirmation_failed` | 7 |

Final visible blocked_reason distribution:

| blocked_reason | rows |
|---|---:|
| `price_confirmation_failed` | 587 |
| `amount_confirmation_failed` | 17 |
| `metric_missing` | 0 |

Action semantics remain unchanged:

- `ActionExecuted` remains 1.
- `ActionBlocked` remains 604.
- No proposal/order/trade/position/PnL is generated.

## Payload

Payload path:

```text
docs/N6_full_metric_union_historical_projection_repair_payload.json
```

The payload contains 289 row items, including previous metadata and target metric-union trace metadata.

## Sample

`stock:SH:688690`:

- source event: `evt_51a3ea62bfb8e93407a5859107a95c0e14ad6d70`
- projection/card: `5954 / 5954`
- old blocked_reason: `metric_missing`
- new blocked_reason: `amount_confirmation_failed`
- metric coverage: `full`

## Boundary Proof

- No database update was performed.
- N5 outbox was not consumed or updated.
- `user_notification_queue` remains deferred and untouched.
- No worker/delivery/push/voice/mobile was started.
- No sim/position/PnL/real trade/proposal/order/trade was generated.
- B-track multi-user app was not modified.

## Decision

`DRY_RUN_PASS`
