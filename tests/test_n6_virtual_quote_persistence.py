from __future__ import annotations

from datetime import datetime, timezone
import argparse
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from ashare_v3.n3n6q import QuoteIdentity, QuoteProvider
from ashare_v3.user import virtual_quote_persistence as quote_persistence_module
from ashare_v3.user.n6_virtual_quote_client import (
    build_n6_virtual_quote_provider,
    canonicalize_mootdx_source_time,
)
from ashare_v3.user.virtual_quote_persistence import (
    LATEST_QUOTE_COLUMNS,
    PostgresVirtualQuoteRepository,
    run_virtual_quote_all_active_accounts_once,
    run_virtual_quote_once,
)


ROOT = Path(__file__).resolve().parents[1]
QUOTE_MINUTE = datetime(2026, 7, 16, 10, 5, tzinfo=timezone.utc)
FIXED_TIME = datetime(2026, 7, 16, 10, 5, 12, tzinfo=timezone.utc)
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_n6_virtual_quote_once",
    ROOT / "scripts/run_n6_virtual_quote_once.py",
)
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = RUNNER
RUNNER_SPEC.loader.exec_module(RUNNER)
RUNTIME_DIRECTORY = TemporaryDirectory()
SERVICE_FILE = Path(RUNTIME_DIRECTORY.name) / "pg_service.conf"
PASS_FILE = Path(RUNTIME_DIRECTORY.name) / ".pgpass"
for runtime_file in (SERVICE_FILE, PASS_FILE):
    runtime_file.write_text("", encoding="utf-8")
    runtime_file.chmod(0o600)
QUOTE_ENVIRONMENT = {
    "PGSERVICE": "n6_quote_writer",
    "PGSERVICEFILE": str(SERVICE_FILE),
    "PGPASSFILE": str(PASS_FILE),
}


class FakeAdapter:
    source_adapter = "mootdx.std"
    source_version = "fake-1"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[QuoteIdentity, ...]] = []

    def fetch_stock_quotes(self, identities):
        self.calls.append(tuple(identities))
        if self.fail:
            raise RuntimeError("fake provider failure")
        return [
            {
                "code": identity.stock_code,
                "market": 1 if identity.exchange == "SH" else 0,
                "price": "10.25",
                "last_close": "10.10",
                "open": "10.11",
                "high": "10.30",
                "low": "10.01",
                "servertime": "10:05:12",
            }
            for identity in identities
        ]


class FakeRepository:
    def __init__(self, identities=(), principal_scopes=None) -> None:
        self.identities = tuple(identities)
        self.principal_scopes = dict(principal_scopes or {})
        self.scope_calls = []
        self.saved: dict[tuple[str, datetime], object] = {}
        self.run_rows: dict[tuple[int, datetime], dict[str, object]] = {}

    def list_open_stock_identities(self, *, principal_id, principal_type):
        self.scope_calls.append((principal_id, principal_type))
        return self.identities

    def list_active_principal_stock_scopes(self, *, quote_minute):
        self.quote_scope_minute = quote_minute
        return self.principal_scopes

    def save_quote_run_and_batches(
        self,
        *,
        principal_id,
        principal_type,
        quote_minute,
        run_status,
        scoped_identity_count,
        passed_count,
        not_ready_count,
        started_at,
        completed_at,
        batches,
        scope_identity_keys=None,
    ):
        run_key = (principal_id, quote_minute)
        if run_key in self.run_rows:
            return 0
        inserted = 0
        allowed = set(scope_identity_keys or ())
        for batch in batches:
            for item in batch.items:
                if allowed and item.identity_key not in allowed:
                    continue
                key = (item.identity_key, quote_minute)
                if key not in self.saved:
                    self.saved[key] = item
                    inserted += 1
        self.run_rows[run_key] = {
            "run_status": run_status,
            "scoped_identity_count": scoped_identity_count,
            "passed_count": passed_count,
            "not_ready_count": not_ready_count,
            "inserted_snapshot_count": inserted,
            "started_at": started_at,
            "completed_at": completed_at,
            "batches": tuple(batches),
        }
        return inserted

    def fetch_latest_for_principal(self, *, principal_id, principal_type):
        raise AssertionError("not used by one-shot tests")


def identity(exchange: str, code: str) -> QuoteIdentity:
    return QuoteIdentity(
        identity_key=f"stock:{exchange}:{code}",
        exchange=exchange,  # type: ignore[arg-type]
        stock_code=code,
    )


