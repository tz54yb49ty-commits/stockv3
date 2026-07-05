# N6 Real Delivery Dry-Run Provider Bounded Smoke Contract

Result: `CONTRACT_PASS`

Gate: `N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_CONTRACT_GATE`

Generated at: `2026-06-10T23:20:46+08:00`

## Contract Scope

- provider_smoke_run_id: `n6_real_delivery_dry_run_provider_bounded_smoke_20260608_chained_shadow_probe`
- mode: dry-run provider bounded smoke
- adapter_kind: `dry_run_provider`
- provider_id: `dry_run_provider_v1`
- source_projection_run_id: `n4_n5_n6_chained_shadow_smoke_20260608_projection_probe`
- source_action_run_id: `n4_n5_n6_chained_shadow_smoke_20260608_action_probe`
- source_notification_source: `n6_delivery_materialized_noop`
- source_queue_status: `ready_for_future_push`
- source_channel: `in_app_notification_preview`
- source registered rows: `50`
- max_events: `10`

## Provider Contract

`DryRunProviderAdapter` must satisfy:

- provider result: `DRY_RUN`
- `can_send_network=false`
- `can_update_n5_outbox_status=false`
- `requires_credentials=false`
- `network_send_attempted=false`
- `provider_delivery_confirmed=false`
- `n5_outbox_status_updated=false`
- fake transport call count: `0`

## Payload Contract

Provider-visible allowed fields:

- `schema_version`
- `delivery_materialization_run_id`
- `source_notification_queue_id`
- `provider_id`
- `channel`
- `title`
- `message`

Provider-visible forbidden fields include trace/source/raw/internal payload keys such as `trace_json`, `source_payload_json`, `raw_n5_payload`, `source_action_run_id`, `payload_json`, and `action_run_internal_payload`.

Expected forbidden payload key rows: `0`.

## Planned Write Scope

- local report artifact: `docs/N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_EXECUTE_REPORT.json`
- database writes: `0`
- N5 outbox updates: `0`
- N5 inbox/checkpoint writes: `0`
- provider attempt audit rows: `0`
- user_notification_queue writes: `0`
- delivery/push/voice/mobile: `0`
- sim/position/pnl/real_trade: `0`
- proposal/order/trade: `0`

## Rollback Contract

Rollback SQL is not required because this bounded smoke is not allowed to write the database.

The rollback/supersession policy remains referenced: if a local report artifact already exists, the next gate must either supersede it explicitly or write a new uniquely named report artifact.

## Allowed Execute Command

Only the following command may be used in the execute user-confirmation gate. It writes one local JSON report artifact and does not read DB, write DB, read secret, or call provider network.

```sh
PYTHONPATH=src:scripts python3 - <<'PY' > docs/N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_EXECUTE_REPORT.json
import json
from datetime import datetime, timezone
from ashare_v3.user.delivery_provider import DryRunProviderAdapter, ProviderSendInput, provider_payload_has_forbidden_keys

run_id = 'n6_real_delivery_dry_run_provider_bounded_smoke_20260608_chained_shadow_probe'
adapter = DryRunProviderAdapter(transport=lambda payload: (_ for _ in ()).throw(RuntimeError('transport must not be called')))
cap = adapter.capability()
assert cap.provider_id == 'dry_run_provider_v1'
assert cap.adapter_kind == 'dry_run_provider'
assert cap.can_send_network is False
assert cap.can_update_n5_outbox_status is False
assert cap.requires_credentials is False

rows = []
for ordinal in range(1, 11):
    result = adapter.send(ProviderSendInput(
        delivery_materialization_run_id=run_id,
        source_notification_queue_id=ordinal,
        provider_id=cap.provider_id,
        channel='in_app_notification_preview',
        title='dry-run provider bounded smoke',
        message='no network; no secret; no db write',
        notification_payload_json={
            'title': 'dry-run provider bounded smoke',
            'message': 'no network; no secret; no db write',
            'trace_json': {'blocked': True},
            'raw_n5_payload': {'blocked': True},
            'source_action_run_id': 'must_not_leak'
        },
    ))
    payload = dict(result.payload)
    assert result.result == 'DRY_RUN'
    assert result.network_send_attempted is False
    assert result.provider_delivery_confirmed is False
    assert result.n5_outbox_status_updated is False
    assert provider_payload_has_forbidden_keys(payload) is False
    rows.append({
        'ordinal': ordinal,
        'result': result.result,
        'network_send_attempted': result.network_send_attempted,
        'provider_delivery_confirmed': result.provider_delivery_confirmed,
        'n5_outbox_status_updated': result.n5_outbox_status_updated,
        'forbidden_payload_keys': False,
    })

report = {
    'result': 'EXECUTE_PASS',
    'status': 'DRY_RUN_PROVIDER_BOUNDED_SMOKE_PASS',
    'provider_smoke_run_id': run_id,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'adapter_kind': cap.adapter_kind,
    'provider_id': cap.provider_id,
    'max_events': 10,
    'selected_rows': len(rows),
    'source_projection_run_id': 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe',
    'source_action_run_id': 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe',
    'source_notification_source': 'n6_delivery_materialized_noop',
    'source_queue_status': 'ready_for_future_push',
    'source_channel': 'in_app_notification_preview',
    'database_writes': 0,
    'network_calls': 0,
    'secret_reads': 0,
    'n5_outbox_updates': 0,
    'fake_transport_call_count': 0,
    'rows': rows,
}
print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
PY
```

## Decision

Allowed next gate: `N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_EXECUTE_USER_CONFIRMATION_GATE`.

Real provider execute remains blocked.
