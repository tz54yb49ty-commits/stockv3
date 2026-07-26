from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.run_n6_ai_public_snapshot_once import (
    AI_PUBLIC_SNAPSHOT_RELATIVE_PATH,
    PUBLIC_SNAPSHOT_FEATURE_FLAG,
    PUBLIC_SNAPSHOT_FILE_ENV,
    PUBLIC_SNAPSHOT_IDENTITY_QUERY,
    PUBLIC_SNAPSHOT_QUERY,
    run_from_args,
    scrub_inherited_forbidden_environment,
)


class FakeCursor:
    def __init__(self, payload, identity):
        self.payload = payload
        self.identity = identity
        self.commands: list[str] = []
        self.closed = False

    def execute(self, command):
        self.commands.append(command)

    def fetchone(self):
        if self.commands[-1] == "SHOW default_transaction_read_only":
            return {"default_transaction_read_only": "on"}
        if self.commands[-1] == PUBLIC_SNAPSHOT_IDENTITY_QUERY:
            return {
                "session_user": self.identity,
                "current_user": self.identity,
            }
        if self.commands[-1] == PUBLIC_SNAPSHOT_QUERY:
            return {"payload": self.payload}
        raise AssertionError(self.commands[-1])

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, payload, identity):
        self.cursor_value = FakeCursor(payload, identity)
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


def raw_public_snapshot():
    return {
        "ok": True,
        "contract_version": "n6-ai-agent-public-v1",
        "profile": {
            "ai_user_id": 1,
            "ai_name": "AI模拟投资员",
            "ai_status": "active",
        },
        "account": {
            "virtual_account_id": 8,
            "account_name": "AI独立模拟账户",
            "account_status": "active",
            "currency": "CNY",
            "initial_cash": 100000000,
            "available_cash": 100000000,
            "frozen_cash": 0,
            "total_cash": 100000000,
            "position_market_value": 0,
            "total_asset_value": 100000000,
            "valuation_status": "ready",
        },
        "positions": [],
        "trades": [],
        "decisions": [],
        "daily_summaries": [],
        "performance": {},
        "strategy": {},
        "runtime": {},
    }


def server_policy_061():
    return {
        "policy_version": "n6_ai_agent_conservative_risk_v1",
        "allowed": True,
        "reason": "passed",
        "buy_budget_cny": 300000,
        "max_identity_exposure_cny": 600000,
        "max_total_exposure_ratio": 0.10,
        "max_daily_new_buys": 10,
        "pause_drawdown_pct": 5,
        "computed_by": "n6_ai_agent_shadow_decision_record",
    }