def provider(adapter: FakeAdapter) -> QuoteProvider:
    return QuoteProvider(
        adapter,
        clock=lambda: FIXED_TIME,
        uuid_factory=lambda: UUID("00000000-0000-0000-0000-000000000001"),
    )


class VirtualQuotePersistenceTests(unittest.TestCase):
    def test_n6_default_quote_client_pins_versioned_primary(self) -> None:
        calls = []
        quote_calls = []

        class FakeClient:
            def quotes(self, *, symbol):
                quote_calls.append(symbol)
                return [
                    {
                        "code": "600211",
                        "market": 1,
                        "price": "39.40",
                        "last_close": "38.30",
                        "open": "38.48",
                        "high": "39.50",
                        "low": "38.28",
                        "servertime": "15:30:06.966",
                    }
                ]

        def factory(**kwargs):
            calls.append(kwargs)
            return FakeClient()

        provider_instance = build_n6_virtual_quote_provider(quotes_factory=factory)
        batch = provider_instance.fetch_quotes((identity("SH", "600211"),))

        self.assertEqual(batch.batch_status, "passed")
        self.assertEqual(batch.items[0].current_price, "39.40000000")
        self.assertEqual(quote_calls, [["600211"]])
        self.assertEqual(
            calls,
            [
                {
                    "market": "std",
                    "server": ("115.238.56.198", 7709),
                    "timeout": 5,
                    "raise_exception": True,
                    "auto_retry": False,
                    "heartbeat": False,
                }
            ],
        )
        self.assertTrue(
            batch.source_version.endswith(
                "|mootdx-endpoint-pool-v1|tdx-hq-primary-hz"
            )
        )

    def test_n6_quote_client_fails_over_after_empty_business_batch(self) -> None:
        calls = []
        closed = []

        class FakeClient:
            def __init__(self, server):
                self.server = server

            def quotes(self, *, symbol):
                if self.server == ("115.238.56.198", 7709):
                    return []
                return [{
                    "code": "600211", "market": 1,
                    "price": "39.40", "low": "38.28",
                    "last_close": "38.30", "open": "38.48",
                    "high": "39.50",
                    "servertime": "10:05:12",
                }]

            def close(self):
                closed.append(self.server)

        provider_instance = build_n6_virtual_quote_provider(
            quotes_factory=lambda **kwargs: (
                calls.append(kwargs["server"]) or FakeClient(kwargs["server"])
            )
        )
        batch = provider_instance.fetch_quotes((identity("SH", "600211"),))

        self.assertEqual(batch.batch_status, "passed")
        self.assertEqual(
            calls,
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )
        self.assertEqual(
            closed,
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )
        self.assertTrue(
            batch.source_version.endswith("|tdx-hq-secondary-sh")
        )

    def test_n6_quote_client_fails_over_after_batch_identity_corruption(
        self,
    ) -> None:
        calls = []

        class FakeClient:
            def __init__(self, server):
                self.server = server

            def quotes(self, *, symbol):
                code = (
                    "000001"
                    if self.server == ("115.238.56.198", 7709)
                    else "600211"
                )
                return [{
                    "code": code, "market": 1,
                    "price": "39.40", "low": "38.28",
                    "servertime": "10:05:12",
                }]

            def close(self):
                return None

        quote_provider = build_n6_virtual_quote_provider(
            quotes_factory=lambda **kwargs: (
                calls.append(kwargs["server"]) or FakeClient(kwargs["server"])
            )
        )
        batch = quote_provider.fetch_quotes((identity("SH", "600211"),))

        self.assertEqual(batch.batch_status, "passed")
        self.assertEqual(
            calls,
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )
        self.assertTrue(batch.source_version.endswith("|tdx-hq-secondary-sh"))

    def test_n6_quote_client_excludes_quarantined_endpoint(self) -> None:
        with TemporaryDirectory() as directory:
            pool = Path(directory) / "pool.toml"
            pool.write_text(
                """
endpoint_pool_version = "test-v1"
transport = "mootdx"
[[endpoints]]
endpoint_id = "bad"
host = "218.6.170.47"
port = 7709
priority = 1
enabled = false
quarantined = true
local_validation_status = "protocol_failed_quarantined"
[[endpoints]]
endpoint_id = "good"
host = "115.238.56.198"
port = 7709
priority = 2
enabled = true
quarantined = false
local_validation_status = "protocol_passed"
""".strip(),
                encoding="utf-8",
            )
            calls = []

            class FakeClient:
                def quotes(self, *, symbol):
                    return [{
                        "code": "600211", "market": 1,
                        "price": "39.40", "low": "38.28",
                        "servertime": "10:05:12",
                    }]

            provider_instance = build_n6_virtual_quote_provider(
                endpoint_pool_path=pool,
                quotes_factory=lambda **kwargs: (
                    calls.append(kwargs["server"]) or FakeClient()
                ),
            )
            batch = provider_instance.fetch_quotes((identity("SH", "600211"),))

        self.assertEqual(calls, [("115.238.56.198", 7709)])
        self.assertTrue(batch.source_version.endswith("|test-v1|good"))

    def test_n6_quote_client_fails_over_when_all_business_times_invalid(self) -> None:
        calls = []

        class FakeClient:
            def __init__(self, server):
                self.server = server

            def quotes(self, *, symbol):
                row = {
                    "code": "600211", "market": 1,
                    "price": "39.40", "low": "38.28",
                    "servertime": "10:05:12.123",
                }
                if self.server == ("115.238.56.198", 7709):
                    row["servertime"] = "2026-07-21 10:05:12"
                return [row]

            def close(self):
                return None

        provider_instance = build_n6_virtual_quote_provider(
            quotes_factory=lambda **kwargs: (
                calls.append(kwargs["server"]) or FakeClient(kwargs["server"])
            )
        )
        batch = provider_instance.fetch_quotes((identity("SH", "600211"),))

        self.assertEqual(batch.batch_status, "passed")
        self.assertEqual(
            calls,
            [("115.238.56.198", 7709), ("180.153.18.170", 7709)],
        )
        self.assertTrue(batch.source_version.endswith("|tdx-hq-secondary-sh"))

    def test_n6_source_time_canonicalization_is_strict(self) -> None:
        valid = {
            "9:30": "09:30",
            "9:30:01": "09:30:01",
            "9:57:20.200": "09:57:20.200",
            "09:30": "09:30",
            "10:00:00.001": "10:00:00.001",
            "23:59:59": "23:59:59",
        }
        for source, expected in valid.items():
            with self.subTest(source=source):
                self.assertEqual(
                    canonicalize_mootdx_source_time(source), expected
                )
        for invalid in (
            None, 95720, " 9:57", "9:7", "9:57 ",
            "2026-07-21 09:57:20", "24:00", "09:60", "09:59:60",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(canonicalize_mootdx_source_time(invalid))

    def test_n6_one_digit_hour_is_canonical_before_shared_provider(self) -> None:
        class FakeClient:
            def quotes(self, *, symbol):
                return [{
                    "code": "002371", "market": 0,
                    "price": "776.90", "low": "773.53",
                    "servertime": "9:57:20.200",
                }]

            def close(self):
                return None

        item = build_n6_virtual_quote_provider(
            quotes_factory=lambda **_kwargs: FakeClient()
        ).fetch_quotes((identity("SZ", "002371"),)).items[0]

        self.assertEqual(item.quality_status, "passed")
        self.assertEqual(item.source_time_text, "09:57:20.200")

    def test_n6_partial_invalid_item_does_not_trigger_endpoint_failover(self) -> None:
        calls = []

        class FakeClient:
            def quotes(self, *, symbol):
                return [
                    {
                        "code": "600211", "market": 1,
                        "price": "39.40", "low": "38.28",
                        "servertime": "9:57:20.200",
                    },
                    {
                        "code": "002371", "market": 0,
                        "price": "776.90", "low": "773.53",
                        "servertime": "2026-07-21 09:57:20",
                    },
                ]

            def close(self):
                return None

        provider_instance = build_n6_virtual_quote_provider(
            quotes_factory=lambda **kwargs: (
                calls.append(kwargs["server"]) or FakeClient()
            )
        )
        batch = provider_instance.fetch_quotes(
            (identity("SH", "600211"), identity("SZ", "002371"))
        )

        self.assertEqual(calls, [("115.238.56.198", 7709)])
        self.assertEqual(batch.batch_status, "partial")
        self.assertEqual(batch.items[0].quality_status, "passed")
        self.assertEqual(batch.items[1].quality_reason, "invalid_source_time")

    def test_n6_endpoint_attempt_log_is_sanitized(self) -> None:
        class FakeClient:
            def quotes(self, *, symbol):
                return [{
                    "code": "600211", "market": 1,
                    "price": "39.40", "low": "38.28",
                    "servertime": "10:05:12",
                }]

            def close(self):
                return None

        with self.assertLogs(
            "ashare_v3.user.n6_virtual_quote_client", level="INFO"
        ) as captured:
            build_n6_virtual_quote_provider(
                quotes_factory=lambda **_kwargs: FakeClient()
            ).fetch_quotes((identity("SH", "600211"),))
        record = "\n".join(captured.output)
        self.assertIn('"endpoint_id":"tdx-hq-primary-hz"', record)
        self.assertIn('"requested_count":1', record)
        self.assertNotIn("115.238.56.198", record)
        self.assertNotIn("39.40", record)

    def test_n6_mootdx_numeric_fields_are_canonical_numeric_24_8(self) -> None:
        class FakeClient:
            def quotes(self, *, symbol):
                return [{
                    "code": "600211", "market": 1,
                    "price": 31.330000000000002,
                    "last_close": 31.2,
                    "open": 31.25,
                    "high": 31.400000000000002,
                    "low": 31.150000000000002,
                    "servertime": "10:05:12.123",
                }]

        provider_instance = build_n6_virtual_quote_provider(
            quotes_factory=lambda **_kwargs: FakeClient()
        )
        item = provider_instance.fetch_quotes(
            (identity("SH", "600211"),)
        ).items[0]

        self.assertEqual(item.quality_status, "passed")
        self.assertEqual(item.current_price, "31.33000000")
        self.assertEqual(item.last_close, "31.20000000")
        self.assertEqual(item.day_high, "31.40000000")
        self.assertEqual(item.day_low, "31.15000000")

    def test_all_active_scope_sql_requires_active_principal_exact_join(self) -> None:
        class Cursor:
            def __init__(self) -> None:
                self.sql = ""

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def execute(self, sql, _params=None):
                self.sql = sql

            def fetchall(self):
                return []

        class Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def cursor(self):
                return self._cursor

        cursor = Cursor()
        with patch.object(
            quote_persistence_module.psycopg,
            "connect",
            return_value=Connection(cursor),
        ):
            result = PostgresVirtualQuoteRepository(
                "service=n6_quote_writer"
            ).list_active_principal_stock_scopes(quote_minute=QUOTE_MINUTE)

        normalized = " ".join(cursor.sql.split()).lower()
        self.assertEqual(result, {})
        self.assertIn("public.n6_quote_writer_pending_scope(%s)", normalized)

    def test_own_principal_scope_and_identity_dedup(self) -> None:
        sh = identity("SH", "600000")
        repo = FakeRepository((sh, sh, identity("SZ", "000001")))
        adapter = FakeAdapter()
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=7,
            principal_type="human_user",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual(repo.scope_calls, [(7, "human_user")])
        self.assertEqual([item.identity_key for item in adapter.calls[0]], [
            "stock:SH:600000",
            "stock:SZ:000001",
        ])
        self.assertEqual(result.requested_count, 2)
        self.assertEqual(result.inserted_count, 2)
        run = next(iter(repo.run_rows.values()))
        self.assertEqual(
            (
                run["run_status"],
                run["scoped_identity_count"],
                run["passed_count"],
                run["not_ready_count"],
                run["inserted_snapshot_count"],
            ),
            ("passed", 2, 2, 0, 2),
        )

    def test_more_than_80_identities_are_chunked(self) -> None:
        identities = tuple(identity("SH", f"6{number:05d}") for number in range(81))
        repo = FakeRepository(identities)
        adapter = FakeAdapter()
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual([len(call) for call in adapter.calls], [80, 1])
        self.assertEqual(result.batch_count, 2)

    def test_all_active_accounts_deduplicate_shared_identity_before_provider(self) -> None:
        shared = identity("SH", "600000")
        repo = FakeRepository(
            principal_scopes={
                (1, "admin"): (shared, identity("SZ", "000001")),
                (2, "human_user"): (shared,),
            }
        )
        adapter = FakeAdapter()

        result = run_virtual_quote_all_active_accounts_once(
            repository=repo,
            provider=provider(adapter),
            quote_minute=QUOTE_MINUTE,
            clock=lambda: FIXED_TIME,
        )

        self.assertEqual(len(adapter.calls), 2)
        self.assertEqual(
            sorted(
                item.identity_key for call in adapter.calls for item in call
            ),
            ["stock:SH:600000", "stock:SZ:000001"],
        )
        self.assertEqual(result.principal_count, 2)
        self.assertEqual(result.unique_identity_count, 2)
        self.assertEqual([item.requested_count for item in result.results], [2, 1])
        self.assertEqual(len(repo.saved), 2)
        self.assertEqual(len(repo.run_rows), 2)

    def test_all_active_accounts_empty_scope_has_no_provider_or_db_write(self) -> None:
        repo = FakeRepository(principal_scopes={})
        adapter = FakeAdapter()
        result = run_virtual_quote_all_active_accounts_once(
            repository=repo,
            provider=provider(adapter),
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual(result.status, "no_scope")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(repo.run_rows, {})

    def test_membership_groups_preserve_original_shared_batch_metadata(self) -> None:
        shared = identity("SH", "600000")
        only_p1 = identity("SZ", "000001")
        repo = FakeRepository(
            principal_scopes={
                (1, "admin"): (shared, only_p1),
                (2, "human_user"): (shared,),
            }
        )

        class SelectiveAdapter(FakeAdapter):
            def fetch_stock_quotes(self, identities):
                self.calls.append(tuple(identities))
                if identities[0].identity_key == only_p1.identity_key:
                    return []
                return [{
                    "code": identities[0].stock_code,
                    "market": 1,
                    "price": "10.25",
                    "last_close": "10.10",
                    "open": "10.11",
                    "high": "10.30",
                    "low": "10.01",
                    "servertime": "10:05:12",
                }]

        adapter = SelectiveAdapter()
        result = run_virtual_quote_all_active_accounts_once(
            repository=repo,
            provider=provider(adapter),
            quote_minute=QUOTE_MINUTE,
            clock=lambda: FIXED_TIME,
        )

        flattened_calls = [
            item.identity_key for call in adapter.calls for item in call
        ]
        self.assertEqual(sorted(flattened_calls), sorted({shared.identity_key, only_p1.identity_key}))
        self.assertEqual(len(flattened_calls), len(set(flattened_calls)))
        p1_batches = repo.run_rows[(1, QUOTE_MINUTE)]["batches"]
        p2_batches = repo.run_rows[(2, QUOTE_MINUTE)]["batches"]
        shared_p1 = next(
            batch for batch in p1_batches
            if batch.items[0].identity_key == shared.identity_key
        )
        self.assertIs(shared_p1, p2_batches[0])
        self.assertEqual(
            (shared_p1.batch_id, shared_p1.item_count, shared_p1.batch_status),
            (p2_batches[0].batch_id, p2_batches[0].item_count, p2_batches[0].batch_status),
        )
        self.assertEqual([item.status for item in result.results], ["partial", "passed"])

    def test_bj_is_persisted_not_ready_without_adapter_call(self) -> None:
        repo = FakeRepository((identity("BJ", "430001"),))
        adapter = FakeAdapter()
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual(adapter.calls, [])
        item = next(iter(repo.saved.values()))
        self.assertEqual(item.quality_status, "not_ready")
        self.assertEqual(item.quality_reason, "unsupported_exchange")
        self.assertEqual(result.status, "failed")
        run = next(iter(repo.run_rows.values()))
        self.assertEqual(
            (run["run_status"], run["passed_count"], run["not_ready_count"]),
            ("failed", 0, 1),
        )

    def test_mixed_sh_bj_only_calls_adapter_for_sh(self) -> None:
        repo = FakeRepository((identity("SH", "600000"), identity("BJ", "430001")))
        adapter = FakeAdapter()
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual([item.exchange for item in adapter.calls[0]], ["SH"])
        self.assertEqual(result.status, "partial")
        run = next(iter(repo.run_rows.values()))
        self.assertEqual(
            (run["run_status"], run["passed_count"], run["not_ready_count"]),
            ("partial", 1, 1),
        )

    def test_same_identity_and_minute_is_idempotent(self) -> None:
        repo = FakeRepository((identity("SH", "600000"),))
        adapter = FakeAdapter()
        first = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        second = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual(first.inserted_count, 1)
        self.assertEqual(second.inserted_count, 0)
        self.assertEqual(len(repo.saved), 1)
        self.assertEqual(len(repo.run_rows), 1)
        self.assertEqual(
            next(iter(repo.run_rows.values()))["inserted_snapshot_count"], 1
        )

    def test_provider_failure_is_not_ready_without_fallback(self) -> None:
        repo = FakeRepository((identity("SZ", "000001"),))
        adapter = FakeAdapter(fail=True)
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        item = next(iter(repo.saved.values()))
        self.assertEqual((item.quality_status, item.quality_reason), (
            "not_ready",
            "provider_error",
        ))
        self.assertEqual(result.status, "failed")

    def test_empty_scope_does_not_call_provider_or_write(self) -> None:
        repo = FakeRepository()
        adapter = FakeAdapter()
        result = run_virtual_quote_once(
            repository=repo,
            provider=provider(adapter),
            principal_id=1,
            principal_type="admin",
            quote_minute=QUOTE_MINUTE,
        )
        self.assertEqual(result.status, "no_scope")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(repo.saved, {})
        self.assertEqual(len(repo.run_rows), 1)
        run = next(iter(repo.run_rows.values()))
        self.assertEqual(
            (
                run["run_status"],
                run["scoped_identity_count"],
                run["passed_count"],
                run["not_ready_count"],
                run["inserted_snapshot_count"],
            ),
            ("no_scope", 0, 0, 0, 0),
        )

    def test_quote_minute_must_be_timezone_aware_and_aligned(self) -> None:
        repo = FakeRepository()
        adapter = FakeAdapter()
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            run_virtual_quote_once(
                repository=repo,
                provider=provider(adapter),
                principal_id=1,
                principal_type="admin",
                quote_minute=datetime(2026, 7, 16, 10, 5),
            )
        with self.assertRaisesRegex(ValueError, "minute-aligned"):
            run_virtual_quote_once(
                repository=repo,
                provider=provider(adapter),
                principal_id=1,
                principal_type="admin",
                quote_minute=FIXED_TIME,
            )

    def test_schema_freezes_unique_minute_and_latest_view(self) -> None:
        sql = (ROOT / "sql/040_n6_virtual_quote_snapshot_schema.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS n6_virtual_quote_run", sql)
        self.assertIn("UNIQUE (principal_id, quote_minute)", sql)
        self.assertIn(
            "run_status IN ('no_scope', 'passed', 'partial', 'failed')", sql
        )
        self.assertIn("scoped_identity_count = passed_count + not_ready_count", sql)
        self.assertIn("UNIQUE (identity_key, quote_minute)", sql)
        self.assertIn("CREATE OR REPLACE VIEW v_n6_virtual_quote_latest", sql)
        self.assertIn("'unsupported_exchange'", sql)
        snapshot_definition = sql.split(
            "CREATE TABLE IF NOT EXISTS n6_virtual_quote_snapshot", 1
        )[1].split("CREATE INDEX", 1)[0]
        self.assertNotIn("principal_id", snapshot_definition)
        self.assertNotIn("quote_run_id", snapshot_definition)

    def test_repository_is_principal_scoped_and_n6_only(self) -> None:
        source = (
            ROOT / "src/ashare_v3/user/virtual_quote_persistence.py"
        ).read_text()
        self.assertIn("p.principal_id = %s", source)
        self.assertIn("p.principal_type = %s", source)
        self.assertIn("a.principal_id = p.principal_id", source)
        self.assertIn("a.virtual_account_status = 'active'", source)
        self.assertIn("default_transaction_read_only=on", source)
        self.assertNotIn("SELECT *", source)
        self.assertNotIn("SELECT q.*", source)
        latest_select = source.split("SELECT q.virtual_quote_snapshot_id", 1)[1]
        latest_select = "q.virtual_quote_snapshot_id" + latest_select.split(
            "FROM v_n6_virtual_quote_latest", 1
        )[0]
        self.assertEqual(
            tuple(re.findall(r"q\.([a-z_]+)", latest_select)),
            LATEST_QUOTE_COLUMNS,
        )
        for forbidden in (
            "stock_realtime_daily_snapshot",
            "condition_pool",
            "common_trigger",
            "common_action",
            "common_event_outbox",
        ):
            self.assertNotIn(forbidden, source)

    def test_one_shot_constructs_only_committed_facade(self) -> None:
        source = (ROOT / "scripts/run_n6_virtual_quote_once.py").read_text()
        self.assertIn("build_n6_virtual_quote_provider", source)
        client_source = (
            ROOT / "src/ashare_v3/user/n6_virtual_quote_client.py"
        ).read_text()
        self.assertIn("QuoteProvider(", client_source)
        self.assertIn("N6MootdxStockQuoteAdapter(", client_source)
        self.assertNotIn("PROTOCOL_SENTINEL", client_source)
        self.assertIn("--execute", source)
        self.assertIn("--scheduled", source)
        self.assertNotIn("--all-active-accounts", source)
        self.assertNotIn("--principal-id", source)
        self.assertNotIn("--principal-type", source)
        self.assertNotIn("--dsn", source)
        self.assertIn("n6_quote_writer_is_open_trade_date", source)
        self.assertIn("default_transaction_read_only=on", source)
        self.assertNotIn("LaunchAgent", source)

    def test_scheduled_session_boundaries_and_minute_truncation(self) -> None:
        shanghai = RUNNER.ASIA_SHANGHAI
        self.assertEqual(
            RUNNER.scheduled_quote_minute(
                datetime(2026, 7, 16, 2, 5, 59, 999999, tzinfo=timezone.utc)
            ).isoformat(),
            "2026-07-16T10:05:00+08:00",
        )
        for hour, minute in ((9, 30), (11, 30), (13, 0), (15, 0)):
            self.assertTrue(
                RUNNER.is_trading_session(
                    datetime(2026, 7, 16, hour, minute, tzinfo=shanghai)
                )
            )
        for hour, minute in ((9, 29), (11, 31), (12, 59), (15, 1)):
            self.assertFalse(
                RUNNER.is_trading_session(
                    datetime(2026, 7, 16, hour, minute, tzinfo=shanghai)
                )
            )

    def test_scheduled_guards_no_op_before_repository_or_provider(self) -> None:
        calls = []

        def forbidden_factory(*args):
            calls.append(args)
            raise AssertionError("repository/provider must not be constructed")

        def held_lock(path):
            raise RUNNER.ScheduledLockHeld("scheduled_lock_held")

        base = argparse.Namespace(
            dsn="unused",
            principal_id=1,
            principal_type="admin",
            quote_minute="2026-07-16T09:29:59+08:00",
            execute=True,
            scheduled=True,
        )
        code, payload = RUNNER.run_from_args(
            base,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(base.quote_minute),
            trade_date_checker=lambda dsn, minute: True,
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual((code, payload["status"], payload["reason"]), (
            0,
            "no_op",
            "outside_trading_session",
        ))
        base.quote_minute = "2026-07-16T10:05:59+08:00"
        code, payload = RUNNER.run_from_args(
            base,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(base.quote_minute),
            trade_date_checker=lambda dsn, minute: False,
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual((code, payload["status"], payload["reason"]), (
            0,
            "no_op",
            "closed_trade_date",
        ))
        code, payload = RUNNER.run_from_args(
            base,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(base.quote_minute),
            trade_date_checker=lambda dsn, minute: True,
            lock_acquirer=held_lock,
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual((code, payload["status"], payload["reason"]), (
            0,
            "no_op",
            "scheduled_lock_held",
        ))
        self.assertEqual(calls, [])

    def test_scheduled_open_minute_runs_with_aligned_db_key(self) -> None:
        repo = FakeRepository()
        args = argparse.Namespace(
            dsn="unused",
            principal_id=1,
            principal_type="admin",
            quote_minute="2026-07-16T10:05:59.999999+08:00",
            execute=True,
            scheduled=True,
        )
        code, payload = RUNNER.run_from_args(
            args,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(args.quote_minute),
            trade_date_checker=lambda dsn, minute: True,
            lock_acquirer=lambda path: nullcontext(),
            repository_factory=lambda dsn: repo,
            provider_factory=lambda: provider(FakeAdapter()),
        )
        self.assertEqual((code, payload["status"]), (0, "no_scope"))
        self.assertEqual(payload["quote_minute"], "2026-07-16T10:05:00+08:00")
        self.assertEqual(repo.run_rows, {})

    def test_scheduled_process_lock_is_non_blocking(self) -> None:
        with TemporaryDirectory() as directory:
            lock_path = Path(directory) / "scheduled.lock"
            with RUNNER.acquire_scheduled_lock(lock_path):
                with self.assertRaisesRegex(RUNNER.ScheduledLockHeld, "scheduled_lock_held"):
                    with RUNNER.acquire_scheduled_lock(lock_path):
                        self.fail("second lock must not be acquired")

    def test_non_scheduled_path_cannot_bypass_session_or_global_lock(self) -> None:
        calls = []

        def forbidden_factory(*args):
            calls.append(args)
            raise AssertionError("guarded provider path must not construct dependencies")

        args = argparse.Namespace(
            quote_minute="2026-07-16T09:29:59+08:00",
            execute=True,
            scheduled=False,
        )
        code, payload = RUNNER.run_from_args(
            args,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(args.quote_minute),
            trade_date_checker=lambda conninfo, minute: True,
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual(
            (code, payload["reason"]), (0, "outside_trading_session")
        )
        args.quote_minute = "2026-07-16T10:05:59+08:00"
        code, payload = RUNNER.run_from_args(
            args,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(args.quote_minute),
            trade_date_checker=lambda conninfo, minute: True,
            lock_acquirer=lambda path: (_ for _ in ()).throw(
                RUNNER.ScheduledLockHeld("scheduled_lock_held")
            ),
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual((code, payload["reason"]), (0, "scheduled_lock_held"))
        self.assertEqual(calls, [])

    def test_same_day_historical_minute_never_constructs_provider(self) -> None:
        calls = []

        def forbidden_factory(*args):
            calls.append(args)
            raise AssertionError("historical minute must stop before provider")

        args = argparse.Namespace(
            quote_minute="2026-07-16T10:05:00+08:00",
            execute=True,
            scheduled=False,
        )
        code, payload = RUNNER.run_from_args(
            args,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(
                "2026-07-16T10:06:00+08:00"
            ),
            trade_date_checker=lambda conninfo, minute: True,
            repository_factory=forbidden_factory,
            provider_factory=forbidden_factory,
        )
        self.assertEqual((code, payload["reason"]), (0, "not_current_quote_minute"))
        self.assertEqual(calls, [])

    def test_all_active_runner_path_does_not_require_principal_arguments(self) -> None:
        repo = FakeRepository(principal_scopes={(1, "admin"): (identity("SH", "600000"),)})
        args = argparse.Namespace(
            dsn="unused",
            principal_id=None,
            principal_type=None,
            all_active_accounts=True,
            quote_minute="2026-07-16T10:05:00+08:00",
            execute=True,
            scheduled=False,
        )
        adapter = FakeAdapter()
        code, payload = RUNNER.run_from_args(
            args,
            environment=QUOTE_ENVIRONMENT,
            now_factory=lambda: datetime.fromisoformat(args.quote_minute),
            trade_date_checker=lambda conninfo, minute: True,
            lock_acquirer=lambda path: nullcontext(),
            repository_factory=lambda dsn: repo,
            provider_factory=lambda: provider(adapter),
        )
        self.assertEqual((code, payload["status"]), (0, "passed"))
        self.assertEqual(payload["principal_count"], 1)
        self.assertEqual(len(adapter.calls), 1)

    def test_quote_writer_wiring_is_exact_and_rejects_secret_overrides(self) -> None:
        self.assertEqual(
            RUNNER.quote_writer_conninfo(QUOTE_ENVIRONMENT),
            "service=n6_quote_writer",
        )
        for environment in (
            {},
            {"PGSERVICE": "postgres"},
            {"PGSERVICE": "n6_virtual_executor"},
            {**QUOTE_ENVIRONMENT, "PGPASSWORD": "redacted"},
            {**QUOTE_ENVIRONMENT, "PGUSER": "owner"},
            {**QUOTE_ENVIRONMENT, "N6_QUOTE_WRITER_DSN": "redacted"},
        ):
            with self.assertRaises(ValueError):
                RUNNER.quote_writer_conninfo(environment)
        with TemporaryDirectory() as directory:
            unsafe = Path(directory) / "unsafe.conf"
            unsafe.write_text("", encoding="utf-8")
            unsafe.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "owner/mode"):
                RUNNER.quote_writer_conninfo(
                    {
                        **QUOTE_ENVIRONMENT,
                        "PGSERVICEFILE": str(unsafe),
                    }
                )

    def test_five_second_cadence_has_multiple_pre_expiry_opportunities(self) -> None:
        self.assertEqual(RUNNER.SCHEDULER_CADENCE_SECONDS, 5)
        proposal_ttl_seconds = 60
        worst_case_wait_seconds = RUNNER.SCHEDULER_CADENCE_SECONDS
        guaranteed_follow_up_ticks = (
            proposal_ttl_seconds - 1
        ) // RUNNER.SCHEDULER_CADENCE_SECONDS
        self.assertLess(worst_case_wait_seconds, proposal_ttl_seconds)
        self.assertGreaterEqual(guaranteed_follow_up_ticks, 11)


if __name__ == "__main__":
    unittest.main()