class N6AIPublicSnapshotPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "vault"
        self.target = self.root / AI_PUBLIC_SNAPSHOT_RELATIVE_PATH
        self.target.parent.mkdir(parents=True)
        self.service = Path(self.temporary.name) / "pg_service.conf"
        self.passfile = Path(self.temporary.name) / "n6_ai_agent.pgpass"
        self.service.write_bytes(b"service")
        self.passfile.write_bytes(b"pass")
        self.service.chmod(0o600)
        self.passfile.chmod(0o600)
        self.environment = {
            PUBLIC_SNAPSHOT_FEATURE_FLAG: "1",
            PUBLIC_SNAPSHOT_FILE_ENV: str(self.target),
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": str(self.service),
            "PGPASSFILE": str(self.passfile),
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _run(
        self,
        *,
        execute=True,
        payload=None,
        environment=None,
        identity="n6_ai_agent",
    ):
        connection = FakeConnection(
            raw_public_snapshot() if payload is None else payload,
            identity,
        )
        called = {"count": 0}

        def factory():
            called["count"] += 1
            return connection

        result = run_from_args(
            argparse.Namespace(execute=execute),
            environment=(
                self.environment
                if environment is None
                else environment
            ),
            connection_factory=factory,
            snapshot_root=self.root,
        )
        return result, connection, called["count"]

    def test_dry_run_has_no_database_or_file_side_effect(self):
        result, connection, calls = self._run(execute=False)
        self.assertEqual(result["status"], "dry_run_preflight")
        self.assertEqual(calls, 0)
        self.assertFalse(connection.closed)
        self.assertFalse(self.target.exists())

    def test_disabled_feature_has_no_database_or_file_side_effect(self):
        environment = dict(self.environment)
        environment.pop(PUBLIC_SNAPSHOT_FEATURE_FLAG)
        result, _, calls = self._run(environment=environment)
        self.assertEqual(result["status"], "feature_disabled")
        self.assertEqual(calls, 0)
        self.assertFalse(self.target.exists())

    def test_publishes_sanitized_snapshot_in_read_only_transaction(self):
        result, connection, calls = self._run()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "published")
        self.assertEqual(calls, 1)
        self.assertTrue(connection.closed)
        self.assertEqual(
            connection.cursor_value.commands,
            [
                "BEGIN READ ONLY",
                "SHOW default_transaction_read_only",
                PUBLIC_SNAPSHOT_IDENTITY_QUERY,
                PUBLIC_SNAPSHOT_QUERY,
                "ROLLBACK",
            ],
        )
        self.assertTrue(connection.cursor_value.closed)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        payload = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["public_scope"], "shared_ai_virtual_account"
        )
        self.assertTrue(payload["readonly"])
        self.assertFalse(payload["controls"]["proposal_enabled"])
        self.assertNotIn("session_token_hash", self.target.read_text())

    def test_existing_snapshot_is_atomically_replaced(self):
        self.target.write_text("old", encoding="utf-8")
        self.target.chmod(0o600)
        first, _, _ = self._run()
        first_bytes = self.target.read_bytes()
        payload = raw_public_snapshot()
        payload["account"]["available_cash"] = 99900000
        second, _, _ = self._run(payload=payload)
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertNotEqual(first_bytes, self.target.read_bytes())
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            list(self.target.parent.glob(".*.tmp")),
            [],
        )

    def test_061_server_policy_snapshot_is_atomically_published(self):
        self.target.write_text("old", encoding="utf-8")
        self.target.chmod(0o600)
        payload = raw_public_snapshot()
        payload["decisions"] = [
            {
                "ai_decision_id": 61,
                "decision_type": "hold",
                "reason_summary": "风险策略允许，但Shadow不创建申请。",
                "risk_assessment": {
                    "trigger": "signal",
                    "level": "low",
                    "summary": "server policy passed",
                    "server_policy": server_policy_061(),
                },
            }
        ]

        result, _, calls = self._run(payload=payload)

        self.assertEqual(calls, 1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["decision_count"], 1)
        published = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(
            published["decisions"][0]["risk_assessment"]["server_policy"],
            server_policy_061(),
        )
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.target.parent.glob(".*.tmp")), [])

    def test_null_authority_fails_without_file(self):
        result, connection, calls = self._run(payload="authority-null")
        self.assertEqual(calls, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "public_snapshot_authority_unavailable"
        )
        self.assertTrue(connection.closed)
        self.assertFalse(self.target.exists())

    def test_owner_database_identity_fails_closed(self):
        result, connection, calls = self._run(
            identity="ashare_v3_user"
        )
        self.assertEqual(calls, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "public_snapshot_publish_failed"
        )
        self.assertTrue(connection.closed)
        self.assertFalse(self.target.exists())

    def test_environment_and_credential_paths_fail_closed(self):
        mutations = {
            "wrong_service": {"PGSERVICE": "ashare_v3_user"},
            "password_env": {"PGPASSWORD": "secret"},
            "dsn_env": {"ASHARE_V3_POSTGRES_DSN": "secret"},
            "wrong_target": {
                PUBLIC_SNAPSHOT_FILE_ENV: str(
                    self.root / "other.json"
                )
            },
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                environment = dict(self.environment)
                environment.update(mutation)
                result, _, calls = self._run(environment=environment)
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reason"], "publisher_environment_invalid"
                )
                self.assertEqual(calls, 0)

    def test_main_boundary_scrubs_only_inherited_forbidden_environment(
        self,
    ):
        environment = dict(self.environment)
        environment.update(
            {
                "ASHARE_V3_POSTGRES_DSN": "owner-secret",
                "OPENAI_API_KEY": "model-secret",
            }
        )
        removed = scrub_inherited_forbidden_environment(environment)
        self.assertEqual(
            removed,
            ("ASHARE_V3_POSTGRES_DSN", "OPENAI_API_KEY"),
        )
        self.assertEqual(environment, self.environment)

    def test_credential_mode_fails_closed_without_connecting(self):
        self.passfile.chmod(0o644)
        result, _, calls = self._run()
        self.assertFalse(result["ok"])
        self.assertEqual(calls, 0)
        self.assertFalse(self.target.exists())

    def test_existing_target_symlink_fifo_or_bad_mode_fails_closed(self):
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text("unchanged", encoding="utf-8")
        cases = ("symlink", "fifo", "bad_mode")
        for case in cases:
            with self.subTest(case=case):
                if self.target.exists() or self.target.is_symlink():
                    self.target.unlink()
                if case == "symlink":
                    self.target.symlink_to(outside)
                elif case == "fifo":
                    os.mkfifo(self.target)
                else:
                    self.target.write_text("old", encoding="utf-8")
                    self.target.chmod(0o644)
                result, _, calls = self._run()
                self.assertEqual(calls, 1)
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reason"], "public_snapshot_publish_failed"
                )
                if self.target.exists() or self.target.is_symlink():
                    self.target.unlink()
        self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged")

    def test_group_writable_parent_fails_closed(self):
        self.target.parent.chmod(0o770)
        result, _, calls = self._run()
        self.assertEqual(calls, 1)
        self.assertFalse(result["ok"])
        self.assertFalse(self.target.exists())

    def test_source_has_no_business_dml_model_or_network_client(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts/run_n6_ai_public_snapshot_once.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "INSERT INTO",
            "UPDATE public.",
            "DELETE FROM",
            "openai",
            "requests",
            "urllib",
            "socket",
            "launchctl",
            "n6_virtual_executor",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
